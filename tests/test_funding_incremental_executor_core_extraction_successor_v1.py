"""Successor unit tests and manifest bindings for the core extraction V1 phase.

Phase ``FUNDING_INCREMENTAL_EXECUTOR_CORE_EXTRACTION_AND_SUCCESSOR_IMPLEMENTATION_V1``.

Covers: exactly ONE active shared scientific core, the synthetic wrapper,
the real-capable wrapper's claim-before-outcome fail-closed envelope, and
both implementation_v1 manifests.  Every fixture is SYNTHETIC; no real
evidence is loaded and no evaluation origin is consumed.
"""
from __future__ import annotations

import ast
import hashlib
import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from qntylab import jigsaw_funding_pressure_incremental_forecast_value_core_v1 as core
from qntylab import jigsaw_funding_pressure_incremental_forecast_value_executor_v0 as executor
from qntylab import jigsaw_funding_pressure_incremental_forecast_value_real_capable_wrapper_v1 as real_capable
from qntylab import jigsaw_funding_pressure_incremental_forecast_value_synthetic_wrapper_v1 as synthetic_wrapper

from test_jigsaw_funding_pressure_incremental_forecast_value_executor_v0 import build_rows
from test_funding_incremental_executor_core_extraction_differential_v1 import (
    corpus_case_registry,
    corpus_digest,
)

ROOT = Path(__file__).resolve().parents[1]
IMPL_V1_DIR = ROOT / "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/implementation_v1"
IMPLEMENTATION_MANIFEST = json.loads((IMPL_V1_DIR / "implementation_manifest.json").read_text(encoding="utf-8"))
DIFFERENTIAL_MANIFEST = json.loads((IMPL_V1_DIR / "differential_corpus_manifest.json").read_text(encoding="utf-8"))

HISTORICAL_SOURCE_SHA256 = "b894d4d9316bed6f8c4f7171b32692aff7b1f0eb32abd686a33fdb38425a7490"
FROZEN_SYNTHETIC_RESULT_DIGEST = "sha256:1fca55ebdbe5c4d5b835cb65f87930755d231449c924eae912b522bd04b53ea2"
CANONICAL_RESULT_SCHEMA_SHA256 = "0eb5029002fe472035023b9d73b4d852cf1a3f18a2693ed3454e5167cca2871f"

CORE_MATH_FUNCTIONS = {
    "har_features",
    "m0_design_row",
    "m1_design_row",
    "target_value",
    "quantize_exact",
    "solve_normal_equations_exact",
    "fit_ordinary_least_squares",
    "linear_forecast",
    "apply_nonnegative_floor",
    "mean_squared_error",
    "relative_mse_improvement",
    "clark_west_adjusted_differences",
    "bartlett_newey_west_long_run_variance",
    "clark_west_statistic",
    "standard_normal_upper_tail",
    "classify",
    "report_decimal",
}


def canonical_bytes(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def file_sha256(relative_path: str) -> str:
    return hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()


# ==========================================================================
# 1 -- exactly ONE active shared scientific core
# ==========================================================================


def test_core_module_defines_every_math_function_verbatim_owner():
    tree = ast.parse(
        (ROOT / "qntylab/jigsaw_funding_pressure_incremental_forecast_value_core_v1.py").read_text(encoding="utf-8")
    )
    defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    missing = CORE_MATH_FUNCTIONS - defined
    assert not missing, f"core module is missing math functions: {sorted(missing)}"


def test_executor_no_longer_defines_the_math_functions_it_imports():
    """ACTIVE_SCIENTIFIC_CORE_COUNT = 1: the executor is a mechanical consumer."""
    tree = ast.parse((ROOT / executor.MODULE_RELATIVE_PATH).read_text(encoding="utf-8"))
    defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    duplicated = CORE_MATH_FUNCTIONS & defined
    assert not duplicated, f"executor redefines core math: {sorted(duplicated)}"
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("core_v1"):
            imported.update(alias.name for alias in node.names)
    assert CORE_MATH_FUNCTIONS <= imported, f"executor does not import from the core: {sorted(CORE_MATH_FUNCTIONS - imported)}"


def test_no_other_funding_incremental_module_redefines_the_core_math():
    """The anti-duplication rule scopes to the funding incremental successor
    tree: no active module of this experiment family may restate the math."""
    family_prefix = "jigsaw_funding_pressure_incremental_forecast_value"
    for path in sorted((ROOT / "qntylab").glob(f"*{family_prefix}*.py")):
        if path.name == "jigsaw_funding_pressure_incremental_forecast_value_core_v1.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        duplicated = CORE_MATH_FUNCTIONS & defined
        assert not duplicated, f"{path.name} redefines core math: {sorted(duplicated)}"


def test_core_identity_is_bound_in_the_implementation_manifest():
    assert IMPLEMENTATION_MANIFEST["shared_core"]["path"] == (
        "qntylab/jigsaw_funding_pressure_incremental_forecast_value_core_v1.py"
    )
    assert IMPLEMENTATION_MANIFEST["shared_core"]["source_sha256"] == file_sha256(
        "qntylab/jigsaw_funding_pressure_incremental_forecast_value_core_v1.py"
    )
    assert IMPLEMENTATION_MANIFEST["shared_core"]["active_shared_scientific_core_count"] == 1
    assert IMPLEMENTATION_MANIFEST["shared_core"]["mechanical_verbatim_extraction"] is True


# ==========================================================================
# 2 -- SYNTHETIC_VALIDATION wrapper
# ==========================================================================


def test_synthetic_wrapper_delegates_to_the_guarded_shared_core():
    rows = build_rows()
    direct = executor.run_incremental_forecast_evaluation(
        rows, execution_mode=executor.EXECUTION_MODE_SYNTHETIC_VALIDATION
    )
    via_wrapper = synthetic_wrapper.run_synthetic_validation_evaluation(
        rows, execution_mode=executor.EXECUTION_MODE_SYNTHETIC_VALIDATION
    )
    assert via_wrapper.result_digest == direct.result_digest == FROZEN_SYNTHETIC_RESULT_DIGEST
    assert via_wrapper == direct


@pytest.mark.parametrize("mode", ["REAL", "PRODUCTION", None, "", "synthetic_validation", 0, True])
def test_synthetic_wrapper_refuses_every_non_synthetic_mode(mode):
    from pytest import raises

    with raises(executor.UnauthorizedExecutionError):
        synthetic_wrapper.run_synthetic_validation_evaluation(build_rows(), execution_mode=mode)


def test_synthetic_wrapper_attestation_is_synthetic_only_and_negative():
    attestation = dict(synthetic_wrapper.SYNTHETIC_QUALIFICATION_ATTESTATION)
    assert attestation["SYNTHETIC_ROWS_ONLY"] is True
    assert attestation["REAL_ROWS_ACCEPTED"] is False
    assert attestation["REAL_OUTCOMES_ACCESSED"] is False
    assert attestation["SCIENTIFIC_EXECUTION_PERFORMED"] is False
    assert attestation["EVALUATION_ORIGINS_CONSUMED"] == 0
    assert attestation["SCIENTIFIC_RESULT_RECORDED"] is False
    assert attestation["SHARED_CORE_INVOCATION_ONLY"] is True
    assert attestation["LOCAL_MATH_DUPLICATED"] is False
    assert attestation["DOWNSTREAM_AUTHORITY"] == "NONE"
    assert attestation["CAPITAL_AUTHORITY"] == "NONE"


# ==========================================================================
# 3 -- REAL_CAPABLE wrapper: claim-before-outcome, fail closed
# ==========================================================================


def test_real_capable_wrapper_fails_closed_without_canonical_authorization():
    """The canonical evaluation authorization does not exist yet."""
    assert not (ROOT / real_capable.CANONICAL_EVALUATION_AUTHORIZATION_RELATIVE_PATH).exists()
    with pytest.raises(executor.UnauthorizedExecutionError):
        real_capable.run_real_capable_evaluation()


def test_real_capable_wrapper_claim_failure_means_zero_rows_and_zero_core_invocations(monkeypatch):
    """CLAIM FAILURE => zero real ForecastRows, zero scientific-core calls."""
    calls = {"rows": 0, "core": 0, "claim": 0, "evidence": 0}

    def fail_validate(authorization_path=None):
        raise executor.UnauthorizedExecutionError("authorization absent (test envelope)")

    def spy_claim(authorization, claim_transport):
        calls["claim"] += 1
        raise AssertionError("claim must never be consumed when validation fails")

    def spy_evidence(authorization, frozen_evidence):
        calls["evidence"] += 1
        raise AssertionError("evidence must never be touched when validation fails")

    def spy_core(rows, authorization):
        calls["core"] += 1
        raise AssertionError("the shared scientific core must never be invoked on claim failure")

    monkeypatch.setattr(real_capable, "validate_canonical_evaluation_authorization", fail_validate)
    monkeypatch.setattr(real_capable, "_consume_irreversible_one_shot_claim", spy_claim)
    monkeypatch.setattr(real_capable, "_authenticate_frozen_evidence", spy_evidence)
    monkeypatch.setattr(real_capable, "_invoke_successor_shared_core", spy_core)
    with pytest.raises(executor.UnauthorizedExecutionError):
        real_capable.run_real_capable_evaluation(
            claim_transport=object(), frozen_evidence=object()
        )
    assert calls == {"rows": 0, "core": 0, "claim": 0, "evidence": 0}


def test_real_capable_wrapper_enforces_the_six_step_order(monkeypatch):
    order = []
    fake_authorization = {
        "artifact_type": real_capable.REQUIRED_AUTHORIZATION_ARTIFACT_TYPE,
        "state": real_capable.REQUIRED_AUTHORIZATION_STATE,
        "scientific_execution_authorized": True,
        "governing_preregistration_digest": executor.GOVERNING_PREREGISTRATION_DIGEST,
        "real_capable_wrapper_project_id": real_capable.PROJECT_ID,
        "execution_mode": "REAL_SCIENTIFIC_EXECUTION",
    }

    class FakeTransport:
        def claim_authorization_once(self, *, project_id, authorization):
            order.append("claim")
            return {"claim_id": "one-shot", "project_id": project_id}

    class FakeEvidence:
        def authenticate(self, *, authorization):
            order.append("evidence")
            return {"authenticated": True}

        def build_real_forecast_rows(self, *, authorization):
            order.append("rows")
            # A minimal synthetic stand-in row: the shared-core invocation
            # itself is mocked in this test, so no scientific computation
            # and no real outcome is ever touched.
            synthetic_row = executor.ForecastRow(
                origin="2024-10-19T00:00:00Z",
                target_completion="2024-10-20T00:00:00Z",
                funding_percentile=Fraction(1, 2),
                rv24_target=Decimal("0.01"),
                rv24_lags=tuple(Decimal("0.02") for _ in range(30)),
            )
            return (synthetic_row,)

    monkeypatch.setattr(
        real_capable,
        "validate_canonical_evaluation_authorization",
        lambda authorization_path=None: order.append("validate") or fake_authorization,
    )
    monkeypatch.setattr(
        real_capable,
        "_invoke_successor_shared_core",
        lambda rows, authorization: order.append("core") or "RESULT",
    )
    monkeypatch.setattr(
        real_capable,
        "_record_exactly_one_result",
        lambda result, claim: order.append("record") or result,
    )
    result = real_capable.run_real_capable_evaluation(
        claim_transport=FakeTransport(), frozen_evidence=FakeEvidence()
    )
    assert order == ["validate", "claim", "evidence", "rows", "core", "record"]
    assert result == "RESULT"


def test_real_capable_wrapper_rejects_malformed_authorizations(tmp_path):
    base = {
        "artifact_type": real_capable.REQUIRED_AUTHORIZATION_ARTIFACT_TYPE,
        "state": real_capable.REQUIRED_AUTHORIZATION_STATE,
        "scientific_execution_authorized": True,
        "governing_preregistration_digest": executor.GOVERNING_PREREGISTRATION_DIGEST,
        "real_capable_wrapper_project_id": real_capable.PROJECT_ID,
    }
    bad_documents = [
        {},
        {**base, "state": "OPEN"},
        {**base, "scientific_execution_authorized": False},
        {**base, "governing_preregistration_digest": "0" * 64},
        {**base, "real_capable_wrapper_project_id": "OTHER"},
        {**base, "artifact_type": "WRONG"},
    ]
    for index, document in enumerate(bad_documents):
        path = tmp_path / f"authorization_{index}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(executor.UnauthorizedExecutionError):
            real_capable.validate_canonical_evaluation_authorization(path)
    absent = tmp_path / "absent.json"
    with pytest.raises(executor.UnauthorizedExecutionError):
        real_capable.validate_canonical_evaluation_authorization(absent)


def test_real_capable_wrapper_phase_attestation_is_all_negative():
    attestation = dict(real_capable.REAL_CAPABLE_PHASE_ATTESTATION)
    assert attestation["REAL_ROWS_CONSTRUCTED"] == 0
    assert attestation["REAL_OUTCOMES_ACCESSED"] is False
    assert attestation["SCIENTIFIC_CORE_INVOCATIONS"] == 0
    assert attestation["SCIENTIFIC_EXECUTION_PERFORMED"] is False
    assert attestation["EVALUATION_ORIGINS_CONSUMED"] == 0
    assert attestation["SCIENTIFIC_RESULT_RECORDED"] is False
    assert attestation["TRIAL_COMPLETION_RECORDED"] is False
    assert attestation["AUTHORIZATION_CLAIM_CONSUMED"] is False
    assert attestation["POST_CLAIM_CRASH_REPLAY_AUTHORIZED"] is False
    assert attestation["CANONICAL_EVALUATION_AUTHORIZATION_EXISTS"] is False
    assert attestation["DOWNSTREAM_AUTHORITY"] == "NONE"
    assert attestation["CAPITAL_AUTHORITY"] == "NONE"


# ==========================================================================
# 4 -- implementation_manifest.json bindings
# ==========================================================================


def test_implementation_manifest_bindings_are_exact():
    manifest = IMPLEMENTATION_MANIFEST
    assert manifest["preregistration_digest"] == "d7ec718ab14e73d2aea24749a22caa2921fd81b8a336e2f2eaffb30ae1e992ef"
    assert manifest["preregistration_file_sha256"] == (
        "42b96afae80e55611bcd9786169050520525fbc5534b9f94c72ed867380ba9cf"
    )
    assert manifest["preregistration_status"] == "PREREGISTERED_NOT_EXECUTED"
    assert manifest["historical_oracle_commit"] == "f6f12994d65c3dfeaf7839de560e58ad99547c62"
    assert manifest["historical_source_sha256"] == HISTORICAL_SOURCE_SHA256
    assert manifest["result_schema"]["schema_sha256"] == CANONICAL_RESULT_SCHEMA_SHA256
    assert manifest["result_schema"]["result_type"] == "IncrementalForecastEvaluation"
    assert manifest["frozen_synthetic_result_digest"] == FROZEN_SYNTHETIC_RESULT_DIGEST


def test_implementation_manifest_binds_the_new_successor_digest():
    manifest = IMPLEMENTATION_MANIFEST
    actual = file_sha256(manifest["successor_source_path"])
    assert manifest["successor_source_sha256"] == actual
    assert actual != HISTORICAL_SOURCE_SHA256
    assert manifest["successor_sha_differs_from_historical_sha"] is True


def test_implementation_manifest_is_canonically_serialized_and_deterministic():
    path = IMPL_V1_DIR / "implementation_manifest.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert path.read_bytes() == canonical_bytes(document)


def test_implementation_manifest_firewall_is_all_negative():
    firewall = IMPLEMENTATION_MANIFEST["outcome_firewall"]
    assert firewall["real_outcome_access"] is False
    assert firewall["scientific_execution"] is False
    assert firewall["evaluation_origins_consumed"] == 0
    assert firewall["new_data_acquisition"] is False
    assert firewall["scientific_result_created"] is False
    assert firewall["trial_completion_recorded"] is False
    assert firewall["order_flow_modified"] is False
    assert firewall["jh01_modified"] is False
    assert firewall["jh01_ledger_read"] is False
    for authority in ("router_authority", "qnty_authority", "trading_authority", "capital_authority"):
        assert firewall[authority] == "NONE", authority


# ==========================================================================
# 5 -- differential_corpus_manifest.json bindings
# ==========================================================================


def test_differential_corpus_manifest_bindings_are_exact():
    manifest = DIFFERENTIAL_MANIFEST
    assert manifest["historical_oracle_commit"] == "f6f12994d65c3dfeaf7839de560e58ad99547c62"
    assert manifest["historical_oracle_source_sha256"] == HISTORICAL_SOURCE_SHA256
    assert manifest["successor_source_sha256"] == file_sha256(manifest["successor_source_path"])
    assert manifest["successor_manifest_sha256"] == hashlib.sha256(
        (IMPL_V1_DIR / "implementation_manifest.json").read_bytes()
    ).hexdigest()
    assert manifest["canonical_result_schema_sha256"] == CANONICAL_RESULT_SCHEMA_SHA256
    assert manifest["frozen_synthetic_result_digest"] == FROZEN_SYNTHETIC_RESULT_DIGEST
    assert manifest["generator_seeds"] == {"valid_forecast_rows": 20260820, "malformed_forecast_rows": 20260821}
    assert manifest["hostile_decimal_contexts"] >= 24
    assert manifest["required_differential_runner_path"] == (
        "tests/test_funding_incremental_executor_core_extraction_differential_v1.py"
    )
    assert manifest["required_existing_fixture_path"] == (
        "tests/test_jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py"
    )
    assert manifest["required_frozen_fixture_path"].endswith("implementation_v0/synthetic_validation.json")


def test_differential_corpus_manifest_corpus_digest_matches_the_runner_registry():
    assert DIFFERENTIAL_MANIFEST["corpus_digest"] == corpus_digest()
    registry = corpus_case_registry()
    counts = DIFFERENTIAL_MANIFEST["corpus_case_counts"]
    assert counts["total"] == len(registry)
    assert counts["valid"] == sum(1 for case in registry if case["kind"] == "valid")
    assert counts["invalid"] == sum(1 for case in registry if case["kind"] == "invalid")


def test_differential_corpus_manifest_is_canonically_serialized_and_deterministic():
    path = IMPL_V1_DIR / "differential_corpus_manifest.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert path.read_bytes() == canonical_bytes(document)
