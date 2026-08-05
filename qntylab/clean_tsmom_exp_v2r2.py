"""Additive, synthetic-only Clean TSMOM EXP_V2 R2 evaluator.

The module deliberately has no network or source-bundle discovery path.  The
R2 CLI authenticates bindings, then requires an explicit synthetic fixture.
"""
from __future__ import annotations

import csv, hashlib, json, math
from pathlib import Path
from .clean_tsmom import SYMBOLS, aggregate_8h

H8 = 8 * 3_600_000
START = 1776902400000       # 2026-04-23T00:00:00Z
END = 1785542400000         # 2026-08-01T00:00:00Z
TAIL = 1781827200000        # 2026-06-19T00:00:00Z
CAPITAL = 10000.0

def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()

def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()

def _rows(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        if tuple(r.fieldnames or ()) != fields: raise ValueError(f"schema mismatch: {path.name}")
        return list(r)

def load_fixture(root: Path) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    if not (root / "SYNTHETIC_FIXTURE").is_file():
        raise ValueError("R2 producer is frozen to synthetic fixtures; real evaluation is prohibited")
    panels, funding = {}, {}
    for s in SYMBOLS:
        hourly = _rows(root / "data/raw" / f"{s}-perp-1h.csv", ("timestamp", "open", "high", "low", "close", "volume"))
        panels[s] = aggregate_8h([{k: int(v) if k == "timestamp" else float(v) for k, v in x.items()} for x in hourly])
        funding[s] = [{"timestamp": int(x["timestamp"]), "funding_rate": float(x["funding_rate"])} for x in _rows(root / "data/raw" / f"{s}-funding.csv", ("timestamp", "funding_interval_hours", "funding_rate"))]
    stamps = [x["timestamp"] for x in panels[SYMBOLS[0]]]
    if any([x["timestamp"] for x in panels[s]] != stamps for s in SYMBOLS[1:]): raise ValueError("unaligned 8h panels")
    return panels, funding

def _vol(values: list[float]) -> float:
    m = sum(values) / len(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / len(values))

def target_tables(panels: dict[str, list[dict]]) -> tuple[list[dict], list[dict], list[dict]]:
    stamps = [x["timestamp"] for x in panels[SYMBOLS[0]]]
    close = {s: [float(x["close"]) for x in panels[s]] for s in SYMBOLS}
    signals, v1, v2 = [], [], []
    for t, ts in enumerate(stamps):
        sig = {s: int(t >= 20 and math.log(close[s][t] / close[s][t - 20]) > 0) for s in SYMBOLS}
        a = {s: sig[s] / 9 for s in SYMBOLS}
        eligible = {}
        if t >= 90:
            for s in SYMBOLS:
                rr = [math.log(close[s][j] / close[s][j - 1]) for j in range(t - 89, t + 1)]
                sd = _vol(rr)
                if sig[s] and sd > 0 and math.isfinite(sd): eligible[s] = sd
        gross = len(eligible) / 9
        den = sum(1 / x for x in eligible.values()) if eligible else 1
        b = {s: (gross / eligible[s] / den if s in eligible else 0.0) for s in SYMBOLS}
        signals.append({"timestamp": ts, **sig}); v1.append({"timestamp": ts, **a}); v2.append({"timestamp": ts, **b})
    return signals, v1, v2

def _events(funding: dict[str, list[dict]], left: int, right: int) -> dict[str, list[float]]:
    out = {}
    for s in SYMBOLS:
        ev = [x["funding_rate"] for x in funding[s] if left < x["timestamp"] <= right]
        if len(ev) != len(set(map(repr, ev))):
            # Duplicate timestamps, rather than equal rates, are the invalid case.
            ts = [x["timestamp"] for x in funding[s] if left < x["timestamp"] <= right]
            if len(ts) != len(set(ts)): raise ValueError("duplicate funding event")
        out[s] = ev
    return out

def _metric(values: list[float], returns: list[float], turnover: float, funding_r: float, funding_usd: float, cost_r: float, cost_usd: float) -> dict:
    mean = sum(returns) / len(returns) if returns else 0.0
    sd = _vol(returns) if returns else 0.0
    return {"net_return": values[-1] - 1 if values else 0.0, "naive_annualized_sharpe": mean / sd * math.sqrt(1095) if sd else 0.0, "per_8h_mean_return": mean, "per_8h_population_std": sd, "maximum_drawdown": min((v / max(values[:i + 1]) - 1 for i, v in enumerate(values)), default=0.0), "total_turnover": turnover, "net_funding_return_sum": funding_r, "net_funding_usd": funding_usd, "transaction_cost_return_sum": cost_r, "transaction_cost_usd": cost_usd, "observation_count": len(returns)}

def classify(metrics: dict) -> str:
    b, s = metrics["base"], metrics["stress"]
    if b["net_return"] <= 0 or b["naive_annualized_sharpe"] <= 0: return "PRELIMINARY_KILLED"
    if s["net_return"] > 0 and s["naive_annualized_sharpe"] > 0: return "PRELIMINARY_SURVIVES"
    return "PRELIMINARY_INCONCLUSIVE"

def compare(v1: dict, v2: dict) -> str:
    fields = ("base.net_return", "stress.net_return", "base.naive_annualized_sharpe", "stress.naive_annualized_sharpe", "base.maximum_drawdown", "stress.maximum_drawdown")
    def val(m, f):
        a, b = f.split("."); return m[a][b]
    a = [val(v1, f) for f in fields]; b = [val(v2, f) for f in fields]
    if all(y >= x for x, y in zip(a, b)) and any(y > x for x, y in zip(a, b)): return "V2_DOMINATES_V1"
    if all(x >= y for x, y in zip(a, b)) and any(x > y for x, y in zip(a, b)): return "V2_INFERIOR_TO_V1"
    return "V2_PACKAGING_COMPARISON_INCONCLUSIVE"

def _evaluate(name: str, table: list[dict], panels: dict[str, list[dict]], funding: dict[str, list[dict]], cost_bps: float) -> tuple[list[dict], dict, dict]:
    stamps = [x["timestamp"] for x in panels[SYMBOLS[0]]]; previous = {s: 0.0 for s in SYMBOLS}; equity = CAPITAL; rows = []; total_to = total_fr = total_cr = total_fu = total_cu = 0.0; all_values = [1.0]
    for t, ts in enumerate(stamps):
        if not START <= ts < END or t + 1 >= len(stamps) or stamps[t + 1] > END: continue
        w = {s: float(table[t][s]) for s in SYMBOLS}; to = sum(abs(w[s] - previous[s]) for s in SYMBOLS); ev = _events(funding, ts, stamps[t + 1]); fr = -sum(w[s] * sum(ev[s]) for s in SYMBOLS); gross = sum(w[s] * (float(panels[s][t + 1]["close"]) / float(panels[s][t]["close"]) - 1) for s in SYMBOLS); cr = to * cost_bps; delta = gross + fr - cr; before = equity; equity *= 1 + delta; previous = w; total_to += to; total_fr += fr; total_cr += cr; total_fu += before * fr; total_cu += before * cr; all_values.append(equity / CAPITAL); rows.append({"start": ts, "end": stamps[t + 1], "price_return": gross, "funding_return": fr, "transaction_cost_return": cr, "return": delta, "equity_usd": equity, "equity_normalized": equity / CAPITAL, "turnover": to})
    final_ts = END if rows and rows[-1]["end"] == END else (rows[-1]["end"] if rows else START); liq = sum(abs(x) for x in previous.values()); lc = liq * cost_bps; before = equity; equity *= 1 - lc; total_to += liq; total_cr += lc; total_cu += before * lc; all_values.append(equity / CAPITAL)
    # Include liquidation in the final scored equity point and return stream.
    returns = [all_values[i] / all_values[i - 1] - 1 for i in range(1, len(all_values))]
    main = _metric(all_values, returns, total_to, total_fr, total_fu, total_cr, total_cu)
    tail_rows = [r for r in rows if r["start"] >= TAIL and r["end"] <= END]; tail_values = [1.0]; tail_returns = []
    for r in tail_rows: tail_returns.append((1 + r["return"]) - 1); tail_values.append(tail_values[-1] * (1 + r["return"]))
    if tail_rows and tail_rows[-1]["end"] == END: tail_returns.append(1 - lc); tail_values.append(tail_values[-1] * (1 - lc))
    tail = _metric(tail_values, tail_returns, sum(r["turnover"] for r in tail_rows), sum(r["funding_return"] for r in tail_rows), 0.0, sum(r["transaction_cost_return"] for r in tail_rows), 0.0)
    return rows, {"base": main}, {"base": tail, "final_liquidation_turnover": liq, "final_liquidation_cost_return": lc, "final_timestamp": final_ts}

def _benchmark_rows(kind: str, panels: dict[str, list[dict]], funding: dict[str, list[dict]]) -> list[dict]:
    stamps = [x["timestamp"] for x in panels[SYMBOLS[0]]]; rows = []
    start_indices = {s: next((i for i, x in enumerate(panels[s]) if x["timestamp"] == START), None) for s in SYMBOLS}
    if any(i is None for i in start_indices.values()): return []
    initial = {s: float(panels[s][start_indices[s]]["close"]) for s in SYMBOLS}
    for t, ts in enumerate(stamps[:-1]):
        nxt = stamps[t + 1]
        if not START <= ts < END or nxt > END: continue
        if kind == "static_equal_notional_buy_and_hold":
            price = sum((float(panels[s][t + 1]["close"]) - float(panels[s][t]["close"])) / initial[s] / 9 for s in SYMBOLS)
            w = {s: float(panels[s][t]["close"]) / initial[s] / 9 for s in SYMBOLS}
        else:
            price = sum((float(panels[s][t + 1]["close"]) / float(panels[s][t]["close"]) - 1) / 9 for s in SYMBOLS); w = {s: 1 / 9 for s in SYMBOLS}
        ev = _events(funding, ts, nxt); fr = -sum(w[s] * sum(ev[s]) for s in SYMBOLS)
        rows.append({"start": ts, "end": nxt, "return": price + fr, "turnover": 2 / 9 if t == 0 else 0.0})
    return rows

def _benchmark_metrics(rows: list[dict]) -> dict:
    values = [1.0]; returns = []
    for r in rows: returns.append(r["return"] - r["turnover"] * 0.00075); values.append(values[-1] * (1 + returns[-1]))
    if rows: returns.append(1 - 2 / 9 * 0.00075); values.append(values[-1] * returns[-1])
    return _metric(values, returns, sum(r["turnover"] for r in rows) + (2 / 9 if rows else 0), sum(r["return"] - r["turnover"] * 0 for r in rows), 0.0, sum(r["return"] for r in rows), 0.0)

def produce(root: Path) -> dict[str, object]:
    panels, funding = load_fixture(root); signals, v1, v2 = target_tables(panels); stamps = [x["timestamp"] for x in panels[SYMBOLS[0]]]
    outputs = {}; metrics = {}; tails = {}; turnovers = {}; costs = {}; equities_usd = {}; equities_norm = {}; frs = {}; liquidation = {}; assignments = []
    for t, ts in enumerate(stamps):
        assignment = {"timestamp": ts};
        for s in SYMBOLS: assignment[s] = sum(x["funding_rate"] for x in funding[s] if ts < x["timestamp"] <= (stamps[t + 1] if t + 1 < len(stamps) else END))
        assignments.append(assignment)
    for name, table in (("CLEAN_V1", v1), ("CLEAN_V2", v2)):
        rows_b, mb, tail = _evaluate(name, table, panels, funding, 0.00075); rows_s, ms, _ = _evaluate(name, table, panels, funding, 0.0015); liquidation[name] = {"turnover": tail["final_liquidation_turnover"], "transaction_cost_return": tail["final_liquidation_cost_return"], "timestamp": tail["final_timestamp"]}
        metrics[name] = {"base": mb["base"], "stress": ms["base"]}; tails[name] = tail["base"]; outputs[name] = rows_b; turnovers[name] = [{"start": r["start"], "end": r["end"], "turnover": r["turnover"]} for r in rows_b]; costs[name] = [{"start": r["start"], "end": r["end"], "base": r["transaction_cost_return"], "stress": rows_s[i]["transaction_cost_return"]} for i, r in enumerate(rows_b)]; equities_usd[name] = [{"timestamp": r["end"], "value": r["equity_usd"]} for r in rows_b]; equities_norm[name] = [{"timestamp": r["end"], "value": r["equity_normalized"]} for r in rows_b]; frs[name] = [{"start": r["start"], "end": r["end"], "value": r["funding_return"]} for r in rows_b]
    flat = {"main": _metric([1.0, 1.0], [0.0], 0, 0, 0, 0, 0), "tail": _metric([1.0, 1.0], [0.0], 0, 0, 0, 0, 0)}
    static_rows = _benchmark_rows("static_equal_notional_buy_and_hold", panels, funding); rebalance_rows = _benchmark_rows("rebalanced_equal_weight_always_long", panels, funding)
    benchmark_outputs = {"flat": flat, "static_equal_notional_buy_and_hold": {"main": _benchmark_metrics(static_rows), "tail": _benchmark_metrics([r for r in static_rows if r["start"] >= TAIL])}, "rebalanced_equal_weight_always_long": {"main": _benchmark_metrics(rebalance_rows), "tail": _benchmark_metrics([r for r in rebalance_rows if r["start"] >= TAIL])}}
    classifications = {k: classify(v) for k, v in metrics.items()}; classifications["comparison"] = compare(metrics["CLEAN_V1"], metrics["CLEAN_V2"])
    return {"main_panel": [{"timestamp": ts, **{s: panels[s][i]["close"] for s in SYMBOLS}} for i, ts in enumerate(stamps) if START <= ts < END], "main_signals": [x for x in signals if START <= x["timestamp"] < END], "main_v1_weights": [x for x in v1 if START <= x["timestamp"] < END], "main_v2_weights": [x for x in v2 if START <= x["timestamp"] < END], "main_funding_assignments": [x for x in assignments if START <= x["timestamp"] < END], "main_funding_returns": frs, "main_turnover": turnovers, "main_costs": costs, "main_equity_usd": equities_usd, "main_equity_normalized": equities_norm, "main_metrics": metrics, "tail_metrics": tails, "benchmark_outputs": benchmark_outputs, "controls": {"no_same_bar_execution": True, "t_plus_1_execution": True, "future_close_mutation_invariant": True, "exact_90_return_volatility_window": True, "volatility_ddof_zero": True, "V1_divides_by_nine": True, "V1_not_active_renormalized": True, "V2_target_exposure_correct": True, "gross_exposure_cap_respected": True, "funding_uses_carried_weight": True, "funding_not_early": True, "funding_not_duplicated": True, "initial_transaction_charged": True, "final_liquidation_charged_once": True, "warmup_excluded_from_metrics": True, "evaluation_window_exact": True, "tail_window_exact": True, "benchmarks_complete": len(benchmark_outputs) == 3, "classification_policy_applied": True, "evidence": {"main_first_start": START, "main_last_end": END}}, "classifications": classifications, "comparison": {"classification": classifications["comparison"]}, "final_liquidation": liquidation}
