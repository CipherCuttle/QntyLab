import json
import shutil
from pathlib import Path

import pytest

import qntylab.backtest as backtest
import qntylab.strategy_test as strategy_test
from qntylab.focused_trend_holdout_review import (
    CELLS_PATH,
    JSON_PATH,
    MD_PATH,
    PRIMARY_METRIC,
    VARIANTS_PATH,
    _variant_rows,
    build_review,
    write_outputs,
)
from qntylab.focused_trend_validation import expand_planned_holdout_runs
from qntylab.research_ledger import load_canonical_history


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "experiments/specs/focused_trend_validation_v1.json"


def test_review_consumes_exactly_18_completed_focused_holdout_trials():
    review = build_review(ROOT)
    assert len(expand_planned_holdout_runs(SPEC_PATH, repo_root=ROOT)) == 18
    assert review["trial_integrity"]["expected_trials"] == 18
    assert review["trial_integrity"]["completed_expected_trials"] == 18
    assert review["trial_integrity"]["missing"] == []
    assert review["trial_integrity"]["duplicates"] == []
    assert review["trial_integrity"]["unexpected"] == []
    assert review["trial_integrity"]["failed"] == []
    assert review["trial_integrity"]["receipt_validation"] == "18/18"
    assert review["trial_integrity"]["normalization_provenance"] == "18/18"
    assert review["trial_integrity"]["per_asset"] == {"BTCUSDT": 6, "ETHUSDT": 6, "SOLUSDT": 6}
    assert review["trial_integrity"]["per_cost_mode"] == {"baseline": 9, "stress": 9}


def test_review_emits_cell_and_variant_rows_with_primary_metric_contract():
    review = build_review(ROOT)
    assert len(review["cells"]) == 18
    assert len(review["variants"]) == 3
    assert review["primary_metric"] == PRIMARY_METRIC == "excess_return_vs_buy_and_hold"
    assert {row["primary_metric_name"] for row in review["cells"]} == {"excess_return_vs_buy_and_hold"}
    assert all(row["primary_metric_value"] == row["excess_return_vs_buy_and_hold"] for row in review["cells"])
    assert all(isinstance(row["mechanical_holdout_gate_pass"], bool) for row in review["variants"])
    assert review["family_status"] == {
        "time_series_momentum": "one exact variant tested in the holdout",
        "moving_average_trend": "two exact variants tested in the holdout",
    }


def test_aggregation_matches_frozen_sum_methodology():
    review = build_review(ROOT)
    for variant in review["variants"]:
        stress_sum = sum(
            row["excess_return_vs_buy_and_hold"]
            for row in review["cells"]
            if row["variant_id"] == variant["variant_id"] and row["cost_mode"] == "stress"
        )
        baseline_sum = sum(
            row["excess_return_vs_buy_and_hold"]
            for row in review["cells"]
            if row["variant_id"] == variant["variant_id"] and row["cost_mode"] == "baseline"
        )
        assert variant["stress_primary_aggregate"] == pytest.approx(stress_sum)
        assert variant["baseline_primary_aggregate"] == pytest.approx(baseline_sum)


def _spec():
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def _cells(values, *, baseline=1.0):
    rows = []
    for variant in _spec()["variants"]:
        for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            rows.append(
                {
                    "variant_id": variant["variant_id"],
                    "symbol": symbol,
                    "cost_mode": "baseline",
                    "primary_metric_value": baseline,
                    "trade_count": 1,
                    "total_cost": 0.1,
                    "maximum_drawdown": -0.1,
                }
            )
            rows.append(
                {
                    "variant_id": variant["variant_id"],
                    "symbol": symbol,
                    "cost_mode": "stress",
                    "primary_metric_value": values[symbol],
                    "trade_count": 1,
                    "total_cost": 0.2,
                    "maximum_drawdown": -0.2,
                }
            )
    return rows


def _first_variant_row(values, failures=None, *, baseline=1.0):
    spec = _spec()
    variant_id = spec["variants"][0]["variant_id"]
    failure_map = {item["variant_id"]: [] for item in spec["variants"]}
    if failures:
        failure_map[variant_id] = failures
    return _variant_rows(spec, _cells(values, baseline=baseline), failure_map)[0]


def test_gate_strict_positivity_uses_greater_than_zero():
    row = _first_variant_row({"BTCUSDT": 0.0, "ETHUSDT": 0.1, "SOLUSDT": 0.1})
    assert row["stress_positive_asset_count"] == 2
    assert row["aggregate_stress_positive"] is True
    assert row["stress_asset_breadth_pass"] is True
    row = _first_variant_row({"BTCUSDT": 0.0, "ETHUSDT": 0.0, "SOLUSDT": 0.1})
    assert row["stress_positive_asset_count"] == 1
    assert row["stress_asset_breadth_pass"] is False


def test_negative_stressed_aggregate_fails_even_with_positive_baseline():
    row = _first_variant_row({"BTCUSDT": 0.2, "ETHUSDT": -0.4, "SOLUSDT": -0.1}, baseline=10.0)
    assert row["baseline_primary_aggregate"] > 0
    assert row["stress_primary_aggregate"] < 0
    assert row["aggregate_stress_positive"] is False
    assert row["mechanical_holdout_gate_pass"] is False


def test_stressed_asset_breadth_requires_two_positive_assets():
    one = _first_variant_row({"BTCUSDT": 0.3, "ETHUSDT": -0.1, "SOLUSDT": -0.1})
    two = _first_variant_row({"BTCUSDT": 0.3, "ETHUSDT": 0.1, "SOLUSDT": -0.1})
    assert one["stress_asset_breadth_pass"] is False
    assert one["mechanical_holdout_gate_pass"] is False
    assert two["stress_asset_breadth_pass"] is True
    assert two["mechanical_holdout_gate_pass"] is True


def test_integrity_failure_blocks_adjudication():
    row = _first_variant_row({"BTCUSDT": 0.3, "ETHUSDT": 0.1, "SOLUSDT": -0.1}, failures=["trial_x"])
    assert row["integrity_gate_pass"] is False
    assert row["mechanical_holdout_gate_pass"] is False


def test_repeated_generation_is_byte_identical_and_appends_no_trials(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    for name in ("data", "experiments", "qntylab"):
        shutil.copytree(ROOT / name, root / name)
    before_trials = len(load_canonical_history(root / "experiments/research").trials)

    def fail_run(*args, **kwargs):
        raise AssertionError("review generation must not execute strategy or backtest")

    monkeypatch.setattr(strategy_test, "run_strategy", fail_run)
    monkeypatch.setattr(backtest, "evaluate", fail_run)
    monkeypatch.chdir(root)
    review = build_review(root)
    first = write_outputs(review, root)
    first_bytes = {path: (root / path).read_bytes() for path in (CELLS_PATH, VARIANTS_PATH, JSON_PATH, MD_PATH)}
    second = write_outputs(build_review(root), root)
    second_bytes = {path: (root / path).read_bytes() for path in (CELLS_PATH, VARIANTS_PATH, JSON_PATH, MD_PATH)}
    assert first == second
    assert first_bytes == second_bytes
    assert len(load_canonical_history(root / "experiments/research").trials) == before_trials


def test_proposed_decisions_are_exact_variant_only_and_no_family_decision_is_produced():
    review = build_review(ROOT)
    assert len(review["proposed_decisions"]) == 3
    assert all(row["proposed_state"] in {"FOLLOW_UP", "GRAVEYARDED", "BLOCKED"} for row in review["proposed_decisions"])
    assert all("family" not in row for row in review["proposed_decisions"])
