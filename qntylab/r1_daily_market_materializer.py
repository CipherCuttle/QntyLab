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

  3. converting container-level corruption (gzip corruption, structurally
     truncated CSV) into the already-frozen CONTAINER_ANOMALY /
     RAW_QUARANTINED_ANOMALY vocabulary
     (qntylab.r1_retention_candidate.ANOMALY_CONTAINER is already declared,
     and listed in experiments/data/r1_bounded_evidence_retention_candidate_v1.json
     :anomaly_triggers, but was never wired to any raising code path) instead
     of letting qntylab.r1_reference_parser.GzipCorruptionError /
     TruncatedCSVError -- or the equivalent ingestion failure for the Parser B
     path, which does not decompress/parse CSV itself -- escape as an
     uncaught, batch-terminating exception. No new contract-visible status
     name is introduced by this module.

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
import re
import zlib
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from typing import Optional

from qntylab import r1_reference_parser as rp
from qntylab import r1_retention_candidate as rc

# --- materialization outcome (boundary-local bookkeeping, not itself new
# frozen scientific protocol -- mirrors the pattern Parser A already uses for
# its own local, non-contract STATUS_* constants) -----------------------------
MATERIALIZED_VALID = "MATERIALIZED_VALID_RECORD"
MATERIALIZATION_QUARANTINED = "MATERIALIZATION_QUARANTINED_NO_RECORD"

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

_ISO_TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3,}Z$")
_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL_STRING_PATTERN = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")


@dataclass
class MaterializationResult:
    """One result per attempted raw object: either a complete, contract-valid
    DailyMarketEvidenceV1 record, or an explicit typed non-valid result.
    Never both, never neither."""
    status: str
    parser: str  # "A" or "B"
    raw_object_sha256: str
    record: Optional[dict] = None
    anomalies: list = field(default_factory=list)
    reason: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.status == MATERIALIZED_VALID


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


def materialize_parser_a(raw_bytes: bytes, expected_utc_date: date, instrument_instance_id: str,
                          expected_raw_sha256: Optional[str] = None) -> MaterializationResult:
    """Parser A path. parse_daily_object already embeds source_object_sha256
    in its own record; this boundary independently recomputes sha256(raw_bytes)
    (never trusting the embedded value alone), requires exact equality, and
    converts any container-level exception into a typed quarantine result
    instead of letting it escape."""
    raw_sha = sha256(raw_bytes).hexdigest()

    if expected_raw_sha256 is not None and expected_raw_sha256 != raw_sha:
        return MaterializationResult(
            status=MATERIALIZATION_QUARANTINED, parser="A", raw_object_sha256=raw_sha,
            anomalies=[rc.ANOMALY_SOURCE_MUTATION],
            reason=f"raw bytes do not match expected_raw_sha256 (expected {expected_raw_sha256}, got {raw_sha})",
        )

    try:
        result = rp.parse_daily_object(raw_bytes, expected_utc_date, instrument_instance_id)
    except (rp.GzipCorruptionError, rp.TruncatedCSVError) as exc:
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
        status=MATERIALIZED_VALID, parser="A", raw_object_sha256=raw_sha, record=record, anomalies=[],
    )


def _decode_container(raw_bytes: bytes) -> tuple[str, list[str]]:
    """Mirrors qntylab.r1_reference_parser.parse_daily_object's own
    container-decoding classification exactly (same exception classes, same
    len/line/column thresholds), so the Parser B path is held to the
    identical definition of 'structurally corrupt' as Parser A -- not a new,
    separately-invented one. Raises rp.GzipCorruptionError / TruncatedCSVError
    (Parser A's own already-defined exception types) on failure; callers of
    this helper are expected to catch them, exactly as materialize_parser_a
    does for Parser A itself."""
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

    if len(raw_bytes) == 0:
        core, anomalies = rc.daily_primitive(
            stream_id=stream_id, utc_date=utc_date, header=rc.BASE_SCHEMA, rows=[],
            historical_cutoff_utc=historical_cutoff_utc,
        )
    else:
        try:
            text, header = _decode_container(raw_bytes)
        except (rp.GzipCorruptionError, rp.TruncatedCSVError) as exc:
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
            rows = list(csv.DictReader(io.StringIO(text)))
            core, anomalies = rc.daily_primitive(
                stream_id=stream_id, utc_date=utc_date, header=tuple(header), rows=rows,
                historical_cutoff_utc=historical_cutoff_utc,
            )

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
    attempted -- materialize_parser_a/materialize_parser_b already convert
    every container-level exception into a typed result, so this loop needs
    no additional exception handling of its own; it exists to make that
    per-item isolation guarantee an explicit, testable property of the
    boundary rather than an incidental consequence of each function's
    internals. Does not bulk-process a real corpus; callers pass a small,
    explicit list."""
    results = []
    for args in items:
        results.append(materialize_fn(*args))
    return results
