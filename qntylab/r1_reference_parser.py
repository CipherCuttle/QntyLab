"""Independent reference parser: RAW BYBIT TRADE OBJECT -> DailyMarketEvidenceV1.

This module is Parser A ("independent contract-derived implementation") for
Gap 2 of the bounded-evidence retention program. It is derived only from the
frozen artifacts:

  experiments/data/r1_normalized_evidence_contract_v1.json
  experiments/data/r1_source_schema_registry_v1.json
  experiments/data/r1_information_loss_ledger_v1.json
  experiments/data/r1_source_precedence_freeze.json
  experiments/data/r1_ingest_contract.json

Independence note: this module does not import qntylab.r1_retention_candidate
(Parser B / the pre-existing daily_primitive candidate) and was written
without reading that module's function bodies. Generic, non-market-semantic
facilities (gzip, csv, hashlib, json) are used directly from the standard
library rather than shared with Parser B.

instrument_instance_id is a lifecycle-layer concern (r1_lifecycle_contract.json)
outside a single raw trade object; callers supply the resolved identity string.

Outcome embargo: this module computes no momentum, funding, rank, weight,
return, PnL, IC, or Sharpe value. It performs no network access and deletes no
raw bytes; RAW_DELETION_AUTHORIZED remains false.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import zlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

CUTOFF_UTC_DATE = date(2026, 6, 30)

KNOWN_SCHEMA_COLUMNS = {
    "bybit_trade_v1": frozenset(
        [
            "timestamp",
            "symbol",
            "side",
            "size",
            "price",
            "tickDirection",
            "trdMatchID",
            "grossValue",
            "homeNotional",
            "foreignNotional",
        ]
    ),
    "bybit_trade_v1_rpi": frozenset(
        [
            "timestamp",
            "symbol",
            "side",
            "size",
            "price",
            "tickDirection",
            "trdMatchID",
            "grossValue",
            "homeNotional",
            "foreignNotional",
            "RPI",
        ]
    ),
}

REQUIRED_ROW_FIELDS = ("timestamp", "size", "price", "trdMatchID")

STATUS_OK = "OK"
STATUS_UNKNOWN_SCHEMA_QUARANTINE = "UNKNOWN_SCHEMA_QUARANTINE"
STATUS_EMPTY_OBJECT = "EMPTY_OBJECT"


class GzipCorruptionError(Exception):
    """Raised when the raw object cannot be gzip-decompressed."""


class TruncatedCSVError(Exception):
    """Raised when the header itself is unparseable/incomplete."""


def canonical_bytes(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def canonical_hash(value) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _decompress(raw_bytes: bytes) -> str:
    try:
        decompressed = gzip.decompress(raw_bytes)
    except (gzip.BadGzipFile, OSError, EOFError, zlib.error) as exc:
        raise GzipCorruptionError(str(exc)) from exc
    return decompressed.decode("utf-8", errors="strict")


def identify_schema(header: list) -> Optional[str]:
    colset = frozenset(header)
    for schema_id, cols in KNOWN_SCHEMA_COLUMNS.items():
        if colset == cols:
            return schema_id
    return None


def _epoch_to_iso(ts: Decimal) -> str:
    """UTC ISO-8601 string, millisecond-or-finer, per
    r1_normalized_evidence_contract_v1.json:DailyMarketEvidenceV1
    first_source_timestamp_utc/last_source_timestamp_utc (type: "timestamp
    (ISO 8601, millisecond or finer)"). The fractional-second component is
    taken from the exact Decimal remainder (never through float) and
    zero-padded up to a millisecond minimum (3 digits); source precision
    finer than milliseconds is preserved verbatim, never truncated.
    """
    whole = int(ts)
    frac = ts - whole
    dt = datetime.fromtimestamp(whole, tz=timezone.utc)
    frac_str = str(frac)
    frac_digits = frac_str.split(".")[1] if "." in frac_str else ""
    if len(frac_digits) < 3:
        frac_digits = frac_digits.ljust(3, "0")
    return f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}.{frac_digits}Z"


def _utc_date_of(ts: Decimal) -> date:
    whole = int(ts)
    return datetime.fromtimestamp(whole, tz=timezone.utc).date()


@dataclass
class DailyParseResult:
    status: str
    schema_id: Optional[str]
    record: Optional[dict]
    rejected_row_count: int
    duplicate_count: int
    diagnostics: dict = field(default_factory=dict)


def _parse_decimal(token: str) -> Decimal:
    return Decimal(token)


def _redundant_field_check(price: Decimal, size: Decimal, row: dict) -> dict:
    """Diagnostic-only cross-check per r1_information_loss_ledger_v1.json.

    Not globalized: a mismatch here never rejects OHLC/turnover data (those
    come from price/size directly), it only feeds the mismatch counters.
    """
    result = {"home_ok": None, "foreign_ok": None, "gross_ok": None}
    try:
        home = _parse_decimal(row["homeNotional"])
        result["home_ok"] = abs(home - size) <= Decimal("1e-9")
    except (InvalidOperation, KeyError, TypeError):
        result["home_ok"] = False
    try:
        foreign = _parse_decimal(row["foreignNotional"])
        expected_foreign = size * price
        denom = expected_foreign if expected_foreign != 0 else Decimal(1)
        result["foreign_ok"] = abs(foreign - expected_foreign) <= abs(denom) * Decimal("1e-6")
    except (InvalidOperation, KeyError, TypeError):
        result["foreign_ok"] = False
        foreign = None
    try:
        gross = _parse_decimal(row["grossValue"])
        if foreign is not None:
            expected_gross = foreign * Decimal("1e8")
            denom = expected_gross if expected_gross != 0 else Decimal(1)
            result["gross_ok"] = abs(gross - expected_gross) <= abs(denom) * Decimal("1e-6")
        else:
            result["gross_ok"] = False
    except (InvalidOperation, KeyError, TypeError):
        result["gross_ok"] = False
    return result


def _canonical_duplicate_representative(group: list) -> tuple:
    """Deterministic, arrival-order-independent representative for a group
    already classified as an equivalent (non-conflicting) duplicate -- see
    experiments/data/r1_normalized_evidence_duplicate_semantics_amendment_v1.json:
    duplicate_representative_selection_rule. `group` entries are
    `(ts, trade_id, price, size)` with `price`/`size` already `Decimal`;
    every member is numerically equal in price and size by construction (the
    caller only reaches this branch once the group's `distinct` set has
    already collapsed to one element), so choosing among them changes no
    numeric value. `str(Decimal(token))` reproduces the original plain
    fixed-point source token for the grammar this rule is scoped to (no
    normalization occurs), so comparing the stringified price/size is
    equivalent to comparing the original source spellings without this
    parser separately retaining the raw tokens. The tie-break key orders on
    price first, then size, matching the frozen rule's
    (price_source_string, size_source_string) pair.
    """
    return min(group, key=lambda g: (str(g[2]), str(g[3])))


def parse_daily_object(
    raw_bytes: bytes,
    expected_utc_date: date,
    instrument_instance_id: str,
) -> DailyParseResult:
    """Parse one raw (gzip-compressed CSV) Bybit trade archive object.

    Returns a DailyParseResult whose `record`, when status is OK, is shaped
    exactly per DailyMarketEvidenceV1 (experiments/data/r1_normalized_evidence_contract_v1.json).
    """
    source_object_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    if len(raw_bytes) == 0:
        return DailyParseResult(
            status=STATUS_EMPTY_OBJECT,
            schema_id=None,
            record=_empty_record(instrument_instance_id, expected_utc_date, source_object_sha256, schema_id=None),
            rejected_row_count=0,
            duplicate_count=0,
            diagnostics={"note": "zero-byte raw object"},
        )

    text = _decompress(raw_bytes)
    truncated_tail = not text.endswith("\n")
    lines = text.splitlines()

    if not lines:
        return DailyParseResult(
            status=STATUS_EMPTY_OBJECT,
            schema_id=None,
            record=_empty_record(instrument_instance_id, expected_utc_date, source_object_sha256, schema_id=None),
            rejected_row_count=0,
            duplicate_count=0,
            diagnostics={"note": "no lines after decompression"},
        )

    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise TruncatedCSVError("no header row present") from exc

    if len(header) < 2:
        raise TruncatedCSVError("header has fewer than 2 columns")

    schema_id = identify_schema(header)
    if schema_id is None:
        return DailyParseResult(
            status=STATUS_UNKNOWN_SCHEMA_QUARANTINE,
            schema_id=None,
            record=None,
            rejected_row_count=max(len(lines) - 1, 0),
            duplicate_count=0,
            diagnostics={
                "observed_columns": header,
                "quarantine_reason": "no registered known_schema_variant matches this column set",
            },
        )

    body_rows = list(csv.DictReader(io.StringIO(text)))
    if body_rows and truncated_tail:
        last = body_rows[-1]
        if any(v is None for v in last.values()) or None in last:
            body_rows = body_rows[:-1]

    rejected_row_count = 0
    duplicate_count = 0
    redundant_mismatches = {"home": 0, "foreign": 0, "gross": 0}
    rpi_values = set()
    valid_rows = []  # (timestamp_decimal, trdMatchID, price, size)

    for row in body_rows:
        if any(row.get(k) in (None, "") for k in REQUIRED_ROW_FIELDS):
            rejected_row_count += 1
            continue
        try:
            ts = _parse_decimal(row["timestamp"])
            price = _parse_decimal(row["price"])
            size = _parse_decimal(row["size"])
        except InvalidOperation:
            rejected_row_count += 1
            continue

        trade_id = row["trdMatchID"]

        try:
            event_date = _utc_date_of(ts)
        except (OverflowError, OSError, ValueError):
            rejected_row_count += 1
            continue

        if event_date > CUTOFF_UTC_DATE:
            rejected_row_count += 1
            continue
        if expected_utc_date is not None and event_date != expected_utc_date:
            rejected_row_count += 1
            continue

        if schema_id == "bybit_trade_v1_rpi":
            rpi_values.add(row.get("RPI"))

        checks = _redundant_field_check(price, size, row)
        if checks["home_ok"] is False:
            redundant_mismatches["home"] += 1
        if checks["foreign_ok"] is False:
            redundant_mismatches["foreign"] += 1
        if checks["gross_ok"] is False:
            redundant_mismatches["gross"] += 1

        valid_rows.append((ts, trade_id, price, size))

    by_id: dict = {}
    for r in valid_rows:
        by_id.setdefault(r[1], []).append(r)

    canonical = []
    conflicting_ids = []
    for trade_id, group in by_id.items():
        if len(group) == 1:
            canonical.append(group[0])
            continue
        distinct = {(g[0], g[2], g[3]) for g in group}
        if len(distinct) == 1:
            canonical.append(_canonical_duplicate_representative(group))
            duplicate_count += len(group) - 1
        else:
            conflicting_ids.append(trade_id)
            rejected_row_count += len(group)

    canonical.sort(key=lambda r: (r[0], r[1]))

    trade_count = len(canonical)
    if trade_count == 0:
        record = _empty_record(instrument_instance_id, expected_utc_date, source_object_sha256, schema_id)
        record["duplicate_count"] = duplicate_count
        record["rejected_row_count"] = rejected_row_count
    else:
        prices = [r[2] for r in canonical]
        sizes = [r[3] for r in canonical]
        base_volume = sum(sizes)
        quote_turnover = sum(p * s for p, s in zip(prices, sizes))
        record = {
            "instrument_instance_id": instrument_instance_id,
            "utc_date": expected_utc_date.isoformat(),
            "open": str(prices[0]),
            "high": str(max(prices)),
            "low": str(min(prices)),
            "close": str(prices[-1]),
            "base_volume": str(base_volume),
            "quote_turnover": str(quote_turnover),
            "trade_count": trade_count,
            "first_source_timestamp_utc": _epoch_to_iso(canonical[0][0]),
            "last_source_timestamp_utc": _epoch_to_iso(canonical[-1][0]),
            "first_source_trade_id": canonical[0][1],
            "last_source_trade_id": canonical[-1][1],
            "duplicate_count": duplicate_count,
            "rejected_row_count": rejected_row_count,
            "schema_id": schema_id,
            "source_object_sha256": source_object_sha256,
        }

    diagnostics = {
        "redundant_field_mismatches": redundant_mismatches,
        "conflicting_duplicate_trade_ids": conflicting_ids,
        "rpi_observed_values": sorted(v for v in rpi_values if v is not None) if schema_id == "bybit_trade_v1_rpi" else None,
        "truncated_tail_detected": truncated_tail,
    }

    return DailyParseResult(
        status=STATUS_OK,
        schema_id=schema_id,
        record=record,
        rejected_row_count=rejected_row_count,
        duplicate_count=duplicate_count,
        diagnostics=diagnostics,
    )


SOURCE_MUTATION = "SOURCE_MUTATION"
SOURCE_UNCHANGED = "SOURCE_UNCHANGED"


def check_source_mutation(url: str, recorded_sha256: str, freshly_retrieved_sha256: str) -> dict:
    """Rehydration mutation check per Phase 10 of the reference-parser audit.

    Never overwrites `recorded_sha256` and never treats a mutated re-fetch as
    proof of the original derivation: the caller is expected to keep
    `recorded_sha256` as the immutable historical binding and surface this
    result as a diagnostic, not as a silent replacement.
    """
    if recorded_sha256 == freshly_retrieved_sha256:
        return {"url": url, "recorded_sha256": recorded_sha256, "status": SOURCE_UNCHANGED}
    return {
        "url": url,
        "recorded_sha256": recorded_sha256,
        "freshly_retrieved_sha256": freshly_retrieved_sha256,
        "status": SOURCE_MUTATION,
    }


def _empty_record(instrument_instance_id, expected_utc_date, source_object_sha256, schema_id) -> dict:
    return {
        "instrument_instance_id": instrument_instance_id,
        "utc_date": expected_utc_date.isoformat() if expected_utc_date else None,
        "open": None,
        "high": None,
        "low": None,
        "close": None,
        "base_volume": "0",
        "quote_turnover": "0",
        "trade_count": 0,
        "first_source_timestamp_utc": None,
        "last_source_timestamp_utc": None,
        "first_source_trade_id": None,
        "last_source_trade_id": None,
        "duplicate_count": 0,
        "rejected_row_count": 0,
        "schema_id": schema_id,
        "source_object_sha256": source_object_sha256,
    }
