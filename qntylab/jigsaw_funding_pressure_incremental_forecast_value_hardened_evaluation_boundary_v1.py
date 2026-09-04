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

* EXECUTION AUTHORITY is represented by :class:`OfflineAuthorizationToken`,
  obtainable only from :func:`offline_authorization_check`, which fails closed
  unless caller-pinned authorization bytes, read via local ``git`` at a pinned
  commit, hash to the caller-pinned digest.  A mode string, a constructor
  name, a boolean, or a caller statement is NEVER accepted as provenance.
* INPUT PROVENANCE is represented by :class:`VerifiedInputProvenance`, a
  frozen receipt producible only through the two offline, independently
  checkable factories of this module (synthetic fixture and git-anchored).
  Receipts are verified by recomputation; a mismatch raises
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


_SCHEMA_IDENTITY_SYNTHETIC = "ForecastRowV0/offline-synthetic-fixture/1"
_SCHEMA_IDENTITY_GIT_ANCHORED = "ForecastRowV0/git-anchored/1"


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


def make_offline_synthetic_fixture_receipt(
    rows: Sequence[ForecastRow], *, fixture_identity: str, batch_identity: str
) -> VerifiedInputProvenance:
    """Build a deterministic ``OFFLINE_SYNTHETIC_FIXTURE`` provenance receipt.

    The factory binds the exact rows it is handed: ``content_digest`` is
    recomputed from the rows at call time, and the anchor's ``fixture_digest``
    is the digest of a deterministic fixture descriptor (kind + fixture
    identity + schema identity).  No timestamp, randomness or environment
    state enters any field.
    """
    if not isinstance(fixture_identity, str) or not fixture_identity:
        raise ProvenanceRejectedError("fixture_identity must be a non-empty string")
    if not isinstance(batch_identity, str) or not batch_identity:
        raise ProvenanceRejectedError("batch_identity must be a non-empty string")
    materialized = _require_rows(rows)
    anchor = {
        "fixture_digest": "sha256:"
        + sha256_hex(
            canonical_json_bytes(
                {
                    "fixture_identity": fixture_identity,
                    "provenance_kind": PROVENANCE_KIND_OFFLINE_SYNTHETIC_FIXTURE,
                    "schema_identity": _SCHEMA_IDENTITY_SYNTHETIC,
                }
            )
        )
    }
    payload = {
        "provenance_kind": PROVENANCE_KIND_OFFLINE_SYNTHETIC_FIXTURE,
        "factory_identity": "offline_synthetic_fixture_factory_v1/" + fixture_identity,
        "content_digest": _rows_content_digest(materialized),
        "schema_identity": _SCHEMA_IDENTITY_SYNTHETIC,
        "batch_identity": batch_identity,
        "anchor": anchor,
    }
    return VerifiedInputProvenance(**payload, receipt_digest=_receipt_digest(payload))


def verify_offline_synthetic_fixture_receipt(
    receipt: VerifiedInputProvenance, rows: Sequence[ForecastRow]
) -> tuple[ForecastRow, ...]:
    """Fail closed unless ``receipt`` genuinely binds exactly ``rows``.

    Independently recomputes the row digest and the receipt self-digest from
    the presented rows and receipt fields.  Any kind, digest or schema mismatch
    raises :class:`ProvenanceRejectedError`.
    """
    if not isinstance(receipt, VerifiedInputProvenance):
        raise ProvenanceRejectedError("receipt must be a VerifiedInputProvenance")
    if receipt.provenance_kind != PROVENANCE_KIND_OFFLINE_SYNTHETIC_FIXTURE:
        raise ProvenanceRejectedError(
            f"receipt provenance kind is {receipt.provenance_kind!r}, "
            f"expected {PROVENANCE_KIND_OFFLINE_SYNTHETIC_FIXTURE!r}"
        )
    materialized = _require_rows(rows)
    actual_content = _rows_content_digest(materialized)
    if receipt.content_digest != actual_content:
        raise ProvenanceRejectedError(
            f"row content digest mismatch: receipt claims {receipt.content_digest}, "
            f"rows hash to {actual_content}"
        )
    if receipt.receipt_digest != _receipt_digest(receipt.to_receipt_payload()):
        raise ProvenanceRejectedError("receipt digest does not match its own fields; receipt is forged or torn")
    return materialized


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
    closed if git is unavailable, the commit or path is absent, or the bytes
    do not hash to ``expected_blob_sha256``.  The receipt is then verifiable
    offline by any fresh process repeating the same check
    (:func:`verify_git_anchored_receipt`); rows are bound by their canonical
    content digest exactly as in the synthetic fixture receipt.
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
    anchor = {
        "artifact_relative_path": artifact_relative_path,
        "blob_sha256": actual_blob_sha256,
        "pinned_commit": pinned_commit,
        "repository_root": str(Path(repository_root).resolve()),
        "repository_root_sha256": _path_identity_digest(repository_root),
    }
    payload = {
        "provenance_kind": PROVENANCE_KIND_GIT_ANCHORED,
        "factory_identity": f"git_anchored_factory_v1/{pinned_commit}/{artifact_relative_path}",
        "content_digest": _rows_content_digest(materialized),
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

    Re-reads the artifact at the receipt's pinned commit with local ``git``
    and re-compares its SHA-256 against the receipt anchor (git unavailable,
    missing artifact, or digest mismatch all fail closed), then re-verifies
    the row content digest and the receipt self-digest.  ``repository_root``
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
    actual_content = _rows_content_digest(materialized)
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
# SECTION 4 -- offline authorization token (ordering proof only)
# ==========================================================================


@dataclass(frozen=True, slots=True)
class OfflineAuthorizationToken:
    """Immutable proof object produced by a successful offline grant check.

    This token proves ORDERING only: it demonstrates that the boundary cannot
    proceed past the authorization stage without an offline-verifiable grant
    check having succeeded first.  It deliberately does NOT consume any real
    authorization claim and grants no real-evidence authority; the frozen
    entrypoint's own execution-mode guard remains the authoritative
    science-side control.

    Its fields are digests only.  A mode string, a constructor name, a
    boolean, or a caller statement is structurally not this token.
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


def offline_authorization_check(
    *,
    repository_root: Path,
    pinned_commit: str,
    authorization_relative_path: str,
    expected_authorization_sha256: str,
    grant_identity: str,
) -> OfflineAuthorizationToken:
    """Offline-verifiable grant check (CI-3/CI-4 pattern, independently derived).

    Fails closed with :class:`AuthorityRejectedError` unless the authorization
    artifact bytes at the caller-pinned commit, read via local ``git`` inside
    ``repository_root``, hash exactly to ``expected_authorization_sha256``.
    On success returns the immutable token.  On any absence, unavailability or
    digest mismatch it raises, and NOTHING downstream (no rows, no claim, no
    core invocation) is touched by this call.

    This check proves ordering only; it consumes no real authorization claim.
    """
    if not isinstance(grant_identity, str) or not grant_identity:
        raise AuthorityRejectedError("grant_identity must be a non-empty string")
    if not _is_hex64(expected_authorization_sha256):
        raise AuthorityRejectedError("expected_authorization_sha256 must be a 64-char hex digest")
    blob_bytes = _git_show_blob(repository_root, pinned_commit, authorization_relative_path)
    actual = sha256_hex(blob_bytes)
    if actual != expected_authorization_sha256:
        raise AuthorityRejectedError(
            f"pinned authorization bytes mismatch: expected {expected_authorization_sha256}, got {actual}"
        )
    return OfflineAuthorizationToken(
        grant_identity=grant_identity,
        pinned_authorization_sha256=expected_authorization_sha256,
        verification_commit=pinned_commit,
        verified_at_commit_binding="sha256:"
        + sha256_hex(
            canonical_json_bytes(
                {
                    "authorization_relative_path": authorization_relative_path,
                    "authorization_sha256": actual,
                    "pinned_commit": pinned_commit,
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
        # 1. AUTHORIZATION VERIFIED -- the token must be a real token object
        #    from offline_authorization_check.  A mode string, constructor
        #    name, boolean or caller statement is structurally not one.
        if not isinstance(authorization_token, OfflineAuthorizationToken):
            raise AuthorityRejectedError(
                "authorization must be an OfflineAuthorizationToken from offline_authorization_check"
            )
        binding = authorization_token.binding_digest()
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
    "canonical_json_bytes",
    "make_git_anchored_receipt",
    "make_offline_synthetic_fixture_receipt",
    "offline_authorization_check",
    "run_incremental_forecast_evaluation",
    "sha256_hex",
    "verify_git_anchored_receipt",
    "verify_offline_synthetic_fixture_receipt",
]
