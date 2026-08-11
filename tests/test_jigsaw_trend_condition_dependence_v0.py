from __future__ import annotations

import numpy as np
import pytest

from datetime import UTC, datetime, timedelta
from pathlib import Path

from qntylab.jigsaw_trend_condition_dependence_v0 import COST_MODES, HORIZON_HOURS, NORMALIZATION_DAYS, PARAMETERS, _sha256, _utility, historical_percentile, longest_common_contiguous, state_bin


def test_percentile_is_pit_and_future_invariant():
    values = np.arange(NORMALIZATION_DAYS + 1, dtype=float)
    before = historical_percentile(values, NORMALIZATION_DAYS)
    extended = np.r_[values, np.repeat(-999.0, 100)]
    assert historical_percentile(extended, NORMALIZATION_DAYS) == before == 100.0


def test_percentile_requires_complete_trailing_history():
    with pytest.raises(ValueError):
        historical_percentile(np.arange(NORMALIZATION_DAYS, dtype=float), NORMALIZATION_DAYS - 1)


def test_labels_are_24h_and_flat_is_exact_zero():
    close = np.arange(1, 40, dtype=float)
    flat = np.zeros_like(close)
    assert _utility(close, flat, 3, 20.0) == 0.0
    assert HORIZON_HOURS == 24


def test_label_does_not_read_past_24h():
    close = np.arange(1, 40, dtype=float)
    position = np.ones_like(close)
    before = _utility(close, position, 3, 0.0)
    close[29:] *= 1000
    assert _utility(close, position, 3, 0.0) == before


def test_cost_modes_cannot_mix_and_parameters_are_frozen():
    assert PARAMETERS == {"fast": 24, "slow": 96, "mode": "long_flat"}
    assert state_bin(100 / 3) == "LOW"
    assert state_bin(200 / 3) == "HIGH"
    assert COST_MODES["BASELINE"] != COST_MODES["STRESS"]


def test_gap_is_not_filled_or_bridged():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    timestamps = [start + timedelta(hours=i) for i in (0, 1, 3, 4)]
    selected, _ = longest_common_contiguous({"BTCUSDT": (timestamps, np.ones(4)), "ETHUSDT": (timestamps, np.ones(4)), "SOLUSDT": (timestamps, np.ones(4))})
    assert len(selected) == 2
    assert selected[1] - selected[0] == timedelta(hours=1)


def test_load_bearing_input_digest_changes(tmp_path: Path):
    path = tmp_path / "input.csv"
    path.write_text("x\n", encoding="utf-8")
    before = _sha256(path)
    path.write_text("y\n", encoding="utf-8")
    assert _sha256(path) != before


def test_no_outcome_selected_strategy_path():
    source = Path("qntylab/jigsaw_trend_condition_dependence_v0.py").read_text(encoding="utf-8")
    assert "moving_average(close[asset], **PARAMETERS)" in source
    assert "best strategy" not in source.lower()
