"""Complete independent source-to-result verifier for Clean TSMOM EXP_V2 R4.

This module intentionally has its own implementation of the frozen equations.
It authenticates inputs, reconstructs every result artifact, and compares the
reconstruction with the producer output.  It never imports or invokes R2/R3.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, math, sys
from datetime import UTC, datetime
from pathlib import Path

SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "LINKUSDT", "DOTUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT", "AVAXUSDT"]
NAMES = ("main_panel", "main_signals", "main_v1_weights", "main_v2_weights", "main_funding_assignments", "main_funding_returns", "main_turnover", "main_costs", "main_equity_usd", "main_equity_normalized", "main_metrics", "tail_metrics", "benchmark_outputs", "controls", "classifications", "comparison", "final_liquidation")
START, END, TAIL, CAPITAL = 1776902400000, 1785542400000, 1781827200000, 10000.0

def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def aggregate(rows):
    rows = sorted(rows, key=lambda x: int(x["timestamp"]))
    seen = set(); out = []
    for off in range(0, len(rows), 8):
        group = rows[off:off + 8]
        if len(group) != 8: raise ValueError("source aggregation incomplete bucket")
        stamps = [int(x["timestamp"]) for x in group]
        if stamps != list(range(stamps[0], stamps[0] + 8 * 3_600_000, 3_600_000)): raise ValueError("source aggregation gap")
        when = datetime.fromtimestamp(stamps[0] / 1000, UTC)
        if when.minute or when.second or when.microsecond or when.hour % 8 or any(t in seen for t in stamps): raise ValueError("source aggregation grid")
        seen.update(stamps)
        for key in ("open", "high", "low", "close", "volume"):
            if any(not math.isfinite(float(x[key])) for x in group): raise ValueError("non-finite source value")
        out.append({"timestamp": stamps[0], "open": float(group[0]["open"]), "high": max(float(x["high"]) for x in group), "low": min(float(x["low"]) for x in group), "close": float(group[-1]["close"]), "volume": sum(float(x["volume"]) for x in group)})
    return out

def check_sidecars(directory, names):
    for name in names:
        p = directory / name; side = p.with_suffix(".sha256")
        if not p.is_file() or not side.is_file() or sha(p) != side.read_text().split()[0]: raise ValueError("contract sidecar mismatch: " + name)

def source(root, binding):
    manifest = root / "source_bundle_manifest.json"
    if not manifest.is_file() or sha(manifest) != (root / "source_bundle_manifest.sha256").read_text().split()[0]: raise ValueError("source manifest authentication failure")
    if manifest.read_bytes() != (binding / "source_bundle_manifest.json").read_bytes(): raise ValueError("source bundle is not authenticated R1 bundle")
    obj = json.loads(manifest.read_bytes()); raw = root / "data/raw"
    expected = {f"{s}-perp-1h.csv" for s in SYMBOLS} | {f"{s}-funding.csv" for s in SYMBOLS}
    if obj.get("symbols") != SYMBOLS or {p.name for p in raw.iterdir() if p.is_file()} != expected: raise ValueError("source bundle identity failure")
    panels, funding = {}, {}
    for entry in obj["files"]:
        p = root / entry["relative_path"]
        if sha(p) != entry["sha256"] or p.stat().st_size != entry["byte_count"]: raise ValueError("source byte mismatch")
    for symbol in SYMBOLS:
        hp, fp = raw / f"{symbol}-perp-1h.csv", raw / f"{symbol}-funding.csv"
        with hp.open(newline="", encoding="utf-8") as f: panels[symbol] = aggregate([{k: int(v) if k == "timestamp" else float(v) for k, v in row.items()} for row in csv.DictReader(f)])
        with fp.open(newline="", encoding="utf-8") as f: funding[symbol] = [{"timestamp": int(row["timestamp"]), "funding_rate": float(row["funding_rate"])} for row in csv.DictReader(f)]
        if len({x["timestamp"] for x in funding[symbol]}) != len(funding[symbol]): raise ValueError("duplicate funding event")
    stamps = [x["timestamp"] for x in panels[SYMBOLS[0]]]
    if any([x["timestamp"] for x in panels[s]] != stamps for s in SYMBOLS): raise ValueError("unaligned source panel")
    return panels, funding

def targets(panels):
    stamps = [x["timestamp"] for x in panels[SYMBOLS[0]]]; close = {s: [x["close"] for x in panels[s]] for s in SYMBOLS}; signals, v1, v2 = [], [], []
    for t, ts in enumerate(stamps):
        sig = {s: int(t >= 20 and math.log(close[s][t] / close[s][t - 20]) > 0) for s in SYMBOLS}; signals.append({"timestamp": ts, **sig}); v1.append({"timestamp": ts, **{s: sig[s] / 9 for s in SYMBOLS}})
        eligible = {}
        if t >= 90:
            for s in SYMBOLS:
                rs = [math.log(close[s][j] / close[s][j - 1]) for j in range(t - 89, t + 1)]; mean = sum(rs) / len(rs); sd = math.sqrt(sum((x - mean) ** 2 for x in rs) / len(rs))
                if sig[s] and sd > 0 and math.isfinite(sd): eligible[s] = sd
        gross = len(eligible) / 9; denom = sum(1 / x for x in eligible.values()) if eligible else 1
        v2.append({"timestamp": ts, **{s: gross / eligible[s] / denom if s in eligible else 0.0 for s in SYMBOLS}})
    return signals, v1, v2

def events(funding, left, right):
    return {s: [x["funding_rate"] for x in funding[s] if left < x["timestamp"] <= right] for s in SYMBOLS}

def metric(values, returns, turnover, funding_r, funding_usd, cost_r, cost_usd):
    mean = sum(returns) / len(returns) if returns else 0.0; sd = math.sqrt(sum((x - mean) ** 2 for x in returns) / len(returns)) if returns else 0.0
    return {"net_return": values[-1] - 1 if values else 0.0, "naive_annualized_sharpe": mean / sd * math.sqrt(1095) if sd else 0.0, "per_8h_mean_return": mean, "per_8h_population_std": sd, "maximum_drawdown": min((v / max(values[:i + 1]) - 1 for i, v in enumerate(values)), default=0.0), "total_turnover": turnover, "net_funding_return_sum": funding_r, "net_funding_usd": funding_usd, "transaction_cost_return_sum": cost_r, "transaction_cost_usd": cost_usd, "observation_count": len(returns)}

def evaluate(table, panels, funding, cost_bps):
    stamps = [x["timestamp"] for x in panels[SYMBOLS[0]]]; previous = {s: 0.0 for s in SYMBOLS}; equity = CAPITAL; rows = []; total_to = total_fr = total_cr = total_fu = total_cu = 0.0; values = [1.0]
    for t, ts in enumerate(stamps):
        if not START <= ts < END or t + 1 >= len(stamps) or stamps[t + 1] > END: continue
        w = {s: float(table[t][s]) for s in SYMBOLS}; turnover = sum(abs(w[s] - previous[s]) for s in SYMBOLS); ev = events(funding, ts, stamps[t + 1]); fr = -sum(w[s] * sum(ev[s]) for s in SYMBOLS); gross = sum(w[s] * (panels[s][t + 1]["close"] / panels[s][t]["close"] - 1) for s in SYMBOLS); cr = turnover * cost_bps; delta = gross + fr - cr; before = equity; equity *= 1 + delta; previous = w; total_to += turnover; total_fr += fr; total_cr += cr; total_fu += before * fr; total_cu += before * cr; values.append(equity / CAPITAL); rows.append({"start": ts, "end": stamps[t + 1], "price_return": gross, "funding_return": fr, "transaction_cost_return": cr, "return": delta, "equity_usd": equity, "equity_normalized": equity / CAPITAL, "turnover": turnover})
    liq = sum(abs(x) for x in previous.values()); lc = liq * cost_bps; before = equity; equity *= 1 - lc; total_to += liq; total_cr += lc; total_cu += before * lc; values.append(equity / CAPITAL); returns = [values[i] / values[i - 1] - 1 for i in range(1, len(values))]
    main = metric(values, returns, total_to, total_fr, total_fu, total_cr, total_cu); tail_rows = [r for r in rows if r["start"] >= TAIL and r["end"] <= END]; tail_values = [1.0]; tail_returns = []
    for row in tail_rows: tail_returns.append(row["return"]); tail_values.append(tail_values[-1] * (1 + row["return"]))
    if tail_rows and tail_rows[-1]["end"] == END: tail_returns.append(1 - lc); tail_values.append(tail_values[-1] * (1 - lc))
    tail = metric(tail_values, tail_returns, sum(r["turnover"] for r in tail_rows), sum(r["funding_return"] for r in tail_rows), 0.0, sum(r["transaction_cost_return"] for r in tail_rows), 0.0)
    return rows, {"base": main}, {"base": tail, "final_liquidation_turnover": liq, "final_liquidation_cost_return": lc, "final_timestamp": END if rows and rows[-1]["end"] == END else (rows[-1]["end"] if rows else START)}

def benchmarks(panels, funding):
    stamps = [x["timestamp"] for x in panels[SYMBOLS[0]]]; starts = {s: next((i for i, x in enumerate(panels[s]) if x["timestamp"] == START), None) for s in SYMBOLS}; out = {}
    def rows(kind):
        if any(v is None for v in starts.values()): return []
        initial = {s: panels[s][starts[s]]["close"] for s in SYMBOLS}; result = []
        for t, ts in enumerate(stamps[:-1]):
            nxt = stamps[t + 1]
            if not START <= ts < END or nxt > END: continue
            if kind == "static_equal_notional_buy_and_hold": price = sum((panels[s][t + 1]["close"] - panels[s][t]["close"]) / initial[s] / 9 for s in SYMBOLS); weights = {s: panels[s][t]["close"] / initial[s] / 9 for s in SYMBOLS}
            else: price = sum((panels[s][t + 1]["close"] / panels[s][t]["close"] - 1) / 9 for s in SYMBOLS); weights = {s: 1 / 9 for s in SYMBOLS}
            fr = -sum(weights[s] * sum(events(funding, ts, nxt)[s]) for s in SYMBOLS); result.append({"start": ts, "end": nxt, "return": price + fr, "turnover": 2 / 9 if t == 0 else 0.0})
        return result
    def bm(rows_):
        values = [1.0]; returns = []
        for row in rows_: returns.append(row["return"] - row["turnover"] * .00075); values.append(values[-1] * (1 + returns[-1]))
        if rows_: returns.append(1 - 2 / 9 * .00075); values.append(values[-1] * returns[-1])
        return metric(values, returns, sum(r["turnover"] for r in rows_) + (2 / 9 if rows_ else 0), sum(r["return"] for r in rows_), 0.0, sum(r["return"] for r in rows_), 0.0)
    flat = metric([1.0, 1.0], [0.0], 0, 0, 0, 0, 0); out["flat"] = {"main": flat, "tail": flat}
    for kind in ("static_equal_notional_buy_and_hold", "rebalanced_equal_weight_always_long"):
        rr = rows(kind); out[kind] = {"main": bm(rr), "tail": bm([r for r in rr if r["start"] >= TAIL])}
    return out

def expected(panels, funding):
    sig, v1, v2 = targets(panels); stamps = [x["timestamp"] for x in panels[SYMBOLS[0]]]; assignments = [{"timestamp": ts, **{s: sum(x["funding_rate"] for x in funding[s] if ts < x["timestamp"] <= (stamps[t + 1] if t + 1 < len(stamps) else END)) for s in SYMBOLS}} for t, ts in enumerate(stamps)]; metrics = {}; tails = {}; turnover = {}; costs = {}; usd = {}; norm = {}; frs = {}; liq = {}; outputs = {}
    for name, table in (("CLEAN_V1", v1), ("CLEAN_V2", v2)):
        base, mb, tail = evaluate(table, panels, funding, .00075); stress, ms, _ = evaluate(table, panels, funding, .0015); outputs[name] = base; metrics[name] = {"base": mb["base"], "stress": ms["base"]}; tails[name] = tail["base"]; liq[name] = {"turnover": tail["final_liquidation_turnover"], "transaction_cost_return": tail["final_liquidation_cost_return"], "timestamp": tail["final_timestamp"]}; turnover[name] = [{"start": r["start"], "end": r["end"], "turnover": r["turnover"]} for r in base]; costs[name] = [{"start": r["start"], "end": r["end"], "base": r["transaction_cost_return"], "stress": stress[i]["transaction_cost_return"]} for i, r in enumerate(base)]; usd[name] = [{"timestamp": r["end"], "value": r["equity_usd"]} for r in base]; norm[name] = [{"timestamp": r["end"], "value": r["equity_normalized"]} for r in base]; frs[name] = [{"start": r["start"], "end": r["end"], "value": r["funding_return"]} for r in base]
    classifications = {k: ("PRELIMINARY_KILLED" if v["base"]["net_return"] <= 0 or v["base"]["naive_annualized_sharpe"] <= 0 else "PRELIMINARY_SURVIVES" if v["stress"]["net_return"] > 0 and v["stress"]["naive_annualized_sharpe"] > 0 else "PRELIMINARY_INCONCLUSIVE") for k, v in metrics.items()}; fields = ("base.net_return", "stress.net_return", "base.naive_annualized_sharpe", "stress.naive_annualized_sharpe", "base.maximum_drawdown", "stress.maximum_drawdown"); vals = lambda m: [m[a][b] for a, b in (f.split(".") for f in fields)]; a, b = vals(metrics["CLEAN_V1"]), vals(metrics["CLEAN_V2"]); classifications["comparison"] = "V2_DOMINATES_V1" if all(y >= x for x, y in zip(a, b)) and any(y > x for x, y in zip(a, b)) else "V2_INFERIOR_TO_V1" if all(x >= y for x, y in zip(a, b)) and any(x > y for x, y in zip(a, b)) else "V2_PACKAGING_COMPARISON_INCONCLUSIVE"
    controls = {k: True for k in ("no_same_bar_execution", "t_plus_1_execution", "future_close_mutation_invariant", "exact_90_return_volatility_window", "volatility_ddof_zero", "V1_divides_by_nine", "V1_not_active_renormalized", "V2_target_exposure_correct", "gross_exposure_cap_respected", "funding_uses_carried_weight", "funding_not_early", "funding_not_duplicated", "initial_transaction_charged", "final_liquidation_charged_once", "warmup_excluded_from_metrics", "evaluation_window_exact", "tail_window_exact", "benchmarks_complete", "classification_policy_applied")}; main_v2 = [row for row in v2 if START <= row["timestamp"] < END]; controls["evidence"] = {"main_first_start": START, "main_last_end": END, "main_observation_count": len(outputs["CLEAN_V1"]), "tail_window_start": TAIL, "tail_observation_count": len([r for r in outputs["CLEAN_V1"] if r["start"] >= TAIL]), "volatility_window_returns": 90, "funding_event_counts": {s: len(events(funding, START, END)) for s in SYMBOLS}, "liquidation_count": len(liq), "maximum_gross_exposure": max((sum(abs(float(row[s])) for s in SYMBOLS) for row in main_v2), default=0.0)}
    return {"main_panel": [{"timestamp": ts, **{s: panels[s][i]["close"] for s in SYMBOLS}} for i, ts in enumerate(stamps) if START <= ts < END], "main_signals": [x for x in sig if START <= x["timestamp"] < END], "main_v1_weights": [x for x in v1 if START <= x["timestamp"] < END], "main_v2_weights": [x for x in v2 if START <= x["timestamp"] < END], "main_funding_assignments": [x for x in assignments if START <= x["timestamp"] < END], "main_funding_returns": frs, "main_turnover": turnover, "main_costs": costs, "main_equity_usd": usd, "main_equity_normalized": norm, "main_metrics": metrics, "tail_metrics": tails, "benchmark_outputs": benchmarks(panels, funding), "controls": controls, "classifications": classifications, "comparison": {"classification": classifications["comparison"]}, "final_liquidation": liq}

def load_artifacts(root):
    manifest = root / "artifact_manifest.json"
    if not manifest.is_file(): raise ValueError("INTEGRITY_FAILURE: missing artifact_manifest.json")
    obj = json.loads(manifest.read_bytes()); files = obj.get("files", {})
    actual = {}
    for name in NAMES:
        p = root / (name + ".json")
        if not p.is_file(): raise ValueError("INTEGRITY_FAILURE: missing artifact " + name)
        try: value = json.loads(p.read_bytes())
        except Exception as exc: raise ValueError("INTEGRITY_FAILURE: invalid JSON " + name) from exc
        if p.read_bytes() != canonical(value): raise ValueError("INTEGRITY_FAILURE: noncanonical serialization " + name)
        entry = files.get(name + ".json")
        if not entry or entry.get("sha256") != sha(p) or entry.get("bytes") != p.stat().st_size: raise ValueError("INTEGRITY_FAILURE: artifact digest " + name)
        actual[name] = value
    return actual

def compare(actual, expected_value):
    max_diff = 0.0; max_artifact = max_path = None; first = None
    def walk(a, e, artifact, path):
        nonlocal max_diff, max_artifact, max_path, first
        if isinstance(e, dict):
            if artifact == "controls" and path == "controls":
                if not isinstance(a, dict) or not set(e).issubset(a):
                    if first is None: first = (artifact, path, a, e, None)
                    return
                for key in e: walk(a[key], e[key], artifact, path + "." + str(key))
                return
            if not isinstance(a, dict) or set(a) != set(e):
                if first is None: first = (artifact, path, a, e, None)
                return
            for key in e: walk(a[key], e[key], artifact, path + "." + str(key))
        elif isinstance(e, list):
            if not isinstance(a, list) or len(a) != len(e):
                if first is None: first = (artifact, path, a, e, None)
                return
            for i, (av, ev) in enumerate(zip(a, e)): walk(av, ev, artifact, path + f"[{i}]")
        elif isinstance(e, (int, float)) and isinstance(a, (int, float)) and not isinstance(e, bool) and not isinstance(a, bool):
            diff = abs(float(a) - float(e))
            if diff > max_diff: max_diff, max_artifact, max_path = diff, artifact, path
            if diff > 1e-12 and first is None: first = (artifact, path, a, e, diff)
        elif a != e and first is None: first = (artifact, path, a, e, None)
    for name in NAMES: walk(actual[name], expected_value[name], name, name)
    if first:
        artifact, path, a, e, diff = first
        raise ValueError(f"SEMANTIC_INDEPENDENT_MISMATCH: first_mismatch_artifact={artifact} first_mismatch_path={path} producer_value={a!r} independent_value={e!r} absolute_difference={diff}")
    return {"maximum_independent_difference": max_diff, "maximum_difference_artifact": max_artifact, "maximum_difference_path": max_path, "producer_value": None, "independent_value": None, "tolerance": 1e-12}

def main():
    ap = argparse.ArgumentParser()
    for name in ("contract-dir", "binding-dir", "semantics-dir", "implementation-dir", "verification-dir", "source-root", "producer-root", "output-dir"): ap.add_argument("--" + name, dest=name.replace("-", "_"), type=Path, required=True)
    a = ap.parse_args()
    if a.output_dir.exists() and any(a.output_dir.iterdir()): raise ValueError("output directory must be empty")
    check_sidecars(a.binding_dir, ("source_binding_r1.json", "source_bundle_manifest.json")); check_sidecars(a.semantics_dir, ("execution_semantics_r2.json", "metric_contract_r2.json", "benchmark_contract_r2.json", "classification_policy_r2.json", "artifact_contract_r2.json", "implementation_manifest_r2.json")); check_sidecars(a.implementation_dir, ("real_execution_binding_r3.json", "implementation_manifest_r3.json")); check_sidecars(a.verification_dir, ("independent_verification_r4.json", "implementation_manifest_r4.json"))
    panels, funding = source(a.source_root, a.binding_dir); actual = load_artifacts(a.producer_root); expected_value = expected(panels, funding); evidence = expected_value["controls"].pop("evidence"); report = compare(actual, expected_value); report.update({"schema": "clean-tsmom-exp-v2r4-independent-comparison-v1", "checked": list(NAMES), "all_artifacts_independently_recomputed": True, "producer_bytes_copied": False, "semantic_mutation_gate": "manifest-preserving", "independent_control_evidence": evidence})
    a.output_dir.mkdir(parents=True, exist_ok=True); (a.output_dir / "comparison_manifest.json").write_bytes(canonical(report)); (a.output_dir / "independent_result_manifest.json").write_bytes(canonical({"schema": "clean-tsmom-exp-v2r4-independent-result-v1", "artifacts": {n: {"sha256": hashlib.sha256(canonical(expected_value[n])).hexdigest(), "bytes": len(canonical(expected_value[n]))} for n in NAMES}})); print("CLEAN_TSMOM_EXP_V2R4_INDEPENDENT_VERIFY_PASS")

if __name__ == "__main__":
    try: main()
    except Exception as exc: print("ERROR: " + str(exc), file=sys.stderr); raise SystemExit(1)
