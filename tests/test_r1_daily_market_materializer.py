"""Tests for the DailyMarketEvidenceV1 materialization boundary
(qntylab.r1_daily_market_materializer), closing the two blockers an
independent NEW CHAT review of commit 1d52ec1 established as open:

These tests exercise the INTERNAL, low-level, non-admission-gated
_materialize_parser_a_unadmitted primitive directly -- they verify the
boundary's own mechanical behavior (raw-hash binding, container-anomaly
conversion, contract-completeness validation, batch isolation), which is
independent of and predates schema admission. They do not exercise, and
must not be read as asserting anything about, the admission-gated public
materialize_parser_a entry point or schema-admitted evidence authority --
that is covered separately by
tests/test_r1_schema_admission_runtime_wiring_v1.py.

  1. source_object_sha256 was not bound into a complete DailyMarketEvidenceV1
     record for the Parser B path (daily_primitive() never receives raw
     bytes and never returns this field).
  2. GzipCorruptionError / TruncatedCSVError escaped as uncaught, per-object,
     batch-terminating exceptions instead of a typed fail-closed result.

A subsequent independent NEW CHAT review of the first repair attempt
(commit c90c54b) found that (2) was only partially closed: a gzip-valid
object whose decompressed body is not valid UTF-8 raises a bare
UnicodeDecodeError out of rp.parse_daily_object() (Parser A's own
_decompress() does not wrap that specific case in GzipCorruptionError), and
_materialize_parser_a_unadmitted() did not catch it -- so it still escaped and still
terminated materialize_batch() before later objects were attempted. The
tests from "gzip-valid invalid utf8 body" onward close that specific gap and
verify batch isolation directly (not just the isolated per-object
functions), while two narrow-catch safety tests confirm this fix did not
widen into a generic `except Exception`.

A second independent NEW CHAT hostile review of that repair (commit 3081118)
established TWO further, distinct blockers, closed by the tests from
"csv error oversized field" and "unterminated quote malformed row" onward:

  A. csv.Error: a gzip-valid, UTF-8-valid object whose CSV body is not
     tokenizable at all by the stdlib csv module (reproducer: a single field
     exceeding csv.field_size_limit()) raised a bare csv.Error out of both
     rp.parse_daily_object's own unwrapped body-row csv.DictReader parse
     (Parser A) and this module's own body-row csv.DictReader parse (Parser
     B), escaping materialize_batch exactly like the earlier
     UnicodeDecodeError gap. Classified with the other structurally-corrupt
     -container cases as CONTAINER_ANOMALY (whole-object tokenization
     failure, not a per-row issue) and closed the same way: an extended,
     still-narrow catch tuple at each boundary call site.

  B. A DISTINCT failure class, not conflated with (A): a structurally
     malformed CSV row (reproducer: an unterminated quote swallowing the
     remainder of one physical row, leaving csv.DictReader's restval=None in
     every column after the swallowed field) reaches
     qntylab.r1_retention_candidate.daily_primitive with required numeric
     columns set to None. daily_primitive already has an existing, frozen,
     contract-authorized malformed-row disposition for exactly this shape
     (reject the row, increment rejected_row_count, append
     ANOMALY_PARSE_REJECTION -- mirroring Parser A's own REQUIRED_ROW_FIELDS
     row-rejection check) but its own try/except only catches (KeyError,
     ValueError, InvalidOperation), not the TypeError that Decimal(None)/
     float(None) raise. This module does NOT catch TypeError (that would
     risk hiding an unrelated programming bug inside daily_primitive);
     instead it pre-filters rows against the exact column set daily_primitive
     numeric-converts, before calling it, and folds the pre-filtered count
     into daily_primitive's own rejected_row_count/anomaly accounting -- see
     r1_daily_market_materializer.py's module docstring and
     _prefilter_parser_b_rows. Additional narrow-catch safety tests confirm
     an unrelated, deliberately-injected TypeError (not this specific
     malformed-row shape) still propagates uncaught from both paths.

This module makes no scientific decision: it does not touch OHLC, duplicate,
timestamp, or event-order logic in either parser. Those remain covered by
their own existing, unmodified test files, re-run here only as a regression
gate (see the bottom of this file), not reimplemented.
"""
import csv
import gzip
import hashlib
import itertools
from datetime import date
from pathlib import Path

import pytest

from qntylab import r1_reference_parser as rp
from qntylab.r1_retention_candidate import BASE_SCHEMA
from qntylab.r1_daily_market_materializer import (
    MATERIALIZED_VALID,
    MATERIALIZATION_QUARANTINED,
    INTERNAL_PARSER_A_CANDIDATE,
    _materialize_parser_a_unadmitted,
    materialize_parser_b,
    materialize_batch,
    validate_daily_market_evidence_v1,
    ALL_CONTRACT_FIELDS,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / ".r1_input_cache/sha256"
CUTOFF = "2026-06-30T23:59:59Z"

HEADER = ("timestamp", "symbol", "side", "size", "price", "tickDirection",
          "trdMatchID", "grossValue", "homeNotional", "foreignNotional")

REAL_OBJECTS = [
    ("BTCUSDT_2020-03-25", "cbca6933a8f0a11429661cfa93b04056055d776ee199209e8af9719ad2060a33", date(2020, 3, 25)),
    ("UNIUSDT_2021-11-30", "8068ed2f06c280ad103b50525c4c8bc14a3a956a6ed40f4fba50ff738d59ebb4", date(2021, 11, 30)),
    ("ANCUSDT_2022-03-15", "cabc599c8d0b2da8df4bb07de64700092701ac8bf4987ee8b4395bef8a6398d2", date(2022, 3, 15)),
    ("FTTUSDT_2022-11-13", "8c085036c9b65a99379941434f3531fa7365b24e31a752cd10a0d80ea8df77fc", date(2022, 11, 13)),
    ("1000000CHEEMSUSDT_2026-05-28", "d1b50f8316c1874d7ae7bde11314d077f3cf1b2baece4a6cdd7459e83cc2ce2a", date(2026, 5, 28)),
]


def _row(ts, size, price, trdid, side="Buy", tickdir="PlusTick"):
    size_f, price_f = float(size), float(price)
    return {"timestamp": str(ts), "symbol": "MONUSDT", "side": side, "size": size, "price": price,
            "tickDirection": tickdir, "trdMatchID": trdid, "grossValue": str(size_f * price_f * 1e8),
            "homeNotional": str(size_f), "foreignNotional": str(size_f * price_f)}


def _raw_bytes(rows):
    text = ",".join(HEADER) + "\n" + "\n".join(",".join(str(row[h]) for h in HEADER) for row in rows) + "\n"
    return gzip.compress(text.encode())


# --- 1/2. raw SHA binding for both parser paths -----------------------------

def test_parser_a_raw_sha_binding():
    raw = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="t-1")])
    result = _materialize_parser_a_unadmitted(raw, date(2023, 11, 14), "x")
    assert result.status == INTERNAL_PARSER_A_CANDIDATE
    assert result.record["source_object_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result.raw_object_sha256 == hashlib.sha256(raw).hexdigest()


def test_parser_b_raw_sha_binding():
    raw = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="t-1")])
    result = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)
    assert result.status == MATERIALIZED_VALID
    assert result.record["source_object_sha256"] == hashlib.sha256(raw).hexdigest()


def test_parser_b_source_object_sha256_bound_even_at_zero_trades():
    """Contract missingness_semantics: null only when trade_count=0 AND no
    object was retrievable. This boundary always has raw_bytes in hand, so
    the object was always retrievable -- the field must stay bound even for
    a valid, zero-trade day."""
    raw = gzip.compress((",".join(HEADER) + "\n").encode())  # header only, zero rows
    result = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)
    assert result.status == MATERIALIZED_VALID
    assert result.record["trade_count"] == 0
    assert result.record["source_object_sha256"] == hashlib.sha256(raw).hexdigest()


# --- 3/15. A/B complete-record equality, including source_object_sha256 ----

def test_ab_complete_record_equality_synthetic():
    raw = _raw_bytes([
        _row("1700000000.000", size="1", price="100", trdid="t-1"),
        _row("1700000100.000", size="2", price="103", trdid="t-2"),
    ])
    a = _materialize_parser_a_unadmitted(raw, date(2023, 11, 14), "obj")
    b = materialize_parser_b(raw, "2023-11-14", "obj", CUTOFF)
    assert a.status == INTERNAL_PARSER_A_CANDIDATE
    assert b.status == MATERIALIZED_VALID
    for field in ALL_CONTRACT_FIELDS:
        assert a.record[field] == b.record[field], field


def test_real_5_objects_full_record_equality():
    checked = 0
    for name, sha, day in REAL_OBJECTS:
        path = CACHE_DIR / sha
        if not path.exists():
            continue
        raw = path.read_bytes()
        a = _materialize_parser_a_unadmitted(raw, day, name)
        b = materialize_parser_b(raw, day.isoformat(), name, CUTOFF)
        assert a.status == INTERNAL_PARSER_A_CANDIDATE, (name, a.reason)
        assert b.status == MATERIALIZED_VALID, (name, b.reason)
        for field in ALL_CONTRACT_FIELDS:
            assert a.record[field] == b.record[field], (name, field, a.record[field], b.record[field])
        assert a.record["source_object_sha256"] == hashlib.sha256(raw).hexdigest()
        assert b.record["source_object_sha256"] == hashlib.sha256(raw).hexdigest()
        checked += 1
    assert checked == 5, "expected all 5 cached real pilot objects to be present"


# --- 4/16. source hash binds exact raw bytes, not logical content -----------

def test_source_sha_differs_on_byte_different_logically_equal_objects():
    rows = [
        _row("1700000000.000", size="1", price="100", trdid="t-1"),
        _row("1700000100.000", size="2", price="103", trdid="t-2"),
    ]
    raw_fwd = _raw_bytes(rows)
    raw_rev = _raw_bytes(list(reversed(rows)))
    assert raw_fwd != raw_rev  # sanity: genuinely different raw bytes

    a_fwd = _materialize_parser_a_unadmitted(raw_fwd, date(2023, 11, 14), "x")
    a_rev = _materialize_parser_a_unadmitted(raw_rev, date(2023, 11, 14), "x")
    b_fwd = materialize_parser_b(raw_fwd, "2023-11-14", "s", CUTOFF)
    b_rev = materialize_parser_b(raw_rev, "2023-11-14", "s", CUTOFF)

    # canonical derived fields: identical (row order does not affect them)
    for field in ("open", "close", "base_volume", "quote_turnover", "trade_count"):
        assert a_fwd.record[field] == a_rev.record[field] == b_fwd.record[field] == b_rev.record[field]

    # source_object_sha256: MUST differ (binds literal raw bytes, not content)
    assert a_fwd.record["source_object_sha256"] != a_rev.record["source_object_sha256"]
    assert b_fwd.record["source_object_sha256"] != b_rev.record["source_object_sha256"]
    assert a_fwd.record["source_object_sha256"] == b_fwd.record["source_object_sha256"]
    assert a_rev.record["source_object_sha256"] == b_rev.record["source_object_sha256"]


# --- 5. required-field / contract-completeness validation -------------------

def test_validator_rejects_missing_key():
    good = {f: None for f in ALL_CONTRACT_FIELDS}
    good.update({"instrument_instance_id": "x", "utc_date": "2023-11-14", "trade_count": 0,
                 "duplicate_count": 0, "rejected_row_count": 0, "schema_id": "bybit_trade_v1",
                 "base_volume": "0", "quote_turnover": "0", "source_object_sha256": "a" * 64})
    del good["schema_id"]
    violations = validate_daily_market_evidence_v1(good)
    assert violations and "missing required contract keys" in violations[0]


def test_validator_accepts_well_formed_zero_trade_record():
    good = {f: None for f in ALL_CONTRACT_FIELDS}
    good.update({"instrument_instance_id": "x", "utc_date": "2023-11-14", "trade_count": 0,
                 "duplicate_count": 0, "rejected_row_count": 0, "schema_id": "bybit_trade_v1",
                 "base_volume": "0", "quote_turnover": "0", "source_object_sha256": "a" * 64})
    assert validate_daily_market_evidence_v1(good) == []


# --- 6/7. missing / wrong source_object_sha256 fails closed -----------------

def test_missing_source_object_sha256_cannot_be_a_valid_record():
    record = {f: None for f in ALL_CONTRACT_FIELDS}
    record.update({"instrument_instance_id": "x", "utc_date": "2023-11-14", "trade_count": 1,
                   "duplicate_count": 0, "rejected_row_count": 0, "schema_id": "bybit_trade_v1",
                   "open": "1", "high": "1", "low": "1", "close": "1",
                   "base_volume": "1", "quote_turnover": "1",
                   "first_source_timestamp_utc": "2023-11-14T00:00:00.000Z",
                   "last_source_timestamp_utc": "2023-11-14T00:00:00.000Z",
                   "first_source_trade_id": "t-1", "last_source_trade_id": "t-1",
                   "source_object_sha256": None})
    violations = validate_daily_market_evidence_v1(record)
    assert any("source_object_sha256" in v for v in violations)


def test_parser_a_wrong_expected_raw_sha256_fails_closed():
    raw = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="t-1")])
    result = _materialize_parser_a_unadmitted(raw, date(2023, 11, 14), "x", expected_raw_sha256="0" * 64)
    assert result.status == MATERIALIZATION_QUARANTINED
    assert result.record is None


def test_parser_b_wrong_expected_raw_sha256_fails_closed():
    raw = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="t-1")])
    result = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF, expected_raw_sha256="0" * 64)
    assert result.status == MATERIALIZATION_QUARANTINED
    assert result.record is None


# --- 8/9/10/11. malformed / corrupt container handling ----------------------

def test_gzip_corrupt_bytes_typed_quarantine_both_parsers():
    garbage = b"not gzip data at all!!"
    a = _materialize_parser_a_unadmitted(garbage, date(2023, 11, 14), "x")
    b = materialize_parser_b(garbage, "2023-11-14", "s", CUTOFF)
    assert a.status == b.status == MATERIALIZATION_QUARANTINED
    assert a.record is None and b.record is None
    assert "CONTAINER_ANOMALY" in a.anomalies
    assert "CONTAINER_ANOMALY" in b.anomalies


def test_gzip_valid_truncated_one_column_header_typed_quarantine_both_parsers():
    truncated = gzip.compress(b"t\n")
    a = _materialize_parser_a_unadmitted(truncated, date(2023, 11, 14), "x")
    b = materialize_parser_b(truncated, "2023-11-14", "s", CUTOFF)
    assert a.status == b.status == MATERIALIZATION_QUARANTINED
    assert "CONTAINER_ANOMALY" in a.anomalies
    assert "CONTAINER_ANOMALY" in b.anomalies


def test_gzip_valid_invalid_utf8_body_typed_quarantine_both_parsers():
    """Regression for the independent-review blocker on c90c54b: gzip-valid
    bytes whose decompressed body is not valid UTF-8 raise a bare
    UnicodeDecodeError out of qntylab.r1_reference_parser.parse_daily_object
    (its own _decompress() does not wrap this case in GzipCorruptionError --
    see r1_daily_market_materializer module docstring). Both parser paths
    must reach the same typed CONTAINER_ANOMALY quarantine as any other
    container-level corruption, not let the exception escape."""
    bad_utf8 = b"\xff\xfe\x00invalid utf8 csv content\n"
    raw = gzip.compress(bad_utf8)
    a = _materialize_parser_a_unadmitted(raw, date(2023, 11, 14), "x")
    b = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)
    assert a.status == b.status == MATERIALIZATION_QUARANTINED
    assert a.record is None and b.record is None
    assert "CONTAINER_ANOMALY" in a.anomalies
    assert "CONTAINER_ANOMALY" in b.anomalies


def test_empty_raw_bytes_now_quarantined_for_parser_a_still_valid_for_parser_b():
    """Parser A's behavior on raw b"" changed under the frozen-G recognition
    repair: qntylab.r1_schema_recognizer's own frozen fixture
    (empty_raw_object in tests/test_r1_schema_recognizer.py) classifies
    zero-length raw bytes as FRAMING_FAILURE(INVALID_GZIP) -- a
    zlib.decompressobj configured for gzip framing never reaches a validated
    end-of-stream on zero input, so this is genuine container corruption, not
    an empty day. Parser A's pre-repair behavior (an ad hoc
    `len(raw_bytes) == 0` special case bypassing recognition entirely) is
    exactly the kind of independent framing decision this repair removes.
    Parser B is unrepaired and out of scope for this task; its own,
    unchanged, non-frozen-conformant treatment of raw b"" as a valid
    zero-trade record is left as-is and verified here only so this
    divergence is explicit, not silently lost."""
    a = _materialize_parser_a_unadmitted(b"", date(2023, 11, 14), "x")
    assert a.status == MATERIALIZATION_QUARANTINED
    assert a.record is None
    assert "CONTAINER_ANOMALY" in a.anomalies

    b = materialize_parser_b(b"", "2023-11-14", "s", CUTOFF)
    assert b.status == MATERIALIZED_VALID
    assert b.record["trade_count"] == 0
    assert b.record["source_object_sha256"] == hashlib.sha256(b"").hexdigest()


def test_gzip_valid_empty_body_typed_valid_zero_trade_record():
    empty_body = gzip.compress(b"")
    a = _materialize_parser_a_unadmitted(empty_body, date(2023, 11, 14), "x")
    b = materialize_parser_b(empty_body, "2023-11-14", "s", CUTOFF)
    assert a.status == INTERNAL_PARSER_A_CANDIDATE
    assert b.status == MATERIALIZED_VALID
    assert a.record["trade_count"] == 0
    assert b.record["trade_count"] == 0


def test_malformed_row_still_typed_valid_with_rejection_accounted():
    text = (",".join(HEADER) + "\n"
            + "notanumber,X,Buy,1,1,PlusTick,id1,1e8,1,1\n"
            + "1700000000,X,Buy,1,1,PlusTick,id2,1e8,1,1\n")
    raw = gzip.compress(text.encode())
    a = _materialize_parser_a_unadmitted(raw, date(2023, 11, 14), "x")
    b = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)
    assert a.status == INTERNAL_PARSER_A_CANDIDATE
    assert b.status == MATERIALIZED_VALID
    assert a.record["rejected_row_count"] == 1
    assert b.record["rejected_row_count"] == 1
    assert a.record["trade_count"] == 1
    assert b.record["trade_count"] == 1


# --- 12/13. batch isolation / one-result-per-attempt accounting ------------

def test_batch_isolation_valid_corrupt_valid():
    valid_a = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="a-1")])
    corrupt = b"not gzip data at all!!"
    valid_c = _raw_bytes([_row("1700000000.000", size="2", price="2", trdid="c-1")])

    items = [
        (valid_a, date(2023, 11, 14), "x|A"),
        (corrupt, date(2023, 11, 14), "x|B"),
        (valid_c, date(2023, 11, 14), "x|C"),
    ]
    results = materialize_batch(items, _materialize_parser_a_unadmitted)

    assert len(results) == 3
    assert results[0].status == INTERNAL_PARSER_A_CANDIDATE
    assert results[1].status == MATERIALIZATION_QUARANTINED
    assert results[2].status == INTERNAL_PARSER_A_CANDIDATE
    # object B's corruption did not prevent C from being attempted/valid
    assert results[2].record["first_source_trade_id"] == "c-1"

    valid_count = sum(1 for r in results if r.status == INTERNAL_PARSER_A_CANDIDATE)
    quarantined_count = sum(1 for r in results if r.status == MATERIALIZATION_QUARANTINED)
    assert valid_count + quarantined_count == len(items) == 3
    assert all(r.status in (INTERNAL_PARSER_A_CANDIDATE, MATERIALIZATION_QUARANTINED) for r in results)


def test_batch_isolation_parser_b():
    valid_a = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="a-1")])
    corrupt = gzip.compress(b"t\n")
    valid_c = _raw_bytes([_row("1700000000.000", size="2", price="2", trdid="c-1")])

    items = [
        (valid_a, "2023-11-14", "A", CUTOFF),
        (corrupt, "2023-11-14", "B", CUTOFF),
        (valid_c, "2023-11-14", "C", CUTOFF),
    ]
    results = materialize_batch(items, materialize_parser_b)
    assert [r.status for r in results] == [MATERIALIZED_VALID, MATERIALIZATION_QUARANTINED, MATERIALIZED_VALID]
    assert results[2].record["first_source_trade_id"] == "c-1"


def test_batch_isolation_invalid_utf8_valid_corrupt_valid_parser_a():
    """Direct regression for the reproduced review blocker: previously the
    bare UnicodeDecodeError from object B escaped _materialize_parser_a_unadmitted and
    terminated materialize_batch's loop before object C was ever attempted."""
    valid_a = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="a-1")])
    bad_utf8 = gzip.compress(b"\xff\xfe\x00invalid utf8 csv content\n")
    valid_c = _raw_bytes([_row("1700000000.000", size="2", price="2", trdid="c-1")])

    items = [
        (valid_a, date(2023, 11, 14), "x|A"),
        (bad_utf8, date(2023, 11, 14), "x|B"),
        (valid_c, date(2023, 11, 14), "x|C"),
    ]
    results = materialize_batch(items, _materialize_parser_a_unadmitted)

    assert len(results) == 3, "object C was not attempted -- batch terminated early"
    assert results[0].status == INTERNAL_PARSER_A_CANDIDATE
    assert results[1].status == MATERIALIZATION_QUARANTINED
    assert "CONTAINER_ANOMALY" in results[1].anomalies
    assert results[2].status == INTERNAL_PARSER_A_CANDIDATE
    assert results[2].record["first_source_trade_id"] == "c-1"

    valid_count = sum(1 for r in results if r.status == INTERNAL_PARSER_A_CANDIDATE)
    typed_nonvalid_count = sum(1 for r in results if r.status == MATERIALIZATION_QUARANTINED)
    assert valid_count + typed_nonvalid_count == len(items) == 3


def test_batch_isolation_invalid_utf8_valid_corrupt_valid_parser_b():
    valid_a = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="a-1")])
    bad_utf8 = gzip.compress(b"\xff\xfe\x00invalid utf8 csv content\n")
    valid_c = _raw_bytes([_row("1700000000.000", size="2", price="2", trdid="c-1")])

    items = [
        (valid_a, "2023-11-14", "A", CUTOFF),
        (bad_utf8, "2023-11-14", "B", CUTOFF),
        (valid_c, "2023-11-14", "C", CUTOFF),
    ]
    results = materialize_batch(items, materialize_parser_b)
    assert len(results) == 3, "object C was not attempted -- batch terminated early"
    assert [r.status for r in results] == [MATERIALIZED_VALID, MATERIALIZATION_QUARANTINED, MATERIALIZED_VALID]
    assert "CONTAINER_ANOMALY" in results[1].anomalies
    assert results[2].record["first_source_trade_id"] == "c-1"

    valid_count = sum(1 for r in results if r.status == MATERIALIZED_VALID)
    typed_nonvalid_count = sum(1 for r in results if r.status == MATERIALIZATION_QUARANTINED)
    assert valid_count + typed_nonvalid_count == len(items) == 3


def test_batch_isolation_alternating_corrupt_valid_four_objects_both_parsers():
    """corrupt / valid / corrupt / valid: the second corrupt object (C) must
    not prevent D from being attempted, for either parser path."""
    corrupt_a = b"not gzip data at all!!"
    valid_b = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="b-1")])
    corrupt_c = gzip.compress(b"\xff\xfe\x00invalid utf8 csv content\n")
    valid_d = _raw_bytes([_row("1700000000.000", size="2", price="2", trdid="d-1")])

    a_items = [
        (corrupt_a, date(2023, 11, 14), "x|A"),
        (valid_b, date(2023, 11, 14), "x|B"),
        (corrupt_c, date(2023, 11, 14), "x|C"),
        (valid_d, date(2023, 11, 14), "x|D"),
    ]
    a_results = materialize_batch(a_items, _materialize_parser_a_unadmitted)
    assert len(a_results) == 4, "batch did not run to completion"
    assert [r.status for r in a_results] == [
        MATERIALIZATION_QUARANTINED, INTERNAL_PARSER_A_CANDIDATE, MATERIALIZATION_QUARANTINED, INTERNAL_PARSER_A_CANDIDATE,
    ]
    assert a_results[3].record["first_source_trade_id"] == "d-1"

    b_items = [
        (corrupt_a, "2023-11-14", "A", CUTOFF),
        (valid_b, "2023-11-14", "B", CUTOFF),
        (corrupt_c, "2023-11-14", "C", CUTOFF),
        (valid_d, "2023-11-14", "D", CUTOFF),
    ]
    b_results = materialize_batch(b_items, materialize_parser_b)
    assert len(b_results) == 4, "batch did not run to completion"
    assert [r.status for r in b_results] == [
        MATERIALIZATION_QUARANTINED, MATERIALIZED_VALID, MATERIALIZATION_QUARANTINED, MATERIALIZED_VALID,
    ]
    assert b_results[3].record["first_source_trade_id"] == "d-1"


def test_unadmitted_parser_a_does_not_swallow_unrelated_exceptions(monkeypatch):
    """Narrow-catch safety: _materialize_parser_a_unadmitted must only convert the three
    explicitly-authorized container-corruption classes (GzipCorruptionError,
    TruncatedCSVError, UnicodeDecodeError) into CONTAINER_ANOMALY. Any other
    exception -- e.g. a genuine programming error inside rp.parse_daily_object
    -- must still propagate uncaught, not be mislabeled as corrupt evidence."""
    import qntylab.r1_reference_parser as rp

    def _boom(raw_bytes, expected_utc_date, instrument_instance_id):
        raise RuntimeError("unrelated programming error, not container corruption")

    monkeypatch.setattr(rp, "parse_daily_object", _boom)
    raw = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="t-1")])
    with pytest.raises(RuntimeError, match="unrelated programming error"):
        _materialize_parser_a_unadmitted(raw, date(2023, 11, 14), "x")


def test_materialize_parser_b_does_not_swallow_unrelated_exceptions(monkeypatch):
    """Same narrow-catch safety property for the Parser B path: only
    rp.GzipCorruptionError / rp.TruncatedCSVError raised by this module's own
    _decode_container are converted to CONTAINER_ANOMALY; an unrelated
    exception from rc.daily_primitive itself must still propagate."""
    import qntylab.r1_retention_candidate as rc_mod

    def _boom(**kwargs):
        raise RuntimeError("unrelated programming error, not container corruption")

    monkeypatch.setattr(rc_mod, "daily_primitive", _boom)
    raw = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="t-1")])
    with pytest.raises(RuntimeError, match="unrelated programming error"):
        materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)


# --- 20/21. csv.Error (field-size-limit) container corruption --------------
# Independent hostile-review-#2 blocker on 3081118: a gzip-valid, UTF-8-valid
# CSV body with a field exceeding csv.field_size_limit() is not tokenizable
# by the stdlib csv module at all and raised bare csv.Error out of both
# parser paths' body-row csv.DictReader parse, escaping materialize_batch.

def _oversized_field_row_text(field_len=None):
    huge = "X" * ((field_len or csv.field_size_limit()) + 1)
    return f"1700000000.000,{huge},Buy,1,1,PlusTick,t-1,1,1,1\n"


def test_csv_error_oversized_data_field_typed_quarantine_both_parsers():
    raw = gzip.compress((",".join(HEADER) + "\n" + _oversized_field_row_text()).encode())
    a = _materialize_parser_a_unadmitted(raw, date(2023, 11, 14), "x")
    b = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)
    assert a.status == b.status == MATERIALIZATION_QUARANTINED
    assert a.record is None and b.record is None
    assert "CONTAINER_ANOMALY" in a.anomalies
    assert "CONTAINER_ANOMALY" in b.anomalies


def test_csv_error_oversized_header_field_typed_quarantine_both_parsers():
    """The same csv.Error can also occur while parsing the header row itself
    (this module's own _decode_container header-parse, and Parser B's own
    header handling), not only the body -- a distinct call site from the
    oversized-data-field case above.

    Parser A's behavior here changed under the frozen-G recognition repair:
    qntylab.r1_schema_recognizer derives the header via a naive comma split
    on the header line, entirely independent of the stdlib csv module's
    field_size_limit -- so an oversized header token is just a very long,
    unmatched field name to frozen G, not a container-level tokenization
    failure. It is correctly classified NO_MATCH (UNKNOWN_SCHEMA_QUARANTINE),
    never a false MATERIALIZED_VALID. Parser B is unrepaired and still routes
    header extraction through Python's csv module, so it still hits a bare
    csv.Error here and is still quarantined as CONTAINER_ANOMALY -- the two
    parsers now diverge in *anomaly label* but both still correctly refuse to
    emit a record."""
    huge = "X" * (csv.field_size_limit() + 1)
    text = f"timestamp,{huge},side,size,price,tickDirection,trdMatchID,grossValue,homeNotional,foreignNotional\n1700000000.000,SYM,Buy,1,1,PlusTick,t-1,1,1,1\n"
    raw = gzip.compress(text.encode())
    a = _materialize_parser_a_unadmitted(raw, date(2023, 11, 14), "x")
    b = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)
    assert a.status == b.status == MATERIALIZATION_QUARANTINED
    assert a.record is None and b.record is None
    assert "UNKNOWN_SCHEMA_QUARANTINE" in a.anomalies
    assert "CONTAINER_ANOMALY" in b.anomalies


def test_batch_isolation_csv_error_valid_corrupt_valid_parser_a():
    """Direct regression for the reproduced review blocker: previously the
    bare csv.Error from object B escaped _materialize_parser_a_unadmitted and terminated
    materialize_batch's loop before object C was ever attempted."""
    valid_a = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="a-1")])
    csv_corrupt = gzip.compress((",".join(HEADER) + "\n" + _oversized_field_row_text()).encode())
    valid_c = _raw_bytes([_row("1700000000.000", size="2", price="2", trdid="c-1")])

    items = [
        (valid_a, date(2023, 11, 14), "x|A"),
        (csv_corrupt, date(2023, 11, 14), "x|B"),
        (valid_c, date(2023, 11, 14), "x|C"),
    ]
    results = materialize_batch(items, _materialize_parser_a_unadmitted)

    assert len(results) == 3, "object C was not attempted -- batch terminated early"
    assert results[0].status == INTERNAL_PARSER_A_CANDIDATE
    assert results[1].status == MATERIALIZATION_QUARANTINED
    assert "CONTAINER_ANOMALY" in results[1].anomalies
    assert results[2].status == INTERNAL_PARSER_A_CANDIDATE
    assert results[2].record["first_source_trade_id"] == "c-1"

    valid_count = sum(1 for r in results if r.status == INTERNAL_PARSER_A_CANDIDATE)
    typed_nonvalid_count = sum(1 for r in results if r.status == MATERIALIZATION_QUARANTINED)
    assert valid_count + typed_nonvalid_count == len(items) == 3


def test_batch_isolation_csv_error_valid_corrupt_valid_parser_b():
    valid_a = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="a-1")])
    csv_corrupt = gzip.compress((",".join(HEADER) + "\n" + _oversized_field_row_text()).encode())
    valid_c = _raw_bytes([_row("1700000000.000", size="2", price="2", trdid="c-1")])

    items = [
        (valid_a, "2023-11-14", "A", CUTOFF),
        (csv_corrupt, "2023-11-14", "B", CUTOFF),
        (valid_c, "2023-11-14", "C", CUTOFF),
    ]
    results = materialize_batch(items, materialize_parser_b)
    assert len(results) == 3, "object C was not attempted -- batch terminated early"
    assert [r.status for r in results] == [MATERIALIZED_VALID, MATERIALIZATION_QUARANTINED, MATERIALIZED_VALID]
    assert "CONTAINER_ANOMALY" in results[1].anomalies
    assert results[2].record["first_source_trade_id"] == "c-1"

    valid_count = sum(1 for r in results if r.status == MATERIALIZED_VALID)
    typed_nonvalid_count = sum(1 for r in results if r.status == MATERIALIZATION_QUARANTINED)
    assert valid_count + typed_nonvalid_count == len(items) == 3


def test_batch_isolation_alternating_csv_error_corrupt_valid_four_objects_both_parsers():
    """corrupt / valid / corrupt / valid using the csv.Error fixture: the
    second corrupt object (C) must not prevent D from being attempted, for
    either parser path."""
    corrupt_a = b"not gzip data at all!!"
    valid_b = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="b-1")])
    corrupt_c = gzip.compress((",".join(HEADER) + "\n" + _oversized_field_row_text()).encode())
    valid_d = _raw_bytes([_row("1700000000.000", size="2", price="2", trdid="d-1")])

    a_items = [
        (corrupt_a, date(2023, 11, 14), "x|A"),
        (valid_b, date(2023, 11, 14), "x|B"),
        (corrupt_c, date(2023, 11, 14), "x|C"),
        (valid_d, date(2023, 11, 14), "x|D"),
    ]
    a_results = materialize_batch(a_items, _materialize_parser_a_unadmitted)
    assert len(a_results) == 4, "batch did not run to completion"
    assert [r.status for r in a_results] == [
        MATERIALIZATION_QUARANTINED, INTERNAL_PARSER_A_CANDIDATE, MATERIALIZATION_QUARANTINED, INTERNAL_PARSER_A_CANDIDATE,
    ]
    assert a_results[3].record["first_source_trade_id"] == "d-1"

    b_items = [
        (corrupt_a, "2023-11-14", "A", CUTOFF),
        (valid_b, "2023-11-14", "B", CUTOFF),
        (corrupt_c, "2023-11-14", "C", CUTOFF),
        (valid_d, "2023-11-14", "D", CUTOFF),
    ]
    b_results = materialize_batch(b_items, materialize_parser_b)
    assert len(b_results) == 4, "batch did not run to completion"
    assert [r.status for r in b_results] == [
        MATERIALIZATION_QUARANTINED, MATERIALIZED_VALID, MATERIALIZATION_QUARANTINED, MATERIALIZED_VALID,
    ]
    assert b_results[3].record["first_source_trade_id"] == "d-1"


def test_unadmitted_parser_a_does_not_swallow_unrelated_typeerror(monkeypatch):
    """Section-9 no-catch-all safety, specific to TypeError: an arbitrary,
    unrelated TypeError raised inside rp.parse_daily_object (a genuine
    programming error, NOT the csv.DictReader restval=None row shape this
    repair targets) must still propagate uncaught. The repair never adds
    TypeError to _materialize_parser_a_unadmitted's catch tuple -- only csv.Error -- so
    this should already hold, but is asserted directly rather than inferred."""
    monkeypatch.setattr(rp, "parse_daily_object",
                         lambda *a, **k: (_ for _ in ()).throw(TypeError("unrelated programming TypeError")))
    raw = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="t-1")])
    with pytest.raises(TypeError, match="unrelated programming TypeError"):
        _materialize_parser_a_unadmitted(raw, date(2023, 11, 14), "x")


def test_materialize_parser_b_does_not_swallow_unrelated_typeerror(monkeypatch):
    """Same property for Parser B: materialize_parser_b never catches
    TypeError anywhere (it prevents the specific None-valued-required-field
    TypeError by pre-filtering row *data* before calling daily_primitive, not
    by catching the exception class) -- an unrelated TypeError raised inside
    rc.daily_primitive itself must still propagate uncaught."""
    import qntylab.r1_retention_candidate as rc_mod

    def _boom(**kwargs):
        raise TypeError("unrelated programming TypeError, not a malformed-row shape")

    monkeypatch.setattr(rc_mod, "daily_primitive", _boom)
    raw = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="t-1")])
    with pytest.raises(TypeError, match="unrelated programming TypeError"):
        materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)


# --- 22. Parser-B TypeError blocker: unterminated-quote malformed row ------
# Independent hostile-review-#2 blocker on 3081118 (distinct from csv.Error
# above): an unterminated quote swallows the remainder of one physical row,
# leaving csv.DictReader's restval=None in every column after the swallowed
# field. daily_primitive's own row-parsing try/except does not catch the
# resulting TypeError from Decimal(None)/float(None). Both parsers must
# reach the SAME already-authorized malformed-row disposition (reject just
# that row, keep processing the rest) -- not merely "no exception".

def _unterminated_quote_body(n_good_rows=50):
    # canonical HEADER order, matching _raw_bytes' own serialization convention
    rows = [",".join(str(_row("1700000000.000", "1", "1", f"t-{i}")[h]) for h in HEADER) for i in range(n_good_rows)]
    rows.append('1700000000.000,"UNCLOSEDQUOTE,Buy,1,1,PlusTick,t-bad,1,1,1')
    return ",".join(HEADER) + "\n" + "\n".join(rows) + "\n"


def test_unterminated_quote_malformed_row_parser_a_and_b_agree_no_exception():
    raw = gzip.compress(_unterminated_quote_body(n_good_rows=50).encode())
    a = _materialize_parser_a_unadmitted(raw, date(2023, 11, 14), "x")
    b = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)

    assert a.status == INTERNAL_PARSER_A_CANDIDATE
    assert b.status == MATERIALIZED_VALID
    # Parser A already had its own REQUIRED_ROW_FIELDS row-rejection check
    # for exactly this row shape; Parser B's boundary-level pre-filter must
    # reach the identical disposition -- same trade_count, same
    # rejected_row_count -- not a different, boundary-invented outcome.
    assert a.record["trade_count"] == b.record["trade_count"] == 50
    assert a.record["rejected_row_count"] == b.record["rejected_row_count"] == 1
    assert "PARSE_REJECTION" in b.anomalies


def test_unterminated_quote_malformed_row_does_not_corrupt_other_rows_numeric_values():
    """The pre-filter must drop only the malformed row, not perturb any
    Decimal/OHLC value daily_primitive computes for the surviving rows."""
    raw = gzip.compress(_unterminated_quote_body(n_good_rows=3).encode())
    b = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)
    assert b.status == MATERIALIZED_VALID
    assert b.record["trade_count"] == 3
    assert b.record["close"] == "1"
    assert b.record["base_volume"] == "3"
    assert b.record["quote_turnover"] == "3"


def test_batch_isolation_unterminated_quote_valid_before_and_after():
    """The malformed-row object itself must still materialize as VALID (the
    row is rejected, the object is not), and must not prevent a subsequent
    object in the same batch from being attempted."""
    malformed_but_valid = gzip.compress(_unterminated_quote_body(n_good_rows=5).encode())
    valid_after = _raw_bytes([_row("1700000000.000", size="2", price="2", trdid="after-1")])

    items = [
        (malformed_but_valid, "2023-11-14", "A", CUTOFF),
        (valid_after, "2023-11-14", "B", CUTOFF),
    ]
    results = materialize_batch(items, materialize_parser_b)
    assert len(results) == 2
    assert results[0].status == MATERIALIZED_VALID
    assert results[0].record["rejected_row_count"] == 1
    assert results[1].status == MATERIALIZED_VALID
    assert results[1].record["first_source_trade_id"] == "after-1"


# --- 17. contract validator used identically on both parsers' output -------

def test_validator_used_on_both_parser_outputs_directly():
    raw = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="t-1")])
    a = _materialize_parser_a_unadmitted(raw, date(2023, 11, 14), "x")
    b = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)
    assert validate_daily_market_evidence_v1(a.record) == []
    assert validate_daily_market_evidence_v1(b.record) == []


# --- 18. independence: boundary does not make either parser call the other -

def _imported_modules(path: Path) -> set:
    import ast
    tree = ast.parse(path.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
    return imported


def test_boundary_module_does_not_import_across_parsers_transitively():
    boundary_imports = _imported_modules(REPO_ROOT / "qntylab/r1_daily_market_materializer.py")
    assert "qntylab.r1_reference_parser" in boundary_imports or "qntylab" in boundary_imports
    assert "qntylab.r1_retention_candidate" in boundary_imports or "qntylab" in boundary_imports
    # the parsers themselves still must not import each other (unchanged
    # property; AST-based, not substring search -- each module's own
    # docstring describes the independence property in prose and would
    # false-positive on a substring check)
    a_imports = _imported_modules(REPO_ROOT / "qntylab/r1_reference_parser.py")
    b_imports = _imported_modules(REPO_ROOT / "qntylab/r1_retention_candidate.py")
    assert not any("r1_retention_candidate" in m for m in a_imports)
    assert not any("r1_reference_parser" in m for m in b_imports)


# --- 19. semantic-parser regression gate (no reimplementation, just re-run) -

def test_regression_timestamp_numeric_duplicate_event_order_untouched():
    """Sanity re-check (not a substitute for the dedicated test files, which
    pytest already collects and runs independently): materializing through
    the new boundary must not change any previously-established semantic
    result for a representative duplicate + event-order + numeric fixture."""
    dup_a = _row("1700000000.000", size="2", price="1.1", trdid="dup-1")
    dup_b = _row("1700000000.000", size="2.00", price="1.10", trdid="dup-1")
    later = _row("1700000100.000", size="5", price="4.35", trdid="dup-later")
    for perm in itertools.permutations([later, dup_b, dup_a]):
        raw = _raw_bytes(list(perm))
        a = _materialize_parser_a_unadmitted(raw, date(2023, 11, 14), "x")
        b = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)
        assert a.record["open"] == b.record["open"] == "1.1"
        assert a.record["close"] == b.record["close"] == "4.35"
        assert a.record["first_source_trade_id"] == b.record["first_source_trade_id"] == "dup-1"
        assert a.record["last_source_trade_id"] == b.record["last_source_trade_id"] == "dup-later"
        assert a.record["first_source_timestamp_utc"] == b.record["first_source_timestamp_utc"] == "2023-11-14T22:13:20.000Z"
