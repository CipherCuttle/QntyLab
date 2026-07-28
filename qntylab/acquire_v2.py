"""Consume the frozen S3 inventory; intentionally never constructs source URLs by month."""
from __future__ import annotations
import csv, hashlib, json, os, time, zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from io import BytesIO, TextIOWrapper
from pathlib import Path
import requests
from .data import load_perp_daily, sha256, validate

BASE = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/"

def _get(session: requests.Session, key: str) -> bytes:
    for attempt in range(3):
        response = session.get(BASE + key, timeout=(10, 90))
        if response.status_code in {404, 403}: raise ValueError(f"permanent HTTP {response.status_code}: {key}")
        if response.ok: return response.content
        if response.status_code < 500: response.raise_for_status()
        time.sleep(.5 * (attempt + 1))
    response.raise_for_status(); raise AssertionError("unreachable")

def _one(symbol: str, objects: list[dict], root: Path) -> dict:
    target = root / "data/raw" / f"{symbol}-perp-1d.csv"; receipt = root / "data/archive/panels" / f"{symbol}.json"
    if target.exists() and receipt.exists():
        rows = load_perp_daily(target); data = json.loads(receipt.read_text())
        if data.get("panel_sha256") == sha256(target) and data.get("object_count") == len(objects): return {"symbol": symbol, "state": "REUSED", **data}
    session = requests.Session(); rows = {}; sources = []
    for item in objects:
        payload = _get(session, item["zip_key"]); digest = hashlib.sha256(payload).hexdigest()
        if item.get("checksum_key"):
            expected = _get(session, item["checksum_key"]).decode().strip().split()[0]
            if digest != expected: raise ValueError(f"checksum mismatch: {item['zip_key']}")
        else: expected = None
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            if len(archive.namelist()) != 1: raise ValueError(f"unexpected archive members: {item['zip_key']}")
            with archive.open(archive.namelist()[0]) as stream:
                for row in csv.reader(TextIOWrapper(stream, encoding="utf-8")):
                    if row and row[0].isdigit(): rows[int(row[0])] = row
        sources.append({"key": item["zip_key"], "checksum_key": item.get("checksum_key"), "sha256": digest})
    normalized = [{"timestamp": datetime.fromtimestamp(stamp / 1000, UTC).isoformat().replace("+00:00", "Z"), "open": row[1], "high": row[2], "low": row[3], "close": row[4], "volume": row[5], "quote_volume": row[7], "trade_count": row[8], "taker_buy_base_volume": row[9], "taker_buy_quote_volume": row[10]} for stamp,row in sorted(rows.items())]
    if not normalized: raise ValueError("no usable observations")
    gaps = validate(normalized, interval_hours=24)
    target.parent.mkdir(parents=True, exist_ok=True); temporary = target.with_suffix('.csv.tmp')
    with temporary.open('w', newline='', encoding='utf-8') as out:
        writer = csv.DictWriter(out, fieldnames=tuple(normalized[0])); writer.writeheader(); writer.writerows(normalized)
    os.replace(temporary, target)
    data = {"panel_sha256": sha256(target), "object_count": len(objects), "source_objects": sources, "rows": len(normalized), "start": normalized[0]["timestamp"], "end": normalized[-1]["timestamp"], "gaps": gaps}
    receipt.parent.mkdir(parents=True, exist_ok=True); receipt.write_text(json.dumps(data, sort_keys=True, indent=2) + '\n')
    return {"symbol": symbol, "state": "VALID_PANEL", **data}

def consume(inventory_path: Path, root: Path, workers: int = 12) -> list[dict]:
    inventory = json.loads(inventory_path.read_text()); grouped = {}
    for item in inventory["objects"]: grouped.setdefault(item["symbol"], []).append(item)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda pair: _one(pair[0], pair[1], root), sorted(grouped.items())))
