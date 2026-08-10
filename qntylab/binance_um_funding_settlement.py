"""Authenticated Binance USD-M funding settlement materializer.

The publisher-checksummed monthly archive is the sole causal source.  The
official USD-M funding-rate REST endpoint is retained only as an independent,
exact coverage witness.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO, TextIOWrapper
from pathlib import Path
from typing import Any

import requests

from .market_observation import InstrumentIdentity

ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/monthly/fundingRate"
REST_ENDPOINT = "https://fapi.binance.com/fapi/v1/fundingRate"
REST_LIMIT = 1000
SOURCE_FAMILY = "data.binance.vision.monthly.fundingRate"
REST_SOURCE_FAMILY = "fapi.binance.com.fundingRate"
CONTRACT_VERSION = "BINANCE_USDM_FUNDING_SETTLEMENT_MATERIALIZER_V0"
SCHEMA_VERSION = "binance-um-monthly-fundingRate-3-v1"
MARKET, CONTRACT_TYPE, VENUE = "usd-m", "perpetual", "binance"
HEADER = ("calc_time", "funding_interval_hours", "last_funding_rate")
_SYMBOL_RE = re.compile(r"^[A-Z0-9]+$")
_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class MaterializationError(ValueError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _stamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _funding_stamp(ms: int) -> str:
    seconds, millis = divmod(ms, 1000)
    value = datetime.fromtimestamp(seconds, UTC).replace(microsecond=millis * 1000)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{millis:03d}Z"


def _utc_boundary(value: str | datetime) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"invalid UTC timestamp: {value!r}") from exc
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    return value.astimezone(UTC)


def _identity_payload(identity: InstrumentIdentity | None) -> dict[str, str] | None:
    if identity is None:
        return None
    return {"symbol": identity.symbol, "market": identity.market, "contract_type": identity.contract_type, "instrument_instance_id": identity.instrument_instance_id}


def _validate_symbol(symbol: str) -> None:
    if not isinstance(symbol, str) or not _SYMBOL_RE.fullmatch(symbol):
        raise ValueError(f"invalid Binance USD-M symbol: {symbol!r}")


def _validate_identity(symbol: str, identity: InstrumentIdentity | None) -> None:
    if identity is not None and (not isinstance(identity, InstrumentIdentity) or identity.symbol != symbol or identity.market != MARKET or identity.contract_type != CONTRACT_TYPE):
        raise MaterializationError("IDENTITY_MISMATCH", "caller-supplied InstrumentIdentity does not match Binance USD-M perpetual request")


def archive_paths(symbol: str, year: int, month: int) -> dict[str, str]:
    _validate_symbol(symbol)
    if not isinstance(year, int) or not isinstance(month, int) or month < 1 or month > 12:
        raise ValueError("invalid year/month")
    filename = f"{symbol}-fundingRate-{year}-{month:02d}.zip"
    source_key = f"data/futures/um/monthly/fundingRate/{symbol}/{filename}"
    zip_url = f"https://data.binance.vision/{source_key}"
    return {"archive_filename": filename, "source_key": source_key, "zip_url": zip_url, "checksum_url": zip_url + ".CHECKSUM"}


def months(start_inclusive: str | datetime, end_inclusive: str | datetime) -> list[tuple[int, int]]:
    start, end = _utc_boundary(start_inclusive), _utc_boundary(end_inclusive)
    if start > end:
        raise ValueError("start_inclusive must not be after end_inclusive")
    cursor = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result: list[tuple[int, int]] = []
    while cursor <= end:
        result.append((cursor.year, cursor.month))
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return result


def _checksum_bytes(value: str | bytes) -> tuple[bytes, str]:
    raw = value.encode("utf-8") if isinstance(value, str) else bytes(value)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MaterializationError("SOURCE_AUTHENTICATION_UNAVAILABLE", "checksum is not UTF-8") from exc
    return raw, text


def _verify_checksum(zip_bytes: bytes, checksum: str | bytes, filename: str) -> tuple[str, str, str]:
    raw, text = _checksum_bytes(checksum)
    parts = text.strip().split()
    if len(parts) != 2 or not _HEX64_RE.fullmatch(parts[0]):
        raise MaterializationError("SOURCE_AUTHENTICATION_UNAVAILABLE", "malformed or absent published checksum")
    published, claimed = parts[0].lower(), parts[1].lstrip("*")
    if claimed != filename:
        raise MaterializationError("SOURCE_AUTHENTICATION_FAILED", "published checksum filename does not match archive")
    actual = hashlib.sha256(zip_bytes).hexdigest()
    if published != actual:
        raise MaterializationError("SOURCE_AUTHENTICATION_FAILED", "published checksum digest does not match archive bytes")
    return published, actual, hashlib.sha256(raw).hexdigest()


def _parse_integer(value: str, label: str, *, positive: bool = False) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise MaterializationError("SCHEMA_INVALID", f"invalid {label}") from exc
    if not isinstance(value, str) or str(result) != value or result < (1 if positive else 0):
        raise MaterializationError("SCHEMA_INVALID", f"invalid {label}")
    return result


def _rate(value: str) -> str:
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise MaterializationError("SCHEMA_INVALID", "invalid funding rate") from exc
    if not number.is_finite():
        raise MaterializationError("SCHEMA_INVALID", "funding rate must be finite")
    if number == 0:
        return "0"
    fixed = format(number, "f")
    if "." in fixed:
        fixed = fixed.rstrip("0").rstrip(".")
    return fixed


def _epoch_ms(value: datetime) -> int:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = value - epoch
    return delta.days * 86_400_000 + delta.seconds * 1_000 + delta.microseconds // 1_000


def rest_query(symbol: str, start_inclusive: str | datetime, end_inclusive: str | datetime) -> dict[str, int | str]:
    """Return the frozen official REST witness query for an admitted range."""
    _validate_symbol(symbol)
    start, end = _utc_boundary(start_inclusive), _utc_boundary(end_inclusive)
    if start > end:
        raise ValueError("start_inclusive must not be after end_inclusive")
    return {"symbol": symbol, "startTime": _epoch_ms(start), "endTime": _epoch_ms(end), "limit": REST_LIMIT}


def _rest_page_bytes(page: bytes | str | list[dict[str, Any]]) -> bytes:
    if isinstance(page, bytes):
        return page
    if isinstance(page, str):
        return page.encode("utf-8")
    return json.dumps(page, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def _parse_rest_page(page: bytes | str | list[dict[str, Any]], symbol: str) -> tuple[bytes, list[tuple[int, str]]]:
    raw = _rest_page_bytes(page)
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MaterializationError("REST_WITNESS_INVALID", "REST witness page is not valid JSON") from exc
    if not isinstance(payload, list):
        raise MaterializationError("REST_WITNESS_INVALID", "REST witness page must be a JSON array")
    parsed: list[tuple[int, str]] = []
    previous: int | None = None
    for row in payload:
        if not isinstance(row, dict) or row.get("symbol") != symbol or not isinstance(row.get("fundingTime"), int) or isinstance(row.get("fundingTime"), bool) or not isinstance(row.get("fundingRate"), str):
            raise MaterializationError("REST_WITNESS_INVALID", "malformed REST witness row")
        timestamp = row["fundingTime"]
        if timestamp < 0 or (previous is not None and timestamp < previous):
            raise MaterializationError("REST_WITNESS_INVALID", "REST rows must be non-decreasing by fundingTime")
        previous = timestamp
        try:
            rate = _rate(row["fundingRate"])
        except MaterializationError as exc:
            raise MaterializationError("REST_WITNESS_INVALID", "invalid REST funding rate") from exc
        parsed.append((timestamp, rate))
    return raw, parsed


def _reconcile_rest_pages(symbol: str, start: datetime, end: datetime, pages: list[bytes | str | list[dict[str, Any]]] | None) -> dict[str, Any]:
    if pages is None:
        return {"status": "REST_COVERAGE_UNAVAILABLE", "rows": [], "pages": [], "digest": None, "differences": []}
    query = rest_query(symbol, start, end)
    rows: list[tuple[int, str]] = []
    page_receipts: list[dict[str, Any]] = []
    for index, page in enumerate(pages):
        raw, page_rows = _parse_rest_page(page, symbol)
        page_query = {**query, "startTime": rows[-1][0] if rows else query["startTime"]}
        bounded = [(timestamp, rate) for timestamp, rate in page_rows if query["startTime"] <= timestamp <= query["endTime"]]
        if page_rows and (page_rows[0][0] < query["startTime"] or page_rows[-1][0] > query["endTime"]):
            raise MaterializationError("REST_WITNESS_INVALID", "REST witness row is outside the requested range")
        if rows and bounded:
            previous = rows[-1]
            first = bounded[0]
            if first[0] < previous[0] or (first[0] == previous[0] and first[1] != previous[1]):
                raise MaterializationError("REST_WITNESS_INVALID", "REST page chain is non-monotonic or conflicting")
            if first == previous:
                bounded = bounded[1:]
        if rows and page_rows and not bounded and page_rows[0] == rows[-1]:
            bounded = []
        for row in bounded:
            if rows and row[0] == rows[-1][0]:
                if row != rows[-1]:
                    raise MaterializationError("REST_WITNESS_INVALID", "conflicting REST duplicate")
                raise MaterializationError("REST_WITNESS_INVALID", "duplicate REST event is not a page boundary")
            if rows and row[0] < rows[-1][0]:
                raise MaterializationError("REST_WITNESS_INVALID", "REST page chain is not ordered")
            rows.append(row)
        page_receipts.append({"page_index": index, "query": page_query, "endpoint": REST_ENDPOINT, "http_status": 200, "raw_sha256": hashlib.sha256(raw).hexdigest(), "raw_byte_count": len(raw), "row_count": len(page_rows), "first_funding_time": _funding_stamp(page_rows[0][0]) if page_rows else None, "last_funding_time": _funding_stamp(page_rows[-1][0]) if page_rows else None})
    return {"status": "AVAILABLE", "rows": rows, "pages": page_receipts, "digest": _digest(page_receipts), "differences": []}


def _coverage_difference(archive_rows: list[dict[str, Any]], rest_rows: list[tuple[int, str]]) -> tuple[str, list[dict[str, Any]]]:
    archive = {(row["funding_time_ms"], row["funding_rate"]) for row in archive_rows}
    rest = set(rest_rows)
    archive_by_time = {timestamp: rate for timestamp, rate in archive}
    rest_by_time = {timestamp: rate for timestamp, rate in rest}
    disagreements = sorted(timestamp for timestamp in archive_by_time.keys() & rest_by_time.keys() if archive_by_time[timestamp] != rest_by_time[timestamp])
    if disagreements:
        return "FUNDING_RATE_DISAGREEMENT", [{"funding_time_ms": timestamp} for timestamp in disagreements]
    extra_rest = sorted(rest - archive)
    if extra_rest:
        return "ARCHIVE_EVENT_MISSING", [{"funding_time_ms": t, "funding_rate": r} for t, r in extra_rest]
    extra_archive = sorted(archive - rest)
    if extra_archive:
        return "REST_WITNESS_MISSING_EVENT", [{"funding_time_ms": t, "funding_rate": r} for t, r in extra_archive]
    return "COMPLETE", []


def _parse_rows(zip_bytes: bytes, symbol: str, filename: str) -> tuple[str, list[dict[str, Any]], int, str, str, list[int]]:
    try:
        archive = zipfile.ZipFile(BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise MaterializationError("ARCHIVE_INVALID", f"unreadable ZIP: {filename}") from exc
    with archive:
        names = archive.namelist()
        expected = f"{filename.removesuffix('.zip')}.csv"
        if len(names) != 1 or names[0] != expected:
            raise MaterializationError("ARCHIVE_INVALID", "archive must contain exactly the expected CSV member")
        try:
            with archive.open(names[0]) as raw:
                rows = list(csv.reader(TextIOWrapper(raw, encoding="utf-8", newline="")))
        except (UnicodeDecodeError, csv.Error, OSError) as exc:
            raise MaterializationError("SCHEMA_INVALID", "unreadable archive CSV") from exc
    if not rows or tuple(rows[0]) != HEADER:
        raise MaterializationError("SCHEMA_INVALID", "funding archive header does not match frozen schema")
    parsed: list[dict[str, Any]] = []
    intervals: list[int] = []
    previous: int | None = None
    for position, row in enumerate(rows[1:], 2):
        if len(row) != len(HEADER):
            raise MaterializationError("SCHEMA_INVALID", f"malformed funding row {position}")
        timestamp = _parse_integer(row[0], "calc_time")
        if previous is not None and timestamp <= previous:
            raise MaterializationError("SCHEMA_INVALID", "funding rows must be strictly increasing by calc_time")
        previous = timestamp
        interval = _parse_integer(row[1], "funding_interval_hours", positive=True)
        intervals.append(interval)
        parsed.append({"symbol": symbol, "funding_time_ms": timestamp, "funding_time_utc": _funding_stamp(timestamp), "funding_rate": _rate(row[2]), "funding_interval_hours": interval})
    if not parsed:
        raise MaterializationError("SCHEMA_INVALID", "archive contains no funding events")
    return names[0], parsed, len(parsed), parsed[0]["funding_time_utc"], parsed[-1]["funding_time_utc"], intervals


def _receipt_digest(receipt: dict[str, Any]) -> str:
    return _digest({key: value for key, value in receipt.items() if key != "retrieved_at"})


def receipt_from_bytes(symbol: str, year: int, month: int, zip_bytes: bytes, checksum: str | bytes, identity: InstrumentIdentity | None = None, retrieved_at: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    paths = archive_paths(symbol, year, month)
    _validate_identity(symbol, identity)
    published, actual, checksum_digest = _verify_checksum(zip_bytes, checksum, paths["archive_filename"])
    member, rows, raw_count, first, last, intervals = _parse_rows(zip_bytes, symbol, paths["archive_filename"])
    receipt = {"symbol": symbol, "InstrumentIdentity": _identity_payload(identity), "source_family": SOURCE_FAMILY, **paths, "year": year, "month": month, "status": "MATERIALIZED_VERIFIED", "retrieved_at": retrieved_at, "published_sha256": published, "actual_raw_sha256": actual, "checksum_text_sha256": checksum_digest, "archive_member_name": member, "raw_row_count": raw_count, "admitted_event_count": len(rows), "first_source_funding_time": first, "last_source_funding_time": last, "observed_interval_hours": sorted(set(intervals)), "schema_version": SCHEMA_VERSION, "materializer_contract_version": CONTRACT_VERSION}
    return receipt, rows


def materialize_from_objects(symbol: str, start_inclusive: str | datetime, end_inclusive: str | datetime, objects: dict[tuple[int, int], tuple[bytes | None, str | bytes | None]], identity: InstrumentIdentity | None = None, retrieval_generation_identity: str = "local-fixture", rest_witness_pages: list[bytes | str | list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    """Materialize authenticated archive objects and supplied REST pages offline."""
    _validate_symbol(symbol)
    start, end = _utc_boundary(start_inclusive), _utc_boundary(end_inclusive)
    requested = months(start, end)
    identity_error: MaterializationError | None = None
    try:
        _validate_identity(symbol, identity)
    except MaterializationError as exc:
        identity_error = exc
    receipts: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    blocked = False
    for year, month in requested:
        paths = archive_paths(symbol, year, month)
        zip_bytes, checksum = objects.get((year, month), (None, None))
        base = {"symbol": symbol, "InstrumentIdentity": _identity_payload(identity), "source_family": SOURCE_FAMILY, **paths, "year": year, "month": month, "retrieved_at": None, "status": "BLOCKED", "published_sha256": None, "actual_raw_sha256": hashlib.sha256(zip_bytes).hexdigest() if zip_bytes is not None else None, "checksum_text_sha256": hashlib.sha256((checksum.encode("utf-8") if isinstance(checksum, str) else bytes(checksum)) ).hexdigest() if checksum is not None else None, "archive_member_name": None, "raw_row_count": 0, "admitted_event_count": 0, "first_source_funding_time": None, "last_source_funding_time": None, "observed_interval_hours": [], "schema_version": SCHEMA_VERSION, "materializer_contract_version": CONTRACT_VERSION}
        if identity_error:
            base["status"] = identity_error.status
        elif zip_bytes is None:
            base["status"] = "SOURCE_OBJECT_ABSENT"
        elif checksum is None:
            base["status"] = "SOURCE_AUTHENTICATION_UNAVAILABLE"
        else:
            try:
                receipt, rows = receipt_from_bytes(symbol, year, month, zip_bytes, checksum, identity)
                base = receipt
                for row in rows:
                    row["_source_month"] = (year, month)
                all_rows.extend(rows)
            except MaterializationError as exc:
                base["status"] = exc.status
        base["receipt_digest"] = _receipt_digest(base)
        receipts.append(base)
        if base["status"] != "MATERIALIZED_VERIFIED":
            blocked = True
    ordered_digests = [r["receipt_digest"] for r in receipts]
    coverage: dict[str, Any]
    try:
        coverage = _reconcile_rest_pages(symbol, start, end, rest_witness_pages)
    except MaterializationError as exc:
        coverage = {"status": exc.status, "rows": [], "pages": [], "digest": None, "differences": []}
    start_ms, end_ms = _epoch_ms(start), _epoch_ms(end)
    admitted_archive_rows = [row for row in all_rows if start_ms <= row["funding_time_ms"] <= end_ms]
    if not blocked and coverage["status"] != "AVAILABLE":
        blocked = True
    if not blocked:
        coverage_status, differences = _coverage_difference(admitted_archive_rows, coverage["rows"])
        coverage["status"], coverage["differences"] = coverage_status, differences
        if coverage_status != "COMPLETE":
            blocked = True
    coverage_reconciliation_digest = _digest({"archive": [(r["funding_time_ms"], r["funding_rate"]) for r in admitted_archive_rows], "rest": coverage["rows"], "status": coverage["status"], "differences": coverage["differences"]})
    if blocked:
        return {"status": "BLOCKED", "symbol": symbol, "receipts": receipts, "normalized_jsonl": None, "manifest": {"symbol": symbol, "coverage_status": coverage["status"], "archive_event_count": len(admitted_archive_rows), "rest_event_count": len(coverage["rows"]), "rest_coverage_witness_digest": coverage["digest"], "coverage_reconciliation_digest": coverage_reconciliation_digest, "reconciliation_differences": coverage["differences"]}}
    events = [{key: row[key] for key in ("symbol", "funding_time_ms", "funding_time_utc", "funding_rate")} for row in admitted_archive_rows]
    normalized_jsonl = "".join(json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n" for event in events)
    normalized_sha256 = hashlib.sha256(normalized_jsonl.encode("utf-8")).hexdigest()
    observed = sorted({interval for row in all_rows for interval in [row["funding_interval_hours"]]})
    archive_digest = _digest(ordered_digests)
    manifest = {"symbol": symbol, "InstrumentIdentity": _identity_payload(identity), "requested_start": _stamp(start), "requested_end": _stamp(end), "normalized_sha256": normalized_sha256, "normalized_event_count": len(events), "normalized_first_funding_time": events[0]["funding_time_utc"] if events else None, "normalized_last_funding_time": events[-1]["funding_time_utc"] if events else None, "funding_content_authority": "PUBLISHER_CHECKSUMMED_BINANCE_ARCHIVE", "coverage_witness": "OFFICIAL_BINANCE_REST", "coverage_status": "COMPLETE", "archive_event_count": len(admitted_archive_rows), "rest_event_count": len(coverage["rows"]), "reconciliation_difference_count": 0, "archive_aggregate_source_receipt_digest": archive_digest, "rest_coverage_witness_digest": coverage["digest"], "coverage_reconciliation_digest": coverage_reconciliation_digest, "observed_funding_interval_hours": observed, "interval_metadata_role": "DIAGNOSTIC_ONLY", "mark_price": "SOURCE_NOT_PROVIDED", "rate_type": "SOURCE_NOT_PROVIDED", "ordered_source_object_receipt_digests": ordered_digests, "aggregate_source_receipt_digest": archive_digest, "materializer_implementation_identity": __name__, "materializer_contract_version": CONTRACT_VERSION, "retrieval_generation_identity": retrieval_generation_identity}
    return {"status": "MATERIALIZED_VERIFIED", "symbol": symbol, "receipts": receipts, "normalized_jsonl": normalized_jsonl, "manifest": manifest}


def materialize(symbol: str, start_inclusive: str | datetime, end_inclusive: str | datetime, root: Path, identity: InstrumentIdentity | None = None, session: requests.Session | None = None, retrieval_generation_identity: str = CONTRACT_VERSION) -> dict[str, Any]:
    client = session or requests.Session()
    objects: dict[tuple[int, int], tuple[bytes | None, str | None]] = {}
    for year, month in months(start_inclusive, end_inclusive):
        paths = archive_paths(symbol, year, month)
        response = client.get(paths["zip_url"], timeout=(10, 90))
        if response.status_code == 404:
            objects[(year, month)] = (None, None)
            continue
        response.raise_for_status()
        checksum_response = client.get(paths["checksum_url"], timeout=30)
        objects[(year, month)] = (response.content, checksum_response.content if checksum_response.status_code == 200 else None)
    rest_pages: list[bytes] | None = []
    query = rest_query(symbol, start_inclusive, end_inclusive)
    try:
        next_start = int(query["startTime"])
        while True:
            params = {**query, "startTime": next_start}
            response = client.get(REST_ENDPOINT, params=params, timeout=(10, 30))
            if response.status_code != 200:
                rest_pages = None
                break
            raw = bytes(response.content)
            rest_pages.append(raw)
            _, page_rows = _parse_rest_page(raw, symbol)
            if not page_rows or page_rows[-1][0] >= int(query["endTime"]):
                break
            if len(page_rows) < REST_LIMIT:
                break
            if page_rows[-1][0] < next_start:
                rest_pages = None
                break
            next_start = page_rows[-1][0]
    except (requests.RequestException, MaterializationError, ValueError, TypeError):
        rest_pages = None
    result = materialize_from_objects(symbol, start_inclusive, end_inclusive, objects, identity, retrieval_generation_identity, rest_pages)
    retrieved_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    archive_dir = root / "data/archive/binance_um_funding_settlement"
    rest_dir = root / "data/archive/binance_um_funding_rest_witness"
    receipt_dir = root / "data/receipts/binance_um_funding_settlement"
    archive_dir.mkdir(parents=True, exist_ok=True)
    rest_dir.mkdir(parents=True, exist_ok=True)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    for zip_bytes, checksum in objects.values():
        if zip_bytes is not None:
            (archive_dir / f"{hashlib.sha256(zip_bytes).hexdigest()}.zip").write_bytes(zip_bytes)
        if checksum is not None:
            raw = checksum.encode("utf-8") if isinstance(checksum, str) else bytes(checksum)
            (archive_dir / f"{hashlib.sha256(raw).hexdigest()}.CHECKSUM").write_bytes(raw)
    if rest_pages:
        for page in rest_pages:
            (rest_dir / f"{hashlib.sha256(page).hexdigest()}.json").write_bytes(page)
    for receipt in result["receipts"]:
        receipt["retrieved_at"] = retrieved_at
        (receipt_dir / f"{symbol}-{receipt['year']}-{receipt['month']:02d}-{receipt['receipt_digest']}.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if result["status"] == "MATERIALIZED_VERIFIED":
        raw_path = root / "data/raw" / f"{symbol}-perp-funding-events.jsonl"
        manifest_path = root / "data/manifests" / f"{symbol}-perp-funding-events-v0.json"
        raw_path.parent.mkdir(parents=True, exist_ok=True); manifest_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(result["normalized_jsonl"], encoding="utf-8")
        manifest_path.write_text(json.dumps(result["manifest"], sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result
