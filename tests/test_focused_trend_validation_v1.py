import json
from collections import Counter
from pathlib import Path

import qntylab.strategy_test as strategy_test
from qntylab.focused_trend_validation import expand_planned_holdout_runs

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "experiments/specs/focused_trend_validation_v1.json"
SOURCE_SPEC_PATH = ROOT / "experiments/specs/curated_breadth_screen_v1.json"
RESEARCH = ROOT / "experiments/research"

EXPECTED_VARIANTS = {
    "variant_f201cbb38819b1e09e763ac7": {
        "candidate_id": "CANDIDATE_H002_MOMENTUM_720_LONG_FLAT",
        "parameters": {"lookback": 720, "mode": "long_flat"},
        "strategy_id": "H002_momentum",
    },
    "variant_00eb140f03a5f6ab40600160": {
        "candidate_id": "CANDIDATE_H003_MA_48_192_LONG_FLAT",
        "parameters": {"fast": 48, "mode": "long_flat", "slow": 192},
        "strategy_id": "H003_moving_average",
    },
    "variant_296a2973dfde57cec911715b": {
        "candidate_id": "CANDIDATE_H003_MA_168_720_LONG_FLAT",
        "parameters": {"fast": 168, "mode": "long_flat", "slow": 720},
        "strategy_id": "H003_moving_average",
    },
}


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_focused_trend_validation_v1_registration_contract():
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    source = json.loads(SOURCE_SPEC_PATH.read_text(encoding="utf-8"))
    state = json.loads((RESEARCH / "state.json").read_text(encoding="utf-8"))
    candidates = _jsonl(RESEARCH / "candidates.jsonl")
    decisions = _jsonl(RESEARCH / "decisions.jsonl")
    trials = _jsonl(RESEARCH / "trials/2026.jsonl")

    assert spec["preregistration_id"] == "PREREGISTER_FOCUSED_TREND_VALIDATION_V1"
    assert spec["status"] == "REGISTERED_NOT_EXECUTED"
    assert spec["registration_only"] is True
    assert spec["expected_starting_head"] == "8028d497e169aabc23e83e2aa9fc47d29104056d"
    assert set(spec["tracks"]) == {
        "A_untouched_2023_holdout",
        "B_forward_paper_shadow_validation",
        "C_h002_h003_family_distinctness_diagnostics",
        "D_h007_benchmark_reconstruction_dependency",
    }

    assert len(spec["variants"]) == 3
    assert [item["variant_id"] for item in spec["variants"]] == list(EXPECTED_VARIANTS)
    by_source_variant = {item["variant_id"]: item for item in source["candidate_details"]}
    by_candidate_variant = {event["variant_id"]: event for event in candidates if event["event_type"] == "CANDIDATE_PROPOSED"}
    for item in spec["variants"]:
        expected = EXPECTED_VARIANTS[item["variant_id"]]
        assert item["candidate_id"] == expected["candidate_id"]
        assert item["strategy_id"] == expected["strategy_id"]
        assert item["parameters"] == expected["parameters"]
        assert by_source_variant[item["variant_id"]]["parameters"] == expected["parameters"]
        assert by_candidate_variant[item["variant_id"]]["parameters"] == expected["parameters"]
        assert state["variants"][item["variant_id"]]["status"] == "FOLLOW_UP"
        assert item["state_required_at_registration"] == "FOLLOW_UP"

    track_a = spec["tracks"]["A_untouched_2023_holdout"]
    assert track_a["planned_trial_count"] == 18
    assert len(track_a["planned_trials"]) == 18
    assert Counter(row["variant_id"] for row in track_a["planned_trials"]) == {variant_id: 6 for variant_id in EXPECTED_VARIANTS}
    assert Counter(row["asset"] for row in track_a["planned_trials"]) == {"BTCUSDT": 6, "ETHUSDT": 6, "SOLUSDT": 6}
    assert Counter(row["cost_mode"] for row in track_a["planned_trials"]) == {"baseline": 9, "stress": 9}
    assert {row["period_id"] for row in track_a["planned_trials"]} == {"2023_UNTOUCHED_HOLDOUT"}
    assert track_a["period"] == {
        "id": "2023_UNTOUCHED_HOLDOUT",
        "start": "2023-01-01T00:00:00Z",
        "end": "2023-12-31T23:00:00Z",
    }
    assert spec["cost_modes"] == source["cost_modes"] == {
        "baseline": {"fee_bps": 10, "slippage_bps": 0},
        "stress": {"fee_bps": 10, "slippage_bps": 10},
    }
    assert spec["assets"] == source["assets"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert track_a["data_requirements"] == {
        "acquisition_provenance_required": True,
        "authoritative_source_acquisition_required": True,
        "exact_hourly_timestamps_required": True,
        "fail_closed_if_complete_valid_data_cannot_be_established": True,
        "no_cross_gap_returns": True,
        "no_forward_fill": True,
        "no_interpolation": True,
        "source_sha256_required": True,
    }
    assert track_a["continuation_gate"]["all_six_cells_complete_per_variant"] is True
    assert track_a["continuation_gate"]["integrity_failures_allowed"] == 0
    assert track_a["continuation_gate"]["aggregate_stressed_primary_result_positive"] is True
    assert track_a["continuation_gate"]["minimum_stressed_primary_positive_asset_count"] == 2
    assert "not universal statistical laws" in track_a["continuation_gate"]["note"]
    assert all("2023" not in str(event["evaluation_start"]) for event in trials if event["variant_id"] in EXPECTED_VARIANTS)

    track_b = spec["tracks"]["B_forward_paper_shadow_validation"]
    assert track_b["first_eligible_timestamp_after_registration_commit"] == "2026-08-02T01:00:00Z"
    assert track_b["minimum_completed_hourly_observations_before_checkpoint"] == 2160
    assert track_b["parameter_or_gate_changes_allowed"] is False
    assert track_b["automatic_decision_allowed"] is False
    assert track_b["run_must_not_begin_during_this_task"] is True
    assert track_b["accounting_modes"] == ["baseline", "stress"]

    track_c = spec["tracks"]["C_h002_h003_family_distinctness_diagnostics"]
    assert track_c["pairs"] == [
        ["variant_f201cbb38819b1e09e763ac7", "variant_00eb140f03a5f6ab40600160"],
        ["variant_f201cbb38819b1e09e763ac7", "variant_296a2973dfde57cec911715b"],
    ]
    assert track_c["diagnostics"] == [
        "position_correlation",
        "strategy_return_correlation",
        "position_disagreement_fraction",
        "concurrent_drawdown_fraction",
        "equal_weight_combination_result",
        "leave_one_asset_out_result",
        "leave_one_period_out_result",
    ]
    assert track_c["weight_policy"] == "Equal-weight combination only; do not optimize weights."
    assert "diagnostic_inspection" in track_c["prohibited_during_registration"]

    track_d = spec["tracks"]["D_h007_benchmark_reconstruction_dependency"]
    assert track_d["dependency_preregistration_id"] == "PREREGISTER_H003_24_96_BENCHMARK_RECONSTRUCTION_V1"
    assert track_d["execute_now"] is False
    assert track_d["h007_current_alpha_family_counting"] == "H007 is not currently counted as an independently validated alpha family."

    spa = spec["statistical_diagnostic"]
    assert spa["name"] == "Hansen SPA"
    assert spa["registered_universe_variant_count"] == 15
    assert spa["implementation_now"] is False
    assert spa["resampling"] == "dependence-aware resampling"
    assert spa["fake_p_values_from_aggregate_summary_rows_prohibited"] is True

    assert len(decisions) == 19
    assert len(trials) == 360
    assert "ledger_events" not in spec
    assert "trial_completed" not in json.dumps(spec).lower()


def test_focused_holdout_plan_expands_to_18_unique_2023_follow_up_identities(monkeypatch):
    def fail_run_strategy(*args, **kwargs):
        raise AssertionError("holdout plan expansion must not execute a strategy")

    monkeypatch.setattr(strategy_test, "run_strategy", fail_run_strategy)
    planned = expand_planned_holdout_runs(SPEC_PATH, repo_root=ROOT)
    assert len(planned) == 18
    assert len({row["trial_id"] for row in planned}) == 18
    assert Counter(row["variant_id"] for row in planned) == {variant_id: 6 for variant_id in EXPECTED_VARIANTS}
    assert Counter(row["asset"] for row in planned) == {"BTCUSDT": 6, "ETHUSDT": 6, "SOLUSDT": 6}
    assert Counter(row["cost_mode"] for row in planned) == {"baseline": 9, "stress": 9}
    assert {row["period"] for row in planned} == {"2023_UNTOUCHED_HOLDOUT"}
    assert {row["research_intent"] for row in planned} == {"FOLLOW_UP"}
    assert {row["config"]["evaluation_start"] for row in planned} == {"2023-01-01T00:00:00Z"}
    assert {row["config"]["evaluation_end"] for row in planned} == {"2023-12-31T23:00:00Z"}
    assert all(row["config"]["normalization_provenance"]["derived_input_sha256"] == row["input_sha256"] for row in planned)


def test_focused_holdout_plan_has_no_collision_with_completed_breadth_screen_trials():
    planned = expand_planned_holdout_runs(SPEC_PATH, repo_root=ROOT)
    completed = {event["trial_id"] for event in _jsonl(RESEARCH / "trials/2026.jsonl")}
    assert len(completed) == 360
    assert {row["trial_id"] for row in planned}.isdisjoint(completed)
