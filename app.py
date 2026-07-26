"""CASCADE web app — judge-facing incident war room.

Serves the pre-seeded scenarios (cached, free to explore) and a gated + capped
live-run endpoint. Designed so the cached experience needs NO DataHub connection
(works on Render out of the box); live runs require DataHub + an Anthropic key.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "demo" / "cached"
FRONTEND = ROOT / "frontend"

# ── Live-run guardrails (protect the API budget) ─────────────────────────
LIVE_CODE = os.getenv("CASCADE_LIVE_CODE", "")          # empty => live disabled
LIVE_MAX_TOTAL = int(os.getenv("CASCADE_LIVE_MAX", "50"))
LIVE_MAX_PER_SESSION = int(os.getenv("CASCADE_LIVE_PER_SESSION", "3"))
_live_total = 0
_live_by_session: dict[str, int] = {}

app = FastAPI(title="CASCADE")


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

    if not LIVE_CODE:
        return fallback("live runs are disabled in this deployment")
    if code != LIVE_CODE:
        raise HTTPException(403, "invalid access code")
    if _live_total >= LIVE_MAX_TOTAL:
        return fallback("global live-run budget reached")
    if _live_by_session.get(session, 0) >= LIVE_MAX_PER_SESSION:
        return fallback("per-session live-run limit reached")

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
    return JSONResponse({"live": True, "trace": result["steps"],
                         "report_markdown": result["final_text"],
                         "incident_urn": result["incident_urn"],
                         "cost_usd": result["cost_usd"],
                         "live_remaining": max(0, LIVE_MAX_TOTAL - _live_total)})
