"""Explicit real-row consumer seam + exactly-once result recording.

Phase ``FUNDING_INCREMENTAL_EXECUTOR_REAL_ROW_CONSUMER_AND_EXACTLY_ONCE_RECORDING_V0``.

This module is the smallest repository-native seam that prepares the Funding
incremental executor for a *future, separately authorized* real evaluation.
It does two, and only two, things:

1. :func:`construct_forecast_rows` -- deterministically converts an explicit,
   fully validated typed input (:class:`ForecastRowInput`) into the executor's
   real :class:`ForecastRow` representation, then runs the result through the
   executor's own frozen :func:`validate_forecast_rows` so the frozen
   schedule / temporal / integrity contract is enforced identically to the
   synthetic path.  No hidden IO, no provider access, no implicit fetching:
   the caller supplies every byte.

2. :func:`record_exactly_one_result` -- records exactly one evaluation result
   durably and idempotently, using the repository-native "canonically
   serialized JSON artifact with a self-digest" durability primitive that
   ``experiments/research/.../execution_result.json`` already uses elsewhere
   in this experiment family.  Writes are atomic (temp file + ``os.replace``),
   an identical replay returns the existing receipt without a second write, a
   conflicting replay is rejected, and a tampered stored receipt fails closed.

This phase does NOT perform the evaluation, does NOT create or pin any
evaluation authorization, does NOT consume a claim, and does NOT touch real
market data, outcomes, providers, or the frozen origins.  The seam is
exercised with synthetic fixtures only.  The real-capable wrapper reaches
:func:`record_exactly_one_result` only *after* its existing
authorization / claim / evidence / core-order guards pass, all of which fail
closed today because no canonical evaluation authorization exists.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path

from qntylab.jigsaw_funding_pressure_incremental_forecast_value_core_v1 import (
    IncrementalForecastError,
)
from qntylab.jigsaw_funding_pressure_incremental_forecast_value_executor_v0 import (
    GOVERNING_PREREGISTRATION_DIGEST,
    HAR_MAX_LAG_DAYS,
    IncrementalForecastEvaluation,
    ForecastRow,
    _stamp,
    _utc,
    target_completion_time,
    validate_forecast_rows,
)

PROJECT_ID = "JIGSAW_FUNDING_PRESSURE_INCREMENTAL_FORECAST_VALUE_REAL_ROW_CONSUMER_V0"

#: Canonical, tracked location a future real run's result receipts live under.
#: It does not exist at this phase and this module never creates it implicitly
#: -- :func:`record_exactly_one_result` writes only under the ``ledger_root``
#: its caller passes, and the real-capable wrapper only ever passes this path
#: on a code path that is unreachable until a canonical evaluation
#: authorization is separately created and pinned.
CANONICAL_RESULT_LEDGER_RELATIVE_PATH = (
    "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/"
    "real_execution_result_ledger_v0"
)

RESULT_RECEIPT_SCHEMA_VERSION = "funding-incremental-real-execution-result-receipt-v0"
RESULT_RECEIPT_ARTIFACT_TYPE = "FUNDING_INCREMENTAL_REAL_EXECUTION_RESULT_RECEIPT"

#: Every field this phase can attest it did NOT do.
NO_EXECUTION_ATTESTATION = {
    "REAL_ROWS_CONSTRUCTED_FROM_REAL_EVIDENCE": False,
    "REAL_OUTCOMES_ACCESSED": False,
    "EVALUATION_ORIGINS_CONSUMED": 0,
    "SCIENTIFIC_CORE_INVOKED": False,
    "AUTHORIZATION_CLAIM_CONSUMED": False,
    "EVALUATION_AUTHORIZATION_CREATED": False,
    "NEW_DATA_ACQUIRED": False,
    "PROVIDER_ACCESSED": False,
    "TRIAL_COMPLETION_RECORDED": False,
    "PREREGISTRATION_MUTATED": False,
    "DOWNSTREAM_AUTHORITY": "NONE",
    "CAPITAL_AUTHORITY": "NONE",
}

_SHA256_HEX = 64
_ISO_Z_SUFFIX = "Z"


class RealRowConsumerError(IncrementalForecastError):
    """Raised on any malformed / missing / duplicate / conflicting real-row input."""


class ResultRecordingConflictError(IncrementalForecastError):
    """Raised when a replay carries the same idempotency key but a different receipt."""


class ResultRecordingTamperError(IncrementalForecastError):
    """Raised when a stored result receipt is malformed or fails its self-digest."""


# ==========================================================================
# 1 -- explicit typed input -> real ForecastRow
# ==========================================================================


@dataclass(frozen=True, slots=True)
class ForecastRowInput:
    """One explicit, transport-safe forecast-row input.

    Every magnitude is carried as an exact, environment-independent scalar:
    the funding percentile as an integer ratio, and each RV24 magnitude as a
    decimal-syntax string (never a binary ``float``).  Conversion to the
    executor's :class:`ForecastRow` is total and deterministic.
    """

    origin: str
    target_completion: str
    funding_percentile_numerator: int
    funding_percentile_denominator: int
    rv24_target: str
    rv24_lags: tuple[str, ...]


def _require_z_timestamp(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.endswith(_ISO_Z_SUFFIX):
        raise RealRowConsumerError(f"{label}: expected a 'Z'-suffixed UTC ISO-8601 string, got {value!r}")
    try:
        parsed = _utc(value)
    except Exception as error:  # noqa: BLE001 -- any parse failure fails closed
        raise RealRowConsumerError(f"{label}: not a valid UTC timestamp: {value!r}") from error
    if _stamp(parsed) != value:
        raise RealRowConsumerError(
            f"{label}: timestamp is not in canonical 'YYYY-MM-DDTHH:MM:SSZ' form: {value!r}"
        )
    return value


def _require_int(value: object, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise RealRowConsumerError(f"{label}: expected a plain int, got {type(value).__name__}")
    return value


def _require_nonnegative_decimal(value: object, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise RealRowConsumerError(f"{label}: expected a decimal-syntax string, got {type(value).__name__}")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise RealRowConsumerError(f"{label}: not a valid decimal literal: {value!r}") from error
    if not parsed.is_finite():
        raise RealRowConsumerError(f"{label}: non-finite magnitude is refused: {value!r}")
    if parsed < 0:
        raise RealRowConsumerError(f"{label}: negative magnitude violates the frozen definition: {value!r}")
    return parsed


def _forecast_row_from_input(item: ForecastRowInput) -> ForecastRow:
    if not isinstance(item, ForecastRowInput):
        raise RealRowConsumerError(f"every input must be a ForecastRowInput, got {type(item).__name__}")

    origin = _require_z_timestamp(item.origin, label="origin")
    target_completion = _require_z_timestamp(item.target_completion, label="target_completion")

    expected_completion = _stamp(target_completion_time(_utc(origin)))
    if target_completion != expected_completion:
        raise RealRowConsumerError(
            f"{origin}: conflicting target_completion {target_completion!r}; the frozen contract requires "
            f"exactly origin + 24h ({expected_completion!r})"
        )

    numerator = _require_int(item.funding_percentile_numerator, label=f"{origin}: funding_percentile_numerator")
    denominator = _require_int(item.funding_percentile_denominator, label=f"{origin}: funding_percentile_denominator")
    if denominator <= 0:
        raise RealRowConsumerError(f"{origin}: funding_percentile_denominator must be strictly positive, got {denominator}")
    percentile = Fraction(numerator, denominator)
    if not Fraction(0) <= percentile <= Fraction(1):
        raise RealRowConsumerError(f"{origin}: funding percentile {percentile} escaped the unit interval [0, 1]")

    rv24_target = _require_nonnegative_decimal(item.rv24_target, label=f"{origin}: rv24_target")

    lags = item.rv24_lags
    if not isinstance(lags, tuple):
        raise RealRowConsumerError(f"{origin}: rv24_lags must be a tuple, got {type(lags).__name__}")
    if len(lags) != HAR_MAX_LAG_DAYS:
        raise RealRowConsumerError(
            f"{origin}: exactly {HAR_MAX_LAG_DAYS} RV24 lags are required, got {len(lags)}"
        )
    rv24_lags = tuple(
        _require_nonnegative_decimal(lag, label=f"{origin}: rv24_lags[{index}]")
        for index, lag in enumerate(lags, start=1)
    )

    return ForecastRow(
        origin=origin,
        target_completion=target_completion,
        funding_percentile=percentile,
        rv24_target=rv24_target,
        rv24_lags=rv24_lags,
    )


def construct_forecast_rows(inputs: Sequence[ForecastRowInput]) -> tuple[ForecastRow, ...]:
    """Deterministically convert explicit typed inputs into real ``ForecastRow``s.

    The conversion is pure: no filesystem, network, provider, evidence loader
    or clock is touched.  Per-row validation runs first (so a single malformed
    field fails closed before the schedule contract is considered), then the
    assembled panel is handed to the executor's own frozen
    :func:`validate_forecast_rows`, which enforces the exact frozen 609-origin
    schedule, strict chronological order, the excluded boundary origin, the
    origin + 24h target-completion rule, exact-Fraction percentiles in
    ``[0, 1]`` and non-negative finite ``Decimal`` magnitudes.

    Fails closed with :class:`RealRowConsumerError` on a non-sequence, an empty
    input, a wrong element type, a malformed field, a duplicate origin or a
    conflicting target completion; and with the executor's own
    :class:`~qntylab.jigsaw_funding_pressure_incremental_forecast_value_core_v1.InputIntegrityError`
    / ``TemporalContractError`` on any frozen-schedule violation.
    """
    if isinstance(inputs, (str, bytes)) or not isinstance(inputs, Sequence):
        raise RealRowConsumerError("inputs must be a non-string sequence of ForecastRowInput")
    if len(inputs) == 0:
        raise RealRowConsumerError("no forecast-row inputs were supplied")

    rows: list[ForecastRow] = []
    seen_origins: set[str] = set()
    for item in inputs:
        row = _forecast_row_from_input(item)
        if row.origin in seen_origins:
            raise RealRowConsumerError(f"duplicate forecast-row origin in the supplied inputs: {row.origin}")
        seen_origins.add(row.origin)
        rows.append(row)

    # The executor owns the frozen schedule / ordering / integrity contract;
    # it is reused verbatim here rather than restated.
    return validate_forecast_rows(tuple(rows))


def forecast_row_to_input(row: ForecastRow) -> ForecastRowInput:
    """Total inverse of :func:`_forecast_row_from_input` for a valid row.

    Provided so a synthetic fixture (or a future evidence builder) can round
    trip a ``ForecastRow`` through the explicit transport type without
    restating field semantics.
    """
    if not isinstance(row, ForecastRow):
        raise RealRowConsumerError(f"expected a ForecastRow, got {type(row).__name__}")
    percentile = row.funding_percentile
    if not isinstance(percentile, Fraction):
        raise RealRowConsumerError(f"{row.origin}: funding percentile must be an exact Fraction")
    if not all(isinstance(lag, Decimal) for lag in row.rv24_lags):
        raise RealRowConsumerError(f"{row.origin}: every RV24 lag must be a Decimal")
    if not isinstance(row.rv24_target, Decimal):
        raise RealRowConsumerError(f"{row.origin}: rv24_target must be a Decimal")
    return ForecastRowInput(
        origin=row.origin,
        target_completion=row.target_completion,
        funding_percentile_numerator=percentile.numerator,
        funding_percentile_denominator=percentile.denominator,
        rv24_target=str(row.rv24_target),
        rv24_lags=tuple(str(lag) for lag in row.rv24_lags),
    )


# ==========================================================================
# 2 -- exactly-once, idempotent, durable result recording
# ==========================================================================


def _canonical_json(payload: object) -> str:
    """Repo-native canonicalization: sorted keys, compact, ASCII, no NaN/Inf."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _require_sha256_prefixed(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise RealRowConsumerError(f"{label}: expected a 'sha256:'-prefixed digest, got {value!r}")
    hex_part = value[len("sha256:"):]
    if len(hex_part) != _SHA256_HEX or any(character not in "0123456789abcdef" for character in hex_part):
        raise RealRowConsumerError(f"{label}: malformed sha256 digest: {value!r}")
    return value


def _require_nonempty_str(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RealRowConsumerError(f"{label}: expected a non-empty string, got {value!r}")
    return value


def _claim_view(claim: object) -> dict[str, object]:
    if not isinstance(claim, Mapping) or not claim:
        raise RealRowConsumerError("the consumed one-shot claim must be a non-empty mapping")
    try:
        view = json.loads(_canonical_json(dict(claim)))
    except (TypeError, ValueError) as error:
        raise RealRowConsumerError(f"the consumed one-shot claim is not canonically serializable: {error}") from error
    if not isinstance(view, dict):
        raise RealRowConsumerError("the consumed one-shot claim did not canonicalize to an object")
    return view


def _claim_identity(claim_view: Mapping[str, object]) -> str:
    for key in ("claim_identity", "claim_id", "ref", "authorization_claim_identity"):
        candidate = claim_view.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
    return "sha256:" + _sha256_hex(_canonical_json(claim_view))


def _result_view(result: object) -> dict[str, object]:
    if not isinstance(result, IncrementalForecastEvaluation):
        raise RealRowConsumerError(
            f"result must be an IncrementalForecastEvaluation, got {type(result).__name__}"
        )
    view = {
        "result_type": type(result).__name__,
        "result_digest": _require_sha256_prefixed(result.result_digest, label="result.result_digest"),
        "project_id": _require_nonempty_str(result.project_id, label="result.project_id"),
        "governing_preregistration_project_id": _require_nonempty_str(
            result.governing_preregistration_project_id, label="result.governing_preregistration_project_id"
        ),
        "governing_candidate_id": _require_nonempty_str(
            result.governing_candidate_id, label="result.governing_candidate_id"
        ),
        "governing_preregistration_digest": _require_nonempty_str(
            result.governing_preregistration_digest, label="result.governing_preregistration_digest"
        ),
        "selected_architecture": _require_nonempty_str(
            result.selected_architecture, label="result.selected_architecture"
        ),
        "execution_mode": _require_nonempty_str(result.execution_mode, label="result.execution_mode"),
        "evaluation_origin_count": result.evaluation_origin_count,
        "classification": _require_nonempty_str(result.classification, label="result.classification"),
    }
    if not isinstance(view["evaluation_origin_count"], int) or isinstance(view["evaluation_origin_count"], bool):
        raise RealRowConsumerError("result.evaluation_origin_count must be a plain int")
    if view["governing_preregistration_digest"] != GOVERNING_PREREGISTRATION_DIGEST:
        raise RealRowConsumerError(
            "result is not bound to the frozen governing preregistration digest; recording fails closed"
        )
    return view


def compute_idempotency_key(*, result: object, claim: object) -> str:
    """Stable key bound to the consumed one-shot claim (not the result).

    The one-shot claim licenses exactly one recorded result, so the key is a
    function of the claim's canonical bytes, the governing preregistration
    digest and the schema version.  Consequences:

    * the same claim + the same result -> the same key and the same self-
      digesting receipt -> an idempotent hit with no second write;
    * the same claim + a *different* result (or different provenance) -> the
      same key but a different receipt digest -> a rejected conflicting replay;
    * a different claim -> a different key -> a distinct receipt.

    ``result`` is still validated here so a malformed result fails closed
    before any key is derived.
    """
    claim_view = _claim_view(claim)
    result_view = _result_view(result)
    material = {
        "claim": claim_view,
        "governing_preregistration_digest": result_view["governing_preregistration_digest"],
        "schema_version": RESULT_RECEIPT_SCHEMA_VERSION,
    }
    return _sha256_hex(_canonical_json(material))


def _receipt_self_digest(body: Mapping[str, object]) -> str:
    without = {key: value for key, value in body.items() if key != "receipt_digest"}
    return "sha256:" + _sha256_hex(_canonical_json(without))


def build_result_receipt(
    *, result: object, claim: object, provenance: Mapping[str, object] | None = None
) -> dict[str, object]:
    """Build the deterministic, self-digesting result receipt.

    The receipt carries enough provenance to replay and audit the write: the
    idempotency key, the claim identity and canonical claim bytes digest, the
    result content digest and governing identities, and -- when supplied -- an
    ``authorization_provenance`` block copied verbatim from the authenticated
    canonical Git provenance receipt.  It contains no wall-clock field, so an
    identical replay reproduces byte-identical bytes.
    """
    claim_view = _claim_view(claim)
    result_view = _result_view(result)
    key = compute_idempotency_key(result=result, claim=claim)

    body: dict[str, object] = {
        "schema_version": RESULT_RECEIPT_SCHEMA_VERSION,
        "artifact_type": RESULT_RECEIPT_ARTIFACT_TYPE,
        "recorder_project_id": PROJECT_ID,
        "idempotency_key": key,
        "claim_identity": _claim_identity(claim_view),
        "claim_canonical_sha256": "sha256:" + _sha256_hex(_canonical_json(claim_view)),
        "downstream_authority": "NONE",
        "capital_authority": "NONE",
    }
    body.update(result_view)
    if provenance is not None:
        if not isinstance(provenance, Mapping):
            raise RealRowConsumerError("provenance must be a mapping when supplied")
        try:
            provenance_view = json.loads(_canonical_json(dict(provenance)))
        except (TypeError, ValueError) as error:
            raise RealRowConsumerError(f"provenance is not canonically serializable: {error}") from error
        body["authorization_provenance"] = provenance_view

    body["receipt_digest"] = _receipt_self_digest(body)
    return body


def _load_and_verify_receipt(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except ValueError as error:
        raise ResultRecordingTamperError(f"stored result receipt at {path} is not valid JSON: {error}") from error
    if not isinstance(document, dict) or "receipt_digest" not in document:
        raise ResultRecordingTamperError(f"stored result receipt at {path} is malformed")
    stored_digest = document["receipt_digest"]
    if not isinstance(stored_digest, str):
        raise ResultRecordingTamperError(f"stored result receipt at {path} has a non-string receipt_digest")
    if _receipt_self_digest(document) != stored_digest:
        raise ResultRecordingTamperError(
            f"stored result receipt at {path} fails its self-digest; tampered or partial write refused"
        )
    if raw != (_canonical_json(document) + "\n").encode("utf-8"):
        raise ResultRecordingTamperError(
            f"stored result receipt at {path} is not in canonical serialized form; partial or edited write refused"
        )
    return document


def record_exactly_one_result(
    *,
    result: object,
    claim: object,
    ledger_root: str | os.PathLike[str],
    provenance: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Durably record exactly one result, idempotently and fail-closed.

    Behaviour:

    * **stable idempotency key** -- :func:`compute_idempotency_key` over the
      canonical claim bytes and the result content digest; it names the
      receipt file, so the same (claim, result) collapses to one artifact;
    * **first write** -- the receipt is serialized canonically, written to a
      sibling temp file, ``fsync``-ed, then ``os.replace``-d into place, so an
      interruption leaves either no receipt or the whole receipt, never an
      ambiguous partial one; the just-written bytes are then re-read and
      verified;
    * **identical replay** -- when a receipt already exists and its rebuilt
      digest matches, the stored receipt is returned and nothing is written;
    * **conflicting replay** -- same key, different rebuilt receipt digest ->
      :class:`ResultRecordingConflictError`;
    * **tamper / partial** -- a stored receipt that fails its self-digest or is
      not canonically serialized -> :class:`ResultRecordingTamperError`.

    The caller is responsible for only reaching this function after every
    authorization / claim / evidence / core-order guard has passed; this
    primitive performs no authorization of its own.
    """
    receipt = build_result_receipt(result=result, claim=claim, provenance=provenance)
    key = receipt["idempotency_key"]
    root = Path(ledger_root)
    path = root / f"{key}.result.json"
    payload = (_canonical_json(receipt) + "\n").encode("utf-8")

    if path.exists():
        stored = _load_and_verify_receipt(path)
        if stored["receipt_digest"] != receipt["receipt_digest"]:
            raise ResultRecordingConflictError(
                f"a different result receipt is already recorded for idempotency key {key}; "
                "conflicting replay refused"
            )
        return stored

    root.mkdir(parents=True, exist_ok=True)
    tmp = root / f".{key}.result.json.tmp-{os.getpid()}"
    try:
        with open(tmp, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    try:
        directory_fd = os.open(root, os.O_DIRECTORY)
    except (OSError, AttributeError):
        directory_fd = None
    if directory_fd is not None:
        try:
            os.fsync(directory_fd)
        except OSError:
            pass
        finally:
            os.close(directory_fd)

    # Re-read what actually landed: a concurrent first-writer that won the
    # race with different bytes is caught here rather than silently accepted.
    persisted = _load_and_verify_receipt(path)
    if persisted["receipt_digest"] != receipt["receipt_digest"]:
        raise ResultRecordingConflictError(
            f"a concurrent writer recorded a different result receipt for idempotency key {key}"
        )
    return persisted


__all__ = [
    "CANONICAL_RESULT_LEDGER_RELATIVE_PATH",
    "ForecastRowInput",
    "NO_EXECUTION_ATTESTATION",
    "PROJECT_ID",
    "RESULT_RECEIPT_ARTIFACT_TYPE",
    "RESULT_RECEIPT_SCHEMA_VERSION",
    "RealRowConsumerError",
    "ResultRecordingConflictError",
    "ResultRecordingTamperError",
    "build_result_receipt",
    "compute_idempotency_key",
    "construct_forecast_rows",
    "forecast_row_to_input",
    "record_exactly_one_result",
]
