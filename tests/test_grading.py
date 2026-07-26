"""Tests for cascade.grading — URN-structural grading and the blind control."""
import pytest

from cascade.grading import grade_no_context, grade_root_cause
from cascade.scenarios import SCENARIOS, SCENARIOS_BY_ID


def annotate_step(urn: str) -> dict:
    return {"tool": "mcp__cascade__update_description", "input": {"entity_urn": urn}}


# ── grade_root_cause ─────────────────────────────────────────────────────

@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_annotating_expected_urn_passes(scenario):
    steps = [
        {"tool": "mcp__datahub__get_lineage", "input": {"urn": scenario["affected_urn"]}},
        annotate_step(scenario["expected_root_cause_urn"]),
    ]
    assert grade_root_cause(steps, "", scenario) is True


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_annotating_affected_dataset_fails(scenario):
    """Annotating the symptom dataset itself is not a root-cause verdict."""
    steps = [annotate_step(scenario["affected_urn"])]
    assert grade_root_cause(steps, "some unrelated report", scenario) is False


def test_empty_steps_and_empty_text_fails():
    scenario = SCENARIOS_BY_ID["null_spike"]
    assert grade_root_cause([], "", scenario) is False


def test_empty_steps_falls_back_to_final_text_urn():
    scenario = SCENARIOS_BY_ID["null_spike"]
    final = f"Root cause: {scenario['expected_root_cause_urn']} stopped loading."
    assert grade_root_cause([], final, scenario) is True


def test_urn_match_is_case_insensitive():
    scenario = SCENARIOS_BY_ID["null_spike"]
    steps = [annotate_step(scenario["expected_root_cause_urn"].upper())]
    assert grade_root_cause(steps, "", scenario) is True


def test_non_dict_steps_are_ignored():
    scenario = SCENARIOS_BY_ID["null_spike"]
    steps = ["garbage", None, annotate_step(scenario["expected_root_cause_urn"])]
    assert grade_root_cause(steps, "", scenario) is True


def test_wrong_tool_does_not_count():
    scenario = SCENARIOS_BY_ID["null_spike"]
    steps = [{"tool": "mcp__datahub__get_dataset",
              "input": {"entity_urn": scenario["expected_root_cause_urn"]}}]
    assert grade_root_cause(steps, "", scenario) is False


# ── grade_no_context (blind control) ─────────────────────────────────────

GENERIC_ETL_GUESS = ("An upstream ETL job likely failed or a schema change broke "
                     "the pipeline; check recent deploys and rerun the load.")


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_generic_etl_guess_fails(scenario):
    assert grade_no_context(GENERIC_ETL_GUESS, scenario) is False


def test_naming_upstream_label_passes_null_spike():
    scenario = SCENARIOS_BY_ID["null_spike"]
    text = "The `countries` lookup source stopped emitting rows."
    assert grade_no_context(text, scenario) is True


def test_naming_upstream_label_passes_bad_aggregation():
    scenario = SCENARIOS_BY_ID["bad_aggregation"]
    text = "Duplicated rows in order_items doubled the join output."
    assert grade_no_context(text, scenario) is True


def test_pii_nulls_platform_qualified_upstream_passes():
    scenario = SCENARIOS_BY_ID["pii_nulls"]
    text = ("The physical snowflake load ORDER_ENTRY_DB.order_entry.customers "
            "is writing NULL emails.")
    assert grade_no_context(text, scenario) is True


def test_pii_nulls_merely_saying_customers_fails():
    """`customers` collides with the affected dataset's own label — echoing the
    symptom dataset must not count as naming the root cause."""
    scenario = SCENARIOS_BY_ID["pii_nulls"]
    assert grade_no_context("The customers table has bad emails.", scenario) is False


def test_pii_nulls_snowflake_without_qualification_fails():
    scenario = SCENARIOS_BY_ID["pii_nulls"]
    assert grade_no_context("Maybe something in snowflake broke.", scenario) is False


def test_empty_text_fails():
    for scenario in SCENARIOS:
        assert grade_no_context("", scenario) is False
        assert grade_no_context(None, scenario) is False
