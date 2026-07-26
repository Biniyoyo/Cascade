"""CASCADE agent: runs an incident through Claude + the DataHub MCP server."""
from __future__ import annotations

import os
import re
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
)

from cascade.prompts import SYSTEM_PROMPT
from cascade.tools import CASCADE_TOOLS_SERVER, LAST, reset_last

DATAHUB_MCP = {
    "type": "stdio",
    "command": "uvx",
    "args": ["mcp-server-datahub@latest"],
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


def _short(name: str) -> str:
    return name.replace("mcp__datahub__", "").replace("mcp__cascade__", "")


async def run_incident(incident_text: str, max_budget_usd: float = 1.0,
                       model: str = DEV_MODEL, quiet: bool = False) -> dict:
    """Run one incident end-to-end. Streams to stdout and returns a rich result:
    { final_text, tools_used, cost_usd, incident_urn, steps[] } where steps is an
    ordered trace the UI can replay: text reasoning, tool calls, tool results."""
    options = build_options(max_budget_usd, model=model)
    reset_last()
    tools_used: list[str] = []
    steps: list[dict] = []
    final_text = ""
    cost = 0.0

    async for msg in query(prompt=incident_text, options=options):
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
            "steps": steps}
