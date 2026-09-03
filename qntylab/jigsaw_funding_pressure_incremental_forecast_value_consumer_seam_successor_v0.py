"""Offline successor consumer seam for the frozen funding-incremental V0.

This module is the implementation-only successor authorized by
``FUNDING_INCREMENTAL_REAL_EXECUTION_CONSUMER_SEAM_SUCCESSOR_IMPLEMENTATION_V0``.
It is deliberately an offline seam: its only authority scope is synthetic
ordering instrumentation, its only input constructor accepts in-memory
``ForecastRow`` values, and its exactly-once ledger is process-local and
non-persistent.

The frozen incremental executor remains the semantic oracle.  The public
boundary below calls its public entrypoint with the fixed synthetic-validation
mode; it never calls a private executor entrypoint, reads evidence, invokes a
provider, consumes a claim, or accesses an evaluation origin.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from threading import RLock
from types import MappingProxyType

from qntylab import jigsaw_funding_pressure_incremental_forecast_value_executor_v0 as executor


PHASE_ID = "FUNDING_INCREMENTAL_REAL_EXECUTION_CONSUMER_SEAM_SUCCESSOR_IMPLEMENTATION_V0"
PROJECT_ID = "FUNDING_INCREMENTAL_REAL_EXECUTION_CONSUMER_SEAM_SUCCESSOR_IMPLEMENTATION_V0"
AUTHORITY_SCOPE = "OFFLINE_SYNTHETIC_ORDERING_INSTRUMENTATION_ONLY"
CONTRACT_SCHEMA_VERSION = "funding-incremental-real-execution-consumer-seam-successor-v0"
IMPLEMENTATION_MANIFEST_RELATIVE_PATH = (
    "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/"
    "consumer_seam_successor_v0/implementation_manifest.json"
)
FROZEN_IMPLEMENTATION_MANIFEST_RELATIVE_PATH = (
    "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/implementation_v1/"
    "implementation_manifest.json"
)

AUTHORITY_ACCEPTED = "AUTHORITY_ACCEPTED"
EPHEMERAL_SYNTHETIC_ORDERING_FIXTURE_ACCEPTED = "EPHEMERAL_SYNTHETIC_ORDERING_FIXTURE_ACCEPTED"
INPUT_INTERPRETATION = "INPUT_INTERPRETATION"
OUTCOME_INTERPRETATION = "OUTCOME_INTERPRETATION"
RESULT_RECORD = "RESULT_RECORD"
ORDERING_EVENTS = (
    AUTHORITY_ACCEPTED,
    EPHEMERAL_SYNTHETIC_ORDERING_FIXTURE_ACCEPTED,
    INPUT_INTERPRETATION,
    OUTCOME_INTERPRETATION,
    RESULT_RECORD,
)


class ConsumerSeamError(executor.IncrementalForecastError):
    """Base class for fail-closed successor-boundary errors."""


class AuthorityBoundaryError(ConsumerSeamError):
    """Raised when an envelope is not the validated offline authority type."""


class ExactlyOnceConflictError(ConsumerSeamError):
    """Raised when one record identity is presented with different content."""


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _fraction(value: Fraction) -> dict[str, int]:
    if isinstance(value, Fraction):
        return {"numerator": value.numerator, "denominator": value.denominator}
    return {"invalid_type": type(value).__module__ + "." + type(value).__qualname__}


def _decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise executor.NumericalContractError("successor serialization refuses a non-finite Decimal")
    return str(value)


def _batch_decimal(value: object) -> object:
    """Serialize without interpreting invalid fields before the frozen gate."""
    if isinstance(value, Decimal):
        return str(value)
    return {"invalid_type": type(value).__module__ + "." + type(value).__qualname__}


def _identity_scalar(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    return {"invalid_type": type(value).__module__ + "." + type(value).__qualname__}


def _row_payload(row: executor.ForecastRow, *, include_values: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "origin": _identity_scalar(row.origin),
        "target_completion": _identity_scalar(row.target_completion),
    }
    if include_values:
        lags = row.rv24_lags if isinstance(row.rv24_lags, (tuple, list)) else ()
        payload.update(
            {
                "funding_percentile": _fraction(row.funding_percentile),
                "rv24_target": _batch_decimal(row.rv24_target),
                "rv24_lags": [_batch_decimal(value) for value in lags],
            }
        )
    return payload


def _batch_content_payload(rows: Sequence[executor.ForecastRow]) -> dict[str, object]:
    return {
        "schema_version": "forecast-row-batch-content-v0",
        "rows": [_row_payload(row, include_values=True) for row in rows],
    }


def _batch_identity_payload(rows: Sequence[executor.ForecastRow]) -> dict[str, object]:
    """Identity is structural; content is separately checked for conflicts."""
    return {
        "schema_version": "forecast-row-batch-identity-v0",
        "rows": [_row_payload(row, include_values=False) for row in rows],
    }


@dataclass(frozen=True, slots=True)
class FrozenContractIdentity:
    executor_source_path: str
    executor_source_sha256: str
    shared_core_path: str
    shared_core_source_sha256: str
    preregistration_project_id: str
    preregistration_digest: str
    preregistration_file_sha256: str
    result_type: str
    result_schema_sha256: str


def _verified_frozen_contract_identity() -> FrozenContractIdentity:
    """Verify the frozen successor bindings before an envelope can be made."""
    root = _repository_root()
    manifest_path = root / FROZEN_IMPLEMENTATION_MANIFEST_RELATIVE_PATH
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise AuthorityBoundaryError("frozen implementation manifest is unavailable or malformed") from exc

    executor_path = root / executor.MODULE_RELATIVE_PATH
    core_path = root / manifest["shared_core"]["path"]
    prereg_path = root / "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/preregistration.json"
    try:
        executor_sha256 = hashlib.sha256(executor_path.read_bytes()).hexdigest()
        core_sha256 = hashlib.sha256(core_path.read_bytes()).hexdigest()
        prereg_sha256 = hashlib.sha256(prereg_path.read_bytes()).hexdigest()
    except (OSError, KeyError, TypeError) as exc:
        raise AuthorityBoundaryError("frozen contract bytes are unavailable") from exc

    if executor_sha256 != manifest["successor_source_sha256"]:
        raise AuthorityBoundaryError("frozen executor source binding mismatch")
    if core_sha256 != manifest["shared_core"]["source_sha256"]:
        raise AuthorityBoundaryError("shared scientific core source binding mismatch")
    if prereg_sha256 != manifest["preregistration_file_sha256"]:
        raise AuthorityBoundaryError("frozen preregistration source binding mismatch")

    return FrozenContractIdentity(
        executor_source_path=manifest["successor_source_path"],
        executor_source_sha256=executor_sha256,
        shared_core_path=manifest["shared_core"]["path"],
        shared_core_source_sha256=core_sha256,
        preregistration_project_id=executor.GOVERNING_PREREGISTRATION_PROJECT_ID,
        preregistration_digest=manifest["preregistration_digest"],
        preregistration_file_sha256=prereg_sha256,
        result_type=manifest["result_schema"]["result_type"],
        result_schema_sha256=manifest["result_schema"]["schema_sha256"],
    )


@dataclass(frozen=True, slots=True, init=False)
class ForecastRowBatch:
    """Typed, immutable batch with deterministic identity and content digest."""

    rows: tuple[executor.ForecastRow, ...]
    input_batch_identity: str
    content_digest: str
    synthetic_only: bool

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("ForecastRowBatch must be created with from_offline_synthetic_rows")

    @classmethod
    def from_offline_synthetic_rows(cls, rows: Sequence[executor.ForecastRow]) -> ForecastRowBatch:
        if isinstance(rows, (str, bytes, bytearray, Mapping)) or not isinstance(rows, Sequence):
            raise executor.InputIntegrityError("successor forecast batch must be a typed sequence of ForecastRow")
        materialized = tuple(rows)
        if not all(type(row) is executor.ForecastRow for row in materialized):
            raise executor.InputIntegrityError("successor forecast batch contains an untyped or foreign row")
        input_batch_identity = _digest(_batch_identity_payload(materialized))
        content_digest = _digest(_batch_content_payload(materialized))
        instance = object.__new__(cls)
        object.__setattr__(instance, "rows", materialized)
        object.__setattr__(instance, "input_batch_identity", input_batch_identity)
        object.__setattr__(instance, "content_digest", content_digest)
        object.__setattr__(instance, "synthetic_only", True)
        return instance


@dataclass(frozen=True, slots=True, init=False)
class AuthorityBoundInputEnvelope:
    """Factory-created authority binding; there is no caller-selected mode."""

    successor_phase_id: str
    authority_scope: str
    authority_receipt_digest: str
    frozen_contract_identity: FrozenContractIdentity
    input_batch_identity: str
    authorizes_execution: bool
    real_data_access: bool
    outcome_access: bool
    provider_access: bool
    evaluation_origin_access: bool

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("AuthorityBoundInputEnvelope must be created with for_offline_synthetic_batch")

    @classmethod
    def for_offline_synthetic_batch(cls, batch: ForecastRowBatch) -> AuthorityBoundInputEnvelope:
        if type(batch) is not ForecastRowBatch:
            raise AuthorityBoundaryError("authority envelope requires a typed ForecastRowBatch")
        contract = _verified_frozen_contract_identity()
        receipt_payload = _receipt_payload(contract, batch.input_batch_identity)
        instance = object.__new__(cls)
        object.__setattr__(instance, "successor_phase_id", PHASE_ID)
        object.__setattr__(instance, "authority_scope", AUTHORITY_SCOPE)
        object.__setattr__(instance, "authority_receipt_digest", _digest(receipt_payload))
        object.__setattr__(instance, "frozen_contract_identity", contract)
        object.__setattr__(instance, "input_batch_identity", batch.input_batch_identity)
        object.__setattr__(instance, "authorizes_execution", False)
        object.__setattr__(instance, "real_data_access", False)
        object.__setattr__(instance, "outcome_access", False)
        object.__setattr__(instance, "provider_access", False)
        object.__setattr__(instance, "evaluation_origin_access", False)
        return instance


def _receipt_payload(contract: FrozenContractIdentity, input_batch_identity: str) -> dict[str, object]:
    return {
        "receipt_type": "EPHEMERAL_SYNTHETIC_ORDERING_AUTHORITY_RECEIPT",
        "phase_id": PHASE_ID,
        "authority_scope": AUTHORITY_SCOPE,
        "frozen_contract_identity": {
            field.name: getattr(contract, field.name) for field in fields(contract)
        },
        "input_batch_identity": input_batch_identity,
        "authorizes_execution": False,
        "real_data_access": False,
        "outcome_access": False,
        "provider_access": False,
        "evaluation_origin_access": False,
        "persistent_authorization_claim_created": False,
        "synthetic_fixture_persisted": False,
    }


def _accept_authority(
    envelope: object, batch: object
) -> tuple[AuthorityBoundInputEnvelope, ForecastRowBatch]:
    if type(envelope) is not AuthorityBoundInputEnvelope:
        raise AuthorityBoundaryError("successor boundary accepts only AuthorityBoundInputEnvelope")
    if type(batch) is not ForecastRowBatch:
        raise executor.InputIntegrityError("successor boundary accepts only ForecastRowBatch")
    if envelope.successor_phase_id != PHASE_ID or envelope.authority_scope != AUTHORITY_SCOPE:
        raise AuthorityBoundaryError("authority envelope is outside the successor phase scope")
    if envelope.input_batch_identity != batch.input_batch_identity:
        raise AuthorityBoundaryError("authority envelope is not bound to this input batch")
    if any(
        (
            envelope.authorizes_execution,
            envelope.real_data_access,
            envelope.outcome_access,
            envelope.provider_access,
            envelope.evaluation_origin_access,
        )
    ):
        raise AuthorityBoundaryError("offline successor authority cannot authorize execution or access")
    current_contract = _verified_frozen_contract_identity()
    if envelope.frozen_contract_identity != current_contract:
        raise AuthorityBoundaryError("authority envelope is not bound to the current frozen contract")
    expected_receipt_digest = _digest(_receipt_payload(current_contract, batch.input_batch_identity))
    if envelope.authority_receipt_digest != expected_receipt_digest:
        raise AuthorityBoundaryError("authority receipt digest mismatch")
    return envelope, batch


@dataclass(frozen=True, slots=True)
class SuccessorConsumerRecord:
    record_identity: str
    evaluation: executor.IncrementalForecastEvaluation
    canonical_record: bytes
    ordering: tuple[str, ...]
    replayed: bool


@dataclass(frozen=True, slots=True)
class _StoredRecord:
    record_identity: str
    input_content_digest: str
    canonical_record: bytes
    evaluation: executor.IncrementalForecastEvaluation
    ordering: tuple[str, ...]


_RECORDS: dict[str, _StoredRecord] = {}
_RECORD_LOCK = RLock()


def _record_identity(envelope: AuthorityBoundInputEnvelope, batch: ForecastRowBatch) -> str:
    return "|".join((envelope.successor_phase_id, envelope.authority_receipt_digest, batch.input_batch_identity))


def _serialize(value: object) -> object:
    if isinstance(value, Fraction):
        return str(executor.report_decimal(value))
    if isinstance(value, Decimal):
        return _decimal(value)
    if isinstance(value, Mapping):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {field.name: _serialize(getattr(value, field.name)) for field in fields(value)}
    return value


def _canonical_record(
    identity: str,
    batch: ForecastRowBatch,
    evaluation: executor.IncrementalForecastEvaluation,
) -> bytes:
    payload = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "record_identity": identity,
        "input_batch_identity": batch.input_batch_identity,
        "input_content_digest": batch.content_digest,
        "result_type": type(evaluation).__name__,
        "result_digest": evaluation.result_digest,
        "result": _serialize(evaluation),
    }
    return (_canonical_json(payload) + "\n").encode("utf-8")


def _interpret_input(batch: ForecastRowBatch) -> tuple[executor.ForecastRow, ...]:
    if batch.synthetic_only is not True:
        raise AuthorityBoundaryError("only offline synthetic batches are admissible")
    if _digest(_batch_content_payload(batch.rows)) != batch.content_digest:
        raise executor.InputIntegrityError("forecast batch content digest mismatch")
    return executor.validate_forecast_rows(batch.rows)


def _ephemeral_fixture_acceptance() -> None:
    """Create no object with persistence or authorization meaning."""
    return None


def _make_record(
    identity: str,
    batch: ForecastRowBatch,
    evaluation: executor.IncrementalForecastEvaluation,
    ordering: tuple[str, ...],
) -> SuccessorConsumerRecord:
    canonical_record = _canonical_record(identity, batch, evaluation)
    stored = _StoredRecord(
        record_identity=identity,
        input_content_digest=batch.content_digest,
        canonical_record=canonical_record,
        evaluation=evaluation,
        ordering=ordering,
    )
    with _RECORD_LOCK:
        existing = _RECORDS.get(identity)
        if existing is not None:
            if existing.input_content_digest != batch.content_digest or existing.canonical_record != canonical_record:
                raise ExactlyOnceConflictError("record identity replay has different content; no record was written")
            return SuccessorConsumerRecord(
                record_identity=existing.record_identity,
                evaluation=existing.evaluation,
                canonical_record=existing.canonical_record,
                ordering=existing.ordering,
                replayed=True,
            )
        _RECORDS[identity] = stored
    return SuccessorConsumerRecord(
        record_identity=identity,
        evaluation=evaluation,
        canonical_record=canonical_record,
        ordering=ordering,
        replayed=False,
    )


def consume_forecast_batch(
    envelope: AuthorityBoundInputEnvelope,
    batch: ForecastRowBatch,
) -> SuccessorConsumerRecord:
    """Consume one typed offline batch through the sole public successor seam.

    The fixed mode passed to the frozen executor is an implementation detail,
    never an envelope field or caller-selected execution mode.  The boundary
    has no real-input branch.
    """
    events: list[str] = []
    accepted_envelope, accepted_batch = _accept_authority(envelope, batch)
    events.append(AUTHORITY_ACCEPTED)

    _ephemeral_fixture_acceptance()
    events.append(EPHEMERAL_SYNTHETIC_ORDERING_FIXTURE_ACCEPTED)

    rows = _interpret_input(accepted_batch)
    events.append(INPUT_INTERPRETATION)
    identity = _record_identity(accepted_envelope, accepted_batch)

    with _RECORD_LOCK:
        existing = _RECORDS.get(identity)
    if existing is not None:
        if existing.input_content_digest != accepted_batch.content_digest:
            raise ExactlyOnceConflictError("record identity replay has different content; no record was written")
        return SuccessorConsumerRecord(
            record_identity=existing.record_identity,
            evaluation=existing.evaluation,
            canonical_record=existing.canonical_record,
            ordering=existing.ordering,
            replayed=True,
        )

    events.append(OUTCOME_INTERPRETATION)
    evaluation = executor.run_incremental_forecast_evaluation(
        rows,
        execution_mode=executor.EXECUTION_MODE_SYNTHETIC_VALIDATION,
    )
    events.append(RESULT_RECORD)
    return _make_record(identity, accepted_batch, evaluation, tuple(events))


OFFLINE_PHASE_ATTESTATION = MappingProxyType(
    {
        "phase_id": PHASE_ID,
        "project_id": PROJECT_ID,
        "authority_scope": AUTHORITY_SCOPE,
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
)


__all__ = [
    "AUTHORITY_ACCEPTED",
    "AUTHORITY_SCOPE",
    "AuthorityBoundInputEnvelope",
    "AuthorityBoundaryError",
    "ConsumerSeamError",
    "EPHEMERAL_SYNTHETIC_ORDERING_FIXTURE_ACCEPTED",
    "ExactlyOnceConflictError",
    "ForecastRowBatch",
    "FrozenContractIdentity",
    "INPUT_INTERPRETATION",
    "OFFLINE_PHASE_ATTESTATION",
    "OUTCOME_INTERPRETATION",
    "PHASE_ID",
    "PROJECT_ID",
    "RESULT_RECORD",
    "SuccessorConsumerRecord",
    "consume_forecast_batch",
]
