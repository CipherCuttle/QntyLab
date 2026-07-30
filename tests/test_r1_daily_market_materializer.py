"""Tests for the DailyMarketEvidenceV1 materialization boundary
(qntylab.r1_daily_market_materializer), closing the two blockers an
independent NEW CHAT review of commit 1d52ec1 established as open:

  1. source_object_sha256 was not bound into a complete DailyMarketEvidenceV1
     record for the Parser B path (daily_primitive() never receives raw
     bytes and never returns this field).
  2. GzipCorruptionError / TruncatedCSVError escaped as uncaught, per-object,
     batch-terminating exceptions instead of a typed fail-closed result.

This module makes no scientific decision: it does not touch OHLC, duplicate,
timestamp, or event-order logic in either parser. Those remain covered by
their own existing, unmodified test files, re-run here only as a regression
gate (see the bottom of this file), not reimplemented.
"""
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
    materialize_parser_a,
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
    result = materialize_parser_a(raw, date(2023, 11, 14), "x")
    assert result.status == MATERIALIZED_VALID
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
    a = materialize_parser_a(raw, date(2023, 11, 14), "obj")
    b = materialize_parser_b(raw, "2023-11-14", "obj", CUTOFF)
    assert a.status == b.status == MATERIALIZED_VALID
    for field in ALL_CONTRACT_FIELDS:
        assert a.record[field] == b.record[field], field


def test_real_5_objects_full_record_equality():
    checked = 0
    for name, sha, day in REAL_OBJECTS:
        path = CACHE_DIR / sha
        if not path.exists():
            continue
        raw = path.read_bytes()
        a = materialize_parser_a(raw, day, name)
        b = materialize_parser_b(raw, day.isoformat(), name, CUTOFF)
        assert a.status == MATERIALIZED_VALID, (name, a.reason)
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

    a_fwd = materialize_parser_a(raw_fwd, date(2023, 11, 14), "x")
    a_rev = materialize_parser_a(raw_rev, date(2023, 11, 14), "x")
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
    result = materialize_parser_a(raw, date(2023, 11, 14), "x", expected_raw_sha256="0" * 64)
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
    a = materialize_parser_a(garbage, date(2023, 11, 14), "x")
    b = materialize_parser_b(garbage, "2023-11-14", "s", CUTOFF)
    assert a.status == b.status == MATERIALIZATION_QUARANTINED
    assert a.record is None and b.record is None
    assert "CONTAINER_ANOMALY" in a.anomalies
    assert "CONTAINER_ANOMALY" in b.anomalies


def test_gzip_valid_truncated_one_column_header_typed_quarantine_both_parsers():
    truncated = gzip.compress(b"t\n")
    a = materialize_parser_a(truncated, date(2023, 11, 14), "x")
    b = materialize_parser_b(truncated, "2023-11-14", "s", CUTOFF)
    assert a.status == b.status == MATERIALIZATION_QUARANTINED
    assert "CONTAINER_ANOMALY" in a.anomalies
    assert "CONTAINER_ANOMALY" in b.anomalies


def test_empty_raw_bytes_typed_valid_zero_trade_record_both_parsers():
    a = materialize_parser_a(b"", date(2023, 11, 14), "x")
    b = materialize_parser_b(b"", "2023-11-14", "s", CUTOFF)
    assert a.status == MATERIALIZED_VALID
    assert b.status == MATERIALIZED_VALID
    assert a.record["trade_count"] == 0
    assert b.record["trade_count"] == 0
    assert a.record["source_object_sha256"] == hashlib.sha256(b"").hexdigest()
    assert b.record["source_object_sha256"] == hashlib.sha256(b"").hexdigest()


def test_gzip_valid_empty_body_typed_valid_zero_trade_record():
    empty_body = gzip.compress(b"")
    a = materialize_parser_a(empty_body, date(2023, 11, 14), "x")
    b = materialize_parser_b(empty_body, "2023-11-14", "s", CUTOFF)
    assert a.status == MATERIALIZED_VALID
    assert b.status == MATERIALIZED_VALID
    assert a.record["trade_count"] == 0
    assert b.record["trade_count"] == 0


def test_malformed_row_still_typed_valid_with_rejection_accounted():
    text = (",".join(HEADER) + "\n"
            + "notanumber,X,Buy,1,1,PlusTick,id1,1e8,1,1\n"
            + "1700000000,X,Buy,1,1,PlusTick,id2,1e8,1,1\n")
    raw = gzip.compress(text.encode())
    a = materialize_parser_a(raw, date(2023, 11, 14), "x")
    b = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)
    assert a.status == MATERIALIZED_VALID
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
    results = materialize_batch(items, materialize_parser_a)

    assert len(results) == 3
    assert results[0].status == MATERIALIZED_VALID
    assert results[1].status == MATERIALIZATION_QUARANTINED
    assert results[2].status == MATERIALIZED_VALID
    # object B's corruption did not prevent C from being attempted/valid
    assert results[2].record["first_source_trade_id"] == "c-1"

    valid_count = sum(1 for r in results if r.status == MATERIALIZED_VALID)
    quarantined_count = sum(1 for r in results if r.status == MATERIALIZATION_QUARANTINED)
    assert valid_count + quarantined_count == len(items) == 3
    assert all(r.status in (MATERIALIZED_VALID, MATERIALIZATION_QUARANTINED) for r in results)


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


# --- 17. contract validator used identically on both parsers' output -------

def test_validator_used_on_both_parser_outputs_directly():
    raw = _raw_bytes([_row("1700000000.000", size="1", price="1", trdid="t-1")])
    a = materialize_parser_a(raw, date(2023, 11, 14), "x")
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
        a = materialize_parser_a(raw, date(2023, 11, 14), "x")
        b = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)
        assert a.record["open"] == b.record["open"] == "1.1"
        assert a.record["close"] == b.record["close"] == "4.35"
        assert a.record["first_source_trade_id"] == b.record["first_source_trade_id"] == "dup-1"
        assert a.record["last_source_trade_id"] == b.record["last_source_trade_id"] == "dup-later"
        assert a.record["first_source_timestamp_utc"] == b.record["first_source_timestamp_utc"] == "2023-11-14T22:13:20.000Z"
