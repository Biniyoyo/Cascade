"""Tests for cascade.datahub_incidents — pure helpers plus mocked GraphQL.

No network: every _gql call is monkeypatched.
"""
import pytest

from cascade import datahub_incidents as di


# ── Pure functions ───────────────────────────────────────────────────────

def test_platform_from_dataset_dbt():
    urn = "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.db.schema.table,PROD)"
    assert di._platform_from_dataset(urn) == "dbt"


def test_platform_from_dataset_snowflake():
    urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.db.schema.table,PROD)"
    assert di._platform_from_dataset(urn) == "snowflake"


def test_platform_from_dataset_fallback():
    assert di._platform_from_dataset("not-a-dataset-urn") == "dbt"


def test_endpoint_from_env(monkeypatch):
    monkeypatch.setenv("DATAHUB_GMS_URL", "http://datahub.example:9002/")
    assert di._endpoint() == "http://datahub.example:9002/api/graphql"


def test_endpoint_default(monkeypatch):
    monkeypatch.delenv("DATAHUB_GMS_URL", raising=False)
    assert di._endpoint() == "http://localhost:8080/api/graphql"


def test_headers_include_token(monkeypatch):
    monkeypatch.setenv("DATAHUB_GMS_TOKEN", "tok123")
    h = di._headers()
    assert h["Authorization"] == "Bearer tok123"
    assert h["Content-Type"] == "application/json"


def test_raise_incident_rejects_bad_priority():
    with pytest.raises(ValueError, match="priority"):
        di.raise_incident("urn:li:dataset:x", "t", "d", priority="URGENT")


# ── Mocked GraphQL: get_owners parsing ───────────────────────────────────

OWNERS_PAYLOAD = {
    "dataset": {
        "ownership": {
            "owners": [
                {
                    "ownershipType": {"urn": "urn:li:ownershipType:__system__technical_owner"},
                    "owner": {
                        "__typename": "CorpUser",
                        "urn": "urn:li:corpuser:jdoe",
                        "properties": {"displayName": "Jane Doe", "email": "jdoe@example.com"},
                    },
                },
                {
                    "ownershipType": {"urn": "urn:li:ownershipType:__system__business_owner"},
                    "owner": {
                        "__typename": "CorpGroup",
                        "urn": "urn:li:corpGroup:data-eng",
                        "properties": {"displayName": "Data Engineering"},
                    },
                },
                {
                    # owner with no properties: name falls back to the urn
                    "ownershipType": {},
                    "owner": {"__typename": "CorpUser", "urn": "urn:li:corpuser:ghost"},
                },
            ]
        }
    }
}


def test_get_owners_parses_users_and_groups(monkeypatch):
    seen = {}

    def fake_gql(query, variables=None):
        seen["query"] = query
        seen["variables"] = variables
        return OWNERS_PAYLOAD

    monkeypatch.setattr(di, "_gql", fake_gql)
    owners = di.get_owners("urn:li:dataset:abc")

    assert seen["variables"] == {"urn": "urn:li:dataset:abc"}
    assert owners == [
        {"urn": "urn:li:corpuser:jdoe", "name": "Jane Doe", "kind": "CorpUser",
         "ownership_type": "technical_owner"},
        {"urn": "urn:li:corpGroup:data-eng", "name": "Data Engineering",
         "kind": "CorpGroup", "ownership_type": "business_owner"},
        {"urn": "urn:li:corpuser:ghost", "name": "urn:li:corpuser:ghost",
         "kind": "CorpUser", "ownership_type": ""},
    ]


def test_get_owners_handles_missing_dataset(monkeypatch):
    monkeypatch.setattr(di, "_gql", lambda q, v=None: {"dataset": None})
    assert di.get_owners("urn:li:dataset:missing") == []


def test_get_owners_handles_no_ownership(monkeypatch):
    monkeypatch.setattr(di, "_gql", lambda q, v=None: {"dataset": {"ownership": None}})
    assert di.get_owners("urn:li:dataset:bare") == []


# ── Mocked GraphQL: raise_incident write path ────────────────────────────

def test_raise_incident_builds_mutation_variables(monkeypatch):
    captured = {}

    def fake_gql(query, variables=None):
        captured["query"] = query
        captured["variables"] = variables
        return {"raiseIncident": "urn:li:incident:new-123"}

    monkeypatch.setattr(di, "_gql", fake_gql)
    urn = di.raise_incident(
        "urn:li:dataset:(urn:li:dataPlatform:dbt,db.schema.t,PROD)",
        "NULL spike in billing_country",
        "Root cause: countries source stopped loading.",
        priority="high",
    )

    assert urn == "urn:li:incident:new-123"
    assert "raiseIncident" in captured["query"]
    assert captured["variables"] == {
        "input": {
            "type": "OPERATIONAL",
            "title": "NULL spike in billing_country",
            "description": "Root cause: countries source stopped loading.",
            "resourceUrn": "urn:li:dataset:(urn:li:dataPlatform:dbt,db.schema.t,PROD)",
            "priority": "HIGH",  # normalized to the enum casing
        }
    }


def test_raise_incident_omits_priority_when_unset(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        di, "_gql",
        lambda q, v=None: captured.update(v=v) or {"raiseIncident": "urn:li:incident:x"})
    di.raise_incident("urn:li:dataset:y", "title", "desc")
    assert "priority" not in captured["v"]["input"]


def test_resolve_incident_sends_resolved_state(monkeypatch):
    captured = {}

    def fake_gql(query, variables=None):
        captured["query"] = query
        captured["variables"] = variables
        return {}

    monkeypatch.setattr(di, "_gql", fake_gql)
    assert di.resolve_incident("urn:li:incident:z", "fixed") is True
    assert captured["variables"] == {
        "urn": "urn:li:incident:z",
        "input": {"state": "RESOLVED", "message": "fixed"},
    }


def test_list_incidents_handles_missing_dataset(monkeypatch):
    monkeypatch.setattr(di, "_gql", lambda q, v=None: {"dataset": None})
    assert di.list_incidents("urn:li:dataset:nope") == []
