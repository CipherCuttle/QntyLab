from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from qntylab import h003_edge_falsification_v0 as h003
from qntylab.research_ledger import compute_trial_id


ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "experiments/specs/h003_edge_falsification_v0_trial_authorization.json"


def test_compiler_matches_exact_frozen_44_trial_authorization() -> None:
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    plan = h003.compile_plan()
    assert len(plan) == 44
    assert len({row["trial_id"] for row in plan}) == 44
    assert {row["trial_id"] for row in plan} == set(auth["authorized_trial_ids"])
    assert {row["window_id"] for row in plan} == {row["id"] for row in auth["metadata"]["windows"]}
    assert {row["cost_mode"] for row in plan} == {row["id"] for row in auth["metadata"]["cost_modes"]}
    assert all(row["config"]["parameters"] == {"fast": 48, "slow": 192, "mode": "long_flat"} for row in plan)
    assert all(row["config"]["research_intent"] == "FOLLOW_UP" for row in plan)


def test_2023_config_binds_historical_normalization_snapshot() -> None:
    rows = [row for row in h003.compile_plan() if row["window_id"] == "BLOCK_2023_KNOWN_HOLDOUT"]
    assert len(rows) == 4
    for row in rows:
        provenance = row["config"]["normalization_provenance"]
        assert row["config"]["input_path"] == h003.NORMALIZED_2023_INPUT
        assert row["input_sha256"] == h003.NORMALIZED_SHA
        assert provenance["authoritative_raw_sha256"] == h003.RAW_SNAPSHOT_SHA
        assert provenance["source_resolution_git_commit"] == h003.SOURCE_RESOLUTION_COMMIT
        assert provenance["authoritative_raw_snapshot_manifest_git_commit"] == h003.RAW_SNAPSHOT_MANIFEST_COMMIT


def test_no_execution_surface_and_plan_writer_is_result_blind(tmp_path: Path) -> None:
    manifest = h003.write_plan(tmp_path / "plan")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["result_blind"] is True
    assert payload["execution_performed"] is False
    assert payload["trial_count"] == 44
    assert len(list((tmp_path / "plan/configs").glob("*.json"))) == 44
    assert not hasattr(h003, "execute")
    assert not hasattr(h003, "run_trials")


def test_compiled_trial_ids_are_independently_recomputable() -> None:
    for row in h003.compile_plan():
        config = row["config"]
        assert row["trial_id"] == compute_trial_id(
            variant_id="variant_00eb140f03a5f6ab40600160",
            symbol="SOLUSDT",
            input_sha256=row["input_sha256"],
            evaluation_start=config["evaluation_start"],
            evaluation_end=config["evaluation_end"],
            fee_bps=config["fee_bps"],
            slippage_bps=config["slippage_bps"],
            gap_policy="REJECT",
            expected_interval="1h",
        )


def test_return_accounting_matches_frozen_formula() -> None:
    close = np.array([100.0, 110.0, 99.0, 108.9])
    position = np.array([1.0, 1.0, 0.0, 1.0])
    net = h003.net_return_path(close, position, 10.0)
    expected = np.array([0.10, -0.101, -0.001])
    np.testing.assert_allclose(net, expected, rtol=0, atol=1e-12)
    metrics = h003.metrics_from_returns(net)
    assert metrics["observation_count"] == 3
    assert metrics["maximum_drawdown"] < 0


def test_reporting_slice_owns_return_by_ending_close() -> None:
    timestamps = [
        "2023-12-31T23:00:00Z",
        "2024-01-01T00:00:00Z",
        "2024-01-01T01:00:00Z",
        "2025-01-01T00:00:00Z",
    ]
    mask = h003.owned_return_mask(timestamps, "2024-01-01T00:00:00Z", "2024-12-31T23:00:00Z")
    assert mask.tolist() == [True, True, False]


def test_exposure_matched_random_control_preserves_path_invariants() -> None:
    held = np.array([0, 0, 1, 1, 1, 0, 1, 1, 0, 0, 0, 1], dtype=float)
    control = h003.exposure_matched_random_timing(held, 17011)
    assert len(control) == len(held)
    assert int(control.sum()) == int(held.sum())
    assert control[0] == held[0]
    assert set(control.tolist()) <= {0.0, 1.0}
    np.testing.assert_array_equal(control, h003.exposure_matched_random_timing(held, 17011))


def test_delayed_control_is_exact_24_bar_lag() -> None:
    held = np.arange(30) % 2
    delayed = h003.delayed_24h(held.astype(float))
    np.testing.assert_array_equal(delayed[:24], np.zeros(24))
    np.testing.assert_array_equal(delayed[24:], held[:6])


def test_verdict_fail_closed_and_falsification_precedes_candidate() -> None:
    assert h003.verdict({}) == "BLOCKED_BY_INPUT_OR_INTEGRITY"
    summary = {
        "baseline": {"annualized_sharpe": 0.5, "calmar_ratio": 0.8, "maximum_drawdown": -0.2},
        "stress": {"annualized_sharpe": 0.2, "calmar_ratio": 0.3},
        "buy_and_hold": {"annualized_sharpe": 0.6, "calmar_ratio": 0.7, "maximum_drawdown": -0.5},
        "block_random_wins_sharpe": 5,
        "block_random_wins_calmar": 5,
        "prior_2023_failure_preserved": True,
    }
    assert h003.verdict(summary) == "FALSIFIED"
    summary["baseline"]["annualized_sharpe"] = 0.9
    assert h003.verdict(summary) == "DEFENSIVE_EDGE_CANDIDATE"
