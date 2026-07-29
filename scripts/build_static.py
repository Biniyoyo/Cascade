"""Build the static (GitHub Pages) war room into docs/.

The hosted judge experience is 100% cached — live runs are disabled in public
deployments — so the FastAPI endpoints can be pre-baked into plain JSON files
and served from any static host (GitHub Pages, no card/server needed):

  docs/index.html                  frontend/index.html, fetches rewritten to
                                   relative *.json paths
  docs/api/config.json             {"live_enabled": false, ...}
  docs/api/scenarios.json          demo/cached/index.json
  docs/api/scenarios/<sid>.json    demo/cached/<sid>.display.json

Run after any frontend or cached-trace change:
  python scripts/build_static.py
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "demo" / "cached"
DOCS = ROOT / "docs"

REWRITES = [
    ("fetch('/api/config')", "fetch('api/config.json')"),
    ("fetch('/api/scenarios')", "fetch('api/scenarios.json')"),
    ("fetch('/api/scenarios/'+id)", "fetch('api/scenarios/'+id+'.json')"),
]


def main() -> None:
    html = (ROOT / "frontend" / "index.html").read_text()
    for old, new in REWRITES:
        if old not in html:
            sys.exit(f"build_static: expected `{old}` in frontend/index.html")
        html = html.replace(old, new)

    api = DOCS / "api"
    (api / "scenarios").mkdir(parents=True, exist_ok=True)
    (DOCS / ".nojekyll").write_text("")
    (DOCS / "index.html").write_text(html)
    (api / "config.json").write_text(json.dumps(
        {"live_enabled": False, "live_remaining": 0,
         "note": "static deployment — run live mode locally (see README)"}))
    shutil.copy(CACHE / "index.json", api / "scenarios.json")
    for f in CACHE.glob("*.display.json"):
        shutil.copy(f, api / "scenarios" / f"{f.name.removesuffix('.display.json')}.json")
    print("static site built in docs/ —",
          len(list((api / 'scenarios').glob('*.json'))), "scenarios")


if __name__ == "__main__":
    main()
