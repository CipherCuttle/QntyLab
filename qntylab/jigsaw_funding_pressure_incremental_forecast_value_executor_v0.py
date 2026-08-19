"""Preregistered funding-pressure incremental forecast-value executor (V0).

SOURCE-BOUND IMPLEMENTATION FREEZE ARTIFACT.

This module implements the frozen contract of
``JIGSAW_FUNDING_PRESSURE_INCREMENTAL_FORECAST_VALUE_PREREGISTRATION_V0``
(preregistration digest
``d7ec718ab14e73d2aea24749a22caa2921fd81b8a336e2f2eaffb30ae1e992ef``) under
the selected architecture ``A_EXPLORATORY_610_INCREMENTAL_FORECAST_TEST``.

It is deliberately inert with respect to real evidence:

* it contains no data reader, no network client, and no evidence loader;
* it never calls ``foundation.load_verified_frozen_evidence`` and never
  constructs or consumes an authorization or a claim transport;
* the single evaluation entrypoint refuses every execution mode other than
  ``SYNTHETIC_VALIDATION``;
* the low-level funding / RV semantics are *reused* from the canonical
  ``jigsaw_funding_pressure_execution_v2`` primitives, never restated here.

Contract-visible arithmetic is exact.  Feature construction, training-set
selection, OLS estimation, forecasting, the zero floor, MSE and the
Clark-West adjusted difference are all computed in exact rational arithmetic
(:class:`fractions.Fraction`); the only inexact steps are the final square
root of the HAC variance and the normal upper-tail probability, both of which
run inside an explicit fixed-precision :class:`decimal.Context`.

The 244-origin scientific evaluation is NOT performed here.  Real evidence
execution requires a separate Git-backed authorization.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType

from qntylab import jigsaw_funding_pressure_execution_foundation_v0 as foundation
from qntylab import jigsaw_funding_pressure_execution_v2 as v2

# ==========================================================================
# SECTION 0 -- identity, authority boundary, execution-mode guard
# ==========================================================================

PROJECT_ID = "JIGSAW_FUNDING_PRESSURE_INCREMENTAL_FORECAST_VALUE_EXECUTION_IMPLEMENTATION_V0"
GOVERNING_PREREGISTRATION_PROJECT_ID = "JIGSAW_FUNDING_PRESSURE_INCREMENTAL_FORECAST_VALUE_PREREGISTRATION_V0"
GOVERNING_CANDIDATE_ID = "CANDIDATE_FUNDING_PRESSURE_INCREMENTAL_RV_FORECAST_VALUE_V0"
GOVERNING_PREREGISTRATION_DIGEST = "d7ec718ab14e73d2aea24749a22caa2921fd81b8a336e2f2eaffb30ae1e992ef"
SELECTED_ARCHITECTURE = "A_EXPLORATORY_610_INCREMENTAL_FORECAST_TEST"
MODULE_RELATIVE_PATH = "qntylab/jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py"

EXECUTION_MODE_SYNTHETIC_VALIDATION = "SYNTHETIC_VALIDATION"
AUTHORIZED_EXECUTION_MODES = (EXECUTION_MODE_SYNTHETIC_VALIDATION,)

#: Frozen, machine-readable statement of what this implementation freeze did
#: NOT do.  Mirrors the shape of ``foundation.NO_OUTCOME_ATTESTATION``.
NO_REAL_EXECUTION_ATTESTATION = MappingProxyType(
    {
        "REAL_EVIDENCE_EXECUTION_PERFORMED": False,
        "REAL_SCIENTIFIC_EXECUTION_PERFORMED": False,
        "REAL_EVALUATION_OUTCOMES_ACCESSED": False,
        "REAL_FORECASTS_COMPUTED": False,
        "REAL_MSE_COMPUTED": False,
        "REAL_CLARK_WEST_COMPUTED": False,
        "REAL_P_VALUE_COMPUTED": False,
        "MARKET_DATA_ACQUIRED": False,
        "FUNDING_DATA_ACQUIRED": False,
        "NETWORK_ACCESS_PERFORMED": False,
        "SCIENTIFIC_RESULT_RECORDED": False,
        "TRIAL_COMPLETION_RECORDED": False,
        "PREREGISTRATION_MUTATED": False,
        "AUTHORIZATION_CLAIM_CONSUMED": False,
        "JH01_LEDGER_ACCESSED": False,
        "ORDER_FLOW_REOPENED": False,
    }
)

#: A PASS classification licenses exactly this and nothing more.
PASS_CLAIM_BOUNDARY = (
    "EXPLORATORY_INCREMENTAL_PREDICTIVE_INFORMATION_ONLY; "
    "NOT_MATERIALITY; NOT_ECONOMIC_SIGNIFICANCE; NOT_CAUSAL; "
    "NOT_INVERSE_FUNDING_EFFECT; NOT_ACTION_UTILITY; NOT_TRADING_EDGE; "
    "NOT_STATE_OBSERVER_PROMOTION; NOT_ROUTER_AUTHORITY; NOT_QNTY_AUTHORITY; "
    "NOT_INDEPENDENT_CONFIRMATION; NOT_SEALED_EVALUATION; NOT_PROSPECTIVE"
)

DOWNSTREAM_AUTHORITY = "NONE"
CAPITAL_AUTHORITY = "NONE"


class IncrementalForecastError(Exception):
    """Base class for every fail-closed condition in this executor."""


class UnauthorizedExecutionError(IncrementalForecastError):
    """Raised when an execution mode other than synthetic validation is used."""


class TemporalContractError(IncrementalForecastError):
    """Raised when the frozen origin schedule or a PIT boundary is violated."""


class InputIntegrityError(IncrementalForecastError):
    """Raised on missing, extra, malformed or non-finite inputs."""


class ContractViolationError(IncrementalForecastError):
    """Raised when a frozen model/statistical convention would be broken."""


class RankDeficientDesignError(IncrementalForecastError):
    """Raised when a refit design matrix is exactly rank deficient."""


class NumericalContractError(IncrementalForecastError):
    """Raised when a fixed-precision numerical routine cannot fail open."""


def require_authorized_execution_mode(execution_mode: object) -> str:
    """Fail closed unless the caller asks for synthetic validation.

    This is defence in depth, not the primary boundary: the primary boundary
    is that this module owns no reader capable of producing real rows.
    """
    if execution_mode not in AUTHORIZED_EXECUTION_MODES:
        raise UnauthorizedExecutionError(
            "real evidence execution is not authorized in this implementation-freeze phase; "
            f"execution_mode must be one of {AUTHORIZED_EXECUTION_MODES!r}, got {execution_mode!r}"
        )
    return EXECUTION_MODE_SYNTHETIC_VALIDATION


# ==========================================================================
# SECTION 1 -- frozen temporal contract (origin schedule / PIT boundaries)
# ==========================================================================

DAY = timedelta(days=1)
FORWARD_HOURS = v2.FORWARD_HOURS
HISTORY_OBSERVATIONS = v2.HISTORY_OBSERVATIONS
PANEL = v2.PANEL

FIRST_DEVELOPMENT_ORIGIN = datetime(2023, 10, 19, tzinfo=UTC)
LAST_DEVELOPMENT_ORIGIN = datetime(2024, 10, 17, tzinfo=UTC)
EXCLUDED_BOUNDARY_ORIGIN = datetime(2024, 10, 18, tzinfo=UTC)
FIRST_EVALUATION_ORIGIN = datetime(2024, 10, 19, tzinfo=UTC)
LAST_EVALUATION_ORIGIN = datetime(2025, 6, 19, tzinfo=UTC)

REQUIRED_DEVELOPMENT_ORIGINS = 365
REQUIRED_EVALUATION_ORIGINS = 244
MINIMUM_TRAINING_ORIGINS = 365

HAR_LAG_WINDOWS = (1, 7, 30)
HAR_MAX_LAG_DAYS = 30

#: The canonical UTC coercion is reused, never re-implemented (Section 10 of
#: the phase contract: do not duplicate verified timestamp semantics).
_utc = v2._utc


def _stamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _daily_span(first: datetime, last: datetime) -> tuple[datetime, ...]:
    first_utc, last_utc = _utc(first), _utc(last)
    if last_utc < first_utc:
        raise TemporalContractError("schedule end precedes schedule start")
    delta = last_utc - first_utc
    if delta % DAY != timedelta(0):
        raise TemporalContractError("schedule endpoints are not an integral number of days apart")
    count = delta.days + 1
    return tuple(first_utc + timedelta(days=index) for index in range(count))


def target_completion_time(origin: datetime) -> datetime:
    """The instant the RV24 target of ``origin`` is complete."""
    return _utc(origin) + timedelta(hours=FORWARD_HOURS)


def development_origins() -> tuple[datetime, ...]:
    span = _daily_span(FIRST_DEVELOPMENT_ORIGIN, LAST_DEVELOPMENT_ORIGIN)
    if len(span) != REQUIRED_DEVELOPMENT_ORIGINS:
        raise TemporalContractError("frozen development origin count drifted")
    return span


def evaluation_origins() -> tuple[datetime, ...]:
    span = _daily_span(FIRST_EVALUATION_ORIGIN, LAST_EVALUATION_ORIGIN)
    if len(span) != REQUIRED_EVALUATION_ORIGINS:
        raise TemporalContractError("frozen evaluation origin count drifted")
    return span


def forecast_row_origins() -> tuple[datetime, ...]:
    """Every origin that may ever carry a forecast row.

    The boundary origin 2024-10-18 is absent by construction: its target
    completes at 2024-10-19T00:00:00Z, which is not strictly before the first
    evaluation origin, so it can never enter a training set, and it is not an
    evaluation origin either.
    """
    if EXCLUDED_BOUNDARY_ORIGIN != LAST_DEVELOPMENT_ORIGIN + DAY:
        raise TemporalContractError("excluded boundary origin is not the day after development")
    if EXCLUDED_BOUNDARY_ORIGIN != FIRST_EVALUATION_ORIGIN - DAY:
        raise TemporalContractError("excluded boundary origin is not the day before evaluation")
    if target_completion_time(EXCLUDED_BOUNDARY_ORIGIN) != FIRST_EVALUATION_ORIGIN:
        raise TemporalContractError("excluded boundary origin target does not land on the first evaluation origin")
    origins = development_origins() + evaluation_origins()
    if EXCLUDED_BOUNDARY_ORIGIN in origins:
        raise TemporalContractError("excluded boundary origin leaked into the forecast row schedule")
    if any(later <= earlier for earlier, later in zip(origins, origins[1:])):
        raise TemporalContractError("forecast row origins are not strictly increasing")
    return origins


def required_rv24_days() -> tuple[datetime, ...]:
    """Daily grid of RV24 observations the executor requires.

    ``rv24[d]`` is the RV24 realized over ``(d, d + 24h]``.  The grid starts
    30 days before the first development origin so the monthly HAR component
    of that origin is fully warmed up, runs contiguously through the last
    evaluation origin, and deliberately *includes* the excluded boundary day
    because that day is a legitimate lag observation for later origins.
    """
    return _daily_span(FIRST_DEVELOPMENT_ORIGIN - timedelta(days=HAR_MAX_LAG_DAYS), LAST_EVALUATION_ORIGIN)


def required_pressure_days() -> tuple[datetime, ...]:
    """Daily grid of funding-pressure observations the executor requires.

    Starts 365 days before the first development origin so the ECDF of that
    origin has its exact frozen 365-observation history.
    """
    return _daily_span(FIRST_DEVELOPMENT_ORIGIN - timedelta(days=HISTORY_OBSERVATIONS), LAST_EVALUATION_ORIGIN)


# ==========================================================================
# SECTION 2 -- exact numeric coercion (fail closed on anything inexact)
# ==========================================================================


def _exact(value: object, *, label: str) -> Fraction:
    """Coerce a contract-visible magnitude to an exact rational.

    Only :class:`~decimal.Decimal` and :class:`~fractions.Fraction` are
    accepted.  ``float`` is refused on purpose: binary floating point would
    make the frozen contract's arithmetic environment-sensitive.
    """
    if isinstance(value, Fraction):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise InputIntegrityError(f"{label}: non-finite Decimal is refused")
        return Fraction(value)
    raise InputIntegrityError(f"{label}: expected Decimal or Fraction, got {type(value).__name__}")


def _require_decimal(value: object, *, label: str, non_negative: bool) -> Decimal:
    if not isinstance(value, Decimal):
        raise InputIntegrityError(f"{label}: expected Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise InputIntegrityError(f"{label}: non-finite value is refused")
    if non_negative and value < 0:
        raise InputIntegrityError(f"{label}: negative value violates the frozen definition")
    return value


# ==========================================================================
# SECTION 3 -- (A) causal forecast row construction
# ==========================================================================


@dataclass(frozen=True, slots=True)
class ForecastRow:
    """One causal daily forecast row.

    Every field is safe-known at ``origin`` except ``rv24_target``, whose
    completion time is ``target_completion`` = ``origin + 24h``.  Nothing in
    this row is ever used as a feature at or after its own completion time.
    """

    origin: str
    target_completion: str
    funding_percentile: Fraction
    rv24_target: Decimal
    #: RV24 observations completing at ``origin``, ``origin - 1d``, ... i.e.
    #: ``rv24_lags[k]`` is the RV24 realized over ``(origin-(k+1)d, origin-k d]``.
    rv24_lags: tuple[Decimal, ...]


def daily_funding_pressure(
    funding_by_symbol: Mapping[str, Sequence[foundation.VerifiedFundingEvent]], day: datetime
) -> Decimal:
    """Canonical ``median_i(abs(latest_known_settlement_rate_i))`` at ``day``.

    Pure delegation to the verified V2 primitives; no funding, timestamp or
    panel semantics are restated here.
    """
    selected = {
        symbol: v2.select_latest_eligible_funding(funding_by_symbol[symbol], day, symbol=symbol)
        for symbol in PANEL
    }
    return v2.median_abs_funding(selected)


def daily_rv24(
    bars_by_symbol: Mapping[str, Sequence[foundation.VerifiedBarOpenClose]], day: datetime
) -> Decimal:
    """Canonical market-wide RV24 over ``(day, day + 24h]``.

    Pure delegation to the verified V2 primitives; the hourly return, equal
    weight and RV24 semantics are not restated here.
    """
    per_symbol = {symbol: v2.hourly_asset_returns(bars_by_symbol[symbol], day) for symbol in PANEL}
    hourly_rows = tuple(
        {symbol: per_symbol[symbol][hour] for symbol in PANEL} for hour in range(FORWARD_HOURS)
    )
    return v2.rv24(v2.market_returns(hourly_rows))


def build_daily_pressure_grid(
    funding_by_symbol: Mapping[str, Sequence[foundation.VerifiedFundingEvent]],
    days: Sequence[datetime],
) -> dict[str, Decimal]:
    return {_stamp(day): daily_funding_pressure(funding_by_symbol, day) for day in days}


def build_daily_rv24_grid(
    bars_by_symbol: Mapping[str, Sequence[foundation.VerifiedBarOpenClose]],
    days: Sequence[datetime],
) -> dict[str, Decimal]:
    return {_stamp(day): daily_rv24(bars_by_symbol, day) for day in days}


def _require_exact_grid(
    grid: Mapping[str, Decimal], required: Sequence[datetime], *, label: str, non_negative: bool
) -> dict[str, Decimal]:
    if not isinstance(grid, Mapping):
        raise InputIntegrityError(f"{label}: grid must be a mapping")
    expected = tuple(_stamp(day) for day in required)
    expected_set = set(expected)
    actual_set = set(grid)
    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)
    if missing:
        raise InputIntegrityError(f"{label}: missing required observations: {missing[:5]}{'...' if len(missing) > 5 else ''}")
    if extra:
        raise InputIntegrityError(f"{label}: unexpected observations outside the frozen grid: {extra[:5]}{'...' if len(extra) > 5 else ''}")
    return {stamp: _require_decimal(grid[stamp], label=f"{label}[{stamp}]", non_negative=non_negative) for stamp in expected}


def build_causal_forecast_rows(
    *,
    rv24_by_day: Mapping[str, Decimal],
    pressure_by_day: Mapping[str, Decimal],
) -> tuple[ForecastRow, ...]:
    """Build the frozen 609-row causal forecast panel.

    ``rv24_by_day[d]`` is the RV24 realized over ``(d, d + 24h]``.
    ``pressure_by_day[d]`` is the funding pressure known at ``d``.

    Fails closed on any missing row, any row outside the frozen grid, any
    non-Decimal, non-finite or negative magnitude.  Nothing is imputed and no
    gap is bridged.
    """
    rv24 = _require_exact_grid(rv24_by_day, required_rv24_days(), label="rv24_by_day", non_negative=True)
    pressure = _require_exact_grid(pressure_by_day, required_pressure_days(), label="pressure_by_day", non_negative=True)

    rows: list[ForecastRow] = []
    for origin in forecast_row_origins():
        prior_pressures = [
            pressure[_stamp(origin - timedelta(days=offset))]
            for offset in range(HISTORY_OBSERVATIONS, 0, -1)
        ]
        # Reused verbatim: exactly 365 prior observations plus the current one,
        # inclusive <= ECDF, percentile in [0, 1].
        percentile = v2.ecdf_percentile(prior_pressures, pressure[_stamp(origin)])
        if not Fraction(0) <= percentile <= Fraction(1):
            raise ContractViolationError("funding percentile escaped [0, 1]")
        lags = tuple(rv24[_stamp(origin - timedelta(days=offset))] for offset in range(1, HAR_MAX_LAG_DAYS + 1))
        rows.append(
            ForecastRow(
                origin=_stamp(origin),
                target_completion=_stamp(target_completion_time(origin)),
                funding_percentile=percentile,
                rv24_target=rv24[_stamp(origin)],
                rv24_lags=lags,
            )
        )
    return tuple(rows)


def validate_forecast_rows(rows: Sequence[ForecastRow]) -> tuple[ForecastRow, ...]:
    """Fail closed unless ``rows`` is exactly the frozen causal row panel."""
    expected = tuple(_stamp(origin) for origin in forecast_row_origins())
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise InputIntegrityError("forecast rows must be a sequence")
    actual = tuple(row.origin for row in rows)
    if len(actual) != len(set(actual)):
        raise InputIntegrityError("duplicate forecast row origin")
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        if missing or extra:
            raise InputIntegrityError(
                f"forecast row schedule mismatch; missing={missing[:3]} extra={extra[:3]}"
            )
        raise TemporalContractError("forecast rows are not in strict chronological order")
    for row in rows:
        if not isinstance(row, ForecastRow):
            raise InputIntegrityError("forecast row has the wrong type")
        origin = _utc(row.origin)
        if _stamp(target_completion_time(origin)) != row.target_completion:
            raise TemporalContractError(f"{row.origin}: target completion time is not origin + 24h")
        if not isinstance(row.funding_percentile, Fraction):
            raise InputIntegrityError(f"{row.origin}: funding percentile must be an exact Fraction")
        if not Fraction(0) <= row.funding_percentile <= Fraction(1):
            raise InputIntegrityError(f"{row.origin}: funding percentile escaped [0, 1]")
        _require_decimal(row.rv24_target, label=f"{row.origin}: rv24_target", non_negative=True)
        if len(row.rv24_lags) != HAR_MAX_LAG_DAYS:
            raise InputIntegrityError(f"{row.origin}: exactly {HAR_MAX_LAG_DAYS} RV24 lags are required")
        for index, lag in enumerate(row.rv24_lags, start=1):
            _require_decimal(lag, label=f"{row.origin}: rv24_lags[{index}]", non_negative=True)
    return tuple(rows)


# ==========================================================================
# SECTION 4 -- (B) expanding training-set selection
# ==========================================================================


def select_training_rows(rows: Sequence[ForecastRow], origin: datetime) -> tuple[ForecastRow, ...]:
    """Expanding window under ``TARGET_COMPLETION_TIME < FORECAST_ORIGIN``.

    The inequality is STRICT.  A row whose target completes exactly at the
    forecast origin is excluded, because at the origin instant the final
    hourly interval of that target has only just closed and the label is not
    established strictly before the decision.
    """
    forecast_origin = _utc(origin)
    selected: list[ForecastRow] = []
    for row in rows:
        completion = _utc(row.target_completion)
        if completion < forecast_origin:
            selected.append(row)
        elif completion == forecast_origin:
            continue  # the frozen cutoff is strict, never <=
    for row in selected:
        if _utc(row.origin) >= forecast_origin:
            raise TemporalContractError("training row origin is not strictly before the forecast origin")
        if _utc(row.target_completion) >= forecast_origin:
            raise TemporalContractError("training row target is not strictly complete before the forecast origin")
    if len(selected) < MINIMUM_TRAINING_ORIGINS:
        raise TemporalContractError(
            f"{_stamp(forecast_origin)}: {len(selected)} completed training origins is below the frozen minimum {MINIMUM_TRAINING_ORIGINS}"
        )
    return tuple(selected)


# ==========================================================================
# SECTION 5 -- (C) HAR features and (D/E) the two frozen designs
# ==========================================================================


def har_features(row: ForecastRow) -> tuple[Fraction, Fraction, Fraction, Fraction]:
    """``(intercept, daily, weekly, monthly)`` from lags known at the origin."""
    lags = row.rv24_lags
    if len(lags) != HAR_MAX_LAG_DAYS:
        raise InputIntegrityError("HAR features require exactly 30 prior daily RV24 values")
    exact = [_exact(lag, label=f"{row.origin}: rv24 lag") for lag in lags]
    daily_window, weekly_window, monthly_window = HAR_LAG_WINDOWS
    daily = sum(exact[:daily_window], Fraction(0)) / daily_window
    weekly = sum(exact[:weekly_window], Fraction(0)) / weekly_window
    monthly = sum(exact[:monthly_window], Fraction(0)) / monthly_window
    return (Fraction(1), daily, weekly, monthly)


def m0_design_row(row: ForecastRow) -> tuple[Fraction, ...]:
    """BASELINE_1_HAR_RV_1_7_30 regressors, intercept first."""
    return har_features(row)


def m1_design_row(row: ForecastRow) -> tuple[Fraction, ...]:
    """M0 regressors plus EXACTLY ONE continuous funding percentile column."""
    base = m0_design_row(row)
    augmented = base + (_exact(row.funding_percentile, label=f"{row.origin}: funding percentile"),)
    if len(augmented) != len(base) + 1:
        raise ContractViolationError("M1 must add exactly one predictor to M0")
    if augmented[: len(base)] != base:
        raise ContractViolationError("M1 must nest M0 exactly")
    return augmented


def target_value(row: ForecastRow) -> Fraction:
    return _exact(row.rv24_target, label=f"{row.origin}: rv24 target")


def _design(rows: Sequence[ForecastRow], builder) -> tuple[tuple[Fraction, ...], ...]:
    return tuple(builder(row) for row in rows)


# ==========================================================================
# SECTION 6 -- (D) exact OLS with intercept
# ==========================================================================


#: Contract-visible quantization point.  The normal equations are formed and
#: solved in exact rational arithmetic; the resulting coefficient vector is
#: then rounded once, to 50 significant digits with ROUND_HALF_EVEN -- the
#: same convention the canonical V2 funding executor already uses.  This is
#: the ONLY rounding step before the loss and Clark-West statistics, and it
#: exists so that every downstream exact rational keeps a bounded
#: denominator instead of accumulating an unbounded one.
OLS_COEFFICIENT_PRECISION = v2.SQRT_PRECISION
OLS_COEFFICIENT_ROUNDING = "DECIMAL_50_SIGNIFICANT_DIGITS_ROUND_HALF_EVEN"
ESTIMATION_CONTEXT = Context(prec=OLS_COEFFICIENT_PRECISION, rounding=v2.SQRT_ROUNDING)
REPORT_PRECISION = v2.SQRT_PRECISION
REPORT_CONTEXT = Context(prec=REPORT_PRECISION, rounding=v2.SQRT_ROUNDING)


def quantize_exact(value: Fraction, context: Context = ESTIMATION_CONTEXT) -> Fraction:
    """Round an exact rational to the frozen fixed-precision grid."""
    if not isinstance(value, Fraction):
        raise ContractViolationError("quantization operates on exact Fractions")
    with localcontext(context):
        rounded = Decimal(value.numerator) / Decimal(value.denominator)
    if not rounded.is_finite():
        raise NumericalContractError("quantized coefficient is not finite")
    return Fraction(rounded)


def solve_normal_equations_exact(
    design: Sequence[Sequence[Fraction]], outcome: Sequence[Fraction]
) -> tuple[Fraction, ...]:
    """Exact OLS with intercept, no regularization, no pseudo-inverse.

    The normal equations are formed and solved in exact rational arithmetic
    with partial pivoting, so the estimate is bit-identical on every run and
    every platform, and rank deficiency is an exact zero pivot rather than a
    tolerance decision.
    """
    if len(design) != len(outcome):
        raise ContractViolationError("design and outcome lengths differ")
    if not design:
        raise ContractViolationError("OLS requires at least one observation")
    width = len(design[0])
    if width == 0:
        raise ContractViolationError("OLS requires at least one regressor")
    for row in design:
        if len(row) != width:
            raise ContractViolationError("ragged design matrix")
        if not all(isinstance(value, Fraction) for value in row):
            raise ContractViolationError("design entries must be exact Fractions")
    if not all(isinstance(value, Fraction) for value in outcome):
        raise ContractViolationError("outcome entries must be exact Fractions")
    if len(design) < width:
        raise RankDeficientDesignError("fewer observations than regressors")

    gram = [[sum((row[i] * row[j] for row in design), Fraction(0)) for j in range(width)] for i in range(width)]
    moment = [sum((row[i] * value for row, value in zip(design, outcome)), Fraction(0)) for i in range(width)]

    augmented = [list(gram[i]) + [moment[i]] for i in range(width)]
    for column in range(width):
        pivot_row = None
        for candidate in range(column, width):
            if augmented[candidate][column] != 0:
                pivot_row = candidate
                break
        if pivot_row is None:
            raise RankDeficientDesignError(f"design matrix is exactly rank deficient at column {column}")
        augmented[column], augmented[pivot_row] = augmented[pivot_row], augmented[column]
        pivot = augmented[column][column]
        augmented[column] = [value / pivot for value in augmented[column]]
        for other in range(width):
            if other == column:
                continue
            factor = augmented[other][column]
            if factor == 0:
                continue
            augmented[other] = [
                value - factor * pivot_value for value, pivot_value in zip(augmented[other], augmented[column])
            ]
    return tuple(augmented[index][width] for index in range(width))


def fit_ordinary_least_squares(
    design: Sequence[Sequence[Fraction]], outcome: Sequence[Fraction]
) -> tuple[Fraction, ...]:
    """The frozen estimator: exact normal-equation solve, then one rounding."""
    return tuple(quantize_exact(value) for value in solve_normal_equations_exact(design, outcome))


# ==========================================================================
# SECTION 7 -- (E) forecasting and (F) the identical nonnegative floor
# ==========================================================================


def linear_forecast(coefficients: Sequence[Fraction], regressors: Sequence[Fraction]) -> Fraction:
    if len(coefficients) != len(regressors):
        raise ContractViolationError("coefficient and regressor lengths differ")
    return sum((a * b for a, b in zip(coefficients, regressors)), Fraction(0))


def apply_nonnegative_floor(forecast: Fraction) -> Fraction:
    """``forecast = max(0, forecast)``, applied identically to M0 and M1."""
    if not isinstance(forecast, Fraction):
        raise ContractViolationError("the zero floor operates on exact Fractions")
    return forecast if forecast > 0 else Fraction(0)


# ==========================================================================
# SECTION 8 -- (G) loss
# ==========================================================================


def mean_squared_error(errors: Sequence[Fraction]) -> Fraction:
    if not errors:
        raise ContractViolationError("MSE requires at least one evaluation origin")
    return sum((error * error for error in errors), Fraction(0)) / len(errors)


def relative_mse_improvement(mse_m0: Fraction, mse_m1: Fraction) -> Fraction:
    if mse_m0 == 0:
        raise ContractViolationError("relative MSE improvement is undefined when MSE_M0 is zero")
    return (mse_m0 - mse_m1) / mse_m0


# ==========================================================================
# SECTION 9 -- (H) Clark-West adjusted MSPE with Bartlett/Newey-West HAC
# ==========================================================================

HAC_KERNEL = "BARTLETT_NEWEY_WEST"
HAC_FIXED_LAG = 5
HAC_AUTOCOVARIANCE_DIVISOR = "SAMPLE_SIZE_T"
HAC_FINITE_SAMPLE_CORRECTION = "NONE"
TEST_REFERENCE_DISTRIBUTION = "STANDARD_NORMAL_ONE_SIDED_UPPER_TAIL"
ALPHA = Decimal("0.05")
#: One-sided 5% standard-normal critical value, used only as a calibration
#: cross-check for the p-value routine.  The gate itself is ``p <= ALPHA``.
Z_CRITICAL_ONE_SIDED_5_PERCENT = Decimal("1.644853626951472714863")

STATISTIC_PRECISION = 50
STATISTIC_CONTEXT = Context(prec=STATISTIC_PRECISION, rounding=ROUND_HALF_EVEN)
P_VALUE_PRECISION = 40
_NORMAL_TAIL_SERIES_THRESHOLD = Decimal(6)
_NORMAL_TAIL_SATURATION = Decimal(100)
_NORMAL_TAIL_MAX_TERMS = 100000
_LN_10 = Decimal("2.302585092994045684017991454684364207601101488628772976033")

#: pi to 150 fractional digits.  Verified in the test suite against an
#: independently computed Machin-formula expansion.
_PI_DIGITS = (
    "3."
    "14159265358979323846264338327950288419716939937510"
    "58209749445923078164062862089986280348253421170679"
    "82148086513282306647093844609550582231725359408128"
)


def clark_west_adjusted_differences(
    *, targets: Sequence[Fraction], forecasts_m0: Sequence[Fraction], forecasts_m1: Sequence[Fraction]
) -> tuple[Fraction, ...]:
    """``d_t = e0_t^2 - e1_t^2 + (f0_t - f1_t)^2``; positive favours M1."""
    if not (len(targets) == len(forecasts_m0) == len(forecasts_m1)):
        raise ContractViolationError("Clark-West inputs have inconsistent lengths")
    if not targets:
        raise ContractViolationError("Clark-West requires at least one evaluation origin")
    values: list[Fraction] = []
    for y, f0, f1 in zip(targets, forecasts_m0, forecasts_m1):
        e0 = y - f0
        e1 = y - f1
        values.append(e0 * e0 - e1 * e1 + (f0 - f1) * (f0 - f1))
    return tuple(values)


def bartlett_newey_west_long_run_variance(values: Sequence[Fraction], *, lag: int = HAC_FIXED_LAG) -> Fraction:
    """Bartlett / Newey-West long-run variance at a FIXED lag.

    ``gamma_j = (1/T) * sum_{t=j+1}^{T} (d_t - dbar)(d_{t-j} - dbar)`` and
    ``S = gamma_0 + 2 * sum_{j=1}^{L} (1 - j/(L+1)) * gamma_j``.

    The lag is the frozen constant 5 and is never selected from the data; the
    autocovariance divisor is the full sample size T; there is no
    finite-sample or degrees-of-freedom correction.
    """
    if lag != HAC_FIXED_LAG:
        raise ContractViolationError(f"the HAC lag is frozen at {HAC_FIXED_LAG}; lag selection is prohibited")
    count = len(values)
    if count <= lag:
        raise ContractViolationError("HAC requires more observations than the fixed lag")
    mean = sum(values, Fraction(0)) / count
    centered = [value - mean for value in values]

    def autocovariance(offset: int) -> Fraction:
        return sum(
            (centered[index] * centered[index - offset] for index in range(offset, count)), Fraction(0)
        ) / count

    total = autocovariance(0)
    for offset in range(1, lag + 1):
        weight = Fraction(lag + 1 - offset, lag + 1)
        total += 2 * weight * autocovariance(offset)
    return total


def _decimal(value: Fraction, context: Context) -> Decimal:
    with localcontext(context):
        return Decimal(value.numerator) / Decimal(value.denominator)


def clark_west_statistic(differences: Sequence[Fraction]) -> tuple[Fraction, Fraction, Decimal]:
    """Return ``(mean_difference, hac_long_run_variance, z_statistic)``.

    ``z = dbar / sqrt(S / T)``.  Everything before the square root is exact.
    """
    count = len(differences)
    mean = sum(differences, Fraction(0)) / count
    long_run_variance = bartlett_newey_west_long_run_variance(differences)
    if long_run_variance <= 0:
        raise NumericalContractError(
            "Bartlett/Newey-West long-run variance is not positive; the one-sided test is not defined"
        )
    variance_of_mean = long_run_variance / count
    with localcontext(STATISTIC_CONTEXT):
        standard_error = _decimal(variance_of_mean, STATISTIC_CONTEXT).sqrt()
        if not standard_error.is_finite() or standard_error <= 0:
            raise NumericalContractError("HAC standard error is not a positive finite number")
        statistic = _decimal(mean, STATISTIC_CONTEXT) / standard_error
    if not statistic.is_finite():
        raise NumericalContractError("Clark-West statistic is not finite")
    return mean, long_run_variance, statistic


def _pi(context: Context) -> Decimal:
    if context.prec > len(_PI_DIGITS) - 2 - 5:
        raise NumericalContractError("requested precision exceeds the frozen pi expansion")
    with localcontext(context):
        return +Decimal(_PI_DIGITS)


def _erf_series(x: Decimal, context: Context) -> Decimal:
    """Maclaurin series for erf at a precision that absorbs its cancellation."""
    with localcontext(context):
        square = x * x
        term = x
        total = x
        epsilon = Decimal(1).scaleb(-(context.prec - 2))
        index = 1
        while True:
            term = -term * square / index
            contribution = term / (2 * index + 1)
            total += contribution
            if abs(contribution) < epsilon:
                break
            index += 1
            if index > _NORMAL_TAIL_MAX_TERMS:
                raise NumericalContractError("erf series did not converge")
        return total * 2 / _pi(context).sqrt()


def _erfc_continued_fraction(x: Decimal, context: Context) -> Decimal:
    """A&S 7.1.14 continued fraction for erfc, evaluated with modified Lentz."""
    with localcontext(context):
        tiny = Decimal(1).scaleb(-(2 * context.prec))
        epsilon = Decimal(1).scaleb(-(context.prec - 2))
        f = tiny
        c = f
        d = Decimal(0)
        index = 1
        while True:
            a = Decimal(1) if index == 1 else Decimal(index - 1) / 2
            d = x + a * d
            if d == 0:
                d = tiny
            c = x + a / c
            if c == 0:
                c = tiny
            d = 1 / d
            delta = c * d
            f = f * delta
            if abs(delta - 1) < epsilon:
                break
            index += 1
            if index > _NORMAL_TAIL_MAX_TERMS:
                raise NumericalContractError("erfc continued fraction did not converge")
        return (-x * x).exp() / _pi(context).sqrt() * f


def standard_normal_upper_tail(z: Decimal) -> Decimal:
    """``P(Z > z)`` for a standard normal Z, deterministic to 40 digits.

    Computed as ``0.5 * erfc(z / sqrt(2))`` with an explicit fixed-precision
    Decimal context: a Maclaurin series below the crossover and the A&S
    7.1.14 continued fraction above it.  No library default can silently
    change the convention.
    """
    if not isinstance(z, Decimal):
        raise NumericalContractError("the test statistic must be a Decimal")
    if not z.is_finite():
        raise NumericalContractError("the test statistic must be finite")
    if z < 0:
        # ``copy_negate`` is exact and context-free; plain unary minus would
        # round the statistic to whatever ambient precision happened to be set.
        return _one_minus(standard_normal_upper_tail(z.copy_negate()))
    if z > _NORMAL_TAIL_SATURATION:
        # P(Z > 100) < 1e-2100, far below the reported precision; the tail is
        # deterministically reported as zero rather than left to underflow.
        return Decimal(0)
    argument_context = Context(prec=P_VALUE_PRECISION + 40, rounding=ROUND_HALF_EVEN)
    with localcontext(argument_context):
        x = z / Decimal(2).sqrt()
    if x <= _NORMAL_TAIL_SERIES_THRESHOLD:
        # ``1 - erf(x)`` cancels away about ``x^2 / ln 10`` digits and the
        # alternating series itself loses the same amount, so both losses are
        # paid for explicitly rather than absorbed silently.
        guard = int(x * x / _LN_10) + 1
        work = Context(prec=P_VALUE_PRECISION + 2 * guard + 30, rounding=ROUND_HALF_EVEN)
        with localcontext(work):
            tail = (Decimal(1) - _erf_series(x, work)) / 2
    else:
        # The continued fraction evaluates erfc directly, so there is no
        # cancellation to absorb and no precision guard is required.
        work = Context(prec=P_VALUE_PRECISION + 30, rounding=ROUND_HALF_EVEN)
        with localcontext(work):
            tail = _erfc_continued_fraction(x, work) / 2
    with localcontext(Context(prec=P_VALUE_PRECISION, rounding=ROUND_HALF_EVEN)):
        result = +tail
    if not result.is_finite() or result < 0 or result > 1:
        raise NumericalContractError("normal upper tail escaped [0, 1]")
    return result


def _one_minus(value: Decimal) -> Decimal:
    with localcontext(Context(prec=P_VALUE_PRECISION, rounding=ROUND_HALF_EVEN)):
        return Decimal(1) - value


# ==========================================================================
# SECTION 10 -- (I) deterministic classification
# ==========================================================================

CLASSIFICATION_PASS = "FUNDING_PRESSURE_INCREMENTAL_VALUE_ESTABLISHED_EXPLORATORY_ONLY"
CLASSIFICATION_FAIL = "FUNDING_PRESSURE_INCREMENTAL_VALUE_NOT_ESTABLISHED"
CLASSIFICATION_BLOCKED = "BLOCKED"


def classify(
    *,
    evaluation_origin_count: int,
    mse_m0: Fraction,
    mse_m1: Fraction,
    p_value: Decimal,
    alpha: Decimal = ALPHA,
) -> tuple[str, dict[str, bool]]:
    """The frozen PASS / FAIL / BLOCKED rule.

    This encodes the classification only.  It is never applied to real frozen
    evaluation outcomes in this implementation-freeze phase.
    """
    if alpha != ALPHA:
        raise ContractViolationError("alpha is frozen at 0.05 one-sided")
    gates = {
        "valid_evaluation_origin_count": evaluation_origin_count == REQUIRED_EVALUATION_ORIGINS,
        "direction_mse_m1_below_mse_m0": mse_m1 < mse_m0,
        "clark_west_one_sided_p_at_or_below_alpha": p_value <= alpha,
    }
    if not gates["valid_evaluation_origin_count"]:
        return CLASSIFICATION_BLOCKED, gates
    if all(gates.values()):
        return CLASSIFICATION_PASS, gates
    return CLASSIFICATION_FAIL, gates


# ==========================================================================
# SECTION 11 -- evaluation assembly and deterministic serialization
# ==========================================================================


@dataclass(frozen=True, slots=True)
class OriginForecast:
    origin: str
    training_origin_count: int
    target: Fraction
    forecast_m0: Fraction
    forecast_m1: Fraction
    error_m0: Fraction
    error_m1: Fraction
    adjusted_difference: Fraction


@dataclass(frozen=True, slots=True)
class IncrementalForecastEvaluation:
    project_id: str
    governing_preregistration_project_id: str
    governing_candidate_id: str
    governing_preregistration_digest: str
    selected_architecture: str
    execution_mode: str
    evaluation_origin_count: int
    first_evaluation_origin: str
    last_evaluation_origin: str
    excluded_boundary_origin: str
    origin_forecasts: tuple[OriginForecast, ...]
    mse_m0: Fraction
    mse_m1: Fraction
    mse_baseline_0_naive: Fraction
    relative_mse_improvement: Fraction
    clark_west_mean_difference: Fraction
    clark_west_long_run_variance: Fraction
    clark_west_statistic: Decimal
    clark_west_one_sided_p_value: Decimal
    gates: Mapping[str, bool]
    classification: str
    claim_boundary: str
    result_digest: str


def report_decimal(value: Fraction | Decimal) -> Decimal:
    """Deterministic fixed-precision projection used for reporting/digesting."""
    if isinstance(value, Decimal):
        with localcontext(REPORT_CONTEXT):
            return +value
    if not isinstance(value, Fraction):
        raise ContractViolationError("reporting projection expects a Fraction or Decimal")
    with localcontext(REPORT_CONTEXT):
        return Decimal(value.numerator) / Decimal(value.denominator)


def _serializable(value: object) -> object:
    if isinstance(value, Fraction):
        return str(report_decimal(value))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise NumericalContractError("result contains a non-finite Decimal")
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _serializable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_serializable(item) for item in value]
    if isinstance(value, OriginForecast):
        return {
            "origin": value.origin,
            "training_origin_count": value.training_origin_count,
            "target": _serializable(value.target),
            "forecast_m0": _serializable(value.forecast_m0),
            "forecast_m1": _serializable(value.forecast_m1),
            "error_m0": _serializable(value.error_m0),
            "error_m1": _serializable(value.error_m1),
            "adjusted_difference": _serializable(value.adjusted_difference),
        }
    return value


def _result_digest(payload: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(
        foundation.canonical_json(_serializable(payload)).encode("utf-8")
    ).hexdigest()


def run_incremental_forecast_evaluation(
    rows: Sequence[ForecastRow], *, execution_mode: object
) -> IncrementalForecastEvaluation:
    """The single evaluation entrypoint.

    Refuses any execution mode other than ``SYNTHETIC_VALIDATION``.  There is
    no code path in this module that can obtain real frozen evidence.
    """
    mode = require_authorized_execution_mode(execution_mode)
    validated = validate_forecast_rows(rows)
    by_origin = {row.origin: row for row in validated}

    # Each row's regressors and target depend only on that row, so they are
    # built exactly once.  This is a memoization of the pure builders above,
    # never an alternative feature path.
    regressors_m0 = {row.origin: m0_design_row(row) for row in validated}
    regressors_m1 = {row.origin: m1_design_row(row) for row in validated}
    targets_by_origin = {row.origin: target_value(row) for row in validated}

    forecasts: list[OriginForecast] = []
    for origin in evaluation_origins():
        stamp = _stamp(origin)
        row = by_origin[stamp]
        training = select_training_rows(validated, origin)
        training_targets = [targets_by_origin[item.origin] for item in training]

        design_m0 = tuple(regressors_m0[item.origin] for item in training)
        design_m1 = tuple(regressors_m1[item.origin] for item in training)
        if len(design_m1[0]) != len(design_m0[0]) + 1:
            raise ContractViolationError("M1 must contain exactly one predictor more than M0")

        beta_m0 = fit_ordinary_least_squares(design_m0, training_targets)
        beta_m1 = fit_ordinary_least_squares(design_m1, training_targets)

        forecast_m0 = apply_nonnegative_floor(linear_forecast(beta_m0, regressors_m0[stamp]))
        forecast_m1 = apply_nonnegative_floor(linear_forecast(beta_m1, regressors_m1[stamp]))

        target = target_value(row)
        forecasts.append(
            OriginForecast(
                origin=stamp,
                training_origin_count=len(training),
                target=target,
                forecast_m0=forecast_m0,
                forecast_m1=forecast_m1,
                error_m0=target - forecast_m0,
                error_m1=target - forecast_m1,
                adjusted_difference=Fraction(0),
            )
        )

    if len(forecasts) != REQUIRED_EVALUATION_ORIGINS:
        raise TemporalContractError(
            f"exactly {REQUIRED_EVALUATION_ORIGINS} evaluation origins are required, produced {len(forecasts)}"
        )

    targets = [item.target for item in forecasts]
    f0 = [item.forecast_m0 for item in forecasts]
    f1 = [item.forecast_m1 for item in forecasts]
    differences = clark_west_adjusted_differences(targets=targets, forecasts_m0=f0, forecasts_m1=f1)
    forecasts = [
        OriginForecast(
            origin=item.origin,
            training_origin_count=item.training_origin_count,
            target=item.target,
            forecast_m0=item.forecast_m0,
            forecast_m1=item.forecast_m1,
            error_m0=item.error_m0,
            error_m1=item.error_m1,
            adjusted_difference=difference,
        )
        for item, difference in zip(forecasts, differences)
    ]

    mse_m0 = mean_squared_error([item.error_m0 for item in forecasts])
    mse_m1 = mean_squared_error([item.error_m1 for item in forecasts])
    # BASELINE_0 is descriptive context only and has no inferential or rescue
    # authority: it never enters a gate or the classification.
    naive_errors = [
        targets_by_origin[item.origin]
        - apply_nonnegative_floor(_exact(by_origin[item.origin].rv24_lags[0], label="baseline_0"))
        for item in forecasts
    ]
    mse_baseline_0 = mean_squared_error(naive_errors)

    mean_difference, long_run_variance, statistic = clark_west_statistic(differences)
    p_value = standard_normal_upper_tail(statistic)
    classification, gates = classify(
        evaluation_origin_count=len(forecasts), mse_m0=mse_m0, mse_m1=mse_m1, p_value=p_value
    )

    payload: dict[str, object] = {
        "project_id": PROJECT_ID,
        "governing_preregistration_project_id": GOVERNING_PREREGISTRATION_PROJECT_ID,
        "governing_candidate_id": GOVERNING_CANDIDATE_ID,
        "governing_preregistration_digest": GOVERNING_PREREGISTRATION_DIGEST,
        "selected_architecture": SELECTED_ARCHITECTURE,
        "execution_mode": mode,
        "evaluation_origin_count": len(forecasts),
        "first_evaluation_origin": _stamp(FIRST_EVALUATION_ORIGIN),
        "last_evaluation_origin": _stamp(LAST_EVALUATION_ORIGIN),
        "excluded_boundary_origin": _stamp(EXCLUDED_BOUNDARY_ORIGIN),
        "hac_kernel": HAC_KERNEL,
        "hac_fixed_lag": HAC_FIXED_LAG,
        "hac_autocovariance_divisor": HAC_AUTOCOVARIANCE_DIVISOR,
        "hac_finite_sample_correction": HAC_FINITE_SAMPLE_CORRECTION,
        "test_reference_distribution": TEST_REFERENCE_DISTRIBUTION,
        "alpha": ALPHA,
        "origin_forecasts": tuple(forecasts),
        "mse_m0": mse_m0,
        "mse_m1": mse_m1,
        "mse_baseline_0_naive": mse_baseline_0,
        "relative_mse_improvement": relative_mse_improvement(mse_m0, mse_m1),
        "clark_west_mean_difference": mean_difference,
        "clark_west_long_run_variance": long_run_variance,
        "clark_west_statistic": statistic,
        "clark_west_one_sided_p_value": p_value,
        "gates": dict(sorted(gates.items())),
        "classification": classification,
        "claim_boundary": PASS_CLAIM_BOUNDARY,
        "no_real_execution_attestation": dict(sorted(NO_REAL_EXECUTION_ATTESTATION.items())),
        "downstream_authority": DOWNSTREAM_AUTHORITY,
        "capital_authority": CAPITAL_AUTHORITY,
    }
    return IncrementalForecastEvaluation(
        project_id=PROJECT_ID,
        governing_preregistration_project_id=GOVERNING_PREREGISTRATION_PROJECT_ID,
        governing_candidate_id=GOVERNING_CANDIDATE_ID,
        governing_preregistration_digest=GOVERNING_PREREGISTRATION_DIGEST,
        selected_architecture=SELECTED_ARCHITECTURE,
        execution_mode=mode,
        evaluation_origin_count=len(forecasts),
        first_evaluation_origin=_stamp(FIRST_EVALUATION_ORIGIN),
        last_evaluation_origin=_stamp(LAST_EVALUATION_ORIGIN),
        excluded_boundary_origin=_stamp(EXCLUDED_BOUNDARY_ORIGIN),
        origin_forecasts=tuple(forecasts),
        mse_m0=mse_m0,
        mse_m1=mse_m1,
        mse_baseline_0_naive=mse_baseline_0,
        relative_mse_improvement=relative_mse_improvement(mse_m0, mse_m1),
        clark_west_mean_difference=mean_difference,
        clark_west_long_run_variance=long_run_variance,
        clark_west_statistic=statistic,
        clark_west_one_sided_p_value=p_value,
        gates=MappingProxyType(dict(sorted(gates.items()))),
        classification=classification,
        claim_boundary=PASS_CLAIM_BOUNDARY,
        result_digest=_result_digest(payload),
    )


# ==========================================================================
# SECTION 12 -- implementation identity
# ==========================================================================


def implementation_source_digest(root: Path | None = None) -> str:
    base = (root or Path(__file__).resolve().parents[1]).resolve()
    module = foundation.resolve_within_repository(MODULE_RELATIVE_PATH, base)
    return hashlib.sha256(module.read_bytes()).hexdigest()


def implementation_identity(root: Path | None = None) -> dict[str, object]:
    return {
        "project_id": PROJECT_ID,
        "governing_preregistration_project_id": GOVERNING_PREREGISTRATION_PROJECT_ID,
        "governing_candidate_id": GOVERNING_CANDIDATE_ID,
        "governing_preregistration_digest": GOVERNING_PREREGISTRATION_DIGEST,
        "selected_architecture": SELECTED_ARCHITECTURE,
        "implementation_source_path": MODULE_RELATIVE_PATH,
        "implementation_source_sha256": implementation_source_digest(root),
        "execution_modes": list(AUTHORIZED_EXECUTION_MODES),
        "downstream_authority": DOWNSTREAM_AUTHORITY,
        "capital_authority": CAPITAL_AUTHORITY,
        "no_real_execution_attestation": dict(sorted(NO_REAL_EXECUTION_ATTESTATION.items())),
    }
