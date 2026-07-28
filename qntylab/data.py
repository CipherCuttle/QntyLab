from __future__ import annotations

import csv, hashlib, json, math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests

BASE_URL = "https://data-api.binance.vision/api/v3/klines"
FIELDS = ("timestamp", "open", "high", "low", "close", "volume")

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
