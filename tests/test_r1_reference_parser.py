import gzip
import hashlib
import inspect
from datetime import date

import pytest

from qntylab import r1_reference_parser as rp

CACHE_DIR = "/home/swirky/DevHub/repos/QntyLab/.r1_input_cache/sha256"

REAL_OBJECTS = {
    "BTCUSDT_2020-03-25": (f"{CACHE_DIR}/cbca6933a8f0a11429661cfa93b04056055d776ee199209e8af9719ad2060a33", date(2020, 3, 25)),
    "CHEEMS_2026-05-28_RPI": (f"{CACHE_DIR}/d1b50f8316c1874d7ae7bde11314d077f3cf1b2baece4a6cdd7459e83cc2ce2a", date(2026, 5, 28)),
}


def _gz(text: str) -> bytes:
    return gzip.compress(text.encode("utf-8"))


BASE_HEADER = "timestamp,symbol,side,size,price,tickDirection,trdMatchID,grossValue,homeNotional,foreignNotional"


def _row(ts, size, price, trade_id, side="Buy", tick="PlusTick"):
    gross = float(size) * float(price) * 1e8
    return f"{ts},TESTUSDT,{side},{size},{price},{tick},{trade_id},{gross},{size},{float(size) * float(price)}"


def test_reference_parser_does_not_import_production_semantic_parser():
    import ast

    src = inspect.getsource(rp)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "r1_retention_candidate" not in alias.name
        if isinstance(node, ast.ImportFrom):
            assert node.module is None or "r1_retention_candidate" not in node.module
        if isinstance(node, ast.Name):
            assert node.id != "daily_primitive"
        if isinstance(node, ast.Attribute):
            assert node.attr != "daily_primitive"
    assert "r1_reference_parser" in rp.__name__


def test_known_old_schema_real_object():
    path, day = REAL_OBJECTS["BTCUSDT_2020-03-25"]
    raw = open(path, "rb").read()
    result = rp.parse_daily_object(raw, day, "bybit_linear|BTCUSDT|perp|test")
    assert result.status == rp.STATUS_OK
    assert result.schema_id == "bybit_trade_v1"
    assert result.record["trade_count"] > 0
    assert result.record["close"] is not None


def test_known_rpi_schema_real_object():
    path, day = REAL_OBJECTS["CHEEMS_2026-05-28_RPI"]
    raw = open(path, "rb").read()
    result = rp.parse_daily_object(raw, day, "bybit_linear|1000000CHEEMSUSDT|perp|test")
    assert result.status == rp.STATUS_OK
    assert result.schema_id == "bybit_trade_v1_rpi"
    assert result.diagnostics["rpi_observed_values"] is not None
    # RPI must never influence OHLC/turnover -- record shape is identical to non-RPI schema
    assert set(result.record.keys()) == {
        "instrument_instance_id", "utc_date", "open", "high", "low", "close",
        "base_volume", "quote_turnover", "trade_count",
        "first_source_timestamp_utc", "last_source_timestamp_utc",
        "first_source_trade_id", "last_source_trade_id",
        "duplicate_count", "rejected_row_count", "schema_id", "source_object_sha256",
    }


def test_unknown_schema_quarantine():
    text = "foo,bar,baz\n1,2,3\n"
    result = rp.parse_daily_object(_gz(text), date(2024, 1, 1), "x")
    assert result.status == rp.STATUS_UNKNOWN_SCHEMA_QUARANTINE
    assert result.record is None
    assert result.rejected_row_count == 1


def test_duplicate_semantics_exact_collapse():
    text = BASE_HEADER + "\n" + _row("1700000000.100", 1, 100, "id-a") + "\n" + _row("1700000000.100", 1, 100, "id-a") + "\n"
    result = rp.parse_daily_object(_gz(text), date(2023, 11, 14), "x")
    assert result.record["trade_count"] == 1
    assert result.record["duplicate_count"] == 1
    assert result.record["rejected_row_count"] == 0


def test_conflicting_duplicate_semantics():
    text = BASE_HEADER + "\n" + _row("1700000000.100", 1, 100, "id-a") + "\n" + _row("1700000000.200", 2, 105, "id-a") + "\n"
    result = rp.parse_daily_object(_gz(text), date(2023, 11, 14), "x")
    assert result.record["trade_count"] == 0
    assert result.record["rejected_row_count"] == 2
    assert "id-a" in result.diagnostics["conflicting_duplicate_trade_ids"]


def test_event_ordering_out_of_order_rows():
    rows = [
        _row("1700000010.000", 1, 103, "id-3"),
        _row("1700000000.000", 1, 100, "id-1"),
        _row("1700000005.000", 1, 101, "id-2"),
    ]
    text = BASE_HEADER + "\n" + "\n".join(rows) + "\n"
    result = rp.parse_daily_object(_gz(text), date(2023, 11, 14), "x")
    assert result.record["open"] == "100"
    assert result.record["close"] == "103"
    assert result.record["first_source_trade_id"] == "id-1"
    assert result.record["last_source_trade_id"] == "id-3"


def test_same_timestamp_tie_behavior_deterministic():
    rows = [
        _row("1700000000.000", 1, 100, "id-zzz"),
        _row("1700000000.000", 1, 200, "id-aaa"),
    ]
    text = BASE_HEADER + "\n" + "\n".join(rows) + "\n"
    result = rp.parse_daily_object(_gz(text), date(2023, 11, 14), "x")
    # tie-break is trade identity, lexicographic ascending -> id-aaa first, id-zzz last
    assert result.record["first_source_trade_id"] == "id-aaa"
    assert result.record["last_source_trade_id"] == "id-zzz"
    assert result.record["close"] == "100"


def test_utc_boundary_end_of_day():
    text = BASE_HEADER + "\n" + _row("1700006399.999999", 1, 100, "id-1") + "\n"
    result = rp.parse_daily_object(_gz(text), date(2023, 11, 14), "x")
    assert result.record["trade_count"] == 1


def test_utc_boundary_start_of_day():
    text = BASE_HEADER + "\n" + _row("1700006400.000000", 1, 100, "id-1") + "\n"
    result = rp.parse_daily_object(_gz(text), date(2023, 11, 15), "x")
    assert result.record["trade_count"] == 1


def test_decimal_precision_preserved():
    text = BASE_HEADER + "\n" + _row("1700000000.000", "0.123456789012345", "6698.123456789", "id-1") + "\n"
    result = rp.parse_daily_object(_gz(text), date(2023, 11, 14), "x")
    assert result.record["close"] == "6698.123456789"
    assert result.record["base_volume"] == "0.123456789012345"


def test_empty_input():
    result = rp.parse_daily_object(b"", date(2023, 11, 14), "x")
    assert result.status == rp.STATUS_EMPTY_OBJECT
    assert result.record["trade_count"] == 0


def test_single_trade_day():
    text = BASE_HEADER + "\n" + _row("1700000000.000", 1, 100, "id-1") + "\n"
    result = rp.parse_daily_object(_gz(text), date(2023, 11, 14), "x")
    assert result.record["trade_count"] == 1
    assert result.record["open"] == result.record["close"] == "100"


def test_malformed_timestamp_rejected():
    text = BASE_HEADER + "\n" + _row("not-a-number", 1, 100, "id-1") + "\n" + _row("1700000000.000", 1, 100, "id-2") + "\n"
    result = rp.parse_daily_object(_gz(text), date(2023, 11, 14), "x")
    assert result.record["trade_count"] == 1
    assert result.record["rejected_row_count"] == 1


def test_missing_required_column_value_rejected():
    text = BASE_HEADER + "\n1700000000.000,TESTUSDT,Buy,1,100,PlusTick,,1e8,1,100\n"
    result = rp.parse_daily_object(_gz(text), date(2023, 11, 14), "x")
    assert result.record["trade_count"] == 0
    assert result.record["rejected_row_count"] == 1


def test_future_cutoff_violation_rejected():
    text = BASE_HEADER + "\n" + _row("1782864000.000", 1, 100, "id-future") + "\n"  # 2026-07-01, past cutoff
    result = rp.parse_daily_object(_gz(text), date(2026, 7, 1), "x")
    assert result.record["rejected_row_count"] == 1
    assert result.record["trade_count"] == 0


def test_reordered_columns_still_identified():
    header = "symbol,timestamp,price,size,side,tickDirection,trdMatchID,grossValue,homeNotional,foreignNotional"
    row = "TESTUSDT,1700000000.000,100,1,Buy,PlusTick,id-1,1e8,1,100"
    result = rp.parse_daily_object(_gz(header + "\n" + row + "\n"), date(2023, 11, 14), "x")
    assert result.schema_id == "bybit_trade_v1"
    assert result.record["trade_count"] == 1


def test_truncated_csv_missing_header_raises():
    with pytest.raises(rp.TruncatedCSVError):
        rp.parse_daily_object(_gz("t"), date(2023, 11, 14), "x")


def test_truncated_tail_row_diagnostic_flagged():
    text = BASE_HEADER + "\n" + _row("1700000000.000", 1, 100, "id-1") + "\n" + "1700000001.000,TESTUSDT,Buy,1"
    result = rp.parse_daily_object(_gz(text), date(2023, 11, 14), "x")
    assert result.diagnostics["truncated_tail_detected"] is True
    assert result.record["trade_count"] == 1


def test_gzip_corruption_raises():
    with pytest.raises(rp.GzipCorruptionError):
        rp.parse_daily_object(b"not-actually-gzip-bytes", date(2023, 11, 14), "x")


def test_deterministic_rerun_same_bytes():
    text = BASE_HEADER + "\n" + _row("1700000010.000", 1, 103, "id-3") + "\n" + _row("1700000000.000", 1, 100, "id-1") + "\n"
    raw = _gz(text)
    r1 = rp.parse_daily_object(raw, date(2023, 11, 14), "x")
    r2 = rp.parse_daily_object(raw, date(2023, 11, 14), "x")
    assert rp.canonical_bytes(r1.record) == rp.canonical_bytes(r2.record)


def test_deterministic_regardless_of_row_order():
    rows_a = [_row("1700000010.000", 1, 103, "id-3"), _row("1700000000.000", 1, 100, "id-1")]
    rows_b = list(reversed(rows_a))
    ra = rp.parse_daily_object(_gz(BASE_HEADER + "\n" + "\n".join(rows_a) + "\n"), date(2023, 11, 14), "x")
    rb = rp.parse_daily_object(_gz(BASE_HEADER + "\n" + "\n".join(rows_b) + "\n"), date(2023, 11, 14), "x")
    ra_record = {k: v for k, v in ra.record.items() if k != "source_object_sha256"}
    rb_record = {k: v for k, v in rb.record.items() if k != "source_object_sha256"}
    assert rp.canonical_bytes(ra_record) == rp.canonical_bytes(rb_record)


def test_source_mutation_detected_and_original_not_overwritten():
    result = rp.check_source_mutation("https://example.invalid/obj.csv.gz", "AAA", "BBB")
    assert result["status"] == rp.SOURCE_MUTATION
    assert result["recorded_sha256"] == "AAA"  # never overwritten with the new value


def test_source_unchanged_when_sha_matches():
    result = rp.check_source_mutation("https://example.invalid/obj.csv.gz", "AAA", "AAA")
    assert result["status"] == rp.SOURCE_UNCHANGED


def test_source_object_sha256_matches_raw_bytes():
    text = BASE_HEADER + "\n" + _row("1700000000.000", 1, 100, "id-1") + "\n"
    raw = _gz(text)
    result = rp.parse_daily_object(raw, date(2023, 11, 14), "x")
    assert result.record["source_object_sha256"] == hashlib.sha256(raw).hexdigest()
