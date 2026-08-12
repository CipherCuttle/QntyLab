"""Frozen, synthetic-testable implementation for Jigsaw Harvest V0.

This module deliberately has no snapshot reader, network client, or execution
entry point.  A later, separately authorized phase may provide verified bars to
the private construction seam.  This implementation phase cannot calculate a
scientific result from the real snapshot.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Sequence


EXPERIMENT_ID = "JIGSAW_HARVEST_V0_PREREGISTRATION_V0"
PREREGISTRATION_DIGEST = "499b355ee2b308b4ae01e8c63b44a9a361d44d50fe381080131f41a4851849e3"
EXPECTED_SNAPSHOT_ID = "rds-v0-c0fa7dc0e51c7680fccbd7e7cdd0945fcd63af3e8c75809a24aa3b216868b9ac"
EXPECTED_SNAPSHOT_DIGEST = "c0fa7dc0e51c7680fccbd7e7cdd0945fcd63af3e8c75809a24aa3b216868b9ac"
UNIVERSE = (
    "ALICEUSDT", "APEUSDT", "API3USDT", "APTUSDT", "BCHUSDT", "CHRUSDT", "CHZUSDT", "ETCUSDT", "GMTUSDT", "INJUSDT",
    "LDOUSDT", "LINKUSDT", "LTCUSDT", "ONEUSDT", "OPUSDT", "REEFUSDT", "SANDUSDT", "TRXUSDT", "XLMUSDT", "XRPUSDT",
)
PROPOSITION_IDS = ("JH01_RV_PERSISTENCE", "JH02_DISPERSION_TO_RV", "JH03_BREADTH_TO_RETURN", "JH04_DRAWDOWN_TO_RETURN")
FIRST_BAR_OPEN = "2023-10-18T23:00:00Z"
LAST_BAR_OPEN = "2025-06-19T23:00:00Z"
FIRST_DECISION = "2023-11-18T00:00:00Z"
LAST_DECISION = "2025-06-19T00:00:00Z"
OBSERVATION_COUNT = 580
HAC_LAG = 5
HAC_CRITICAL_VALUE_95 = 1.959963984540054
FAMILYWISE_ALPHA = 0.05
AUTHORITY = "NON_AUTHORITATIVE_EXPLORATORY_ONLY"


class FrozenInputError(ValueError):
    """A frozen coverage, provenance, or result-completeness invariant failed."""


class RealExecutionDisabledError(RuntimeError):
    """Raised before real snapshot bars can enter this implementation candidate."""


@dataclass(frozen=True)
class BarClose:
    """A source bar identified by open time, with its closing price and availability."""

    bar_open_time: datetime
    close: float
    safe_known_after: datetime


@dataclass(frozen=True)
class DesignRow:
    decision_time: datetime
    rv24_prior: float
    dispersion24: float
    breadth7d: float
    drawdown_depth30d: float
    rv24_future: float
    market_return_future: float


@dataclass(frozen=True)
class RegressionResult:
    proposition_id: str
    beta: float
    hac_standard_error: float
    confidence_interval_95: tuple[float, float]
    raw_p_value_two_sided: float
    holm_adjusted_p_value: float
    classification: str


def _utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise FrozenInputError("timezone-aware UTC timestamp required")
    return value.astimezone(UTC)


def _stamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def preregistration_digest(value: Mapping[str, Any]) -> str:
    """Digest the preregistration semantics without its self-referential field."""
    body = {key: item for key, item in value.items() if key != "preregistration_digest"}
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def result_digest(value: Mapping[str, Any]) -> str:
    """Digest a deterministic receipt without its self-referential field."""
    body = {key: item for key, item in value.items() if key != "result_digest"}
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def primary_hac_bandwidth(observation_count: int) -> int:
    if observation_count != OBSERVATION_COUNT:
        raise FrozenInputError("the frozen harvest requires exactly 580 common observations")
    return math.floor(4 * (observation_count / 100) ** (2 / 9))


def canonical_schedule() -> tuple[datetime, ...]:
    first, last = _utc(FIRST_DECISION), _utc(LAST_DECISION)
    schedule = tuple(first + timedelta(days=index) for index in range(OBSERVATION_COUNT))
    if schedule[-1] != last or primary_hac_bandwidth(len(schedule)) != HAC_LAG:
        raise AssertionError("frozen schedule or HAC derivation is inconsistent")
    return schedule


def derive_common_schedule(*, first_bar_open: datetime | str, last_bar_open: datetime | str) -> tuple[datetime, ...]:
    """Derive and then bind the only permitted decision schedule from coverage."""
    first_open, last_open = _utc(first_bar_open), _utc(last_bar_open)
    if (first_open, last_open) != (_utc(FIRST_BAR_OPEN), _utc(LAST_BAR_OPEN)):
        raise FrozenInputError("snapshot coverage differs from the frozen V0 coverage")
    first_close = first_open + timedelta(hours=1)
    last_close = last_open + timedelta(hours=1)
    earliest = first_close + timedelta(hours=720)
    latest = last_close - timedelta(hours=24)
    if (earliest, latest) != (_utc(FIRST_DECISION), _utc(LAST_DECISION)):
        raise FrozenInputError("coverage arithmetic does not yield the frozen decision endpoints")
    return canonical_schedule()


def validate_real_snapshot_identity(*, snapshot_id: str, snapshot_digest: str, universe: Sequence[str]) -> None:
    if snapshot_id != EXPECTED_SNAPSHOT_ID or snapshot_digest != EXPECTED_SNAPSHOT_DIGEST:
        raise FrozenInputError("snapshot substitution rejected")
    if tuple(universe) != UNIVERSE:
        raise FrozenInputError("universe mutation rejected")


def real_execution_is_disabled(*, snapshot_id: str, snapshot_digest: str, universe: Sequence[str]) -> None:
    """The only public real-snapshot seam: validate identity then fail before data access."""
    validate_real_snapshot_identity(snapshot_id=snapshot_id, snapshot_digest=snapshot_digest, universe=universe)
    raise RealExecutionDisabledError("real Jigsaw Harvest execution is separately gated and disabled in this candidate")


def asset_log_return(previous_close: float, current_close: float) -> float:
    if not all(isinstance(item, (int, float)) and math.isfinite(item) and item > 0 for item in (previous_close, current_close)):
        raise FrozenInputError("positive finite closes required")
    return math.log(float(current_close) / float(previous_close))


def market_hourly_return(asset_returns: Mapping[str, float]) -> float:
    if tuple(asset_returns) != UNIVERSE:
        raise FrozenInputError("market return requires the exact ordered universe")
    values = tuple(asset_returns[symbol] for symbol in UNIVERSE)
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in values):
        raise FrozenInputError("finite asset returns required")
    return sum(values) / len(UNIVERSE)


def market_return_24(hourly_market_returns: Sequence[float]) -> float:
    if len(hourly_market_returns) != 24 or any(not math.isfinite(value) for value in hourly_market_returns):
        raise FrozenInputError("exactly 24 finite market returns required")
    return sum(hourly_market_returns)


def market_rv24(hourly_market_returns: Sequence[float]) -> float:
    if len(hourly_market_returns) != 24 or any(not math.isfinite(value) for value in hourly_market_returns):
        raise FrozenInputError("exactly 24 finite market returns required")
    return math.sqrt(sum(value * value for value in hourly_market_returns))


def dispersion24(asset_returns_24h: Mapping[str, float]) -> float:
    if tuple(asset_returns_24h) != UNIVERSE:
        raise FrozenInputError("dispersion requires the exact ordered universe")
    values = tuple(asset_returns_24h[symbol] for symbol in UNIVERSE)
    if any(not math.isfinite(value) for value in values):
        raise FrozenInputError("finite 24-hour asset returns required")
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def breadth7d(asset_returns_7d: Mapping[str, float]) -> float:
    if tuple(asset_returns_7d) != UNIVERSE:
        raise FrozenInputError("breadth requires the exact ordered universe")
    values = tuple(asset_returns_7d[symbol] for symbol in UNIVERSE)
    if any(not math.isfinite(value) for value in values):
        raise FrozenInputError("finite seven-day asset returns required")
    return sum(value > 0 for value in values) / len(values)


def drawdown_depth30d(index_window: Sequence[float]) -> float:
    if len(index_window) != 721 or any(not math.isfinite(value) or value <= 0 for value in index_window):
        raise FrozenInputError("721 positive finite inclusive index values required")
    peak = max(index_window)
    return 1.0 - index_window[-1] / peak


def _validate_hourly_partition(rows: Sequence[BarClose]) -> dict[datetime, BarClose]:
    if not rows:
        raise FrozenInputError("empty bar partition")
    mapping: dict[datetime, BarClose] = {}
    for row in rows:
        opened, known = _utc(row.bar_open_time), _utc(row.safe_known_after)
        if not isinstance(row.close, (int, float)) or not math.isfinite(row.close) or row.close <= 0:
            raise FrozenInputError("positive finite close required")
        if known != opened + timedelta(hours=1):
            raise FrozenInputError("safe-known-after must equal the source bar close")
        if opened in mapping:
            raise FrozenInputError("duplicate bar open")
        mapping[opened] = row
    opens = sorted(mapping)
    if any(right - left != timedelta(hours=1) for left, right in zip(opens, opens[1:])):
        raise FrozenInputError("hourly gap rejected")
    if (opens[0], opens[-1]) != (_utc(FIRST_BAR_OPEN), _utc(LAST_BAR_OPEN)):
        raise FrozenInputError("partition coverage differs from frozen snapshot coverage")
    return mapping


def _build_design_rows(*, bars_by_symbol: Mapping[str, Sequence[BarClose]]) -> tuple[DesignRow, ...]:
    """Private future-execution seam; never called by this implementation task."""
    if tuple(bars_by_symbol) != UNIVERSE:
        raise FrozenInputError("exact ordered 20-symbol bar mapping required")
    bars = {symbol: _validate_hourly_partition(bars_by_symbol[symbol]) for symbol in UNIVERSE}
    schedule = derive_common_schedule(first_bar_open=FIRST_BAR_OPEN, last_bar_open=LAST_BAR_OPEN)
    first_open = _utc(FIRST_BAR_OPEN)
    opens = tuple(first_open + timedelta(hours=index) for index in range(int((_utc(LAST_BAR_OPEN) - first_open).total_seconds() // 3600) + 1))
    close_boundaries = tuple(opened + timedelta(hours=1) for opened in opens)
    asset_returns: dict[str, dict[datetime, float]] = {symbol: {} for symbol in UNIVERSE}
    market_returns: dict[datetime, float] = {}
    for prior_open, current_open in zip(opens, opens[1:]):
        close_boundary = current_open + timedelta(hours=1)
        per_asset = {symbol: asset_log_return(bars[symbol][prior_open].close, bars[symbol][current_open].close) for symbol in UNIVERSE}
        for symbol in UNIVERSE:
            asset_returns[symbol][close_boundary] = per_asset[symbol]
        market_returns[close_boundary] = market_hourly_return(per_asset)
    first_close = close_boundaries[0]
    index: dict[datetime, float] = {first_close: 1.0}
    for boundary in close_boundaries[1:]:
        index[boundary] = index[boundary - timedelta(hours=1)] * math.exp(market_returns[boundary])
    rows: list[DesignRow] = []
    for decision in schedule:
        past24 = tuple(decision - timedelta(hours=offset) for offset in range(23, -1, -1))
        past168 = tuple(decision - timedelta(hours=offset) for offset in range(167, -1, -1))
        future24 = tuple(decision + timedelta(hours=offset) for offset in range(1, 25))
        if any(boundary not in market_returns for boundary in (*past24, *past168, *future24)):
            raise FrozenInputError("feature or outcome coverage missing")
        if any(bars[symbol][boundary - timedelta(hours=1)].safe_known_after > decision for symbol in UNIVERSE for boundary in past168):
            raise FrozenInputError("feature bar violates safe-known-after boundary")
        returns24 = {symbol: sum(asset_returns[symbol][boundary] for boundary in past24) for symbol in UNIVERSE}
        returns7d = {symbol: sum(asset_returns[symbol][boundary] for boundary in past168) for symbol in UNIVERSE}
        index_window = tuple(index[decision - timedelta(hours=offset)] for offset in range(720, -1, -1))
        rows.append(DesignRow(
            decision_time=decision,
            rv24_prior=market_rv24([market_returns[boundary] for boundary in past24]),
            dispersion24=dispersion24(returns24),
            breadth7d=breadth7d(returns7d),
            drawdown_depth30d=drawdown_depth30d(index_window),
            rv24_future=market_rv24([market_returns[boundary] for boundary in future24]),
            market_return_future=market_return_24([market_returns[boundary] for boundary in future24]),
        ))
    _validate_design_rows(rows)
    return tuple(rows)


def _validate_design_rows(rows: Sequence[DesignRow]) -> None:
    if len(rows) != OBSERVATION_COUNT:
        raise FrozenInputError("all 580 frozen observations are required")
    if tuple(row.decision_time for row in rows) != canonical_schedule():
        raise FrozenInputError("decision schedule mismatch")
    numeric = ("rv24_prior", "dispersion24", "breadth7d", "drawdown_depth30d", "rv24_future", "market_return_future")
    if any(not all(math.isfinite(getattr(row, field)) for field in numeric) for row in rows):
        raise FrozenInputError("non-finite design value")


def _ols_hac(*, proposition_id: str, x: Sequence[float], y: Sequence[float]) -> tuple[float, float, tuple[float, float], float]:
    if len(x) != OBSERVATION_COUNT or len(y) != OBSERVATION_COUNT:
        raise FrozenInputError("OLS requires the frozen common sample")
    n = len(x)
    sum_x, sum_y = sum(x), sum(y)
    sum_xx = sum(value * value for value in x)
    mean_x, mean_y = sum_x / n, sum_y / n
    sxx = sum((value - mean_x) ** 2 for value in x)
    if sxx <= 0 or not math.isfinite(sxx):
        raise FrozenInputError(f"degenerate feature for {proposition_id}")
    beta = sum((left - mean_x) * (right - mean_y) for left, right in zip(x, y)) / sxx
    alpha = mean_y - beta * mean_x
    residuals = [right - alpha - beta * left for left, right in zip(x, y)]
    a00, a01, a11 = float(n), sum_x, sum_xx
    determinant = a00 * a11 - a01 * a01
    if determinant <= 0:
        raise FrozenInputError("singular OLS design")
    inverse = ((a11 / determinant, -a01 / determinant), (-a01 / determinant, a00 / determinant))
    scores = [(residual, feature * residual) for feature, residual in zip(x, residuals)]
    meat = [[0.0, 0.0], [0.0, 0.0]]
    for left, right in scores:
        meat[0][0] += left * left
        meat[0][1] += left * right
        meat[1][0] += right * left
        meat[1][1] += right * right
    for lag in range(1, HAC_LAG + 1):
        weight = 1.0 - lag / (HAC_LAG + 1)
        for current in range(lag, n):
            now, before = scores[current], scores[current - lag]
            for row in range(2):
                for column in range(2):
                    meat[row][column] += weight * (now[row] * before[column] + before[row] * now[column])
    middle = [[sum(inverse[row][k] * meat[k][column] for k in range(2)) for column in range(2)] for row in range(2)]
    covariance = [[sum(middle[row][k] * inverse[column][k] for k in range(2)) for column in range(2)] for row in range(2)]
    variance = covariance[1][1]
    if variance < -1e-15 or not math.isfinite(variance):
        raise FrozenInputError("invalid HAC variance")
    standard_error = math.sqrt(max(variance, 0.0))
    if standard_error == 0:
        raise FrozenInputError("zero HAC standard error")
    z_score = beta / standard_error
    raw_p = math.erfc(abs(z_score) / math.sqrt(2.0))
    interval = (beta - HAC_CRITICAL_VALUE_95 * standard_error, beta + HAC_CRITICAL_VALUE_95 * standard_error)
    return beta, standard_error, interval, raw_p


def holm_adjust(raw_p_values: Mapping[str, float]) -> dict[str, float]:
    if tuple(sorted(raw_p_values)) != tuple(sorted(PROPOSITION_IDS)) or len(raw_p_values) != len(PROPOSITION_IDS):
        raise FrozenInputError("Holm family must contain exactly the four frozen propositions")
    if any(not math.isfinite(value) or value < 0 or value > 1 for value in raw_p_values.values()):
        raise FrozenInputError("valid p-values required")
    ranked = sorted(raw_p_values.items(), key=lambda item: (item[1], item[0]))
    adjusted: dict[str, float] = {}
    running = 0.0
    family_size = len(ranked)
    for index, (proposition_id, raw_p) in enumerate(ranked):
        running = max(running, min(1.0, (family_size - index) * raw_p))
        adjusted[proposition_id] = running
    return adjusted


def classify(*, beta: float, interval: tuple[float, float], holm_p: float, predicted_sign: str = "POSITIVE") -> str:
    if predicted_sign != "POSITIVE":
        raise FrozenInputError("all frozen Harvest V0 directions are positive")
    low, high = interval
    if beta > 0 and low > 0 and holm_p <= FAMILYWISE_ALPHA:
        return "SUPPORTED_WITHIN_FROZEN_SCOPE"
    if high < 0:
        return "NOT_SUPPORTED"
    return "INCONCLUSIVE"


def analyze_synthetic_fixture(rows: Sequence[DesignRow], *, implementation_identity: str = "synthetic-fixture") -> dict[str, Any]:
    """Run the frozen statistic only on controlled design-row fixtures, never snapshot bars."""
    _validate_design_rows(rows)
    columns = {
        "JH01_RV_PERSISTENCE": ([row.rv24_prior for row in rows], [row.rv24_future for row in rows]),
        "JH02_DISPERSION_TO_RV": ([row.dispersion24 for row in rows], [row.rv24_future for row in rows]),
        "JH03_BREADTH_TO_RETURN": ([row.breadth7d for row in rows], [row.market_return_future for row in rows]),
        "JH04_DRAWDOWN_TO_RETURN": ([row.drawdown_depth30d for row in rows], [row.market_return_future for row in rows]),
    }
    raw: dict[str, tuple[float, float, tuple[float, float], float]] = {identifier: _ols_hac(proposition_id=identifier, x=columns[identifier][0], y=columns[identifier][1]) for identifier in PROPOSITION_IDS}
    adjusted = holm_adjust({identifier: raw[identifier][3] for identifier in PROPOSITION_IDS})
    results = []
    for identifier in PROPOSITION_IDS:
        beta, standard_error, interval, raw_p = raw[identifier]
        results.append({
            "proposition_id": identifier,
            "beta": beta,
            "hac_standard_error": standard_error,
            "hac_confidence_interval_95": list(interval),
            "raw_p_value_two_sided": raw_p,
            "holm_adjusted_p_value": adjusted[identifier],
            "classification": classify(beta=beta, interval=interval, holm_p=adjusted[identifier]),
        })
    result = {
        "experiment_id": EXPERIMENT_ID,
        "preregistration_digest": PREREGISTRATION_DIGEST,
        "execution_mode": "SYNTHETIC_FIXTURE_ONLY",
        "snapshot_id": None,
        "snapshot_digest": None,
        "snapshot_binding": "SYNTHETIC_FIXTURE_NO_REAL_SNAPSHOT",
        "implementation_identity": implementation_identity,
        "observation_count": OBSERVATION_COUNT,
        "primary_hac_lag": HAC_LAG,
        "result_order": list(PROPOSITION_IDS),
        "results": results,
        "authority": AUTHORITY,
        "scientific_result": "NONE_SYNTHETIC_FIXTURE_ONLY",
    }
    result["result_digest"] = result_digest(result)
    return result
