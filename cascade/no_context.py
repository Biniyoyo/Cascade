"""The 'without context' half of the A/B: the SAME model, given ONLY the symptom
and NO access to DataHub's graph, must guess the root cause and blast radius.
This is the control that proves DataHub's thesis — context, not model, is the unlock."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from cascade.agent import DEV_MODEL

NO_CONTEXT_SYSTEM = """\
You are an on-call data engineer triaging a data incident. You have NO access to
the data catalog, lineage, schema, or ownership — ONLY the symptom described to you.
Give your best-effort diagnosis from the symptom alone:
- Your best GUESS at the likely root cause (be honest that you cannot confirm it).
- Which downstream assets/dashboards are PROBABLY affected (you don't know the real ones).
- Name the specific upstream table you most suspect, even if you cannot confirm it.
- Be concise (a short paragraph).
"""
# NOTE: the last bullet previously read "Do not invent specific asset names or
# URNs you can't know" — which discouraged the control from doing the very thing
# it is scored on. Fixed here; the published control runs predate the fix and
# are labelled in docs/eval.md, which also shows the control never named the
# root-cause table anyway.


def run_no_context(scenario: dict, model: str = DEV_MODEL) -> dict:
    """One cheap, tool-less LLM call. Returns {text, model}."""
    from anthropic import Anthropic

    client = Anthropic()  # ANTHROPIC_API_KEY
    prompt = (f"Incident on dataset '{scenario['affected_label']}'. "
              f"Symptom: {scenario['symptom']}\n\n"
              f"Without a data catalog or lineage, what's your best guess at the root "
              f"cause and the likely downstream impact?")
    msg = client.messages.create(
        model=model, max_tokens=450,
        system=NO_CONTEXT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    return {"text": text, "model": model}
