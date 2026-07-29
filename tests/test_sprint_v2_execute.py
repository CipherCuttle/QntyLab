import json
from pathlib import Path

import numpy as np
import pytest

from qntylab.sprint_v2 import FrozenInputs
from qntylab.sprint_v2_execute import UNRESOLVED, _book, canonical_bytes, execute, execute_variant, verify_semantic_closure


VARIANT = ("H012_momentum_7d", 7, 1)


def fixture(days=4, names=10):
    symbols = tuple(f"S{i:02d}" for i in range(names))
    dates = tuple(f"2020-01-{i + 1:02d}" for i in range(days))
    close = np.tile(np.arange(100.0, 100.0 + names), (days, 1))
    scores = {name: np.tile(np.arange(float(names), 0.0, -1.0), (days, 1)) for name, _, _ in __import__("qntylab.sprint_v2", fromlist=["EXPECTED_FACTORS"]).EXPECTED_FACTORS}
    return FrozenInputs(dates, symbols, close, np.full_like(close, np.nan), np.full_like(close, np.nan), np.ones_like(close, dtype=bool), {}, scores, (5, 10, 20), 20260728, 2, True)


def test_breadth_bucket_direction_and_neutral_weights_are_closed():
    symbols = tuple(f"S{i}" for i in range(11)); score = np.arange(11.0, 0, -1)
    assert not np.any(_book(symbols[:9], score[:9], np.ones(9, bool), 1))
    book = _book(symbols, score, np.ones(11, bool), -1)
    assert book.sum() == pytest.approx(0) and book[0] == pytest.approx(-.5) and book[-1] == pytest.approx(.5)


def test_forced_gap_funding_sign_costs_and_objective_classification():
    inputs = fixture(); close = inputs.close.copy(); close[1, 0] = np.nan
    events = {inputs.symbols[0]: ({"timestamp": "2020-01-02T00:00:00Z", "funding_rate": "0.01"},)}
    custom = FrozenInputs(inputs.dates, inputs.symbols, close, inputs.funding, inputs.premium, inputs.eligible, events, inputs.scores, inputs.cost_bps, inputs.null_seed, inputs.null_count, True)
    result = execute_variant(custom, VARIANT)
    first = result["daily_portfolio_records"][0]
    assert inputs.symbols[0] in first["forced_close_symbols"] and first["funding_pnl"] < 0
    assert first["fees"]["10"] == pytest.approx(first["turnover"] * .001)
    assert result["classification"]["status"] == "OBJECTIVE_KILL"


def test_future_mutation_does_not_change_earlier_book_and_weekly_invalid_retains_book():
    inputs = fixture(days=9); before = execute_variant(inputs, VARIANT, anchor=2)
    scores = {key: value.copy() for key, value in inputs.scores.items()}; scores[VARIANT[0]][-1] *= -1
    changed = FrozenInputs(inputs.dates, inputs.symbols, inputs.close, inputs.funding, inputs.premium, inputs.eligible, inputs.funding_events, scores, inputs.cost_bps, inputs.null_seed, inputs.null_count, True)
    after = execute_variant(changed, VARIANT, anchor=2)
    assert before["daily_portfolio_records"][:-1] == after["daily_portfolio_records"][:-1]
    # Wednesday 2020-01-01 makes a valid book; the next Wednesday has only
    # nine finite scores and therefore retains it rather than substituting.
    scores[VARIANT[0]][7, -1] = np.nan
    retained = execute_variant(FrozenInputs(inputs.dates, inputs.symbols, inputs.close, inputs.funding, inputs.premium, inputs.eligible, inputs.funding_events, scores, inputs.cost_bps, inputs.null_seed, inputs.null_count, True), VARIANT, anchor=2)
    assert retained["daily_portfolio_records"][7]["weights"] == retained["daily_portfolio_records"][6]["weights"]


def test_ic_and_unresolved_positive_classification_and_closure_binding():
    inputs = fixture(); close = inputs.close.copy()
    close[1] = close[0] * (1 + np.linspace(.10, -.10, len(inputs.symbols)))
    close[2:] = close[1]
    result = execute_variant(FrozenInputs(inputs.dates, inputs.symbols, close, inputs.funding, inputs.premium, inputs.eligible, inputs.funding_events, inputs.scores, inputs.cost_bps, inputs.null_seed, inputs.null_count, True), VARIANT)
    assert result["ic"]["daily"][0]["value"] > .99
    assert result["classification"]["status"] == UNRESOLVED
    assert verify_semantic_closure(Path(__file__).resolve().parents[1])["closure_gates"]["EXECUTION_SEMANTICS_COMPLETE"]


def test_all_variants_weekly_and_seeded_null_are_deterministic():
    inputs = fixture()
    first, second = execute(inputs), execute(inputs)
    assert canonical_bytes(first) == canonical_bytes(second)
    assert len(first["variants"]) == 8
    for row in first["variants"]:
        assert set(row["weekly_robustness"]["anchors"]) == {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
        assert len(row["random_rank_null"]["draw_cost_reports"]) == 2
