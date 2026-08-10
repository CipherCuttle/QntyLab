from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from datetime import UTC, datetime

import pytest

from qntylab.binance_um_kline_1h import (
    FIELDS, MaterializationError, archive_paths, materialize_from_objects, months, receipt_from_bytes,
)
from qntylab.market_observation import InstrumentIdentity

SYMBOL = "BTCUSDT"
HEADER = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


def _identity(symbol=SYMBOL, market="usd-m", contract_type="perpetual"):
    return InstrumentIdentity(symbol, market, contract_type, "fixture-instance")


def _rows(*hours: int):
    return [[str(int(datetime(2024, 1, 1, hour, tzinfo=UTC).timestamp() * 1000)), "1", "2", "1", "1.5", "3", "0", "0", "0", "0", "0", "0"] for hour in hours]


def _zip(rows, *, header=False, members=1, filename=None):
    filename = filename or archive_paths(SYMBOL, 2024, 1)["archive_filename"]
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        for n in range(members):
            text = io.StringIO(); writer = csv.writer(text)
            if header: writer.writerow(HEADER if header is True else header)
            writer.writerows(rows)
            z.writestr(f"{filename.removesuffix('.zip')}{n}.csv", text.getvalue())
    return stream.getvalue()


def _check(data, filename=None):
    filename = filename or archive_paths(SYMBOL, 2024, 1)["archive_filename"]
    return f"{hashlib.sha256(data).hexdigest()}  {filename}\n"


def _result(objects, start="2024-01-01T00:00:00Z", end="2024-01-01T02:00:00Z", identity=None):
    return materialize_from_objects(SYMBOL, start, end, objects, _identity() if identity is None else identity)


def test_a1_valid_archive_checksum_and_six_field_normalization():
    data = _zip(_rows(0, 1, 2), header=True)
    result = _result({(2024, 1): (data, _check(data))})
    assert result["status"] == "MATERIALIZED_VERIFIED"
    assert result["normalized_csv"].splitlines()[0] == ",".join(FIELDS)
    assert result["manifest"]["normalized_row_count"] == 3


@pytest.mark.parametrize("checksum", ["f" * 64 + "  BTCUSDT-1h-2024-01.zip\n", "0" * 64 + "  wrong.zip\n"])
def test_a2_a3_bad_checksum_is_never_admitted(checksum):
    data = _zip(_rows(0))
    result = _result({(2024, 1): (data, checksum)})
    assert result["status"] == "BLOCKED"
    assert result["receipts"][0]["status"] == "SOURCE_AUTHENTICATION_FAILED"


def test_a4_checksum_missing_a5_absence_and_a18_no_lifecycle_claim():
    data = _zip(_rows(0))
    missing_checksum = _result({(2024, 1): (data, None)})
    absent = _result({})
    assert missing_checksum["receipts"][0]["status"] == "SOURCE_AUTHENTICATION_UNAVAILABLE"
    assert absent["receipts"][0]["status"] == "SOURCE_OBJECT_ABSENT"
    assert "TRADABLE" not in str(absent)


@pytest.mark.parametrize("data", [b"not a zip", _zip(_rows(0), members=2)])
def test_a6_a7_bad_archive_layout_blocked(data):
    result = _result({(2024, 1): (data, _check(data))})
    assert result["status"] == "BLOCKED"
    assert result["receipts"][0]["status"] in {"ARCHIVE_INVALID", "SCHEMA_INVALID"}


def test_a8_a9_malformed_row_fails_closed_and_only_exact_first_header_is_allowed():
    bad = _zip([_rows(0)[0][:-1]])
    assert _result({(2024, 1): (bad, _check(bad))})["status"] == "BLOCKED"
    header_middle = _zip([_rows(0)[0], HEADER])
    assert _result({(2024, 1): (header_middle, _check(header_middle))})["status"] == "BLOCKED"


def test_h1_h2_exact_observed_header_only_allowed_at_first_row():
    accepted = _zip(_rows(0), header=True)
    assert _result({(2024, 1): (accepted, _check(accepted))})["status"] == "MATERIALIZED_VERIFIED"
    rejected = _zip([_rows(0)[0], HEADER])
    assert _result({(2024, 1): (rejected, _check(rejected))})["status"] == "BLOCKED"


@pytest.mark.parametrize("header", [
    [*HEADER[:7], "quote_asset_volume", *HEADER[8:]],  # spelling mutation
    [HEADER[1], HEADER[0], *HEADER[2:]],                 # reordered
    HEADER[:-1],                                         # 11 fields
    [*HEADER, "extra"],                                 # 13 fields
    ["nonnumeric"] * 12,                                # arbitrary row
])
def test_h3_to_h7_near_or_unknown_headers_are_rejected(header):
    data = _zip(_rows(0), header=header)
    assert _result({(2024, 1): (data, _check(data))})["status"] == "BLOCKED"


def test_h8_to_h10_header_does_not_weaken_data_validation_or_output():
    malformed = _zip([_rows(0)[0][:-1]], header=True)
    assert _result({(2024, 1): (malformed, _check(malformed))})["status"] == "BLOCKED"
    headered, bare = _zip(_rows(0, 1), header=True), _zip(_rows(0, 1))
    a = _result({(2024, 1): (headered, _check(headered))})
    b = _result({(2024, 1): (bare, _check(bare))})
    assert a["normalized_csv"] == b["normalized_csv"]
    assert "open_time" not in a["normalized_csv"]


def test_a10_conflicting_duplicate_timestamp_fails_closed():
    rows = _rows(0) + [[*_rows(0)[0][:4], "1.6", *_rows(0)[0][5:]]]
    data = _zip(rows)
    assert _result({(2024, 1): (data, _check(data))})["status"] == "BLOCKED"


def test_a11_gap_is_preserved_and_reported_not_filled():
    data = _zip(_rows(0, 2))
    result = _result({(2024, 1): (data, _check(data))})
    assert result["manifest"]["gap_count"] == 1
    assert result["normalized_csv"].count("\n") == 3


def test_a12_a13_clip_is_inclusive_at_both_edges():
    data = _zip(_rows(0, 1, 2))
    result = _result({(2024, 1): (data, _check(data))}, "2024-01-01T01:00:00Z", "2024-01-01T01:00:00Z")
    assert result["normalized_csv"].splitlines()[1].startswith("2024-01-01T01:00:00Z,")
    assert result["manifest"]["normalized_row_count"] == 1


def test_a14_terminal_month_included_and_month_edges_are_exact():
    assert months("2024-01-31T23:00:00Z", "2024-02-01T00:00:00Z") == [(2024, 1), (2024, 2)]
    assert months("2024-02-29T23:00:00Z", "2024-02-29T23:00:00Z") == [(2024, 2)]
    assert months("2026-06-30T23:00:00Z", "2026-06-30T23:00:00Z") == [(2026, 6)]


def test_a15_future_bars_excluded_and_a16_a17_identity_mismatch_rejected():
    data = _zip(_rows(0, 1, 2))
    result = _result({(2024, 1): (data, _check(data))}, end="2024-01-01T01:00:00Z")
    assert "T02:00:00Z" not in result["normalized_csv"]
    for identity in (_identity("ETHUSDT"), _identity(market="spot"), _identity(contract_type="delivery")):
        invalid = _result({(2024, 1): (data, _check(data))}, identity=identity)
        assert invalid["status"] == "BLOCKED"
        assert invalid["receipts"][0]["status"] == "IDENTITY_MISMATCH"


def test_a20_source_bytes_change_manifest_receipt_digest():
    first = _zip(_rows(0))
    second = _zip(_rows(0), header=True)
    a = _result({(2024, 1): (first, _check(first))})
    b = _result({(2024, 1): (second, _check(second))})
    assert a["manifest"]["aggregate_source_receipt_digest"] != b["manifest"]["aggregate_source_receipt_digest"]


def test_receipt_carries_required_provenance_fields():
    data = _zip(_rows(0)); receipt, _ = receipt_from_bytes(SYMBOL, 2024, 1, data, _check(data), _identity())
    assert {"source_key", "zip_url", "checksum_url", "published_sha256", "actual_raw_sha256", "archive_member_name", "raw_row_count", "admitted_bar_count", "schema_version"} <= set(receipt)
