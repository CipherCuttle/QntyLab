"""Shared scientific core for the funding-pressure incremental forecast value.

MECHANICAL CORE EXTRACTION ARTIFACT (phase
``FUNDING_INCREMENTAL_EXECUTOR_CORE_EXTRACTION_AND_SUCCESSOR_IMPLEMENTATION_V1``).

Every function, constant, exception and helper in this module was moved
VERBATIM out of the guarded assembly of
``qntylab.jigsaw_funding_pressure_incremental_forecast_value_executor_v0``
(historical V0 source sha256
``b894d4d9316bed6f8c4f7171b32692aff7b1f0eb32abd686a33fdb38425a7490`` at commit
``f6f12994d65c3dfeaf7839de560e58ad99547c62``).  No formula, rounding rule,
error message, ordering, data structure or Decimal context was changed,
optimized or cleaned up.  The executor module is now a mechanical consumer of
this core; this is the EXACTLY ONE active shared scientific core in the
successor tree (HAR assembly, OLS, forecasting, loss, Clark-West adjusted
MSPE, Bartlett/Newey-West HAC, p-value, classification).

The core is deliberately inert with respect to real evidence: it contains no
data reader, no network client, no evidence loader and no claim transport.
Contract-visible arithmetic is exact (:class:`fractions.Fraction`); the only
inexact steps are the final square root of the HAC variance and the normal
upper-tail probability, both of which run inside an explicit fixed-precision
:class:`decimal.Context`.

The 244-origin scientific evaluation is NOT performed here.  Real evidence
execution requires a separate Git-backed authorization.
"""
from __future__ import annotations

from collections.abc import Sequence
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction

from qntylab import jigsaw_funding_pressure_execution_v2 as v2

# ==========================================================================
# SECTION 0 -- fail-closed exception hierarchy (moved verbatim)
# ==========================================================================


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


# ==========================================================================
# Frozen evaluation-origin count (moved verbatim from the temporal contract;
# the classification rule below depends on it).
# ==========================================================================

REQUIRED_EVALUATION_ORIGINS = 244


# ==========================================================================
# Exact numeric coercion (moved verbatim; fail closed on anything inexact)
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


# ==========================================================================
# (C) HAR features and (D/E) the two frozen designs (moved verbatim)
# ==========================================================================


HAR_LAG_WINDOWS = (1, 7, 30)
HAR_MAX_LAG_DAYS = 30


def har_features(row) -> tuple[Fraction, Fraction, Fraction, Fraction]:
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


def m0_design_row(row) -> tuple[Fraction, ...]:
    """BASELINE_1_HAR_RV_1_7_30 regressors, intercept first."""
    return har_features(row)


def m1_design_row(row) -> tuple[Fraction, ...]:
    """M0 regressors plus EXACTLY ONE continuous funding percentile column."""
    base = m0_design_row(row)
    augmented = base + (_exact(row.funding_percentile, label=f"{row.origin}: funding percentile"),)
    if len(augmented) != len(base) + 1:
        raise ContractViolationError("M1 must add exactly one predictor to M0")
    if augmented[: len(base)] != base:
        raise ContractViolationError("M1 must nest M0 exactly")
    return augmented


def target_value(row) -> Fraction:
    return _exact(row.rv24_target, label=f"{row.origin}: rv24 target")


def _design(rows, builder) -> tuple[tuple[Fraction, ...], ...]:
    return tuple(builder(row) for row in rows)


# ==========================================================================
# (D) exact OLS with intercept (moved verbatim)
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
# (E) forecasting and (F) the identical nonnegative floor (moved verbatim)
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
# (G) loss (moved verbatim)
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
# (H) Clark-West adjusted MSPE with Bartlett/Newey-West HAC (moved verbatim)
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
# (I) deterministic classification (moved verbatim)
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
# Deterministic fixed-precision reporting projection (moved verbatim)
# ==========================================================================


def report_decimal(value: Fraction | Decimal) -> Decimal:
    """Deterministic fixed-precision projection used for reporting/digesting."""
    if isinstance(value, Decimal):
        with localcontext(REPORT_CONTEXT):
            return +value
    if not isinstance(value, Fraction):
        raise ContractViolationError("reporting projection expects a Fraction or Decimal")
    with localcontext(REPORT_CONTEXT):
        return Decimal(value.numerator) / Decimal(value.denominator)
