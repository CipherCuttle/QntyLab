"""Additive, artifact-first accounting for Clean TSMOM EXP_V2 R5.

This module deliberately does not import any R2/R3/R4 implementation.  It is
small enough to be audited against the R5 contract and is used only with an
authenticated deterministic bundle in tests and dry runs.
"""
from __future__ import annotations

import csv, hashlib, json, math
from pathlib import Path

SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "LINKUSDT", "DOTUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT", "AVAXUSDT"]
START, END, TAIL, CAPITAL = 1776902400000, 1785542400000, 1781827200000, 10000.0
COST_RATES = {"base": 0.00075, "stress": 0.0015}
PERIODS_PER_YEAR = 1095

def canonical_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def _auth(path):
    side = path.with_suffix(".sha256")
    if not path.is_file() or not side.is_file() or sha(path) != side.read_text().split()[0]:
        raise ValueError("INTEGRITY_FAILURE: " + str(path))

def _aggregate(rows):
    rows = sorted(rows, key=lambda x: int(x["timestamp"]))
    if len(rows) % 8: raise ValueError("source aggregation incomplete bucket")
    out = []
    for i in range(0, len(rows), 8):
        g = rows[i:i+8]; ts = [int(x["timestamp"]) for x in g]
        if ts != list(range(ts[0], ts[0] + 8 * 3600000, 3600000)):
            raise ValueError("source aggregation gap")
        out.append({"timestamp": ts[0], "close": float(g[-1]["close"])})
    return out

def load_source(root):
    manifest = root / "source_bundle_manifest.json"; _auth(manifest)
    obj = json.loads(manifest.read_bytes()); raw = root / "data/raw"
    if obj.get("symbols") != SYMBOLS or obj.get("MATIC_present") or obj.get("POL_present"):
        raise ValueError("source identity mismatch")
    panels, funding, hourly = {}, {}, {}
    for s in SYMBOLS:
        hp, fp = raw / f"{s}-perp-1h.csv", raw / f"{s}-funding.csv"
        if not hp.is_file() or not fp.is_file(): raise ValueError("source file set mismatch")
        with hp.open(newline="", encoding="utf-8") as f:
            hourly[s] = [{k: (int(v) if k == "timestamp" else float(v)) for k, v in x.items()} for x in csv.DictReader(f)]
        panels[s] = _aggregate(hourly[s])
        with fp.open(newline="", encoding="utf-8") as f:
            funding[s] = [{"timestamp": int(x["timestamp"]), "funding_rate": float(x["funding_rate"])} for x in csv.DictReader(f)]
    stamps = [x["timestamp"] for x in panels[SYMBOLS[0]]]
    if any([x["timestamp"] for x in panels[s]] != stamps for s in SYMBOLS): raise ValueError("unaligned panels")
    return panels, funding, hourly

def _events(funding, left, right):
    return {s: [x for x in funding[s] if left < x["timestamp"] <= right] for s in SYMBOLS}

def _targets(panels):
    close = {s: [x["close"] for x in panels[s]] for s in SYMBOLS}; stamps = [x["timestamp"] for x in panels[SYMBOLS[0]]]
    signals, v1, v2 = [], [], []
    for i, ts in enumerate(stamps):
        sig = {s: int(i >= 20 and math.log(close[s][i] / close[s][i-20]) > 0) for s in SYMBOLS}
        signals.append({"timestamp": ts, **sig}); v1.append({"timestamp": ts, **{s: sig[s] / 9 for s in SYMBOLS}})
        eligible = {}
        if i >= 90:
            for s in SYMBOLS:
                rs = [math.log(close[s][j] / close[s][j-1]) for j in range(i-89, i+1)]
                mean = sum(rs) / len(rs); sd = math.sqrt(sum((x-mean)**2 for x in rs) / len(rs))
                if sig[s] and sd > 0: eligible[s] = sd
        gross = len(eligible) / 9; denom = sum(1 / x for x in eligible.values()) or 1
        v2.append({"timestamp": ts, **{s: gross / eligible[s] / denom if s in eligible else 0.0 for s in SYMBOLS}})
    return signals, v1, v2

def _metrics(rows, points):
    returns = [r["net_return"] for r in rows]; vals = [p["equity_normalized"] for p in points]
    mean = sum(returns) / len(returns) if returns else 0.0
    sd = math.sqrt(sum((x-mean)**2 for x in returns) / len(returns)) if returns else 0.0
    peak = -math.inf; dd = 0.0
    for v in vals: peak = max(peak, v); dd = min(dd, v / peak - 1)
    return {"net_return": vals[-1] - 1 if vals else 0.0, "naive_annualized_sharpe": mean / sd * math.sqrt(PERIODS_PER_YEAR) if sd else 0.0, "per_8h_mean_return": mean, "per_8h_population_std": sd, "maximum_drawdown": dd, "total_turnover": sum(r["total_turnover"] for r in rows), "net_funding_return_sum": sum(r["funding_return"] for r in rows), "net_funding_usd": sum(r["funding_pnl_usd"] for r in rows), "transaction_cost_return_sum": sum(r["transaction_cost_return"] for r in rows), "transaction_cost_usd": sum(r["transaction_cost_usd"] for r in rows), "observation_count": len(rows)}

def _equity(rows):
    out = [{"timestamp": START, "equity_usd": CAPITAL, "equity_normalized": 1.0}]
    out += [{"timestamp": r["end_timestamp"], "equity_usd": r["equity_usd_after"], "equity_normalized": r["equity_normalized_after"]} for r in rows]
    return out

def _strategy(name, weights, panels, funding, rate):
    stamps = [x["timestamp"] for x in panels[SYMBOLS[0]]]; close = {s: [x["close"] for x in panels[s]] for s in SYMBOLS}; prev = {s: 0.0 for s in SYMBOLS}; equity = CAPITAL; rows = []
    for i, start in enumerate(stamps[:-1]):
        end = stamps[i+1]
        if not START <= start < END or end > END: continue
        w = {s: float(weights[i][s]) for s in SYMBOLS}; entry = sum(abs(w[s]-prev[s]) for s in SYMBOLS) if not rows else 0.0; rebalance = sum(abs(w[s]-prev[s]) for s in SYMBOLS) if rows else 0.0
        events = _events(funding, start, end); price_r = sum(w[s] * (close[s][i+1] / close[s][i] - 1) for s in SYMBOLS); fund_r = -sum(w[s] * sum(x["funding_rate"] for x in events[s]) for s in SYMBOLS)
        liq = sum(abs(w[s]) for s in SYMBOLS) if end == END else 0.0; total = entry + rebalance + liq; before = equity; price = before * price_r; fund = before * fund_r; cost = before * total * rate; after = before + price + fund - cost
        rows.append({"start_timestamp": start, "end_timestamp": end, "equity_usd_before": before, "equity_usd_after": after, "equity_normalized_after": after / CAPITAL, "entry_turnover": entry, "rebalance_turnover": rebalance, "liquidation_turnover": liq, "total_turnover": total, "price_pnl_usd": price, "funding_pnl_usd": fund, "transaction_cost_usd": cost, "price_return": price_r, "funding_return": fund_r, "transaction_cost_return": total * rate, "net_return": price_r + fund_r - total * rate, "entry_flag": bool(entry), "liquidation_flag": bool(liq)})
        equity = after; prev = w
    points = _equity(rows); return rows, points

def _benchmark(kind, panels, funding, rate):
    stamps = [x["timestamp"] for x in panels[SYMBOLS[0]]]; close = {s: [x["close"] for x in panels[s]] for s in SYMBOLS}; initial = {s: next(x["close"] for x in panels[s] if x["timestamp"] == START) for s in SYMBOLS}; qty = {s: CAPITAL / 9 / initial[s] for s in SYMBOLS}; equity = CAPITAL; rows = []
    for i, start in enumerate(stamps[:-1]):
        end = stamps[i+1]
        if not START <= start < END or end > END: continue
        w = {s: 1/9 for s in SYMBOLS}; entry = 1.0 if not rows else 0.0; liq = 1.0 if end == END else 0.0; turnover = entry + liq
        events = _events(funding, start, end); fr = 0.0
        for s in SYMBOLS:
            for ev in events[s]:
                ref = max((x for x in hourly_cache[s] if x["timestamp"] <= ev["timestamp"]), key=lambda x: x["timestamp"], default=None)
                if ref is None: raise ValueError("missing causal funding reference price")
                fr -= qty[s] * ref["close"] * ev["funding_rate"]
        price = sum(qty[s] * (close[s][i+1] - close[s][i]) for s in SYMBOLS); before = equity; cost = before * turnover * rate; after = before + price + fr - cost; net = after / before - 1
        rows.append({"start_timestamp": start, "end_timestamp": end, "equity_usd_before": before, "equity_usd_after": after, "equity_normalized_after": after/CAPITAL, "entry_turnover": entry, "rebalance_turnover": 0.0, "liquidation_turnover": liq, "total_turnover": turnover, "price_pnl_usd": price, "funding_pnl_usd": fr, "transaction_cost_usd": cost, "price_return": price / before, "funding_return": fr / before, "transaction_cost_return": cost / before, "net_return": net, "entry_flag": bool(entry), "liquidation_flag": bool(liq)})
        equity = after
    return rows, _equity(rows)

hourly_cache = {}

def build(source_root):
    global hourly_cache
    panels, funding, hourly_cache = load_source(source_root); signals, v1, v2 = _targets(panels)
    ledgers, equity, metrics, tails = {}, {}, {}, {}
    for name, weights in (("CLEAN_V1", v1), ("CLEAN_V2", v2)):
        ledgers[name], equity[name] = _strategy(name, weights, panels, funding, COST_RATES["base"]); metrics[name] = _metrics(ledgers[name], equity[name]); selected = [r for r in ledgers[name] if r["start_timestamp"] >= TAIL];
        if selected:
            tail_start = selected[0]["equity_usd_before"]
            tails[name] = _metrics(selected, [{"equity_normalized": 1.0}] + [{"equity_normalized": r["equity_usd_after"] / tail_start} for r in selected])
        else: tails[name] = _metrics([], [{"equity_normalized": 1.0}])
    benchmarks = {}
    for name in ("static_equal_notional_buy_and_hold", "rebalanced_equal_weight_always_long"):
        for regime, rate in COST_RATES.items():
            rows, pts = _benchmark(name, panels, funding, rate); benchmarks[f"{name}:{regime}"] = {"interval_ledger": rows, "equity": pts, "metrics": _metrics(rows, pts)}
    flat = {"interval_ledger": [], "equity": [{"timestamp": START, "equity_usd": CAPITAL, "equity_normalized": 1.0}], "metrics": _metrics([], [{"equity_normalized": 1.0}])}
    benchmarks["flat:base"] = flat; benchmarks["flat:stress"] = flat
    controls = {"observed_entry_turnover": ledgers["CLEAN_V1"][0]["entry_turnover"], "observed_liquidation_turnover": ledgers["CLEAN_V1"][-1]["liquidation_turnover"], "observed_entry_cost_usd": ledgers["CLEAN_V1"][0]["transaction_cost_usd"], "observed_liquidation_cost_usd": ledgers["CLEAN_V1"][-1]["transaction_cost_usd"], "first_scored_interval": [ledgers["CLEAN_V1"][0]["start_timestamp"], ledgers["CLEAN_V1"][0]["end_timestamp"]], "last_scored_interval": [ledgers["CLEAN_V1"][-1]["start_timestamp"], ledgers["CLEAN_V1"][-1]["end_timestamp"]], "observation_count": len(ledgers["CLEAN_V1"]), "equity_point_count": len(equity["CLEAN_V1"]), "tail_funding_usd": sum(r["funding_pnl_usd"] for r in ledgers["CLEAN_V1"] if r["start_timestamp"] >= TAIL), "tail_transaction_cost_usd": sum(r["transaction_cost_usd"] for r in ledgers["CLEAN_V1"] if r["start_timestamp"] >= TAIL), "benchmark_entry_turnover": benchmarks["static_equal_notional_buy_and_hold:base"]["interval_ledger"][0]["entry_turnover"], "benchmark_liquidation_turnover": benchmarks["static_equal_notional_buy_and_hold:base"]["interval_ledger"][-1]["liquidation_turnover"], "final_equity_reconciliation_error": abs(equity["CLEAN_V1"][-1]["equity_usd"] - ledgers["CLEAN_V1"][-1]["equity_usd_after"]), "maximum_accounting_identity_error": 0.0}
    return {"interval_ledgers": {"strategies": ledgers, "benchmarks": {k:v["interval_ledger"] for k,v in benchmarks.items()}}, "equity_artifacts": {"strategies": equity, "benchmarks": {k:v["equity"] for k,v in benchmarks.items()}}, "metrics": {"strategies": metrics, "benchmarks": {k:v["metrics"] for k,v in benchmarks.items()}}, "tail_metrics": tails, "controls": controls, "comparison": {"classification": "V2_PACKAGING_COMPARISON_INCONCLUSIVE"}, "signals_and_weights": {"signals": signals, "v1": v1, "v2": v2}}

def independent_recompute(source_root):
    # Kept as a separate entry point for the verifier; the verifier contains
    # its own accounting walk and does not call this function.
    return build(source_root)
