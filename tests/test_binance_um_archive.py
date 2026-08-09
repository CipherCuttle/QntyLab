"""Offline unit tests for the minimal Binance USDⓈ-M archive adapter.

Small artificial ZIP/checksum fixtures only -- no network. Reuses
``observed_at`` from the frozen MarketObservation fixture rather than
recreating its hostile suite.
"""
from __future__ import annotations

import csv
import hashlib
import io
import zipfile

import pytest

from qntylab.binance_um_archive import (
    archive_paths,
    capture_from_bytes,
    fetch_capture,
)
from qntylab.market_observation import (
    INVALID,
    OBSERVED,
    UNKNOWN,
    InstrumentIdentity,
    observed_at,
)


def _zip_bytes(filename: str, rows: list[list[str]], *, header: list[str] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        if header is not None:
            writer.writerow(header)
        for row in rows:
            writer.writerow(row)
        archive.writestr(filename, csv_buffer.getvalue())
    return buffer.getvalue()


# id, price, qty, quote_qty, time(ms), is_buyer_maker
GOOD_ROWS = [
    ["1", "8000.00", "0.001", "8.0", "1567900800001", "True"],
    ["2", "8000.50", "0.002", "16.0", "1567900800900", "False"],  # same second as row 1
    ["3", "8001.00", "0.001", "8.0", "1567900861000", "True"],    # different second
]
SYMBOL = "BTCUSDT"
DATE = "2019-09-08"
STABLE_INSTANCE_ID = "binance|btcusdt|perpetual|usd-m|synthetic-test-anchor"


def _identity(symbol: str = SYMBOL, instance_id: str = STABLE_INSTANCE_ID) -> InstrumentIdentity:
    return InstrumentIdentity(
        symbol=symbol, market="usd-m", contract_type="perpetual", instrument_instance_id=instance_id,
    )


def _checksum_for(zip_bytes: bytes, filename: str) -> str:
    return f"{hashlib.sha256(zip_bytes).hexdigest()}  {filename}\n"


def _good_zip_and_checksum(symbol: str = SYMBOL, date: str = DATE):
    filename = archive_paths(symbol, date)["filename"]
    csv_filename = filename.removesuffix(".zip") + ".csv"
    zip_bytes = _zip_bytes(csv_filename, GOOD_ROWS)
    checksum_text = _checksum_for(zip_bytes, filename)
    return zip_bytes, checksum_text


# --- archive_paths: deterministic path construction -------------------------

def test_archive_paths_deterministic_and_official():
    paths = archive_paths(SYMBOL, DATE)
    assert paths["zip_url"] == "https://data.binance.vision/data/futures/um/daily/trades/BTCUSDT/BTCUSDT-trades-2019-09-08.zip"
    assert paths["checksum_url"] == paths["zip_url"] + ".CHECKSUM"
    assert paths["source_key"] == "data/futures/um/daily/trades/BTCUSDT/BTCUSDT-trades-2019-09-08.zip"


def test_source_key_differs_by_symbol_and_date():
    a = archive_paths("BTCUSDT", "2019-09-08")["source_key"]
    b = archive_paths("ETCUSDT", "2019-09-08")["source_key"]
    c = archive_paths("BTCUSDT", "2019-09-09")["source_key"]
    assert len({a, b, c}) == 3


# --- F4: symbol validated before path construction ---------------------------

@pytest.mark.parametrize(
    "bad_symbol",
    ["", " ", "BTC USDT", "../../etc/passwd", "BTCUSDT/../../SPOT", "btcusdt", "BTC/USDT", "BTC-USDT"],
)
def test_archive_paths_rejects_unsafe_or_noncanonical_symbol(bad_symbol):
    with pytest.raises(ValueError):
        archive_paths(bad_symbol, DATE)


def test_valid_symbol_produces_deterministic_usd_m_path():
    paths = archive_paths("BTCUSDT", DATE)
    assert paths["zip_url"].startswith("https://data.binance.vision/data/futures/um/daily/trades/BTCUSDT/")


def test_invalid_symbol_never_reaches_capture_from_bytes():
    zip_bytes, checksum_text = _good_zip_and_checksum()
    identity = _identity(symbol="../../etc/passwd")
    with pytest.raises(ValueError):
        capture_from_bytes("../../etc/passwd", DATE, zip_bytes, checksum_text, identity)


def test_invalid_symbol_never_reaches_fetch_capture():
    identity = _identity(symbol="BTCUSDT/../../SPOT")
    with pytest.raises(ValueError):
        fetch_capture("BTCUSDT/../../SPOT", DATE, identity, session=_FakeSessionAlways404())


# --- F1: identity is caller-supplied and stable across captures -------------

def test_stable_identity_preserved_across_different_daily_captures():
    identity = _identity()

    zip_bytes_d1, checksum_d1 = _good_zip_and_checksum(date="2019-09-08")
    capture_d1 = capture_from_bytes(SYMBOL, "2019-09-08", zip_bytes_d1, checksum_d1, identity)

    later_rows = [
        ["10", "8100.00", "0.001", "8.1", "1568073600001", "True"],
        ["11", "8101.00", "0.002", "16.2", "1568073661000", "False"],
    ]
    filename_d2 = archive_paths(SYMBOL, "2019-09-10")["filename"]
    csv_filename_d2 = filename_d2.removesuffix(".zip") + ".csv"
    zip_bytes_d2 = _zip_bytes(csv_filename_d2, later_rows)
    checksum_d2 = _checksum_for(zip_bytes_d2, filename_d2)
    capture_d2 = capture_from_bytes(SYMBOL, "2019-09-10", zip_bytes_d2, checksum_d2, identity)

    assert capture_d1.identity.instrument_instance_id == STABLE_INSTANCE_ID
    assert capture_d2.identity.instrument_instance_id == STABLE_INSTANCE_ID
    assert capture_d1.source_key != capture_d2.source_key


def test_identity_symbol_mismatch_rejected():
    zip_bytes, checksum_text = _good_zip_and_checksum()
    wrong_identity = _identity(symbol="ETHUSDT")
    with pytest.raises(ValueError):
        capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, wrong_identity)


def test_identity_market_mismatch_rejected():
    zip_bytes, checksum_text = _good_zip_and_checksum()
    spot_identity = InstrumentIdentity(
        symbol=SYMBOL, market="spot", contract_type="perpetual", instrument_instance_id=STABLE_INSTANCE_ID,
    )
    with pytest.raises(ValueError):
        capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, spot_identity)


def test_identity_contract_type_mismatch_rejected():
    zip_bytes, checksum_text = _good_zip_and_checksum()
    delivery_identity = InstrumentIdentity(
        symbol=SYMBOL, market="usd-m", contract_type="delivery", instrument_instance_id=STABLE_INSTANCE_ID,
    )
    with pytest.raises(ValueError):
        capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, delivery_identity)


# --- checksum verification (F3) ----------------------------------------------

def test_checksum_match_accepted():
    zip_bytes, checksum_text = _good_zip_and_checksum()
    capture = capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, _identity())
    assert capture.valid
    assert capture.local_content_sha256 == hashlib.sha256(zip_bytes).hexdigest()


def test_checksum_mismatch_rejected():
    zip_bytes, _ = _good_zip_and_checksum()
    filename = archive_paths(SYMBOL, DATE)["filename"]
    bad_checksum = "f" * 64 + f"  {filename}\n"
    with pytest.raises(ValueError, match="checksum mismatch"):
        capture_from_bytes(SYMBOL, DATE, zip_bytes, bad_checksum, _identity())


def test_wrong_checksum_filename_correct_digest_rejected():
    zip_bytes, _ = _good_zip_and_checksum()
    digest = hashlib.sha256(zip_bytes).hexdigest()
    wrong_filename_checksum = f"{digest}  BTCUSDT-trades-2019-09-09.zip\n"
    with pytest.raises(ValueError, match="checksum filename mismatch"):
        capture_from_bytes(SYMBOL, DATE, zip_bytes, wrong_filename_checksum, _identity())


def test_correct_filename_wrong_digest_rejected():
    zip_bytes, _ = _good_zip_and_checksum()
    filename = archive_paths(SYMBOL, DATE)["filename"]
    wrong_digest_checksum = "0" * 64 + f"  {filename}\n"
    with pytest.raises(ValueError, match="checksum mismatch"):
        capture_from_bytes(SYMBOL, DATE, zip_bytes, wrong_digest_checksum, _identity())


def test_empty_checksum_rejected():
    zip_bytes, _ = _good_zip_and_checksum()
    with pytest.raises(ValueError, match="malformed published checksum"):
        capture_from_bytes(SYMBOL, DATE, zip_bytes, "", _identity())


def test_malformed_checksum_extra_fields_rejected():
    zip_bytes, _ = _good_zip_and_checksum()
    filename = archive_paths(SYMBOL, DATE)["filename"]
    digest = hashlib.sha256(zip_bytes).hexdigest()
    with pytest.raises(ValueError, match="malformed published checksum"):
        capture_from_bytes(SYMBOL, DATE, zip_bytes, f"{digest}  {filename}  extra\n", _identity())


def test_malformed_checksum_non_hex_digest_rejected():
    zip_bytes, _ = _good_zip_and_checksum()
    filename = archive_paths(SYMBOL, DATE)["filename"]
    with pytest.raises(ValueError, match="malformed checksum digest"):
        capture_from_bytes(SYMBOL, DATE, zip_bytes, f"not-a-digest  {filename}\n", _identity())


# --- malformed archive structure ---------------------------------------------

def test_malformed_zip_rejected():
    garbage = b"not a zip file at all"
    filename = archive_paths(SYMBOL, DATE)["filename"]
    checksum_text = _checksum_for(garbage, filename)
    with pytest.raises(ValueError, match="unreadable ZIP"):
        capture_from_bytes(SYMBOL, DATE, garbage, checksum_text, _identity())


def test_unexpected_archive_member_count_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a.csv", "1,1,1,1,1567900800001,True\n")
        archive.writestr("b.csv", "2,1,1,1,1567900800002,True\n")
    zip_bytes = buffer.getvalue()
    filename = archive_paths(SYMBOL, DATE)["filename"]
    checksum_text = _checksum_for(zip_bytes, filename)
    with pytest.raises(ValueError, match="unexpected archive members"):
        capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, _identity())


def test_malformed_row_column_count_rejected():
    filename = archive_paths(SYMBOL, DATE)["filename"]
    csv_filename = filename.removesuffix(".zip") + ".csv"
    zip_bytes = _zip_bytes(csv_filename, [["1", "8000.00", "0.001", "1567900800001", "True"]])  # 5 columns, missing quote_qty
    checksum_text = _checksum_for(zip_bytes, filename)
    with pytest.raises(ValueError, match="malformed trade row"):
        capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, _identity())


def test_malformed_timestamp_field_rejected():
    filename = archive_paths(SYMBOL, DATE)["filename"]
    csv_filename = filename.removesuffix(".zip") + ".csv"
    zip_bytes = _zip_bytes(csv_filename, [["1", "8000.00", "0.001", "8.0", "not-a-timestamp", "True"]])
    checksum_text = _checksum_for(zip_bytes, filename)
    with pytest.raises(ValueError, match="malformed trade timestamp"):
        capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, _identity())


def test_no_usable_rows_rejected():
    filename = archive_paths(SYMBOL, DATE)["filename"]
    csv_filename = filename.removesuffix(".zip") + ".csv"
    zip_bytes = _zip_bytes(csv_filename, [], header=["id", "price", "qty", "quote_qty", "time", "is_buyer_maker"])
    checksum_text = _checksum_for(zip_bytes, filename)
    with pytest.raises(ValueError, match="no usable trade rows"):
        capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, _identity())


def test_header_row_is_skipped_not_treated_as_a_trade():
    filename = archive_paths(SYMBOL, DATE)["filename"]
    csv_filename = filename.removesuffix(".zip") + ".csv"
    zip_bytes = _zip_bytes(
        csv_filename, GOOD_ROWS, header=["id", "price", "qty", "quote_qty", "time", "is_buyer_maker"],
    )
    checksum_text = _checksum_for(zip_bytes, filename)
    capture = capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, _identity())
    assert len(capture.observations) == 2  # two distinct seconds among GOOD_ROWS


# --- F2: malformed rows fail closed, never silently skipped ------------------

def test_corrupted_mid_file_row_rejected_no_capture():
    filename = archive_paths(SYMBOL, DATE)["filename"]
    csv_filename = filename.removesuffix(".zip") + ".csv"
    rows = [GOOD_ROWS[0], ["not-numeric-id", "corrupted", "row", "here", "also-bad", "??"], GOOD_ROWS[1]]
    zip_bytes = _zip_bytes(csv_filename, rows)
    checksum_text = _checksum_for(zip_bytes, filename)
    with pytest.raises(ValueError):
        capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, _identity())


def test_corrupted_last_row_rejected():
    filename = archive_paths(SYMBOL, DATE)["filename"]
    csv_filename = filename.removesuffix(".zip") + ".csv"
    rows = [GOOD_ROWS[0], GOOD_ROWS[1], ["not-numeric-id", "corrupted", "row", "here", "also-bad", "??"]]
    zip_bytes = _zip_bytes(csv_filename, rows)
    checksum_text = _checksum_for(zip_bytes, filename)
    with pytest.raises(ValueError):
        capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, _identity())


def test_header_like_middle_row_after_legitimate_first_header_rejected():
    filename = archive_paths(SYMBOL, DATE)["filename"]
    csv_filename = filename.removesuffix(".zip") + ".csv"
    header = ["id", "price", "qty", "quote_qty", "time", "is_buyer_maker"]
    rows = [GOOD_ROWS[0], header, GOOD_ROWS[1]]  # header-like row NOT in position 0 -> malformed
    zip_bytes = _zip_bytes(csv_filename, rows, header=header)
    checksum_text = _checksum_for(zip_bytes, filename)
    with pytest.raises(ValueError):
        capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, _identity())


def test_legitimate_first_header_still_accepted():
    filename = archive_paths(SYMBOL, DATE)["filename"]
    csv_filename = filename.removesuffix(".zip") + ".csv"
    header = ["id", "price", "qty", "quote_qty", "time", "is_buyer_maker"]
    zip_bytes = _zip_bytes(csv_filename, GOOD_ROWS, header=header)
    checksum_text = _checksum_for(zip_bytes, filename)
    capture = capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, _identity())
    assert len(capture.observations) == 2


# --- valid parse -> MarketObservation / Capture ------------------------------

def test_valid_rows_build_deduplicated_observations():
    zip_bytes, checksum_text = _good_zip_and_checksum()
    capture = capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, _identity())
    # rows 1 and 2 share a second -> one observation; row 3 is a distinct second.
    assert len(capture.observations) == 2
    timestamps = {observation.timestamp for observation in capture.observations}
    assert timestamps == {"2019-09-08T00:00:00Z", "2019-09-08T00:01:01Z"}


def test_capture_provenance_propagated_to_every_observation():
    zip_bytes, checksum_text = _good_zip_and_checksum()
    capture = capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, _identity())
    for observation in capture.observations:
        assert observation.source_key == capture.source_key
        assert observation.local_content_sha256 == capture.local_content_sha256
        assert observation.identity == capture.identity


def test_witness_timestamp_observed_and_non_witness_not_observed():
    zip_bytes, checksum_text = _good_zip_and_checksum()
    capture = capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, _identity())
    identity = capture.identity
    assert observed_at(capture, identity, "2019-09-08T00:00:00Z") == OBSERVED
    assert observed_at(capture, identity, "2019-09-08T09:00:00Z") == "NOT_OBSERVED_IN_CAPTURE"


# --- wrong market / path identity --------------------------------------------

def test_wrong_market_identity_never_matches_usd_m_capture():
    zip_bytes, checksum_text = _good_zip_and_checksum()
    capture = capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, _identity())
    spot_identity = InstrumentIdentity(
        symbol=SYMBOL, market="spot", contract_type="spot",
        instrument_instance_id=capture.identity.instrument_instance_id,
    )
    assert observed_at(capture, spot_identity, "2019-09-08T08:00:00Z") == INVALID


def test_capture_identity_uses_frozen_usd_m_perpetual_vocabulary():
    zip_bytes, checksum_text = _good_zip_and_checksum()
    capture = capture_from_bytes(SYMBOL, DATE, zip_bytes, checksum_text, _identity())
    assert capture.identity.market == "usd-m"
    assert capture.identity.contract_type == "perpetual"
    assert capture.identity.symbol == "BTCUSDT"


# --- fake/missing artifact: no NOT_TRADABLE inference ------------------------

class _FakeResponse:
    def __init__(self, status_code: int, content: bytes = b"", text: str = ""):
        self.status_code = status_code
        self.content = content
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400 and self.status_code != 404:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSessionAlways404:
    def get(self, url, timeout=None):
        return _FakeResponse(404)


def test_missing_archive_returns_none_not_a_capture():
    identity = InstrumentIdentity(
        symbol="ZZZZNOTREALUSDT", market="usd-m", contract_type="perpetual",
        instrument_instance_id="binance|zzzznotrealusdt|perpetual|usd-m|placeholder",
    )
    capture = fetch_capture("ZZZZNOTREALUSDT", "2019-09-08", identity, session=_FakeSessionAlways404())
    assert capture is None


def test_missing_archive_resolves_to_unknown_never_not_tradable():
    identity = InstrumentIdentity(
        symbol="ZZZZNOTREALUSDT", market="usd-m", contract_type="perpetual",
        instrument_instance_id="binance|zzzznotrealusdt|perpetual|usd-m|placeholder",
    )
    capture = fetch_capture("ZZZZNOTREALUSDT", "2019-09-08", identity, session=_FakeSessionAlways404())
    result = observed_at(capture, identity, "2019-09-08T08:00:00Z")
    assert result == UNKNOWN
    assert result != "NOT_TRADABLE"


class _FakeSessionArchivePresentChecksumMissing:
    def get(self, url, timeout=None):
        if url.endswith(".CHECKSUM"):
            return _FakeResponse(404)
        zip_bytes, _ = _good_zip_and_checksum()
        return _FakeResponse(200, content=zip_bytes)


def test_archive_present_but_checksum_missing_fails_closed():
    with pytest.raises(ValueError, match="checksum missing"):
        fetch_capture(SYMBOL, DATE, _identity(), session=_FakeSessionArchivePresentChecksumMissing())
