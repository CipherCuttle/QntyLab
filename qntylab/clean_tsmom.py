"""Frozen, causal, QntyLab-native clean TSMOM V1/V2 experiment.

This module deliberately does not import Qnty, quantbot, or historical runners.
The pure functions are the contract surface used by the offline and hostile tests.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, math, os, shutil, tempfile, urllib.request, zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "LINKUSDT", "DOTUSDT", "BNBUSDT", "ADAUSDT", "MATICUSDT", "SOLUSDT", "AVAXUSDT"]
V1_ID = "qntylab_clean_tsmom_v1_equal_weight_v0"
V2_ID = "qntylab_clean_tsmom_v2_inverse_vol_v0"
EVAL = {"selection_date": "2026-04-22", "warmup_start": "2026-03-01T00:00:00Z", "start": "2026-04-23T00:00:00Z", "end": "2026-08-01T00:00:00Z", "tail_start": "2026-06-19T00:00:00Z", "tail_end": "2026-08-01T00:00:00Z"}
COSTS = {"base": {"fee_bps": 5.0, "slippage_bps": 2.5, "rate": 0.00075}, "stress": {"fee_bps": 10.0, "slippage_bps": 5.0, "rate": 0.0015}}
INITIAL_CAPITAL = 10000.0

def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

def digest(value: Any) -> str: return hashlib.sha256(canonical(value)).hexdigest()

def _dt(s: str) -> datetime: return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)

def validate_spec(value: dict[str, Any], expected_keys: set[str]) -> None:
    if set(value) != expected_keys: raise ValueError(f"spec keys mismatch: {sorted(set(value) ^ expected_keys)}")
    raw = canonical(value)
    if b"NaN" in raw or b"Infinity" in raw: raise ValueError("non-finite JSON")
    if "universe" in value and value["universe"] != SYMBOLS: raise ValueError("universe mismatch")
    if "evaluation" in value and value["evaluation"] != EVAL: raise ValueError("evaluation dates mismatch")

def aggregate_8h(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows: raise ValueError("empty hourly panel")
    rows = sorted(rows, key=lambda r: int(r["timestamp"]))
    seen = set(); out = []
    for r in rows:
        ts = int(r["timestamp"]); when = datetime.fromtimestamp(ts / 1000, UTC)
        if ts in seen or when.minute or when.second or when.microsecond: raise ValueError("duplicate/off-grid hour")
        seen.add(ts)
    for i in range(0, len(rows), 8):
        group = rows[i:i + 8]
        if len(group) != 8: raise ValueError("incomplete 8h bucket")
        stamps = [int(x["timestamp"]) for x in group]
        if stamps != list(range(stamps[0], stamps[0] + 8 * 3600000, 3600000)): raise ValueError("hourly gap")
        start = datetime.fromtimestamp(stamps[0] / 1000, UTC)
        if start.hour % 8: raise ValueError("8h bucket off-grid")
        vals = [[float(row[k]) for row in group] for k in ("open", "high", "low", "close", "volume")]
        if any(not math.isfinite(v) for col in vals for v in col) or any(v <= 0 for col in vals[:4] for v in col) or any(v < 0 for v in vals[4]): raise ValueError("invalid OHLCV")
        o, h, l, c, vol = vals
        if h[0] < max(o[0], l[0]) or l[0] > min(o[0], h[0]) or h[-1] < max(c[-1], l[-1]) or l[-1] > min(c[-1], h[-1]): raise ValueError("inconsistent OHLC")
        out.append({"timestamp": stamps[0], "open": o[0], "high": max(h), "low": min(l), "close": c[-1], "volume": sum(vol)})
    return out

def signal(close: np.ndarray, lookback: int = 20) -> np.ndarray:
    if lookback != 20: raise ValueError("lookback is frozen at 20")
    out = np.zeros(len(close), dtype=int)
    for t in range(lookback, len(close)):
        out[t] = int(math.log(close[t] / close[t-lookback]) > 0)
    return out

def weights_v1(closes: np.ndarray) -> np.ndarray:
    if closes.ndim != 2 or closes.shape[1] != 10: raise ValueError("expected [bars,10] closes")
    sig = np.column_stack([signal(closes[:, i]) for i in range(10)])
    return sig / 10.0

def weights_v2(closes: np.ndarray) -> tuple[np.ndarray, int]:
    if closes.ndim != 2 or closes.shape[1] != 10: raise ValueError("expected [bars,10] closes")
    sig = np.column_stack([signal(closes[:, i]) for i in range(10)])
    lr = np.log(closes[1:] / closes[:-1]); out = np.zeros_like(closes, dtype=float); heat_count = 0
    for t in range(len(closes)):
        if t < 90: continue
        vol = np.std(lr[t-89:t+1], axis=0, ddof=0); eligible = (sig[t] == 1) & np.isfinite(vol) & (vol > 0)
        idx = np.flatnonzero(eligible)
        if len(idx):
            raw = 1.0 / vol[idx]; target = len(idx) / 10.0; row = target * raw / raw.sum()
            out[t, idx] = row
            if out[t].sum() > 1.0 + 1e-15: out[t] *= 1.0 / out[t].sum(); heat_count += 1
    return out, heat_count

def _funding_lookup(events: list[dict[str, Any]], boundaries: set[int]) -> dict[tuple[str, int], float]:
    out = {}
    for e in events:
        key = (str(e["symbol"]), int(e["timestamp"]))
        if key in out: raise ValueError("duplicate funding event")
        if key[1] not in boundaries: raise ValueError("funding event off frozen boundary")
        out[key] = float(e["funding_rate"])
    return out

def run_equity(closes: np.ndarray, weights: np.ndarray, timestamps: list[int], funding: list[dict[str, Any]], start: str, end: str, cost_rate: float) -> dict[str, Any]:
    if len(closes) != len(weights) or len(timestamps) != len(closes): raise ValueError("alignment mismatch")
    begin, finish = int(_dt(start).timestamp() * 1000), int(_dt(end).timestamp() * 1000)
    ix = [i for i, ts in enumerate(timestamps) if begin <= ts < finish]
    if not ix: raise ValueError("empty evaluation")
    prev = np.zeros(10); equity = INITIAL_CAPITAL; rows = []; funding_map = _funding_lookup(funding, set(timestamps))
    fee = turnover = funding_paid = funding_received = 0.0; episodes = 0
    for pos, i in enumerate(ix):
        if i == 0: continue
        new = weights[i-1] if i > 0 else np.zeros(10)
        price = closes[i] / closes[i-1] - 1.0
        held = prev.copy(); pr = float(np.dot(held, price)); fr = 0.0
        for j, symbol in enumerate(SYMBOLS):
            rate = funding_map.get((symbol, timestamps[i]), 0.0); fr += -held[j] * rate
            if -held[j] * rate > 0: funding_received += -held[j] * rate
            else: funding_paid += held[j] * rate
        turn = float(np.abs(new - held).sum()); cost = turn * cost_rate; equity *= 1 + pr + fr - cost
        fee += turn * cost_rate * (2 / 3); turnover += turn
        episodes += int(np.count_nonzero((held == 0) & (new > 0))); prev = new
        rows.append({"timestamp": timestamps[i], "price_return": pr, "funding_return": fr, "turnover": turn, "cost": cost, "equity": equity})
    final_turn = float(np.abs(prev).sum()); final_cost = final_turn * cost_rate; equity_liq = equity * (1 - final_cost)
    eq = np.array([r["equity"] for r in rows]); rets = np.array([r["price_return"] + r["funding_return"] - r["cost"] for r in rows]); peak = np.maximum.accumulate(np.r_[INITIAL_CAPITAL, eq])[1:]; dd = eq / peak - 1
    sharpe = float(rets.mean() / rets.std(ddof=0) * math.sqrt(365 * 3)) if len(rets) and rets.std(ddof=0) else 0.0
    return {"valid_8h_bars": len(rows), "initial_equity": INITIAL_CAPITAL, "final_marked_equity": equity, "final_liquidation_adjusted_equity": equity_liq, "gross_return": float(np.prod(1 + np.array([r["price_return"] for r in rows])) - 1) if rows else 0.0, "net_return": equity_liq / INITIAL_CAPITAL - 1, "sharpe": sharpe, "maximum_drawdown": float(dd.min()) if len(dd) else 0.0, "turnover": turnover + final_turn, "fee_cost": fee, "slippage_cost": fee / 2, "funding_paid": funding_paid * INITIAL_CAPITAL, "funding_received": funding_received * INITIAL_CAPITAL, "net_funding": (funding_received - funding_paid) * INITIAL_CAPITAL, "average_gross_exposure": float(np.mean([np.abs(weights[i-1]).sum() for i in ix if i > 0])) if len(ix) > 1 else 0.0, "maximum_gross_exposure": float(np.max(np.abs(weights).sum(axis=1))), "position_episode_count": episodes, "equity_rows": rows, "weights": weights.tolist(), "timestamps": timestamps}

def _json(path: Path, value: Any) -> None: path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(canonical(value) + b"\n")

def verify_specs(root: Path) -> None:
    for name in ("source_contract.json", "v1_equal_weight.json", "v2_inverse_vol.json", "evaluation_v0.json"):
        value = json.loads((root / name).read_text()); validate_spec(value, set(value))
        side = root / name.replace(".json", ".sha256"); expected = side.read_text().split()[0]
        if expected != hashlib.sha256((root / name).read_bytes()).hexdigest(): raise ValueError(f"checksum mismatch: {name}")

def main() -> None:
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="command", required=True); s = sub.add_parser("verify-spec"); s.add_argument("root", type=Path)
    a = p.parse_args()
    if a.command == "verify-spec": verify_specs(a.root); print("SPEC_VERIFY_PASS")

if __name__ == "__main__": main()
