from __future__ import annotations

import csv
import hashlib
import io
import zipfile
import json

import pytest

from qntylab.binance_um_funding_settlement import (
    HEADER,
    archive_paths,
    materialize,
    materialize_from_objects,
)
from qntylab.market_observation import InstrumentIdentity

SYMBOL = "BTCUSDT"


def _identity(symbol=SYMBOL, market="usd-m", contract_type="perpetual"):
    return InstrumentIdentity(symbol, market, contract_type, "fixture-instance")


def _ms(hour: int, millis: int = 0) -> int:
    return (1_704_067_200 + hour * 3_600 + millis // 1000) * 1000 + millis % 1000


def _zip(rows, *, member=None, header=HEADER, extra=False, compression=zipfile.ZIP_STORED):
    member = member or f"{SYMBOL}-fundingRate-2024-01.csv"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=compression) as archive:
        text = io.StringIO(newline="")
        writer = csv.writer(text, lineterminator="\n")
        if header is not None:
            writer.writerow(header)
        writer.writerows(rows)
        archive.writestr(member, text.getvalue())
        if extra:
            archive.writestr("extra.csv", "x\n")
    return stream.getvalue()


def _checksum(data, filename=None):
    filename = filename or archive_paths(SYMBOL, 2024, 1)["archive_filename"]
    return f"{hashlib.sha256(data).hexdigest()}  {filename}\n"


def _rows(*items):
    return [[str(_ms(hour, millis)), str(interval), rate] for hour, millis, interval, rate in items]


def _result(data, checksum=None, start="2024-01-01T00:00:00Z", end="2024-01-01T23:00:00Z"):
    witness = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            rows = list(csv.DictReader(io.TextIOWrapper(archive.open(archive.namelist()[0]), encoding="utf-8"))) if archive.namelist() else []
        for row in rows:
            if "calc_time" in row and "last_funding_rate" in row:
                witness.append({"symbol": SYMBOL, "fundingTime": int(row["calc_time"]), "fundingRate": row["last_funding_rate"]})
    except (zipfile.BadZipFile, KeyError, ValueError):
        pass
    return materialize_from_objects(SYMBOL, start, end, {(2024, 1): (data, _checksum(data) if checksum is None else checksum)}, _identity(), rest_witness_pages=[witness])


def test_valid_auth_exact_timestamp_decimal_and_jsonl_shape():
    data = _zip(_rows((0, 123, 8, "9.8E-7"), (8, 123, 8, "-0.00010000"), (16, 123, 8, "0")))
    result = _result(data)
    assert result["status"] == "MATERIALIZED_VERIFIED"
    assert result["manifest"]["normalized_event_count"] == 3
    assert '"funding_time_ms":1704067200123' in result["normalized_jsonl"]
    assert '"funding_rate":"0.00000098"' in result["normalized_jsonl"]
    assert '"funding_rate":"-0.0001"' in result["normalized_jsonl"]
    assert 'funding_interval_hours' not in result["normalized_jsonl"]


@pytest.mark.parametrize("checksum, status", [
    ("0" * 64 + "  BTCUSDT-fundingRate-2024-01.zip\n", "SOURCE_AUTHENTICATION_FAILED"),
    ("f" * 64 + "  wrong.zip\n", "SOURCE_AUTHENTICATION_FAILED"),
    ("not a checksum\n", "SOURCE_AUTHENTICATION_UNAVAILABLE"),
    (None, "SOURCE_AUTHENTICATION_UNAVAILABLE"),
])
def test_checksum_failures_block(checksum, status):
    data = _zip(_rows((0, 0, 8, "0")))
    objects = {(2024, 1): (data, checksum)}
    result = materialize_from_objects(SYMBOL, "2024-01-01T00:00:00Z", "2024-01-01T23:00:00Z", objects, _identity())
    assert result["status"] == "BLOCKED"
    assert result["receipts"][0]["status"] == status


@pytest.mark.parametrize("data, expected", [
    (b"bad zip", "ARCHIVE_INVALID"),
    (_zip(_rows((0, 0, 8, "0")), extra=True), "ARCHIVE_INVALID"),
    (_zip(_rows((0, 0, 8, "0")), member="wrong.csv"), "ARCHIVE_INVALID"),
    (_zip(_rows((0, 0, 8, "0")), header=("calc_time", "funding_interval_hours", "rate")), "SCHEMA_INVALID"),
    (_zip([["1", "8"]]), "SCHEMA_INVALID"),
])
def test_archive_and_schema_fail_closed(data, expected):
    assert _result(data)["receipts"][0]["status"] == expected


@pytest.mark.parametrize("rows", [
    _rows((0, 0, 8, "NaN")),
    _rows((0, 0, 0, "0")),
    _rows((0, 0, 8, "Infinity")),
    _rows((0, 0, 8, "0"), (0, 0, 8, "0")),
    _rows((8, 0, 8, "0"), (0, 0, 8, "0")),
])
def test_numeric_order_and_duplicate_failures(rows):
    assert _result(_zip(rows))["status"] == "BLOCKED"


@pytest.mark.parametrize("intervals", [(8, 8), (4, 4), (8, 4)])
def test_interval_sequences_and_declared_transition_pass(intervals):
    data = _zip(_rows((0, 0, intervals[0], "0"), (intervals[0], 0, intervals[1], "0")))
    assert _result(data)["status"] == "MATERIALIZED_VERIFIED"


def test_authentic_timestamp_jitter_is_complete_and_preserved():
    data = _zip(_rows((0, 0, 8, "0"), (12, 0, 8, "0")))
    result = _result(data)
    assert result["status"] == "MATERIALIZED_VERIFIED"
    assert result["manifest"]["coverage_status"] == "COMPLETE"


def test_rest_witness_outcomes_are_exact():
    data = _zip(_rows((0, 3, 8, "0.0001"), (8, 998, 8, "0.0002"), (16, 1, 8, "0.0003")))
    archive_rows = [{"symbol": SYMBOL, "fundingTime": _ms(h, m), "fundingRate": rate} for h, m, _, rate in [(0, 3, 8, "0.0001"), (8, 998, 8, "0.0002"), (16, 1, 8, "0.0003")]]
    base = {(2024, 1): (data, _checksum(data))}
    assert materialize_from_objects(SYMBOL, "2024-01-01T00:00:00Z", "2024-01-01T23:00:00Z", base, _identity(), rest_witness_pages=[archive_rows[:1], archive_rows[1:]])["status"] == "MATERIALIZED_VERIFIED"
    assert materialize_from_objects(SYMBOL, "2024-01-01T00:00:00Z", "2024-01-01T23:00:00Z", base, _identity(), rest_witness_pages=[[archive_rows[0], {"symbol": SYMBOL, "fundingTime": _ms(4), "fundingRate": "0"}, *archive_rows[1:]]])["manifest"]["coverage_status"] == "ARCHIVE_EVENT_MISSING"
    assert materialize_from_objects(SYMBOL, "2024-01-01T00:00:00Z", "2024-01-01T23:00:00Z", base, _identity(), rest_witness_pages=[[archive_rows[0], archive_rows[2]]])["manifest"]["coverage_status"] == "REST_WITNESS_MISSING_EVENT"
    mismatch = [dict(archive_rows[0], fundingRate="0.0009"), *archive_rows[1:]]
    assert materialize_from_objects(SYMBOL, "2024-01-01T00:00:00Z", "2024-01-01T23:00:00Z", base, _identity(), rest_witness_pages=[mismatch])["manifest"]["coverage_status"] == "FUNDING_RATE_DISAGREEMENT"


def test_rest_decimal_equivalence_boundary_duplicate_and_conflict_block():
    data = _zip(_rows((0, 0, 8, "9.8E-7"), (8, 0, 8, "0")))
    base = {(2024, 1): (data, _checksum(data))}
    x = {"symbol": SYMBOL, "fundingTime": _ms(0), "fundingRate": "9.8E-7"}
    y = {"symbol": SYMBOL, "fundingTime": _ms(8), "fundingRate": "0"}
    assert materialize_from_objects(SYMBOL, "2024-01-01T00:00:00Z", "2024-01-01T23:00:00Z", base, _identity(), rest_witness_pages=[[x], [x, y]])["status"] == "MATERIALIZED_VERIFIED"
    conflict = dict(x, fundingRate="0.1")
    result = materialize_from_objects(SYMBOL, "2024-01-01T00:00:00Z", "2024-01-01T23:00:00Z", base, _identity(), rest_witness_pages=[[x], [conflict, y]])
    assert result["manifest"]["coverage_status"] == "REST_WITNESS_INVALID"


def test_rest_unavailable_blocks_and_rest_cannot_change_causal_digest():
    data = _zip(_rows((0, 0, 8, "0.00010000")))
    base = {(2024, 1): (data, _checksum(data))}
    unavailable = materialize_from_objects(SYMBOL, "2024-01-01T00:00:00Z", "2024-01-01T23:00:00Z", base, _identity())
    assert unavailable["status"] == "BLOCKED"
    assert unavailable["manifest"]["coverage_status"] == "REST_COVERAGE_UNAVAILABLE"
    a = _result(data, start="2024-01-01T00:00:00Z", end="2024-01-01T00:00:00Z")
    witness = [{"symbol": SYMBOL, "fundingTime": _ms(0), "fundingRate": "0.0001", "markPrice": "1"}]
    b = materialize_from_objects(SYMBOL, "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z", base, _identity(), rest_witness_pages=[witness])
    assert a["normalized_jsonl"] == b["normalized_jsonl"]
    assert a["manifest"]["normalized_sha256"] == b["manifest"]["normalized_sha256"]
    assert a["manifest"]["rest_coverage_witness_digest"] != b["manifest"]["rest_coverage_witness_digest"]


def test_cross_month_merge_duplicate_and_missing_month():
    jan = _zip(_rows((0, 0, 8, "0"), (8, 0, 8, "0")))
    feb = _zip(_rows((16, 0, 8, "0"), (24, 0, 8, "0")), member="BTCUSDT-fundingRate-2024-02.csv")
    objects = {(2024, 1): (jan, _checksum(jan)), (2024, 2): (feb, _checksum(feb, "BTCUSDT-fundingRate-2024-02.zip"))}
    witness = [[{"symbol": SYMBOL, "fundingTime": _ms(h), "fundingRate": "0"} for h in (0, 8, 16, 24)]]
    result = materialize_from_objects(SYMBOL, "2024-01-01T00:00:00Z", "2024-02-01T08:00:00Z", objects, _identity(), rest_witness_pages=witness)
    assert result["status"] == "MATERIALIZED_VERIFIED"
    assert result["manifest"]["normalized_event_count"] == 4
    duplicate_feb = _zip(_rows((0, 0, 8, "0")), member="BTCUSDT-fundingRate-2024-02.csv")
    duplicate = materialize_from_objects(SYMBOL, "2024-01-01T00:00:00Z", "2024-02-01T00:00:00Z", {(2024, 1): (jan, _checksum(jan)), (2024, 2): (duplicate_feb, _checksum(duplicate_feb, "BTCUSDT-fundingRate-2024-02.zip"))}, _identity())
    assert duplicate["status"] == "BLOCKED"
    missing = materialize_from_objects(SYMBOL, "2024-01-01T00:00:00Z", "2024-02-01T00:00:00Z", {(2024, 1): (jan, _checksum(jan))}, _identity())
    assert missing["receipts"][1]["status"] == "SOURCE_OBJECT_ABSENT"


def test_determinism_and_archive_revision_separate_economics_from_provenance():
    first = _zip(_rows((0, 0, 8, "0.00010000")))
    second = _zip(_rows((0, 0, 8, "0.0001")), compression=zipfile.ZIP_DEFLATED)
    a, b = _result(first), _result(second)
    assert a["normalized_jsonl"] == b["normalized_jsonl"]
    assert a["manifest"]["normalized_sha256"] == b["manifest"]["normalized_sha256"]
    assert a["receipts"][0]["actual_raw_sha256"] != b["receipts"][0]["actual_raw_sha256"]
    assert a["receipts"][0]["receipt_digest"] != b["receipts"][0]["receipt_digest"]
    assert a["manifest"]["aggregate_source_receipt_digest"] != b["manifest"]["aggregate_source_receipt_digest"]


class _Response:
    def __init__(self, content, status_code=200):
        self.content, self.status_code = content, status_code

    @property
    def text(self):
        return self.content.decode()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError("unexpected HTTP failure")


class _Session:
    def __init__(self, data):
        self.data = data
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        if url.endswith(".CHECKSUM"):
            return _Response(_checksum(self.data).encode())
        if "fapi.binance.com" in url:
            with zipfile.ZipFile(io.BytesIO(self.data)) as archive:
                rows = list(csv.DictReader(io.TextIOWrapper(archive.open(archive.namelist()[0]), encoding="utf-8")))
            payload = [{"symbol": SYMBOL, "fundingTime": int(row["calc_time"]), "fundingRate": row["last_funding_rate"]} for row in rows]
            return _Response(json.dumps(payload).encode())
        return _Response(self.data)


def test_network_wrapper_requests_only_archive_and_checksum_and_writes_outputs(tmp_path):
    data = _zip(_rows((0, 0, 8, "0")))
    session = _Session(data)
    result = materialize(SYMBOL, "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z", tmp_path, _identity(), session)
    assert result["status"] == "MATERIALIZED_VERIFIED"
    assert any("fapi.binance.com/fapi/v1/fundingRate" in url for url in session.urls)
    assert (tmp_path / "data/raw/BTCUSDT-perp-funding-events.jsonl").exists()
    assert list((tmp_path / "data/archive/binance_um_funding_settlement").glob("*.CHECKSUM"))
