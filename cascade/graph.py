"""Blast-radius graph builder — pulls a simplified downstream lineage graph from
DataHub for the UI visualization. Precomputed at build time so the deployed app
serves it statically (no live DataHub needed for the cached demo)."""
from __future__ import annotations

from cascade.datahub_incidents import _gql

_LINEAGE = """
query blast($urn: String!, $direction: LineageDirection!) {
  searchAcrossLineage(input: {
    urn: $urn, direction: $direction, query: "*", start: 0, count: 60
  }) {
    total
    searchResults {
      degree
      entity {
        urn
        type
        ... on Dataset  { name platform { name properties { displayName } } }
        ... on Dashboard { properties { name } platform { name properties { displayName } } }
        ... on Chart     { properties { name } platform { name properties { displayName } } }
      }
    }
  }
}"""


def _name(e: dict) -> str:
    return e.get("name") or (e.get("properties") or {}).get("name") or e.get("urn", "").split(",")[-2:][0]


def _platform(e: dict) -> str:
    p = e.get("platform") or {}
    return ((p.get("properties") or {}).get("displayName")) or p.get("name") or ""


def _nodes(urn: str, direction: str) -> list[dict]:
    data = _gql(_LINEAGE, {"urn": urn, "direction": direction})
    res = (data.get("searchAcrossLineage") or {}).get("searchResults", []) or []
    out = []
    for r in res:
        e = r.get("entity") or {}
        out.append({
            "urn": e.get("urn"),
            "type": e.get("type"),
            "name": _name(e),
            "platform": _platform(e),
            "degree": r.get("degree", 1),
        })
    return out


def blast_radius(affected_urn: str) -> dict:
    """Return {downstream:[...], counts:{DASHBOARD, CHART, DATASET, total}}."""
    downs = _nodes(affected_urn, "DOWNSTREAM")
    counts: dict[str, int] = {}
    for n in downs:
        counts[n["type"]] = counts.get(n["type"], 0) + 1
    counts["total"] = len(downs)
    return {"downstream": downs, "counts": counts}


def upstream_nodes(affected_urn: str) -> list[dict]:
    return _nodes(affected_urn, "UPSTREAM")
