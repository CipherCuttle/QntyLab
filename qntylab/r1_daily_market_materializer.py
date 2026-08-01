"""DailyMarketEvidenceV1 materialization boundary (Gap-2 record assembler).

This module is the mechanical boundary between raw archive bytes and a
contract-conforming DailyMarketEvidenceV1 record for BOTH Parser A
(qntylab.r1_reference_parser) and Parser B (qntylab.r1_retention_candidate).
It performs no OHLC/duplicate/timestamp/event-order derivation of its own --
all of that remains entirely Parser A's or Parser B's job, called through
unmodified. It owns exactly three mechanical concerns that neither parser
owns on its own:

  1. source_object_sha256 binding: Parser A already computes and returns this
     field itself; this boundary re-verifies it against sha256(raw_bytes) and
     fails closed on any mismatch (ANOMALY_SOURCE_MUTATION). Parser B's
     daily_primitive() does not receive raw bytes and does not compute this
     field at all -- this boundary computes sha256(raw_bytes) once, here, and
     binds it into a complete record for the Parser B path. It never reuses
     r1_input_bom.canonical_hash/normalized_primitive_sha256 for this field:
     those hash the *normalized primitive*, not the *raw archive object*, and
     the frozen contract requires source_object_sha256 to bind the latter.

  2. contract-completeness validation (validate_daily_market_evidence_v1):
     a purely mechanical check of required keys / non-null conditions / basic
     types per r1_normalized_evidence_contract_v1.json:DailyMarketEvidenceV1.
     It asserts no scientific-consistency rule beyond what that contract text
     itself states.

  3. converting container-level corruption (gzip corruption, invalid-UTF-8
     decompressed body, structurally truncated CSV) into the already-frozen
     CONTAINER_ANOMALY / RAW_QUARANTINED_ANOMALY vocabulary
     (qntylab.r1_retention_candidate.ANOMALY_CONTAINER is already declared,
     and listed in experiments/data/r1_bounded_evidence_retention_candidate_v1.json
     :anomaly_triggers, but was never wired to any raising code path) instead
     of letting qntylab.r1_reference_parser.GzipCorruptionError /
     TruncatedCSVError -- or the equivalent ingestion failure for the Parser B
     path, which does not decompress/parse CSV itself -- escape as an
     uncaught, batch-terminating exception. No new contract-visible status
     name is introduced by this module.

     Note on UnicodeDecodeError specifically: qntylab.r1_reference_parser's
     own _decompress() calls .decode("utf-8", errors="strict") outside its
     GzipCorruptionError try/except, so a gzip-valid object whose
     decompressed body is not valid UTF-8 raises a bare UnicodeDecodeError
     out of rp.parse_daily_object(), not a GzipCorruptionError. This module
     does not edit r1_reference_parser.py to fix that internally; instead
     _materialize_parser_a_unadmitted() additionally catches UnicodeDecodeError at its
     own call site and maps it to the same CONTAINER_ANOMALY outcome, so
     both parser paths reach the identical typed quarantine for the
     identical raw-object corruption despite that difference in Parser A's
     internal exception-wrapping. This is a boundary-level compensation for
     an already-reachable Parser A gap, not a new exception class invented
     by this module and not a change to Parser A's own file.

     Note on csv.Error specifically (independent hostile-review blocker #2
     on commit 3081118): a gzip-valid, UTF-8-valid object whose CSV body is
     structurally corrupt in a way stdlib csv cannot tokenize at all --
     observed reproducer: a single field exceeding csv.field_size_limit()
     (131072 bytes), reachable from e.g. a dropped newline or an
     unterminated quote swallowing the remainder of the object -- raises a
     bare csv.Error out of csv.DictReader/csv.reader iteration. Both
     rp.parse_daily_object (Parser A, via its own unwrapped
     `list(csv.DictReader(...))` body-row parse) and this module's own
     _decode_container/materialize_parser_b body-row parse are affected.
     This is whole-object-level CSV tokenization failure -- csv.Error aborts
     the entire reader, not one row -- so it is classified with the other
     structurally-corrupt-container cases (gzip corruption, invalid UTF-8,
     truncated header) as CONTAINER_ANOMALY, not as a per-row rejection.
     _materialize_parser_a_unadmitted() catches csv.Error at its rp.parse_daily_object()
     call site (no edit to r1_reference_parser.py); materialize_parser_b()
     catches it across both its container-decode step and its own body-row
     csv.DictReader parse.

     Note on the Parser-B TypeError specifically (same hostile review, a
     distinct failure class -- NOT conflated with csv.Error above): a
     structurally malformed CSV row (observed reproducer: an unterminated
     quote that swallows the remainder of one physical row, leaving
     csv.DictReader's restval=None in every column after the swallowed
     field) reaches qntylab.r1_retention_candidate.daily_primitive with
     required numeric columns (timestamp/size/price/homeNotional/
     foreignNotional/grossValue) set to None. daily_primitive already has
     an existing, frozen, contract-authorized malformed-row disposition for
     exactly this row shape -- reject the row, increment rejected_row_count,
     append ANOMALY_PARSE_REJECTION, continue with the remaining rows
     (mirroring Parser A's own REQUIRED_ROW_FIELDS row-rejection check) --
     but daily_primitive's try/except at that step only catches
     (KeyError, ValueError, InvalidOperation); Decimal(None)/float(None)
     raise TypeError, which is not in that tuple, so the row crashes the
     whole call instead of being rejected. This module does not catch
     TypeError (that would risk hiding an unrelated programming bug inside
     daily_primitive); instead materialize_parser_b() pre-filters rows
     against the exact fixed set of columns daily_primitive's own
     try-block numeric-converts unconditionally, before calling
     daily_primitive, and folds the pre-filtered count into the same
     rejected_row_count/ANOMALY_PARSE_REJECTION accounting daily_primitive
     already produces for its other row-rejection causes -- so the
     observable disposition is identical to what daily_primitive's own
     mechanism already intends, not a new boundary-invented outcome, and no
     Decimal/OHLC/aggregation logic is reimplemented here.

Independence: this module calls both parsers but does not let either parser
call the other, and performs no semantic parsing itself (only raw-hash
binding, record assembly, contract-completeness checking, and typed error
wrapping).

Outcome embargo: this module computes no momentum, funding, rank, weight,
return, PnL, IC, or Sharpe value, and deletes no raw bytes.
RAW_DELETION_AUTHORIZED remains false.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import re
import zlib
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Optional

from qntylab import r1_reference_parser as rp
from qntylab import r1_retention_candidate as rc
from qntylab import r1_schema_admission as admission
from qntylab import r1_schema_recognizer as recognizer

# --- materialization outcome (boundary-local bookkeeping, not itself new
# frozen scientific protocol -- mirrors the pattern Parser A already uses for
# its own local, non-contract STATUS_* constants) -----------------------------
# Public three-way result algebra per the FROZEN
# experiments/data/r1_empty_object_result_algebra_amendment_v1.json. Only
# materialize_parser_a (and its compatibility alias) may emit these.
MATERIALIZED_VALID = "MATERIALIZED_VALID_RECORD"
EMPTY_OBJECT_OBSERVATION = "EMPTY_OBJECT_ZERO_TRADE_OBSERVATION"
MATERIALIZATION_QUARANTINED = "MATERIALIZATION_QUARANTINED_NO_RECORD"

# Internal-only status for _materialize_parser_a_unadmitted's own mechanically
# record-shaped candidate output. Distinct in VALUE, not merely by leading
# underscore, from MATERIALIZED_VALID above: per the frozen result algebra's
# low_level_capability_boundary, this primitive's output is Parser-A
# implementation capability, never public schema-admitted evidence, no matter
# how record-shaped or field-complete it looks. Only materialize_parser_a's
# own additional admission-derived-schema-id validation may promote a
# candidate carrying this status to public MATERIALIZED_VALID.
INTERNAL_PARSER_A_CANDIDATE = "INTERNAL_PARSER_A_CANDIDATE_RECORD_NOT_PUBLIC_EVIDENCE"

# --- FROZEN EMPTY_OBJECT result-algebra authority binding -------------------
#
# Same exact-hash-verification pattern qntylab.r1_schema_admission already
# uses for its own frozen authority: one named artifact, verified by exact
# bytes, cached once per process -- never "whichever is newest" and never an
# ambient fallback on mismatch.
_ROOT = Path(__file__).resolve().parent.parent
_DATA = _ROOT / "experiments/data"
_RESULT_ALGEBRA_ARTIFACT_PATH = _DATA / "r1_empty_object_result_algebra_amendment_v1.json"

_EXPECTED_RESULT_ALGEBRA_SEMANTIC_SHA256 = (
    "4c50be84a84b9ba4817fd92ef1cb5dde075b66135e1a00bacf532ac1b6876c46"
)
_EXPECTED_RESULT_ALGEBRA_EFFECTIVE_SHA256 = (
    "5406f96160662e3d7da6d04c43dda58e96e0f965c7f73ac321a63283710899d6"
)
_EXPECTED_RESULT_ALGEBRA_REVIEWED_CANDIDATE_SHA = "a720c79a9580e164775e5b9ff2a08c0824aee343"
_EXPECTED_RESULT_ALGEBRA_REVIEW_PAYLOAD_SHA256 = (
    "3466a29be7fa01b63f7843c375024a4bc35ca343d64d35034c62ab59830e88b6"
)


def _canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def _semantic_sha256(value) -> str:
    return sha256(_canonical(value)).hexdigest()


def _verify_result_algebra_authority(result_algebra_bytes: bytes) -> dict:
    """Fail-closed verification that the supplied bytes are byte-identical to
    the FROZEN, independently hostile-reviewed EMPTY_OBJECT result-algebra
    amendment this module conforms to. Raises ValueError on any mismatch --
    never proceeds to derive a public outcome against unverified authority.
    Callers at the public boundary must catch this and fail closed to
    MATERIALIZATION_QUARANTINED, never let it escape as an untyped exception
    or be treated as license to emit a valid/observation result."""
    doc = json.loads(result_algebra_bytes)
    if doc.get("status") != "FROZEN" or doc.get("self_freeze_authorized") is not False:
        raise ValueError("result algebra artifact is not a frozen, non-self-frozen candidate")
    if _semantic_sha256(doc["semantic_body"]) != _EXPECTED_RESULT_ALGEBRA_SEMANTIC_SHA256:
        raise ValueError("result algebra semantic content mismatch")
    if _semantic_sha256(doc["effective_combined_contract_binding"]) != _EXPECTED_RESULT_ALGEBRA_EFFECTIVE_SHA256:
        raise ValueError("result algebra effective binding mismatch")
    provenance = doc.get("freeze_provenance") or {}
    if provenance.get("candidate_commit_reviewed_sha") != _EXPECTED_RESULT_ALGEBRA_REVIEWED_CANDIDATE_SHA:
        raise ValueError("result algebra freeze provenance reviewed-candidate sha mismatch")
    if provenance.get("review_receipt_payload_sha256") != _EXPECTED_RESULT_ALGEBRA_REVIEW_PAYLOAD_SHA256:
        raise ValueError("result algebra review receipt payload sha mismatch")
    return doc


_default_result_algebra_bytes: bytes | None = None


def _load_default_result_algebra_bytes() -> bytes:
    """Fail-closed loader for the one named, exact result-algebra authority.
    Cached once per process, mirroring r1_schema_admission's own
    _load_default_authority_bytes precedent -- never re-reads the mutable
    ambient file on every call."""
    global _default_result_algebra_bytes
    if _default_result_algebra_bytes is None:
        _default_result_algebra_bytes = _RESULT_ALGEBRA_ARTIFACT_PATH.read_bytes()
    return _default_result_algebra_bytes

# Frozen DailyMarketEvidenceV1 field set, read directly from
# r1_normalized_evidence_contract_v1.json:layers.DailyMarketEvidenceV1.fields.
REQUIRED_ALWAYS_NON_NULL = ("instrument_instance_id", "utc_date", "trade_count",
                             "duplicate_count", "rejected_row_count")
# required: true, but missingness_semantics explicitly permits null when
# trade_count == 0 (never forward-filled / never synthetic).
REQUIRED_NON_NULL_WHEN_TRADES_PRESENT = (
    "close", "quote_turnover", "first_source_timestamp_utc", "last_source_timestamp_utc",
    "first_source_trade_id", "last_source_trade_id",
)
# required: true, missingness_semantics: "never null for a day with
# trade_count>0; null only when trade_count=0 AND no object was retrievable".
# This boundary is only ever invoked with raw bytes already in hand, so from
# its perspective the object was always retrievable -- source_object_sha256
# must be non-null in every record it emits, independent of trade_count.
ALWAYS_NON_NULL_WHEN_OBJECT_RETRIEVED = ("source_object_sha256",)
# required: false (diagnostic/corroboration only) but still contract-defined;
# present as a key always, null exactly when trade_count == 0.
OPTIONAL_CONTRACT_DEFINED = ("open", "high", "low", "base_volume")
ALL_CONTRACT_FIELDS = (
    "instrument_instance_id", "utc_date", "open", "high", "low", "close",
    "base_volume", "quote_turnover", "trade_count", "first_source_timestamp_utc",
    "last_source_timestamp_utc", "first_source_trade_id", "last_source_trade_id",
    "duplicate_count", "rejected_row_count", "schema_id", "source_object_sha256",
)

# Exact set of columns qntylab.r1_retention_candidate.daily_primitive's own
# row-parsing try-block (r1_retention_candidate.py, inside daily_primitive)
# unconditionally numeric-converts via Decimal()/float() before its existing
# (KeyError, ValueError, InvalidOperation) except-clause can apply -- see
# module docstring's "Note on the Parser-B TypeError". A None value in any
# of these (csv.DictReader's restval for a short/malformed row) makes that
# conversion raise TypeError, which is not in daily_primitive's own except
# tuple. This boundary pre-filters exactly these columns -- not side,
# trdMatchID, or tickDirection, which daily_primitive stores without
# numeric conversion and does not crash on -- so the row still reaches
# daily_primitive's already-authorized PARSE_REJECTION disposition instead
# of crashing the whole call.
_PARSER_B_NUMERIC_ROW_FIELDS = ("timestamp", "size", "price", "homeNotional", "foreignNotional", "grossValue")

_ISO_TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3,}Z$")
_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL_STRING_PATTERN = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")


@dataclass
class MaterializationResult:
    """One result per attempted raw object. For the canonical public
    Parser-A boundary (materialize_parser_a), exactly one of three tagged
    outcomes per the FROZEN EMPTY_OBJECT result algebra: a complete,
    contract-valid DailyMarketEvidenceV1 record (`record` present,
    `observation` absent), a typed EMPTY_OBJECT zero-trade observation
    (`observation` present, `record` absent), or quarantine (both absent).
    Parser B and the internal Parser-A candidate primitive never populate
    `observation`; it exists on this shared dataclass so the public
    boundary's tagged-union invariant is representable without a second
    result type."""
    status: str
    parser: str  # "A" or "B"
    raw_object_sha256: str
    record: Optional[dict] = None
    observation: Optional[dict] = None
    anomalies: list = field(default_factory=list)
    reason: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return (
            self.status == MATERIALIZED_VALID
            and self.record is not None
            and self.observation is None
        )


def validate_daily_market_evidence_v1(record: dict) -> list[str]:
    """Purely mechanical contract-completeness check against
    r1_normalized_evidence_contract_v1.json:DailyMarketEvidenceV1. Returns a
    list of violations (empty == valid). Asserts no rule beyond what the
    frozen contract text itself states: required keys present, required
    non-null conditions, and basic type/shape checks. Makes no scientific
    judgment (does not recompute OHLC, does not re-derive duplicate/timestamp
    semantics)."""
    violations: list[str] = []

    missing_keys = [k for k in ALL_CONTRACT_FIELDS if k not in record]
    if missing_keys:
        violations.append(f"missing required contract keys: {sorted(missing_keys)}")
        return violations  # cannot check further without the keys present

    for k in REQUIRED_ALWAYS_NON_NULL:
        if record[k] is None:
            violations.append(f"{k} must never be null (contract: never null)")

    for k in ALWAYS_NON_NULL_WHEN_OBJECT_RETRIEVED:
        v = record.get(k)
        if v is None:
            violations.append(f"{k} must not be null: the raw object was retrievable "
                               f"(this boundary was invoked with its bytes)")
        elif not (isinstance(v, str) and _SHA256_HEX_PATTERN.match(v)):
            violations.append(f"{k} not a 64-char lowercase hex sha256: {v!r}")

    if not isinstance(record["trade_count"], int) or record["trade_count"] < 0:
        violations.append("trade_count must be a non-negative integer")
    if not isinstance(record["duplicate_count"], int) or record["duplicate_count"] < 0:
        violations.append("duplicate_count must be a non-negative integer")
    if not isinstance(record["rejected_row_count"], int) or record["rejected_row_count"] < 0:
        violations.append("rejected_row_count must be a non-negative integer")

    trade_count = record.get("trade_count")
    has_trades = isinstance(trade_count, int) and trade_count > 0

    if has_trades:
        for k in REQUIRED_NON_NULL_WHEN_TRADES_PRESENT:
            if record[k] is None:
                violations.append(f"{k} must not be null when trade_count>0")
        for k in OPTIONAL_CONTRACT_DEFINED:
            if record[k] is None:
                violations.append(f"{k} must not be null when trade_count>0 (precision_semantics)")

        for k in ("first_source_timestamp_utc", "last_source_timestamp_utc"):
            v = record.get(k)
            if isinstance(v, str) and not _ISO_TS_PATTERN.match(v):
                violations.append(f"{k} not ISO-8601 millisecond-or-finer UTC: {v!r}")
            elif not isinstance(v, str):
                violations.append(f"{k} must be a string when trade_count>0, got {type(v)}")

        for k in ("close",) + OPTIONAL_CONTRACT_DEFINED + ("quote_turnover",):
            v = record.get(k)
            if v is not None and not (isinstance(v, str) and _DECIMAL_STRING_PATTERN.match(v)):
                violations.append(f"{k} must be a decimal-string when non-null, got {v!r}")

        for k in ("first_source_trade_id", "last_source_trade_id"):
            if not isinstance(record.get(k), str):
                violations.append(f"{k} must be a non-null string when trade_count>0")
    else:
        # trade_count == 0: close/timestamps/trade-ids null (never
        # forward-filled/synthetic; source_object_sha256 stays bound
        # regardless, checked above); base_volume/quote_turnover are a true
        # zero, not null (contract: "0 when trade_count=0", distinct from
        # close's null); open/high/low null (undefined price).
        for k in ("close", "first_source_timestamp_utc", "last_source_timestamp_utc",
                  "first_source_trade_id", "last_source_trade_id",
                  "open", "high", "low"):
            if record.get(k) is not None:
                violations.append(f"{k} must be null when trade_count==0")
        for k in ("base_volume", "quote_turnover"):
            if record.get(k) != "0":
                violations.append(f"{k} must be the string '0' when trade_count==0, got {record.get(k)!r}")

    if not isinstance(record.get("instrument_instance_id"), str):
        violations.append("instrument_instance_id must be a string")
    if not isinstance(record.get("utc_date"), str):
        violations.append("utc_date must be a string")

    return violations


def _materialize_parser_a_unadmitted(raw_bytes: bytes, expected_utc_date: date, instrument_instance_id: str,
                          expected_raw_sha256: Optional[str] = None) -> MaterializationResult:
    """INTERNAL low-level Parser-A materialization primitive. This function
    performs NO schema admission: it materializes any raw object within
    Parser A's own row-semantics support scope, whether or not that
    object's schema is authorized for DailyMarketEvidenceV1 (e.g. it will
    happily materialize a structurally-recognized-but-unauthorized
    bybit_trade_v1_rpi object, which the frozen schema-admission scope
    denies). Its output is Parser-A implementation capability, not
    schema-admitted evidence authority -- do not call this from ordinary
    production code.

    This primitive exists only for two callers: (1) materialize_parser_a
    below, which composes it behind the frozen schema-admission gate to
    produce the canonical, admission-gated public entry point; and (2)
    narrowly scoped low-level tests that must exercise Parser A's/this
    boundary's own mechanical behavior (container-anomaly conversion,
    contract-completeness validation, raw-hash binding) independent of
    schema admission -- those tests must not, and do not, treat this
    primitive's output as admitted evidence.

    parse_daily_object already embeds source_object_sha256 in its own
    record; this boundary independently recomputes sha256(raw_bytes) (never
    trusting the embedded value alone), requires exact equality, and
    converts exactly the four explicitly-authorized, reachable
    container-corruption failure classes into a typed CONTAINER_ANOMALY
    quarantine result instead of letting them escape:
    rp.GzipCorruptionError, rp.TruncatedCSVError (both raised inside
    rp.parse_daily_object itself), UnicodeDecodeError (raised by
    rp.parse_daily_object's internal call to
    r1_reference_parser._decompress(), whose final .decode("utf-8",
    errors="strict") is not itself wrapped in that function's own
    GzipCorruptionError try/except -- see module docstring), and csv.Error
    (raised by rp.parse_daily_object's own unwrapped
    `list(csv.DictReader(...))` body-row parse when the CSV body is not
    tokenizable at all, e.g. a field exceeding csv.field_size_limit() --
    see module docstring). This is a fixed, narrow tuple, not a bare
    `except Exception`: any other exception (a genuine programming error,
    not an authorized object-corruption class) still propagates uncaught,
    exactly as before."""
    raw_sha = sha256(raw_bytes).hexdigest()

    if expected_raw_sha256 is not None and expected_raw_sha256 != raw_sha:
        return MaterializationResult(
            status=MATERIALIZATION_QUARANTINED, parser="A", raw_object_sha256=raw_sha,
            anomalies=[rc.ANOMALY_SOURCE_MUTATION],
            reason=f"raw bytes do not match expected_raw_sha256 (expected {expected_raw_sha256}, got {raw_sha})",
        )

    try:
        result = rp.parse_daily_object(raw_bytes, expected_utc_date, instrument_instance_id)
    except (rp.GzipCorruptionError, rp.TruncatedCSVError, UnicodeDecodeError, csv.Error) as exc:
        return MaterializationResult(
            status=MATERIALIZATION_QUARANTINED, parser="A", raw_object_sha256=raw_sha,
            anomalies=[rc.ANOMALY_CONTAINER],
            reason=f"{type(exc).__name__}: {exc}",
        )

    if result.record is None:
        # e.g. STATUS_UNKNOWN_SCHEMA_QUARANTINE: Parser A's own typed,
        # non-exception refusal to emit a record. Passed through unchanged,
        # not reinterpreted.
        return MaterializationResult(
            status=MATERIALIZATION_QUARANTINED, parser="A", raw_object_sha256=raw_sha,
            anomalies=[result.status], reason=result.status,
        )

    record = result.record
    if record.get("source_object_sha256") != raw_sha:
        return MaterializationResult(
            status=MATERIALIZATION_QUARANTINED, parser="A", raw_object_sha256=raw_sha,
            anomalies=[rc.ANOMALY_SOURCE_MUTATION],
            reason=f"Parser A's own embedded source_object_sha256 {record.get('source_object_sha256')!r} "
                   f"!= sha256(raw_bytes) {raw_sha!r}",
        )

    violations = validate_daily_market_evidence_v1(record)
    if violations:
        return MaterializationResult(
            status=MATERIALIZATION_QUARANTINED, parser="A", raw_object_sha256=raw_sha,
            record=None, anomalies=["CONTRACT_COMPLETENESS_VIOLATION"], reason="; ".join(violations),
        )

    return MaterializationResult(
        status=INTERNAL_PARSER_A_CANDIDATE, parser="A", raw_object_sha256=raw_sha, record=record, anomalies=[],
    )


SCHEMA_INADMISSIBLE = "SCHEMA_INADMISSIBLE"

# Exact recognition reasons for the frozen recognition amendment's one
# EMPTY_OBJECT condition (r1_schema_recognizer._framing_failure("EMPTY_OBJECT")
# always returns this exact 1-tuple). Matched by exact tuple equality, never
# substring/`in`, per the frozen result algebra's "no broadening" requirement.
_EMPTY_OBJECT_REASONS = ("EMPTY_OBJECT",)


def _validate_admitted_record(record: dict, evaluation: "admission.SchemaAdmissionEvaluation") -> list[str]:
    """Narrow admitted-record validator per the frozen result algebra's
    validity_predicate: enforces record.schema_id against the already-derived
    SchemaAdmissionEvaluation only. Never re-opens a live registry file --
    evaluation.schema_id is the sole schema-authority input. Returns a list
    of violations (empty == valid)."""
    violations: list[str] = []
    if evaluation.admission != admission.ADMISSIBLE:
        violations.append("schema admission is not SCHEMA_ADMISSIBLE")
    if evaluation.recognition_disposition != recognizer.RECOGNIZED:
        violations.append("recognition disposition is not RECOGNIZED")
    if not isinstance(evaluation.schema_id, str) or not evaluation.schema_id:
        violations.append("admission-derived schema_id is not a non-null string")

    schema_id = record.get("schema_id")
    if not isinstance(schema_id, str) or not schema_id:
        violations.append(f"record.schema_id is not a non-null string: {schema_id!r}")
    elif schema_id != evaluation.schema_id:
        violations.append(
            f"record.schema_id {schema_id!r} != admission-derived schema_id {evaluation.schema_id!r}"
        )
    return violations


def materialize_parser_a(raw_bytes: bytes, expected_utc_date: date, instrument_instance_id: str,
                          expected_raw_sha256: Optional[str] = None) -> MaterializationResult:
    """THE canonical public Parser-A materialization entry point: one exact
    source object X -> FROZEN schema admission gate
    (qntylab.r1_schema_admission) -> internal Parser A materialization
    (_materialize_parser_a_unadmitted), permitted only when admission
    passes. `raw_bytes` is read once by the caller and threaded, as the same
    immutable bytes object, through hashing, admission, and (if admitted)
    Parser A parsing -- there is no separate re-open/re-read step that could
    desynchronize the bytes admission evaluated from the bytes Parser A
    parses.

    Ordinary callers should always use this function, never the internal
    _materialize_parser_a_unadmitted primitive: this is the only public
    Parser-A materialization path, and it is unconditionally
    admission-gated. There is no parameter on this function that can skip,
    override, or short-circuit that gate.

    Recognition is necessarily evaluated twice on the admitted path (once
    inside qntylab.r1_schema_admission.evaluate_schema_admission, once again
    inside rp.parse_daily_object via qntylab.r1_schema_recognizer): both
    evaluations apply the identical frozen G to the identical X and R, so
    they are redundant but deterministic, not divergent. No recognition
    receipt/cache is introduced solely to avoid this recomputation (R1
    correctness-first scope; see task notes).

    A structurally recognized-but-unauthorized schema (e.g.
    bybit_trade_v1_rpi) never reaches Parser A through this function, even
    though Parser A's own row-semantics support scope happens to include it:
    schema admission denial is a gate on materialization, not merely
    advisory metadata.

    Return value conforms to the FROZEN EMPTY_OBJECT result algebra
    (experiments/data/r1_empty_object_result_algebra_amendment_v1.json):
    exactly one of MATERIALIZED_VALID_RECORD (record present, observation
    absent), EMPTY_OBJECT_ZERO_TRADE_OBSERVATION (observation present,
    record absent), or MATERIALIZATION_QUARANTINED_NO_RECORD (both absent)
    is ever returned -- never both payloads, never neither status.
    """
    raw_sha = sha256(raw_bytes).hexdigest()

    if expected_raw_sha256 is not None and expected_raw_sha256 != raw_sha:
        return MaterializationResult(
            status=MATERIALIZATION_QUARANTINED, parser="A", raw_object_sha256=raw_sha,
            anomalies=[rc.ANOMALY_SOURCE_MUTATION],
            reason=f"raw bytes do not match expected_raw_sha256 (expected {expected_raw_sha256}, got {raw_sha})",
        )

    try:
        _verify_result_algebra_authority(_load_default_result_algebra_bytes())
    except (ValueError, OSError, json.JSONDecodeError, KeyError) as exc:
        return MaterializationResult(
            status=MATERIALIZATION_QUARANTINED, parser="A", raw_object_sha256=raw_sha,
            anomalies=["RESULT_ALGEBRA_AUTHORITY_MISMATCH"],
            reason=f"{type(exc).__name__}: {exc}",
        )

    evaluation = admission.evaluate_schema_admission(raw_bytes)

    if evaluation.admission != admission.ADMISSIBLE:
        # Frozen schema_admission_rule text's one explicit carve-out: "EMPTY_OBJECT
        # receives no fabricated schema authorization; its downstream zero-trade
        # handling remains governed only by existing materialization/completeness
        # semantics." Per the FROZEN result algebra, that downstream handling is
        # now the typed EMPTY_OBJECT_ZERO_TRADE_OBSERVATION outcome -- an
        # observation, never a DailyMarketEvidenceV1 record and never
        # MATERIALIZED_VALID_RECORD. Matched by exact reason-tuple equality
        # (never substring/`in`), so no other FRAMING_FAILURE -- including
        # near-empty bodies that are FEWER_THAN_TWO_TOKENS, EMPTY_TOKEN_NAME,
        # BOM_PRESENT, INVALID_GZIP, or INVALID_UTF8 -- can qualify.
        if (evaluation.recognition_disposition == recognizer.FRAMING_FAILURE
                and evaluation.reasons == _EMPTY_OBJECT_REASONS):
            observation = {
                "instrument_instance_id": instrument_instance_id,
                "utc_date": expected_utc_date.isoformat(),
                "source_object_sha256": raw_sha,
                "trade_count": 0,
                "recognition_disposition": evaluation.recognition_disposition,
                "recognition_reasons": evaluation.reasons,
                "schema_admission": evaluation.admission,
            }
            return MaterializationResult(
                status=EMPTY_OBJECT_OBSERVATION, parser="A", raw_object_sha256=raw_sha,
                observation=observation, anomalies=[],
            )
        return MaterializationResult(
            status=MATERIALIZATION_QUARANTINED, parser="A", raw_object_sha256=raw_sha,
            anomalies=[SCHEMA_INADMISSIBLE],
            reason=(f"frozen schema admission denied: recognition_disposition="
                    f"{evaluation.recognition_disposition!r} schema_id={evaluation.schema_id!r}"),
        )

    candidate = _materialize_parser_a_unadmitted(raw_bytes, expected_utc_date, instrument_instance_id)

    if candidate.status != INTERNAL_PARSER_A_CANDIDATE or candidate.record is None:
        # A private-primitive failure (container anomaly, contract-completeness
        # violation, source mutation) becomes public quarantine -- never public
        # validity. candidate.reason/anomalies are passed through unchanged.
        return MaterializationResult(
            status=MATERIALIZATION_QUARANTINED, parser="A", raw_object_sha256=raw_sha,
            anomalies=list(candidate.anomalies), reason=candidate.reason,
        )

    schema_violations = _validate_admitted_record(candidate.record, evaluation)
    if schema_violations:
        return MaterializationResult(
            status=MATERIALIZATION_QUARANTINED, parser="A", raw_object_sha256=raw_sha,
            anomalies=["SCHEMA_IDENTITY_MISMATCH"], reason="; ".join(schema_violations),
        )

    # Defense-in-depth: independently reverify, at this public boundary, that
    # every exact-X identity available here still names the same raw bytes --
    # never trust the private primitive's own internal source-hash check
    # alone (that check must also remain, unmodified, in
    # _materialize_parser_a_unadmitted). A hostile mutation that silently
    # removes/weakens the private check must still be caught here.
    source_identity_violations = []
    if candidate.raw_object_sha256 != raw_sha:
        source_identity_violations.append(
            f"candidate.raw_object_sha256 {candidate.raw_object_sha256!r} != sha256(raw_bytes) {raw_sha!r}"
        )
    if candidate.record is None:
        source_identity_violations.append("candidate.record is not present")
    else:
        candidate_source_sha = candidate.record.get("source_object_sha256")
        if candidate_source_sha != raw_sha:
            source_identity_violations.append(
                f"candidate.record['source_object_sha256'] {candidate_source_sha!r} != sha256(raw_bytes) {raw_sha!r}"
            )
    if evaluation.source_object_sha256 != raw_sha:
        source_identity_violations.append(
            f"evaluation.source_object_sha256 {evaluation.source_object_sha256!r} != sha256(raw_bytes) {raw_sha!r}"
        )
    if source_identity_violations:
        return MaterializationResult(
            status=MATERIALIZATION_QUARANTINED, parser="A", raw_object_sha256=raw_sha,
            anomalies=[rc.ANOMALY_SOURCE_MUTATION], reason="; ".join(source_identity_violations),
        )

    return MaterializationResult(
        status=MATERIALIZED_VALID, parser="A", raw_object_sha256=raw_sha, record=candidate.record, anomalies=[],
    )


# Compatibility alias for the name this gate was first reviewed and wired
# under (see experiments/data/r1_schema_admission_runtime_wiring_review_v1.json).
# Not a separate implementation: literally the same function object as
# materialize_parser_a above, so the two can never drift.
materialize_admitted_parser_a = materialize_parser_a


def _decode_container(raw_bytes: bytes) -> tuple[str, list[str]]:
    """Reaches the identical *outcome* classification as
    qntylab.r1_reference_parser.parse_daily_object (same len/line/column
    thresholds; the same three raw-object shapes end up quarantined:
    invalid gzip, invalid-UTF-8 decompressed body, and a missing/too-short
    CSV header) -- not the identical internal exception path. Parser A's
    own _decompress() lets an invalid-UTF-8 body escape as a bare
    UnicodeDecodeError instead of wrapping it in GzipCorruptionError (see
    module docstring); this helper instead wraps that case as
    GzipCorruptionError directly, at decode time. Raises
    rp.GzipCorruptionError / TruncatedCSVError (Parser A's own
    already-defined exception types) on failure; callers of this helper are
    expected to catch them, exactly as materialize_parser_a does for Parser
    A itself (materialize_parser_a additionally catches UnicodeDecodeError
    directly, to compensate for Parser A's own un-wrapped case rather than
    editing r1_reference_parser.py)."""
    try:
        text = gzip.decompress(raw_bytes).decode("utf-8", errors="strict")
    except (gzip.BadGzipFile, OSError, EOFError, zlib.error, UnicodeDecodeError) as exc:
        raise rp.GzipCorruptionError(str(exc)) from exc

    lines = text.splitlines()
    if not lines:
        return text, []

    header = next(csv.reader(io.StringIO(text)), None)
    if header is None:
        raise rp.TruncatedCSVError("no header row present")
    if len(header) < 2:
        raise rp.TruncatedCSVError("header has fewer than 2 columns")
    return text, header


def _prefilter_parser_b_rows(rows: list) -> tuple[list, int]:
    """Drops rows daily_primitive's own row-parsing try-block would crash on
    with TypeError (see _PARSER_B_NUMERIC_ROW_FIELDS and the module
    docstring's "Note on the Parser-B TypeError"), returning
    (usable_rows, dropped_count). Checks nothing beyond that exact column
    set -- no numeric parsing, no Decimal conversion, no OHLC/aggregation
    logic; daily_primitive still does all of that, unmodified, on the
    surviving rows."""
    usable = []
    dropped = 0
    for row in rows:
        if any(row.get(k) is None for k in _PARSER_B_NUMERIC_ROW_FIELDS):
            dropped += 1
            continue
        usable.append(row)
    return usable, dropped


def materialize_parser_b(raw_bytes: bytes, utc_date: str, stream_id: str,
                          historical_cutoff_utc: str,
                          expected_raw_sha256: Optional[str] = None) -> MaterializationResult:
    """Parser B path. daily_primitive() never receives raw bytes and never
    computes source_object_sha256 -- this boundary computes sha256(raw_bytes)
    once, here, from the exact bytes handed in, and binds it into the
    assembled record. It does not reuse r1_input_bom.canonical_hash /
    normalized_primitive_sha256 for this purpose: those hash the normalized
    primitive, not the raw object, and are a different quantity. No
    OHLC/duplicate/timestamp logic in qntylab.r1_retention_candidate.daily_primitive
    is modified or reimplemented here."""
    raw_sha = sha256(raw_bytes).hexdigest()

    if expected_raw_sha256 is not None and expected_raw_sha256 != raw_sha:
        return MaterializationResult(
            status=MATERIALIZATION_QUARANTINED, parser="B", raw_object_sha256=raw_sha,
            anomalies=[rc.ANOMALY_SOURCE_MUTATION],
            reason=f"raw bytes do not match expected_raw_sha256 (expected {expected_raw_sha256}, got {raw_sha})",
        )

    precheck_rejected = 0
    if len(raw_bytes) == 0:
        core, anomalies = rc.daily_primitive(
            stream_id=stream_id, utc_date=utc_date, header=rc.BASE_SCHEMA, rows=[],
            historical_cutoff_utc=historical_cutoff_utc,
        )
    else:
        try:
            text, header = _decode_container(raw_bytes)
            if header:
                rows, precheck_rejected = _prefilter_parser_b_rows(list(csv.DictReader(io.StringIO(text))))
        except (rp.GzipCorruptionError, rp.TruncatedCSVError, csv.Error) as exc:
            return MaterializationResult(
                status=MATERIALIZATION_QUARANTINED, parser="B", raw_object_sha256=raw_sha,
                anomalies=[rc.ANOMALY_CONTAINER],
                reason=f"{type(exc).__name__}: {exc}",
            )
        if not header:
            core, anomalies = rc.daily_primitive(
                stream_id=stream_id, utc_date=utc_date, header=rc.BASE_SCHEMA, rows=[],
                historical_cutoff_utc=historical_cutoff_utc,
            )
        else:
            core, anomalies = rc.daily_primitive(
                stream_id=stream_id, utc_date=utc_date, header=tuple(header), rows=rows,
                historical_cutoff_utc=historical_cutoff_utc,
            )
            if precheck_rejected:
                # Fold the pre-filtered count into daily_primitive's own
                # rejected_row_count/anomaly accounting -- identical
                # disposition to what daily_primitive's existing except
                # tuple already produces for its other row-rejection
                # causes (see _prefilter_parser_b_rows docstring), not a
                # new boundary-invented outcome.
                core["rejected_row_count"] = core.get("rejected_row_count", 0) + precheck_rejected
                anomalies = sorted(set(anomalies) | {rc.ANOMALY_PARSE_REJECTION})

    record = dict(core)
    # daily_primitive's own dict key is "stream_id" (its internal candidate
    # parameter name); the frozen contract's field name is
    # "instrument_instance_id". This is a pure renaming, not a scientific
    # decision -- Parser A already emits the contract's own field name
    # directly, so the boundary normalizes Parser B's output to match.
    record["instrument_instance_id"] = record.pop("stream_id")
    # source_object_sha256 binds the raw object, not trade presence: this
    # boundary was invoked with raw_bytes in hand, so per the contract's own
    # missingness rule ("null only when ... no object was retrievable") the
    # field is always bound here, independent of trade_count.
    record["source_object_sha256"] = raw_sha

    violations = validate_daily_market_evidence_v1(record)
    if violations:
        return MaterializationResult(
            status=MATERIALIZATION_QUARANTINED, parser="B", raw_object_sha256=raw_sha,
            record=None, anomalies=list(anomalies) + ["CONTRACT_COMPLETENESS_VIOLATION"],
            reason="; ".join(violations),
        )

    return MaterializationResult(
        status=MATERIALIZED_VALID, parser="B", raw_object_sha256=raw_sha, record=record,
        anomalies=list(anomalies),
    )


def materialize_batch(items: list, materialize_fn) -> list:
    """Bounded batch isolation primitive: one MaterializationResult per
    attempted item, in input order. A corrupt item never raises out of this
    function and never prevents later items in the same batch from being
    attempted -- materialize_parser_a/materialize_parser_b (and the internal
    _materialize_parser_a_unadmitted primitive) already convert every
    container-level exception into a typed result, so this loop needs no
    additional exception handling of its own; it exists to make that
    per-item isolation guarantee an explicit, testable property of the
    boundary rather than an incidental consequence of each function's
    internals. Does not bulk-process a real corpus; callers pass a small,
    explicit list.

    `materialize_fn` is caller-supplied so an ordinary caller who passes the
    public, admission-gated materialize_parser_a naturally gets a gated
    batch; passing the internal _materialize_parser_a_unadmitted primitive
    is reserved for the same narrow implementation-test scope that
    justifies calling it directly at all (see its own docstring)."""
    results = []
    for args in items:
        results.append(materialize_fn(*args))
    return results
