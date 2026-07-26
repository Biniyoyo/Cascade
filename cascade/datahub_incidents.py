"""Native DataHub Incidents client + ownership lookup.

The DataHub MCP server exposes read tools and light mutations (tags, descriptions,
owners) but *no* incident tools. CASCADE needs to raise real, native incidents so
they appear on the asset's Incidents tab and drive DataHub's health signals — the
loop DataHub's own agent stack can't close today. This thin GraphQL client provides
that, and is the basis for the `raise_incident` MCP tool we contribute upstream.

Talks to the GMS GraphQL endpoint (``$DATAHUB_GMS_URL/api/graphql``).
"""
from __future__ import annotations

import os
import re
from typing import Any, Optional

import requests


def _endpoint() -> str:
    base = os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080").rstrip("/")
    return f"{base}/api/graphql"


def _headers() -> dict:
    token = os.environ.get("DATAHUB_GMS_TOKEN", "dummy-local")
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        # Local quickstart has auth disabled; naming the actor keeps writes attributed.
        "X-DataHub-Actor": os.environ.get("DATAHUB_ACTOR", "urn:li:corpuser:datahub"),
    }


def _gql(query: str, variables: Optional[dict] = None) -> dict:
    resp = requests.post(_endpoint(), headers=_headers(),
                         json={"query": query, "variables": variables or {}}, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    if body.get("errors"):
        raise RuntimeError(f"DataHub GraphQL error: {body['errors']}")
    return body.get("data", {})


# ── Incidents ────────────────────────────────────────────────────────────
_RAISE = """mutation raiseIncident($input: RaiseIncidentInput!) {
  raiseIncident(input: $input)
}"""

_UPDATE_STATUS = """mutation updateIncidentStatus($urn: String!, $input: IncidentStatusInput!) {
  updateIncidentStatus(urn: $urn, input: $input)
}"""

_LIST = """query incidents($urn: String!) {
  dataset(urn: $urn) {
    incidents(start: 0, count: 20) {
      total
      incidents { urn title description incidentType status { state message } }
    }
  }
}"""


PRIORITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


def raise_incident(resource_urn: str, title: str, description: str,
                   incident_type: str = "OPERATIONAL",
                   priority: Optional[str] = None) -> str:
    """Raise a native DataHub incident on an asset. Returns the incident URN.
    priority is an enum: CRITICAL | HIGH | MEDIUM | LOW."""
    inp: dict[str, Any] = {
        "type": incident_type,
        "title": title,
        "description": description,
        "resourceUrn": resource_urn,
    }
    if priority:
        p = priority.upper()
        if p not in PRIORITIES:
            raise ValueError(f"priority must be one of {PRIORITIES}, got {priority!r}")
        inp["priority"] = p
    return _gql(_RAISE, {"input": inp})["raiseIncident"]


def resolve_incident(incident_urn: str, message: str = "Resolved by CASCADE") -> bool:
    """Mark an incident RESOLVED."""
    _gql(_UPDATE_STATUS, {"urn": incident_urn,
                          "input": {"state": "RESOLVED", "message": message}})
    return True


def list_incidents(resource_urn: str) -> list[dict]:
    data = _gql(_LIST, {"urn": resource_urn})
    return (data.get("dataset") or {}).get("incidents", {}).get("incidents", [])


# ── Assertions (remediation: prevent recurrence) ─────────────────────────
_UPSERT_ASSERTION = """mutation upsertCustom($urn: String!, $input: UpsertCustomAssertionInput!) {
  upsertCustomAssertion(urn: $urn, input: $input) { urn }
}"""


def _platform_from_dataset(urn: str) -> str:
    # urn:li:dataset:(urn:li:dataPlatform:dbt,...) -> "dbt"
    m = re.search(r"dataPlatform:([a-zA-Z0-9_-]+)", urn)
    return m.group(1) if m else "dbt"


def create_field_assertion(dataset_urn: str, field_path: str, description: str,
                           logic: str) -> str:
    """Create a custom data-quality assertion on a column (e.g. NOT NULL) so the
    incident's root problem is guarded against recurrence. Returns assertion URN."""
    import uuid
    aurn = "urn:li:assertion:cascade-" + uuid.uuid4().hex[:12]
    inp = {
        "entityUrn": dataset_urn,
        "type": "CASCADE data-quality guard",
        "description": description,
        "fieldPath": field_path,
        "platform": {"name": _platform_from_dataset(dataset_urn)},
        "logic": logic,
    }
    return _gql(_UPSERT_ASSERTION, {"urn": aurn, "input": inp})["upsertCustomAssertion"]["urn"]


# ── Ownership (for routing) ──────────────────────────────────────────────
_OWNERS = """query owners($urn: String!) {
  dataset(urn: $urn) {
    ownership { owners {
      ownershipType { urn }
      owner {
        __typename
        ... on CorpUser  { urn properties { displayName email } }
        ... on CorpGroup { urn properties { displayName } }
      }
    } }
  }
}"""


def get_owners(resource_urn: str) -> list[dict]:
    """Return a simple list of owners: [{urn, name, kind, ownership_type}]."""
    data = _gql(_OWNERS, {"urn": resource_urn})
    owners = ((data.get("dataset") or {}).get("ownership") or {}).get("owners", []) or []
    out = []
    for o in owners:
        ow = o.get("owner") or {}
        props = ow.get("properties") or {}
        out.append({
            "urn": ow.get("urn"),
            "name": props.get("displayName") or ow.get("urn"),
            "kind": ow.get("__typename"),
            "ownership_type": (o.get("ownershipType") or {}).get("urn", "").split("__")[-1],
        })
    return out
