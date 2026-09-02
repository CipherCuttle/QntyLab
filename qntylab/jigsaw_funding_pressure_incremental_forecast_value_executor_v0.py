"""Preregistered funding-pressure incremental forecast-value executor (V0).

SOURCE-BOUND IMPLEMENTATION FREEZE ARTIFACT.

This module implements the frozen contract of
``JIGSAW_FUNDING_PRESSURE_INCREMENTAL_FORECAST_VALUE_PREREGISTRATION_V0``
(preregistration digest
``d7ec718ab14e73d2aea24749a22caa2921fd81b8a336e2f2eaffb30ae1e992ef``) under
the selected architecture ``A_EXPLORATORY_610_INCREMENTAL_FORECAST_TEST``.

CORE EXTRACTION SUPERSESSION (phase
``FUNDING_INCREMENTAL_EXECUTOR_CORE_EXTRACTION_AND_SUCCESSOR_IMPLEMENTATION_V1``):
the contract-visible mathematical core (HAR assembly, OLS, forecasting, loss,
Clark-West adjusted MSPE, Bartlett/Newey-West HAC, p-value, classification)
was mechanically moved VERBATIM into
``qntylab.jigsaw_funding_pressure_incremental_forecast_value_core_v1`` -- the
exactly one active shared scientific core -- and is re-exported here under
the same names.  This module keeps its full public API, its guarded
entrypoint and its assembly behavior bit-identical to the historical V0
source (sha256
``b894d4d9316bed6f8c4f7171b32692aff7b1f0eb32abd686a33fdb38425a7490`` at
commit ``f6f12994d65c3dfeaf7839de560e58ad99547c62``); only its source bytes
(and therefore its source digest) changed, which is the authorized
supersession.

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
from qntylab.jigsaw_funding_pressure_incremental_forecast_value_core_v1 import (
    ALPHA,
    CLASSIFICATION_BLOCKED,
    CLASSIFICATION_FAIL,
    CLASSIFICATION_PASS,
    ESTIMATION_CONTEXT,
    HAR_LAG_WINDOWS,
    HAR_MAX_LAG_DAYS,
    HAC_AUTOCOVARIANCE_DIVISOR,
    HAC_FIXED_LAG,
    HAC_FINITE_SAMPLE_CORRECTION,
    HAC_KERNEL,
    IncrementalForecastError,
    InputIntegrityError,
    ContractViolationError,
    NumericalContractError,
    OLS_COEFFICIENT_PRECISION,
    OLS_COEFFICIENT_ROUNDING,
    P_VALUE_PRECISION,
    RankDeficientDesignError,
    REPORT_CONTEXT,
    REPORT_PRECISION,
    REQUIRED_EVALUATION_ORIGINS,
    STATISTIC_CONTEXT,
    STATISTIC_PRECISION,
    TemporalContractError,
    TEST_REFERENCE_DISTRIBUTION,
    UnauthorizedExecutionError,
    Z_CRITICAL_ONE_SIDED_5_PERCENT,
    _LN_10,
    _NORMAL_TAIL_MAX_TERMS,
    _NORMAL_TAIL_SATURATION,
    _NORMAL_TAIL_SERIES_THRESHOLD,
    _PI_DIGITS,
    _decimal,
    _design,
    _erf_series,
    _erfc_continued_fraction,
    _exact,
    _one_minus,
    _pi,
    apply_nonnegative_floor,
    bartlett_newey_west_long_run_variance,
    classify,
    clark_west_adjusted_differences,
    clark_west_statistic,
    fit_ordinary_least_squares,
    har_features,
    linear_forecast,
    m0_design_row,
    m1_design_row,
    mean_squared_error,
    quantize_exact,
    relative_mse_improvement,
    report_decimal,
    solve_normal_equations_exact,
    standard_normal_upper_tail,
    target_value,
)

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
MINIMUM_TRAINING_ORIGINS = 365

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


def _assemble_incremental_forecast_evaluation(
    rows: Sequence[ForecastRow], mode: str
) -> IncrementalForecastEvaluation:
    """The frozen evaluation assembly over the shared scientific core.

    Mechanical continuation of the historical V0 entrypoint body; the only
    caller-visible change is that the math now lives in the shared core.
    """
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


def run_incremental_forecast_evaluation(
    rows: Sequence[ForecastRow], *, execution_mode: object
) -> IncrementalForecastEvaluation:
    """The single evaluation entrypoint.

    Refuses any execution mode other than ``SYNTHETIC_VALIDATION``.  There is
    no code path in this module that can obtain real frozen evidence.
    """
    mode = require_authorized_execution_mode(execution_mode)
    return _assemble_incremental_forecast_evaluation(rows, mode)


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
