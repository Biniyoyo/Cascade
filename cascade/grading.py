"""Structural (URN-based) grading for the eval — dependency-free.

STRICT semantics (v2): the agent's root-cause verdict is the asset it ACTUALLY
ANNOTATES — the update_description write targeting the ground-truth URN. A URN
merely mentioned in prose does NOT count. Completeness additionally requires the
native incident and the guard assertion to have been created (non-null URNs
returned by the write tools).
"""


def _annotated_urns(steps: list) -> set:
    urns = set()
    for st in steps or []:
        if not isinstance(st, dict):
            continue
        if (st.get("tool") or "").endswith("update_description"):
            u = ((st.get("input") or {}).get("entity_urn") or "").lower()
            if u:
                urns.add(u)
    return urns


def grade_root_cause(steps: list, final_text: str, scenario: dict) -> bool:
    """PASS iff the agent wrote its root-cause annotation to the ground-truth
    TABLE — accepted at any layer of its ingestion chain (postgres origin,
    warehouse load, or dbt source), never the affected dataset itself, and
    never merely because a URN appears in the final text."""
    accepted = {u.lower() for u in scenario.get("expected_root_cause_urns",
                [scenario.get("expected_root_cause_urn", "")]) if u}
    affected = scenario["affected_urn"].lower()
    accepted.discard(affected)
    return bool(accepted & _annotated_urns(steps))


def grade_completeness(record: dict) -> dict:
    """The full write-back loop: incident raised, guard assertion created."""
    return {
        "incident_created": bool(record.get("incident_urn")),
        "assertion_created": bool(record.get("assertion_urn")),
    }


def grade_no_context(text: str, scenario: dict) -> bool:
    """The blind control names the root cause only if it identifies the specific
    upstream ASSET (label + platform when the label collides with the affected
    dataset's own name) — echoing the symptom dataset does not count."""
    import re
    t = (text or "").lower()
    label = scenario["expected_root_cause"].lower()
    if label == "upstream customers load":
        # collides with the affected dataset's own name: require a platform-
        # qualified upstream reference, not an echo of the symptom dataset
        return ("customers" in t and "order_entry" in t
                and ("snowflake" in t or "postgres" in t))
    if "_" in label:
        # identifier-style name (order_items) — a plain mention IS naming the asset
        return re.search(rf"\b{label}\b", t) is not None
    # natural-language word (countries) — require an asset-style reference, not
    # ordinary English usage ("maps valid countries to NULL" must not count)
    pat = rf"(`{label}`|{label}\s+(table|lookup|model|dataset|source|dim)\b)"
    return re.search(pat, t) is not None
