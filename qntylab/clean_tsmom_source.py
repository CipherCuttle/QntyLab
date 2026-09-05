"""Bounded official Binance USD-M source adapter for clean TSMOM V1.

This adapter deliberately treats premium-index klines as optional.  The V1
contract consumes only settled funding events and USD-M trade klines.
"""
from __future__ import annotations

import csv, hashlib, io, json, urllib.error, urllib.parse, urllib.request, zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

ARCHIVE_ROOT = "https://data.binance.vision/data/futures/um/monthly"
REST_ROOT = "https://fapi.binance.com/fapi/v1"
KLINE_FIELDS = ("timestamp", "open", "high", "low", "close", "volume")
FUNDING_FIELDS = ("timestamp", "funding_interval_hours", "funding_rate")


def month_starts(start: datetime, end: datetime) -> list[tuple[int, int]]:
    current = start.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    limit = end.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    out = []
    while current < limit:
        out.append((current.year, current.month))
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def archive_url(kind: str, symbol: str, year: int, month: int) -> str:
    if kind == "fundingRate":
        return f"{ARCHIVE_ROOT}/fundingRate/{symbol}/{symbol}-fundingRate-{year}-{month:02d}.zip"
    return f"{ARCHIVE_ROOT}/{kind}/{symbol}/1h/{symbol}-1h-{year}-{month:02d}.zip"


def parse_zip_rows(payload: bytes, *, expected_symbol: str, expected_kind: str) -> tuple[list[list[str]], list[str]]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != 1:
            raise ValueError(f"unexpected ZIP members for {expected_symbol}/{expected_kind}")
        rows = list(csv.reader(io.TextIOWrapper(archive.open(names[0]), encoding="utf-8")))
    if rows and rows[0] and not rows[0][0].isdigit():
        rows = rows[1:]
    minimum = 3 if expected_kind == "fundingRate" else 6
    if any(len(row) < minimum for row in rows):
        raise ValueError(f"unexpected CSV width for {expected_symbol}/{expected_kind}")
    return [row for row in rows if row and row[0].isdigit()], names


def _get(url: str) -> tuple[int, bytes, dict[str, str]]:
    request = urllib.request.Request(url, headers={"User-Agent": "QntyLab-clean-tsmom-v1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers.items())


def _canonical_kline(row: list[str]) -> dict[str, str]:
    return dict(zip(KLINE_FIELDS, (row[0], row[1], row[2], row[3], row[4], row[5])))


def _canonical_funding(row: list[str]) -> dict[str, str]:
    # Binance calc_time can contain millisecond jitter; the frozen evaluator
    # consumes the settled event on its exact 8h UTC boundary.
    stamp = int(row[0])
    boundary = stamp - (stamp % (8 * 3600000))
    return dict(zip(FUNDING_FIELDS, (str(boundary), row[1], row[2])))


def rest_klines(symbol: str, start_ms: int, end_ms: int) -> tuple[list[list], dict]:
    query = urllib.parse.urlencode({"symbol": symbol, "interval": "1h", "startTime": start_ms, "endTime": end_ms, "limit": 1000})
    url = f"{REST_ROOT}/klines?{query}"
    status, body, headers = _get(url)
    receipt = {"url": url, "status": status, "byte_count": len(body), "sha256": hashlib.sha256(body).hexdigest(), "headers": headers}
    if status != 200:
        raise ValueError(f"REST kline request failed: {status}")
    return json.loads(body), receipt


def acquire_panel(root: Path, symbols: list[str], start: datetime, end: datetime) -> dict:
    """Acquire only frozen symbols/months; resolve archive gaps from exact REST."""
    raw_root = root / "data" / "raw"
    manifest_root = root / "data" / "manifests"
    raw_root.mkdir(parents=True, exist_ok=True); manifest_root.mkdir(parents=True, exist_ok=True)
    months = month_starts(start, end); archive_requests = rest_requests = 0
    panel = {}; resolutions = []
    for symbol in symbols:
        bars: dict[int, list[str]] = {}; funding: dict[int, list[str]] = {}; sources = []
        for year, month in months:
            for kind, target in (("klines", bars), ("fundingRate", funding)):
                url = archive_url(kind, symbol, year, month); status, body, _ = _get(url); archive_requests += 1
                if status == 404:
                    sources.append({"url": url, "status": status, "byte_count": len(body), "sha256": hashlib.sha256(body).hexdigest()}); continue
                if status != 200: raise ValueError(f"archive request failed: {status} {url}")
                rows, members = parse_zip_rows(body, expected_symbol=symbol, expected_kind=kind)
                sources.append({"url": url, "status": status, "byte_count": len(body), "sha256": hashlib.sha256(body).hexdigest(), "members": members, "row_count": len(rows)})
                for row in rows: target[int(row[0])] = row
        expected = list(range(int(start.timestamp() * 1000), int(end.timestamp() * 1000), 3600000))
        missing = [ts for ts in expected if ts not in bars]
        if missing:
            for left, right in ((missing[0], missing[-1] + 3600000),):
                rest_rows, receipt = rest_klines(symbol, left - 3600000, right + 3600000); rest_requests += 1
                rest_map = {int(row[0]): row for row in rest_rows}
                for ts in missing:
                    if ts not in rest_map: raise ValueError(f"unresolved exact REST gap {symbol} {ts}")
                    bars[ts] = rest_map[ts]
                overlap = [ts for ts in (left - 3600000, right) if ts in bars and ts in rest_map]
                if any(bars[ts][:6] != rest_map[ts][:6] for ts in overlap): raise ValueError(f"archive/REST disagreement {symbol}")
                resolutions.append({"symbol": symbol, "timestamps": missing, "provenance": "OFFICIAL_REST_EXACT_GAP_RESOLUTION", "receipt": receipt, "overlap": overlap})
        ordered = [_canonical_kline(bars[ts]) for ts in expected]
        funding_rows = [_canonical_funding(funding[ts]) for ts in sorted(funding) if int(start.timestamp()*1000) <= ts < int(end.timestamp()*1000)]
        raw = raw_root / f"{symbol}-perp-1h.csv"
        with raw.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=KLINE_FIELDS); writer.writeheader(); writer.writerows(ordered)
        funding_raw = raw_root / f"{symbol}-funding.csv"
        with funding_raw.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FUNDING_FIELDS); writer.writeheader(); writer.writerows(funding_rows)
        panel[symbol] = {"rows": len(ordered), "funding_rows": len(funding_rows), "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(), "funding_sha256": hashlib.sha256(funding_raw.read_bytes()).hexdigest(), "sources": sources}
        (manifest_root / f"{symbol}-perp-1h.json").write_text(json.dumps(panel[symbol], sort_keys=True, indent=2) + "\n")
    result = {"symbols": symbols, "start": start.isoformat().replace("+00:00", "Z"), "end": end.isoformat().replace("+00:00", "Z"), "panel": panel, "resolutions": resolutions, "archive_requests": archive_requests, "rest_requests": rest_requests, "premium_index_required": False}
    (manifest_root / "clean-tsmom-v1-source-manifest.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result
