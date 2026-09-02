"""Differential equivalence gate: successor core extraction V1 vs historical V0.

Phase ``FUNDING_INCREMENTAL_EXECUTOR_CORE_EXTRACTION_AND_SUCCESSOR_IMPLEMENTATION_V1``.

The oracle is the ACTUAL historical V0 bytes at commit
``f6f12994d65c3dfeaf7839de560e58ad99547c62`` (source sha256
``b894d4d9316bed6f8c4f7171b32692aff7b1f0eb32abd686a33fdb38425a7490``),
loaded from the isolated read-only oracle worktree via importlib.  The
oracle's source sha256 is verified inside this module before use.  No
approximation of V0 is recreated here.

Equivalence rules (authorization ``equivalence_closure_gate``):

* valid inputs: exact contract-visible field equality, canonical
  serialization equality (``json.dumps(sort_keys=True,
  separators=(",", ":"))``) and result digest equality;
* invalid inputs: same failure class AND same fail-closed semantics --
  exception class name plus contract-visible failure detail, not merely
  "both raise";
* any unexplained valid divergence = SCIENTIFIC_SEMANTICS_CHANGED = phase
  FAIL.

Every fixture is SYNTHETIC.  No real evidence is loaded, no real evaluation
outcome is read, no evaluation origin is consumed, no market or funding
data is acquired, and no network call is made.
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Context, Decimal, ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP, ROUND_UP, ROUND_05UP, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from qntylab import jigsaw_funding_pressure_execution_v2 as v2
from qntylab import jigsaw_funding_pressure_incremental_forecast_value_executor_v0 as successor

from test_jigsaw_funding_pressure_incremental_forecast_value_executor_v0 import (
    build_rows as successor_build_rows,
    synthetic_grids,
)

ROOT = Path(__file__).resolve().parents[1]

ORACLE_COMMIT = "f6f12994d65c3dfeaf7839de560e58ad99547c62"
ORACLE_SOURCE_RELATIVE_PATH = "qntylab/jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py"
ORACLE_SOURCE_SHA256 = "b894d4d9316bed6f8c4f7171b32692aff7b1f0eb32abd686a33fdb38425a7490"
ORACLE_WORKTREE_ENV_VAR = "QNTYLAB_FUNDING_V0_ORACLE_WORKTREE"

FROZEN_SYNTHETIC_RESULT_DIGEST = "sha256:1fca55ebdbe5c4d5b835cb65f87930755d231449c924eae912b522bd04b53ea2"
CANONICAL_RESULT_SCHEMA_SHA256 = "0eb5029002fe472035023b9d73b4d852cf1a3f18a2693ed3454e5167cca2871f"

VALID_ROWS_SEED = 20260820
MALFORMED_ROWS_SEED = 20260821

MODE = successor.EXECUTION_MODE_SYNTHETIC_VALIDATION


# --------------------------------------------------------------------------
# oracle loading (actual historical bytes, verified)
# --------------------------------------------------------------------------


def _oracle_worktree_root() -> Path:
    candidates: list[Path] = []
    env = os.environ.get(ORACLE_WORKTREE_ENV_VAR)
    if env:
        candidates.append(Path(env))
    listing = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    current_block: dict[str, str] = {}
    for line in listing.splitlines():
        if line.startswith("worktree "):
            current_block = {"worktree": line[len("worktree "):]}
        elif line.startswith("HEAD ") and current_block:
            current_block["HEAD"] = line[len("HEAD "):]
            if current_block.get("HEAD") == ORACLE_COMMIT:
                candidates.append(Path(current_block["worktree"]))
            current_block = {}
    for candidate in candidates:
        source = candidate / ORACLE_SOURCE_RELATIVE_PATH
        if source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() == ORACLE_SOURCE_SHA256:
            return candidate
    pytest.fail(
        "no oracle worktree with the verified historical V0 bytes was found "
        f"(set {ORACLE_WORKTREE_ENV_VAR} or run `git worktree add --detach "
        f"<path> {ORACLE_COMMIT}`); candidates={candidates}"
    )


def _load_oracle_module():
    root = _oracle_worktree_root()
    source_path = root / ORACLE_SOURCE_RELATIVE_PATH
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    assert digest == ORACLE_SOURCE_SHA256, "oracle bytes are not the historical V0 source"
    spec = importlib.util.spec_from_file_location("funding_incremental_v0_oracle_executor", source_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def oracle():
    return _load_oracle_module()


@pytest.fixture(scope="session")
def oracle_root():
    return _oracle_worktree_root()


# --------------------------------------------------------------------------
# comparison helpers
# --------------------------------------------------------------------------


def failure_of(call, *args, **kwargs):
    """Capture the fail-closed semantics: class name + contract-visible detail."""
    try:
        call(*args, **kwargs)
    except Exception as error:  # noqa: BLE001 - the comparison IS the test
        return {
            "raised": True,
            "class": type(error).__name__,
            "mro": [base.__name__ for base in type(error).__mro__],
            "message": str(error),
        }
    return {"raised": False}


def assert_same_failure(callable_a, callable_b, *, case_id: str):
    left = failure_of(callable_a)
    right = failure_of(callable_b)
    assert left == right, f"{case_id}: failure semantics diverged:\n oracle={left}\n successor={right}"
    assert left["raised"] is True, f"{case_id}: expected a fail-closed error on both sides"


def canonical_result_document(module, result) -> str:
    """Contract-visible canonical serialization of an evaluation result."""

    def serialize(value):
        if isinstance(value, Fraction):
            return str(module.report_decimal(value))
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise AssertionError("non-finite Decimal in a canonical result")
            return str(value)
        if isinstance(value, Mapping):
            return {str(key): serialize(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [serialize(item) for item in value]
        if isinstance(value, module.OriginForecast):
            return {
                field.name: serialize(getattr(value, field.name)) for field in dataclasses.fields(module.OriginForecast)
            }
        return value

    document = {
        field.name: serialize(getattr(result, field.name)) for field in dataclasses.fields(module.IncrementalForecastEvaluation)
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":"))


def assert_equivalent_results(oracle, result_o, result_s, *, case_id: str):
    """Valid-input equivalence: fields, canonical serialization, digest."""
    for field in dataclasses.fields(oracle.IncrementalForecastEvaluation):
        left = getattr(result_o, field.name)
        right = getattr(result_s, field.name)
        if field.name == "origin_forecasts":
            assert len(left) == len(right), case_id
            for index, (item_o, item_s) in enumerate(zip(left, right)):
                for sub in dataclasses.fields(oracle.OriginForecast):
                    assert getattr(item_o, sub.name) == getattr(item_s, sub.name), (
                        f"{case_id}: origin_forecasts[{index}].{sub.name} diverged"
                    )
        elif field.name == "gates":
            assert dict(left) == dict(right), f"{case_id}: gates diverged"
        else:
            assert left == right, f"{case_id}: field {field.name} diverged"
    assert result_o.result_digest == result_s.result_digest, f"{case_id}: result digest diverged"
    assert canonical_result_document(oracle, result_o) == canonical_result_document(successor, result_s), (
        f"{case_id}: canonical serialization diverged"
    )


def row_tuple(module, row):
    return (
        row.origin,
        row.target_completion,
        row.funding_percentile,
        str(row.rv24_target),
        tuple(str(lag) for lag in row.rv24_lags),
    )


def make_row(module, origin, *, percentile=Fraction(1, 2), target="0.01", lag_value="0.02", lags=None):
    origin_dt = module._utc(origin)
    return module.ForecastRow(
        origin=module._stamp(origin_dt),
        target_completion=module._stamp(module.target_completion_time(origin_dt)),
        funding_percentile=percentile,
        rv24_target=Decimal(target),
        rv24_lags=tuple(Decimal(lag_value) for _ in range(30)) if lags is None else tuple(lags),
    )


def run_both_full(oracle, grids, *, case_id: str, seed_note: str | None = None):
    """Build rows per module from identical grids and compare full results."""
    rows_o = oracle.build_causal_forecast_rows(
        rv24_by_day=grids["rv24"], pressure_by_day=grids["pressure"]
    )
    rows_s = successor.build_causal_forecast_rows(
        rv24_by_day=grids["rv24"], pressure_by_day=grids["pressure"]
    )
    assert [row_tuple(oracle, row) for row in rows_o] == [row_tuple(successor, row) for row in rows_s], (
        f"{case_id}: causal row construction diverged"
    )
    result_o = oracle.run_incremental_forecast_evaluation(rows_o, execution_mode=MODE)
    result_s = successor.run_incremental_forecast_evaluation(rows_s, execution_mode=MODE)
    assert_equivalent_results(oracle, result_o, result_s, case_id=case_id)
    return result_s


# --------------------------------------------------------------------------
# corpus registry (bound into differential_corpus_manifest.json)
# --------------------------------------------------------------------------


def corpus_case_registry() -> list[dict[str, object]]:
    """The deterministic differential corpus, in canonical order."""
    cases: list[dict[str, object]] = []
    def add(case_id, kind, failure_class=None, detail=None):
        cases.append(
            {
                "case_id": case_id,
                "kind": kind,
                "failure_class": failure_class,
                "detail": detail or case_id,
            }
        )

    # -- valid fixtures harvested from the V0 test file -------------------
    add("valid_canonical_synthetic_fixture", "valid", detail="build_rows() default grids")
    add("valid_alternate_seed_999", "valid")
    add("valid_analytic_funding_signal_pass", "valid", detail="classification PASS case")
    add("valid_pure_noise_fail", "valid", detail="classification FAIL case")
    add(f"valid_pseudo_random_rows_seed_{VALID_ROWS_SEED}", "valid")
    add("valid_schedule_boundaries", "valid")
    add("valid_har_and_design_rows", "valid")
    add("valid_exact_ols_fixtures", "valid")
    add("valid_quantization_edges", "valid")
    add("valid_loss_and_floor_fixtures", "valid")
    add("valid_clark_west_hac_fixtures", "valid")
    add("valid_normal_tail_grid", "valid")
    add("valid_classification_grid", "valid")
    add("valid_report_decimal_fixtures", "valid")
    add("valid_exact_coercion_fixtures", "valid")
    add("valid_daily_pressure_delegation", "valid")
    add("valid_daily_rv24_delegation", "valid")
    add("invalid_panel_reorder", "invalid", "ComputationError")
    add("invalid_panel_substitution", "invalid", "ComputationError")
    add("valid_replay_bit_identity", "valid")

    # -- invalid classes ---------------------------------------------------
    add("invalid_unauthorized_mode_REAL", "invalid", "UnauthorizedExecutionError")
    add("invalid_unauthorized_mode_none", "invalid", "UnauthorizedExecutionError")
    add("invalid_unauthorized_mode_empty", "invalid", "UnauthorizedExecutionError")
    add("invalid_unauthorized_mode_lowercase", "invalid", "UnauthorizedExecutionError")
    add("invalid_unauthorized_mode_int", "invalid", "UnauthorizedExecutionError")
    add("invalid_swapped_temporal_order", "invalid", "TemporalContractError")
    add("invalid_target_completion_not_origin_plus_24h", "invalid", "TemporalContractError")
    add("invalid_training_below_frozen_minimum", "invalid", "TemporalContractError")
    add("invalid_training_row_at_or_after_origin", "invalid", "TemporalContractError")
    add("invalid_missing_forecast_row", "invalid", "InputIntegrityError")
    add("invalid_extra_forecast_row", "invalid", "InputIntegrityError")
    add("invalid_duplicate_forecast_row", "invalid", "InputIntegrityError")
    add("invalid_boundary_origin_reintroduced", "invalid", "InputIntegrityError")
    add("invalid_missing_grid_observation", "invalid", "InputIntegrityError")
    add("invalid_extra_grid_observation", "invalid", "InputIntegrityError")
    add("invalid_non_finite_grid_value", "invalid", "InputIntegrityError")
    add("invalid_negative_grid_value", "invalid", "InputIntegrityError")
    add("invalid_float_grid_value", "invalid", "InputIntegrityError")
    add("invalid_non_finite_row_target", "invalid", "InputIntegrityError")
    add("invalid_percentile_outside_unit_interval", "invalid", "InputIntegrityError")
    add("invalid_wrong_lag_count", "invalid", "InputIntegrityError")
    add("invalid_exact_refuses_float", "invalid", "InputIntegrityError")
    add("invalid_hac_lag_selection", "invalid", "ContractViolationError")
    add("invalid_alpha_not_frozen", "invalid", "ContractViolationError")
    add("invalid_empty_mse", "invalid", "ContractViolationError")
    add("invalid_relative_improvement_zero_baseline", "invalid", "ContractViolationError")
    add("invalid_linear_forecast_length_mismatch", "invalid", "ContractViolationError")
    add("invalid_floor_on_float", "invalid", "ContractViolationError")
    add("invalid_quantize_on_float", "invalid", "ContractViolationError")
    add("invalid_ols_float_entry", "invalid", "ContractViolationError")
    add("invalid_ols_ragged_design", "invalid", "ContractViolationError")
    add("invalid_clark_west_length_mismatch", "invalid", "ContractViolationError")
    add("invalid_clark_west_empty", "invalid", "ContractViolationError")
    add("invalid_ols_rank_deficient_duplicate_column", "invalid", "RankDeficientDesignError")
    add("invalid_ols_rank_deficient_constant_column", "invalid", "RankDeficientDesignError")
    add("invalid_ols_fewer_observations_than_regressors", "invalid", "RankDeficientDesignError")
    add("invalid_evaluation_rank_deficient_flat_pressure", "invalid", "RankDeficientDesignError")
    add("invalid_hac_variance_not_positive", "invalid", "NumericalContractError")
    add("invalid_p_value_nan", "invalid", "NumericalContractError")
    add("invalid_p_value_float", "invalid", "NumericalContractError")
    add(f"invalid_pseudo_random_malformed_rows_seed_{MALFORMED_ROWS_SEED}", "invalid", "InputIntegrityError")

    # -- hostile Decimal contexts -----------------------------------------
    for index, context in enumerate(HOSTILE_CONTEXTS):
        add(
            f"hostile_decimal_context_{index:02d}",
            "valid",
            detail=(
                f"prec={context.prec} rounding={context.rounding} "
                f"Emin={context.Emin} Emax={context.Emax}"
            ),
        )
    return cases


def corpus_digest() -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(corpus_case_registry(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


# --------------------------------------------------------------------------
# hostile Decimal contexts (>= 24, deterministic)
# --------------------------------------------------------------------------

HOSTILE_CONTEXTS = [
    Context(prec=1, rounding=ROUND_UP),
    Context(prec=2, rounding=ROUND_FLOOR),
    Context(prec=7, rounding=ROUND_CEILING),
    Context(prec=300, rounding=ROUND_05UP),
    Context(prec=9, Emin=-5, Emax=5, rounding=ROUND_UP),
    Context(prec=3, rounding=ROUND_DOWN),
    Context(prec=13, rounding=ROUND_HALF_UP),
    Context(prec=28, rounding=ROUND_HALF_EVEN),
    Context(prec=50, rounding=ROUND_UP),
    Context(prec=4, Emin=-20, Emax=20, rounding=ROUND_FLOOR),
    Context(prec=6, rounding=ROUND_DOWN),
    Context(prec=11, rounding=ROUND_05UP),
    Context(prec=17, rounding=ROUND_CEILING),
    Context(prec=23, rounding=ROUND_HALF_UP),
    Context(prec=31, rounding=ROUND_DOWN),
    Context(prec=64, rounding=ROUND_FLOOR),
    Context(prec=2, Emin=-3, Emax=3, rounding=ROUND_CEILING),
    Context(prec=5, rounding=ROUND_UP),
    Context(prec=8, rounding=ROUND_HALF_EVEN),
    Context(prec=12, Emin=-9, Emax=9, rounding=ROUND_HALF_UP),
    Context(prec=19, rounding=ROUND_05UP),
    Context(prec=40, rounding=ROUND_DOWN),
    Context(prec=99, rounding=ROUND_FLOOR),
    Context(prec=150, rounding=ROUND_HALF_UP),
]

assert len(HOSTILE_CONTEXTS) >= 24


# ==========================================================================
# 1 -- oracle identity and schema binding
# ==========================================================================


def test_oracle_is_the_actual_historical_v0_bytes(oracle_root):
    source = oracle_root / ORACLE_SOURCE_RELATIVE_PATH
    assert hashlib.sha256(source.read_bytes()).hexdigest() == ORACLE_SOURCE_SHA256
    assert source.exists()


def test_successor_source_digest_differs_from_the_historical_digest():
    successor_digest = hashlib.sha256(
        (ROOT / successor.MODULE_RELATIVE_PATH).read_bytes()
    ).hexdigest()
    assert successor_digest != ORACLE_SOURCE_SHA256


def test_canonical_result_schema_digest_is_unchanged():
    """RESULT_SCHEMA_IDENTITY = PASS: the computed schema digest still equals
    0eb50290... with the dataclasses living in the executor module."""
    import ast

    tree = ast.parse((ROOT / successor.MODULE_RELATIVE_PATH).read_text(encoding="utf-8"))
    fields = {
        node.name: [
            item.target.id
            for item in node.body
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
        ]
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in {"IncrementalForecastEvaluation", "OriginForecast"}
    }
    schema = {
        "result_type": "IncrementalForecastEvaluation",
        "fields": fields["IncrementalForecastEvaluation"],
        "origin_forecast_fields": fields["OriginForecast"],
    }
    digest = hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert digest == CANONICAL_RESULT_SCHEMA_SHA256


def test_module_level_contract_constants_are_identical(oracle):
    for name in (
        "GOVERNING_PREREGISTRATION_DIGEST",
        "SELECTED_ARCHITECTURE",
        "AUTHORIZED_EXECUTION_MODES",
        "PASS_CLAIM_BOUNDARY",
        "DOWNSTREAM_AUTHORITY",
        "CAPITAL_AUTHORITY",
        "HAR_LAG_WINDOWS",
        "HAR_MAX_LAG_DAYS",
        "HAC_KERNEL",
        "HAC_FIXED_LAG",
        "HAC_AUTOCOVARIANCE_DIVISOR",
        "HAC_FINITE_SAMPLE_CORRECTION",
        "TEST_REFERENCE_DISTRIBUTION",
        "ALPHA",
        "Z_CRITICAL_ONE_SIDED_5_PERCENT",
        "CLASSIFICATION_PASS",
        "CLASSIFICATION_FAIL",
        "CLASSIFICATION_BLOCKED",
        "REQUIRED_EVALUATION_ORIGINS",
        "REQUIRED_DEVELOPMENT_ORIGINS",
        "MINIMUM_TRAINING_ORIGINS",
        "FIRST_DEVELOPMENT_ORIGIN",
        "LAST_DEVELOPMENT_ORIGIN",
        "EXCLUDED_BOUNDARY_ORIGIN",
        "FIRST_EVALUATION_ORIGIN",
        "LAST_EVALUATION_ORIGIN",
        "OLS_COEFFICIENT_PRECISION",
        "OLS_COEFFICIENT_ROUNDING",
        "REPORT_PRECISION",
        "STATISTIC_PRECISION",
        "P_VALUE_PRECISION",
        "_PI_DIGITS",
        "_LN_10",
        "_NORMAL_TAIL_SERIES_THRESHOLD",
        "_NORMAL_TAIL_SATURATION",
        "_NORMAL_TAIL_MAX_TERMS",
    ):
        assert getattr(successor, name) == getattr(oracle, name), name
    for name in ("ESTIMATION_CONTEXT", "REPORT_CONTEXT", "STATISTIC_CONTEXT"):
        left, right = getattr(successor, name), getattr(oracle, name)
        assert (left.prec, left.rounding, left.Emin, left.Emax) == (
            right.prec,
            right.rounding,
            right.Emin,
            right.Emax,
        ), name
    assert dict(successor.NO_REAL_EXECUTION_ATTESTATION) == dict(oracle.NO_REAL_EXECUTION_ATTESTATION)


# ==========================================================================
# 2 -- schedule boundaries (valid)
# ==========================================================================


def test_schedule_functions_are_identical(oracle):
    assert oracle.development_origins() == successor.development_origins()
    assert oracle.evaluation_origins() == successor.evaluation_origins()
    assert oracle.forecast_row_origins() == successor.forecast_row_origins()
    assert oracle.required_rv24_days() == successor.required_rv24_days()
    assert oracle.required_pressure_days() == successor.required_pressure_days()
    for day in (oracle.FIRST_EVALUATION_ORIGIN, oracle.EXCLUDED_BOUNDARY_ORIGIN, oracle.LAST_EVALUATION_ORIGIN):
        assert oracle.target_completion_time(day) == successor.target_completion_time(day)
        assert oracle._stamp(day) == successor._stamp(day)


def test_boundary_origin_strict_cutoff_behaves_identically(oracle):
    first = oracle.FIRST_EVALUATION_ORIGIN
    padding_o = [make_row(oracle, first - timedelta(days=offset)) for offset in range(2, 2 + oracle.MINIMUM_TRAINING_ORIGINS)]
    padding_s = [make_row(successor, first - timedelta(days=offset)) for offset in range(2, 2 + successor.MINIMUM_TRAINING_ORIGINS)]
    boundary_o = make_row(oracle, datetime(2024, 10, 18, tzinfo=UTC))
    boundary_s = make_row(successor, datetime(2024, 10, 18, tzinfo=UTC))
    excluded_o = oracle.select_training_rows(padding_o + [boundary_o], first)
    excluded_s = successor.select_training_rows(padding_s + [boundary_s], first)
    assert [row.origin for row in excluded_o] == [row.origin for row in excluded_s]
    assert boundary_o.origin not in {row.origin for row in excluded_o}
    later_o = oracle.select_training_rows(padding_o + [boundary_o], first + timedelta(days=1))
    later_s = successor.select_training_rows(padding_s + [boundary_s], first + timedelta(days=1))
    assert boundary_o.origin in {row.origin for row in later_o}
    assert [row.origin for row in later_o] == [row.origin for row in later_s]


# ==========================================================================
# 3 -- full-evaluation valid corpus
# ==========================================================================


def test_differential_canonical_synthetic_fixture_and_frozen_digest_gate(oracle):
    """FROZEN_SYNTHETIC_DIGEST_EQUALITY = PASS (and full differential equality)."""
    grids = dict(zip(("rv24", "pressure"), synthetic_grids()))
    result = run_both_full(oracle, grids, case_id="canonical_synthetic_fixture")
    assert result.result_digest == FROZEN_SYNTHETIC_RESULT_DIGEST


def test_differential_alternate_seed_999(oracle):
    grids = dict(zip(("rv24", "pressure"), synthetic_grids(seed=999)))
    run_both_full(oracle, grids, case_id="alternate_seed_999")


def test_differential_analytic_funding_signal_is_a_pass_case(oracle):
    grids = dict(zip(("rv24", "pressure"), synthetic_grids(funding_signal=Fraction(40))))
    result = run_both_full(oracle, grids, case_id="analytic_funding_signal_pass")
    assert result.classification == successor.CLASSIFICATION_PASS


def test_differential_pure_noise_is_a_fail_case(oracle):
    grids = dict(zip(("rv24", "pressure"), synthetic_grids()))
    rows_o = oracle.build_causal_forecast_rows(rv24_by_day=grids["rv24"], pressure_by_day=grids["pressure"])
    rows_s = successor.build_causal_forecast_rows(rv24_by_day=grids["rv24"], pressure_by_day=grids["pressure"])
    result_o = oracle.run_incremental_forecast_evaluation(rows_o, execution_mode=MODE)
    result_s = successor.run_incremental_forecast_evaluation(rows_s, execution_mode=MODE)
    assert result_o.classification == result_s.classification == successor.CLASSIFICATION_FAIL
    assert_equivalent_results(oracle, result_o, result_s, case_id="pure_noise_fail")


def test_differential_pseudo_random_valid_rows_seed_20260820(oracle):
    grids = dict(zip(("rv24", "pressure"), synthetic_grids(seed=VALID_ROWS_SEED)))
    run_both_full(oracle, grids, case_id=f"pseudo_random_valid_rows_seed_{VALID_ROWS_SEED}")


def test_differential_replay_is_bit_identical(oracle):
    grids = dict(zip(("rv24", "pressure"), synthetic_grids()))
    first = run_both_full(oracle, grids, case_id="replay_first")
    second = run_both_full(oracle, grids, case_id="replay_second")
    assert first.result_digest == second.result_digest == FROZEN_SYNTHETIC_RESULT_DIGEST


# ==========================================================================
# 4 -- low-level valid battery
# ==========================================================================


def test_differential_har_and_design_rows(oracle):
    grids = dict(zip(("rv24", "pressure"), synthetic_grids()))
    rows_o = oracle.build_causal_forecast_rows(rv24_by_day=grids["rv24"], pressure_by_day=grids["pressure"])
    rows_s = successor.build_causal_forecast_rows(rv24_by_day=grids["rv24"], pressure_by_day=grids["pressure"])
    for index in (0, 1, 200, 365, 608):
        row_o, row_s = rows_o[index], rows_s[index]
        assert oracle.har_features(row_o) == successor.har_features(row_s)
        assert oracle.m0_design_row(row_o) == successor.m0_design_row(row_s)
        assert oracle.m1_design_row(row_o) == successor.m1_design_row(row_s)
        assert oracle.target_value(row_o) == successor.target_value(row_s)
    lags = [Decimal(index) for index in range(1, 31)]
    row_o = make_row(oracle, datetime(2024, 10, 19, tzinfo=UTC), percentile=Fraction(37, 366), lags=lags)
    row_s = make_row(successor, datetime(2024, 10, 19, tzinfo=UTC), percentile=Fraction(37, 366), lags=lags)
    assert oracle.har_features(row_o) == successor.har_features(row_s)
    assert oracle.m1_design_row(row_o) == successor.m1_design_row(row_s)


def test_differential_exact_ols_fixtures(oracle):
    design_a = [(Fraction(1), Fraction(x1), Fraction(x2)) for x1, x2 in ((1, 0), (0, 1), (2, 3), (5, 1), (4, 4), (7, 2))]
    outcome_a = [Fraction(3 + 2 * x1 - x2) for x1, x2 in ((1, 0), (0, 1), (2, 3), (5, 1), (4, 4), (7, 2))]
    design_b = [(Fraction(1), Fraction(index), Fraction(index * index, 7)) for index in range(1, 12)]
    outcome_b = [Fraction(index * 3 + 1, 5) for index in range(1, 12)]
    design_c = [
        (Fraction(1), Fraction(index, 3), Fraction(index * index, 7), Fraction(index * index * index, 11))
        for index in range(1, 25)
    ]
    outcome_c = [Fraction(index * index + 3 * index - 5, 13) for index in range(1, 25)]
    for design, outcome in ((design_a, outcome_a), (design_b, outcome_b), (design_c, outcome_c)):
        assert oracle.solve_normal_equations_exact(design, outcome) == successor.solve_normal_equations_exact(design, outcome)
        assert oracle.fit_ordinary_least_squares(design, outcome) == successor.fit_ordinary_least_squares(design, outcome)


def test_differential_quantization_edges(oracle):
    values = [
        Fraction(1, 3),
        Fraction(1, 4),
        Fraction(-1, 7),
        Fraction(10**60 + 1, 3),
        Fraction(1, 10**60),
        Fraction(-10**40, 7),
        Fraction(0),
        Fraction(10**400),
    ]
    for value in values:
        assert oracle.quantize_exact(value) == successor.quantize_exact(value)
        assert oracle.report_decimal(value) == successor.report_decimal(value)


def test_differential_loss_floor_and_linear_forecast(oracle):
    errors = [Fraction(1), Fraction(-2), Fraction(3, 2), Fraction(-7, 5)]
    assert oracle.mean_squared_error(errors) == successor.mean_squared_error(errors)
    assert oracle.relative_mse_improvement(Fraction(4), Fraction(3)) == successor.relative_mse_improvement(Fraction(4), Fraction(3))
    for forecast in (Fraction(-1, 3), Fraction(0), Fraction(7, 9), Fraction(10**30, 3)):
        assert oracle.apply_nonnegative_floor(forecast) == successor.apply_nonnegative_floor(forecast)
    beta = (Fraction(3), Fraction(-2, 7), Fraction(11, 13))
    regressors = (Fraction(1, 5), Fraction(-9, 4), Fraction(22, 7))
    assert oracle.linear_forecast(beta, regressors) == successor.linear_forecast(beta, regressors)


def test_differential_clark_west_and_hac_fixtures(oracle):
    targets = [Fraction(3), Fraction(5), Fraction(-2, 7)]
    f0 = [Fraction(1), Fraction(4), Fraction(1, 3)]
    f1 = [Fraction(2), Fraction(9, 2), Fraction(-5, 6)]
    assert oracle.clark_west_adjusted_differences(targets=targets, forecasts_m0=f0, forecasts_m1=f1) == (
        successor.clark_west_adjusted_differences(targets=targets, forecasts_m0=f0, forecasts_m1=f1)
    )
    sequences = [
        [Fraction((index * 37) % 11 - 5, 3) for index in range(60)],
        [Fraction((-1) ** index) for index in range(12)],
        [Fraction(1), Fraction(-1)] * 20,
        [Fraction(index, 97) for index in range(6, 61)],
    ]
    for values in sequences:
        assert oracle.bartlett_newey_west_long_run_variance(values) == successor.bartlett_newey_west_long_run_variance(values)
    favouring = [Fraction(1, 100) + Fraction((index % 5) - 2, 10000) for index in range(60)]
    assert oracle.clark_west_statistic(favouring) == successor.clark_west_statistic(favouring)
    assert oracle.clark_west_statistic([-value for value in favouring]) == successor.clark_west_statistic(
        [-value for value in favouring]
    )


def test_differential_normal_tail_grid(oracle):
    for tenths in range(-90, 91):
        z = Decimal(tenths) / 10
        assert oracle.standard_normal_upper_tail(z) == successor.standard_normal_upper_tail(z), f"z={z}"
    for z in (Decimal(0), Decimal(-1000), Decimal(1000), successor.Z_CRITICAL_ONE_SIDED_5_PERCENT):
        assert oracle.standard_normal_upper_tail(z) == successor.standard_normal_upper_tail(z)


def test_differential_classification_grid(oracle):
    cases = [
        {"evaluation_origin_count": 244, "mse_m0": Fraction(2), "mse_m1": Fraction(1), "p_value": Decimal("0.05")},
        {"evaluation_origin_count": 244, "mse_m0": Fraction(2), "mse_m1": Fraction(1), "p_value": Decimal("0.050001")},
        {"evaluation_origin_count": 244, "mse_m0": Fraction(1), "mse_m1": Fraction(1), "p_value": Decimal("0.001")},
        {"evaluation_origin_count": 244, "mse_m0": Fraction(1), "mse_m1": Fraction(2), "p_value": Decimal("0.001")},
        {"evaluation_origin_count": 243, "mse_m0": Fraction(2), "mse_m1": Fraction(1), "p_value": Decimal("0.001")},
        {"evaluation_origin_count": 0, "mse_m0": Fraction(1), "mse_m1": Fraction(0), "p_value": Decimal("0.9")},
    ]
    for case in cases:
        assert oracle.classify(**case) == successor.classify(**case)


def test_differential_exact_coercion_fixtures(oracle):
    assert oracle._exact(Decimal("0.25"), label="probe") == successor._exact(Decimal("0.25"), label="probe")
    assert oracle._exact(Fraction(1, 4), label="probe") == successor._exact(Fraction(1, 4), label="probe")
    assert oracle._exact(Decimal("-1e-30"), label="probe") == successor._exact(Decimal("-1e-30"), label="probe")
    assert oracle.report_decimal(Decimal("1.23456789012345678901234567890123")) == successor.report_decimal(
        Decimal("1.23456789012345678901234567890123")
    )


# ==========================================================================
# 5 -- canonical low-level delegation under panel reorder / substitution
# ==========================================================================


def _funding_fixture(day):
    from test_jigsaw_funding_pressure_incremental_forecast_value_executor_v0 import funding_event

    return {
        symbol: [
            funding_event(symbol, day - timedelta(hours=32), "0.5"),
            funding_event(symbol, day - timedelta(hours=8), f"-0.{index + 1:04d}"),
        ]
        for index, symbol in enumerate(v2.PANEL)
    }


def _bars_fixture(day):
    from test_jigsaw_funding_pressure_incremental_forecast_value_executor_v0 import ohlcv_bar

    bars = {}
    for index, symbol in enumerate(v2.PANEL):
        series = []
        for hour in range(-2, 27):
            close = Decimal(100) + Decimal(hour * (index + 1)) / 1000
            series.append(ohlcv_bar(symbol, day + timedelta(hours=hour - 1), str(close)))
        bars[symbol] = series
    return bars


def test_differential_daily_pressure_and_rv24_delegation(oracle):
    day = datetime(2024, 3, 1, tzinfo=UTC)
    funding = _funding_fixture(day)
    bars = _bars_fixture(day)
    assert oracle.daily_funding_pressure(funding, day) == successor.daily_funding_pressure(funding, day)
    assert oracle.daily_rv24(bars, day) == successor.daily_rv24(bars, day)


def test_differential_panel_reorder_fails_closed_identically(oracle, monkeypatch):
    """The canonical V2 primitives refuse any non-canonical panel ordering;
    the differential requirement is identical fail-closed semantics."""
    day = datetime(2024, 3, 1, tzinfo=UTC)
    funding = _funding_fixture(day)
    reordered = list(v2.PANEL)
    reordered[0], reordered[1] = reordered[1], reordered[0]
    monkeypatch.setattr(oracle, "PANEL", tuple(reordered))
    monkeypatch.setattr(successor, "PANEL", tuple(reordered))
    assert_same_failure(
        lambda: oracle.daily_funding_pressure(funding, day),
        lambda: successor.daily_funding_pressure(funding, day),
        case_id="panel_reorder",
    )


def test_differential_panel_substitution_fails_closed_identically(oracle, monkeypatch):
    day = datetime(2024, 3, 1, tzinfo=UTC)
    funding = _funding_fixture(day)
    substituted = list(v2.PANEL)
    substituted[9] = "DOGEUSDT"
    funding["DOGEUSDT"] = funding["REEFUSDT"]
    monkeypatch.setattr(oracle, "PANEL", tuple(substituted))
    monkeypatch.setattr(successor, "PANEL", tuple(substituted))
    assert_same_failure(
        lambda: oracle.daily_funding_pressure(funding, day),
        lambda: successor.daily_funding_pressure(funding, day),
        case_id="panel_substitution",
    )


def test_differential_panel_substitution_without_events_fails_identically(oracle, monkeypatch):
    day = datetime(2024, 3, 1, tzinfo=UTC)
    funding = _funding_fixture(day)
    substituted = list(v2.PANEL)
    substituted[9] = "DOGEUSDT"
    monkeypatch.setattr(oracle, "PANEL", tuple(substituted))
    monkeypatch.setattr(successor, "PANEL", tuple(substituted))
    assert_same_failure(
        lambda: oracle.daily_funding_pressure(funding, day),
        lambda: successor.daily_funding_pressure(funding, day),
        case_id="panel_substitution_without_events",
    )


# ==========================================================================
# 6 -- invalid corpus: same failure class AND same fail-closed semantics
# ==========================================================================


def test_differential_unauthorized_execution_modes(oracle):
    grids = dict(zip(("rv24", "pressure"), synthetic_grids()))
    rows_o = oracle.build_causal_forecast_rows(rv24_by_day=grids["rv24"], pressure_by_day=grids["pressure"])
    rows_s = successor.build_causal_forecast_rows(rv24_by_day=grids["rv24"], pressure_by_day=grids["pressure"])
    for mode in ("REAL", "PRODUCTION", "REAL_EVIDENCE", "SCIENTIFIC_EXECUTION", "", None, "synthetic_validation", True, 0, object()):
        assert_same_failure(
            lambda m=mode: oracle.run_incremental_forecast_evaluation(rows_o, execution_mode=m),
            lambda m=mode: successor.run_incremental_forecast_evaluation(rows_s, execution_mode=m),
            case_id=f"unauthorized_mode_{mode!r}",
        )


def test_differential_temporal_contract_failures(oracle):
    grids = dict(zip(("rv24", "pressure"), synthetic_grids()))
    rows_o = list(oracle.build_causal_forecast_rows(rv24_by_day=grids["rv24"], pressure_by_day=grids["pressure"]))
    rows_s = list(successor.build_causal_forecast_rows(rv24_by_day=grids["rv24"], pressure_by_day=grids["pressure"]))

    swapped_o, swapped_s = list(rows_o), list(rows_s)
    swapped_o[10], swapped_o[11] = swapped_o[11], swapped_o[10]
    swapped_s[10], swapped_s[11] = swapped_s[11], swapped_s[10]
    assert_same_failure(
        lambda: oracle.validate_forecast_rows(swapped_o),
        lambda: successor.validate_forecast_rows(swapped_s),
        case_id="swapped_temporal_order",
    )

    bad_o, bad_s = rows_o[0], rows_s[0]
    tampered_o = list(rows_o)
    tampered_s = list(rows_s)
    tampered_o[0] = oracle.ForecastRow(
        origin=bad_o.origin,
        target_completion=oracle._stamp(oracle._utc(bad_o.origin) + timedelta(hours=23)),
        funding_percentile=bad_o.funding_percentile,
        rv24_target=bad_o.rv24_target,
        rv24_lags=bad_o.rv24_lags,
    )
    tampered_s[0] = successor.ForecastRow(
        origin=bad_s.origin,
        target_completion=successor._stamp(successor._utc(bad_s.origin) + timedelta(hours=23)),
        funding_percentile=bad_s.funding_percentile,
        rv24_target=bad_s.rv24_target,
        rv24_lags=bad_s.rv24_lags,
    )
    assert_same_failure(
        lambda: oracle.validate_forecast_rows(tampered_o),
        lambda: successor.validate_forecast_rows(tampered_s),
        case_id="target_completion_not_origin_plus_24h",
    )

    origin = oracle.FIRST_EVALUATION_ORIGIN
    short_o = [make_row(oracle, origin - timedelta(days=offset)) for offset in range(2, 12)]
    short_s = [make_row(successor, origin - timedelta(days=offset)) for offset in range(2, 12)]
    assert_same_failure(
        lambda: oracle.select_training_rows(short_o, origin),
        lambda: successor.select_training_rows(short_s, origin),
        case_id="training_below_frozen_minimum",
    )
    assert_same_failure(
        lambda: oracle.select_training_rows([make_row(oracle, origin)], origin),
        lambda: successor.select_training_rows([make_row(successor, origin)], origin),
        case_id="training_row_at_or_after_origin",
    )


def test_differential_input_integrity_failures(oracle):
    grids = dict(zip(("rv24", "pressure"), synthetic_grids()))
    rows_o = oracle.build_causal_forecast_rows(rv24_by_day=grids["rv24"], pressure_by_day=grids["pressure"])
    rows_s = successor.build_causal_forecast_rows(rv24_by_day=grids["rv24"], pressure_by_day=grids["pressure"])

    assert_same_failure(
        lambda: oracle.validate_forecast_rows(rows_o[:-1]),
        lambda: successor.validate_forecast_rows(rows_s[:-1]),
        case_id="missing_forecast_row",
    )
    extra_o = rows_o + (make_row(oracle, datetime(2025, 6, 20, tzinfo=UTC)),)
    extra_s = rows_s + (make_row(successor, datetime(2025, 6, 20, tzinfo=UTC)),)
    assert_same_failure(
        lambda: oracle.validate_forecast_rows(extra_o),
        lambda: successor.validate_forecast_rows(extra_s),
        case_id="extra_forecast_row",
    )
    assert_same_failure(
        lambda: oracle.validate_forecast_rows(rows_o + (rows_o[-1],)),
        lambda: successor.validate_forecast_rows(rows_s + (rows_s[-1],)),
        case_id="duplicate_forecast_row",
    )
    with_boundary_o = rows_o[:365] + (make_row(oracle, datetime(2024, 10, 18, tzinfo=UTC)),) + rows_o[365:]
    with_boundary_s = rows_s[:365] + (make_row(successor, datetime(2024, 10, 18, tzinfo=UTC)),) + rows_s[365:]
    assert_same_failure(
        lambda: oracle.validate_forecast_rows(with_boundary_o),
        lambda: successor.validate_forecast_rows(with_boundary_s),
        case_id="boundary_origin_reintroduced",
    )

    dropped_rv24 = dict(grids["rv24"])
    dropped_rv24.pop(successor._stamp(datetime(2024, 3, 3, tzinfo=UTC)))
    assert_same_failure(
        lambda: oracle.build_causal_forecast_rows(rv24_by_day=dropped_rv24, pressure_by_day=grids["pressure"]),
        lambda: successor.build_causal_forecast_rows(rv24_by_day=dropped_rv24, pressure_by_day=grids["pressure"]),
        case_id="missing_grid_observation",
    )
    extended = dict(grids["rv24"])
    extended[successor._stamp(datetime(2025, 6, 20, tzinfo=UTC))] = Decimal("0.01")
    assert_same_failure(
        lambda: oracle.build_causal_forecast_rows(rv24_by_day=extended, pressure_by_day=grids["pressure"]),
        lambda: successor.build_causal_forecast_rows(rv24_by_day=extended, pressure_by_day=grids["pressure"]),
        case_id="extra_grid_observation",
    )
    for bad in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), Decimal("-0.001"), 0.01, "0.01", None):
        tampered = dict(grids["rv24"])
        tampered[successor._stamp(datetime(2024, 5, 5, tzinfo=UTC))] = bad
        assert_same_failure(
            lambda b=bad: oracle.build_causal_forecast_rows(rv24_by_day=tampered, pressure_by_day=grids["pressure"]),
            lambda b=bad: successor.build_causal_forecast_rows(rv24_by_day=tampered, pressure_by_day=grids["pressure"]),
            case_id=f"bad_grid_value_{type(bad).__name__}",
        )

    def tampered_row(module, rows, index, **changes):
        base = rows[index]
        fields = {
            "origin": base.origin,
            "target_completion": base.target_completion,
            "funding_percentile": base.funding_percentile,
            "rv24_target": base.rv24_target,
            "rv24_lags": base.rv24_lags,
        }
        fields.update(changes)
        return module.ForecastRow(**fields)

    for index, changes in (
        (5, {"rv24_target": Decimal("NaN")}),
        (7, {"funding_percentile": Fraction(367, 366)}),
        (11, {"rv24_lags": tuple(Decimal("0.02") for _ in range(29))}),
        (13, {"rv24_target": Decimal("-0.01")}),
        (17, {"funding_percentile": Fraction(-1, 366)}),
    ):
        assert_same_failure(
            lambda i=index, c=changes: oracle.validate_forecast_rows(
                rows_o[:i] + (tampered_row(oracle, rows_o, i, **c),) + rows_o[i + 1:]
            ),
            lambda i=index, c=changes: successor.validate_forecast_rows(
                rows_s[:i] + (tampered_row(successor, rows_s, i, **c),) + rows_s[i + 1:]
            ),
            case_id=f"tampered_row_{index}",
        )

    assert_same_failure(
        lambda: oracle._exact(0.25, label="probe"),
        lambda: successor._exact(0.25, label="probe"),
        case_id="exact_refuses_float",
    )


def test_differential_contract_violation_failures(oracle):
    assert_same_failure(
        lambda: oracle.bartlett_newey_west_long_run_variance([Fraction(index) for index in range(40)], lag=4),
        lambda: successor.bartlett_newey_west_long_run_variance([Fraction(index) for index in range(40)], lag=4),
        case_id="hac_lag_selection",
    )
    assert_same_failure(
        lambda: oracle.classify(
            evaluation_origin_count=244, mse_m0=Fraction(2), mse_m1=Fraction(1),
            p_value=Decimal("0.01"), alpha=Decimal("0.10"),
        ),
        lambda: successor.classify(
            evaluation_origin_count=244, mse_m0=Fraction(2), mse_m1=Fraction(1),
            p_value=Decimal("0.01"), alpha=Decimal("0.10"),
        ),
        case_id="alpha_not_frozen",
    )
    assert_same_failure(lambda: oracle.mean_squared_error([]), lambda: successor.mean_squared_error([]), case_id="empty_mse")
    assert_same_failure(
        lambda: oracle.relative_mse_improvement(Fraction(0), Fraction(1)),
        lambda: successor.relative_mse_improvement(Fraction(0), Fraction(1)),
        case_id="relative_improvement_zero_baseline",
    )
    assert_same_failure(
        lambda: oracle.linear_forecast((Fraction(1),), (Fraction(1), Fraction(2))),
        lambda: successor.linear_forecast((Fraction(1),), (Fraction(1), Fraction(2))),
        case_id="linear_forecast_length_mismatch",
    )
    assert_same_failure(
        lambda: oracle.apply_nonnegative_floor(0.5),
        lambda: successor.apply_nonnegative_floor(0.5),
        case_id="floor_on_float",
    )
    assert_same_failure(
        lambda: oracle.quantize_exact(0.5), lambda: successor.quantize_exact(0.5), case_id="quantize_on_float"
    )
    assert_same_failure(
        lambda: oracle.solve_normal_equations_exact([(Fraction(1), 2.0)], [Fraction(1)]),
        lambda: successor.solve_normal_equations_exact([(Fraction(1), 2.0)], [Fraction(1)]),
        case_id="ols_float_entry",
    )
    assert_same_failure(
        lambda: oracle.solve_normal_equations_exact(
            [(Fraction(1), Fraction(2)), (Fraction(1),)], [Fraction(1), Fraction(2)]
        ),
        lambda: successor.solve_normal_equations_exact(
            [(Fraction(1), Fraction(2)), (Fraction(1),)], [Fraction(1), Fraction(2)]
        ),
        case_id="ols_ragged_design",
    )
    assert_same_failure(
        lambda: oracle.clark_west_adjusted_differences(targets=[Fraction(1)], forecasts_m0=[Fraction(1)], forecasts_m1=[]),
        lambda: successor.clark_west_adjusted_differences(targets=[Fraction(1)], forecasts_m0=[Fraction(1)], forecasts_m1=[]),
        case_id="clark_west_length_mismatch",
    )
    assert_same_failure(
        lambda: oracle.clark_west_adjusted_differences(targets=[], forecasts_m0=[], forecasts_m1=[]),
        lambda: successor.clark_west_adjusted_differences(targets=[], forecasts_m0=[], forecasts_m1=[]),
        case_id="clark_west_empty",
    )


def test_differential_rank_deficient_failures(oracle):
    duplicate = [(Fraction(1), Fraction(index), Fraction(index)) for index in range(1, 8)]
    outcome = [Fraction(index) for index in range(1, 8)]
    assert_same_failure(
        lambda: oracle.solve_normal_equations_exact(duplicate, outcome),
        lambda: successor.solve_normal_equations_exact(duplicate, outcome),
        case_id="rank_deficient_duplicate_column",
    )
    constant = [(Fraction(1), Fraction(4)) for _ in range(6)]
    assert_same_failure(
        lambda: oracle.solve_normal_equations_exact(constant, [Fraction(index) for index in range(6)]),
        lambda: successor.solve_normal_equations_exact(constant, [Fraction(index) for index in range(6)]),
        case_id="rank_deficient_constant_column",
    )
    assert_same_failure(
        lambda: oracle.solve_normal_equations_exact([(Fraction(1), Fraction(2))], [Fraction(1)]),
        lambda: successor.solve_normal_equations_exact([(Fraction(1), Fraction(2))], [Fraction(1)]),
        case_id="fewer_observations_than_regressors",
    )

    rv24, pressure = synthetic_grids()
    flat = {stamp: Decimal("0.0000500") for stamp in pressure}
    assert_same_failure(
        lambda: oracle.run_incremental_forecast_evaluation(
            oracle.build_causal_forecast_rows(rv24_by_day=rv24, pressure_by_day=flat), execution_mode=MODE
        ),
        lambda: successor.run_incremental_forecast_evaluation(
            successor.build_causal_forecast_rows(rv24_by_day=rv24, pressure_by_day=flat), execution_mode=MODE
        ),
        case_id="evaluation_rank_deficient_flat_pressure",
    )


def test_differential_numerical_contract_failures(oracle):
    assert_same_failure(
        lambda: oracle.clark_west_statistic([Fraction(3)] * 40),
        lambda: successor.clark_west_statistic([Fraction(3)] * 40),
        case_id="hac_variance_not_positive",
    )
    assert_same_failure(
        lambda: oracle.standard_normal_upper_tail(Decimal("NaN")),
        lambda: successor.standard_normal_upper_tail(Decimal("NaN")),
        case_id="p_value_nan",
    )
    assert_same_failure(
        lambda: oracle.standard_normal_upper_tail(1.0),
        lambda: successor.standard_normal_upper_tail(1.0),
        case_id="p_value_float",
    )


def test_differential_pseudo_random_malformed_rows_seed_20260821(oracle):
    """Deterministic malformed-row corpus from seed 20260821."""
    grids = dict(zip(("rv24", "pressure"), synthetic_grids(seed=MALFORMED_ROWS_SEED)))
    rows_o = list(oracle.build_causal_forecast_rows(rv24_by_day=grids["rv24"], pressure_by_day=grids["pressure"]))
    rows_s = list(successor.build_causal_forecast_rows(rv24_by_day=grids["rv24"], pressure_by_day=grids["pressure"]))
    assert len(rows_o) == len(rows_s)

    def corrupt(module, rows):
        corrupted = list(rows)
        for index in range(0, len(corrupted), 17):
            base = corrupted[index]
            corrupted[index] = module.ForecastRow(
                origin=base.origin,
                target_completion=base.target_completion,
                funding_percentile=base.funding_percentile,
                rv24_target=Decimal("NaN"),
                rv24_lags=base.rv24_lags,
            )
        for index in range(5, len(corrupted), 23):
            base = corrupted[index]
            if isinstance(corrupted[index].rv24_target, Decimal) and corrupted[index].rv24_target.is_finite():
                corrupted[index] = module.ForecastRow(
                    origin=base.origin,
                    target_completion=base.target_completion,
                    funding_percentile=Fraction(367, 366),
                    rv24_target=base.rv24_target,
                    rv24_lags=base.rv24_lags,
                )
        for index in range(11, len(corrupted), 41):
            base = corrupted[index]
            if base.funding_percentile == Fraction(367, 366):
                continue
            corrupted[index] = module.ForecastRow(
                origin=base.origin,
                target_completion=base.target_completion,
                funding_percentile=base.funding_percentile,
                rv24_target=base.rv24_target,
                rv24_lags=base.rv24_lags[:29],
            )
        return corrupted

    assert_same_failure(
        lambda: oracle.run_incremental_forecast_evaluation(corrupt(oracle, rows_o), execution_mode=MODE),
        lambda: successor.run_incremental_forecast_evaluation(corrupt(successor, rows_s), execution_mode=MODE),
        case_id=f"pseudo_random_malformed_rows_seed_{MALFORMED_ROWS_SEED}",
    )

    # malformed grids from the same seed: deterministic bad days
    draw_days = [datetime(2024, 2, 1 + offset, tzinfo=UTC) for offset in range(0, 29, 7)]
    for day in draw_days:
        bad_grid = dict(grids["rv24"])
        bad_grid[successor._stamp(day)] = Decimal("Infinity")
        assert_same_failure(
            lambda g=bad_grid: oracle.build_causal_forecast_rows(rv24_by_day=g, pressure_by_day=grids["pressure"]),
            lambda g=bad_grid: successor.build_causal_forecast_rows(rv24_by_day=g, pressure_by_day=grids["pressure"]),
            case_id=f"malformed_grid_{successor._stamp(day)}",
        )


# ==========================================================================
# 7 -- hostile Decimal contexts (>= 24)
# ==========================================================================


def test_differential_hostile_decimal_contexts_core_battery(oracle):
    """All hostile contexts: identical core outputs under identical contexts."""
    differences = [Fraction(1, 100) + Fraction((index % 5) - 2, 10000) for index in range(60)]
    for index, context in enumerate(HOSTILE_CONTEXTS):
        with localcontext(context):
            quantized_o = oracle.quantize_exact(Fraction(1, 3))
            quantized_s = successor.quantize_exact(Fraction(1, 3))
            statistic_o = oracle.clark_west_statistic(differences)
            statistic_s = successor.clark_west_statistic(differences)
            tail_o = [oracle.standard_normal_upper_tail(Decimal(t) / 10) for t in range(-20, 21)]
            tail_s = [successor.standard_normal_upper_tail(Decimal(t) / 10) for t in range(-20, 21)]
            report_o = oracle.report_decimal(Fraction(-22, 7))
            report_s = successor.report_decimal(Fraction(-22, 7))
        assert quantized_o == quantized_s, f"hostile context {index}"
        assert statistic_o == statistic_s, f"hostile context {index}"
        assert tail_o == tail_s, f"hostile context {index}"
        assert report_o == report_s, f"hostile context {index}"


def test_differential_hostile_decimal_contexts_full_evaluation(oracle):
    """Full evaluations under every hostile context: identical digests."""
    grids = dict(zip(("rv24", "pressure"), synthetic_grids()))
    rows_o = oracle.build_causal_forecast_rows(rv24_by_day=grids["rv24"], pressure_by_day=grids["pressure"])
    rows_s = successor.build_causal_forecast_rows(rv24_by_day=grids["rv24"], pressure_by_day=grids["pressure"])
    for index, context in enumerate(HOSTILE_CONTEXTS):
        with localcontext(context):
            result_o = oracle.run_incremental_forecast_evaluation(rows_o, execution_mode=MODE)
            result_s = successor.run_incremental_forecast_evaluation(rows_s, execution_mode=MODE)
        assert result_o.result_digest == result_s.result_digest, f"hostile context {index}"
        assert result_s.result_digest == FROZEN_SYNTHETIC_RESULT_DIGEST, f"hostile context {index}"


# ==========================================================================
# 8 -- corpus registry integrity
# ==========================================================================


def test_corpus_registry_covers_the_required_classes_and_minima():
    registry = corpus_case_registry()
    kinds = [case["kind"] for case in registry]
    assert kinds.count("valid") >= 20
    assert kinds.count("invalid") >= 40
    assert len(HOSTILE_CONTEXTS) >= 24
    for failure_class in (
        "UnauthorizedExecutionError",
        "TemporalContractError",
        "InputIntegrityError",
        "ContractViolationError",
        "RankDeficientDesignError",
        "NumericalContractError",
    ):
        assert any(case["failure_class"] == failure_class for case in registry), failure_class
    assert any(str(VALID_ROWS_SEED) in case["case_id"] for case in registry)
    assert any(str(MALFORMED_ROWS_SEED) in case["case_id"] for case in registry)
    assert len({case["case_id"] for case in registry}) == len(registry), "duplicate case ids"
