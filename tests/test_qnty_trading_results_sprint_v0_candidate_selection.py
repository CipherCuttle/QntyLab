import json
from pathlib import Path

from qntylab import breadth_v2_family_decision as reducer


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments/specs/qnty_trading_results_sprint_v0_candidate_selection.json"


def _load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_freeze_has_exactly_three_canonical_candidates_and_no_execution():
    manifest = _load_manifest()
    assert manifest["execution_in_this_phase"] is False
    assert manifest["selected_candidate_count"] == 3
    candidates = manifest["candidates"]
    assert len(candidates) == 3
    assert len({item["candidate_id"] for item in candidates}) == 3
    assert len({item["variant_id"] for item in candidates}) == 3

    proposals = {
        row["variant_id"]: row
        for line in (ROOT / "experiments/research/candidates.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
        for row in [json.loads(line)]
        if row.get("event_type") == "CANDIDATE_PROPOSED"
    }
    pass_families = set(manifest["canonical_reconciliation"]["pass_families"])
    for item in candidates:
        proposal = proposals[item["variant_id"]]
        assert item["candidate_id"] == proposal["candidate_id"]
        assert item["event_id"] == proposal["event_id"]
        assert item["family"] == proposal["family_id"]
        assert item["family"] in pass_families
        assert item["parameters"] == proposal["parameters"]


def test_contract_reuses_frozen_breadth_v2_semantics():
    contract = _load_manifest()["evaluation_contract"]
    assert contract["assets_universe"]["sha256"] == reducer.INPUT_UNIVERSE_SHA256
    assert contract["assets_universe"]["symbols"] == list(reducer.ASSETS)
    assert contract["benchmark"] == "BUY_AND_HOLD_PRIMARY_AND_CASH_SECONDARY"
    assert contract["costs"]["BASELINE_EXECUTION"]["fee_bps_per_one_way_turnover"] == 10
    assert contract["costs"]["STRESS_EXECUTION"]["fee_bps_per_one_way_turnover"] == 10
    assert contract["costs"]["STRESS_EXECUTION"]["slippage_bps_per_one_way_turnover"] == 10
    assert contract["funding_treatment"]["mode"] == "REALIZED_FUNDING_SETTLEMENTS_REQUIRED"
    assert contract["temporal_design"]["decision_clock"].startswith("after close")
    assert contract["temporal_design"]["execution_clock"].endswith("t+1")


def test_future_window_is_sealed_and_selection_windows_are_disjoint():
    manifest = _load_manifest()
    contract = manifest["evaluation_contract"]
    future = contract["future_execution_window"]
    assert future["sealed_t0"] == "2026-08-10T19:00:00Z"
    assert future["end"] == "2026-11-08T19:00:00Z"
    assert future["minimum_complete_hours"] == 2160
    assert future["adjudication_authorized_at"] == future["end"]
    assert future["selection_window_relation"] == "disjoint from historical selection windows"
    for window in contract["historical_selection_windows"]:
        assert window["end"] < future["sealed_t0"]


def test_qntyagenteval_no_match_is_explicit_and_no_evaluator_is_created():
    manifest = _load_manifest()
    applicability = manifest["qntyagenteval_applicability"]
    assert applicability["applicability"] == "NO_MATCH"
    assert applicability["compatible_contract_id"] is None
    assert "Do not build" in applicability["action"]
