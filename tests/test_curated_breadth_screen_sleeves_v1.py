import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from qntylab.backtest import evaluate
from qntylab.curated_breadth_screen import expand_planned_runs
from qntylab.research_ledger import compute_variant_id
from qntylab.strategies import positions
from qntylab.strategy_test import _strategy_warmup_bars, _validate_positions, run_strategy

from tests.test_strategy_test import config, research_root, write_fixture


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "experiments/specs/curated_breadth_screen_v1.json"


H006_VARIANTS = {
    1: "variant_66cfc915025fc7745f4c51e2",
    3: "variant_c21463e36d437e98cf38698b",
    6: "variant_1e859ceb2d7330750601ba1c",
    12: "variant_b2704b638049f154fd8799bd",
}
H007_VARIANTS = {
    24: "variant_622da030e9dacdf22315383b",
    72: "variant_66992d55a7d8a402179ce209",
    168: "variant_2ec6b5a20cd8e3181a6a46f0",
}


def _h007_params(rv_window=24):
    return {
        "fast": 24,
        "slow": 96,
        "realized_volatility_window": rv_window,
        "volatility_baseline_window": 720,
        "minimum_multiplier": 0.25,
        "maximum_multiplier": 1.0,
        "mode": "long_flat",
    }


def _rows(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open(newline="", encoding="utf-8")))


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)


def _write_hourly_fixture(path: Path, closes: list[float]) -> None:
    start = datetime(2021, 1, 1, tzinfo=UTC)
    rows = []
    for i, close in enumerate(closes):
        stamp = (start + timedelta(hours=i)).isoformat().replace("+00:00", "Z")
        rows.append({"timestamp": stamp, "open": str(close), "high": str(close), "low": str(close), "close": str(close), "volume": "1"})
    _write_rows(path, rows)


def test_h006_formula_alignment_zero_history_and_variant_ids():
    close = np.array([100.0, 110.0, 99.0, 99.0, 108.9])
    pos = positions("H006_short_horizon_reversal", close, {"lookback": 1, "mode": "long_short"})
    assert pos.tolist() == pytest.approx([0.0, 0.0, -1.0, 1.0, 0.0])
    assert pos[1] == 0.0
    result = evaluate(close, pos, 0)
    assert result["net_returns"] == pytest.approx([0.0, 0.0, 0.0, 0.1])

    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    for lookback, variant_id in H006_VARIANTS.items():
        candidate = next(item for item in spec["candidate_details"] if item["variant_id"] == variant_id)
        assert candidate["parameters"] == {"lookback": lookback, "mode": "long_short"}
        assert compute_variant_id(
            {
                "strategy_id": "H006_short_horizon_reversal",
                "strategy_version": "existing-qntylab-strategies-v1",
                "parameters": candidate["parameters"],
                "mode": "long_short",
                "expected_interval": "1h",
                "funding_boundary_mode": "NOT_APPLICABLE",
            }
        ) == variant_id


def test_h006_gap_handling_remains_fail_closed(tmp_path):
    good = tmp_path / "good.csv"
    bad = tmp_path / "bad.csv"
    write_fixture(good, [100, 101, 102, 101, 100, 99, 98, 97])
    write_fixture(bad, [100, 101, 102, 101, 100, 99, 98, 97], skip_hour=2)
    cfg = config(
        tmp_path,
        strategy_id="H006_short_horizon_reversal",
        input_path=str(good),
        evaluation_start="2021-01-01T02:00:00Z",
        evaluation_end="2021-01-01T07:00:00Z",
        parameters={"lookback": 1, "mode": "long_short"},
    )
    root = research_root(tmp_path, [cfg])
    assert run_strategy(
        strategy_id="H006_short_horizon_reversal",
        input_path=good,
        config_path=cfg,
        output=tmp_path / "good",
        research_root=root,
        require_clean_source=False,
    )["receipt"]["warmup_range"]["observation_count"] == 2
    with pytest.raises(ValueError, match="timestamp gap rejected"):
        run_strategy(
            strategy_id="H006_short_horizon_reversal",
            input_path=bad,
            config_path=cfg,
            output=tmp_path / "bad",
            research_root=root,
            require_clean_source=False,
        )


def test_h007_formula_uses_log_return_annualization_strict_prior_baseline_and_clipping():
    params = _h007_params(rv_window=24)
    close = 100 * np.exp(np.linspace(0, 1.7, 820) + 0.015 * np.sin(np.arange(820) / 3))
    pos = positions("H007_volatility_scaled_moving_average", close, params)

    t = 780
    returns = np.diff(np.log(close), prepend=np.nan)
    rv = np.sqrt(8760 * np.mean(returns[t - 23 : t + 1] ** 2))
    prior_rv = [
        np.sqrt(8760 * np.mean(returns[i - 23 : i + 1] ** 2))
        for i in range(t - 720, t)
    ]
    multiplier = float(np.clip(np.median(prior_rv) / rv, 0.25, 1.0))
    ma_fast = close[t - 23 : t + 1].mean()
    ma_slow = close[t - 95 : t + 1].mean()

    assert ma_fast > ma_slow
    assert pos[t + 1] == pytest.approx(multiplier)
    assert 0.25 <= pos[t + 1] <= 1.0
    simple_rv = np.sqrt(8760 * np.mean((close[t - 23 : t + 1] / close[t - 24 : t] - 1) ** 2))
    assert simple_rv != pytest.approx(rv)

    lower_vol_close = close.copy()
    lower_vol_close[t] = close[t - 1] * np.exp(returns[t] / 10)
    lower_vol_pos = positions("H007_volatility_scaled_moving_average", lower_vol_close, params)
    assert lower_vol_pos[t + 1] != pytest.approx(pos[t + 1])


def test_h007_base_zero_fractional_alignment_finite_bounds_and_variant_ids():
    params = _h007_params(rv_window=72)
    close = 100 * np.exp(-np.linspace(0, 1.5, 900) + 0.015 * np.sin(np.arange(900) / 4))
    pos = positions("H007_volatility_scaled_moving_average", close, params)
    assert np.all(np.isfinite(pos))
    assert float(pos.min()) >= 0.0
    assert float(pos.max()) <= 1.0
    assert pos[-1] == 0.0

    up_close = 100 * np.exp(np.linspace(0, 1.5, 900) + 0.02 * np.sin(np.arange(900) / 4))
    up_pos = positions("H007_volatility_scaled_moving_average", up_close, params)
    assert 0.0 < up_pos[-1] <= 1.0

    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    for rv_window, variant_id in H007_VARIANTS.items():
        candidate = next(item for item in spec["candidate_details"] if item["variant_id"] == variant_id)
        assert candidate["parameters"] == _h007_params(rv_window)
        assert compute_variant_id(
            {
                "strategy_id": "H007_volatility_scaled_moving_average",
                "strategy_version": "existing-qntylab-strategies-v1",
                "parameters": candidate["parameters"],
                "mode": "long_flat",
                "expected_interval": "1h",
                "funding_boundary_mode": "NOT_APPLICABLE",
            }
        ) == variant_id


def test_h007_warmup_affects_first_evaluation_bar_and_preperiod_is_excluded(tmp_path):
    fixture = tmp_path / "warm.csv"
    closes = (100 * np.exp(np.linspace(0, 1.8, 760) + 0.02 * np.sin(np.arange(760) / 5))).tolist()
    _write_hourly_fixture(fixture, closes)
    params = _h007_params(rv_window=24)
    start = _strategy_warmup_bars("H007_volatility_scaled_moving_average", params)
    start_stamp = _rows(fixture)[start]["timestamp"]
    end_stamp = _rows(fixture)[start + 5]["timestamp"]
    cfg = config(
        tmp_path,
        strategy_id="H007_volatility_scaled_moving_average",
        input_path=str(fixture),
        evaluation_start=start_stamp,
        evaluation_end=end_stamp,
        parameters=params,
        fee_bps=0,
    )
    root = research_root(tmp_path, [cfg])
    result = run_strategy(
        strategy_id="H007_volatility_scaled_moving_average",
        input_path=fixture,
        config_path=cfg,
        output=tmp_path / "warm",
        research_root=root,
        require_clean_source=False,
    )
    full_pos = positions("H007_volatility_scaled_moving_average", np.array(closes), params)
    eval_pos = full_pos[start : start + 6]
    assert result["receipt"]["warmup_range"]["observation_count"] == start
    assert result["metrics"]["observation_count"] == 5
    assert result["metrics"]["exposure_fraction"] == pytest.approx(float(np.abs(eval_pos).mean()))
    assert result["metrics"]["total_cost"] == pytest.approx(float(np.abs(np.diff(eval_pos)).sum() * 0))

    no_warm_cfg = config(
        tmp_path,
        strategy_id="H007_volatility_scaled_moving_average",
        input_path=str(fixture),
        evaluation_start="2021-01-01T00:00:00Z",
        evaluation_end="2021-01-01T05:00:00Z",
        parameters=params,
    )
    with pytest.raises(ValueError, match="insufficient warmup observations"):
        run_strategy(
            strategy_id="H007_volatility_scaled_moving_average",
            input_path=fixture,
            config_path=no_warm_cfg,
            output=tmp_path / "no-warm",
            research_root=research_root(tmp_path / "no-warm-root", [no_warm_cfg]),
            require_clean_source=False,
        )


def test_warmup_and_evaluation_gaps_fail_closed(tmp_path):
    params = _h007_params(rv_window=24)
    start = _strategy_warmup_bars("H007_volatility_scaled_moving_average", params)
    good = tmp_path / "good.csv"
    warm_gap = tmp_path / "warm_gap.csv"
    eval_gap = tmp_path / "eval_gap.csv"
    _write_hourly_fixture(good, (100 + np.arange(start + 8)).tolist())
    rows = _rows(good)
    for row in rows[start - 3 :]:
        stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")) + timedelta(hours=1)
        row["timestamp"] = stamp.isoformat().replace("+00:00", "Z")
    _write_rows(warm_gap, rows)
    rows = _rows(good)
    for row in rows[start + 3 :]:
        stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")) + timedelta(hours=1)
        row["timestamp"] = stamp.isoformat().replace("+00:00", "Z")
    _write_rows(eval_gap, rows)
    start_stamp = _rows(good)[start]["timestamp"]
    end_stamp = _rows(good)[start + 6]["timestamp"]
    cfg = config(
        tmp_path,
        strategy_id="H007_volatility_scaled_moving_average",
        input_path=str(good),
        evaluation_start=start_stamp,
        evaluation_end=end_stamp,
        parameters=params,
    )
    root = research_root(tmp_path, [cfg])
    for bad in (warm_gap, eval_gap):
        with pytest.raises(ValueError):
            run_strategy(
                strategy_id="H007_volatility_scaled_moving_average",
                input_path=bad,
                config_path=cfg,
                output=tmp_path / bad.stem,
                research_root=root,
                require_clean_source=False,
            )


def test_fractional_position_accounting_and_validation():
    close = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
    position = np.array([0.0, 0.5, 0.75, 0.25, 0.0])
    result = evaluate(close, position, 20)
    turnover = np.array([0.5, 0.25, 0.5, 0.25])
    assert result["turnover"] == pytest.approx(float(turnover.sum()))
    assert result["fee_cost"] == pytest.approx(float(turnover.sum() * 20 / 10_000))
    assert evaluate(close, np.array([0.5, 0.5, 0.5, 0.5, 0.5]), 20)["turnover"] == 0

    params = {"mode": "long_flat"}
    _validate_positions(position, "H007_volatility_scaled_moving_average", params)
    for bad in (
        np.array([0.0, 1.1]),
        np.array([0.0, -0.1]),
        np.array([0.0, np.nan]),
        np.array([0.0, np.inf]),
    ):
        with pytest.raises(ValueError):
            _validate_positions(bad, "H007_volatility_scaled_moving_average", params)


def test_existing_strategy_regression_values_remain_unchanged():
    close = np.array([100.0, 110.0, 99.0, 99.0, 108.9])
    h002 = positions("H002_momentum", close, {"lookback": 1, "mode": "long_short"})
    assert h002.tolist() == pytest.approx([0.0, 0.0, 1.0, -1.0, 0.0])
    h002_result = evaluate(close, h002, 10)
    assert h002_result["gross_cumulative_return"] == pytest.approx(-0.1)
    assert h002_result["fee_cost"] == pytest.approx(0.004)
    assert h002_result["trade_count"] == 3

    h003 = positions("H003_moving_average", np.array([1, 2, 3, 4, 3, 2], dtype=float), {"fast": 2, "slow": 3, "mode": "long_flat"})
    h005 = positions("H005_donchian", np.array([1, 2, 3, 2, 1, 4], dtype=float), {"lookback": 2, "mode": "long_flat"})
    assert h003.tolist() == pytest.approx([0, 0, 0, 1, 1, 1])
    assert h005.tolist() == pytest.approx([0, 0, 0, 1, 0, 0])


def test_screen_expansion_is_deterministic_unique_and_non_mutating():
    before_trials = (ROOT / "experiments/research/trials/2026.jsonl").read_bytes()
    first = expand_planned_runs(SPEC_PATH, repo_root=ROOT)
    second = expand_planned_runs(SPEC_PATH, repo_root=ROOT)
    assert first == second
    assert len(first) == 360
    assert len({item["trial_id"] for item in first}) == 360
    assert len({item["variant_id"] for item in first}) == 15
    assert {item["variant_id"] for item in first} == set(json.loads(SPEC_PATH.read_text(encoding="utf-8"))["new_variant_ids"])
    assert {item["candidate_id"] for item in first} == set(json.loads(SPEC_PATH.read_text(encoding="utf-8"))["new_candidate_ids"])
    assert (ROOT / "experiments/research/trials/2026.jsonl").read_bytes() == before_trials
    assert all(item["config"]["research_intent"] == "SCREEN" for item in first)
    assert "variant_282aa437c78189c7c8b2c124" not in {item["variant_id"] for item in first}
    assert "variant_aa66ba0edf856ac06f055917" not in {item["variant_id"] for item in first}
