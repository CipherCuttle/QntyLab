"""Deterministic artificial fixtures for Breadth V2 runner/ledger integration
tests.  Nothing here touches real market data; every price and funding value
is a closed-form deterministic function of its position in the series.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import UTC, datetime, timedelta

from qntylab.breadth_v2_input_bundle import PANEL_ORDER


def _stamp(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(UTC)


def hourly_range(start: str, end: str) -> list[str]:
    a, b = _parse(start), _parse(end)
    n = int((b - a).total_seconds() // 3600)
    return [_stamp(a + timedelta(hours=i)) for i in range(n + 1)]


def _random_walk_prices(seed: int, n: int) -> list[float]:
    """Deterministic (seeded) geometric random walk -- never a smooth, exactly
    periodic pattern.  A momentum/reversal/breakout rule run against a smooth
    periodic price would extract a perfectly exploitable edge every cycle and
    compound to an unrealistic magnitude over an 8,760-hour synthetic period;
    a seeded random walk with a modest hourly volatility avoids that while
    remaining fully reproducible for a given seed."""
    rng = random.Random(f"breadth-v2-fixture-{seed}")
    log_price = math.log(100.0 + 3.0 * (seed % 7))
    prices = []
    for _ in range(n):
        log_price += rng.gauss(0.0, 0.004)
        prices.append(math.exp(log_price))
    return prices


def synthetic_price_source(symbol: str, source_start: str, source_end: str, seed: int) -> dict:
    stamps = hourly_range(source_start, source_end)
    closes = _random_walk_prices(seed, len(stamps))
    rows = [
        {"timestamp": t, "open": "1", "high": "2", "low": "0.5", "close": repr(round(closes[i], 8)), "volume": "1"}
        for i, t in enumerate(stamps)
    ]
    csv = "timestamp,open,high,low,close,volume\n" + "".join(",".join(row[k] for k in ("timestamp", "open", "high", "low", "close", "volume")) + "\n" for row in rows)
    csv_bytes = csv.encode()
    manifest = {
        "normalized_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "gap_count": 0,
        "materializer_contract_version": "BINANCE_USD_M_PERPETUAL_1H_MATERIALIZER_V0",
        "aggregate_source_receipt_digest": hashlib.sha256(f"price-receipt-{symbol}".encode()).hexdigest(),
    }
    return {"manifest": manifest, "normalized_csv": csv}


def synthetic_funding_source(symbol: str, source_start: str, source_end: str, seed: int) -> dict:
    start, end = _parse(source_start), _parse(source_end)
    events = []
    t = start.replace(hour=(start.hour // 8) * 8, minute=0, second=0, microsecond=0)
    if t < start:
        t += timedelta(hours=8)
    index = 0
    while t <= end:
        rate = 0.0001 * math.sin(seed * 0.19 + index * 0.7)
        events.append({
            "symbol": symbol,
            "funding_time_ms": int(t.timestamp() * 1000),
            "funding_time_utc": _stamp(t),
            "funding_rate": round(rate, 8),
        })
        t += timedelta(hours=8)
        index += 1
    jsonl = "".join(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n" for event in events)
    jsonl_bytes = jsonl.encode()
    manifest = {
        "normalized_sha256": hashlib.sha256(jsonl_bytes).hexdigest(),
        "coverage_status": "COMPLETE",
        "materializer_contract_version": "BINANCE_USDM_FUNDING_SETTLEMENT_MATERIALIZER_V0",
        "archive_aggregate_source_receipt_digest": hashlib.sha256(f"funding-archive-{symbol}".encode()).hexdigest(),
        "rest_coverage_witness_digest": hashlib.sha256(f"funding-rest-{symbol}".encode()).hexdigest(),
        "coverage_reconciliation_digest": hashlib.sha256(f"funding-reconciliation-{symbol}".encode()).hexdigest(),
    }
    return {"manifest": manifest, "normalized_jsonl": jsonl}


def build_sources(
    symbols: list[str], evaluation_start: str, evaluation_end: str, *,
    required_price_closes: int, required_funding_signal_events: int = 0, seed_offset: int = 0,
) -> tuple[dict, dict]:
    price_start = _stamp(_parse(evaluation_start) - timedelta(hours=required_price_closes))
    price_end = _stamp(_parse(evaluation_end) - timedelta(hours=1))
    funding_warmup_hours = max(required_funding_signal_events * 8 + 8, 8)
    funding_start = _stamp(_parse(evaluation_start) - timedelta(hours=funding_warmup_hours))
    funding_end = evaluation_end
    price_sources, funding_sources = {}, {}
    for offset, symbol in enumerate(symbols):
        seed = seed_offset + offset + 1
        price_sources[symbol] = synthetic_price_source(symbol, price_start, price_end, seed)
        funding_sources[symbol] = synthetic_funding_source(symbol, funding_start, funding_end, seed)
    return price_sources, funding_sources


FROZEN_PANEL_ORDER = PANEL_ORDER
