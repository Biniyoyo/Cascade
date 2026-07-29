"""CASCADE's own in-process MCP tools — the capabilities the DataHub MCP server
lacks. These wrap the native Incidents API + ownership lookup so the agent can
raise real incidents and route them, autonomously. This is also the reference
implementation for the `raise_incident` tool we contribute upstream."""
from __future__ import annotations

from claude_agent_sdk import tool, create_sdk_mcp_server

from cascade import datahub_incidents as di

# In-process record of what the agent wrote this run (SDK MCP tools run in the same
# process), so the runner captures the exact URNs — no fragile text parsing.
LAST = {"incident": None, "assertion": None}

MAX_AUTO_ASSIGNEES = 5


def reset_last():
    LAST["incident"] = None
    LAST["assertion"] = None


def _owner_urns(resource_urn: str) -> list[str]:
    """Assignable owner URNs from DataHub's ownership graph, most-accountable
    first (technical owner / steward before generic business owner)."""
    rank = {"TECHNICAL_OWNER": 0, "DATA_STEWARD": 1, "BUSINESS_OWNER": 2}
    owners = [o for o in di.get_owners(resource_urn)
              if (o.get("urn") or "").startswith("urn:li:corp")]
    owners.sort(key=lambda o: rank.get(o.get("ownership_type", ""), 3))
    seen, urns = set(), []
    for o in owners:
        if o["urn"] not in seen:
            seen.add(o["urn"])
            urns.append(o["urn"])
    return urns[:MAX_AUTO_ASSIGNEES]


@tool(
    "raise_incident",
    "Raise a REAL native DataHub incident on an asset. It appears on the asset's "
    "Incidents tab and drives DataHub health signals. Call this once you have "
    "confirmed the root cause, to formally open the incident. "
    "priority is one of CRITICAL, HIGH, MEDIUM, LOW. assignee_urns (optional) "
    "assigns the incident to the routed owners' corpuser/corpGroup URNs.",
    {"resource_urn": str, "title": str, "description": str, "priority": str,
     "assignee_urns": list},
)
async def raise_incident(args):
    # Routing is a property of the graph, not of the model remembering to ask
    # for it: when the agent doesn't name assignees, fall back to the asset's
    # own owners so every incident lands on a real person or team.
    assignees = [u for u in (args.get("assignee_urns") or [])
                 if isinstance(u, str) and u.startswith("urn:li:corp")]
    auto_routed = False
    if not assignees:
        assignees = _owner_urns(args["resource_urn"])
        auto_routed = bool(assignees)

    urn = di.raise_incident(
        args["resource_urn"], args["title"], args["description"],
        priority=(args.get("priority") or "HIGH"),
        assignee_urns=assignees or None,
    )
    LAST["incident"] = urn
    routed = (f" Assigned to {len(assignees)} owner(s) from DataHub's ownership graph"
              f"{' (auto-routed)' if auto_routed else ''}: {', '.join(assignees)}."
              if assignees else " No owners found on the asset — incident is unassigned.")
    return {"content": [{"type": "text",
                         "text": f"Raised native DataHub incident {urn} on "
                                 f"{args['resource_urn']}.{routed}"}]}


@tool(
    "get_owners",
    "List the owners of a DataHub asset (people and teams, with their ownership "
    "role) so the incident can be routed to whoever is responsible.",
    {"resource_urn": str},
)
async def get_owners(args):
    owners = di.get_owners(args["resource_urn"])
    if not owners:
        return {"content": [{"type": "text", "text": "No owners found for this asset."}]}
    lines = [f"- {o['name']} ({o['ownership_type']}, {o['kind']}) urn={o.get('urn','?')}"
             for o in owners]
    return {"content": [{"type": "text", "text": "Owners:\n" + "\n".join(lines)}]}


@tool(
    "create_assertion",
    "Create a data-quality assertion on a column to PREVENT the incident from "
    "recurring (e.g. a NOT NULL guard). Call this as part of remediation once the "
    "root cause is known. logic is a short predicate (e.g. 'billing_country IS NOT NULL').",
    {"dataset_urn": str, "field_path": str, "description": str, "logic": str},
)
async def create_assertion(args):
    urn = di.create_field_assertion(
        args["dataset_urn"], args["field_path"], args["description"], args["logic"])
    LAST["assertion"] = urn
    return {"content": [{"type": "text",
                         "text": f"Created data-quality assertion {urn} guarding "
                                 f"{args['field_path']} on {args['dataset_urn']}"}]}


CASCADE_TOOLS_SERVER = create_sdk_mcp_server(
    "cascade", version="0.1.0",
    tools=[raise_incident, get_owners, create_assertion],
)
