"""The official DataHub MCP server's tools, embedded in-process.

Wraps the exact tool functions from the `mcp-server-datahub` package (pinned in
requirements) and serves them through the Agent SDK's in-process MCP mechanism —
same tool names, same behavior, same GraphQL calls as the standalone server.

Why embedded: the standalone server's stdio/http startup (heavy acryl-datahub
import) races the CLI's tool snapshot on some CLI versions, leaving the agent
without its DataHub tools. In-process registration is deterministic: the tools
exist the moment the conversation starts. Schemas are generated from the
package functions' real signatures, so behavior tracks the pinned upstream
version rather than a hand-maintained copy.
"""
from __future__ import annotations

import inspect
import json
import os
import typing

os.environ.setdefault("DATAHUB_TELEMETRY_ENABLED", "false")

from claude_agent_sdk import tool, create_sdk_mcp_server  # noqa: E402

from datahub.sdk.main_client import DataHubClient  # noqa: E402
from mcp_server_datahub.graphql_helpers import set_datahub_client  # noqa: E402
from mcp_server_datahub.tools.search import search  # noqa: E402
from mcp_server_datahub.tools.lineage import (  # noqa: E402
    get_lineage, get_lineage_paths_between)
from mcp_server_datahub.tools.entities import (  # noqa: E402
    get_entities, list_schema_fields)
from mcp_server_datahub.tools.descriptions import update_description  # noqa: E402
from mcp_server_datahub.tools.dataset_queries import get_dataset_queries  # noqa: E402

MAX_RESULT_CHARS = 60_000  # keep giant lineage payloads inside the agent context

_client: DataHubClient | None = None


def _ensure_client() -> None:
    global _client
    if _client is None:
        _client = DataHubClient.from_env()
        set_datahub_client(_client)


def _json_type(ann) -> dict:
    origin = typing.get_origin(ann)
    if ann in (str,):
        return {"type": "string"}
    if ann in (int,):
        return {"type": "integer"}
    if ann in (bool,):
        return {"type": "boolean"}
    if origin is typing.Literal:
        return {"type": "string", "enum": [str(a) for a in typing.get_args(ann)]}
    if origin is typing.Union:
        args = [a for a in typing.get_args(ann) if a is not type(None)]
        if len(args) == 1:
            return _json_type(args[0])
        return {}  # permissive for List[str] | str etc.
    if origin in (list, typing.List):
        return {"type": "array"}
    return {}


def _schema_for(fn) -> dict:
    sig = inspect.signature(fn)
    try:
        hints = typing.get_type_hints(fn)
    except Exception:  # noqa: BLE001
        hints = {}
    props, required = {}, []
    for name, p in sig.parameters.items():
        props[name] = _json_type(hints.get(name, str))
        if p.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": props, "required": required}


def _wrap(fn):
    sig = inspect.signature(fn)

    async def handler(args: dict):
        _ensure_client()
        # ContextVars don't survive the SDK's per-call task contexts — rebind
        # the package's client context on every invocation (idempotent).
        set_datahub_client(_client)
        kwargs = {k: v for k, v in (args or {}).items() if k in sig.parameters}
        try:
            result = fn(**kwargs)
            text = result if isinstance(result, str) else json.dumps(
                result, indent=1, default=str)
        except Exception as e:  # noqa: BLE001
            text = f"Error from {fn.__name__}: {e}"
        if len(text) > MAX_RESULT_CHARS:
            text = (text[:MAX_RESULT_CHARS]
                    + f"\n... [truncated at {MAX_RESULT_CHARS} chars — narrow the "
                      "query (column filter, max_hops, limit/offset) for the rest]")
        return {"content": [{"type": "text", "text": text}]}

    doc = (inspect.getdoc(fn) or fn.__name__).strip()
    return tool(fn.__name__, doc[:900], _schema_for(fn))(handler)


_TOOLS = [search, get_lineage, get_lineage_paths_between, get_entities,
          list_schema_fields, update_description, get_dataset_queries]

EMBEDDED_DATAHUB_SERVER = create_sdk_mcp_server(
    name="datahub", version="0.5.3-embedded", tools=[_wrap(f) for f in _TOOLS])
