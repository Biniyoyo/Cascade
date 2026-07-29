"""CASCADE agent: runs an incident through Claude + the DataHub MCP server."""
from __future__ import annotations

import os
import warnings
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    UserMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    PermissionResultAllow,
    PermissionResultDeny,
)

from cascade.prompts import SYSTEM_PROMPT
from cascade.tools import CASCADE_TOOLS_SERVER, LAST, reset_last
from cascade.datahub_embedded import EMBEDDED_DATAHUB_SERVER

# Give stdio MCP servers time to finish their (heavy) startup before the
# conversation's tool snapshot is taken — the DataHub server imports the full
# acryl-datahub SDK (~4s).
os.environ.setdefault("MCP_TIMEOUT", "45000")
os.environ.setdefault("MCP_TOOL_TIMEOUT", "120000")

DATAHUB_MCP = {
    # Streamable-HTTP transport against a persistent warm server instance —
    # stdio spawn was too slow (heavy acryl-datahub import) for the SDK's
    # startup tool snapshot. Start it once per machine:
    #   scripts/start_mcp_server.sh   (or see README quickstart)
    "type": "sse",
    "url": os.environ.get("DATAHUB_MCP_URL", "http://127.0.0.1:8000/sse"),
}

# Read + writeback tools CASCADE is allowed to call, autonomously.
ALLOWED_TOOLS = [
    # DataHub MCP (read + light writes)
    "mcp__datahub__search",
    "mcp__datahub__get_lineage",
    "mcp__datahub__get_lineage_paths_between",
    "mcp__datahub__list_schema_fields",
    "mcp__datahub__get_entities",
    "mcp__datahub__get_dataset_queries",
    "mcp__datahub__update_description",
    # CASCADE's own tools (native incidents + owner routing + assertion guard)
    "mcp__cascade__raise_incident",
    "mcp__cascade__get_owners",
    "mcp__cascade__create_assertion",
]

# The three tools that mutate the graph — everything else CASCADE touches is
# read-only. Propose mode intercepts exactly these; the audit trail records
# exactly these. (Full MCP names, as seen by the permission system.)
WRITE_TOOLS = {
    "mcp__cascade__raise_incident",
    "mcp__cascade__create_assertion",
    "mcp__datahub__update_description",
}

PROPOSE_NOTE = (
    "\n\nPROPOSE MODE: do not execute writes. Any write tool you call will be "
    "intercepted and recorded as a proposal instead of executing. End your report "
    "with a 'PROPOSED ACTIONS' section listing the exact tool calls (tool name + "
    "arguments) you would make."
)


# Cheap model for development/testing; premium model for the final demo runs.
DEV_MODEL = "claude-haiku-4-5-20251001"      # ~10x cheaper — default while building
FINAL_MODEL = "claude-sonnet-5"              # sharper reasoning for the recorded demo


def build_options(max_budget_usd: float = 1.0,
                  model: str = DEV_MODEL) -> ClaudeAgentOptions:
    """ACT mode, strictly sandboxed: `tools=[]` removes every built-in tool
    (Bash, file tools, ToolSearch, ...), so the ONLY tools that exist are the
    DataHub MCP server's and CASCADE's own — which `allowed_tools` then
    auto-approves for autonomous use. This enforces the restricted toolset
    without a permission callback (which would force streaming input and, with
    this SDK version, interferes with stdio MCP server attachment)."""
    return ClaudeAgentOptions(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[],                             # no built-ins — MCP tools only
        mcp_servers={"datahub": EMBEDDED_DATAHUB_SERVER, "cascade": CASCADE_TOOLS_SERVER},
        allowed_tools=ALLOWED_TOOLS,
        permission_mode="bypassPermissions",  # safe: only the MCP toolset exists
        max_budget_usd=max_budget_usd,        # hard spend cap per run
        max_turns=40,
    )


def build_propose_options(max_budget_usd: float, model: str,
                          proposed_writes: list[dict]) -> ClaudeAgentOptions:
    """Options for PROPOSE mode: same read access, but the write tools are NOT
    auto-approved — they fall through to a `can_use_tool` permission callback
    (claude-agent-sdk >= 0.2) that records the exact intended call into
    `proposed_writes` and denies execution. Two SDK constraints shape this:
    the callback is never consulted under permission_mode='bypassPermissions',
    and a whole-tool allowed_tools entry auto-approves before the callback runs
    — so writes are removed from the allowlist and the mode is 'default'."""

    async def gate(tool_name, tool_input, _context):
        if tool_name in WRITE_TOOLS:
            proposed_writes.append({"tool": _short(tool_name), "input": tool_input})
            return PermissionResultDeny(
                message=(f"PROPOSE MODE: recorded as proposed action "
                         f"#{len(proposed_writes)} — NOT executed. Do not retry; "
                         "continue, and list this call in your PROPOSED ACTIONS "
                         "section."))
        return PermissionResultAllow()

    # Read tools stay whole-tool allowlisted, which shadows the callback for
    # them (auto-approved before it is consulted). That is intentional — only
    # writes are gated — so silence the SDK's advisory warning about it.
    warnings.filterwarnings("ignore", message=r"can_use_tool will not be invoked for")

    return ClaudeAgentOptions(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"datahub": EMBEDDED_DATAHUB_SERVER, "cascade": CASCADE_TOOLS_SERVER},
        allowed_tools=[t for t in ALLOWED_TOOLS if t not in WRITE_TOOLS],
        permission_mode="default",     # writes fall through to the gate above
        can_use_tool=gate,
        max_budget_usd=max_budget_usd,
        max_turns=40,
    )


async def _as_stream(text: str):
    """can_use_tool requires streaming-mode input (the SDK rejects a plain
    string prompt when a permission callback is set), so wrap the single
    incident prompt in a one-message async iterable."""
    yield {"type": "user", "message": {"role": "user", "content": text},
           "parent_tool_use_id": None, "session_id": "default"}


def _short(name: str) -> str:
    return name.replace("mcp__datahub__", "").replace("mcp__cascade__", "")


async def run_incident(incident_text: str, max_budget_usd: float = 1.0,
                       model: str = DEV_MODEL, quiet: bool = False,
                       propose: bool = False) -> dict:
    """Run one incident end-to-end. Streams to stdout and returns a rich result:
    { final_text, tools_used, cost_usd, incident_urn, steps[], audit[],
    proposed_writes[] } where steps is an ordered trace the UI can replay:
    text reasoning, tool calls, tool results.

    audit[] records every write-tool call ({ts, tool, input, executed}) so
    callers can persist a who/what/when trail.

    propose=True is a dry run: the agent investigates with full read access,
    but the three write tools are intercepted by a permission callback and
    collected into result["proposed_writes"] instead of executing — a human
    confirms and applies them. propose=False is byte-identical to the
    original autonomous behavior."""
    proposed_writes: list[dict] = []
    if propose:
        options = build_propose_options(max_budget_usd, model=model,
                                        proposed_writes=proposed_writes)
        prompt = _as_stream(incident_text + PROPOSE_NOTE)
    else:
        options = build_options(max_budget_usd, model=model)
        prompt = incident_text
    reset_last()
    tools_used: list[str] = []
    steps: list[dict] = []
    audit: list[dict] = []
    final_text = ""
    cost = 0.0

    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    steps.append({"kind": "text", "text": block.text})
                    if not quiet:
                        print(block.text, flush=True)
                elif isinstance(block, ToolUseBlock):
                    name = _short(block.name)
                    tools_used.append(name)
                    steps.append({"kind": "tool_use", "tool": name, "input": block.input})
                    if block.name in WRITE_TOOLS:
                        audit.append({
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "tool": name,
                            "input": block.input,
                            "executed": not propose,
                        })
                    if not quiet:
                        print(f"  \033[36m→ {name}({str(block.input)[:100]})\033[0m", flush=True)
        elif isinstance(msg, UserMessage):
            for block in getattr(msg, "content", []) or []:
                if isinstance(block, ToolResultBlock):
                    text = ""
                    if isinstance(block.content, list):
                        text = " ".join(
                            (c.get("text", "") if isinstance(c, dict)
                             else getattr(c, "text", "")) for c in block.content)
                    elif isinstance(block.content, str):
                        text = block.content
                    steps.append({"kind": "tool_result", "text": text[:4000]})
        elif isinstance(msg, ResultMessage):
            final_text = getattr(msg, "result", "") or final_text
            cost = getattr(msg, "total_cost_usd", 0.0) or 0.0

    return {"final_text": final_text, "tools_used": tools_used, "cost_usd": cost,
            "incident_urn": LAST["incident"], "assertion_urn": LAST["assertion"],
            "steps": steps, "audit": audit, "proposed_writes": proposed_writes}
