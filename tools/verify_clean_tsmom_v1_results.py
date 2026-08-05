"""Independent, offline verifier for the source-resolved clean TSMOM result.

This module intentionally does not import qntylab.clean_tsmom or numpy.  It
reconstructs the panel, signals, weights, funding, costs, equity and metrics
from the frozen JSON specifications and retained CSV bytes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path


SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "LINKUSDT", "DOTUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT", "AVAXUSDT"]
TOLERANCE = 1e-12
FROZEN_SPEC_SHA256 = {
    "experiments/clean_tsmom/v1/source_contract.json": "50a0f70447c683b8414affc1cf120e291dde558dea3fe22f312086ad1cc533b4",
    "experiments/clean_tsmom/v1/v1_equal_weight.json": "9ce16a99860bc6a03859810ccf07e6d21f4468e696c81695e635f7085878ce85",
    "experiments/clean_tsmom/v1/v2_inverse_vol.json": "4ea90e5a9ce9109a9db5ba16d545e2c7d614428895753aa1e93c627ddef8c3c2",
    "experiments/clean_tsmom/v1/evaluation_v1.json": "f6ba36fe0e13046b2c5b68714fcb8c15342c1e8af83a7bcf43d63e9ed05dcfa5",
}
FROZEN_SPEC_SIDECAR_SHA256 = {
    "experiments/clean_tsmom/v1/source_contract.sha256": "3da94b0fbaf9fbb291b14081cea262d433480df178341a4971bc063780d30f9d",
    "experiments/clean_tsmom/v1/v1_equal_weight.sha256": "2e2e0c1f368d199d49bdfe813550d44629c22256ebaa15eaa442d27156873038",
    "experiments/clean_tsmom/v1/v2_inverse_vol.sha256": "c3e44116cdcb04f18b84a3bff568f4081e76069c48fa4334bb798f2a0230f995",
    "experiments/clean_tsmom/v1/evaluation_v1.sha256": "bd31684d24a00243377093c4a9921a6a785fd06ff0325d40d4ee9b58f814d9e2",
}
EXPECTED_RESULT_SHA256 = "19196a8d40d2cde7ca362289d2c5368737d9ef7067cef6b78592fcdb5e3dd9aa"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def _stamp(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def validate_frozen_artifacts(root: Path, expected_result_sha256: str = EXPECTED_RESULT_SHA256):
    for spec_path, expected_sha256 in FROZEN_SPEC_SHA256.items():
        path = root / spec_path
        if _sha(path) != expected_sha256:
            raise ValueError(f"frozen specification hash mismatch: {spec_path}")
        sidecar_path = root / spec_path.replace(".json", ".sha256")
        if _sha(sidecar_path) != FROZEN_SPEC_SIDECAR_SHA256[str(sidecar_path.relative_to(root))]:
            raise ValueError(f"frozen specification sidecar hash mismatch: {sidecar_path.relative_to(root)}")
        declared = sidecar_path.read_text(encoding="utf-8").split()[0]
        if declared != expected_sha256:
            raise ValueError(f"frozen specification sidecar declaration mismatch: {spec_path}")
    result_path = root / "experiments/clean_tsmom/v1/results_v1.json"
    if _sha(result_path) != expected_result_sha256:
        raise ValueError("original result artifact hash mismatch")


def aggregate(rows):
    if len(rows) % 8:
        raise ValueError("hourly rows do not form complete buckets")
    stamps = [int(row["timestamp"]) for row in rows]
    if len(set(stamps)) != len(stamps):
        raise ValueError("duplicate hourly timestamp")
    bars = []
    for offset in range(0, len(rows), 8):
        group = rows[offset : offset + 8]
        ts = [int(row["timestamp"]) for row in group]
        if any(t % 3_600_000 for t in ts) or ts != list(range(ts[0], ts[0] + 8 * 3_600_000, 3_600_000)):
            raise ValueError("hourly gap or off-grid row")
        values = {key: [float(row[key]) for row in group] for key in ("open", "high", "low", "close", "volume")}
        if any(not math.isfinite(value) for values in values.values() for value in values):
            raise ValueError("non-finite OHLCV")
        if any(value <= 0 for key in ("open", "high", "low", "close") for value in values[key]) or any(value < 0 for value in values["volume"]):
            raise ValueError("invalid OHLCV")
        bars.append({"timestamp": ts[0], "open": values["open"][0], "high": max(values["high"]), "low": min(values["low"]), "close": values["close"][-1], "volume": sum(values["volume"])})
    return bars


def build_panel(root: Path):
    bars = {}
    funding = []
    manifest = _load_json(root / "experiments/clean_tsmom/v1/source_manifest.json")["panel"]
    for symbol in SYMBOLS:
        price_path = root / "data/raw" / f"{symbol}-perp-1h.csv"
        funding_path = root / "data/raw" / f"{symbol}-funding.csv"
        if _sha(price_path) != manifest[symbol]["sha256"] or _sha(funding_path) != manifest[symbol]["funding_sha256"]:
            raise ValueError(f"source hash mismatch: {symbol}")
        bars[symbol] = aggregate(_rows(price_path))
        funding.extend({**row, "symbol": symbol} for row in _rows(funding_path))
    timestamps = [bar["timestamp"] for bar in bars[SYMBOLS[0]]]
    if any([bar["timestamp"] for bar in bars[symbol]] != timestamps for symbol in SYMBOLS):
        raise ValueError("common panel misalignment")
    closes = {symbol: [bar["close"] for bar in bars[symbol]] for symbol in SYMBOLS}
    return timestamps, closes, funding


def signals(close):
    result = [0] * len(close)
    for index in range(20, len(close)):
        result[index] = int(math.log(close[index] / close[index - 20]) > 0)
    return result


def weights(closes, mode):
    sig = {symbol: signals(closes[symbol]) for symbol in SYMBOLS}
    out = [{symbol: 0.0 for symbol in SYMBOLS} for _ in range(len(closes[SYMBOLS[0]]))]
    for index in range(len(out)):
        if mode == "v1":
            for symbol in SYMBOLS:
                out[index][symbol] = sig[symbol][index] / 9.0
        elif index >= 90:
            vol = {}
            for symbol in SYMBOLS:
                returns = [math.log(closes[symbol][j] / closes[symbol][j - 1]) for j in range(index - 89, index + 1)]
                mean = sum(returns) / len(returns)
                sigma = math.sqrt(sum((value - mean) ** 2 for value in returns) / len(returns))
                if sig[symbol][index] and math.isfinite(sigma) and sigma > 0:
                    vol[symbol] = sigma
            if vol:
                target = len(vol) / 9.0
                inverse_total = sum(1.0 / value for value in vol.values())
                for symbol, sigma in vol.items():
                    out[index][symbol] = target * (1.0 / sigma) / inverse_total
        else:
            continue
    return out


def run(timestamps, closes, funding, portfolio_weights, start, end, cost_rate):
    begin, finish = _stamp(start), _stamp(end)
    indices = [index for index, timestamp in enumerate(timestamps) if begin <= timestamp < finish]
    funding_map = {}
    for event in funding:
        key = (event["symbol"], int(event["timestamp"]))
        if key in funding_map:
            raise ValueError("duplicate funding event")
        if key[1] not in set(timestamps):
            raise ValueError("funding event off panel boundary")
        funding_map[key] = float(event["funding_rate"])
    previous = {symbol: 0.0 for symbol in SYMBOLS}
    equity = 10_000.0
    rows = []
    turnover = fee_cost = funding_paid = funding_received = 0.0
    episodes = 0
    for index in indices:
        if index == 0:
            continue
        current = portfolio_weights[index - 1]
        price_return = sum(previous[symbol] * (closes[symbol][index] / closes[symbol][index - 1] - 1.0) for symbol in SYMBOLS)
        funding_return = sum(-previous[symbol] * funding_map.get((symbol, timestamps[index]), 0.0) for symbol in SYMBOLS)
        for symbol in SYMBOLS:
            value = -previous[symbol] * funding_map.get((symbol, timestamps[index]), 0.0)
            if value >= 0:
                funding_received += value
            else:
                funding_paid += -value
        turn = sum(abs(current[symbol] - previous[symbol]) for symbol in SYMBOLS)
        cost = turn * cost_rate
        equity *= 1.0 + price_return + funding_return - cost
        turnover += turn
        fee_cost += cost * 2.0 / 3.0
        episodes += sum(previous[symbol] == 0 and current[symbol] > 0 for symbol in SYMBOLS)
        rows.append({"timestamp": timestamps[index], "price_return": price_return, "funding_return": funding_return, "turnover": turn, "cost": cost, "equity": equity})
        previous = current
    liquidation_turnover = sum(abs(value) for value in previous.values())
    equity_liquidated = equity * (1.0 - liquidation_turnover * cost_rate)
    returns = [row["price_return"] + row["funding_return"] - row["cost"] for row in rows]
    mean = sum(returns) / len(returns)
    sigma = math.sqrt(sum((value - mean) ** 2 for value in returns) / len(returns))
    peak = 10_000.0
    drawdowns = []
    for row in rows:
        peak = max(peak, row["equity"])
        drawdowns.append(row["equity"] / peak - 1.0)
    exposure = [sum(abs(value) for value in portfolio_weights[index - 1].values()) for index in indices if index]
    return {"valid_8h_bars": len(rows), "net_return": equity_liquidated / 10_000.0 - 1.0, "sharpe": mean / sigma * math.sqrt(365 * 3) if sigma else 0.0, "maximum_drawdown": min(drawdowns) if drawdowns else 0.0, "turnover": turnover + liquidation_turnover, "fee_cost": fee_cost, "slippage_cost": fee_cost / 2.0, "funding_paid": funding_paid * 10_000.0, "funding_received": funding_received * 10_000.0, "net_funding": (funding_received - funding_paid) * 10_000.0, "average_gross_exposure": sum(exposure) / len(exposure) if exposure else 0.0, "maximum_gross_exposure": max(sum(abs(value) for value in row.values()) for row in portfolio_weights), "position_episode_count": episodes, "equity_rows": rows}


def verify(root: Path):
    validate_frozen_artifacts(root)
    evaluation = _load_json(root / "experiments/clean_tsmom/v1/evaluation_v1.json")["evaluation"]
    timestamps, closes, funding = build_panel(root)
    submitted = _load_json(root / "experiments/clean_tsmom/v1/results_v1.json")["results"]
    reports = {}
    for package, mode in (("CLEAN_V1", "v1"), ("CLEAN_V2", "v2")):
        package_weights = weights(closes, mode)
        for scenario, rate in (("base", 0.00075), ("stress", 0.0015)):
            key = f"{package}_{scenario}"
            independent = run(timestamps, closes, funding, package_weights, evaluation["start"], evaluation["end"], rate)
            reports[key] = {field: (submitted[key][field], independent[field], abs(submitted[key][field] - independent[field])) for field in ("net_return", "sharpe", "maximum_drawdown", "turnover", "fee_cost", "slippage_cost", "funding_paid", "funding_received", "net_funding", "valid_8h_bars")}
    return {"timestamps": len(timestamps), "main_bars": 300, "tail_bars": 129, "result_artifact_sha256": EXPECTED_RESULT_SHA256, "reports": reports}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    report = verify(args.root)
    failures = [(key, field, diff) for key, values in report["reports"].items() for field, (_, _, diff) in values.items() if diff > TOLERANCE]
    print(json.dumps(report, sort_keys=True, indent=2))
    if failures:
        raise SystemExit(f"INDEPENDENT_VERIFY_FAIL {failures[:3]}")
    print("INDEPENDENT_VERIFY_PASS")


if __name__ == "__main__":
    main()
