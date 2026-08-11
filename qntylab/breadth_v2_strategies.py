"""Pure, causal Breadth V2 target-weight generators.

These functions never account for cash, PnL, funding, or costs.  They only
turn observations available at a decision boundary into target weights.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


def _require(values: Sequence[float], n: int, name: str) -> None:
    if len(values) < n:
        raise ValueError(f"{name} requires {n} observations")


def time_series_momentum(closes: Sequence[float], lookback: int) -> float:
    _require(closes, lookback + 1, "momentum")
    return 1.0 if closes[-1] > closes[-1 - lookback] else 0.0


def moving_average_trend(closes: Sequence[float], fast: int, slow: int) -> float:
    _require(closes, slow, "moving average")
    return 1.0 if sum(closes[-fast:]) / fast > sum(closes[-slow:]) / slow else 0.0


def price_breakout(closes: Sequence[float], lookback: int, prior_state: float = 0.0) -> float:
    """Persistent channel state; the channel excludes close_t itself."""
    _require(closes, lookback + 1, "breakout")
    prior = closes[-lookback - 1 : -1]
    if closes[-1] > max(prior):
        return 1.0
    if closes[-1] < min(prior):
        return 0.0
    return float(bool(prior_state))


def cross_sectional_weights(
    lookback: int,
    closes_by_symbol: Mapping[str, Sequence[float]],
    panel_order: Sequence[str],
    reversal: bool = False,
) -> dict[str, float]:
    if len(panel_order) != 20 or set(panel_order) != set(closes_by_symbol):
        raise ValueError("fixed 20-asset panel is incomplete or changed")
    scores = {}
    for symbol in panel_order:
        values = closes_by_symbol[symbol]
        _require(values, lookback + 1, "cross-sectional rank")
        scores[symbol] = values[-1] / values[-1 - lookback] - 1.0
    ranked = sorted(panel_order, key=lambda s: ((scores[s] if reversal else -scores[s]), panel_order.index(s)))
    longs, shorts = ranked[:4], ranked[-4:]
    weights = {symbol: 0.0 for symbol in panel_order}
    for symbol in longs:
        weights[symbol] = 0.25
    for symbol in shorts:
        weights[symbol] = -0.25
    return weights


def funding_carry_weights(
    events_by_symbol: Mapping[str, Sequence[float]],
    window_events: int,
    panel_order: Sequence[str],
) -> dict[str, float]:
    if len(panel_order) != 20 or set(panel_order) != set(events_by_symbol):
        raise ValueError("fixed 20-asset panel is incomplete or changed")
    scores = {}
    for symbol in panel_order:
        events = events_by_symbol[symbol]
        _require(events, window_events, "funding carry")
        scores[symbol] = sum(events[-window_events:]) / window_events
    ranked = sorted(panel_order, key=lambda s: (scores[s], panel_order.index(s)))
    weights = {symbol: 0.0 for symbol in panel_order}
    for symbol in ranked[:4]:
        weights[symbol] = 0.25
    for symbol in ranked[-4:]:
        weights[symbol] = -0.25
    return weights


def volatility_targeting(
    closes: Sequence[float], realized_volatility_window: int, *, fast: int = 24, slow: int = 96,
    target: float = 0.25, baseline_window: int = 720,
) -> float:
    if baseline_window != 720:
        raise ValueError("volatility_baseline_window is identity compatibility only and must be 720")
    _require(closes, max(slow, realized_volatility_window) + 1, "volatility targeting")
    base = moving_average_trend(closes, fast, slow)
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - realized_volatility_window, len(closes))]
    rv = math.sqrt(8760.0 * sum(r * r for r in returns) / len(returns))
    multiplier = max(0.25, min(1.0, target / rv)) if rv else 1.0
    return base * multiplier


def target_weights(family: str, params: Mapping[str, object], **observations: object) -> dict[str, float] | float:
    if family == "TIME_SERIES_MOMENTUM":
        return time_series_momentum(observations["closes"], int(params["lookback"]))
    if family == "MOVING_AVERAGE_TREND":
        return moving_average_trend(observations["closes"], int(params["fast"]), int(params["slow"]))
    if family == "PRICE_BREAKOUT":
        return price_breakout(observations["closes"], int(params["lookback"]), float(observations.get("prior_state", 0)))
    if family == "CROSS_SECTIONAL_MOMENTUM":
        return cross_sectional_weights(int(params["lookback"]), observations["closes_by_symbol"], observations["panel_order"])
    if family == "CROSS_SECTIONAL_REVERSAL":
        return cross_sectional_weights(int(params["lookback"]), observations["closes_by_symbol"], observations["panel_order"], True)
    if family == "FUNDING_CARRY":
        return funding_carry_weights(observations["events_by_symbol"], int(params["funding_window_events"]), observations["panel_order"])
    if family == "VOLATILITY_TARGETING":
        return volatility_targeting(observations["closes"], int(params["realized_volatility_window"]), baseline_window=int(params["volatility_baseline_window"]))
    raise ValueError(f"unsupported Breadth V2 family: {family}")
