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

DATAHUB_MCP = {
    "type": "stdio",
    "command": "uvx",
    # Pinned for reproducible deploys (latest on PyPI as of 2026-07-26).
    "args": ["mcp-server-datahub==0.6.0"],
    "env": {
        "DATAHUB_GMS_URL": os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080"),
        "DATAHUB_GMS_TOKEN": os.environ.get("DATAHUB_GMS_TOKEN", "dummy-local"),
        "TOOLS_IS_MUTATION_ENABLED": "true",
    },
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
    return ClaudeAgentOptions(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"datahub": DATAHUB_MCP, "cascade": CASCADE_TOOLS_SERVER},
        allowed_tools=ALLOWED_TOOLS,
        permission_mode="bypassPermissions",  # autonomous tool use
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
        mcp_servers={"datahub": DATAHUB_MCP, "cascade": CASCADE_TOOLS_SERVER},
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
                        text = " ".join(getattr(c, "text", "") for c in block.content)
                    elif isinstance(block.content, str):
                        text = block.content
                    steps.append({"kind": "tool_result", "text": text[:4000]})
        elif isinstance(msg, ResultMessage):
            final_text = getattr(msg, "result", "") or final_text
            cost = getattr(msg, "total_cost_usd", 0.0) or 0.0

    return {"final_text": final_text, "tools_used": tools_used, "cost_usd": cost,
            "incident_urn": LAST["incident"], "assertion_urn": LAST["assertion"],
            "steps": steps, "audit": audit, "proposed_writes": proposed_writes}
