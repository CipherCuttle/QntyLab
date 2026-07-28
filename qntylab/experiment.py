from __future__ import annotations
import csv, json
from collections import defaultdict
from pathlib import Path
import numpy as np
from .backtest import evaluate, segments
from .data import load
from .strategies import positions
from .data import load_perp, load_funding
from .perp import funding_to_bars, positions as perp_positions, evaluate_perp

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

def _perp_splits(close, position, timestamps, funding, fee_bps):
    result = {"full": evaluate_perp(close, position, timestamps, funding, fee_bps)}
    for i, name in enumerate(("early", "middle", "late")):
        lo, hi = i * len(close) // 3, (i + 1) * len(close) // 3
        window_hours = {stamp[:13] + ":00:00Z" for stamp in timestamps[lo:hi]}
        in_window = [event for event in funding if event["timestamp"][:13] + ":00:00Z" in window_hours]
        result[name] = evaluate_perp(close[lo:hi], position[lo:hi], timestamps[lo:hi], in_window, fee_bps)
    return result

def _perp_classify(metrics, splits, control, supported_assets):
    positive_segments = sum(splits[name]["net_cumulative_return"] > 0 for name in ("early", "middle", "late"))
    if metrics["net_cumulative_return"] <= 0: return "KILL"
    if positive_segments < 2: return "KILL"
    if supported_assets < 2: return "KILL"
    if metrics["net_cumulative_return"] <= control["net_cumulative_return"]: return "WEAK"
    return "INTERESTING"

def run_perp(spec_path: Path, root: Path) -> dict:
    spec = json.loads(spec_path.read_text()); rows_out = []
    for symbol in spec["symbols"]:
        rows = load_perp(root / "data/raw" / f"{symbol}-perp-1h.csv"); funding_events = load_funding(root / "data/raw" / f"{symbol}-funding.csv")
        timestamps = [row["timestamp"] for row in rows]; close = np.array([float(row["close"]) for row in rows]); premium = np.array([float(row["premium"]) for row in rows])
        quote = np.array([float(row["quote_volume"]) for row in rows]); taker = np.array([float(row["taker_buy_quote_volume"]) for row in rows]); ofi = 2 * np.divide(taker, quote, out=np.full(len(quote), .5), where=quote > 0) - 1
        funding = funding_to_bars(timestamps, funding_events)
        for family in spec["families"]:
            for variant in family["variants"]:
                position = perp_positions(family["id"], close, premium, ofi, funding, variant)
                splits = _perp_splits(close, position, timestamps, funding_events, 10); base = splits["full"]
                costs = {str(cost): evaluate_perp(close, position, timestamps, funding_events, cost) for cost in (5, 10, 20)}
                delayed = np.r_[0., position[:-1]]
                control = evaluate_perp(close, delayed, timestamps, funding_events, 10)
                years = {}
                net = np.array(base["net_returns"])
                for year in sorted({stamp[:4] for stamp in timestamps[1:]}):
                    idx = [i for i, stamp in enumerate(timestamps[1:]) if stamp.startswith(year)]
                    years[year] = float(np.prod(1 + net[idx]) - 1)
                for collection in (splits, costs):
                    for value in collection.values(): value.pop("net_returns", None)
                control.pop("net_returns", None)
                rows_out.append({"family": family["id"], "hypothesis": family["hypothesis"], "economic_story": family["economic_story"], "falsifier": family["falsifier"], "symbol": symbol, "params": variant, "metrics": base, "splits": splits, "cost_stress": costs, "extra_bar_delay_control": control, "year_returns": years})
    groups = defaultdict(list)
    for row in rows_out: groups[row["family"] + json.dumps(row["params"], sort_keys=True)].append(row)
    for items in groups.values():
        supported = sum(item["metrics"]["net_cumulative_return"] > 0 and sum(item["splits"][name]["net_cumulative_return"] > 0 for name in ("early", "middle", "late")) >= 2 for item in items)
        for item in items:
            item["cross_asset_support"] = supported
            item["verdict"] = _perp_classify(item["metrics"], item["splits"], item["extra_bar_delay_control"], supported)
    output = {"identity": "EXPLORATORY ONLY; NON_AUTHORITATIVE; NO SCIENTIFIC VALIDATION; NO HOLDOUT; NO PAPER/LIVE AUTHORITY; NO TRADING EXECUTION", "alignment_contract": "bar-t values are delayed one bar; settled funding is assigned to its containing hour then delayed; no return is earned across a gap", "spec": spec, "results": rows_out}
    target = root / "experiments/results/sprint_v1_perp_results.json"; target.write_text(json.dumps(output, sort_keys=True, indent=2) + "\n")
    with (root / "experiments/results/sprint_v1_perp_summary.csv").open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=["family", "symbol", "params", "net_10bps", "price_pnl", "funding_cashflow", "fees", "control_net", "cross_asset_support", "verdict"], lineterminator="\n"); writer.writeheader()
        for item in rows_out: writer.writerow({"family":item["family"], "symbol":item["symbol"], "params":json.dumps(item["params"], sort_keys=True), "net_10bps":item["metrics"]["net_cumulative_return"], "price_pnl":item["metrics"]["price_pnl"], "funding_cashflow":item["metrics"]["funding_cashflow"], "fees":item["metrics"]["fees"], "control_net":item["extra_bar_delay_control"]["net_cumulative_return"], "cross_asset_support":item["cross_asset_support"], "verdict":item["verdict"]})
    return output
