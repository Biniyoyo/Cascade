"""Owner routing on incident write-back.

Routing must not depend on the model remembering to pass `assignee_urns`:
when the agent omits them, the tool falls back to the asset's own owners from
DataHub's ownership graph, so every incident lands on a real person or team.
"""
import anyio
import pytest

from cascade import tools
from cascade import datahub_incidents as di

DATASET = "urn:li:dataset:(urn:li:dataPlatform:dbt,db.schema.t,PROD)"

OWNERS = [
    {"urn": "urn:li:corpuser:biz", "name": "Biz", "kind": "CorpUser",
     "ownership_type": "BUSINESS_OWNER"},
    {"urn": "urn:li:corpGroup:platform", "name": "Platform", "kind": "CorpGroup",
     "ownership_type": "TECHNICAL_OWNER"},
    {"urn": "urn:li:corpuser:steward", "name": "Steward", "kind": "CorpUser",
     "ownership_type": "DATA_STEWARD"},
    {"urn": "urn:li:corpGroup:platform", "name": "Platform", "kind": "CorpGroup",
     "ownership_type": "DATA_STEWARD"},  # same URN twice — must dedupe
    {"urn": None, "name": "broken", "kind": "CorpUser", "ownership_type": ""},
]


@pytest.fixture
def captured(monkeypatch):
    seen = {}

    def fake_raise(resource_urn, title, description, incident_type="OPERATIONAL",
                   priority=None, assignee_urns=None):
        seen["assignees"] = assignee_urns
        return "urn:li:incident:abc"

    monkeypatch.setattr(di, "raise_incident", fake_raise)
    monkeypatch.setattr(di, "get_owners", lambda urn: OWNERS)
    tools.reset_last()
    return seen


def _call(**extra):
    args = {"resource_urn": DATASET, "title": "t", "description": "d",
            "priority": "HIGH", **extra}
    return anyio.run(tools.raise_incident.handler, args)


def test_owner_urns_ranked_deduped_and_capped(monkeypatch):
    monkeypatch.setattr(di, "get_owners", lambda urn: OWNERS)
    assert tools._owner_urns(DATASET) == [
        "urn:li:corpGroup:platform",   # technical owner first
        "urn:li:corpuser:steward",     # then steward
        "urn:li:corpuser:biz",         # business owner last
    ]


def test_auto_routes_to_owners_when_agent_omits_assignees(captured):
    result = _call()
    assert captured["assignees"] == [
        "urn:li:corpGroup:platform", "urn:li:corpuser:steward", "urn:li:corpuser:biz"]
    assert "auto-routed" in result["content"][0]["text"]
    assert tools.LAST["incident"] == "urn:li:incident:abc"


def test_explicit_assignees_win_over_auto_routing(captured):
    result = _call(assignee_urns=["urn:li:corpuser:oncall"])
    assert captured["assignees"] == ["urn:li:corpuser:oncall"]
    assert "auto-routed" not in result["content"][0]["text"]


def test_non_corp_urns_are_never_assigned(captured):
    _call(assignee_urns=["urn:li:dataset:not-a-person", "not-a-urn"])
    # falls back to owners rather than sending a malformed assignee
    assert captured["assignees"] == [
        "urn:li:corpGroup:platform", "urn:li:corpuser:steward", "urn:li:corpuser:biz"]


def test_unowned_asset_raises_unassigned_incident(monkeypatch, captured):
    monkeypatch.setattr(di, "get_owners", lambda urn: [])
    result = _call()
    assert captured["assignees"] is None
    assert "unassigned" in result["content"][0]["text"]
