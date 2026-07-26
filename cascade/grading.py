"""Structural (URN-based) grading for the eval — dependency-free."""


def grade_root_cause(steps: list, final_text: str, scenario: dict) -> bool:
    """Structural grading: the agent's root-cause verdict is the asset it ANNOTATES
    (update_description entity_urn) — an action, not a word. Correct iff that URN is
    the scenario's ground-truth upstream (and never the affected dataset itself).
    Falls back to the incident description naming the expected URN."""
    expected = scenario["expected_root_cause_urn"].lower()
    affected = scenario["affected_urn"].lower()
    for st in steps:
        if not isinstance(st, dict):
            continue
        tool = (st.get("tool") or "")
        inp = st.get("input") or {}
        if tool.endswith("update_description"):
            target = (inp.get("entity_urn") or "").lower()
            if target == expected and target != affected:
                return True
    return expected in (final_text or "").lower()


def grade_no_context(text: str, scenario: dict) -> bool:
    """The blind control names the root cause only if it identifies the specific
    upstream ASSET (label + platform when the label collides with the affected
    dataset's own name) — echoing the symptom dataset does not count."""
    t = (text or "").lower()
    label = scenario["expected_root_cause"].lower()
    if label == "snowflake customers load":
        # collides with affected label "customers": require the platform-qualified asset
        return "snowflake" in t and "customers" in t and "order_entry" in t
    return label in t
