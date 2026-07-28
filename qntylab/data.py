from __future__ import annotations

import csv, hashlib, json, math, zipfile
from io import BytesIO, TextIOWrapper
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests

BASE_URL = "https://data-api.binance.vision/api/v3/klines"
FIELDS = ("timestamp", "open", "high", "low", "close", "volume")
PERP_FIELDS = ("timestamp", "open", "high", "low", "close", "volume", "quote_volume", "trade_count", "taker_buy_base_volume", "taker_buy_quote_volume", "premium")
FUNDING_FIELDS = ("timestamp", "funding_interval_hours", "funding_rate")
ARCHIVE_URL = "https://data.binance.vision/data/futures/um/monthly/{kind}/{symbol}/{interval}/{filename}.zip"

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def validate(rows: list[dict[str, str]], interval_hours: int = 1) -> list[str]:
    if not rows: raise ValueError("zero rows")
    previous = None; gaps: list[str] = []
    for i, row in enumerate(rows, 1):
        try:
            when = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            o, h, l, c, v = (float(row[x]) for x in FIELDS[1:])
        except (KeyError, TypeError, ValueError) as exc: raise ValueError(f"invalid row {i}") from exc
        if not all(math.isfinite(x) for x in (o, h, l, c, v)) or min(o,h,l,c) <= 0 or v < 0: raise ValueError(f"invalid OHLCV row {i}")
        if h < max(o,c,l) or l > min(o,c,h): raise ValueError(f"inconsistent OHLC row {i}")
        if previous is not None:
            delta = when - previous
            if delta <= timedelta(0): raise ValueError("timestamps must be strictly increasing and unique")
            if delta != timedelta(hours=interval_hours): gaps.append(f"{previous.isoformat()} -> {when.isoformat()} ({delta})")
        previous = when
    return gaps

def fetch(symbol: str, start: str, root: Path, interval: str = "1h", end: datetime | None = None) -> dict:
    if interval != "1h": raise ValueError("v0 supports only 1h")
    start_at = datetime.fromisoformat(start).replace(tzinfo=UTC)
    # The latest *complete* candle starts one hour before the current UTC hour.
    now = end or datetime.now(UTC)
    final_open = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    cursor = int(start_at.timestamp() * 1000); final_ms = int(final_open.timestamp() * 1000)
    bars: list[list] = []
    session = requests.Session()
    while cursor <= final_ms:
        response = session.get(BASE_URL, params={"symbol": symbol, "interval": interval, "startTime": cursor, "endTime": final_ms, "limit": 1000}, timeout=30)
        response.raise_for_status(); page = response.json()
        if not page: break
        bars.extend(page); cursor = int(page[-1][0]) + 3_600_000
    dedup = {int(bar[0]): bar for bar in bars}
    rows = [{"timestamp": datetime.fromtimestamp(t / 1000, UTC).isoformat().replace("+00:00", "Z"), "open": str(b[1]), "high": str(b[2]), "low": str(b[3]), "close": str(b[4]), "volume": str(b[5])} for t, b in sorted(dedup.items())]
    gaps = validate(rows)
    raw = root / "data/raw" / f"{symbol}-{interval}.csv"; raw.parent.mkdir(parents=True, exist_ok=True)
    with raw.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    manifest = {"source": BASE_URL, "source_kind": "Binance Spot public market-data REST", "symbol": symbol, "timeframe": interval, "start": rows[0]["timestamp"], "end": rows[-1]["timestamp"], "rows": len(rows), "sha256": sha256(raw), "retrieved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"), "gaps": gaps, "complete_candles_only": True}
    target = root / "data/manifests" / f"{symbol}-{interval}.json"; target.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return manifest

def load(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as src: rows = list(csv.DictReader(src))
    validate(rows); return rows

def _months(start: str, end: datetime) -> list[tuple[int, int]]:
    current = datetime.fromisoformat(start).replace(tzinfo=UTC)
    last = (end.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)).replace(day=1)
    result = []
    while current <= last:
        result.append((current.year, current.month))
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    return result

def _archive_rows(session: requests.Session, kind: str, symbol: str, interval: str, year: int, month: int) -> list[list[str]]:
    stem = f"{symbol}-{interval}-{year}-{month:02d}" if kind != "fundingRate" else f"{symbol}-fundingRate-{year}-{month:02d}"
    url = ARCHIVE_URL.format(kind=kind, symbol=symbol, interval=interval, filename=stem)
    if kind == "fundingRate": url = url.replace(f"/{symbol}/{interval}/", f"/{symbol}/")
    response = session.get(url, timeout=60)
    if response.status_code == 404: return []
    response.raise_for_status()
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        names = archive.namelist()
        if len(names) != 1: raise ValueError(f"unexpected archive members: {url}")
        with archive.open(names[0]) as raw:
            return list(csv.reader(TextIOWrapper(raw, encoding="utf-8")))

def _validate_perp(rows: list[dict[str, str]]) -> list[str]:
    gaps = validate(rows)
    for i, row in enumerate(rows, 1):
        try:
            values = [float(row[field]) for field in PERP_FIELDS[5:]]
        except (KeyError, ValueError) as exc: raise ValueError(f"invalid perp row {i}") from exc
        if not all(math.isfinite(value) for value in values) or min(values[:2]) < 0 or row["trade_count"] == "":
            raise ValueError(f"invalid perp economics row {i}")
        if float(row["taker_buy_quote_volume"]) > float(row["quote_volume"]) + 1e-6:
            raise ValueError(f"taker volume exceeds total at row {i}")
    return gaps

def fetch_perp(symbol: str, start: str, root: Path, end: datetime | None = None) -> dict:
    """Fetch only completed archive months; archive rows are the durable raw source."""
    now = end or datetime.now(UTC)
    months = _months(start, now)
    session = requests.Session(); klines: dict[int, list[str]] = {}; premiums: dict[int, list[str]] = {}; funding: list[dict[str, str]] = []
    for year, month in months:
        for row in _archive_rows(session, "klines", symbol, "1h", year, month):
            if row and row[0].isdigit(): klines[int(row[0])] = row
        for row in _archive_rows(session, "premiumIndexKlines", symbol, "1h", year, month):
            if row and row[0].isdigit(): premiums[int(row[0])] = row
        for row in _archive_rows(session, "fundingRate", symbol, "1h", year, month):
            if row and row[0].isdigit(): funding.append({"timestamp": datetime.fromtimestamp(int(row[0]) / 1000, UTC).isoformat().replace("+00:00", "Z"), "funding_interval_hours": row[1], "funding_rate": row[2]})
    rows = []
    for stamp, bar in sorted(klines.items()):
        premium = premiums.get(stamp)
        if premium is None: continue
        rows.append({"timestamp": datetime.fromtimestamp(stamp / 1000, UTC).isoformat().replace("+00:00", "Z"), "open": bar[1], "high": bar[2], "low": bar[3], "close": bar[4], "volume": bar[5], "quote_volume": bar[7], "trade_count": bar[8], "taker_buy_base_volume": bar[9], "taker_buy_quote_volume": bar[10], "premium": premium[4]})
    gaps = _validate_perp(rows)
    funding.sort(key=lambda row: row["timestamp"])
    if len({row["timestamp"] for row in funding}) != len(funding): raise ValueError("duplicate funding events")
    for row in funding:
        if not math.isfinite(float(row["funding_rate"])) or abs(float(row["funding_rate"])) > 1: raise ValueError("funding rate out of range")
    raw = root / "data/raw" / f"{symbol}-perp-1h.csv"; raw.parent.mkdir(parents=True, exist_ok=True)
    with raw.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=PERP_FIELDS); writer.writeheader(); writer.writerows(rows)
    funding_path = root / "data/raw" / f"{symbol}-funding.csv"
    with funding_path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=FUNDING_FIELDS); writer.writeheader(); writer.writerows(funding)
    manifest = {"source": "https://data.binance.vision/data/futures/um/monthly", "market": "USD-M perpetual", "symbol": symbol, "data_type": ["klines", "premiumIndexKlines", "fundingRate"], "timeframe": "1h", "start": rows[0]["timestamp"], "end": rows[-1]["timestamp"], "rows": len(rows), "sha256": {"perp": sha256(raw), "funding": sha256(funding_path)}, "retrieved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"), "gaps": gaps, "funding_events": len(funding), "complete_archive_months_only": True}
    (root / "data/manifests" / f"{symbol}-perp-1h.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return manifest

def load_perp(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as src: rows = list(csv.DictReader(src))
    _validate_perp(rows); return rows

def load_funding(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as src: rows = list(csv.DictReader(src))
    if not rows or len({row["timestamp"] for row in rows}) != len(rows): raise ValueError("funding rows missing or duplicate")
    return rows

def fetch_funding(symbol: str, start: str, root: Path, end: datetime | None = None) -> dict:
    session = requests.Session(); events = []
    for year, month in _months(start, end or datetime.now(UTC)):
        for row in _archive_rows(session, "fundingRate", symbol, "1h", year, month):
            if row and row[0].isdigit(): events.append({"timestamp": datetime.fromtimestamp(int(row[0]) / 1000, UTC).isoformat().replace("+00:00", "Z"), "funding_interval_hours": row[1], "funding_rate": row[2]})
    events.sort(key=lambda row: row["timestamp"])
    if not events or len({row["timestamp"] for row in events}) != len(events): raise ValueError("funding history unavailable or duplicate")
    target = root / "data/raw" / f"{symbol}-funding.csv"
    with target.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=FUNDING_FIELDS); writer.writeheader(); writer.writerows(events)
    result = {"symbol": symbol, "rows": len(events), "sha256": sha256(target), "start": events[0]["timestamp"], "end": events[-1]["timestamp"], "source": "Binance public-data fundingRate archive"}
    manifest_path = root / "data/manifests" / f"{symbol}-perp-1h.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text()); manifest["funding_events"] = result["rows"]; manifest["sha256"]["funding"] = result["sha256"]; manifest["funding_source"] = result["source"]
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return result
