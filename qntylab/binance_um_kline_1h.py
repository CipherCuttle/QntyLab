"""Provenance-bound Binance USD-M perpetual monthly 1h OHLCV materializer.

This intentionally small adapter knows one source family only.  It neither
discovers instruments nor makes lifecycle/tradability claims; an unavailable
object is recorded as unavailable source evidence.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import zipfile
from datetime import UTC, datetime, timedelta
from io import BytesIO, StringIO, TextIOWrapper
from pathlib import Path
from typing import Any

import requests

from .market_observation import InstrumentIdentity

ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/monthly/klines"
FIELDS = (
    "open_time",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
)
LEGACY_FIELDS = ("timestamp", "open", "high", "low", "close", "volume")
CONTRACT_VERSION = "BINANCE_USD_M_PERPETUAL_1H_MATERIALIZER_V0"
SCHEMA_VERSION = "binance-um-monthly-kline-12-v1"
MARKET, CONTRACT_TYPE, VENUE = "usd-m", "perpetual", "binance"
_SYMBOL_RE = re.compile(r"^[A-Z0-9]+$")
_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
# Literal, checksum-verified row 1 from BTCUSDT-1h-2024-01.zip.  This is
# deliberately not normalized or matched fuzzily: only this exact first row
# is an allowed header in V0.
_ALLOWED_HEADER_V1 = ("open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore")
_COLUMNS = 12


class MaterializationError(ValueError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _utc_hour(value: str | datetime) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"invalid UTC timestamp: {value!r}") from exc
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    value = value.astimezone(UTC)
    if value.minute or value.second or value.microsecond:
        raise ValueError("timestamp must be hour-aligned")
    return value


def _stamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _identity_payload(identity: InstrumentIdentity | None) -> dict[str, str] | None:
    if identity is None:
        return None
    return {"symbol": identity.symbol, "market": identity.market, "contract_type": identity.contract_type, "instrument_instance_id": identity.instrument_instance_id}


def _validate_symbol(symbol: str) -> None:
    if not isinstance(symbol, str) or not _SYMBOL_RE.fullmatch(symbol):
        raise ValueError(f"invalid Binance USD-M symbol: {symbol!r}")


def _validate_identity(symbol: str, identity: InstrumentIdentity | None) -> None:
    if identity is None:
        return
    if not isinstance(identity, InstrumentIdentity) or identity.symbol != symbol or identity.market != MARKET or identity.contract_type != CONTRACT_TYPE:
        raise MaterializationError("IDENTITY_MISMATCH", "caller-supplied InstrumentIdentity does not match Binance USD-M perpetual request")


def archive_paths(symbol: str, year: int, month: int) -> dict[str, str]:
    _validate_symbol(symbol)
    if not isinstance(year, int) or not isinstance(month, int) or not 1 <= month <= 12:
        raise ValueError("invalid year/month")
    filename = f"{symbol}-1h-{year}-{month:02d}.zip"
    zip_url = f"{ARCHIVE_BASE}/{symbol}/1h/{filename}"
    return {"archive_filename": filename, "zip_url": zip_url, "checksum_url": zip_url + ".CHECKSUM", "source_key": f"data/futures/um/monthly/klines/{symbol}/1h/{filename}"}


def months(start_inclusive: str | datetime, end_inclusive: str | datetime) -> list[tuple[int, int]]:
    start, end = _utc_hour(start_inclusive), _utc_hour(end_inclusive)
    if start > end:
        raise ValueError("start_inclusive must not be after end_inclusive")
    cursor = start.replace(day=1, hour=0)
    result = []
    while cursor <= end:
        result.append((cursor.year, cursor.month))
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return result


def _verify_checksum(zip_bytes: bytes, checksum_text: str, filename: str) -> tuple[str, str]:
    parts = checksum_text.strip().split()
    if len(parts) != 2 or not _HEX64_RE.fullmatch(parts[0]):
        raise MaterializationError("SOURCE_AUTHENTICATION_UNAVAILABLE", "malformed or absent published checksum")
    published, claimed_filename = parts[0].lower(), parts[1].lstrip("*")
    if claimed_filename != filename:
        raise MaterializationError("SOURCE_AUTHENTICATION_FAILED", "published checksum filename does not match archive")
    actual = hashlib.sha256(zip_bytes).hexdigest()
    if published != actual:
        raise MaterializationError("SOURCE_AUTHENTICATION_FAILED", "published checksum digest does not match archive bytes")
    return published, actual


def _parse_rows(zip_bytes: bytes, filename: str) -> tuple[str, list[dict[str, str]], int, str, str]:
    try:
        archive = zipfile.ZipFile(BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise MaterializationError("ARCHIVE_INVALID", f"unreadable ZIP: {filename}") from exc
    with archive:
        names = archive.namelist()
        if len(names) != 1 or not names[0].lower().endswith(".csv"):
            raise MaterializationError("ARCHIVE_INVALID", "archive must contain exactly one CSV member")
        member = names[0]
        try:
            with archive.open(member) as raw:
                source_rows = list(csv.reader(TextIOWrapper(raw, encoding="utf-8", newline="")))
        except (UnicodeDecodeError, csv.Error, OSError, zipfile.BadZipFile) as exc:
            raise MaterializationError("SCHEMA_INVALID", "unreadable archive CSV") from exc
    if not source_rows:
        raise MaterializationError("SCHEMA_INVALID", "archive contains zero rows")
    begin = 1 if tuple(source_rows[0]) == _ALLOWED_HEADER_V1 else 0
    parsed: list[dict[str, str]] = []
    seen: set[int] = set()
    for position, row in enumerate(source_rows[begin:], begin + 1):
        if len(row) != _COLUMNS:
            raise MaterializationError("SCHEMA_INVALID", f"malformed kline row {position}")
        try:
            ms = int(row[0])
            if str(ms) != row[0] or ms < 0 or ms % 3_600_000:
                raise ValueError
            when = datetime.fromtimestamp(ms / 1000, UTC)
            values = [float(row[i]) for i in range(1, 6)]
            close_ms = int(row[6])
            trade_count = int(row[8])
            quote_volume = float(row[7])
            taker_buy_base_volume = float(row[9])
            taker_buy_quote_volume = float(row[10])
        except (ValueError, OverflowError, OSError) as exc:
            raise MaterializationError("SCHEMA_INVALID", f"invalid kline timestamp/numeric field at row {position}") from exc
        o, h, l, c, v = values
        all_numeric = [*values, quote_volume, taker_buy_base_volume, taker_buy_quote_volume]
        if (
            not all(math.isfinite(x) for x in all_numeric)
            or close_ms < 0
            or trade_count < 0
            or min(o, h, l, c) <= 0
            or min(v, quote_volume, taker_buy_base_volume, taker_buy_quote_volume) < 0
            or taker_buy_quote_volume > quote_volume
            or taker_buy_base_volume > v
            or h < max(o, c, l)
            or l > min(o, c, h)
        ):
            raise MaterializationError("SCHEMA_INVALID", f"invalid OHLCV at row {position}")
        if ms in seen:
            raise MaterializationError("SCHEMA_INVALID", f"duplicate opening timestamp at row {position}")
        seen.add(ms)
        parsed.append(
            {
                "open_time": row[0],
                "timestamp": _stamp(when),
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "volume": row[5],
                "close_time": row[6],
                "quote_volume": row[7],
                "trade_count": row[8],
                "taker_buy_base_volume": row[9],
                "taker_buy_quote_volume": row[10],
            }
        )
    if not parsed:
        raise MaterializationError("SCHEMA_INVALID", "archive contains no data rows")
    parsed.sort(key=lambda row: row["timestamp"])
    return member, parsed, len(source_rows) - begin, parsed[0]["timestamp"], parsed[-1]["timestamp"]


def receipt_from_bytes(symbol: str, year: int, month: int, zip_bytes: bytes, checksum_text: str, identity: InstrumentIdentity | None = None, retrieved_at: str | None = None) -> tuple[dict[str, Any], list[dict[str, str]]]:
    paths = archive_paths(symbol, year, month)
    _validate_identity(symbol, identity)
    try:
        published, actual = _verify_checksum(zip_bytes, checksum_text, paths["archive_filename"])
        member, rows, raw_count, first, last = _parse_rows(zip_bytes, paths["archive_filename"])
    except MaterializationError:
        raise
    receipt = {"symbol": symbol, "InstrumentIdentity": _identity_payload(identity), "source_family": "data.binance.vision.monthly.klines", **paths, "year": year, "month": month, "interval": "1h", "retrieved_at": retrieved_at, "status": "MATERIALIZED_VERIFIED", "published_sha256": published, "actual_raw_sha256": actual, "archive_member_name": member, "raw_row_count": raw_count, "admitted_bar_count": len(rows), "first_source_timestamp": first, "last_source_timestamp": last, "schema_version": SCHEMA_VERSION}
    return receipt, rows


def _receipt_digest(receipt: dict[str, Any]) -> str:
    return _digest({key: value for key, value in receipt.items() if key != "retrieved_at"})


def materialize_from_objects(symbol: str, start_inclusive: str | datetime, end_inclusive: str | datetime, objects: dict[tuple[int, int], tuple[bytes | None, str | None]], identity: InstrumentIdentity | None = None, retrieval_generation_identity: str = "local-fixture") -> dict[str, Any]:
    """Pure materialization for authenticated object bytes; used by offline tests."""
    _validate_symbol(symbol)
    start, end = _utc_hour(start_inclusive), _utc_hour(end_inclusive)
    requested_months = months(start, end)
    try:
        _validate_identity(symbol, identity)
        identity_error = None
    except MaterializationError as exc:
        identity_error = exc
    receipts, all_rows, blocked = [], [], False
    for year, month in requested_months:
        paths = archive_paths(symbol, year, month)
        zip_bytes, checksum = objects.get((year, month), (None, None))
        base = {"symbol": symbol, "InstrumentIdentity": _identity_payload(identity), "source_family": "data.binance.vision.monthly.klines", **paths, "year": year, "month": month, "interval": "1h", "retrieved_at": None, "schema_version": SCHEMA_VERSION}
        if identity_error is not None:
            receipt = {**base, "status": "IDENTITY_MISMATCH", "published_sha256": None, "actual_raw_sha256": hashlib.sha256(zip_bytes).hexdigest() if zip_bytes is not None else None, "archive_member_name": None, "raw_row_count": 0, "admitted_bar_count": 0, "first_source_timestamp": None, "last_source_timestamp": None}
            blocked = True
        elif zip_bytes is None:
            receipt = {**base, "status": "SOURCE_OBJECT_ABSENT", "published_sha256": None, "actual_raw_sha256": None, "archive_member_name": None, "raw_row_count": 0, "admitted_bar_count": 0, "first_source_timestamp": None, "last_source_timestamp": None}
            blocked = True
        elif checksum is None:
            receipt = {**base, "status": "SOURCE_AUTHENTICATION_UNAVAILABLE", "published_sha256": None, "actual_raw_sha256": hashlib.sha256(zip_bytes).hexdigest(), "archive_member_name": None, "raw_row_count": 0, "admitted_bar_count": 0, "first_source_timestamp": None, "last_source_timestamp": None}
            blocked = True
        else:
            try:
                receipt, rows = receipt_from_bytes(symbol, year, month, zip_bytes, checksum, identity)
                all_rows.extend(rows)
            except MaterializationError as exc:
                receipt = {**base, "status": exc.status, "published_sha256": None, "actual_raw_sha256": hashlib.sha256(zip_bytes).hexdigest(), "archive_member_name": None, "raw_row_count": 0, "admitted_bar_count": 0, "first_source_timestamp": None, "last_source_timestamp": None}
                blocked = True
        receipt["receipt_digest"] = _receipt_digest(receipt)
        receipts.append(receipt)
    if blocked:
        return {"status": "BLOCKED", "symbol": symbol, "receipts": receipts, "normalized_csv": None, "manifest": None}
    clipped = [row for row in sorted(all_rows, key=lambda row: row["timestamp"]) if _stamp(start) <= row["timestamp"] <= _stamp(end)]
    if len({row["timestamp"] for row in clipped}) != len(clipped):
        raise MaterializationError("SCHEMA_INVALID", "duplicate timestamp across source objects")
    gaps = [f"{prior['timestamp']} -> {current['timestamp']}" for prior, current in zip(clipped, clipped[1:]) if _utc_hour(current["timestamp"]) - _utc_hour(prior["timestamp"]) != timedelta(hours=1)]
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader(); writer.writerows(clipped)
    normalized_csv = output.getvalue()
    normalized_sha256 = hashlib.sha256(normalized_csv.encode()).hexdigest()
    manifest = {"symbol": symbol, "InstrumentIdentity": _identity_payload(identity), "requested_start": _stamp(start), "requested_end": _stamp(end), "interval": "1h", "normalized_sha256": normalized_sha256, "normalized_row_count": len(clipped), "normalized_first_timestamp": clipped[0]["timestamp"] if clipped else None, "normalized_last_timestamp": clipped[-1]["timestamp"] if clipped else None, "gap_count": len(gaps), "gap_details": gaps, "ordered_source_object_receipt_digests": [receipt["receipt_digest"] for receipt in receipts], "aggregate_source_receipt_digest": _digest([receipt["receipt_digest"] for receipt in receipts]), "materializer_implementation_identity": __name__, "materializer_contract_version": CONTRACT_VERSION, "retrieval_generation_identity": retrieval_generation_identity}
    return {"status": "MATERIALIZED_VERIFIED", "symbol": symbol, "receipts": receipts, "normalized_csv": normalized_csv, "manifest": manifest}


def materialize(symbol: str, start_inclusive: str | datetime, end_inclusive: str | datetime, root: Path, identity: InstrumentIdentity | None = None, session: requests.Session | None = None, retrieval_generation_identity: str = "binance-um-kline-1h-v0") -> dict[str, Any]:
    """Fetch each required monthly object, preserve verified bytes, and write evidence."""
    client = session or requests.Session()
    start, end = _utc_hour(start_inclusive), _utc_hour(end_inclusive)
    objects: dict[tuple[int, int], tuple[bytes | None, str | None]] = {}
    retrieved_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    for year, month in months(start, end):
        paths = archive_paths(symbol, year, month)
        response = client.get(paths["zip_url"], timeout=(10, 90))
        if response.status_code == 404:
            objects[(year, month)] = (None, None); continue
        response.raise_for_status()
        check = client.get(paths["checksum_url"], timeout=30)
        objects[(year, month)] = (response.content, check.text if check.status_code == 200 else None)
    result = materialize_from_objects(symbol, start, end, objects, identity, retrieval_generation_identity)
    # Retain every actually downloaded source byte object by content address,
    # even when another requested object blocks the aggregate materialization.
    cache = root / "data" / "archive" / "binance_um_kline_1h"
    cache.mkdir(parents=True, exist_ok=True)
    for zip_bytes, _ in objects.values():
        if zip_bytes is not None:
            digest = hashlib.sha256(zip_bytes).hexdigest()
            (cache / f"{digest}.zip").write_bytes(zip_bytes)
    receipt_dir = root / "data" / "receipts" / "binance_um_kline_1h"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    for receipt in result["receipts"]:
        receipt["retrieved_at"] = retrieved_at
        (receipt_dir / f"{symbol}-1h-{receipt['year']}-{receipt['month']:02d}.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if result["status"] == "MATERIALIZED_VERIFIED":
        actual = result["receipts"]
        raw = root / "data" / "raw" / f"{symbol}-perp-1h.csv"
        raw.parent.mkdir(parents=True, exist_ok=True); raw.write_text(result["normalized_csv"], encoding="utf-8")
        manifest_path = root / "data" / "manifests" / f"{symbol}-perp-1h-hourly-input-v0.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True); manifest_path.write_text(json.dumps(result["manifest"], sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result
