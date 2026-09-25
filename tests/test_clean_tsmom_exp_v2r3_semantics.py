import json

import pytest

from qntylab.clean_tsmom_exp_v2r3 import END, START, SYMBOLS, _events, classify, compare
from tests._clean_tsmom_exp_v2r3_fixture import r3_case, run_producer


def _out(case, tmp_path):
    output = tmp_path / "out"; result = run_producer(case, output); assert result.returncode == 0, result.stderr
    return {p.stem: json.loads(p.read_bytes()) for p in output.glob("*.json")}


def test_r3_causal_timeline_and_boundaries(r3_case, tmp_path):
    out = _out(r3_case, tmp_path)
    panel, signals, v1, v2 = out["main_panel"], out["main_signals"], out["main_v1_weights"], out["main_v2_weights"]
    assert panel[0]["timestamp"] == START and panel[-1]["timestamp"] < END
    assert all(a["timestamp"] == b["timestamp"] for a, b in zip(panel, signals))
    assert all(a["timestamp"] == b["timestamp"] for a, b in zip(signals, v1))
    assert any(set(row[s] for s in SYMBOLS) == {0} for row in signals)
    assert any(set(row[s] for s in SYMBOLS) == {1} for row in signals)
    assert all(sum(row[s] for s in SYMBOLS) <= 1.0 + 1e-12 for row in v2)
    assert out["controls"]["no_same_bar_execution"] and out["controls"]["t_plus_1_execution"]
    assert out["controls"]["evidence"]["main_first_start"] == START
    assert out["controls"]["evidence"]["main_last_end"] == END
    assert out["main_metrics"]["CLEAN_V1"]["base"]["observation_count"] == len(panel) + 1


def test_r3_weight_and_funding_semantics_are_behaviorally_present(r3_case, tmp_path):
    out = _out(r3_case, tmp_path)
    first = out["main_v1_weights"][0]
    assert all(first[s] in (0, 1 / 9) for s in SYMBOLS)
    assert any(any(row[s] != 0 for s in SYMBOLS) for row in out["main_funding_assignments"])
    assert out["controls"]["funding_uses_carried_weight"]
    assert out["controls"]["funding_not_early"] and out["controls"]["funding_not_duplicated"]
    assert out["controls"]["initial_transaction_charged"] and out["controls"]["final_liquidation_charged_once"]
    assert all(out["final_liquidation"][name]["timestamp"] == END for name in ("CLEAN_V1", "CLEAN_V2"))
    assert out["controls"]["exact_90_return_volatility_window"] and out["controls"]["volatility_ddof_zero"]


def test_duplicate_funding_timestamps_are_rejected_by_r3_event_path():
    funding = {s: [{"timestamp": 2, "funding_rate": 0.1}, {"timestamp": 2, "funding_rate": -0.1}] for s in SYMBOLS}
    with pytest.raises(ValueError, match="duplicate funding"):
        _events(funding, 0, 3)


@pytest.mark.parametrize("metrics,expected", [
    ({"base": {"net_return": 0, "naive_annualized_sharpe": 1}, "stress": {"net_return": 1, "naive_annualized_sharpe": 1}}, "PRELIMINARY_KILLED"),
    ({"base": {"net_return": 1, "naive_annualized_sharpe": 1}, "stress": {"net_return": 1, "naive_annualized_sharpe": 1}}, "PRELIMINARY_SURVIVES"),
    ({"base": {"net_return": 1, "naive_annualized_sharpe": 1}, "stress": {"net_return": 0, "naive_annualized_sharpe": 1}}, "PRELIMINARY_INCONCLUSIVE"),
])
def test_every_classification_boundary_is_explicit(metrics, expected):
    assert classify(metrics) == expected


def test_every_pareto_comparison_boundary_is_explicit():
    base = {"base": {"net_return": 1, "naive_annualized_sharpe": 1, "maximum_drawdown": -1}, "stress": {"net_return": 1, "naive_annualized_sharpe": 1, "maximum_drawdown": -1}}
    better = {"base": {"net_return": 2, "naive_annualized_sharpe": 2, "maximum_drawdown": -1}, "stress": {"net_return": 2, "naive_annualized_sharpe": 2, "maximum_drawdown": -1}}
    worse = {"base": {"net_return": 2, "naive_annualized_sharpe": 0, "maximum_drawdown": -2}, "stress": {"net_return": 0, "naive_annualized_sharpe": 2, "maximum_drawdown": -1}}
    assert compare(base, better) == "V2_DOMINATES_V1"
    assert compare(better, base) == "V2_INFERIOR_TO_V1"
    assert compare(base, worse) == "V2_PACKAGING_COMPARISON_INCONCLUSIVE"


def test_controls_are_evidence_bearing_not_unsupported_constants(r3_case, tmp_path):
    controls = _out(r3_case, tmp_path)["controls"]
    assert set(controls["evidence"]) == {"main_first_start", "main_last_end"}
    assert controls["evidence"]["main_first_start"] < controls["evidence"]["main_last_end"]
