"""Independent conformance implementation for frozen R1 source recognition.

This module consumes caller-selected, exact registry bytes.  It neither selects
protocol authority nor reads an ambient registry path; callers must supply the
already verified R snapshot required by frozen G.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import zlib


FRAMING_FAILURE = "FRAMING_FAILURE"
MALFORMED_HEADER = "MALFORMED_HEADER"
NO_MATCH = "NO_MATCH"
RECOGNIZED = "RECOGNIZED"
AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class SchemaSignature:
    schema_id: str
    field_set: frozenset[str]


@dataclass(frozen=True)
class VerifiedRegistrySnapshot:
    """A registry parsed from the exact bytes selected by the caller."""

    exact_artifact_bytes: bytes
    registry_snapshot_sha256: str
    signatures: tuple[SchemaSignature, ...]

    @classmethod
    def from_exact_artifact_bytes(
        cls, exact_artifact_bytes: bytes, expected_registry_sha256: str
    ) -> "VerifiedRegistrySnapshot":
        actual_sha256 = hashlib.sha256(exact_artifact_bytes).hexdigest()
        if actual_sha256 != expected_registry_sha256:
            raise ValueError("registry bytes do not match the selected registry snapshot")
        try:
            registry = json.loads(exact_artifact_bytes)
            variants = registry["known_schema_variants"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError("registry snapshot is not a usable R1 registry") from exc
        if not isinstance(variants, dict):
            raise ValueError("registry known_schema_variants must be an object")

        signatures = []
        for schema_id, entry in variants.items():
            field_set = entry.get("field_set") if isinstance(entry, dict) else None
            if not isinstance(schema_id, str) or not isinstance(field_set, list):
                raise ValueError("registry schema signature is malformed")
            if not all(isinstance(field, str) for field in field_set):
                raise ValueError("registry field_set must contain strings")
            signatures.append(SchemaSignature(schema_id, frozenset(field_set)))
        return cls(exact_artifact_bytes, actual_sha256, tuple(signatures))


@dataclass(frozen=True)
class RecognitionResult:
    disposition: str
    reasons: tuple[str, ...] = ()
    schema_id: str | None = None
    matching_schema_ids: tuple[str, ...] = ()


def _framing_failure(reason: str) -> RecognitionResult:
    return RecognitionResult(FRAMING_FAILURE, (reason,))


def _derive_header(raw_bytes: bytes) -> tuple[str, ...] | RecognitionResult:
    """Frozen G derive_header steps 1--8, using zlib only as a format witness."""
    try:
        inflater = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
        payload = inflater.decompress(raw_bytes)
    except zlib.error:
        return _framing_failure("INVALID_GZIP")

    # G requires a validated stream end (including trailer), rather than merely
    # exception-free output.  ``eof`` witnesses that format-level condition.
    if not inflater.eof:
        return _framing_failure("INVALID_GZIP")
    if inflater.unused_data:
        return _framing_failure("MULTI_MEMBER_GZIP")

    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return _framing_failure("INVALID_UTF8")
    if text.startswith("\ufeff"):
        return _framing_failure("BOM_PRESENT")
    if not text:
        return _framing_failure("EMPTY_OBJECT")

    header_line = text.split("\n", 1)[0]
    if "\r" in header_line:
        return _framing_failure("NON_LF_LINE_TERMINATOR")
    raw_header = tuple(header_line.split(","))
    if len(raw_header) < 2:
        return _framing_failure("FEWER_THAN_TWO_TOKENS")
    return raw_header


def _well_formed_header(raw_header: tuple[str, ...]) -> frozenset[str] | RecognitionResult:
    """Frozen G header_well_formedness: report every applicable reason."""
    reasons: list[str] = []
    if any(token == "" for token in raw_header):
        reasons.append("EMPTY_TOKEN_NAME")
    if len(set(raw_header)) != len(raw_header):
        reasons.append("DUPLICATE_TOKEN_NAME")
    if any('"' in token for token in raw_header):
        reasons.append("QUOTE_CHARACTER_IN_TOKEN")
    if reasons:
        return RecognitionResult(MALFORMED_HEADER, tuple(reasons))
    return frozenset(raw_header)


def recognize_source_object(
    raw_bytes: bytes, registry_snapshot: VerifiedRegistrySnapshot
) -> RecognitionResult:
    """Recognize exact X against an exact, caller-selected R snapshot.

    This is only X -> H -> S recognition.  It makes no authorization,
    admission, record-validity, or materialization decision.
    """
    if not isinstance(raw_bytes, bytes):
        raise TypeError("raw_bytes must be bytes")
    if not isinstance(registry_snapshot, VerifiedRegistrySnapshot):
        raise TypeError("registry_snapshot must be a VerifiedRegistrySnapshot")

    derived = _derive_header(raw_bytes)
    if isinstance(derived, RecognitionResult):
        return derived
    well_formed = _well_formed_header(derived)
    if isinstance(well_formed, RecognitionResult):
        return well_formed

    matches = tuple(
        sorted(signature.schema_id for signature in registry_snapshot.signatures
               if well_formed == signature.field_set)
    )
    if not matches:
        return RecognitionResult(NO_MATCH)
    if len(matches) == 1:
        return RecognitionResult(RECOGNIZED, schema_id=matches[0])
    return RecognitionResult(AMBIGUOUS, matching_schema_ids=matches)
