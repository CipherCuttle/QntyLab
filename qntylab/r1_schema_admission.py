"""Runtime implementation of the FROZEN R1 DailyMarketEvidenceV1 schema-admission
predicate (experiments/data/r1_daily_market_evidence_schema_admission_amendment_v1.json).

This module is IMPLEMENTATION evidence claiming conformance to that frozen
text -- it is never itself normative authority. It applies the frozen
recognizer (qntylab.r1_schema_recognizer, the executable G witness) directly
to the exact source-object bytes X being evaluated; it never restates G's
gzip/decode/header/matching logic and never accepts a caller-supplied
disposition, schema_id, or recognition-result/receipt-shaped value as
admission input (BLOCK_FORGED_RECOGNITION_RESULT, repair_history
repair_index 5) -- there is no parameter through which such a claim could be
asserted. It is written independently of, and does not import,
tests/test_r1_daily_market_evidence_schema_admission_amendment_v1.py: tests
are not a runtime dependency.

daily_market_evidence_v1_schema_admission(X) -> SchemaAdmissionEvaluation:
    recognition_result := recognize_G,R(X)   (derived here, from exact X and R)
    SCHEMA_ADMISSIBLE only when recognition_result is RECOGNIZED(schema_id),
    schema_id is a member of that same exact R, and the frozen registry-scope
    authority explicitly says AUTHORIZED_FOR_DAILYMARKET for schema_id.
    Every other outcome (FRAMING_FAILURE, MALFORMED_HEADER, NO_MATCH,
    AMBIGUOUS, registered-but-not-authorized, unlisted/future) is
    SCHEMA_INADMISSIBLE. This governs only the schema dimension of
    DailyMarketEvidenceV1 admissibility and is necessary, not sufficient.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from qntylab import r1_schema_recognizer as recognizer

ADMISSIBLE = "SCHEMA_ADMISSIBLE"
INADMISSIBLE = "SCHEMA_INADMISSIBLE"
AUTHORIZED_FOR_DAILYMARKET = "AUTHORIZED_FOR_DAILYMARKET"
NOT_AUTHORIZED_FOR_DAILYMARKET = "NOT_AUTHORIZED_FOR_DAILYMARKET"

# --- exact R1 frozen authority binding -------------------------------------
#
# One named artifact per authority, verified by exact bytes -- never
# "whichever is newest" and never an ambient/implicit selector. A caller
# needing to exercise an explicit G/R/scope binding mismatch (fail-closed
# behavior) may pass its own *_bytes override into evaluate_schema_admission;
# nothing here falls back silently to "whatever is on disk" when an override
# is supplied but does not hash-verify.
_ROOT = Path(__file__).resolve().parent.parent
_DATA = _ROOT / "experiments/data"

_ADMISSION_ARTIFACT_PATH = _DATA / "r1_daily_market_evidence_schema_admission_amendment_v1.json"
_CONTRACT_ARTIFACT_PATH = _DATA / "r1_normalized_evidence_contract_v1.json"
_REGISTRY_ARTIFACT_PATH = _DATA / "r1_source_schema_registry_v1.json"
_RECOGNITION_ARTIFACT_PATH = _DATA / "r1_source_structure_recognition_amendment_v1.json"
_SCOPE_ARTIFACT_PATH = _DATA / "r1_source_schema_registry_scope_amendment_v1.json"

_EXPECTED_ADMISSION_SEMANTIC_SHA256 = "99e8f4e6c9a741f33f1a9bd9528eb3c00a2775ee84557f724663c3154b2df445"
_EXPECTED_ADMISSION_EFFECTIVE_SHA256 = "a3786f875057484b5dcea1f85194ffc17237d7bc21ce7335a639d4ab64612067"
_EXPECTED_REGISTRY_SHA256 = "02d2a75cdaa3d53a2708d2d20d5bf19f934fc68e6ee1b942404994d80ab94c4d"
_EXPECTED_RECOGNITION_SEMANTIC_SHA256 = "9a919ec68af8cee6caf661286315b61dd104d61c070676a75bfe89448c7e9758"
_EXPECTED_RECOGNITION_EFFECTIVE_SHA256 = "222b5edcb7370accd73526a034bf129f537a9cb5aac4b8ad157399d32899662c"
_EXPECTED_SCOPE_SEMANTIC_SHA256 = "f1645ce186c73232bb5e4945f734f2ea1c94db856255da0332272bedacd87571"
_EXPECTED_SCOPE_EFFECTIVE_SHA256 = "3291c33ff0d4d33a1b9f43938c832bc6d0ba32e0c45b3628a80dc55e1c155ac0"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def _semantic_sha256(value) -> str:
    return _sha256(_canonical(value))


@dataclass(frozen=True)
class SchemaAdmissionEvaluation:
    """One result per attempted raw object. `reasons` mirrors the underlying
    RecognitionResult.reasons verbatim (e.g. ("EMPTY_OBJECT",) for that one
    FRAMING_FAILURE reason) so a caller can recognize the frozen text's one
    explicit carve-out without re-deriving recognition a second time."""

    source_object_sha256: str
    recognition_disposition: str
    schema_id: str | None
    admission: str  # SCHEMA_ADMISSIBLE | SCHEMA_INADMISSIBLE
    reasons: tuple[str, ...] = ()


def _verify_frozen_authority(
    admission_bytes: bytes,
    contract_bytes: bytes,
    registry_bytes: bytes,
    recognition_bytes: bytes,
    scope_bytes: bytes,
) -> dict:
    """Fail-closed verification that the supplied authority bytes are
    byte-identical to the FROZEN, independently hostile-reviewed R1 schema
    admission authority this module conforms to. Raises ValueError on any
    mismatch -- never proceeds to derive a recognition/scope decision against
    unverified authority."""
    candidate = json.loads(admission_bytes)
    if candidate.get("status") != "FROZEN" or candidate.get("self_freeze_authorized") is not False:
        raise ValueError("schema admission artifact is not a frozen, non-self-frozen candidate")
    if _semantic_sha256(candidate["semantic_body"]) != _EXPECTED_ADMISSION_SEMANTIC_SHA256:
        raise ValueError("schema admission semantic content mismatch")
    if _semantic_sha256(candidate["effective_combined_contract_binding"]) != _EXPECTED_ADMISSION_EFFECTIVE_SHA256:
        raise ValueError("schema admission effective binding mismatch")

    bound = candidate["bound_authority"]
    exact = {
        "base_contract_sha256": contract_bytes,
        "base_registry_sha256": registry_bytes,
        "frozen_source_structure_recognition_amendment_sha256": recognition_bytes,
        "frozen_source_schema_registry_scope_amendment_sha256": scope_bytes,
    }
    for field, payload in exact.items():
        if _sha256(payload) != bound[field]:
            raise ValueError(f"schema admission bound_authority.{field} mismatch")

    recognition = json.loads(recognition_bytes)
    if recognition.get("status") != "FROZEN":
        raise ValueError("recognition amendment is not frozen")
    if recognition["amendment_semantic_content_sha256"] != _EXPECTED_RECOGNITION_SEMANTIC_SHA256:
        raise ValueError("recognition amendment semantic content mismatch")
    if recognition["effective_combined_contract_binding_sha256"] != _EXPECTED_RECOGNITION_EFFECTIVE_SHA256:
        raise ValueError("recognition amendment effective binding mismatch")
    if recognition["amendment_semantic_content_sha256"] != bound["frozen_source_structure_recognition_semantic_sha256"]:
        raise ValueError("schema admission recognition semantic binding mismatch")
    if (recognition["effective_combined_contract_binding_sha256"]
            != bound["frozen_source_structure_recognition_effective_binding_sha256"]):
        raise ValueError("schema admission recognition effective binding mismatch")

    scope = json.loads(scope_bytes)
    if scope.get("status") != "FROZEN":
        raise ValueError("registry-scope amendment is not frozen")
    if scope["amendment_semantic_content_sha256"] != _EXPECTED_SCOPE_SEMANTIC_SHA256:
        raise ValueError("registry-scope amendment semantic content mismatch")
    if scope["effective_combined_contract_binding_sha256"] != _EXPECTED_SCOPE_EFFECTIVE_SHA256:
        raise ValueError("registry-scope amendment effective binding mismatch")
    if scope["amendment_semantic_content_sha256"] != bound["frozen_source_schema_registry_scope_semantic_sha256"]:
        raise ValueError("schema admission scope semantic binding mismatch")
    if (scope["effective_combined_contract_binding_sha256"]
            != bound["frozen_source_schema_registry_scope_effective_binding_sha256"]):
        raise ValueError("schema admission scope effective binding mismatch")

    return {"admission": candidate, "recognition": recognition, "scope": scope}


def _scope_authorization(schema_id: str, registry_bytes: bytes, scope: dict) -> str:
    """Frozen scope semantics: exact R membership plus the explicit,
    frozen structural_authorization_matrix; otherwise default deny."""
    known = json.loads(registry_bytes)["known_schema_variants"]
    if schema_id not in known:
        return NOT_AUTHORIZED_FOR_DAILYMARKET
    entry = scope["semantic_body"]["structural_authorization_matrix"].get(schema_id)
    return entry["daily_market_authorization"] if entry else NOT_AUTHORIZED_FOR_DAILYMARKET


_default_authority_bytes: dict | None = None


def _load_default_authority_bytes() -> dict:
    """Fail-closed loader for the one named, exact R1 authority set. Raises
    ValueError (via _verify_frozen_authority, invoked by callers) if bytes on
    disk have drifted from the expected frozen hashes -- never silently falls
    back to unverified bytes."""
    global _default_authority_bytes
    if _default_authority_bytes is None:
        _default_authority_bytes = {
            "admission_bytes": _ADMISSION_ARTIFACT_PATH.read_bytes(),
            "contract_bytes": _CONTRACT_ARTIFACT_PATH.read_bytes(),
            "registry_bytes": _REGISTRY_ARTIFACT_PATH.read_bytes(),
            "recognition_bytes": _RECOGNITION_ARTIFACT_PATH.read_bytes(),
            "scope_bytes": _SCOPE_ARTIFACT_PATH.read_bytes(),
        }
    return _default_authority_bytes


def evaluate_schema_admission(
    raw_bytes: bytes,
    *,
    admission_bytes: bytes | None = None,
    contract_bytes: bytes | None = None,
    registry_bytes: bytes | None = None,
    recognition_bytes: bytes | None = None,
    scope_bytes: bytes | None = None,
) -> SchemaAdmissionEvaluation:
    """daily_market_evidence_v1_schema_admission(X) per the FROZEN schema
    admission amendment. `raw_bytes` is the only source-identity input --
    recognition_result is derived here by applying frozen G to these exact
    bytes and exact R, never accepted from a caller. The `*_bytes` keyword
    overrides exist only to let a caller exercise an explicit G/R/scope
    binding mismatch (fail-closed via ValueError, before recognition or
    scope is ever consulted); none of them is a channel for asserting a
    disposition, schema_id, or recognition-result claim -- no such parameter
    exists. Defaults are the one named, exact, sha256-verified R1 authority
    set, read once per process and reused.
    """
    if not isinstance(raw_bytes, bytes):
        raise TypeError("raw_bytes must be bytes")

    defaults = _load_default_authority_bytes()
    admission_bytes = admission_bytes if admission_bytes is not None else defaults["admission_bytes"]
    contract_bytes = contract_bytes if contract_bytes is not None else defaults["contract_bytes"]
    registry_bytes = registry_bytes if registry_bytes is not None else defaults["registry_bytes"]
    recognition_bytes = recognition_bytes if recognition_bytes is not None else defaults["recognition_bytes"]
    scope_bytes = scope_bytes if scope_bytes is not None else defaults["scope_bytes"]

    authority = _verify_frozen_authority(
        admission_bytes, contract_bytes, registry_bytes, recognition_bytes, scope_bytes
    )

    registry_snapshot = recognizer.VerifiedRegistrySnapshot.from_exact_artifact_bytes(
        registry_bytes, _sha256(registry_bytes)
    )
    result = recognizer.recognize_source_object(raw_bytes, registry_snapshot)
    source_object_sha256 = _sha256(raw_bytes)

    if result.disposition != recognizer.RECOGNIZED or result.schema_id is None:
        return SchemaAdmissionEvaluation(
            source_object_sha256, result.disposition, result.schema_id, INADMISSIBLE, result.reasons
        )

    known = json.loads(registry_bytes)["known_schema_variants"]
    if result.schema_id not in known:
        return SchemaAdmissionEvaluation(
            source_object_sha256, result.disposition, result.schema_id, INADMISSIBLE, result.reasons
        )

    if _scope_authorization(result.schema_id, registry_bytes, authority["scope"]) != AUTHORIZED_FOR_DAILYMARKET:
        return SchemaAdmissionEvaluation(
            source_object_sha256, result.disposition, result.schema_id, INADMISSIBLE, result.reasons
        )

    return SchemaAdmissionEvaluation(
        source_object_sha256, result.disposition, result.schema_id, ADMISSIBLE, result.reasons
    )
