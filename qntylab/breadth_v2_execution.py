"""Breadth V2 execution contract V0: one causal portfolio accounting kernel."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping, Sequence

PANEL_SIZE = 20
TARGET_WEIGHT_BASIS = "PRE_COST_EQUITY"
SUPPORTED_RATE_TYPES = frozenset({"REALIZED", "realized", "funding"})
SUPPORTED_FAMILIES = frozenset({"TIME_SERIES_MOMENTUM", "MOVING_AVERAGE_TREND", "PRICE_BREAKOUT", "CROSS_SECTIONAL_MOMENTUM", "CROSS_SECTIONAL_REVERSAL", "FUNDING_CARRY", "VOLATILITY_TARGETING"})
REGISTERED_SCIENTIFIC_CELLS = 3360
EXECUTION_UNITS = 1992


@dataclass(frozen=True)
class FundingEvent:
    symbol: str
    funding_time: str
    funding_rate: float
    mark_price: float
    rate_type: str = "REALIZED"
    source: str = "synthetic"
    coverage: str = "COMPLETE"

    def __post_init__(self) -> None:
        if self.rate_type not in SUPPORTED_RATE_TYPES:
            raise ValueError(f"unsupported funding rate_type: {self.rate_type}")


@dataclass(frozen=True)
class PriceSeries:
    closes: Mapping[str, float]
    highs: Mapping[str, float] | None = None
    lows: Mapping[str, float] | None = None
    provenance: str = "synthetic"


@dataclass
class AssetContribution:
    price_pnl: float = 0.0
    funding_pnl: float = 0.0
    fee_cost: float = 0.0
    slippage_cost: float = 0.0

    @property
    def net_contribution(self) -> float:
        return self.price_pnl + self.funding_pnl - self.fee_cost - self.slippage_cost


@dataclass
class ExecutionResult:
    equity: float
    initial_equity: float
    turnover_notional: float
    fee_cost: float
    slippage_cost: float
    funding_pnl: float
    price_pnl: float
    contributions: dict[str, AssetContribution]
    event_log: list[dict[str, object]] = field(default_factory=list)

    @property
    def final_pnl(self) -> float:
        return self.equity - self.initial_equity


class PortfolioKernel:
    """Shared single-asset/panel futures accounting kernel."""

    def __init__(self, initial_equity: float = 1_000.0, fee_bps: float = 10.0, slippage_bps: float = 0.0):
        self.initial_equity = float(initial_equity)
        self.fee_bps, self.slippage_bps = float(fee_bps), float(slippage_bps)

    def execute(
        self, boundaries: Sequence[str], prices: Mapping[str, PriceSeries], funding_events: Sequence[FundingEvent],
        target_fn: Callable[[str, Mapping[str, float], Mapping[str, float], float], Mapping[str, float]],
        symbols: Sequence[str],
    ) -> ExecutionResult:
        # Validate every required boundary before entering the event clock.
        if not boundaries or set(symbols) != set(prices):
            raise ValueError("price input is incomplete")
        if any(boundary not in prices[s].closes for boundary in boundaries for s in symbols):
            raise ValueError("required evaluation input is incomplete")
        equity, quantities, old_prices = self.initial_equity, {s: 0.0 for s in symbols}, {}
        contributions = {s: AssetContribution() for s in symbols}
        turnover = fees = slippage = funding_pnl = price_pnl = 0.0
        by_time: dict[str, list[FundingEvent]] = {}
        for event in funding_events:
            if event.symbol not in symbols or event.coverage != "COMPLETE":
                raise ValueError("funding evidence gap or unknown symbol")
            by_time.setdefault(event.funding_time, []).append(event)
        log: list[dict[str, object]] = []
        prior_weights = {s: 0.0 for s in symbols}
        for t in boundaries:
            # The interval price move and event-time funding both use the position arriving at t.
            for symbol in symbols:
                new_price = float(prices[symbol].closes[t])
                if symbol in old_prices:
                    pnl = quantities[symbol] * (new_price - old_prices[symbol])
                    contributions[symbol].price_pnl += pnl; equity += pnl; price_pnl += pnl
                old_prices[symbol] = new_price
            for event in by_time.get(t, []):
                cashflow = -quantities[event.symbol] * event.mark_price * event.funding_rate
                contributions[event.symbol].funding_pnl += cashflow; equity += cashflow; funding_pnl += cashflow
                log.append({"time": t, "kind": "funding", "symbol": event.symbol, "quantity": quantities[event.symbol], "cashflow": cashflow})
            targets = dict(target_fn(t, {s: prices[s].closes[t] for s in symbols}, prior_weights, equity))
            pre_cost_equity = equity
            for symbol in symbols:
                target_notional = float(targets.get(symbol, 0.0)) * pre_cost_equity
                current_notional = quantities[symbol] * old_prices[symbol]
                trade = abs(target_notional - current_notional)
                turnover += trade
                fee, slip = trade * self.fee_bps / 10000, trade * self.slippage_bps / 10000
                fees += fee; slippage += slip; equity -= fee + slip
                contributions[symbol].fee_cost += fee; contributions[symbol].slippage_cost += slip
                quantities[symbol] = target_notional / old_prices[symbol]
                prior_weights[symbol] = float(targets.get(symbol, 0.0))
            log.append({"time": t, "kind": "rebalance", "target_weight_basis": TARGET_WEIGHT_BASIS, "targets": targets})
        # Final boundary is already marked and funding-settled; liquidate and charge terminal turnover.
        for symbol in symbols:
            trade = abs(quantities[symbol] * old_prices[symbol]); turnover += trade
            fee, slip = trade * self.fee_bps / 10000, trade * self.slippage_bps / 10000
            fees += fee; slippage += slip; equity -= fee + slip
            contributions[symbol].fee_cost += fee; contributions[symbol].slippage_cost += slip
            quantities[symbol] = 0.0
        log.append({"time": boundaries[-1], "kind": "terminal_liquidation"})
        result = ExecutionResult(equity, self.initial_equity, turnover, fees, slippage, funding_pnl, price_pnl, contributions, log)
        if abs(sum(c.net_contribution for c in contributions.values()) - result.final_pnl) > 1e-9:
            raise AssertionError("asset contributions do not reconcile to portfolio PnL")
        return result


def _sha(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def evaluation_input_bundle_sha256(*, instrument_contract_id: str, symbols: Sequence[str], boundaries: Sequence[str], decision_clock: str, assets: Mapping[str, Mapping[str, str]],) -> str:
    payload = {"contract": "BREADTH_V2_INPUT_BUNDLE_V0", "instrument_contract_id": instrument_contract_id, "symbols": list(symbols), "boundaries": list(boundaries), "decision_clock": decision_clock, "assets": {s: assets[s] for s in symbols}}
    return _sha(payload)


def breadth_v2_evaluation_id(*, registered_screen_id: str, variant_id: str, execution_contract_digest: str, execution_unit_type: str, evaluation_input_bundle_sha256: str, period_id: str, cost_mode: str, fee_bps: float, slippage_bps: float, instrument_contract_id: str) -> str:
    return _sha({"contract": "BREADTH_V2_EVALUATION_ID_V0", "registered_screen_id": registered_screen_id, "variant_id": variant_id, "execution_contract_digest": execution_contract_digest, "execution_unit_type": execution_unit_type, "evaluation_input_bundle_sha256": evaluation_input_bundle_sha256, "period_id": period_id, "cost_mode": cost_mode, "fee_bps": fee_bps, "slippage_bps": slippage_bps, "instrument_contract_id": instrument_contract_id})


def sealed_t0(canonical_merge_commit_utc: str) -> str:
    dt = datetime.fromisoformat(canonical_merge_commit_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    next_hour = dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return next_hour.isoformat().replace("+00:00", "Z")


def registered_candidate_mappings(path: str = "experiments/research/candidates.jsonl") -> dict[str, str]:
    """Validate the committed 28-event V2 catalog without changing it."""
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    v2 = [row for row in rows if row["candidate_id"].startswith("CANDIDATE_BREADTH_V2_")]
    if len(v2) != 28 or any(row["event_type"] != "CANDIDATE_PROPOSED" for row in v2):
        raise ValueError("Breadth V2 catalog must contain exactly 28 proposed candidates")
    if any(row["family_id"] not in SUPPORTED_FAMILIES for row in v2):
        raise ValueError("unmapped Breadth V2 family")
    counts = {family: sum(row["family_id"] == family for row in v2) for family in SUPPORTED_FAMILIES}
    if counts != {family: 4 for family in SUPPORTED_FAMILIES}:
        raise ValueError(f"unexpected Breadth V2 family counts: {counts}")
    return {row["variant_id"]: row["family_id"] for row in v2}
