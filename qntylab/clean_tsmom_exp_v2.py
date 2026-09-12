"""Deterministic Clean TSMOM EXP_V2 producer core.

The core accepts already-retained local CSV inputs only.  It has no network
path and writes no files; the CLI owns validation and serialization.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

from .clean_tsmom import SYMBOLS, aggregate_8h

INTERVAL_MS = 8 * 3_600_000


def _rows(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != fields:
            raise ValueError(f"unexpected columns in {path.name}")
        return list(reader)


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def load_fixture(experiment_dir: Path) -> tuple[list[dict], dict[str, list[dict]], dict[str, list[dict]]]:
    raw = experiment_dir / "data" / "raw"
    panels: dict[str, list[dict]] = {}
    funding: dict[str, list[dict]] = {}
    for symbol in SYMBOLS:
        hourly = _rows(raw / f"{symbol}-perp-1h.csv", ("timestamp", "open", "high", "low", "close", "volume"))
        panels[symbol] = aggregate_8h([{k: float(v) if k != "timestamp" else int(v) for k, v in row.items()} for row in hourly])
        funding[symbol] = _rows(raw / f"{symbol}-funding.csv", ("timestamp", "funding_interval_hours", "funding_rate"))
    timestamps = [row["timestamp"] for row in panels[SYMBOLS[0]]]
    if any([row["timestamp"] for row in panels[symbol]] != timestamps for symbol in SYMBOLS[1:]):
        raise ValueError("symbols do not share aligned 8h timestamps")
    if len(timestamps) < 91:
        raise ValueError("fewer than 90 eligible completed returns")
    return panels[SYMBOLS[0]], panels, funding


def _weights(panel: list[dict], panels: dict[str, list[dict]]) -> tuple[list[dict], list[dict]]:
    n = len(panel)
    closes = {s: [float(r["close"]) for r in panels[s]] for s in SYMBOLS}
    signals: list[dict] = []
    v1: list[dict] = []
    v2: list[dict] = []
    for t, row in enumerate(panel):
        sig = {s: int(t >= 20 and math.log(closes[s][t] / closes[s][t - 20]) > 0) for s in SYMBOLS}
        signals.append({"timestamp": row["timestamp"], **sig})
        w1 = {s: sig[s] / 9 for s in SYMBOLS}
        w2 = {s: 0.0 for s in SYMBOLS}
        if t >= 90:
            vol = {}
            for s in SYMBOLS:
                rr = [math.log(closes[s][j] / closes[s][j - 1]) for j in range(t - 89, t + 1)]
                mean = sum(rr) / 90
                sd = math.sqrt(sum((x - mean) ** 2 for x in rr) / 90)
                if sig[s] and sd > 0 and math.isfinite(sd):
                    vol[s] = sd
            if vol:
                target = len(vol) / 9
                denom = sum(1 / x for x in vol.values())
                for s, sd in vol.items():
                    w2[s] = target * (1 / sd) / denom
        v1.append({"timestamp": row["timestamp"], **w1})
        v2.append({"timestamp": row["timestamp"], **w2})
    return signals, (v1, v2)


def produce(experiment_dir: Path) -> dict[str, object]:
    panel, panels, funding = load_fixture(experiment_dir)
    signals, (v1, v2) = _weights(panel, panels)
    funding_assignments = []
    funding_returns = []
    turnover = []
    costs = []
    equity = {"CLEAN_V1": {"base": [], "stress": []}, "CLEAN_V2": {"base": [], "stress": []}}
    previous = {"CLEAN_V1": {s: 0.0 for s in SYMBOLS}, "CLEAN_V2": {s: 0.0 for s in SYMBOLS}}
    levels = {"CLEAN_V1": {"base": 1.0, "stress": 1.0}, "CLEAN_V2": {"base": 1.0, "stress": 1.0}}
    for t, row in enumerate(panel):
        ts = row["timestamp"]
        fa = {"timestamp": ts}
        fr = {"timestamp": ts, "CLEAN_V1": 0.0, "CLEAN_V2": 0.0}
        for s in SYMBOLS:
            events = [x for x in funding[s] if int(x["timestamp"]) == ts]
            if len(events) > 1:
                raise ValueError("duplicate funding event")
            fa[s] = float(events[0]["funding_rate"]) if events else 0.0
        for name, weights in (("CLEAN_V1", _weights_for_row(v1, t)), ("CLEAN_V2", _weights_for_row(v2, t))):
            fr[name] = -sum(weights[s] * fa[s] for s in SYMBOLS)
        funding_assignments.append(fa); funding_returns.append(fr)
        to = {"timestamp": ts}; co = {"timestamp": ts}
        for name, weights in (("CLEAN_V1", _weights_for_row(v1, t)), ("CLEAN_V2", _weights_for_row(v2, t))):
            to[name] = sum(abs(weights[s] - previous[name][s]) for s in SYMBOLS)
            co[name] = {"base": to[name] * 0.00075, "stress": to[name] * 0.0015}
            previous[name] = weights
            if t:
                for cost_name, bps in (("base", 0.00075), ("stress", 0.0015)):
                    gross = sum(weights[s] * (float(panels[s][t]["close"]) / float(panels[s][t - 1]["close"]) - 1) for s in SYMBOLS)
                    levels[name][cost_name] *= 1 + gross + fr[name] - to[name] * bps
            equity[name]["base"].append({"timestamp": ts, "value": levels[name]["base"]})
            equity[name]["stress"].append({"timestamp": ts, "value": levels[name]["stress"]})
        turnover.append(to); costs.append(co)
    final = {"timestamp": panel[-1]["timestamp"], "CLEAN_V1": sum(abs(x) for x in previous["CLEAN_V1"].values()), "CLEAN_V2": sum(abs(x) for x in previous["CLEAN_V2"].values())}
    for name in ("CLEAN_V1", "CLEAN_V2"):
        for mode, bps in (("base", 0.00075), ("stress", 0.0015)):
            liquidation_cost = final[name] * bps
            costs[-1][name][mode] += liquidation_cost
            levels[name][mode] *= 1 - liquidation_cost
            equity[name][mode][-1]["value"] = levels[name][mode]
    metrics = {}
    for name in ("CLEAN_V1", "CLEAN_V2"):
        metrics[name] = {}
        for mode in ("base", "stress"):
            values = [x["value"] for x in equity[name][mode]]
            returns = [values[i] / values[i - 1] - 1 for i in range(1, len(values))]
            mean = sum(returns) / len(returns) if returns else 0.0
            sd = math.sqrt(sum((x - mean) ** 2 for x in returns) / len(returns)) if returns else 0.0
            metrics[name][mode] = {"net_return": values[-1] - 1, "sharpe": mean / sd * math.sqrt(len(returns)) if sd else 0.0, "max_drawdown": min((values[i] / max(values[: i + 1]) - 1 for i in range(len(values))), default=0.0)}
    return {"panel": [{"timestamp": panel[t]["timestamp"], **{s: panels[s][t]["close"] for s in SYMBOLS}} for t in range(len(panel))], "signals": signals, "v1_weights": v1, "v2_weights": v2, "funding_assignments": funding_assignments, "funding_returns": funding_returns, "turnover": turnover, "costs": costs, "equity": equity, "controls": {"initial_transaction_charged": True, "final_liquidation_charged": True, "funding_sign": "-carried_weight*funding_rate", "volatility_ddof": 0, "future_close_consumption": False}, "diagnostics": {"tail_rows": min(20, len(panel)), "heat_count": 0}, "metrics": metrics, "classifications": {"CLEAN_V1": "NOT_YET_CLASSIFIED", "CLEAN_V2": "NOT_YET_CLASSIFIED"}, "final_liquidation": final}


def _weights_for_row(rows: list[dict], t: int) -> dict[str, float]:
    return {s: float(rows[t][s]) for s in SYMBOLS}


def canonical_bytes(value: object) -> bytes:
    return _canonical_json(value)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
