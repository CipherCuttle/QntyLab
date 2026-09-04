"""Hardened evaluation boundary for the frozen V0 incremental forecast evaluation.

Stage 2 module of the governed task
``FUNDING_INCREMENTAL_CONTRACT_INTEGRITY_HARDENING_IMPLEMENTATION_V0``.

This module structurally enforces the twelve decision invariants of
``tests/test_funding_incremental_contract_integrity_hardening_decision_v0.py``
around the FROZEN V0 executor
:mod:`qntylab.jigsaw_funding_pressure_incremental_forecast_value_executor_v0`.
It is an *orchestration boundary only*: every piece of scientific behavior is
delegated, verbatim, to the frozen public entrypoint
:func:`run_incremental_forecast_evaluation`.  The frozen executor module is
imported through its public names ONLY.  The executor's private assembly
identifier is deliberately never imported or referenced from this module
(neither in code nor in prose, so a content scan stays unambiguous); the exact
scan policy is documented at ``GRANDFATHERED_PRIVATE_ASSEMBLY_LOCATIONS``.

Structural independence thesis (invariants
``PROVENANCE_CONSTRUCTOR_HONESTY`` and ``EXECUTION_MODE_IS_NOT_PROVENANCE``):

* EXECUTION AUTHORITY is authenticated, never attested.  The trust root is
  fixed by reviewed source constants (``EXPECTED_CANONICAL_AUTHORIZATION_COMMIT``
  + ``EXPECTED_CANONICAL_AUTHORIZATION_SHA256`` + canonical anchor commits +
  canonical repository locator + the fixed canonical artifact path), following
  the CI-3 model of
  :mod:`qntylab.jigsaw_funding_pressure_incremental_forecast_value_evaluation_authorization_provenance_v1`.
  The caller supplies NO repository, commit, path or digest.  A token
  (:class:`OfflineAuthorizationToken`) is a DESCRIPTIVE RECEIPT only: at
  admission time the boundary independently re-reads the canonical
  authorization bytes from the pinned canonical commit via local ``git`` and
  refuses any token whose binding does not exactly match the freshly
  re-authenticated canonical grant.  No arrow runs from a caller assertion to
  verified state.
* INPUT PROVENANCE is represented by :class:`VerifiedInputProvenance`, a
  frozen receipt.  Synthetic provenance can be issued ONLY from fixture bytes
  that match a source-pinned :class:`SyntheticFixtureContract` (fixture bytes
  digest AND resulting row digest are pinned constants); there is NO
  constructor that accepts arbitrary pre-existing ``ForecastRow`` values and
  elevates them to verified synthetic provenance.  Git-anchored provenance
  binds the row content digest that is authenticated INSIDE the committed
  artifact bytes; presented rows must hash to exactly that digest.
  Verification recomputes everything and fails closed with
  :class:`ProvenanceRejectedError`.
* SEMANTIC EVALUATION MODE is passed through opaquely to the frozen
  entrypoint, which retains its own guard.  Provenance identity never depends
  on the mode.

Exactly-once process boundary (invariants ``EXACTLY_ONCE_PROCESS_BOUNDARY``,
``EXACTLY_ONCE_SECOND_WORKER``, ``CONFLICTING_REPLAY_FAILS_CLOSED``,
``RESULT_RECORD_IS_DURABLE``): :class:`HardenedDurableClaimStore` is an
append-only JSONL store under an explicit, test-controlled directory, guarded
by an ``fcntl.flock`` sidecar lock.  Every conflict decision is made atomically
under the lock by re-reading the identity state from disk.  There is no
module-global mutable persistence and no process-local persistence: a fresh
process observes identical durable state.  Torn, partial or corrupt lines fail
closed with :class:`DurableRecordCorruptionError` (never silently skipped).

Ordering (``AUTHORITY_FAILURE_PRECEDES_ROWS`` /
``AUTHORITY_FAILURE_ZERO_OBSERVABLE_SCIENCE``):
:class:`HardenedEvaluationBoundary` enforces
AUTHORIZATION VERIFIED -> IRREVERSIBLE CLAIM -> EVIDENCE AUTHENTICATED ->
ROWS CONSTRUCTED -> SCIENTIFIC CORE -> RESULT RECORDED and exposes per-run
instrumentation counters, so a test can prove that an authority failure leaves
zero rows constructed and zero core invocations.

Determinism: every semantic digest in this module is derived from canonical
JSON only (``json.dumps(..., sort_keys=True, separators=(",", ":"))`` with an
explicit, documented Decimal/Fraction -> ``str()`` encoding of exact values).
No timestamp, PID, hostname, randomness or UUID enters any identity.
``recorded_at_utc`` is durable-record metadata written at append time; it is
never a semantic identity component.

Exploratory-only: nothing here licenses real evidence execution or any
downstream authority.  The frozen executor's no-real-execution attestation
remains the governing statement.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence

from qntylab.jigsaw_funding_pressure_incremental_forecast_value_executor_v0 import (
    ForecastRow,
    IncrementalForecastEvaluation,
    run_incremental_forecast_evaluation,
)

# ==========================================================================
# SECTION 0 -- identity, canonical serialization, private-seam scan policy
# ==========================================================================

PROJECT_ID = (
    "FUNDING_INCREMENTAL_CONTRACT_INTEGRITY_HARDENING_IMPLEMENTATION_V0"
    "::HARDENED_EVALUATION_BOUNDARY_V1"
)

#: Provenance kinds understood by this boundary.  Exactly two offline,
#: independently verifiable sources exist; there is deliberately no "real"
#: provenance kind (nothing in this phase may touch real evidence).
PROVENANCE_KIND_OFFLINE_SYNTHETIC_FIXTURE = "OFFLINE_SYNTHETIC_FIXTURE"
PROVENANCE_KIND_GIT_ANCHORED = "GIT_ANCHORED"

#: Outcome states of a durable record.
OUTCOME_CLAIMED_WITHOUT_OUTCOME = "CLAIMED_WITHOUT_OUTCOME"
OUTCOME_RECORDED = "RECORDED"
DURABLE_OUTCOME_STATES = (
    OUTCOME_CLAIMED_WITHOUT_OUTCOME,
    OUTCOME_RECORDED,
)

#: JSONL record schema version of the durable claim store.
DURABLE_RECORD_SCHEMA_VERSION = "HARDENED_DURABLE_RECORD_V1"

#: Frozen entrypoint execution-mode contract, re-exported for callers that
#: need to address the only authorized mode by name.
EXECUTION_MODE_SYNTHETIC_VALIDATION = "SYNTHETIC_VALIDATION"

#: The twelve decision invariants this module structurally enables.  They are
#: exported as plain string constants so a test can assert that the module
#: names them without importing decision JSON.
AUTHORITY_FAILURE_PRECEDES_ROWS = "AUTHORITY_FAILURE_PRECEDES_ROWS"
AUTHORITY_FAILURE_ZERO_OBSERVABLE_SCIENCE = "AUTHORITY_FAILURE_ZERO_OBSERVABLE_SCIENCE"
CONFLICTING_REPLAY_FAILS_CLOSED = "CONFLICTING_REPLAY_FAILS_CLOSED"
EXECUTION_MODE_IS_NOT_PROVENANCE = "EXECUTION_MODE_IS_NOT_PROVENANCE"
EXACTLY_ONCE_PROCESS_BOUNDARY = "EXACTLY_ONCE_PROCESS_BOUNDARY"
EXACTLY_ONCE_SECOND_WORKER = "EXACTLY_ONCE_SECOND_WORKER"
FROZEN_V0_BYTES_UNCHANGED = "FROZEN_V0_BYTES_UNCHANGED"
NO_PROCESS_LOCAL_PERSISTENCE_STATE = "NO_PROCESS_LOCAL_PERSISTENCE_STATE"
PRIVATE_EXECUTION_SEAM_FORBIDDEN = "PRIVATE_EXECUTION_SEAM_FORBIDDEN"
PROVENANCE_CONSTRUCTOR_HONESTY = "PROVENANCE_CONSTRUCTOR_HONESTY"
RESULT_RECORD_IS_DURABLE = "RESULT_RECORD_IS_DURABLE"
RESULT_RECORDING_PROSE_MATCHES_BEHAVIOR = "RESULT_RECORDING_PROSE_MATCHES_BEHAVIOR"

#: Scan policy for the executor's private assembly identifier (spec item 10).
#: A repository scan for that identifier must produce hits in EXACTLY these
#: files:
#:
#: * the frozen executor module -- its definition site plus the single frozen
#:   internal call from the public entrypoint;
#: * the frozen real-capable wrapper module (grandfathered).
#:
#: This module never references the identifier in code or prose.  The scan
#: test can implement the policy as: collect the set of repository-relative
#: paths whose contents contain the identifier and require it to equal
#: ``set(GRANDFATHERED_PRIVATE_ASSEMBLY_LOCATIONS)``.
GRANDFATHERED_PRIVATE_ASSEMBLY_LOCATIONS = (
    "qntylab/jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py",
    "qntylab/jigsaw_funding_pressure_incremental_forecast_value_real_capable_wrapper_v1.py",
)

#: Canonical serialization contract (documented, deterministic):
#: * ``Fraction`` -> ``str(Fraction)`` (exact ``numerator/denominator`` form);
#: * ``Decimal`` -> ``str(Decimal)`` (exact decimal expansion as constructed;
#:   non-finite values are refused);
#: * mappings -> JSON objects with string keys, ``sort_keys=True``;
#: * sequences -> JSON arrays in given order;
#: * ``json.dumps(..., sort_keys=True, separators=(",", ":"))``, UTF-8 bytes.
_CANONICAL_SEPARATORS = (",", ":")


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize ``value`` to canonical JSON bytes (sorted keys, tight separators).

    ``Fraction`` and ``Decimal`` are encoded deterministically via ``str()`` of
    their exact values (see the module-level contract above).  Non-finite
    decimals are refused.  Strings, integers, floats, booleans and ``None``
    pass through; any other type fails closed.
    """
    return json.dumps(
        _to_jsonable(value), sort_keys=True, separators=_CANONICAL_SEPARATORS, ensure_ascii=True
    ).encode("utf-8")


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite Decimal cannot be canonically serialized")
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError(f"cannot canonically serialize value of type {type(value).__name__}")


def sha256_hex(data: bytes) -> str:
    """Lowercase hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


# ==========================================================================
# SECTION 0a -- canonical authority constants (the trust root is SOURCE-PINNED)
# ==========================================================================
#
# The caller NEVER selects the trust root.  Every binding below is a reviewed
# source constant derived from the merged governing decision (CI-3 model of
# ``jigsaw_funding_pressure_incremental_forecast_value_evaluation_authorization_provenance_v1``):
# canonical repository identity, the fixed canonical authorization artifact
# path, the pinned immutable canonical commit, the pinned artifact bytes
# digest, the immutable anchor-commit lineage, and the governing decision
# identity fields the artifact must carry.  A throwaway repository cannot
# reconstruct this combination, and no caller parameter can substitute any of
# these values.

#: Canonical GitHub locator of QntyLab (contextual check only; the pinned
#: commit below is the root of trust).
CANONICAL_REPOSITORY_LOCATOR = "github.com/CipherCuttle/QntyLab"

#: Fixed, tracked path of the canonical authorization artifact: the merged
#: governing decision of this implementation phase.  A caller cannot override
#: which path the bytes are read from.
CANONICAL_AUTHORIZATION_ARTIFACT_RELATIVE_PATH = (
    "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/"
    "contract_integrity_hardening_decision_v0/decision.json"
)

#: The exact immutable canonical commit the authorization artifact is resolved
#: from: the merge commit of the governing decision (PR #244, canonical parent
#: of the implementation branch).  This is the root of trust; a caller cannot
#: supply or override it.
EXPECTED_CANONICAL_AUTHORIZATION_COMMIT = "12202259845ada4f9876288426fed91aba5b6861"

#: SHA-256 of the exact canonical authorization blob bytes (the governing
#: decision document) at the pinned canonical commit.  A file cannot carry its
#: own hash; this pin binds "the accepted bytes" to the reviewed decision.
EXPECTED_CANONICAL_AUTHORIZATION_SHA256 = (
    "712cda5d4e82414ab095deecabaa7d2af054bc7b97ab5cbd394c9fdbeda32a23"
)

#: Immutable QntyLab anchor commits retained as a defence-in-depth lineage
#: check: both must be ancestors of the pinned canonical authorization commit.
#: An unrelated repository does not contain these object IDs.
PREREGISTRATION_ANCHOR_COMMIT = "d2f1839c286ec0407eefd02d878a1b16572bd902"
HISTORICAL_V0_ORACLE_ANCHOR_COMMIT = "f6f12994d65c3dfeaf7839de560e58ad99547c62"
CANONICAL_ANCHOR_COMMITS = (
    PREREGISTRATION_ANCHOR_COMMIT,
    HISTORICAL_V0_ORACLE_ANCHOR_COMMIT,
)

#: Fixed grant identity of this phase's canonical grant.  A token describing
#: any other grant is a forged receipt.
CANONICAL_GRANT_IDENTITY = (
    "FUNDING_INCREMENTAL_CONTRACT_INTEGRITY_HARDENING_IMPLEMENTATION_V0"
    "::HARDENED_EVALUATION_BOUNDARY_V1::CANONICAL_GIT_GRANT_V0"
)

#: Field bindings the canonical authorization artifact (the governing decision)
#: must carry.  The decision is a governance-only artifact: it grants exactly
#: one bounded NON-scientific implementation phase and no scientific
#: evaluation, real-data, outcome, or provider authority.
REQUIRED_AUTHORIZATION_ARTIFACT_TYPE = "FUNDING_INCREMENTAL_CONTRACT_INTEGRITY_HARDENING_DECISION"
REQUIRED_AUTHORIZATION_STATE = "CLOSED_PASS"
REQUIRED_AUTHORIZED_LATER_IMPLEMENTATION_PHASE = (
    "FUNDING_INCREMENTAL_CONTRACT_INTEGRITY_HARDENING_IMPLEMENTATION_V0"
)
REQUIRED_SELECTED_ARCHITECTURE = (
    "OPTION_B_PRESERVE_FROZEN_V0_ORACLE_VERSIONED_HARDENED_SUCCESSOR"
)

# ==========================================================================
# SECTION 0b -- pinned synthetic fixture contract (provenance trust root)
# ==========================================================================
#
# OFFLINE_SYNTHETIC_FIXTURE provenance is issued ONLY from fixture bytes whose
# identity, schema, bytes digest and resulting row content digest are pinned
# here as reviewed source constants.  There is deliberately exactly ONE
# admissible synthetic fixture in this phase; admitting a new fixture is a
# reviewed source change (a governance act), never a caller option.  Arbitrary
# pre-existing ``ForecastRow`` values can NEVER be elevated to verified
# synthetic provenance.


@dataclass(frozen=True, slots=True)
class SyntheticFixtureContract:
    """Source-pinned trust root for one synthetic fixture.

    Every field is a reviewed constant.  A fixture whose bytes do not hash to
    ``fixture_sha256``, whose identity/schema differs, or whose decoded rows do
    not hash to ``row_content_digest`` is refused; no caller parameter can
    relax any of these bindings.
    """

    fixture_identity: str
    schema_identity: str
    fixture_sha256: str
    row_content_digest: str
    factory_identity: str
    row_count: int


#: The canonical fixture identity and schema of the single admissible fixture.
SYNTHETIC_FIXTURE_IDENTITY = "HARDENED_BOUNDARY_SYNTHETIC_FIXTURE_V0"
SYNTHETIC_FIXTURE_SCHEMA_IDENTITY = "ForecastRowV0/offline-synthetic-fixture/1"

#: SHA-256 of the exact canonical fixture bytes, and the canonical row content
#: digest of the rows those bytes deterministically decode to.  Both pins were
#: derived from the frozen deterministic row grid of the invariant suite.
EXPECTED_SYNTHETIC_FIXTURE_SHA256 = (
    "5f48eb5adf5cbb3ca9ada65a93f22cf3700d5269a65fb2aeb67c08166670cf22"
)
EXPECTED_SYNTHETIC_FIXTURE_ROW_CONTENT_DIGEST = (
    "sha256:fab6423260a03178f783822dffb80cb9a79ea614bd764dd9ef88e96f4445b034"
)
EXPECTED_SYNTHETIC_FIXTURE_ROW_COUNT = 609

#: The pinned contract instance (the only synthetic trust root of this module).
CANONICAL_SYNTHETIC_FIXTURE_CONTRACT = SyntheticFixtureContract(
    fixture_identity=SYNTHETIC_FIXTURE_IDENTITY,
    schema_identity=SYNTHETIC_FIXTURE_SCHEMA_IDENTITY,
    fixture_sha256=EXPECTED_SYNTHETIC_FIXTURE_SHA256,
    row_content_digest=EXPECTED_SYNTHETIC_FIXTURE_ROW_CONTENT_DIGEST,
    factory_identity="offline_synthetic_fixture_factory_v1/" + SYNTHETIC_FIXTURE_IDENTITY,
    row_count=EXPECTED_SYNTHETIC_FIXTURE_ROW_COUNT,
)


# ==========================================================================
# SECTION 1 -- exception hierarchy (fail closed, distinct)
# ==========================================================================


class HardeningBoundaryError(Exception):
    """Base class for every hardened-boundary failure (always fail closed)."""


class AuthorityRejectedError(HardeningBoundaryError):
    """Authorization was absent, malformed, or failed its offline check."""


class ProvenanceRejectedError(HardeningBoundaryError):
    """A provenance receipt was malformed or failed re-verification."""


class AlreadyClaimedError(HardeningBoundaryError):
    """The durable claim identity already exists (AFTER_CLAIM fail-closed)."""


class ConflictingReplayError(HardeningBoundaryError):
    """Same claim identity with a different claim digest: deterministic CONFLICT."""


class DurableRecordCorruptionError(HardeningBoundaryError):
    """The durable store contains a torn, partial or corrupt line."""


# ==========================================================================
# SECTION 2 -- verified input provenance
# ==========================================================================


@dataclass(frozen=True, slots=True)
class VerifiedInputProvenance:
    """Narrow, immutable provenance-bound receipt for one forecast-row batch.

    This dataclass is NOT a "trust me" constructor: instances are produced only
    by :func:`make_offline_synthetic_fixture_receipt` and
    :func:`make_git_anchored_receipt`, both of which compute every digest from
    the actual rows at construction time.  Verification is independent of
    construction: :func:`verify_offline_synthetic_fixture_receipt` and
    :func:`verify_git_anchored_receipt` recompute the digests from the rows
    being presented and fail closed on any mismatch, so a hand-built receipt
    is worthless unless its digests genuinely match the rows it claims.

    Fields:

    * ``provenance_kind`` -- one of the two offline kinds;
    * ``factory_identity`` -- deterministic string identifying the factory
      (for git-anchored receipts: pinned commit and artifact path);
    * ``content_digest`` -- ``"sha256:<hex>"`` over the canonical JSON of the
      bound rows in order (Decimal/Fraction encoded as documented);
    * ``schema_identity`` -- frozen row-shape version the factory declared;
    * ``batch_identity`` -- deterministic caller-declared batch identity;
    * ``anchor`` -- kind-specific immutable verification material;
    * ``receipt_digest`` -- ``"sha256:<hex>"`` over the canonical JSON of all
      fields above except ``receipt_digest`` itself.
    """

    provenance_kind: str
    factory_identity: str
    content_digest: str
    schema_identity: str
    batch_identity: str
    anchor: Mapping[str, str]
    receipt_digest: str

    def to_receipt_payload(self) -> dict[str, Any]:
        """Canonical payload of every semantic field (excludes ``receipt_digest``)."""
        return {
            "provenance_kind": self.provenance_kind,
            "factory_identity": self.factory_identity,
            "content_digest": self.content_digest,
            "schema_identity": self.schema_identity,
            "batch_identity": self.batch_identity,
            "anchor": dict(sorted(self.anchor.items())),
        }

    def receipt(self) -> dict[str, Any]:
        """Full receipt payload including ``receipt_digest`` (canonical record)."""
        payload = self.to_receipt_payload()
        payload["receipt_digest"] = self.receipt_digest
        return payload


_SCHEMA_IDENTITY_SYNTHETIC = SYNTHETIC_FIXTURE_SCHEMA_IDENTITY
GIT_ANCHORED_BUNDLE_SCHEMA_IDENTITY = "ForecastRowV0/git-anchored/1"
_SCHEMA_IDENTITY_GIT_ANCHORED = GIT_ANCHORED_BUNDLE_SCHEMA_IDENTITY


def _row_payload(row: ForecastRow) -> dict[str, Any]:
    """Canonical JSON payload of one ``ForecastRow`` (exact-value encoding)."""
    return {
        "origin": row.origin,
        "target_completion": row.target_completion,
        "funding_percentile": row.funding_percentile,
        "rv24_target": row.rv24_target,
        "rv24_lags": list(row.rv24_lags),
    }


def _rows_content_digest(rows: tuple[ForecastRow, ...]) -> str:
    """Canonical digest over ``rows`` in given order (deterministic)."""
    return "sha256:" + sha256_hex(canonical_json_bytes([_row_payload(row) for row in rows]))


def _receipt_digest(payload: Mapping[str, Any]) -> str:
    return "sha256:" + sha256_hex(canonical_json_bytes(dict(payload)))


def _require_rows(rows: Sequence[ForecastRow]) -> tuple[ForecastRow, ...]:
    materialized = tuple(rows)
    if not materialized or not all(isinstance(row, ForecastRow) for row in materialized):
        raise ProvenanceRejectedError("provenance requires non-empty ForecastRow rows")
    return materialized


def decode_synthetic_fixture_rows(fixture_bytes: bytes) -> tuple[ForecastRow, ...]:
    """Authenticate fixture bytes against the pinned contract, then decode rows.

    This is the ONLY way synthetic rows acquire verified provenance: the bytes
    are authenticated FIRST (pinned identity, schema, and bytes digest), then
    deterministically decoded into ``ForecastRow`` values, then the decoded
    rows must hash to the pinned row content digest.  Arbitrary pre-existing
    rows can never enter through here, and arbitrary fixture bytes can never
    authenticate (both pins are reviewed source constants).
    """
    contract = CANONICAL_SYNTHETIC_FIXTURE_CONTRACT
    if not isinstance(fixture_bytes, (bytes, bytearray)):
        raise ProvenanceRejectedError("fixture material must be bytes")
    fixture_bytes = bytes(fixture_bytes)
    actual_fixture_sha256 = sha256_hex(fixture_bytes)
    if actual_fixture_sha256 != contract.fixture_sha256:
        raise ProvenanceRejectedError(
            f"synthetic fixture bytes digest mismatch: contract pins {contract.fixture_sha256}, "
            f"presented bytes hash to {actual_fixture_sha256}; unauthenticated fixture material "
            "cannot gain verified provenance"
        )
    try:
        document = json.loads(fixture_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProvenanceRejectedError(f"synthetic fixture is malformed: {exc}") from exc
    if not isinstance(document, dict):
        raise ProvenanceRejectedError("synthetic fixture must be a JSON object")
    required_keys = {"fixture_identity", "schema_identity", "rows"}
    if set(document) != required_keys:
        raise ProvenanceRejectedError(
            f"synthetic fixture fields {sorted(set(document) ^ required_keys)} are missing or unexpected"
        )
    if document["fixture_identity"] != contract.fixture_identity:
        raise ProvenanceRejectedError(
            f"synthetic fixture identity mismatch: contract pins {contract.fixture_identity!r}, "
            f"fixture declares {document['fixture_identity']!r}"
        )
    if document["schema_identity"] != contract.schema_identity:
        raise ProvenanceRejectedError(
            f"synthetic fixture schema mismatch: contract pins {contract.schema_identity!r}, "
            f"fixture declares {document['schema_identity']!r}"
        )
    raw_rows = document["rows"]
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ProvenanceRejectedError("synthetic fixture rows must be a non-empty JSON array")
    row_keys = {"origin", "target_completion", "funding_percentile", "rv24_target", "rv24_lags"}
    decoded: list[ForecastRow] = []
    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, dict) or set(raw_row) != row_keys:
            raise ProvenanceRejectedError(
                f"synthetic fixture row {index} does not match the pinned row schema"
            )
        for key in ("origin", "target_completion", "funding_percentile", "rv24_target"):
            if not isinstance(raw_row[key], str):
                raise ProvenanceRejectedError(f"synthetic fixture row {index} field {key!r} must be a string")
        if not isinstance(raw_row["rv24_lags"], list) or not all(
            isinstance(lag, str) for lag in raw_row["rv24_lags"]
        ):
            raise ProvenanceRejectedError(f"synthetic fixture row {index} rv24_lags must be strings")
        try:
            decoded.append(
                ForecastRow(
                    origin=raw_row["origin"],
                    target_completion=raw_row["target_completion"],
                    funding_percentile=Fraction(raw_row["funding_percentile"]),
                    rv24_target=Decimal(raw_row["rv24_target"]),
                    rv24_lags=tuple(Decimal(lag) for lag in raw_row["rv24_lags"]),
                )
            )
        except (ValueError, ArithmeticError) as exc:
            raise ProvenanceRejectedError(
                f"synthetic fixture row {index} could not be decoded: {exc}"
            ) from exc
    rows = tuple(decoded)
    actual_row_digest = _rows_content_digest(rows)
    if actual_row_digest != contract.row_content_digest:
        raise ProvenanceRejectedError(
            f"synthetic fixture row content digest mismatch: contract pins "
            f"{contract.row_content_digest}, decoded rows hash to {actual_row_digest}"
        )
    if len(rows) != contract.row_count:
        raise ProvenanceRejectedError(
            f"synthetic fixture row count mismatch: contract pins {contract.row_count}, "
            f"decoded {len(rows)}"
        )
    return rows


def make_offline_synthetic_fixture_receipt_from_authenticated_fixture(
    fixture_bytes: bytes, *, batch_identity: str
) -> VerifiedInputProvenance:
    """Issue a verified ``OFFLINE_SYNTHETIC_FIXTURE`` receipt from fixture bytes.

    The fixture bytes are authenticated against :data:`CANONICAL_SYNTHETIC_FIXTURE_CONTRACT`
    (bytes digest, identity, schema) and deterministically decoded; the receipt
    binds the resulting rows via their recomputed content digest, which must
    equal the pinned row content digest.  ``batch_identity`` is the only
    caller-supplied field and is descriptive only -- it can never select rows,
    fixture identity, or any digest.
    """
    if not isinstance(batch_identity, str) or not batch_identity:
        raise ProvenanceRejectedError("batch_identity must be a non-empty string")
    contract = CANONICAL_SYNTHETIC_FIXTURE_CONTRACT
    rows = decode_synthetic_fixture_rows(fixture_bytes)
    content_digest = _rows_content_digest(rows)
    if content_digest != contract.row_content_digest:  # defence in depth
        raise ProvenanceRejectedError("decoded fixture rows do not match the pinned row content digest")
    anchor = {
        "fixture_identity": contract.fixture_identity,
        "fixture_sha256": contract.fixture_sha256,
        "row_content_digest": contract.row_content_digest,
        "schema_identity": contract.schema_identity,
    }
    payload = {
        "provenance_kind": PROVENANCE_KIND_OFFLINE_SYNTHETIC_FIXTURE,
        "factory_identity": contract.factory_identity,
        "content_digest": content_digest,
        "schema_identity": contract.schema_identity,
        "batch_identity": batch_identity,
        "anchor": anchor,
    }
    return VerifiedInputProvenance(**payload, receipt_digest=_receipt_digest(payload))


def verify_offline_synthetic_fixture_receipt(
    receipt: VerifiedInputProvenance, rows: Sequence[ForecastRow]
) -> tuple[ForecastRow, ...]:
    """Fail closed unless ``receipt`` genuinely binds exactly ``rows``.

    Independently recomputes the row digest from the presented rows and checks
    that the receipt's anchor EXACTLY equals the pinned synthetic fixture
    contract (identity, bytes digest, schema, row digest), that the row digest
    equals the pinned row content digest, and that the receipt self-digest is
    intact.  A self-consistent hand-built receipt is therefore worthless: it
    cannot reproduce the pinned contract anchor.  Any mismatch raises
    :class:`ProvenanceRejectedError`.
    """
    if not isinstance(receipt, VerifiedInputProvenance):
        raise ProvenanceRejectedError("receipt must be a VerifiedInputProvenance")
    if receipt.provenance_kind != PROVENANCE_KIND_OFFLINE_SYNTHETIC_FIXTURE:
        raise ProvenanceRejectedError(
            f"receipt provenance kind is {receipt.provenance_kind!r}, "
            f"expected {PROVENANCE_KIND_OFFLINE_SYNTHETIC_FIXTURE!r}"
        )
    contract = CANONICAL_SYNTHETIC_FIXTURE_CONTRACT
    expected_anchor = {
        "fixture_identity": contract.fixture_identity,
        "fixture_sha256": contract.fixture_sha256,
        "row_content_digest": contract.row_content_digest,
        "schema_identity": contract.schema_identity,
    }
    if dict(receipt.anchor) != expected_anchor:
        raise ProvenanceRejectedError(
            "synthetic fixture receipt anchor does not match the pinned fixture contract; "
            "the receipt is forged or was issued for a different (unpinned) fixture"
        )
    if receipt.factory_identity != contract.factory_identity:
        raise ProvenanceRejectedError(
            f"synthetic fixture receipt factory identity {receipt.factory_identity!r} does not "
            f"match the pinned factory identity {contract.factory_identity!r}"
        )
    materialized = _require_rows(rows)
    actual_content = _rows_content_digest(materialized)
    if receipt.content_digest != actual_content:
        raise ProvenanceRejectedError(
            f"row content digest mismatch: receipt claims {receipt.content_digest}, "
            f"rows hash to {actual_content}"
        )
    if receipt.content_digest != contract.row_content_digest:
        raise ProvenanceRejectedError(
            f"receipt row content digest does not match the pinned fixture contract digest "
            f"{contract.row_content_digest}"
        )
    if receipt.receipt_digest != _receipt_digest(receipt.to_receipt_payload()):
        raise ProvenanceRejectedError("receipt digest does not match its own fields; receipt is forged or torn")
    return materialized


def git_anchored_artifact_bytes(rows: Sequence[ForecastRow]) -> bytes:
    """Author the canonical ``GIT_ANCHORED`` artifact bundle for ``rows``.

    The committed artifact itself must carry the row content digest, so the
    Git-anchored receipt can verify that the AUTHENTICATED artifact bytes bind
    the exact presented rows (no blob A can ever provenance rows B).  The
    bundle is deterministic canonical JSON over the row payloads.
    """
    materialized = _require_rows(rows)
    return canonical_json_bytes(
        {
            "provenance_kind": PROVENANCE_KIND_GIT_ANCHORED,
            "row_content_digest": _rows_content_digest(materialized),
            "schema_identity": GIT_ANCHORED_BUNDLE_SCHEMA_IDENTITY,
        }
    )


def _parse_git_anchored_bundle(blob_bytes: bytes) -> str:
    """Parse the authenticated artifact bundle and return its row content digest.

    The artifact must be a canonical JSON object with exactly the fields
    ``provenance_kind``, ``row_content_digest`` and ``schema_identity``; any
    other shape, kind, schema, or a non-hex digest fails closed.  The returned
    digest is the one AUTHENTICATED INSIDE the artifact bytes -- the caller
    must require exact equality with the digest of the presented rows.
    """
    try:
        document = json.loads(blob_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProvenanceRejectedError(f"git-anchored artifact is not a canonical bundle: {exc}") from exc
    if not isinstance(document, dict):
        raise ProvenanceRejectedError("git-anchored artifact must be a JSON object")
    required_keys = {"provenance_kind", "row_content_digest", "schema_identity"}
    if set(document) != required_keys:
        raise ProvenanceRejectedError(
            f"git-anchored artifact fields {sorted(set(document) ^ required_keys)} are missing or unexpected"
        )
    if document["provenance_kind"] != PROVENANCE_KIND_GIT_ANCHORED:
        raise ProvenanceRejectedError(
            f"git-anchored artifact provenance kind is {document['provenance_kind']!r}"
        )
    if document["schema_identity"] != GIT_ANCHORED_BUNDLE_SCHEMA_IDENTITY:
        raise ProvenanceRejectedError(
            f"git-anchored artifact schema identity is {document['schema_identity']!r}, "
            f"expected {GIT_ANCHORED_BUNDLE_SCHEMA_IDENTITY!r}"
        )
    inner_digest = document["row_content_digest"]
    if not isinstance(inner_digest, str) or not inner_digest.startswith("sha256:") or not _is_hex64(
        inner_digest[len("sha256:"):]
    ):
        raise ProvenanceRejectedError("git-anchored artifact row_content_digest is not a sha256 digest string")
    return inner_digest


def make_git_anchored_receipt(
    rows: Sequence[ForecastRow],
    *,
    batch_identity: str,
    repository_root: Path,
    pinned_commit: str,
    artifact_relative_path: str,
    expected_blob_sha256: str,
) -> VerifiedInputProvenance:
    """Build a ``GIT_ANCHORED`` provenance receipt from offline git truth.

    Reads the artifact bytes at ``pinned_commit`` via local ``git`` commands
    inside ``repository_root`` and records their SHA-256.  Construction fails
    closed if git is unavailable, the commit or path is absent, the bytes do
    not hash to ``expected_blob_sha256``, or the authenticated artifact does
    not parse as a canonical bundle whose INNER ``row_content_digest`` binds
    exactly the presented rows.  The receipt is then verifiable offline by any
    fresh process repeating the same check
    (:func:`verify_git_anchored_receipt`).  The row binding is one-directional
    and structural: authenticated artifact -> rows.  Unrelated rows can never
    borrow a blob's identity, and a blob can never provenance rows it does not
    itself digest.
    """
    if not isinstance(batch_identity, str) or not batch_identity:
        raise ProvenanceRejectedError("batch_identity must be a non-empty string")
    materialized = _require_rows(rows)
    if not _is_hex64(expected_blob_sha256):
        raise ProvenanceRejectedError("expected_blob_sha256 must be a 64-char hex digest")
    blob_bytes = _git_show_blob(repository_root, pinned_commit, artifact_relative_path)
    actual_blob_sha256 = sha256_hex(blob_bytes)
    if actual_blob_sha256 != expected_blob_sha256:
        raise ProvenanceRejectedError(
            f"git artifact digest mismatch at pinned commit {pinned_commit!r}: "
            f"expected {expected_blob_sha256}, got {actual_blob_sha256}"
        )
    content_digest = _rows_content_digest(materialized)
    authenticated_row_digest = _parse_git_anchored_bundle(blob_bytes)
    if authenticated_row_digest != content_digest:
        raise ProvenanceRejectedError(
            "authenticated git artifact does not bind the presented rows: the artifact's inner "
            f"row_content_digest is {authenticated_row_digest}, but the presented rows hash to "
            f"{content_digest}; unrelated rows cannot be provenanced by a foreign blob"
        )
    anchor = {
        "artifact_relative_path": artifact_relative_path,
        "blob_sha256": actual_blob_sha256,
        "pinned_commit": pinned_commit,
        "repository_root": str(Path(repository_root).resolve()),
        "repository_root_sha256": _path_identity_digest(repository_root),
        "row_content_digest": authenticated_row_digest,
    }
    payload = {
        "provenance_kind": PROVENANCE_KIND_GIT_ANCHORED,
        "factory_identity": f"git_anchored_factory_v1/{pinned_commit}/{artifact_relative_path}",
        "content_digest": content_digest,
        "schema_identity": _SCHEMA_IDENTITY_GIT_ANCHORED,
        "batch_identity": batch_identity,
        "anchor": anchor,
    }
    return VerifiedInputProvenance(**payload, receipt_digest=_receipt_digest(payload))


def verify_git_anchored_receipt(
    receipt: VerifiedInputProvenance,
    rows: Sequence[ForecastRow],
    *,
    repository_root: Path | None = None,
) -> tuple[ForecastRow, ...]:
    """Fail closed unless ``receipt`` re-verifies offline against ``rows``.

    Re-reads the artifact at the receipt's pinned commit with local ``git``,
    re-compares its SHA-256 against the receipt anchor (git unavailable,
    missing artifact, or digest mismatch all fail closed), re-parses the
    authenticated artifact bundle, and requires the INNER ``row_content_digest``
    (the digest authenticated inside the artifact bytes) to equal BOTH the
    receipt's row content digest AND the digest recomputed from the presented
    rows; then re-verifies the receipt self-digest.  ``repository_root``
    defaults to the root recorded in the receipt anchor and may be overridden
    explicitly (portable re-verification on a fresh checkout of the same
    repository identity).
    """
    if not isinstance(receipt, VerifiedInputProvenance):
        raise ProvenanceRejectedError("receipt must be a VerifiedInputProvenance")
    if receipt.provenance_kind != PROVENANCE_KIND_GIT_ANCHORED:
        raise ProvenanceRejectedError(
            f"receipt provenance kind is {receipt.provenance_kind!r}, "
            f"expected {PROVENANCE_KIND_GIT_ANCHORED!r}"
        )
    materialized = _require_rows(rows)
    anchor = receipt.anchor
    for required in ("pinned_commit", "artifact_relative_path", "blob_sha256"):
        if required not in anchor:
            raise ProvenanceRejectedError(f"git-anchored receipt anchor is missing {required!r}")
    if not _is_hex64(str(anchor["blob_sha256"])):
        raise ProvenanceRejectedError("receipt anchor blob_sha256 is not a 64-char hex digest")
    root = Path(repository_root if repository_root is not None else str(anchor.get("repository_root", ".")))
    blob_bytes = _git_show_blob(root, str(anchor["pinned_commit"]), str(anchor["artifact_relative_path"]))
    if sha256_hex(blob_bytes) != anchor["blob_sha256"]:
        raise ProvenanceRejectedError("git artifact digest no longer matches the receipt anchor")
    authenticated_row_digest = _parse_git_anchored_bundle(blob_bytes)
    actual_content = _rows_content_digest(materialized)
    if authenticated_row_digest != receipt.content_digest:
        raise ProvenanceRejectedError(
            "authenticated git artifact row_content_digest no longer matches the receipt's "
            f"bound digest {receipt.content_digest}"
        )
    if receipt.content_digest != actual_content:
        raise ProvenanceRejectedError(
            f"row content digest mismatch: receipt claims {receipt.content_digest}, "
            f"rows hash to {actual_content}"
        )
    if receipt.receipt_digest != _receipt_digest(receipt.to_receipt_payload()):
        raise ProvenanceRejectedError("receipt digest does not match its own fields; receipt is forged or torn")
    return materialized


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _git_show_blob(repository_root: Path, commit: str, path: str) -> bytes:
    """Offline git read: artifact bytes at ``commit:path``; fails closed."""
    if not isinstance(repository_root, Path) or not repository_root.is_dir():
        raise ProvenanceRejectedError(f"repository_root is not a directory: {repository_root!r}")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-fA-F]{6,64}", commit) is None:
        raise ProvenanceRejectedError(f"pinned commit is not a plausible object id: {commit!r}")
    try:
        proc = subprocess.run(
            ["git", "-C", str(repository_root), "cat-file", "blob", f"{commit}:{path}"],
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProvenanceRejectedError(f"git is unavailable or the offline read failed: {exc}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise ProvenanceRejectedError(
            f"git artifact {commit}:{path} is absent or unreadable "
            f"(returncode {proc.returncode}): {detail}"
        )
    return proc.stdout


def _path_identity_digest(path: Path) -> str:
    """Deterministic digest of a normalized absolute path (identity only)."""
    return sha256_hex(str(Path(path).resolve()).encode("utf-8"))


# ==========================================================================
# SECTION 3 -- provenanced forecast batch
# ==========================================================================


@dataclass(frozen=True, slots=True)
class ProvenancedForecastBatch:
    """A ``ForecastRow`` tuple inseparably bound to verified provenance.

    Construction is intentionally constrained: instances are produced only by
    :func:`admit_verified_batch` (or
    :meth:`HardenedEvaluationBoundary.admit_batch`), which FIRST verifies the
    receipt against the rows and only then composes the batch.  There is no
    construction path that wraps arbitrary rows without verified provenance.
    """

    rows: tuple[ForecastRow, ...]
    provenance: VerifiedInputProvenance
    batch_identity: str

    def canonical_batch_digest(self) -> str:
        """Deterministic digest over the bound rows and the provenance receipt."""
        return "sha256:" + sha256_hex(
            canonical_json_bytes(
                {
                    "batch_identity": self.batch_identity,
                    "provenance": self.provenance.to_receipt_payload(),
                    "rows": [_row_payload(row) for row in self.rows],
                }
            )
        )

    def reverify(self) -> tuple[ForecastRow, ...]:
        """Re-run receipt<->rows verification (fail closed) and return the rows."""
        return _verify_receipt_against_rows(self.provenance, self.rows)


def _verify_receipt_against_rows(
    provenance: VerifiedInputProvenance, rows: tuple[ForecastRow, ...]
) -> tuple[ForecastRow, ...]:
    if provenance.provenance_kind == PROVENANCE_KIND_OFFLINE_SYNTHETIC_FIXTURE:
        return verify_offline_synthetic_fixture_receipt(provenance, rows)
    if provenance.provenance_kind == PROVENANCE_KIND_GIT_ANCHORED:
        return verify_git_anchored_receipt(provenance, rows)
    raise ProvenanceRejectedError(f"unknown provenance kind: {provenance.provenance_kind!r}")


def admit_verified_batch(
    provenance: VerifiedInputProvenance, rows: Sequence[ForecastRow]
) -> ProvenancedForecastBatch:
    """The ONLY way to obtain a :class:`ProvenancedForecastBatch`.

    Verification precedes composition: a mismatched or forged receipt raises
    :class:`ProvenanceRejectedError` and no batch object ever exists.
    """
    verified_rows = _verify_receipt_against_rows(provenance, tuple(rows))
    return ProvenancedForecastBatch(
        rows=verified_rows, provenance=provenance, batch_identity=provenance.batch_identity
    )


# ==========================================================================
# SECTION 4 -- canonical authorization authentication (H1/H2 repair)
# ==========================================================================
#
# A token is a DESCRIPTIVE RECEIPT, never authority.  Constructing the Python
# object proves nothing: authority is established ONLY by the boundary's own
# independent re-authentication of the canonical authorization binding against
# canonical Git immediately before a claim, row, or core activity.  The former
# caller-selected check (caller-supplied repository/commit/path/expected
# digest) is REMOVED: the requester must never choose the trust root.


@dataclass(frozen=True, slots=True)
class OfflineAuthorizationToken:
    """Immutable DESCRIPTIVE RECEIPT of one successful canonical grant check.

    This token carries NO authority by itself: it can be constructed freely by
    any caller with plausible fields, so :meth:`HardenedEvaluationBoundary.run_evaluation`
    treats it as a receipt only and requires its binding to equal the binding
    the boundary itself freshly re-authenticates from canonical Git at
    admission time.  A forged or stale receipt -- including one describing a
    throwaway repository -- is rejected because it cannot match the freshly
    authenticated canonical binding.

    It deliberately does NOT consume any real authorization claim and grants
    no real-evidence authority; the frozen entrypoint's own execution-mode
    guard remains the authoritative science-side control.
    """

    grant_identity: str
    pinned_authorization_sha256: str
    verification_commit: str
    verified_at_commit_binding: str

    def binding_digest(self) -> str:
        """Deterministic binding digest for the durable record's authorization field."""
        return "sha256:" + sha256_hex(
            canonical_json_bytes(
                {
                    "grant_identity": self.grant_identity,
                    "pinned_authorization_sha256": self.pinned_authorization_sha256,
                    "verification_commit": self.verification_commit,
                    "verified_at_commit_binding": self.verified_at_commit_binding,
                }
            )
        )


def _authority_repository_root() -> Path:
    """The repository the boundary authenticates against: ALWAYS this module's own.

    The trust root is fixed by construction; no caller can redirect the
    boundary's authority resolution at another repository.
    """
    return Path(__file__).resolve().parents[1]


def _authority_git(root: Path, *args: str, check: bool = True) -> bytes:
    """Read-only Git plumbing for authority authentication; fails closed.

    An inherited ``GIT_DIR``/``GIT_WORK_TREE`` would silently redirect the
    read at another repository, so every ``GIT_*`` variable is dropped and
    ``-C`` is the only thing selecting the repository.  ``--no-optional-locks``
    keeps a read from rewriting ``.git/index``.  Only local object-database
    reads are ever issued (no network, no remote refs, no token use).
    """
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        completed = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), *args],
            check=False,
            capture_output=True,
            timeout=30,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AuthorityRejectedError(
            f"git plumbing is unavailable while authenticating the canonical grant ({args!r}): {error}"
        ) from error
    if check and completed.returncode:
        detail = completed.stderr.decode("utf-8", "replace").strip() or "git command failed"
        raise AuthorityRejectedError(
            f"canonical grant could not be authenticated ({args!r}): {detail}"
        )
    return completed.stdout


def _authority_git_text(root: Path, *args: str, check: bool = True) -> str:
    return _authority_git(root, *args, check=check).decode("utf-8", "replace").strip()


def _authority_git_ok(root: Path, *args: str) -> bool:
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        completed = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), *args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _canonical_remote_locator(raw: str) -> str | None:
    value = raw.strip()
    for prefix in ("https://github.com/", "git@github.com:", "ssh://git@github.com/"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    else:
        return None
    if value.endswith("/"):
        value = value[:-1]
    if value.endswith(".git"):
        value = value[:-4]
    parts = value.split("/")
    if len(parts) != 2 or not all(parts):
        return None
    return f"github.com/{parts[0]}/{parts[1]}"


def _require_canonical_repository_context(root: Path) -> None:
    """Contextual repository-identity check (NOT the root of trust).

    The pinned commit below is the root of trust; this check additionally
    refuses repositories whose ``origin`` is not canonical QntyLab.
    """
    if not (root / ".git").exists():
        raise AuthorityRejectedError(
            f"no usable Git metadata at {root}: canonical grant authentication fails closed"
        )
    configured = _authority_git_text(root, "config", "--get", "remote.origin.url", check=False)
    lines = [line for line in configured.splitlines() if line.strip()]
    if len(lines) != 1:
        raise AuthorityRejectedError(
            "canonical repository identity is unverifiable: remote.origin.url is absent or ambiguous"
        )
    if _canonical_remote_locator(lines[0]) != CANONICAL_REPOSITORY_LOCATOR:
        raise AuthorityRejectedError(
            f"wrong repository identity: remote.origin.url does not resolve to "
            f"{CANONICAL_REPOSITORY_LOCATOR!r}; a throwaway or foreign repository can never "
            "authenticate the canonical grant"
        )


def _resolve_pinned_canonical_authorization_commit(root: Path) -> None:
    """Resolve and fully validate the source-pinned canonical commit.

    Fails closed when the pinned object is absent, is not a commit, does not
    verify to an immutable object id, is neither the current checkout nor an
    ancestor of it, or when a canonical anchor is not an ancestor of the
    pinned commit (wrong repository lineage).
    """
    pinned = EXPECTED_CANONICAL_AUTHORIZATION_COMMIT
    if _authority_git_text(root, "cat-file", "-t", pinned, check=False) != "commit":
        raise AuthorityRejectedError(
            "pinned canonical authorization commit is not present or resolvable in this repository"
        )
    verified = _authority_git_text(root, "rev-parse", "--verify", "--quiet", f"{pinned}^{{commit}}", check=False)
    if verified != pinned:
        raise AuthorityRejectedError(
            "pinned canonical authorization commit did not verify to an immutable commit object"
        )
    head = _authority_git_text(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}", check=False)
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise AuthorityRejectedError("HEAD does not resolve to a commit object")
    if head != pinned and not _authority_git_ok(root, "merge-base", "--is-ancestor", pinned, head):
        raise AuthorityRejectedError(
            "pinned canonical authorization commit is neither the current checkout nor an "
            "ancestor of it; an unpinned, divergent, or forged commit is refused"
        )
    for anchor in CANONICAL_ANCHOR_COMMITS:
        if _authority_git_text(root, "cat-file", "-t", anchor, check=False) != "commit":
            raise AuthorityRejectedError(
                f"wrong repository identity: canonical anchor {anchor} is not a commit in this repository"
            )
        if not _authority_git_ok(root, "merge-base", "--is-ancestor", anchor, pinned):
            raise AuthorityRejectedError(
                f"wrong repository identity: canonical anchor {anchor} is not an ancestor of the "
                "pinned canonical authorization commit"
            )


def _canonical_authorization_blob(root: Path) -> bytes:
    """The canonical authorization blob bytes at ``PINNED_COMMIT:<fixed path>``.

    The tree entry is read from the pinned commit itself (``git ls-tree``), not
    from the worktree index or ``HEAD``, so a worktree-local file, a different
    branch, or a later tree cannot supply or hide the artifact.
    """
    entry = _authority_git_text(
        root,
        "ls-tree",
        "--full-tree",
        EXPECTED_CANONICAL_AUTHORIZATION_COMMIT,
        "--",
        CANONICAL_AUTHORIZATION_ARTIFACT_RELATIVE_PATH,
        check=False,
    )
    if not entry:
        raise AuthorityRejectedError(
            "no canonical authorization artifact exists at the pinned canonical commit "
            f"({CANONICAL_AUTHORIZATION_ARTIFACT_RELATIVE_PATH} at "
            f"{EXPECTED_CANONICAL_AUTHORIZATION_COMMIT}); execution fails closed"
        )
    meta = entry.partition("\t")[0].split()
    if len(meta) != 3:
        raise AuthorityRejectedError("canonical authorization artifact tree entry is unreadable")
    mode, kind, blob_oid = meta
    if kind != "blob" or not re.fullmatch(r"[0-9a-f]{40}", blob_oid):
        raise AuthorityRejectedError(
            "canonical authorization artifact path does not resolve to a Git blob at the pinned commit"
        )
    if mode == "120000":
        raise AuthorityRejectedError(
            "canonical authorization artifact path is a symlink in the pinned tree; a regular blob is required"
        )
    return _authority_git(root, "cat-file", "blob", blob_oid, check=True)


def _require_canonical_authorization_bindings(blob_bytes: bytes) -> None:
    """The authenticated artifact must BE the governing decision for this phase."""
    try:
        document = json.loads(blob_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AuthorityRejectedError(f"canonical authorization artifact is malformed: {error}") from error
    if not isinstance(document, dict):
        raise AuthorityRejectedError("canonical authorization artifact must be a JSON object")
    expected_fields = {
        "artifact_type": REQUIRED_AUTHORIZATION_ARTIFACT_TYPE,
        "state": REQUIRED_AUTHORIZATION_STATE,
        "authorized_later_implementation_phase": REQUIRED_AUTHORIZED_LATER_IMPLEMENTATION_PHASE,
        "selected_architecture": REQUIRED_SELECTED_ARCHITECTURE,
        "scientific_execution_authorized": False,
        "real_data_access_authorized": False,
        "outcome_access_authorized": False,
        "provider_access_authorized": False,
    }
    for field, want in expected_fields.items():
        if document.get(field) != want:
            raise AuthorityRejectedError(
                f"canonical authorization artifact field {field!r} mismatch: expected {want!r}, "
                f"got {document.get(field)!r}"
            )


def authenticate_canonical_hardening_authorization(
    *, root: Path | None = None
) -> OfflineAuthorizationToken:
    """Authenticate the canonical authorization binding (CI-3 model).

    The trust root is entirely source-pinned: canonical repository locator,
    fixed artifact path, pinned immutable commit, pinned bytes digest, anchor
    lineage, and governing-decision field bindings.  The caller supplies NO
    repository identity, commit, path, or digest; ``root`` can only *point at*
    a checkout and every canonical constraint still fails closed in a wrong
    one.  Reads are local Git object-database reads only: NO network, NO
    GitHub API, NO token use, NO remote refs.

    Fails closed with :class:`AuthorityRejectedError` on: a wrong or unusable
    repository, an absent/forged/divergent pinned commit, a broken anchor
    lineage, an absent artifact at the pinned commit, modified artifact bytes,
    or governing-decision field mismatches.  On success returns the descriptive
    receipt token whose binding :meth:`HardenedEvaluationBoundary.run_evaluation`
    independently re-derives at admission time.
    """
    resolved_root = (root or _authority_repository_root()).resolve()
    _require_canonical_repository_context(resolved_root)
    _resolve_pinned_canonical_authorization_commit(resolved_root)
    blob_bytes = _canonical_authorization_blob(resolved_root)
    blob_sha256 = sha256_hex(blob_bytes)
    if blob_sha256 != EXPECTED_CANONICAL_AUTHORIZATION_SHA256:
        raise AuthorityRejectedError(
            "canonical authorization artifact bytes do not match the pinned content digest; "
            "modified authorization bytes are refused"
        )
    _require_canonical_authorization_bindings(blob_bytes)
    return OfflineAuthorizationToken(
        grant_identity=CANONICAL_GRANT_IDENTITY,
        pinned_authorization_sha256=blob_sha256,
        verification_commit=EXPECTED_CANONICAL_AUTHORIZATION_COMMIT,
        verified_at_commit_binding="sha256:"
        + sha256_hex(
            canonical_json_bytes(
                {
                    "anchors": list(CANONICAL_ANCHOR_COMMITS),
                    "artifact_path": CANONICAL_AUTHORIZATION_ARTIFACT_RELATIVE_PATH,
                    "artifact_sha256": blob_sha256,
                    "pinned_commit": EXPECTED_CANONICAL_AUTHORIZATION_COMMIT,
                    "repository": CANONICAL_REPOSITORY_LOCATOR,
                }
            )
        ),
    )


# ==========================================================================
# SECTION 5 -- hardened durable claim store
# ==========================================================================


def _utc_now_iso() -> str:
    """ISO-8601 UTC timestamp for durable record METADATA (never identity)."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _is_iso_utc_metadata(value: str) -> bool:
    """Structural check that ``value`` parses as ISO-8601 (``Z`` suffix allowed)."""
    try:
        datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class DurableClaimRecord:
    """One durable record line (JSONL) of the exactly-once claim store.

    ``recorded_at_utc`` is ISO-8601 UTC metadata written when the record line
    is appended; it is NEVER a semantic identity component (identity is
    ``claim_identity`` + ``claim_digest`` only).  ``result_digest`` is null
    until a result has been recorded.
    """

    claim_identity: str
    claim_digest: str
    result_digest: str | None
    authorization_binding: str
    recorded_at_utc: str
    outcome_state: str
    schema_version: str = DURABLE_RECORD_SCHEMA_VERSION

    def to_json_line(self) -> str:
        """Canonical single-line JSON (sorted keys, tight separators)."""
        return canonical_json_bytes(
            {
                "authorization_binding": self.authorization_binding,
                "claim_digest": self.claim_digest,
                "claim_identity": self.claim_identity,
                "outcome_state": self.outcome_state,
                "recorded_at_utc": self.recorded_at_utc,
                "result_digest": self.result_digest,
                "schema_version": self.schema_version,
            }
        ).decode("utf-8")

    @staticmethod
    def from_json_line(line: str) -> "DurableClaimRecord":
        """Parse one JSONL line; any malformation raises
        :class:`DurableRecordCorruptionError` (fail closed, never skipped)."""
        try:
            raw = json.loads(line)
        except (json.JSONDecodeError, ValueError) as exc:
            raise DurableRecordCorruptionError(
                f"durable record line is not valid JSON: {line[:120]!r}"
            ) from exc
        if not isinstance(raw, dict):
            raise DurableRecordCorruptionError("durable record line is not a JSON object")
        required: dict[str, tuple[type, ...]] = {
            "claim_identity": (str,),
            "claim_digest": (str,),
            "result_digest": (str, type(None)),
            "authorization_binding": (str,),
            "recorded_at_utc": (str,),
            "outcome_state": (str,),
            "schema_version": (str,),
        }
        if set(raw) != set(required):
            raise DurableRecordCorruptionError(
                f"durable record fields {sorted(set(required) ^ set(raw))} are missing or unexpected"
            )
        for field, types in required.items():
            if not isinstance(raw[field], types):
                raise DurableRecordCorruptionError(f"durable record field {field!r} has the wrong type")
        if raw["schema_version"] != DURABLE_RECORD_SCHEMA_VERSION:
            raise DurableRecordCorruptionError(
                f"unknown durable record schema_version {raw['schema_version']!r}"
            )
        if raw["outcome_state"] not in DURABLE_OUTCOME_STATES:
            raise DurableRecordCorruptionError(f"unknown outcome_state {raw['outcome_state']!r}")
        if not _is_iso_utc_metadata(raw["recorded_at_utc"]):
            raise DurableRecordCorruptionError("recorded_at_utc is not parseable ISO-8601 metadata")
        if raw["outcome_state"] == OUTCOME_RECORDED and raw["result_digest"] is None:
            raise DurableRecordCorruptionError("RECORDED record must carry a result_digest")
        return DurableClaimRecord(**raw)


def _identity_filename_component(claim_identity: str) -> str:
    """Hash a claim identity into a traversal-proof shard filename component.

    The mapping is deterministic (same identity -> same filename every time,
    in every process) and cannot escape the store directory: only lowercase
    hex, ``-`` and ``_`` appear, and a collision-resistant 32-hex prefix is
    always present.
    """
    if not isinstance(claim_identity, str) or not claim_identity:
        raise DurableRecordCorruptionError("claim_identity must be a non-empty string")
    digest = sha256_hex(claim_identity.encode("utf-8"))
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", claim_identity)[:40]
    return f"{digest[:32]}-{sanitized}"


class HardenedDurableClaimStore:
    """Local append-only durable store enforcing the exactly-once claim.

    * The directory is an explicit constructor parameter (test controlled);
      this class NEVER defaults to a home or repository path.  Claim
      identities are hashed into shard filenames via
      :func:`_identity_filename_component`, so no identity text can traverse
      the path.
    * Layout: one JSONL shard per claim identity plus one global
      ``hardened_claims.lock`` flock sidecar (local-locking precedent:
      ``qntylab/dsh_stage_a_v1_hard_orchestration.py``).
    * Decisions are atomic: under the exclusive sidecar lock the identity
      state is re-read from disk.  Same identity + same claim_digest ->
      idempotent.  Same identity + different claim_digest -> deterministic
      :class:`ConflictingReplayError`.  A new claim attempt over an existing
      CLAIMED_WITHOUT_OUTCOME record -> :class:`AlreadyClaimedError` (no
      automatic retry exists).
    * Appends are flushed and ``fsync``-ed before the lock is released, so a
      record that the caller has observed is durable.
    * Torn/partial/corrupt lines raise :class:`DurableRecordCorruptionError`;
      they are never skipped or repaired silently.
    * No module-global dicts/sets/caches as source of truth: every decision
      reads the durable files; a fresh process observes identical state.
    """

    def __init__(self, directory: Path):
        """Create (or adopt) the store under the explicit ``directory``.

        The directory is created if missing; shards and the flock sidecar live
        inside it.  No other filesystem location is ever used.
        """
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.directory / "hardened_claims.lock"

    # -- paths -------------------------------------------------------------

    def shard_path(self, claim_identity: str) -> Path:
        """Deterministic, traversal-proof shard path for ``claim_identity``."""
        return self.directory / (_identity_filename_component(claim_identity) + ".jsonl")

    # -- durable reads ------------------------------------------------------

    def read_records(self) -> tuple[DurableClaimRecord, ...]:
        """Read every record across shards in deterministic filename order.

        Any torn, partial or corrupt line raises
        :class:`DurableRecordCorruptionError`; nothing is skipped.
        """
        records: list[DurableClaimRecord] = []
        for shard in sorted(self.directory.glob("*.jsonl")):
            with shard.open("r", encoding="utf-8") as handle:
                for number, line in enumerate(handle, start=1):
                    stripped = line.strip()
                    if not stripped:
                        raise DurableRecordCorruptionError(f"blank line at {shard.name}:{number}")
                    try:
                        records.append(DurableClaimRecord.from_json_line(stripped))
                    except DurableRecordCorruptionError as exc:
                        raise DurableRecordCorruptionError(f"{shard.name}:{number}: {exc}") from exc
        return tuple(records)

    def latest_record_for(self, claim_identity: str) -> DurableClaimRecord | None:
        """Latest record for ``claim_identity`` or ``None`` (corruption still raises)."""
        shard = self.shard_path(claim_identity)
        if not shard.exists():
            return None
        matches: list[DurableClaimRecord] = []
        with shard.open("r", encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    raise DurableRecordCorruptionError(f"blank line at {shard.name}:{number}")
                try:
                    matches.append(DurableClaimRecord.from_json_line(stripped))
                except DurableRecordCorruptionError as exc:
                    raise DurableRecordCorruptionError(f"{shard.name}:{number}: {exc}") from exc
        return matches[-1] if matches else None

    def lookup(self, claim_identity: str) -> DurableClaimRecord | None:
        """Fresh-process state lookup: CLAIMED_WITHOUT_OUTCOME, RECORDED or None."""
        return self.latest_record_for(claim_identity)

    # -- locking ------------------------------------------------------------

    class _FileLock:
        """Context manager holding an exclusive flock on the sidecar."""

        def __init__(self, lock_path: Path):
            self.lock_path = lock_path
            self.handle: Any = None

        def __enter__(self) -> "HardenedDurableClaimStore._FileLock":
            self.handle = self.lock_path.open("a+")
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()

    def _locked(self) -> "HardenedDurableClaimStore._FileLock":
        return HardenedDurableClaimStore._FileLock(self.lock_path)

    def _append_locked(self, shard: Path, record: DurableClaimRecord) -> None:
        """Append one line durably.  Caller MUST hold the flock."""
        with shard.open("a", encoding="utf-8") as handle:
            handle.write(record.to_json_line() + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    # -- durable writes: atomic claim and record ----------------------------

    def claim_once(self, claim_identity: str, claim_digest: str, authorization_binding: str) -> DurableClaimRecord:
        """Atomically acquire the durable claim for this identity.

        Under the exclusive sidecar lock the identity state is re-read from
        disk and decided:

        * no prior record -> append CLAIMED_WITHOUT_OUTCOME, return it;
        * identical claim_digest and state RECORDED -> idempotent replay:
          return the original durable record unchanged (no new line);
        * identical claim_digest but state CLAIMED_WITHOUT_OUTCOME -> raise
          :class:`AlreadyClaimedError` (duplicate rerun fails closed; no
          automatic retry);
        * different claim_digest for the same identity -> deterministic
          :class:`ConflictingReplayError` (CONFLICT fails closed).
        """
        shard = self.shard_path(claim_identity)
        with self._locked():
            existing = self.latest_record_for(claim_identity)
            if existing is not None:
                if existing.claim_digest != claim_digest:
                    raise ConflictingReplayError(
                        f"conflicting replay for claim identity {claim_identity!r}: durable digest "
                        f"{existing.claim_digest}, presented {claim_digest}"
                    )
                if existing.outcome_state == OUTCOME_CLAIMED_WITHOUT_OUTCOME:
                    raise AlreadyClaimedError(
                        f"claim identity {claim_identity!r} is CLAIMED_WITHOUT_OUTCOME; duplicate rerun "
                        "fails closed and no automatic retry exists"
                    )
                return existing  # idempotent RECORDED replay
            record = DurableClaimRecord(
                claim_identity=claim_identity,
                claim_digest=claim_digest,
                result_digest=None,
                authorization_binding=authorization_binding,
                recorded_at_utc=_utc_now_iso(),
                outcome_state=OUTCOME_CLAIMED_WITHOUT_OUTCOME,
            )
            self._append_locked(shard, record)
            return record

    def record_result(
        self, claim_identity: str, claim_digest: str, result_digest: str
    ) -> DurableClaimRecord:
        """Atomically append the RECORDED outcome for an existing claim.

        Fails closed with :class:`AlreadyClaimedError` if no claim exists or
        the record is already RECORDED (records are append-only and are never
        rewritten).  Fails closed with :class:`ConflictingReplayError` on a
        claim-digest mismatch.
        """
        shard = self.shard_path(claim_identity)
        with self._locked():
            existing = self.latest_record_for(claim_identity)
            if existing is None:
                raise AlreadyClaimedError(
                    f"no durable claim exists for identity {claim_identity!r}; refusing to record a result"
                )
            if existing.claim_digest != claim_digest:
                raise ConflictingReplayError(
                    f"conflicting replay for claim identity {claim_identity!r} during result recording"
                )
            if existing.outcome_state == OUTCOME_RECORDED:
                raise AlreadyClaimedError(
                    f"claim identity {claim_identity!r} is already RECORDED; durable records are "
                    "append-only and are never rewritten"
                )
            recorded = DurableClaimRecord(
                claim_identity=existing.claim_identity,
                claim_digest=existing.claim_digest,
                result_digest=result_digest,
                authorization_binding=existing.authorization_binding,
                recorded_at_utc=_utc_now_iso(),
                outcome_state=OUTCOME_RECORDED,
            )
            self._append_locked(shard, recorded)
            return recorded


# ==========================================================================
# SECTION 6 -- hardened evaluation boundary
# ==========================================================================


@dataclass(frozen=True, slots=True)
class BoundaryInstrumentation:
    """Per-run counters proving ordering behavior.

    Tests observe ``HardenedEvaluationBoundary.instrumentation`` after a call
    (including after a caught exception) to prove that an authority failure
    leaves ``rows_constructed == 0`` and ``core_invocations == 0``.  These
    counters are process-local observability only; they are never persisted
    and never enter any identity.
    """

    rows_constructed: int = 0
    core_invocations: int = 0
    events: tuple[str, ...] = ()

    def with_event(self, event: str) -> "BoundaryInstrumentation":
        """Return an instrumentation copy with ``event`` appended."""
        return BoundaryInstrumentation(
            rows_constructed=self.rows_constructed,
            core_invocations=self.core_invocations,
            events=self.events + (event,),
        )

    def with_rows(self, count: int) -> "BoundaryInstrumentation":
        """Return an instrumentation copy with ``rows_constructed`` set."""
        return BoundaryInstrumentation(
            rows_constructed=count,
            core_invocations=self.core_invocations,
            events=self.events,
        )

    def with_core_invocation(self) -> "BoundaryInstrumentation":
        """Return an instrumentation copy with ``core_invocations`` incremented."""
        return BoundaryInstrumentation(
            rows_constructed=self.rows_constructed,
            core_invocations=self.core_invocations + 1,
            events=self.events,
        )


@dataclass(frozen=True, slots=True)
class HardenedEvaluationOutcome:
    """Result of one hardened evaluation run.

    ``evaluation`` is the frozen dataclass returned by the frozen entrypoint,
    or ``None`` for an IDEMPOTENT RECORDED REPLAY (an identical rerun after
    the AFTER_RECORD crash window): in that case the original durable outcome
    state is observable through ``record`` (RECORDED + the original
    ``result_digest``) and the frozen core is deliberately NOT re-executed.
    """

    evaluation: IncrementalForecastEvaluation | None
    record: DurableClaimRecord
    batch_digest: str
    instrumentation: BoundaryInstrumentation


class HardenedEvaluationBoundary:
    """Orchestrates AUTHORIZATION -> CLAIM -> EVIDENCE -> ROWS -> CORE -> RECORD.

    Ordering is structural: each stage's output is the only input of the next,
    and every stage can fail closed before the first row is constructed or the
    frozen core is invoked.  ``execution_mode`` is passed through opaquely to
    the frozen entrypoint; provenance identity never depends on it.

    Crash windows (behavior, not prose):

    * BEFORE_CLAIM: no side effects anywhere; a rerun is allowed and an
      authority failure produces zero rows and zero core invocations.
    * AFTER_CLAIM_BEFORE_EVALUATION: the claim is durable
      (CLAIMED_WITHOUT_OUTCOME); a duplicate rerun raises
      :class:`AlreadyClaimedError`; a fresh process observes the state via
      :meth:`lookup_claim`.  There is NO automatic retry.
    * AFTER_EVALUATION_BEFORE_RECORD: the duplicate-claim guard above already
      prevents silent re-execution; recovery requires the explicit
      :meth:`reconcile` method, which only represents observed state or
      refuses -- it never invents outcomes.
    * AFTER_RECORD_BEFORE_RETURN: the RECORDED record is durable; a fresh
      observer sees RECORDED via :meth:`lookup_claim`; an identical replay of
      :meth:`run_evaluation` returns the original durable outcome state with
      zero core invocations.
    """

    def __init__(self, claim_store: HardenedDurableClaimStore):
        """Bind the explicit, test-controlled durable store; nothing global."""
        self.claim_store = claim_store
        #: Instrumentation of the most recent :meth:`run_evaluation` attempt
        #: (process-local observability only; never persisted).
        self.instrumentation = BoundaryInstrumentation()

    # -- batch admission -----------------------------------------------------

    def admit_batch(
        self, provenance: VerifiedInputProvenance, rows: Sequence[ForecastRow]
    ) -> ProvenancedForecastBatch:
        """Verify the receipt against ``rows`` and compose the batch.

        This is the boundary's only batch admission path and the only way a
        caller can hand rows to :meth:`run_evaluation`.  Verification failure
        raises :class:`ProvenanceRejectedError` before any claim exists.
        """
        return admit_verified_batch(provenance, rows)

    # -- main path -------------------------------------------------------------

    def run_evaluation(
        self,
        *,
        authorization_token: OfflineAuthorizationToken,
        batch: ProvenancedForecastBatch,
        claim_identity: str,
        execution_mode: object,
    ) -> HardenedEvaluationOutcome:
        """Execute the hardened pipeline and return result + durable record.

        Raises (fail closed, in this order): :class:`AuthorityRejectedError`
        (no token / malformed binding), :class:`AlreadyClaimedError`,
        :class:`ConflictingReplayError`, :class:`DurableRecordCorruptionError`,
        :class:`ProvenanceRejectedError`, or any frozen-entrypoint error.
        An AUTHORITY FAILURE occurs before any row is constructed and before
        the core is invoked, so both instrumentation counters remain zero.

        On an identical replay of an already RECORDED claim (AFTER_RECORD
        crash window), returns the original durable outcome state without
        re-executing the frozen core: ``outcome.evaluation`` is ``None`` and
        ``outcome.record`` is the original RECORDED record.
        """
        self.instrumentation = BoundaryInstrumentation()
        # 1. AUTHORIZATION VERIFIED -- authority is INDEPENDENTLY AUTHENTICATED
        #    at admission time, never attested.  The boundary re-runs the full
        #    canonical Git authentication itself (canonical repository locator,
        #    pinned commit, pinned artifact digest, anchor lineage, governing
        #    decision bindings) and only then requires the presented token to
        #    be the receipt OF THAT FRESHLY AUTHENTICATED GRANT.  A directly
        #    constructed OfflineAuthorizationToken with plausible fields is a
        #    worthless receipt: it cannot match the fresh canonical binding
        #    unless the canonical authentication has genuinely just passed.
        if not isinstance(authorization_token, OfflineAuthorizationToken):
            raise AuthorityRejectedError(
                "authorization must be an OfflineAuthorizationToken receipt from "
                "authenticate_canonical_hardening_authorization"
            )
        canonical_grant = authenticate_canonical_hardening_authorization()
        if authorization_token != canonical_grant:
            raise AuthorityRejectedError(
                "presented authorization token does not match the freshly authenticated canonical "
                "grant; the receipt is forged, stale, or describes a non-canonical repository "
                "(self-attestation is never authority)"
            )
        binding = canonical_grant.binding_digest()
        self.instrumentation = self.instrumentation.with_event("AUTHORIZATION_VERIFIED")
        # 2. IRREVERSIBLE CLAIM -- durable, atomic, exactly once.  The claim
        #    digest is semantic: canonical JSON over identity, authorization
        #    binding and batch digest only (no timestamps, no mode).
        claim_digest = self._claim_digest(
            claim_identity=claim_identity,
            authorization_binding=binding,
            batch_digest=batch.canonical_batch_digest(),
        )
        record = self.claim_store.claim_once(claim_identity, claim_digest, binding)
        self.instrumentation = self.instrumentation.with_event("CLAIM_DURABLE")
        if record.outcome_state == OUTCOME_RECORDED:
            # Identical replay of an already-recorded result: idempotent
            # RECORDED.  Never re-execute the core; never append a new line.
            return HardenedEvaluationOutcome(
                evaluation=None,
                record=record,
                batch_digest=batch.canonical_batch_digest(),
                instrumentation=self.instrumentation.with_event("IDEMPOTENT_RECORDED_REPLAY"),
            )
        # 3. EVIDENCE AUTHENTICATED -- re-verify the receipt<->rows binding
        #    immediately before use (defense in depth; admission verified it
        #    at composition time).
        verified_rows = batch.reverify()
        self.instrumentation = self.instrumentation.with_event("EVIDENCE_AUTHENTICATED")
        # 4. ROWS CONSTRUCTED -- the verified tuple is the exact row set handed
        #    to the frozen core.  Nothing else constructs rows in this module.
        rows = tuple(verified_rows)
        self.instrumentation = self.instrumentation.with_event("ROWS_CONSTRUCTED").with_rows(len(rows))
        # 5. SCIENTIFIC CORE -- frozen public entrypoint only; execution_mode
        #    passes through opaquely and the frozen mode guard still applies.
        self.instrumentation = self.instrumentation.with_core_invocation().with_event("CORE_INVOKED")
        evaluation = run_incremental_forecast_evaluation(rows, execution_mode=execution_mode)
        self.instrumentation = self.instrumentation.with_event("CORE_RETURNED")
        # 6. RESULT RECORDED -- durable append of the frozen result digest.
        record = self.claim_store.record_result(
            claim_identity=claim_identity,
            claim_digest=claim_digest,
            result_digest=evaluation.result_digest,
        )
        self.instrumentation = self.instrumentation.with_event("RESULT_RECORDED")
        return HardenedEvaluationOutcome(
            evaluation=evaluation,
            record=record,
            batch_digest=batch.canonical_batch_digest(),
            instrumentation=self.instrumentation,
        )

    # -- observation and reconciliation ----------------------------------------

    def lookup_claim(self, claim_identity: str) -> DurableClaimRecord | None:
        """Fresh-process observable state for ``claim_identity`` (None if absent)."""
        return self.claim_store.lookup(claim_identity)

    def reconcile(self, claim_identity: str, claim_digest: str | None = None) -> DurableClaimRecord | None:
        """Explicit reconciliation: represent observed state or refuse.

        NEVER retries, re-executes, or invents an outcome.  With
        ``claim_digest`` provided, a deterministic mismatch raises
        :class:`ConflictingReplayError`.  Returns the observed durable record
        (CLAIMED_WITHOUT_OUTCOME or RECORDED) or ``None`` when no record
        exists.  Any decision about redoing work belongs to a human or an
        explicit successor phase -- not to this method.
        """
        record = self.claim_store.lookup(claim_identity)
        if record is None:
            return None
        if claim_digest is not None and record.claim_digest != claim_digest:
            raise ConflictingReplayError(
                f"reconciliation refused for {claim_identity!r}: durable digest {record.claim_digest} "
                f"does not match presented digest {claim_digest}"
            )
        return record

    # -- identity ----------------------------------------------------------------

    @staticmethod
    def _claim_digest(*, claim_identity: str, authorization_binding: str, batch_digest: str) -> str:
        """Semantic claim digest: canonical JSON only; no metadata enters it."""
        return "sha256:" + sha256_hex(
            canonical_json_bytes(
                {
                    "authorization_binding": authorization_binding,
                    "batch_digest": batch_digest,
                    "claim_identity": claim_identity,
                }
            )
        )


# ==========================================================================
# SECTION 7 -- public API
# ==========================================================================


__all__ = [
    "AUTHORITY_FAILURE_PRECEDES_ROWS",
    "AUTHORITY_FAILURE_ZERO_OBSERVABLE_SCIENCE",
    "AlreadyClaimedError",
    "AuthorityRejectedError",
    "BoundaryInstrumentation",
    "CANONICAL_ANCHOR_COMMITS",
    "CANONICAL_AUTHORIZATION_ARTIFACT_RELATIVE_PATH",
    "CANONICAL_GRANT_IDENTITY",
    "CANONICAL_REPOSITORY_LOCATOR",
    "CANONICAL_SYNTHETIC_FIXTURE_CONTRACT",
    "CONFLICTING_REPLAY_FAILS_CLOSED",
    "ConflictingReplayError",
    "DURABLE_OUTCOME_STATES",
    "DURABLE_RECORD_SCHEMA_VERSION",
    "DurableClaimRecord",
    "DurableRecordCorruptionError",
    "EXECUTION_MODE_IS_NOT_PROVENANCE",
    "EXECUTION_MODE_SYNTHETIC_VALIDATION",
    "EXACTLY_ONCE_PROCESS_BOUNDARY",
    "EXACTLY_ONCE_SECOND_WORKER",
    "FROZEN_V0_BYTES_UNCHANGED",
    "GRANDFATHERED_PRIVATE_ASSEMBLY_LOCATIONS",
    "HardenedDurableClaimStore",
    "HardenedEvaluationBoundary",
    "HardenedEvaluationOutcome",
    "HardeningBoundaryError",
    "NO_PROCESS_LOCAL_PERSISTENCE_STATE",
    "OUTCOME_CLAIMED_WITHOUT_OUTCOME",
    "OUTCOME_RECORDED",
    "OfflineAuthorizationToken",
    "PRIVATE_EXECUTION_SEAM_FORBIDDEN",
    "PROVENANCE_CONSTRUCTOR_HONESTY",
    "PROVENANCE_KIND_GIT_ANCHORED",
    "PROVENANCE_KIND_OFFLINE_SYNTHETIC_FIXTURE",
    "ProvenancedForecastBatch",
    "ProvenanceRejectedError",
    "PROJECT_ID",
    "RESULT_RECORDING_PROSE_MATCHES_BEHAVIOR",
    "RESULT_RECORD_IS_DURABLE",
    "VerifiedInputProvenance",
    "admit_verified_batch",
    "authenticate_canonical_hardening_authorization",
    "canonical_json_bytes",
    "decode_synthetic_fixture_rows",
    "EXPECTED_CANONICAL_AUTHORIZATION_COMMIT",
    "EXPECTED_CANONICAL_AUTHORIZATION_SHA256",
    "EXPECTED_SYNTHETIC_FIXTURE_ROW_CONTENT_DIGEST",
    "EXPECTED_SYNTHETIC_FIXTURE_SHA256",
    "git_anchored_artifact_bytes",
    "GIT_ANCHORED_BUNDLE_SCHEMA_IDENTITY",
    "make_git_anchored_receipt",
    "make_offline_synthetic_fixture_receipt_from_authenticated_fixture",
    "run_incremental_forecast_evaluation",
    "sha256_hex",
    "SYNTHETIC_FIXTURE_IDENTITY",
    "SYNTHETIC_FIXTURE_SCHEMA_IDENTITY",
    "SyntheticFixtureContract",
    "verify_git_anchored_receipt",
    "verify_offline_synthetic_fixture_receipt",
]
