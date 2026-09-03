"""Offline verification for the one authorized funding consumer successor.

All rows in this file are deterministic synthetic fixtures.  The tests never
load evidence, access outcomes from disk, call a provider, consume a claim, or
consume an evaluation origin.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import tomllib
from decimal import Context, Decimal, ROUND_DOWN, localcontext
from pathlib import Path

import pytest

from qntylab import jigsaw_funding_pressure_incremental_forecast_value_consumer_seam_successor_v0 as seam
from qntylab import jigsaw_funding_pressure_incremental_forecast_value_executor_v0 as executor
from test_jigsaw_funding_pressure_incremental_forecast_value_executor_v0 import build_rows


ROOT = Path(__file__).resolve().parents[1]
FROZEN_RESULT_DIGEST = "sha256:1fca55ebdbe5c4d5b835cb65f87930755d231449c924eae912b522bd04b53ea2"
FROZEN_PREREG_SHA256 = "42b96afae80e55611bcd9786169050520525fbc5534b9f94c72ed867380ba9cf"
FROZEN_EXECUTOR_SHA256 = "1ffcfeb959cfc547fcda96384c1c8f58b3f5cbc174c5d535324480ede312e8c6"
SUCCESSOR_PROJECT_ID = "FUNDING_INCREMENTAL_REAL_EXECUTION_CONSUMER_SEAM_SUCCESSOR_IMPLEMENTATION_V0"
SUCCESSOR_ARTIFACT_ROOT = ROOT / "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/consumer_seam_successor_v0"


@pytest.fixture(autouse=True)
def isolated_ephemeral_record_store():
    with seam._RECORD_LOCK:
        seam._RECORDS.clear()
    yield
    with seam._RECORD_LOCK:
        seam._RECORDS.clear()


def _batch(seed: int = 20240101) -> seam.ForecastRowBatch:
    return seam.ForecastRowBatch.from_offline_synthetic_rows(build_rows(seed=seed))


def _envelope(batch: seam.ForecastRowBatch) -> seam.AuthorityBoundInputEnvelope:
    return seam.AuthorityBoundInputEnvelope.for_offline_synthetic_batch(batch)


def _successor_project_record() -> dict:
    registry = tomllib.loads((ROOT / "docs/state/projects.toml").read_text(encoding="utf-8"))
    matches = [record for record in registry["project"] if record["project_id"] == SUCCESSOR_PROJECT_ID]
    assert len(matches) == 1
    return matches[0]


def test_successor_is_implemented_but_waiting_for_its_single_terminal_review():
    record = _successor_project_record()
    authoritative_artifacts = record["authoritative_artifacts"]

    assert record["state"] == "IMPLEMENTATION_IN_REVIEW"
    assert record["implementation_count"] == 1
    assert record["implementation_completed"] is True
    assert record["hostile_review_count"] == 0
    assert "hostile_review_verdict" not in record
    assert "hostile_review_critical" not in record
    assert "hostile_review_high" not in record
    assert record["targeted_rereview_used"] is False
    assert "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/consumer_seam_successor_v0/hostile_review.md" not in authoritative_artifacts
    assert "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/consumer_seam_successor_v0/closure.json" not in authoritative_artifacts
    assert "exactly one terminal hostile review" in record["next_action"]

    assert (SUCCESSOR_ARTIFACT_ROOT / "implementation_manifest.json").is_file()
    assert not (SUCCESSOR_ARTIFACT_ROOT / "hostile_review.md").exists()
    assert not (SUCCESSOR_ARTIFACT_ROOT / "closure.json").exists()
    assert (ROOT / "qntylab/jigsaw_funding_pressure_incremental_forecast_value_consumer_seam_successor_v0.py").is_file()

    for field in (
        "implementation_authorized",
        "scientific_evaluation_authorized",
        "scientific_execution_authorized",
        "data_access_authorized",
        "real_data_access_authorized",
        "market_data_access_authorized",
        "outcome_access_authorized",
        "provider_access_authorized",
        "claim_access_authorized",
        "synthetic_ordering_fixture_authorizes_execution",
        "real_outcome_access_performed",
        "scientific_execution_performed",
        "new_data_acquisition_performed",
        "scientific_result_created",
        "trial_completion_recorded",
    ):
        assert record[field] is False, field
    for field in ("router_authority", "qnty_authority", "trading_authority", "capital_authority", "downstream_authority"):
        assert record[field] == "NONE", field


def test_typed_authority_boundary_preserves_frozen_result_and_ordering():
    batch = _batch()
    envelope = _envelope(batch)
    direct = executor.run_incremental_forecast_evaluation(
        batch.rows, execution_mode=executor.EXECUTION_MODE_SYNTHETIC_VALIDATION
    )
    first = seam.consume_forecast_batch(envelope, batch)

    assert first.evaluation == direct
    assert first.evaluation.result_digest == FROZEN_RESULT_DIGEST
    assert first.replayed is False
    assert first.ordering == seam.ORDERING_EVENTS
    assert first.record_identity == "|".join(
        (seam.PHASE_ID, envelope.authority_receipt_digest, batch.input_batch_identity)
    )

    replay = seam.consume_forecast_batch(envelope, batch)
    assert replay.replayed is True
    assert replay.record_identity == first.record_identity
    assert replay.canonical_record == first.canonical_record
    assert replay.evaluation == first.evaluation


def test_envelope_is_factory_only_and_binds_all_required_identities():
    batch = _batch(999)
    envelope = _envelope(batch)
    assert dataclasses.fields(envelope)
    assert envelope.successor_phase_id == seam.PHASE_ID
    assert envelope.authority_scope == seam.AUTHORITY_SCOPE
    assert envelope.input_batch_identity == batch.input_batch_identity
    assert envelope.authority_receipt_digest.startswith("sha256:")
    assert envelope.authorizes_execution is False
    assert envelope.real_data_access is False
    assert envelope.outcome_access is False
    assert envelope.provider_access is False
    assert envelope.evaluation_origin_access is False
    assert not hasattr(envelope, "execution_mode")

    with pytest.raises(TypeError):
        seam.AuthorityBoundInputEnvelope()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        seam.ForecastRowBatch()  # type: ignore[call-arg]


@pytest.mark.parametrize("bad_envelope", [None, {}, {"successor_phase_id": seam.PHASE_ID}])
def test_raw_or_untyped_authority_inputs_fail_closed(bad_envelope):
    batch = _batch(1001)
    with pytest.raises(seam.AuthorityBoundaryError):
        seam.consume_forecast_batch(bad_envelope, batch)


def test_raw_or_untyped_forecast_inputs_fail_closed_after_authority_fixture():
    batch = _batch(1002)
    envelope = _envelope(batch)
    with pytest.raises(executor.InputIntegrityError):
        seam.consume_forecast_batch(envelope, {"rows": batch.rows})


def test_invalid_typed_rows_preserve_frozen_failure_class_and_message():
    rows = build_rows(seed=1003)
    broken = list(rows)
    broken[4] = dataclasses.replace(broken[4], rv24_lags=broken[4].rv24_lags[:-1])
    batch = seam.ForecastRowBatch.from_offline_synthetic_rows(tuple(broken))
    envelope = _envelope(batch)

    with pytest.raises(executor.InputIntegrityError) as frozen_error:
        executor.run_incremental_forecast_evaluation(
            batch.rows, execution_mode=executor.EXECUTION_MODE_SYNTHETIC_VALIDATION
        )
    with pytest.raises(executor.InputIntegrityError) as successor_error:
        seam.consume_forecast_batch(envelope, batch)
    assert str(successor_error.value) == str(frozen_error.value)


def test_invalid_numeric_typed_rows_reach_the_frozen_failure_gate():
    rows = list(build_rows(seed=10031))
    rows[3] = dataclasses.replace(rows[3], funding_percentile=0.5)  # type: ignore[arg-type]
    batch = seam.ForecastRowBatch.from_offline_synthetic_rows(tuple(rows))
    envelope = _envelope(batch)
    with pytest.raises(executor.InputIntegrityError) as frozen_error:
        executor.run_incremental_forecast_evaluation(
            batch.rows, execution_mode=executor.EXECUTION_MODE_SYNTHETIC_VALIDATION
        )
    with pytest.raises(executor.InputIntegrityError) as successor_error:
        seam.consume_forecast_batch(envelope, batch)
    assert str(successor_error.value) == str(frozen_error.value)


def test_same_record_identity_with_different_content_fails_closed():
    rows = list(build_rows(seed=1004))
    first_batch = seam.ForecastRowBatch.from_offline_synthetic_rows(tuple(rows))
    envelope = _envelope(first_batch)
    first = seam.consume_forecast_batch(envelope, first_batch)

    rows[0] = dataclasses.replace(rows[0], rv24_target=rows[0].rv24_target + Decimal("0.000001"))
    conflicting_batch = seam.ForecastRowBatch.from_offline_synthetic_rows(tuple(rows))
    assert conflicting_batch.input_batch_identity == first_batch.input_batch_identity
    assert conflicting_batch.content_digest != first_batch.content_digest
    with pytest.raises(seam.ExactlyOnceConflictError):
        seam.consume_forecast_batch(envelope, conflicting_batch)

    replay = seam.consume_forecast_batch(envelope, first_batch)
    assert replay.record_identity == first.record_identity
    assert replay.canonical_record == first.canonical_record


def test_batch_and_record_serialization_are_deterministic_without_wall_clock():
    first_batch = _batch(1005)
    second_batch = _batch(1005)
    first_envelope = _envelope(first_batch)
    second_envelope = _envelope(second_batch)
    assert first_batch.input_batch_identity == second_batch.input_batch_identity
    assert first_batch.content_digest == second_batch.content_digest
    assert first_envelope.authority_receipt_digest == second_envelope.authority_receipt_digest

    first = seam.consume_forecast_batch(first_envelope, first_batch)
    second = seam.consume_forecast_batch(second_envelope, second_batch)
    assert second.replayed is True
    assert first.record_identity == second.record_identity
    assert first.canonical_record == second.canonical_record
    assert b"2026-" not in first.canonical_record


def test_hostile_decimal_context_does_not_change_successor_result():
    batch = _batch(1006)
    envelope = _envelope(batch)
    hostile = Context(prec=1, rounding=ROUND_DOWN, Emin=-999999, Emax=999999)
    with localcontext(hostile):
        successor = seam.consume_forecast_batch(envelope, batch)
        frozen = executor.run_incremental_forecast_evaluation(
            batch.rows, execution_mode=executor.EXECUTION_MODE_SYNTHETIC_VALIDATION
        )
    assert successor.evaluation == frozen


def test_successor_has_one_public_boundary_and_no_private_executor_bypass():
    source = (ROOT / "qntylab/jigsaw_funding_pressure_incremental_forecast_value_consumer_seam_successor_v0.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    public_functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }
    assert public_functions == {"consume_forecast_batch"}
    names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }
    attributes = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }
    assert "_assemble_incremental_forecast_evaluation" not in names | attributes
    assert not {"requests", "urllib", "acquire", "provider", "claim_authorization_once"} & (names | attributes)


def test_offline_attestation_is_all_negative():
    assert dict(seam.OFFLINE_PHASE_ATTESTATION) == {
        "phase_id": seam.PHASE_ID,
        "project_id": seam.PROJECT_ID,
        "authority_scope": seam.AUTHORITY_SCOPE,
        "real_data_accessed": False,
        "outcomes_accessed": False,
        "providers_accessed": False,
        "real_claims_accessed_or_consumed": False,
        "evaluation_origins_consumed": 0,
        "persistent_authorization_claim_created": False,
        "scientific_execution_performed": False,
        "router_authority": "NONE",
        "qnty_authority": "NONE",
        "trading_authority": "NONE",
        "capital_authority": "NONE",
    }


def test_frozen_source_and_preregistration_bindings_are_unchanged():
    manifest = json.loads(
        (ROOT / seam.FROZEN_IMPLEMENTATION_MANIFEST_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    assert hashlib.sha256((ROOT / executor.MODULE_RELATIVE_PATH).read_bytes()).hexdigest() == FROZEN_EXECUTOR_SHA256
    assert hashlib.sha256(
        (ROOT / "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/preregistration.json").read_bytes()
    ).hexdigest() == FROZEN_PREREG_SHA256
    assert manifest["frozen_synthetic_result_digest"] == FROZEN_RESULT_DIGEST


def test_successor_manifest_binds_its_source_and_authority_artifacts():
    manifest_path = ROOT / seam.IMPLEMENTATION_MANIFEST_RELATIVE_PATH
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["phase_id"] == seam.PHASE_ID
    assert manifest["project_id"] == seam.PROJECT_ID
    assert manifest["source_path"] == "qntylab/jigsaw_funding_pressure_incremental_forecast_value_consumer_seam_successor_v0.py"
    assert manifest["source_sha256"] == hashlib.sha256(
        (ROOT / manifest["source_path"]).read_bytes()
    ).hexdigest()
    assert manifest["ordering"]["events"] == list(seam.ORDERING_EVENTS)
    assert manifest["exactly_once"]["wall_clock_dependency"] is False
    assert manifest["offline_firewall"]["scientific_execution_performed"] is False
    assert manifest["verification"]["single_hostile_review_required"] is True
