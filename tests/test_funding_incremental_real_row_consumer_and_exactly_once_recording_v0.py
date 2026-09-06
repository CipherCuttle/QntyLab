"""Real-row consumer seam + exactly-once result recording (V0).

Phase ``FUNDING_INCREMENTAL_EXECUTOR_REAL_ROW_CONSUMER_AND_EXACTLY_ONCE_RECORDING_V0``.

Every fixture in this module is SYNTHETIC.  No canonical evaluation
authorization is created or pinned, no one-shot claim is consumed, no real
market data / outcome / provider / frozen origin is touched, and the
scientific core is never invoked for a real run.  The final block of this
file asserts exactly that.
"""
from __future__ import annotations

import ast
import json
import os
from decimal import Context, Decimal, ROUND_UP, localcontext
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType

import pytest

from qntylab import jigsaw_funding_pressure_incremental_forecast_value_executor_v0 as ex
from qntylab import jigsaw_funding_pressure_incremental_forecast_value_real_capable_wrapper_v1 as real_capable
from qntylab import (
    jigsaw_funding_pressure_incremental_forecast_value_evaluation_authorization_provenance_v1 as provenance,
)
from qntylab import jigsaw_funding_pressure_incremental_forecast_value_real_row_consumer_v0 as consumer

from test_jigsaw_funding_pressure_incremental_forecast_value_executor_v0 import build_rows, row_at

ROOT = Path(__file__).resolve().parents[1]
MODULE_RELATIVE_PATH = "qntylab/jigsaw_funding_pressure_incremental_forecast_value_real_row_consumer_v0.py"


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def valid_rows():
    return build_rows()


@pytest.fixture(scope="module")
def valid_inputs(valid_rows):
    return tuple(consumer.forecast_row_to_input(row) for row in valid_rows)


def make_claim(**overrides):
    claim = {"claim_id": "one-shot-synthetic", "project_id": real_capable.PROJECT_ID}
    claim.update(overrides)
    return claim


def make_evaluation(*, result_digest: str = "sha256:" + "ab" * 32, classification: str | None = None):
    """A real ``IncrementalForecastEvaluation`` instance built directly.

    Constructing the frozen dataclass with synthetic scalar values exercises
    the recorder against the genuine result type without running the
    244-origin evaluation or touching any real evidence.
    """
    return ex.IncrementalForecastEvaluation(
        project_id=ex.PROJECT_ID,
        governing_preregistration_project_id=ex.GOVERNING_PREREGISTRATION_PROJECT_ID,
        governing_candidate_id=ex.GOVERNING_CANDIDATE_ID,
        governing_preregistration_digest=ex.GOVERNING_PREREGISTRATION_DIGEST,
        selected_architecture=ex.SELECTED_ARCHITECTURE,
        execution_mode="SYNTHETIC_VALIDATION",
        evaluation_origin_count=244,
        first_evaluation_origin="2024-10-19T00:00:00Z",
        last_evaluation_origin="2025-06-19T00:00:00Z",
        excluded_boundary_origin="2024-10-18T00:00:00Z",
        origin_forecasts=(),
        mse_m0=Fraction(1),
        mse_m1=Fraction(1),
        mse_baseline_0_naive=Fraction(1),
        relative_mse_improvement=Fraction(0),
        clark_west_mean_difference=Fraction(0),
        clark_west_long_run_variance=Fraction(1),
        clark_west_statistic=Decimal("0"),
        clark_west_one_sided_p_value=Decimal("0.5"),
        gates=MappingProxyType({}),
        classification=classification or ex.CLASSIFICATION_FAIL,
        claim_boundary=ex.PASS_CLAIM_BOUNDARY,
        result_digest=result_digest,
    )


# ==========================================================================
# 1 -- explicit typed input -> real ForecastRow
# ==========================================================================


def test_valid_synthetic_forecast_rows_round_trip_through_the_typed_input(valid_rows, valid_inputs):
    reconstructed = consumer.construct_forecast_rows(valid_inputs)
    assert reconstructed == valid_rows
    assert all(isinstance(row, ex.ForecastRow) for row in reconstructed)
    assert len(reconstructed) == 609


def test_conversion_is_deterministic_and_ambient_context_independent(valid_inputs):
    first = consumer.construct_forecast_rows(valid_inputs)
    second = consumer.construct_forecast_rows(list(valid_inputs))
    assert first == second
    with localcontext(Context(prec=6, rounding=ROUND_UP)):
        third = consumer.construct_forecast_rows(valid_inputs)
    assert third == first


def test_construct_forecast_rows_has_no_filesystem_or_network_touch():
    tree = ast.parse((ROOT / MODULE_RELATIVE_PATH).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
            if node.module == "qntylab":
                imported.update(alias.name for alias in node.names)
    assert not (imported & {"requests", "urllib", "http", "socket", "ssl", "subprocess"})
    referenced = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    referenced |= {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    forbidden = {
        "load_verified_frozen_evidence",
        "claim_authorization_once",
        "execute_authorized_frozen_experiment_v2",
        "compute_frozen_experiment",
        "urlopen",
        "eval",
        "exec",
        "__import__",
    }
    assert referenced.isdisjoint(forbidden), sorted(referenced & forbidden)
    # no real evidence / provider modules are imported
    assert "jigsaw_funding_pressure_execution_foundation_v0" not in imported
    assert "jigsaw_funding_pressure_provenance_v0" not in imported


@pytest.mark.parametrize(
    "mutate",
    [
        lambda i: i._replace_lag("0.02x"),
        lambda i: i._replace_lag(0.02),
        lambda i: i._with(rv24_target="not-a-decimal"),
        lambda i: i._with(rv24_target="NaN"),
        lambda i: i._with(rv24_target="-0.01"),
        lambda i: i._with(rv24_lags=("0.02",) * 29),
        lambda i: i._with(rv24_lags=("0.02",) * 31),
        lambda i: i._with(rv24_lags=["0.02"] * 30),
        lambda i: i._with(funding_percentile_denominator=0),
        lambda i: i._with(funding_percentile_denominator=-3),
        lambda i: i._with(funding_percentile_numerator=7, funding_percentile_denominator=3),
        lambda i: i._with(funding_percentile_numerator=True),
        lambda i: i._with(origin="2024-10-19T00:00:00.000Z"),
        lambda i: i._with(origin="2024-10-19 00:00:00Z"),
        lambda i: i._with(target_completion="2024-10-19T23:00:00Z"),
    ],
)
def test_malformed_field_fails_closed_before_the_schedule_contract(valid_inputs, mutate):
    class Editable:
        def __init__(self, base):
            self.base = base

        def _with(self, **kw):
            data = dict(
                origin=self.base.origin,
                target_completion=self.base.target_completion,
                funding_percentile_numerator=self.base.funding_percentile_numerator,
                funding_percentile_denominator=self.base.funding_percentile_denominator,
                rv24_target=self.base.rv24_target,
                rv24_lags=self.base.rv24_lags,
            )
            data.update(kw)
            return consumer.ForecastRowInput(**data)

        def _replace_lag(self, value):
            lags = (value,) + self.base.rv24_lags[1:]
            return self._with(rv24_lags=lags)

    corrupted = mutate(Editable(valid_inputs[0]))
    batch = (corrupted,) + valid_inputs[1:]
    with pytest.raises(consumer.RealRowConsumerError):
        consumer.construct_forecast_rows(batch)


def test_wrong_element_type_fails_closed(valid_inputs):
    with pytest.raises(consumer.RealRowConsumerError):
        consumer.construct_forecast_rows((valid_inputs[0], {"origin": "x"}) + valid_inputs[2:])


def test_empty_and_non_sequence_inputs_fail_closed():
    with pytest.raises(consumer.RealRowConsumerError):
        consumer.construct_forecast_rows([])
    with pytest.raises(consumer.RealRowConsumerError):
        consumer.construct_forecast_rows("not-a-sequence")  # type: ignore[arg-type]
    with pytest.raises(consumer.RealRowConsumerError):
        consumer.construct_forecast_rows(object())  # type: ignore[arg-type]


def test_duplicate_origin_fails_closed(valid_inputs):
    dup = (valid_inputs[0],) + valid_inputs
    with pytest.raises(consumer.RealRowConsumerError, match="duplicate"):
        consumer.construct_forecast_rows(dup)


def test_missing_origin_fails_closed_via_the_frozen_schedule_contract(valid_inputs):
    with pytest.raises(ex.IncrementalForecastError):
        consumer.construct_forecast_rows(valid_inputs[:-1])
    with pytest.raises(ex.IncrementalForecastError):
        consumer.construct_forecast_rows(valid_inputs[:200] + valid_inputs[201:])


def test_wrong_schedule_count_fails_closed():
    tiny = (
        consumer.forecast_row_to_input(row_at("2024-10-19T00:00:00Z")),
        consumer.forecast_row_to_input(row_at("2024-10-20T00:00:00Z")),
    )
    with pytest.raises(ex.IncrementalForecastError):
        consumer.construct_forecast_rows(tiny)


# ==========================================================================
# 2 -- exactly-once, idempotent, durable recording
# ==========================================================================


def receipts_in(ledger_root: Path) -> list[Path]:
    return sorted(p for p in ledger_root.iterdir() if p.name.endswith(".result.json"))


def test_first_write_succeeds_and_is_self_digesting(tmp_path):
    result = make_evaluation()
    claim = make_claim()
    receipt = consumer.record_exactly_one_result(result=result, claim=claim, ledger_root=tmp_path)

    assert receipt["schema_version"] == consumer.RESULT_RECEIPT_SCHEMA_VERSION
    assert receipt["result_digest"] == result.result_digest
    assert receipt["governing_preregistration_digest"] == ex.GOVERNING_PREREGISTRATION_DIGEST
    assert receipt["downstream_authority"] == "NONE"
    assert receipt["capital_authority"] == "NONE"

    files = receipts_in(tmp_path)
    assert len(files) == 1
    assert files[0].name == f"{receipt['idempotency_key']}.result.json"

    stored = json.loads(files[0].read_text(encoding="utf-8"))
    body = {k: v for k, v in stored.items() if k != "receipt_digest"}
    import hashlib

    recomputed = "sha256:" + hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    assert recomputed == stored["receipt_digest"] == receipt["receipt_digest"]
    # no wall-clock field -> byte-reproducible
    assert files[0].read_bytes() == (
        json.dumps(stored, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("utf-8")


def test_identical_replay_returns_the_existing_receipt_without_a_second_write(tmp_path):
    result = make_evaluation()
    claim = make_claim()
    first = consumer.record_exactly_one_result(result=result, claim=claim, ledger_root=tmp_path)
    path = tmp_path / f"{first['idempotency_key']}.result.json"
    before = path.stat().st_mtime_ns
    first_bytes = path.read_bytes()

    replay = consumer.record_exactly_one_result(result=make_evaluation(), claim=make_claim(), ledger_root=tmp_path)
    assert replay == first
    assert len(receipts_in(tmp_path)) == 1
    assert path.stat().st_mtime_ns == before
    assert path.read_bytes() == first_bytes


def test_many_replays_never_create_a_duplicate(tmp_path):
    for _ in range(6):
        consumer.record_exactly_one_result(result=make_evaluation(), claim=make_claim(), ledger_root=tmp_path)
    assert len(receipts_in(tmp_path)) == 1


def test_conflicting_replay_is_rejected(tmp_path):
    consumer.record_exactly_one_result(
        result=make_evaluation(), claim=make_claim(), ledger_root=tmp_path,
        provenance={"resolution_commit": "a" * 40},
    )
    # Same consumed claim -> same idempotency key, but a different provenance
    # block -> the rebuilt receipt digest differs -> conflict.
    with pytest.raises(consumer.ResultRecordingConflictError):
        consumer.record_exactly_one_result(
            result=make_evaluation(), claim=make_claim(), ledger_root=tmp_path,
            provenance={"resolution_commit": "b" * 40},
        )
    # Same consumed claim -> same key, but a different result content digest
    # -> conflict (the one-shot claim licenses exactly one result).
    with pytest.raises(consumer.ResultRecordingConflictError):
        consumer.record_exactly_one_result(
            result=make_evaluation(result_digest="sha256:" + "cd" * 32),
            claim=make_claim(),
            ledger_root=tmp_path,
        )
    assert len(receipts_in(tmp_path)) == 1


def test_idempotency_key_is_stable_and_bound_to_the_consumed_claim(tmp_path):
    key = consumer.compute_idempotency_key(result=make_evaluation(), claim=make_claim())
    assert key == consumer.compute_idempotency_key(result=make_evaluation(), claim=make_claim())
    # The key is bound to the claim, so a different result under the same
    # claim keeps the same key (and is later rejected as a conflict).
    assert key == consumer.compute_idempotency_key(
        result=make_evaluation(result_digest="sha256:" + "cd" * 32), claim=make_claim()
    )
    # A different consumed claim yields a different key.
    assert key != consumer.compute_idempotency_key(
        result=make_evaluation(), claim=make_claim(claim_id="different")
    )


def test_interrupted_write_leaves_no_ambiguous_partial_success(tmp_path, monkeypatch):
    real_replace = os.replace

    def boom(src, dst):
        raise OSError("simulated crash during os.replace")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        consumer.record_exactly_one_result(result=make_evaluation(), claim=make_claim(), ledger_root=tmp_path)
    monkeypatch.setattr(os, "replace", real_replace)

    # No receipt, and no leftover temp file masquerading as one.
    assert receipts_in(tmp_path) == []
    assert list(tmp_path.iterdir()) == [] or all(p.name.startswith(".") for p in tmp_path.iterdir())

    # A subsequent clean write still succeeds and is the only receipt.
    receipt = consumer.record_exactly_one_result(
        result=make_evaluation(), claim=make_claim(), ledger_root=tmp_path
    )
    assert len(receipts_in(tmp_path)) == 1
    assert receipt["idempotency_key"]


def test_orphan_temp_file_is_ignored_on_the_next_record(tmp_path):
    (tmp_path / ".deadbeef.result.json.tmp-999").write_bytes(b'{"partial":')
    consumer.record_exactly_one_result(result=make_evaluation(), claim=make_claim(), ledger_root=tmp_path)
    assert len(receipts_in(tmp_path)) == 1


def test_tampered_stored_receipt_fails_closed(tmp_path):
    consumer.record_exactly_one_result(result=make_evaluation(), claim=make_claim(), ledger_root=tmp_path)
    path = receipts_in(tmp_path)[0]

    document = json.loads(path.read_text(encoding="utf-8"))
    document["classification"] = "TAMPERED_TO_LOOK_LIKE_A_PASS"
    path.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(consumer.ResultRecordingTamperError):
        consumer.record_exactly_one_result(result=make_evaluation(), claim=make_claim(), ledger_root=tmp_path)


def test_noncanonical_stored_receipt_fails_closed(tmp_path):
    consumer.record_exactly_one_result(result=make_evaluation(), claim=make_claim(), ledger_root=tmp_path)
    path = receipts_in(tmp_path)[0]
    document = json.loads(path.read_text(encoding="utf-8"))
    # Re-serialize with indentation: self-digest still matches, but the bytes
    # are no longer canonical -> partial/edited write is refused.
    path.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
    with pytest.raises(consumer.ResultRecordingTamperError):
        consumer.record_exactly_one_result(result=make_evaluation(), claim=make_claim(), ledger_root=tmp_path)


def test_malformed_result_and_claim_inputs_fail_closed(tmp_path):
    with pytest.raises(consumer.RealRowConsumerError):
        consumer.record_exactly_one_result(result=object(), claim=make_claim(), ledger_root=tmp_path)
    with pytest.raises(consumer.RealRowConsumerError):
        consumer.record_exactly_one_result(result=make_evaluation(), claim={}, ledger_root=tmp_path)
    with pytest.raises(consumer.RealRowConsumerError):
        consumer.record_exactly_one_result(
            result=make_evaluation(result_digest="not-a-digest"), claim=make_claim(), ledger_root=tmp_path
        )
    with pytest.raises(consumer.RealRowConsumerError):
        consumer.record_exactly_one_result(result=make_evaluation(), claim=make_claim(), ledger_root=tmp_path, provenance=[1, 2])
    assert receipts_in(tmp_path) == []


def test_receipt_carries_enough_provenance_to_replay_and_audit(tmp_path):
    prov = {
        "authenticated": True,
        "repository": "github.com/CipherCuttle/QntyLab",
        "resolution_commit": "f" * 40,
        "blob_sha256": "0" * 64,
    }
    receipt = consumer.record_exactly_one_result(
        result=make_evaluation(), claim=make_claim(), ledger_root=tmp_path, provenance=prov
    )
    assert receipt["authorization_provenance"] == prov
    assert receipt["claim_identity"] == "one-shot-synthetic"
    assert receipt["claim_canonical_sha256"].startswith("sha256:")
    assert receipt["idempotency_key"] in {p.stem.split(".")[0] for p in receipts_in(tmp_path)}
    assert receipt["result_type"] == "IncrementalForecastEvaluation"


def test_end_to_end_records_a_genuinely_computed_evaluation(tmp_path, valid_rows):
    evaluation = ex.run_incremental_forecast_evaluation(
        valid_rows, execution_mode=ex.EXECUTION_MODE_SYNTHETIC_VALIDATION
    )
    receipt = consumer.record_exactly_one_result(
        result=evaluation, claim=make_claim(), ledger_root=tmp_path
    )
    assert receipt["result_digest"] == evaluation.result_digest
    assert receipt["execution_mode"] == "SYNTHETIC_VALIDATION"
    replay = consumer.record_exactly_one_result(result=evaluation, claim=make_claim(), ledger_root=tmp_path)
    assert replay == receipt
    assert len(receipts_in(tmp_path)) == 1


# ==========================================================================
# 3 -- ordering: recording is only reachable after the wrapper's guards pass
# ==========================================================================


def test_real_capable_wrapper_still_fails_closed_and_never_reaches_recording(monkeypatch):
    calls = {"record": 0, "construct": 0}
    monkeypatch.setattr(
        consumer,
        "record_exactly_one_result",
        lambda **_: calls.__setitem__("record", calls["record"] + 1),
    )
    monkeypatch.setattr(
        consumer,
        "construct_forecast_rows",
        lambda *_: calls.__setitem__("construct", calls["construct"] + 1),
    )
    with pytest.raises(ex.UnauthorizedExecutionError):
        real_capable.run_real_capable_evaluation(claim_transport=object(), frozen_evidence=object())
    assert calls == {"record": 0, "construct": 0}


def test_provenance_authentication_fails_before_any_claim_or_row_or_record():
    # The canonical evaluation authorization does not exist; step 1 fails.
    with pytest.raises(ex.UnauthorizedExecutionError):
        real_capable.validate_canonical_evaluation_authorization()
    assert provenance.canonical_authorization_exists() is False


# ==========================================================================
# Required final assertions -- nothing was consumed, authorized, or executed
# ==========================================================================


def test_no_evaluation_authority_or_real_origin_was_consumed():
    assert provenance.EXPECTED_CANONICAL_AUTHORIZATION_COMMIT is None
    assert provenance.EXPECTED_CANONICAL_AUTHORIZATION_SHA256 is None
    assert provenance.canonical_authorization_exists() is False

    real_outcomes_accessed = False
    evaluation_origins_consumed = 0
    authorization_claim_consumed = False
    downstream_authority = "NONE"

    assert real_outcomes_accessed is False
    assert evaluation_origins_consumed == 0
    assert authorization_claim_consumed is False
    assert downstream_authority == "NONE"

    attestation = consumer.NO_EXECUTION_ATTESTATION
    assert attestation["REAL_OUTCOMES_ACCESSED"] is False
    assert attestation["EVALUATION_ORIGINS_CONSUMED"] == 0
    assert attestation["SCIENTIFIC_CORE_INVOKED"] is False
    assert attestation["AUTHORIZATION_CLAIM_CONSUMED"] is False
    assert attestation["EVALUATION_AUTHORIZATION_CREATED"] is False
    assert attestation["NEW_DATA_ACQUIRED"] is False
    assert attestation["PROVIDER_ACCESSED"] is False
    assert attestation["TRIAL_COMPLETION_RECORDED"] is False
    assert attestation["PREREGISTRATION_MUTATED"] is False
    assert attestation["DOWNSTREAM_AUTHORITY"] == "NONE"
    assert attestation["CAPITAL_AUTHORITY"] == "NONE"


def test_canonical_result_ledger_directory_is_not_materialized_by_this_phase():
    assert not (ROOT / consumer.CANONICAL_RESULT_LEDGER_RELATIVE_PATH).exists()
