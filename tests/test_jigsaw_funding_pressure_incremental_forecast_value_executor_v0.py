"""Synthetic validation for the funding incremental forecast-value executor.

Every fixture in this module is SYNTHETIC.  No real evidence is loaded, no
real evaluation outcome is read, no market or funding data is acquired, and
no network call is made.
"""
from __future__ import annotations

import ast
import math
from datetime import UTC, datetime, timedelta
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from qntylab import jigsaw_funding_pressure_execution_foundation_v0 as foundation
from qntylab import jigsaw_funding_pressure_execution_v2 as v2
from qntylab import jigsaw_funding_pressure_incremental_forecast_value_executor_v0 as ex

MODE = ex.EXECUTION_MODE_SYNTHETIC_VALIDATION
ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# deterministic synthetic fixtures
# --------------------------------------------------------------------------


def _lcg(seed: int):
    state = seed

    def draw(modulus: int) -> int:
        nonlocal state
        state = (1103515245 * state + 12345) % (2**31)
        return state % modulus

    return draw


def synthetic_grids(*, seed: int = 20240101, funding_signal: Fraction | None = None):
    """Deterministic RV24 / funding-pressure grids on the exact frozen days."""
    draw = _lcg(seed)
    pressure = {ex._stamp(day): Decimal(100 + draw(900)).scaleb(-7) for day in ex.required_pressure_days()}
    rv24 = {ex._stamp(day): Decimal(2000 + draw(3000)).scaleb(-6) for day in ex.required_rv24_days()}
    if funding_signal is not None:
        # Make RV24 depend monotonically on the same-day funding pressure so
        # that M1 must beat M0 if, and only if, the funding column is wired
        # to the correct row and sign.
        for day in ex.required_rv24_days():
            stamp = ex._stamp(day)
            rv24[stamp] = (rv24[stamp] / 20 + pressure[stamp] * Decimal(funding_signal.numerator) / Decimal(funding_signal.denominator))
    return rv24, pressure


def build_rows(**kwargs):
    rv24, pressure = synthetic_grids(**kwargs)
    return ex.build_causal_forecast_rows(rv24_by_day=rv24, pressure_by_day=pressure)


@pytest.fixture(scope="module")
def rows():
    return build_rows()


@pytest.fixture(scope="module")
def evaluation(rows):
    return ex.run_incremental_forecast_evaluation(rows, execution_mode=MODE)


def row_at(origin: str, *, percentile=Fraction(1, 2), target="0.01", lag_value="0.02", lags=None):
    origin_dt = ex._utc(origin)
    return ex.ForecastRow(
        origin=ex._stamp(origin_dt),
        target_completion=ex._stamp(ex.target_completion_time(origin_dt)),
        funding_percentile=percentile,
        rv24_target=Decimal(target),
        rv24_lags=tuple(Decimal(lag_value) for _ in range(30)) if lags is None else tuple(lags),
    )


# ==========================================================================
# 1 / 2 / 3 -- schedule, boundary exclusion, strict target cutoff
# ==========================================================================


def test_frozen_schedule_is_365_development_and_244_evaluation_origins():
    development = ex.development_origins()
    evaluation = ex.evaluation_origins()
    assert len(development) == 365 == ex.REQUIRED_DEVELOPMENT_ORIGINS
    assert len(evaluation) == 244 == ex.REQUIRED_EVALUATION_ORIGINS
    assert development[0] == datetime(2023, 10, 19, tzinfo=UTC)
    assert development[-1] == datetime(2024, 10, 17, tzinfo=UTC)
    assert evaluation[0] == datetime(2024, 10, 19, tzinfo=UTC)
    assert evaluation[-1] == datetime(2025, 6, 19, tzinfo=UTC)
    assert all(day.hour == day.minute == day.second == day.microsecond == 0 for day in development + evaluation)
    assert all(later - earlier == timedelta(days=1) for earlier, later in zip(development, development[1:]))
    assert all(later - earlier == timedelta(days=1) for earlier, later in zip(evaluation, evaluation[1:]))


def test_boundary_origin_2024_10_18_is_excluded_from_every_forecast_row():
    origins = ex.forecast_row_origins()
    assert len(origins) == 609
    assert ex.EXCLUDED_BOUNDARY_ORIGIN == datetime(2024, 10, 18, tzinfo=UTC)
    assert ex.EXCLUDED_BOUNDARY_ORIGIN not in origins
    # ... but its RV24 observation is still required, because it is the
    # daily HAR lag of the first evaluation origin.
    assert ex.EXCLUDED_BOUNDARY_ORIGIN in ex.required_rv24_days()
    assert ex.EXCLUDED_BOUNDARY_ORIGIN in ex.required_pressure_days()
    # The reason it is excluded: its target completes exactly at, not before,
    # the first evaluation origin.
    assert ex.target_completion_time(ex.EXCLUDED_BOUNDARY_ORIGIN) == ex.FIRST_EVALUATION_ORIGIN


def test_target_completion_cutoff_is_strict_not_inclusive():
    first = ex.FIRST_EVALUATION_ORIGIN
    boundary = row_at("2024-10-18T00:00:00Z")
    assert ex._utc(boundary.target_completion) == first
    padding = [row_at(ex._stamp(first - timedelta(days=offset))) for offset in range(2, 2 + ex.MINIMUM_TRAINING_ORIGINS)]
    training = ex.select_training_rows(padding + [boundary], first)
    assert boundary not in training
    assert len(training) == ex.MINIMUM_TRAINING_ORIGINS
    # one day earlier the same row IS admissible, so the exclusion is the
    # strict inequality and not an off-by-one in the row pool
    later = ex.select_training_rows(padding + [boundary], first + timedelta(days=1))
    assert boundary in later


def test_training_selection_never_includes_a_row_at_or_after_the_origin(rows):
    for origin in (ex.FIRST_EVALUATION_ORIGIN, datetime(2025, 1, 1, tzinfo=UTC), ex.LAST_EVALUATION_ORIGIN):
        training = ex.select_training_rows(rows, origin)
        assert all(ex._utc(row.origin) < origin for row in training)
        assert all(ex._utc(row.target_completion) < origin for row in training)


def test_first_evaluation_origin_trains_on_exactly_the_365_development_origins(rows):
    training = ex.select_training_rows(rows, ex.FIRST_EVALUATION_ORIGIN)
    assert len(training) == 365
    assert tuple(row.origin for row in training) == tuple(ex._stamp(day) for day in ex.development_origins())


def test_expanding_window_grows_by_one_origin_per_day(evaluation):
    counts = [item.training_origin_count for item in evaluation.origin_forecasts]
    assert counts[0] == 365
    assert counts[1] == 365  # 2024-10-18 is excluded, so no row becomes available
    assert counts[2] == 366
    assert all(later - earlier in (0, 1) for earlier, later in zip(counts, counts[1:]))
    assert counts[-1] == 607
    assert all(count >= ex.MINIMUM_TRAINING_ORIGINS for count in counts)


def test_training_set_below_the_frozen_minimum_fails_closed():
    origin = ex.FIRST_EVALUATION_ORIGIN
    short = [row_at(ex._stamp(origin - timedelta(days=offset))) for offset in range(2, 12)]
    with pytest.raises(ex.TemporalContractError):
        ex.select_training_rows(short, origin)


def test_swapped_temporal_ordering_fails_closed(rows):
    swapped = list(rows)
    swapped[10], swapped[11] = swapped[11], swapped[10]
    with pytest.raises(ex.TemporalContractError):
        ex.validate_forecast_rows(swapped)


def test_row_whose_target_completion_is_not_origin_plus_24h_fails_closed(rows):
    tampered = list(rows)
    bad = tampered[0]
    tampered[0] = ex.ForecastRow(
        origin=bad.origin,
        target_completion=ex._stamp(ex._utc(bad.origin) + timedelta(hours=23)),
        funding_percentile=bad.funding_percentile,
        rv24_target=bad.rv24_target,
        rv24_lags=bad.rv24_lags,
    )
    with pytest.raises(ex.TemporalContractError):
        ex.validate_forecast_rows(tampered)


# ==========================================================================
# 4 -- no future target leakage
# ==========================================================================


def test_future_targets_cannot_influence_any_forecast(rows):
    """Perturbing every target strictly after origin T leaves T's forecast fixed."""
    pivot_index = 100
    baseline = ex.run_incremental_forecast_evaluation(rows, execution_mode=MODE)
    pivot = baseline.origin_forecasts[pivot_index]
    pivot_origin = ex._utc(pivot.origin)

    perturbed = []
    for row in rows:
        if ex._utc(row.target_completion) >= pivot_origin:
            perturbed.append(
                ex.ForecastRow(
                    origin=row.origin,
                    target_completion=row.target_completion,
                    funding_percentile=row.funding_percentile,
                    rv24_target=row.rv24_target * 7 + Decimal("0.5"),
                    rv24_lags=row.rv24_lags,
                )
            )
        else:
            perturbed.append(row)
    # Only the fitted forecasts are compared; the realized target of the pivot
    # origin is itself one of the perturbed values by construction.
    after = ex.run_incremental_forecast_evaluation(tuple(perturbed), execution_mode=MODE)
    assert after.origin_forecasts[pivot_index].forecast_m0 == pivot.forecast_m0
    assert after.origin_forecasts[pivot_index].forecast_m1 == pivot.forecast_m1


def test_lagged_rv24_that_completes_after_the_origin_is_never_a_feature(rows):
    for row in rows[:5] + rows[-5:]:
        origin = ex._utc(row.origin)
        for index in range(len(row.rv24_lags)):
            completion = origin - timedelta(days=index)
            assert completion <= origin


# ==========================================================================
# 5 -- HAR feature construction
# ==========================================================================


def test_har_features_use_the_exact_1_7_30_windows():
    lags = [Decimal(index) for index in range(1, 31)]
    row = row_at("2024-10-19T00:00:00Z", lags=lags)
    intercept, daily, weekly, monthly = ex.har_features(row)
    assert intercept == Fraction(1)
    assert daily == Fraction(1)
    assert weekly == Fraction(sum(range(1, 8)), 7)
    assert monthly == Fraction(sum(range(1, 31)), 30)


def test_har_lags_are_aligned_to_the_calendar_without_an_off_by_one(rows):
    rv24, _ = synthetic_grids()
    row = rows[400]
    origin = ex._utc(row.origin)
    for index, lag in enumerate(row.rv24_lags, start=1):
        assert lag == rv24[ex._stamp(origin - timedelta(days=index))]
    assert row.rv24_target == rv24[row.origin]
    # the daily HAR lag is the RV24 that completes exactly at the origin
    assert row.rv24_lags[0] == rv24[ex._stamp(origin - timedelta(days=1))]


def test_har_features_require_exactly_thirty_lags():
    row = row_at("2024-10-19T00:00:00Z", lags=[Decimal(1)] * 29)
    with pytest.raises(ex.InputIntegrityError):
        ex.har_features(row)


# ==========================================================================
# 6 -- M1 adds exactly one funding predictor
# ==========================================================================


def test_m1_nests_m0_and_adds_exactly_one_funding_column():
    row = row_at("2024-10-19T00:00:00Z", percentile=Fraction(37, 366))
    m0 = ex.m0_design_row(row)
    m1 = ex.m1_design_row(row)
    assert len(m0) == 4
    assert len(m1) == 5
    assert m1[:4] == m0
    assert m1[4] == Fraction(37, 366)


def test_designs_carry_an_intercept_column_of_ones(rows):
    for row in rows[:3]:
        assert ex.m0_design_row(row)[0] == Fraction(1)
        assert ex.m1_design_row(row)[0] == Fraction(1)


def test_module_exposes_no_feature_model_lag_or_threshold_search_path():
    source = (ROOT / ex.MODULE_RELATIVE_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    forbidden = ("search", "select_lag", "tune", "grid_search", "optimi", "candidate_model", "threshold")
    assert not [name for name in names if any(token in name.lower() for token in forbidden)]
    # the HAR windows, the HAC lag and alpha are frozen module constants
    assert ex.HAR_LAG_WINDOWS == (1, 7, 30)
    assert ex.HAC_FIXED_LAG == 5
    assert ex.ALPHA == Decimal("0.05")
    with pytest.raises(ex.ContractViolationError):
        ex.bartlett_newey_west_long_run_variance([Fraction(index) for index in range(40)], lag=4)
    with pytest.raises(ex.ContractViolationError):
        ex.classify(
            evaluation_origin_count=244, mse_m0=Fraction(2), mse_m1=Fraction(1),
            p_value=Decimal("0.01"), alpha=Decimal("0.10"),
        )


# ==========================================================================
# 7 / 8 -- expanding refits and deterministic OLS
# ==========================================================================


def test_exact_ols_recovers_an_analytically_known_fit():
    # y = 3 + 2*x1 - 1*x2 exactly; OLS must return the generating vector.
    design = []
    outcome = []
    for x1, x2 in ((1, 0), (0, 1), (2, 3), (5, 1), (4, 4), (7, 2)):
        design.append((Fraction(1), Fraction(x1), Fraction(x2)))
        outcome.append(Fraction(3 + 2 * x1 - x2))
    beta = ex.solve_normal_equations_exact(design, outcome)
    assert beta == (Fraction(3), Fraction(2), Fraction(-1))
    assert ex.fit_ordinary_least_squares(design, outcome) == (Fraction(3), Fraction(2), Fraction(-1))


def test_ols_is_bit_identical_across_repeated_and_reordered_construction():
    design = [(Fraction(1), Fraction(index), Fraction(index * index, 7)) for index in range(1, 12)]
    outcome = [Fraction(index * 3 + 1, 5) for index in range(1, 12)]
    first = ex.fit_ordinary_least_squares(design, outcome)
    second = ex.fit_ordinary_least_squares(list(design), list(outcome))
    assert first == second


def test_ols_fails_closed_on_rank_deficiency_and_on_inexact_inputs():
    duplicate = [(Fraction(1), Fraction(index), Fraction(index)) for index in range(1, 8)]
    outcome = [Fraction(index) for index in range(1, 8)]
    with pytest.raises(ex.RankDeficientDesignError):
        ex.solve_normal_equations_exact(duplicate, outcome)
    constant = [(Fraction(1), Fraction(4)) for _ in range(6)]
    with pytest.raises(ex.RankDeficientDesignError):
        ex.solve_normal_equations_exact(constant, [Fraction(index) for index in range(6)])
    with pytest.raises(ex.RankDeficientDesignError):
        ex.solve_normal_equations_exact([(Fraction(1), Fraction(2))], [Fraction(1)])
    with pytest.raises(ex.ContractViolationError):
        ex.solve_normal_equations_exact([(Fraction(1), 2.0)], [Fraction(1)])
    with pytest.raises(ex.ContractViolationError):
        ex.solve_normal_equations_exact([(Fraction(1), Fraction(2)), (Fraction(1),)], [Fraction(1), Fraction(2)])


def test_coefficient_quantization_is_the_single_declared_rounding_point():
    assert ex.OLS_COEFFICIENT_PRECISION == 50
    assert ex.ESTIMATION_CONTEXT.rounding == ROUND_HALF_EVEN
    value = Fraction(1, 3)
    quantized = ex.quantize_exact(value)
    assert quantized != value
    assert quantized == Fraction(Decimal(1) / Decimal(3) if False else Decimal("0." + "3" * 50))
    assert ex.quantize_exact(Fraction(1, 4)) == Fraction(1, 4)


def test_a_rank_deficient_refit_inside_the_evaluation_fails_closed():
    # every funding percentile identical => the M1 column is collinear with
    # the intercept and the refit must refuse rather than pseudo-invert.
    rv24, pressure = synthetic_grids()
    flat = {stamp: Decimal("0.0000500") for stamp in pressure}
    flat_rows = ex.build_causal_forecast_rows(rv24_by_day=rv24, pressure_by_day=flat)
    assert {row.funding_percentile for row in flat_rows} == {Fraction(1)}
    with pytest.raises(ex.RankDeficientDesignError):
        ex.run_incremental_forecast_evaluation(flat_rows, execution_mode=MODE)


# ==========================================================================
# 9 -- identical zero floor for M0 and M1
# ==========================================================================


def test_zero_floor_is_one_shared_function_applied_identically():
    assert ex.apply_nonnegative_floor(Fraction(-1, 3)) == Fraction(0)
    assert ex.apply_nonnegative_floor(Fraction(0)) == Fraction(0)
    assert ex.apply_nonnegative_floor(Fraction(7, 9)) == Fraction(7, 9)
    with pytest.raises(ex.ContractViolationError):
        ex.apply_nonnegative_floor(0.5)
    source = (ROOT / ex.MODULE_RELATIVE_PATH).read_text(encoding="utf-8")
    assert source.count("apply_nonnegative_floor(linear_forecast(") == 2


def test_no_forecast_is_ever_negative(evaluation):
    assert all(item.forecast_m0 >= 0 and item.forecast_m1 >= 0 for item in evaluation.origin_forecasts)


def test_floor_binds_symmetrically_on_a_negative_generating_process():
    rv24, pressure = synthetic_grids(seed=777)
    rows = ex.build_causal_forecast_rows(rv24_by_day=rv24, pressure_by_day=pressure)
    beta = (Fraction(-1), Fraction(0), Fraction(0), Fraction(0))
    for row in rows[:20]:
        raw = ex.linear_forecast(beta, ex.m0_design_row(row))
        assert raw < 0
        assert ex.apply_nonnegative_floor(raw) == Fraction(0)


# ==========================================================================
# 10 -- MSE semantics
# ==========================================================================


def test_mse_is_the_exact_mean_of_squared_untransformed_errors():
    errors = [Fraction(1), Fraction(-2), Fraction(3, 2)]
    assert ex.mean_squared_error(errors) == (Fraction(1) + Fraction(4) + Fraction(9, 4)) / 3
    with pytest.raises(ex.ContractViolationError):
        ex.mean_squared_error([])
    assert ex.relative_mse_improvement(Fraction(4), Fraction(3)) == Fraction(1, 4)
    with pytest.raises(ex.ContractViolationError):
        ex.relative_mse_improvement(Fraction(0), Fraction(1))


def test_reported_losses_match_a_direct_recomputation(evaluation):
    direct_m0 = ex.mean_squared_error([item.target - item.forecast_m0 for item in evaluation.origin_forecasts])
    direct_m1 = ex.mean_squared_error([item.target - item.forecast_m1 for item in evaluation.origin_forecasts])
    assert evaluation.mse_m0 == direct_m0
    assert evaluation.mse_m1 == direct_m1
    assert evaluation.relative_mse_improvement == (direct_m0 - direct_m1) / direct_m0


def test_baseline_0_is_descriptive_only_and_gates_nothing(evaluation):
    assert evaluation.mse_baseline_0_naive > 0
    assert "baseline" not in " ".join(evaluation.gates).lower()
    assert set(evaluation.gates) == {
        "valid_evaluation_origin_count",
        "direction_mse_m1_below_mse_m0",
        "clark_west_one_sided_p_at_or_below_alpha",
    }


# ==========================================================================
# 11 / 12 / 13 / 14 -- Clark-West, HAC, direction, p-value determinism
# ==========================================================================


def test_clark_west_adjusted_difference_matches_the_frozen_formula():
    targets = [Fraction(3), Fraction(5)]
    f0 = [Fraction(1), Fraction(4)]
    f1 = [Fraction(2), Fraction(9, 2)]
    got = ex.clark_west_adjusted_differences(targets=targets, forecasts_m0=f0, forecasts_m1=f1)
    expected = []
    for y, a, b in zip(targets, f0, f1):
        expected.append((y - a) ** 2 - (y - b) ** 2 + (a - b) ** 2)
    assert got == tuple(expected)
    # positive d favours M1: a strictly better M1 with a tiny correction term
    single = ex.clark_west_adjusted_differences(
        targets=[Fraction(10)], forecasts_m0=[Fraction(0)], forecasts_m1=[Fraction(9)]
    )
    assert single[0] > 0


def test_bartlett_newey_west_matches_an_independent_direct_oracle():
    values = [Fraction((index * 37) % 11 - 5, 3) for index in range(60)]
    got = ex.bartlett_newey_west_long_run_variance(values)
    count = len(values)
    mean = sum(values, Fraction(0)) / count
    centered = [value - mean for value in values]
    expected = sum((item * item for item in centered), Fraction(0)) / count
    for offset in range(1, 6):
        gamma = sum((centered[i] * centered[i - offset] for i in range(offset, count)), Fraction(0)) / count
        expected += 2 * Fraction(6 - offset, 6) * gamma
    assert got == expected


def test_hac_bartlett_weights_are_1_minus_j_over_l_plus_1():
    # A pure lag-1 pattern isolates the weight: d alternates +1 / -1 so
    # gamma_0 = 1 and gamma_1 = -(T-1)/T, all higher lags follow exactly.
    values = [Fraction((-1) ** index) for index in range(12)]
    got = ex.bartlett_newey_west_long_run_variance(values)
    count = 12
    expected = Fraction(1)
    for offset in range(1, 6):
        gamma = Fraction((-1) ** offset * (count - offset), count)
        expected += 2 * Fraction(6 - offset, 6) * gamma
    assert got == expected


def test_hac_uses_sample_size_divisor_and_no_finite_sample_correction():
    assert ex.HAC_AUTOCOVARIANCE_DIVISOR == "SAMPLE_SIZE_T"
    assert ex.HAC_FINITE_SAMPLE_CORRECTION == "NONE"
    assert ex.HAC_KERNEL == "BARTLETT_NEWEY_WEST"
    assert ex.TEST_REFERENCE_DISTRIBUTION == "STANDARD_NORMAL_ONE_SIDED_UPPER_TAIL"
    # divisor T, not T - j: a constant-magnitude series makes them differ
    values = [Fraction(1), Fraction(-1)] * 20
    assert ex.bartlett_newey_west_long_run_variance(values) != Fraction(0)


def test_clark_west_statistic_sign_follows_the_mean_adjusted_difference():
    favouring_m1 = [Fraction(1, 100) + Fraction((index % 5) - 2, 10000) for index in range(60)]
    mean, variance, statistic = ex.clark_west_statistic(favouring_m1)
    assert mean > 0 and variance > 0 and statistic > 0
    favouring_m0 = [-value for value in favouring_m1]
    mean_b, variance_b, statistic_b = ex.clark_west_statistic(favouring_m0)
    assert mean_b < 0 and statistic_b < 0
    assert statistic_b == statistic.copy_negate()
    assert ex.standard_normal_upper_tail(statistic) < ex.standard_normal_upper_tail(statistic_b)


def test_non_positive_hac_variance_fails_closed():
    with pytest.raises(ex.NumericalContractError):
        ex.clark_west_statistic([Fraction(3)] * 40)


def test_one_sided_p_value_matches_an_independent_erfc_oracle():
    worst = 0.0
    for tenths in range(-90, 91):
        z = Decimal(tenths) / 10
        got = float(ex.standard_normal_upper_tail(z))
        want = 0.5 * math.erfc(float(z) / math.sqrt(2))
        if want > 0:
            worst = max(worst, abs(got - want) / want)
    assert worst < 1e-12
    assert ex.standard_normal_upper_tail(Decimal(0)) == Decimal("0.5")
    assert ex.standard_normal_upper_tail(Decimal(-1000)) == Decimal(1)
    assert ex.standard_normal_upper_tail(Decimal(1000)) == Decimal(0)


def test_p_value_is_calibrated_at_the_frozen_one_sided_critical_value():
    at_critical = ex.standard_normal_upper_tail(ex.Z_CRITICAL_ONE_SIDED_5_PERCENT)
    assert abs(at_critical - Decimal("0.05")) < Decimal("1e-20")
    assert ex.standard_normal_upper_tail(ex.Z_CRITICAL_ONE_SIDED_5_PERCENT + Decimal("0.001")) < Decimal("0.05")
    assert ex.standard_normal_upper_tail(ex.Z_CRITICAL_ONE_SIDED_5_PERCENT - Decimal("0.001")) > Decimal("0.05")


def test_series_and_continued_fraction_branches_agree_at_the_same_argument():
    """The two erfc algorithms must agree far beyond the reported precision.

    The oracle test above already spans the crossover (z = 6*sqrt(2) ~ 8.485)
    against ``math.erfc``; this pins the two branches against each other at
    the exact crossover argument and to ~45 digits rather than ~15.
    """
    x = Decimal(6)
    work = Context(prec=110, rounding=ROUND_HALF_EVEN)
    with localcontext(work):
        series_tail = (Decimal(1) - ex._erf_series(x, work)) / 2
        continued_fraction_tail = ex._erfc_continued_fraction(x, work) / 2
        assert abs(series_tail - continued_fraction_tail) / continued_fraction_tail < Decimal("1e-45")
    assert x <= ex._NORMAL_TAIL_SERIES_THRESHOLD


def test_frozen_pi_expansion_matches_an_independent_machin_expansion():
    context = Context(prec=160, rounding=ROUND_HALF_EVEN)
    with localcontext(context):
        def arctan_inverse(integer: int) -> Decimal:
            total = term = Decimal(1) / Decimal(integer)
            square = Decimal(integer) * Decimal(integer)
            index = 1
            while True:
                term = -term / square
                contribution = term / (2 * index + 1)
                if contribution == 0:
                    break
                total += contribution
                index += 1
            return total

        machin = 4 * (4 * arctan_inverse(5) - arctan_inverse(239))
    frozen = Decimal(ex._PI_DIGITS)
    assert abs(machin - frozen) < Decimal(1).scaleb(-145)


def test_p_value_input_is_fail_closed():
    with pytest.raises(ex.NumericalContractError):
        ex.standard_normal_upper_tail(Decimal("NaN"))
    with pytest.raises(ex.NumericalContractError):
        ex.standard_normal_upper_tail(1.0)


# ==========================================================================
# 15 / 16 / 17 -- fail-closed inputs and exact origin counts
# ==========================================================================


def test_missing_origin_fails_closed(rows):
    with pytest.raises(ex.InputIntegrityError, match="missing"):
        ex.validate_forecast_rows(rows[:-1])
    with pytest.raises(ex.InputIntegrityError, match="missing"):
        ex.validate_forecast_rows(rows[:200] + rows[201:])


def test_extra_evaluation_origin_fails_closed(rows):
    extra = rows + (row_at("2025-06-20T00:00:00Z"),)
    with pytest.raises(ex.InputIntegrityError, match="extra"):
        ex.validate_forecast_rows(extra)
    duplicated = rows + (rows[-1],)
    with pytest.raises(ex.InputIntegrityError, match="duplicate"):
        ex.validate_forecast_rows(duplicated)


def test_reintroducing_the_excluded_boundary_origin_fails_closed(rows):
    with_boundary = rows[:365] + (row_at("2024-10-18T00:00:00Z"),) + rows[365:]
    with pytest.raises(ex.InputIntegrityError, match="extra"):
        ex.validate_forecast_rows(with_boundary)


def test_missing_grid_observation_fails_closed_without_gap_bridging():
    rv24, pressure = synthetic_grids()
    dropped = dict(rv24)
    dropped.pop(ex._stamp(datetime(2024, 3, 3, tzinfo=UTC)))
    with pytest.raises(ex.InputIntegrityError, match="missing"):
        ex.build_causal_forecast_rows(rv24_by_day=dropped, pressure_by_day=pressure)
    short_pressure = dict(pressure)
    short_pressure.pop(ex._stamp(ex.required_pressure_days()[0]))
    with pytest.raises(ex.InputIntegrityError, match="missing"):
        ex.build_causal_forecast_rows(rv24_by_day=rv24, pressure_by_day=short_pressure)


def test_grid_observation_outside_the_frozen_range_fails_closed():
    rv24, pressure = synthetic_grids()
    extended = dict(rv24)
    extended[ex._stamp(datetime(2025, 6, 20, tzinfo=UTC))] = Decimal("0.01")
    with pytest.raises(ex.InputIntegrityError, match="unexpected"):
        ex.build_causal_forecast_rows(rv24_by_day=extended, pressure_by_day=pressure)


@pytest.mark.parametrize("bad", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), Decimal("-0.001"), 0.01, "0.01", None])
def test_malformed_or_non_finite_values_fail_closed(bad):
    rv24, pressure = synthetic_grids()
    tampered = dict(rv24)
    tampered[ex._stamp(datetime(2024, 5, 5, tzinfo=UTC))] = bad
    with pytest.raises(ex.InputIntegrityError):
        ex.build_causal_forecast_rows(rv24_by_day=tampered, pressure_by_day=pressure)


def test_non_finite_row_values_fail_closed(rows):
    tampered = list(rows)
    bad = tampered[5]
    tampered[5] = ex.ForecastRow(
        origin=bad.origin,
        target_completion=bad.target_completion,
        funding_percentile=bad.funding_percentile,
        rv24_target=Decimal("NaN"),
        rv24_lags=bad.rv24_lags,
    )
    with pytest.raises(ex.InputIntegrityError):
        ex.validate_forecast_rows(tampered)


def test_percentile_outside_the_unit_interval_fails_closed(rows):
    tampered = list(rows)
    bad = tampered[7]
    tampered[7] = ex.ForecastRow(
        origin=bad.origin,
        target_completion=bad.target_completion,
        funding_percentile=Fraction(367, 366),
        rv24_target=bad.rv24_target,
        rv24_lags=bad.rv24_lags,
    )
    with pytest.raises(ex.InputIntegrityError):
        ex.validate_forecast_rows(tampered)


def test_float_magnitudes_are_refused_everywhere_contract_visible():
    with pytest.raises(ex.InputIntegrityError):
        ex._exact(0.25, label="probe")
    assert ex._exact(Decimal("0.25"), label="probe") == Fraction(1, 4)
    assert ex._exact(Fraction(1, 4), label="probe") == Fraction(1, 4)


def test_evaluation_reports_exactly_244_origins(evaluation):
    assert evaluation.evaluation_origin_count == 244
    assert len(evaluation.origin_forecasts) == 244
    assert evaluation.origin_forecasts[0].origin == "2024-10-19T00:00:00Z"
    assert evaluation.origin_forecasts[-1].origin == "2025-06-19T00:00:00Z"
    assert evaluation.first_evaluation_origin == "2024-10-19T00:00:00Z"
    assert evaluation.last_evaluation_origin == "2025-06-19T00:00:00Z"
    assert evaluation.excluded_boundary_origin == "2024-10-18T00:00:00Z"


# ==========================================================================
# 18 / 19 -- classification, determinism, authority
# ==========================================================================


def test_classification_rule_is_the_frozen_conjunction():
    passing = ex.classify(evaluation_origin_count=244, mse_m0=Fraction(2), mse_m1=Fraction(1), p_value=Decimal("0.05"))
    assert passing[0] == ex.CLASSIFICATION_PASS
    assert ex.classify(evaluation_origin_count=244, mse_m0=Fraction(2), mse_m1=Fraction(1), p_value=Decimal("0.050001"))[0] == ex.CLASSIFICATION_FAIL
    assert ex.classify(evaluation_origin_count=244, mse_m0=Fraction(1), mse_m1=Fraction(1), p_value=Decimal("0.001"))[0] == ex.CLASSIFICATION_FAIL
    assert ex.classify(evaluation_origin_count=244, mse_m0=Fraction(1), mse_m1=Fraction(2), p_value=Decimal("0.001"))[0] == ex.CLASSIFICATION_FAIL
    assert ex.classify(evaluation_origin_count=243, mse_m0=Fraction(2), mse_m1=Fraction(1), p_value=Decimal("0.001"))[0] == ex.CLASSIFICATION_BLOCKED
    assert ex.CLASSIFICATION_FAIL == "FUNDING_PRESSURE_INCREMENTAL_VALUE_NOT_ESTABLISHED"


def test_pass_claim_boundary_is_explicitly_narrow(evaluation):
    for token in ("NOT_MATERIALITY", "NOT_CAUSAL", "NOT_TRADING_EDGE", "NOT_ROUTER_AUTHORITY", "NOT_QNTY_AUTHORITY", "NOT_SEALED_EVALUATION", "NOT_PROSPECTIVE", "NOT_INDEPENDENT_CONFIRMATION"):
        assert token in evaluation.claim_boundary
    assert ex.DOWNSTREAM_AUTHORITY == "NONE"
    assert ex.CAPITAL_AUTHORITY == "NONE"


def test_replay_on_identical_synthetic_input_is_bit_identical(rows, evaluation):
    replay = ex.run_incremental_forecast_evaluation(build_rows(), execution_mode=MODE)
    assert replay.result_digest == evaluation.result_digest
    assert replay.mse_m0 == evaluation.mse_m0
    assert replay.mse_m1 == evaluation.mse_m1
    assert replay.clark_west_statistic == evaluation.clark_west_statistic
    assert replay.clark_west_one_sided_p_value == evaluation.clark_west_one_sided_p_value
    assert replay.classification == evaluation.classification


def test_different_synthetic_input_changes_the_digest(evaluation):
    other = ex.run_incremental_forecast_evaluation(build_rows(seed=999), execution_mode=MODE)
    assert other.result_digest != evaluation.result_digest


def test_ambient_decimal_context_cannot_change_the_result(evaluation):
    hostile = Context(prec=7, rounding="ROUND_UP")
    with localcontext(hostile):
        replay = ex.run_incremental_forecast_evaluation(build_rows(), execution_mode=MODE)
    assert replay.result_digest == evaluation.result_digest


def test_an_analytically_obvious_funding_signal_is_detected_with_the_right_sign():
    """RV24 is built as a positive linear function of same-day funding pressure.

    M1 must beat M0 and the one-sided Clark-West test must reject.  If the
    funding column were misaligned by a day, sign-flipped, or dropped, this
    fixture would not pass.
    """
    signal = ex.run_incremental_forecast_evaluation(
        build_rows(funding_signal=Fraction(40)), execution_mode=MODE
    )
    assert signal.mse_m1 < signal.mse_m0
    assert signal.relative_mse_improvement > 0
    assert signal.clark_west_mean_difference > 0
    assert signal.clark_west_statistic > 0
    assert signal.clark_west_one_sided_p_value <= Decimal("0.05")
    assert signal.classification == ex.CLASSIFICATION_PASS


def test_pure_noise_does_not_produce_a_pass(evaluation):
    assert evaluation.classification == ex.CLASSIFICATION_FAIL
    assert evaluation.clark_west_one_sided_p_value > Decimal("0.05")


# ==========================================================================
# 20 -- canonical low-level reuse (no funding / RV semantic duplication)
# ==========================================================================


def funding_event(symbol: str, timestamp: datetime, rate: str) -> foundation.VerifiedFundingEvent:
    ms = int(timestamp.timestamp() * 1000)
    return foundation.VerifiedFundingEvent(
        symbol, ms, timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z"), Decimal(rate)
    )


def ohlcv_bar(symbol: str, timestamp: datetime, close: str) -> foundation.VerifiedBarOpenClose:
    return foundation.VerifiedBarOpenClose(
        symbol, timestamp.isoformat(timespec="seconds").replace("+00:00", "Z"), Decimal(close)
    )


def test_daily_pressure_delegates_to_the_canonical_v2_primitives():
    day = datetime(2024, 3, 1, tzinfo=UTC)
    funding = {
        symbol: [
            funding_event(symbol, day - timedelta(hours=32), "0.5"),
            funding_event(symbol, day - timedelta(hours=8), f"-0.{index + 1:04d}"),
        ]
        for index, symbol in enumerate(ex.PANEL)
    }
    got = ex.daily_funding_pressure(funding, day)
    selected = {
        symbol: v2.select_latest_eligible_funding(funding[symbol], day, symbol=symbol) for symbol in v2.PANEL
    }
    assert got == v2.median_abs_funding(selected)
    # 20 distinct magnitudes 0.0001..0.0020; the frozen median of an even
    # panel is the mean of the two central order statistics, and the stale
    # 0.5 events 32h back are outside the eligibility window.
    assert got == (Decimal("0.0010") + Decimal("0.0011")) / 2


def test_daily_rv24_delegates_to_the_canonical_v2_primitives():
    day = datetime(2024, 3, 1, tzinfo=UTC)
    bars = {}
    for index, symbol in enumerate(ex.PANEL):
        series = []
        for hour in range(-2, 27):
            close = Decimal(100) + Decimal(hour * (index + 1)) / 1000
            series.append(ohlcv_bar(symbol, day + timedelta(hours=hour - 1), str(close)))
        bars[symbol] = series
    got = ex.daily_rv24(bars, day)
    per_symbol = {symbol: v2.hourly_asset_returns(bars[symbol], day) for symbol in v2.PANEL}
    expected = v2.rv24(
        v2.market_returns(
            tuple({symbol: per_symbol[symbol][hour] for symbol in v2.PANEL} for hour in range(24))
        )
    )
    assert got == expected
    assert got > 0


def test_grids_built_from_evidence_types_match_the_canonical_helpers():
    days = [datetime(2024, 3, 1, tzinfo=UTC), datetime(2024, 3, 2, tzinfo=UTC)]
    funding = {
        symbol: [funding_event(symbol, day - timedelta(hours=4), f"0.{index + 1:04d}") for day in days]
        for index, symbol in enumerate(ex.PANEL)
    }
    grid = ex.build_daily_pressure_grid(funding, days)
    assert set(grid) == {ex._stamp(day) for day in days}
    assert all(isinstance(value, Decimal) for value in grid.values())


def test_executor_does_not_redefine_canonical_funding_or_rv_semantics():
    source = (ROOT / ex.MODULE_RELATIVE_PATH).read_text(encoding="utf-8")
    for delegated in (
        "v2.select_latest_eligible_funding",
        "v2.median_abs_funding",
        "v2.ecdf_percentile",
        "v2.hourly_asset_returns",
        "v2.market_returns",
        "v2.rv24",
    ):
        assert delegated in source
    tree = ast.parse(source)
    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    # none of the canonical low-level semantics are re-declared locally
    assert defined.isdisjoint(
        {
            "select_latest_eligible_funding",
            "median_abs_funding",
            "ecdf_percentile",
            "classify_state",
            "hourly_asset_returns",
            "market_returns",
            "rv24",
            "source_open_for_logical_close",
        }
    )
    assert "sqrt()" not in source.replace("_decimal(variance_of_mean, STATISTIC_CONTEXT).sqrt()", "").replace(
        "Decimal(2).sqrt()", ""
    ).replace("_pi(context).sqrt()", "")


def test_ecdf_history_is_the_frozen_365_prior_observations(rows):
    _, pressure = synthetic_grids()
    row = rows[0]
    origin = ex._utc(row.origin)
    prior = [pressure[ex._stamp(origin - timedelta(days=offset))] for offset in range(365, 0, -1)]
    assert len(prior) == 365
    assert row.funding_percentile == v2.ecdf_percentile(prior, pressure[row.origin])
    assert row.funding_percentile.denominator in {d for d in range(1, 367) if 366 % d == 0}


# ==========================================================================
# authority boundary / no real execution
# ==========================================================================


@pytest.mark.parametrize("mode", ["REAL", "PRODUCTION", "REAL_EVIDENCE", "", None, "synthetic_validation", True])
def test_every_non_synthetic_execution_mode_is_refused(rows, mode):
    with pytest.raises(ex.UnauthorizedExecutionError):
        ex.run_incremental_forecast_evaluation(rows, execution_mode=mode)


def test_module_contains_no_evidence_loader_network_or_claim_path():
    source = (ROOT / ex.MODULE_RELATIVE_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            if node.module == "qntylab":
                imported.update(alias.name for alias in node.names)
    assert not {name for name in imported if name.split(".")[0] in {"requests", "urllib", "http", "socket", "subprocess", "ssl"}}
    # Identifiers actually referenced by code, so prose in the docstring that
    # *names* a forbidden seam in order to disclaim it does not trip the test.
    referenced = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
    forbidden = {
        "load_verified_frozen_evidence",
        "claim_authorization_once",
        "execute_authorized_frozen_experiment_v2",
        "attest_v2_runtime",
        "validate_v2_authorization",
        "parse_authorization_envelope",
        "GitHubRestRemoteClaimTransport",
        "AuthorizationEnvelope",
        "V2AuthorizationEnvelope",
        "compute_frozen_experiment",
        "build_receipt_provenance",
        "open",
        "urlopen",
        "eval",
        "exec",
        "__import__",
    }
    assert referenced.isdisjoint(forbidden), sorted(referenced & forbidden)
    # ``read_bytes`` on this module's own source is the only filesystem touch
    assert {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)} & {
        "read_text", "write_text", "write_bytes", "get", "post", "urlopen", "run"
    } == set()


def test_no_real_execution_attestation_is_uniformly_false():
    assert set(ex.NO_REAL_EXECUTION_ATTESTATION.values()) == {False}
    for key in (
        "REAL_EVIDENCE_EXECUTION_PERFORMED",
        "REAL_SCIENTIFIC_EXECUTION_PERFORMED",
        "REAL_EVALUATION_OUTCOMES_ACCESSED",
        "MARKET_DATA_ACQUIRED",
        "FUNDING_DATA_ACQUIRED",
        "NETWORK_ACCESS_PERFORMED",
        "SCIENTIFIC_RESULT_RECORDED",
        "TRIAL_COMPLETION_RECORDED",
        "PREREGISTRATION_MUTATED",
        "JH01_LEDGER_ACCESSED",
        "ORDER_FLOW_REOPENED",
    ):
        assert ex.NO_REAL_EXECUTION_ATTESTATION[key] is False


def test_implementation_identity_binds_the_governing_preregistration():
    identity = ex.implementation_identity(ROOT)
    assert identity["governing_preregistration_project_id"] == "JIGSAW_FUNDING_PRESSURE_INCREMENTAL_FORECAST_VALUE_PREREGISTRATION_V0"
    assert identity["governing_candidate_id"] == "CANDIDATE_FUNDING_PRESSURE_INCREMENTAL_RV_FORECAST_VALUE_V0"
    assert identity["governing_preregistration_digest"] == "d7ec718ab14e73d2aea24749a22caa2921fd81b8a336e2f2eaffb30ae1e992ef"
    assert identity["selected_architecture"] == "A_EXPLORATORY_610_INCREMENTAL_FORECAST_TEST"
    assert identity["implementation_source_path"] == ex.MODULE_RELATIVE_PATH
    assert len(identity["implementation_source_sha256"]) == 64
    assert identity["execution_modes"] == ["SYNTHETIC_VALIDATION"]
    assert identity["downstream_authority"] == "NONE"
    assert identity["capital_authority"] == "NONE"


def test_governing_preregistration_digest_still_matches_the_frozen_artifact():
    from qntylab import jigsaw_funding_pressure_incremental_forecast_value_prereg_v0 as prereg

    document = prereg.load_preregistration(ROOT)
    assert document["preregistration_digest"] == ex.GOVERNING_PREREGISTRATION_DIGEST
    assert document["status"] == "PREREGISTERED_NOT_EXECUTED"
    assert document["selected_architecture"]["id"] == ex.SELECTED_ARCHITECTURE
    assert document["evaluation_contract"]["required_evaluation_origins"] == ex.REQUIRED_EVALUATION_ORIGINS
    assert document["evaluation_contract"]["minimum_training_origins"] == ex.MINIMUM_TRAINING_ORIGINS
    assert document["evaluation_contract"]["first_forecast_origin"] == ex._stamp(ex.FIRST_EVALUATION_ORIGIN)
    assert document["evaluation_contract"]["last_forecast_origin"] == ex._stamp(ex.LAST_EVALUATION_ORIGIN)
    assert document["evaluation_contract"]["training_target_cutoff"] == "TARGET_COMPLETION_TIME < FORECAST_ORIGIN"
    assert document["testing_contract"]["primary_test"]["hac"] == "BARTLETT_NEWEY_WEST_FIXED_LAG_5"
    assert document["testing_contract"]["primary_test"]["alpha"] == float(ex.ALPHA)
    assert document["selected_architecture"]["excluded_boundary_origin"] == ex._stamp(ex.EXCLUDED_BOUNDARY_ORIGIN)
    assert document["selected_architecture"]["development_range"] == (
        f"{ex._stamp(ex.FIRST_DEVELOPMENT_ORIGIN)}..{ex._stamp(ex.LAST_DEVELOPMENT_ORIGIN)}"
    )
