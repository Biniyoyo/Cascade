"""PROPOSED CONTRIBUTION to acryldata/mcp-server-datahub.

Adds incident write tools — the primitive the MCP server currently lacks. Its
mutation tools stop at tags/terms/owners/descriptions; DataHub's native Incidents
API (raiseIncident / updateIncidentStatus) is not exposed to agents. This module
adds `raise_incident` and `update_incident_status`, gated behind the existing
TOOLS_IS_MUTATION_ENABLED flag, so agents can close the incident-response loop.

Drop-in shape mirrors the server's existing tool registration; wire into
register_mutation_tools(). Uses the same GraphQL client the server already holds.
"""
from __future__ import annotations

from typing import Optional

# The server passes its GraphQL executor; signature matches existing tools.

RAISE_INCIDENT = """mutation raiseIncident($input: RaiseIncidentInput!) {
  raiseIncident(input: $input)
}"""

UPDATE_STATUS = """mutation updateIncidentStatus($urn: String!, $input: IncidentStatusInput!) {
  updateIncidentStatus(urn: $urn, input: $input)
}"""

VALID_PRIORITY = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


def register_incident_tools(mcp, execute_graphql):
    """Call from register_mutation_tools(...) when TOOLS_IS_MUTATION_ENABLED."""

    @mcp.tool()
    def raise_incident(
        resource_urn: str,
        title: str,
        description: str,
        type: str = "OPERATIONAL",
        priority: Optional[str] = None,
    ) -> str:
        """Raise a native DataHub incident on an asset (appears on its Incidents
        tab and drives health signals). priority: CRITICAL|HIGH|MEDIUM|LOW."""
        inp: dict = {"type": type, "title": title,
                     "description": description, "resourceUrn": resource_urn}
        if priority:
            p = priority.upper()
            if p not in VALID_PRIORITY:
                raise ValueError(f"priority must be one of {VALID_PRIORITY}")
            inp["priority"] = p
        data = execute_graphql(RAISE_INCIDENT, {"input": inp})
        return data["raiseIncident"]  # the new incident URN

    @mcp.tool()
    def update_incident_status(urn: str, state: str,
                               message: str = "") -> bool:
        """Update an incident's status. state: ACTIVE|RESOLVED."""
        execute_graphql(UPDATE_STATUS,
                        {"urn": urn, "input": {"state": state.upper(), "message": message}})
        return True

    return [raise_incident, update_incident_status]
