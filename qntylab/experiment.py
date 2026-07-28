from __future__ import annotations
import csv, json
from collections import defaultdict
from pathlib import Path
import numpy as np
from .backtest import evaluate, segments
from .data import load
from .strategies import positions

def _classify(metrics: dict, split: dict, bh: dict) -> str:
    signs = [split[x]["net_cumulative_return"] > 0 for x in ("early", "middle", "late")]
    if metrics["net_cumulative_return"] <= 0: return "KILLED_NEGATIVE_BASE_COST"
    if sum(signs) < 2: return "KILLED_ONE_REGIME"
    if metrics["net_cumulative_return"] <= bh["net_cumulative_return"] and metrics["short_exposure"] == 0: return "KILLED_LONG_BETA"
    return "INTERESTING_EXPLORATORY"

def run(spec_path: Path, root: Path) -> dict:
    spec = json.loads(spec_path.read_text()); results = []
    for symbol in spec["symbols"]:
        rows = load(root / "data/raw" / f"{symbol}-1h.csv"); close = np.array([float(x["close"]) for x in rows]); timestamps = [x["timestamp"] for x in rows]
        bh = evaluate(close, np.ones(len(close)), 10)
        for family in spec["families"]:
            for variant in family["variants"]:
                pos = positions(family["id"], close, variant)
                split = segments(close, pos, 10); base = split["full"]
                costs = {str(c): evaluate(close, pos, c) for c in (5,10,20)}
                net = np.array(base.pop("net_returns")); top = sorted(net, reverse=True)[:5]; without = np.delete(net, int(net.argmax()))
                years: dict[str, list[int]] = defaultdict(list)
                for i, stamp in enumerate(timestamps[1:]): years[stamp[:4]].append(i)
                year_returns = {y: float(np.prod(1 + net[ix]) - 1) for y, ix in years.items()}
                for part in split.values(): part.pop("net_returns", None)
                for part in costs.values(): part.pop("net_returns", None)
                results.append({"family": family["id"], "hypothesis": family["hypothesis"], "economic_story": family["economic_story"], "falsifier": family["falsifier"], "expected_failure_mode": family["expected_failure_mode"], "symbol": symbol, "params": variant, "metrics": base, "splits": split, "cost_stress": costs, "buy_and_hold_base_10bps": bh["net_cumulative_return"], "year_returns": year_returns, "best_five_bar_contribution": float(sum(top)), "net_excluding_best_bar": float(np.prod(1 + without) - 1), "verdict": _classify(base, split, bh)})
    # Cross-asset check: a family/parameter must be positive on >=2 assets to survive this sprint.
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in results: groups[item["family"] + json.dumps(item["params"], sort_keys=True)].append(item)
    for items in groups.values():
        good = sum(x["verdict"] == "INTERESTING_EXPLORATORY" for x in items)
        for item in items:
            item["cross_asset_interesting_count"] = good
            if item["verdict"] == "INTERESTING_EXPLORATORY" and good < 2: item["verdict"] = "KILLED_SINGLE_ASSET"
    output = {"identity": "EXPLORATORY ONLY; NON_AUTHORITATIVE; NO SCIENTIFIC VALIDATION; NO HOLDOUT; NO PAPER/LIVE AUTHORITY; NO TRADING EXECUTION", "execution": "signal through close[t], position effective next bar; bar return close[t] to close[t+1]; costs on absolute position change", "spec": spec, "results": results}
    target = root / "experiments/results/sprint_v0_results.json"; target.write_text(json.dumps(output, sort_keys=True, indent=2) + "\n")
    with (root / "experiments/results/sprint_v0_summary.csv").open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=["family","symbol","params","net_10bps","max_drawdown","sharpe","cross_asset_interesting_count","verdict"]); writer.writeheader()
        for x in results: writer.writerow({"family":x["family"],"symbol":x["symbol"],"params":json.dumps(x["params"], sort_keys=True),"net_10bps":x["metrics"]["net_cumulative_return"],"max_drawdown":x["metrics"]["max_drawdown"],"sharpe":x["metrics"]["sharpe"],"cross_asset_interesting_count":x["cross_asset_interesting_count"],"verdict":x["verdict"]})
    return output
