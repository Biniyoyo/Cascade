"""CASCADE web app — judge-facing incident war room.

Serves the pre-seeded scenarios (cached, free to explore) and a gated + capped
live-run endpoint. Designed so the cached experience needs NO DataHub connection
(works on Render out of the box); live runs require DataHub + an Anthropic key.

Also exposes POST /api/trigger — the assertion-failure-webhook-shaped entry
point a DataHub Actions consumer would call — and persists a per-run audit
trail of every write the agent made (or proposed) to audit/audit.jsonl.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "demo" / "cached"
FRONTEND = ROOT / "frontend"
AUDIT_DIR = ROOT / "audit"
AUDIT_FILE = AUDIT_DIR / "audit.jsonl"

# ── Live-run guardrails (protect the API budget) ─────────────────────────
LIVE_CODE = os.getenv("CASCADE_LIVE_CODE", "")          # empty => live disabled
LIVE_MAX_TOTAL = int(os.getenv("CASCADE_LIVE_MAX", "50"))
LIVE_MAX_PER_SESSION = int(os.getenv("CASCADE_LIVE_PER_SESSION", "3"))
_live_total = 0
_live_by_session: dict[str, int] = {}

app = FastAPI(title="CASCADE")


def _live_gate(code: str, session: str) -> str | None:
    """Shared gate for the live endpoints. Returns a human-readable fallback
    reason when a live run can't happen (disabled / budget caps), None when it
    can. Raises 403 on a wrong access code."""
    if not LIVE_CODE:
        return "live runs are disabled in this deployment"
    if code != LIVE_CODE:
        raise HTTPException(403, "invalid access code")
    if _live_total >= LIVE_MAX_TOTAL:
        return "global live-run budget reached"
    if _live_by_session.get(session, 0) >= LIVE_MAX_PER_SESSION:
        return "per-session live-run limit reached"
    return None


def _persist_audit(source: str, meta: dict, result: dict) -> None:
    """Append one JSON line per completed live run to audit/audit.jsonl:
    when it ran, what triggered it, and every write the agent executed
    (result["audit"]) or proposed (result["proposed_writes"])."""
    entry = {"ts": datetime.now(timezone.utc).isoformat(),
             "source": source, **meta,
             "incident_urn": result.get("incident_urn"),
             "assertion_urn": result.get("assertion_urn"),
             "cost_usd": result.get("cost_usd"),
             "writes": result.get("audit", []),
             "proposed_writes": result.get("proposed_writes", [])}
    try:
        AUDIT_DIR.mkdir(exist_ok=True)
        with AUDIT_FILE.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:  # never fail a run over audit IO, but say so loudly
        print(f"[audit] FAILED to persist audit entry: {e}", file=sys.stderr)


def _dataset_label(urn: str) -> str:
    """Best-effort short label from a dataset URN, e.g.
    urn:li:dataset:(urn:li:dataPlatform:dbt,db.schema.orders,PROD) -> orders."""
    try:
        inner = urn[urn.index("(") + 1:urn.rindex(")")]
        return inner.split(",")[1].split(".")[-1]
    except (ValueError, IndexError):
        return urn


@app.get("/", response_class=HTMLResponse)
def index():
    return (FRONTEND / "index.html").read_text()


@app.get("/api/scenarios")
def scenarios():
    return json.loads((CACHE / "index.json").read_text())


@app.get("/api/scenarios/{sid}")
def scenario(sid: str):
    f = CACHE / f"{sid}.display.json"
    if not f.exists():
        raise HTTPException(404, "unknown scenario")
    return json.loads(f.read_text())


@app.get("/api/config")
def config():
    return {"live_enabled": bool(LIVE_CODE),
            "live_remaining": max(0, LIVE_MAX_TOTAL - _live_total)}


@app.post("/api/run-live/{sid}")
async def run_live(sid: str, request: Request):
    """Gated, capped live run. Falls back to the cached result when unavailable."""
    global _live_total
    cached = CACHE / f"{sid}.display.json"
    if not cached.exists():
        raise HTTPException(404, "unknown scenario")

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    code = body.get("code", "")
    session = request.client.host if request.client else "anon"

    def fallback(reason):
        payload = json.loads(cached.read_text())
        return JSONResponse({"live": False, "reason": reason,
                             "trace": payload["trace"],
                             "report_markdown": payload["report_markdown"],
                             "incident_urn": payload["incident_urn"]})

    reason = _live_gate(code, session)
    if reason:
        return fallback(reason)

    # Do the real run (requires DataHub reachable + ANTHROPIC_API_KEY).
    try:
        from cascade.agent import run_incident
        from cascade.scenarios import SCENARIOS_BY_ID, incident_prompt
        from cascade import datahub_incidents as di
        sc = SCENARIOS_BY_ID[sid]
        for i in di.list_incidents(sc["affected_urn"]):
            if i["status"]["state"] == "ACTIVE":
                di.resolve_incident(i["urn"], "reset before live run")
        result = await run_incident(incident_prompt(sc), max_budget_usd=1.0, quiet=True)
    except Exception as e:
        return fallback(f"live backend unavailable ({type(e).__name__})")

    _live_total += 1
    _live_by_session[session] = _live_by_session.get(session, 0) + 1
    _persist_audit("run-live", {"scenario": sid, "session": session}, result)
    return JSONResponse({"live": True, "trace": result["steps"],
                         "report_markdown": result["final_text"],
                         "incident_urn": result["incident_urn"],
                         "cost_usd": result["cost_usd"],
                         "live_remaining": max(0, LIVE_MAX_TOTAL - _live_total)})


@app.post("/api/trigger")
async def trigger(request: Request):
    """Assertion-failure webhook: CASCADE's production entry point.

    This is the hook a DataHub assertion-failure webhook — or an Actions-
    framework consumer subscribed to assertion run events — would point at:
    DataHub detects a failing assertion, POSTs the failure here, and CASCADE
    triages it with the exact guardrails of the judge-facing live run: access-
    code gate, global + per-session run caps, allowlisted tools, hard per-run
    spend cap, and an audit-logged result.

    Body (assertion-failure shape):
      urn       dataset URN the assertion fired on (required)
      column    failing column / field path (optional)
      symptom   what the assertion observed (required)
      priority  CRITICAL | HIGH | MEDIUM | LOW (default HIGH)
      code      live access code — same gate as /api/run-live
      propose   true => investigate but only PROPOSE writes for human
                confirmation (default false; recommended for initial
                production rollout — see docs/deploy-safely.md)

    Degrades gracefully (live:false, plus the prompt it would have run) when
    live runs are disabled, budgets are exhausted, or no ANTHROPIC_API_KEY is
    configured."""
    global _live_total
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "invalid JSON body")
    urn = str(body.get("urn") or "").strip()
    symptom = str(body.get("symptom") or "").strip()
    if not urn or not symptom:
        raise HTTPException(422, "'urn' and 'symptom' are required")
    column = str(body.get("column") or "").strip()
    priority = str(body.get("priority") or "HIGH").upper()
    if priority not in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
        priority = "HIGH"
    propose = bool(body.get("propose", False))
    session = request.client.host if request.client else "anon"

    # Same prompt path the live run uses (scenario dict -> incident_prompt).
    from cascade.scenarios import incident_prompt
    scenario = {
        "priority": priority,
        "affected_label": _dataset_label(urn),
        "affected_urn": urn,
        "failure_type": (f"Assertion failure on `{column}`" if column
                         else "Assertion failure"),
        "symptom": symptom,
    }
    prompt = incident_prompt(scenario)

    def fallback(reason):
        return JSONResponse({"live": False, "reason": reason,
                             "propose": propose, "would_run": prompt})

    reason = _live_gate(str(body.get("code", "")), session)
    if reason:
        return fallback(reason)

    try:
        from cascade.agent import run_incident  # first import loads .env
        if not os.getenv("ANTHROPIC_API_KEY"):
            return fallback("no ANTHROPIC_API_KEY configured")
        result = await run_incident(prompt, max_budget_usd=1.0, quiet=True,
                                    propose=propose)
    except Exception as e:
        return fallback(f"live backend unavailable ({type(e).__name__})")

    _live_total += 1
    _live_by_session[session] = _live_by_session.get(session, 0) + 1
    _persist_audit("trigger", {"urn": urn, "column": column,
                               "priority": priority, "propose": propose,
                               "session": session}, result)
    return JSONResponse({"live": True, "propose": propose,
                         "trace": result["steps"],
                         "report_markdown": result["final_text"],
                         "incident_urn": result["incident_urn"],
                         "proposed_writes": result["proposed_writes"],
                         "cost_usd": result["cost_usd"],
                         "live_remaining": max(0, LIVE_MAX_TOTAL - _live_total)})
