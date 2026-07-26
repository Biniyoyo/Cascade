"""API tests against the real cached fixtures in demo/cached/ — no network,
no DataHub, no ANTHROPIC_API_KEY required."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as app_module

client = TestClient(app_module.app)

CACHE = Path(app_module.__file__).resolve().parent / "demo" / "cached"


# ── Cached scenario endpoints ────────────────────────────────────────────

def test_scenarios_index_lists_three():
    r = client.get("/api/scenarios")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 3
    assert {s["id"] for s in data} == {"null_spike", "bad_aggregation", "pii_nulls"}
    for s in data:
        assert s["name"] and s["priority"]


def test_scenario_detail_returns_display_payload():
    r = client.get("/api/scenarios/null_spike")
    assert r.status_code == 200
    data = r.json()
    assert data == json.loads((CACHE / "null_spike.display.json").read_text())
    assert data["id"] == "null_spike"
    for key in ("trace", "report_markdown", "incident_urn", "root_cause", "blast"):
        assert key in data
    assert isinstance(data["trace"], list) and len(data["trace"]) > 0


def test_unknown_scenario_404():
    r = client.get("/api/scenarios/does_not_exist")
    assert r.status_code == 404


# ── /api/config ──────────────────────────────────────────────────────────

def test_config_reports_live_disabled(monkeypatch):
    monkeypatch.setattr(app_module, "LIVE_CODE", "")
    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert data["live_enabled"] is False
    assert data["live_remaining"] >= 0


# ── /api/run-live gated + fallback path ──────────────────────────────────

def test_run_live_disabled_falls_back_to_cached(monkeypatch):
    """Without a live code configured (i.e. no keys/backends), the endpoint
    must degrade gracefully to the cached result."""
    monkeypatch.setattr(app_module, "LIVE_CODE", "")
    r = client.post("/api/run-live/null_spike", json={})
    assert r.status_code == 200
    data = r.json()
    assert data["live"] is False
    assert "disabled" in data["reason"]
    cached = json.loads((CACHE / "null_spike.display.json").read_text())
    assert data["trace"] == cached["trace"]
    assert data["report_markdown"] == cached["report_markdown"]
    assert data["incident_urn"] == cached["incident_urn"]


def test_run_live_no_body_is_tolerated(monkeypatch):
    monkeypatch.setattr(app_module, "LIVE_CODE", "")
    r = client.post("/api/run-live/pii_nulls")  # no JSON body at all
    assert r.status_code == 200
    assert r.json()["live"] is False


def test_run_live_unknown_scenario_404(monkeypatch):
    monkeypatch.setattr(app_module, "LIVE_CODE", "")
    r = client.post("/api/run-live/nope", json={})
    assert r.status_code == 404


def test_run_live_wrong_code_403(monkeypatch):
    monkeypatch.setattr(app_module, "LIVE_CODE", "sekrit")
    r = client.post("/api/run-live/null_spike", json={"code": "wrong"})
    assert r.status_code == 403


def test_run_live_budget_exhausted_falls_back(monkeypatch):
    """Correct code but global budget spent: fall back, never hit the backend."""
    monkeypatch.setattr(app_module, "LIVE_CODE", "sekrit")
    monkeypatch.setattr(app_module, "_live_total", app_module.LIVE_MAX_TOTAL)
    r = client.post("/api/run-live/null_spike", json={"code": "sekrit"})
    assert r.status_code == 200
    data = r.json()
    assert data["live"] is False
    assert "budget" in data["reason"]
    assert data["incident_urn"]


def test_run_live_session_cap_falls_back(monkeypatch):
    monkeypatch.setattr(app_module, "LIVE_CODE", "sekrit")
    monkeypatch.setattr(app_module, "_live_total", 0)
    monkeypatch.setattr(app_module, "_live_by_session",
                        {"testclient": app_module.LIVE_MAX_PER_SESSION})
    r = client.post("/api/run-live/null_spike", json={"code": "sekrit"})
    assert r.status_code == 200
    data = r.json()
    assert data["live"] is False
    assert "per-session" in data["reason"]
