"""Breadth V2 runner: wires the frozen candidate, input bundle, execution and
path contracts to the existing append-only research ledger.

This module contains no strategy arithmetic and no ledger schema of its own.
Target weights come from ``qntylab.breadth_v2_strategies``, accounting comes
from ``qntylab.breadth_v2_execution.PortfolioKernel``, evidence serialization
comes from ``qntylab.breadth_v2_path``, and ledger identity/storage comes from
``qntylab.research_ledger``.  See ``experiments/specs/
breadth_v2_runner_ledger_integration_v0.md`` for the frozen contract.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import breadth_v2_strategies as strategies
from . import family_ontology
from .breadth_v2_execution import (
    INSTRUMENT_CONTRACT_ID,
    FundingEvent,
    PortfolioKernel,
    PriceSeries,
    breadth_v2_evaluation_id,
    evaluation_input_bundle_sha256,
)
from .breadth_v2_input_bundle import PANEL_ORDER
from .breadth_v2_path import build_path, describe as describe_path, digest as path_digest, reconcile as reconcile_path, serialize as serialize_path
from .instrument_contract import BINANCE_USDM_PERPETUAL_USDT_V1, FUNDING_INCLUDED_PROVENANCE_BOUND, contract_digest as instrument_contract_digest
from . import research_ledger

REGISTERED_SCREEN_ID = "QNTYLAB_BREADTH_V2_20260810"
REGISTERED_VARIANT_DENOMINATOR = 28
REGISTERED_SCIENTIFIC_CELL_DENOMINATOR = 3360
RECEIPT_SCHEMA_VERSION = "BREADTH_V2_RECEIPT_V0"

SINGLE_ASSET = "SINGLE_ASSET"
SYNCHRONIZED_PANEL = "SYNCHRONIZED_PANEL"
PANEL_EXECUTION_UNIT_ID = "BREADTH_V2_FIXED_PANEL_20"

SINGLE_ASSET_FAMILIES = ("TIME_SERIES_MOMENTUM", "MOVING_AVERAGE_TREND", "PRICE_BREAKOUT", "VOLATILITY_TARGETING")
PANEL_FAMILIES = ("CROSS_SECTIONAL_MOMENTUM", "CROSS_SECTIONAL_REVERSAL", "FUNDING_CARRY")
ALL_FAMILIES = SINGLE_ASSET_FAMILIES + PANEL_FAMILIES

# The 20 assets developed against.  Membership, order and count are frozen by
# experiments/specs/breadth_v2_preregistration.md and must equal PANEL_ORDER.
FROZEN_PANEL_ORDER = PANEL_ORDER

REGISTERED_PERIODS = {
    "DEV_2022": ("2022-01-01T00:00:00Z", "2022-12-31T23:00:00Z"),
    "DEV_2024": ("2024-01-01T00:00:00Z", "2024-12-31T23:00:00Z"),
    "DEV_2025": ("2025-01-01T00:00:00Z", "2025-12-31T23:00:00Z"),
}

COST_MODES = {
    "BASELINE_EXECUTION": {"fee_bps": 10.0, "slippage_bps": 0.0},
    "STRESS_EXECUTION": {"fee_bps": 10.0, "slippage_bps": 10.0},
}

BENCHMARK_MAP = {
    "TIME_SERIES_MOMENTUM": "BUY_AND_HOLD",
    "MOVING_AVERAGE_TREND": "BUY_AND_HOLD",
    "PRICE_BREAKOUT": "BUY_AND_HOLD",
    "CROSS_SECTIONAL_MOMENTUM": "FLAT",
    "CROSS_SECTIONAL_REVERSAL": "FLAT",
    "FUNDING_CARRY": "FLAT",
    "VOLATILITY_TARGETING": "UNSCALED_MA_24_96",
}

EXECUTION_CONTRACT_SPEC_PATHS = (
    "experiments/specs/breadth_v2_execution_contract_v0.md",
    "experiments/specs/breadth_v2_execution_contract_v0r1.md",
)
RELEVANT_SOURCE_PATHS = (
    "qntylab/breadth_v2_execution.py",
    "qntylab/breadth_v2_strategies.py",
    "qntylab/breadth_v2_input_bundle.py",
    "qntylab/breadth_v2_runner.py",
    "qntylab/breadth_v2_path.py",
    "qntylab/research_ledger.py",
    "qntylab/instrument_contract.py",
)


class RunnerBlocked(RuntimeError):
    """A blocked input or contract violation.  Never accompanies a completed trial."""


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha(value: Any) -> str:
    return _sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def _file_sha256(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def execution_contract_digest(repo_root: Path = Path(".")) -> str:
    rows = sorted(
        ({"path": path, "sha256": _file_sha256(repo_root / path)} for path in EXECUTION_CONTRACT_SPEC_PATHS),
        key=lambda row: row["path"],
    )
    return _canonical_sha(rows)


def relevant_source_sha256(repo_root: Path = Path(".")) -> str:
    rows = sorted(
        ({"path": path, "sha256": _file_sha256(repo_root / path)} for path in RELEVANT_SOURCE_PATHS),
        key=lambda row: row["path"],
    )
    return _canonical_sha(rows)


def require_clean_relevant_source(repo_root: Path = Path(".")) -> None:
    """Production guard: refuse to run while any relevant tracked file is dirty."""
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", *RELEVANT_SOURCE_PATHS],
        cwd=repo_root, capture_output=True, text=True, check=True,
    )
    if result.stdout.strip():
        raise RunnerBlocked(f"relevant Breadth V2 source is dirty: {result.stdout.strip()}")


def repository_commit(repo_root: Path = Path(".")) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def family_execution_unit_type(family_id: str) -> str:
    if family_id in SINGLE_ASSET_FAMILIES:
        return SINGLE_ASSET
    if family_id in PANEL_FAMILIES:
        return SYNCHRONIZED_PANEL
    raise RunnerBlocked(f"unregistered Breadth V2 family: {family_id}")


@dataclass(frozen=True)
class ExecutionUnitDescriptor:
    family_id: str
    variant_id: str
    execution_unit_type: str
    execution_unit_id: str
    period_id: str
    cost_mode: str


def enumerate_registered_execution_plan(candidates_path: str = "experiments/research/candidates.jsonl") -> list[ExecutionUnitDescriptor]:
    """Pure enumerator: the complete registered plan, with no data access.

    Requires exactly 1,920 SINGLE_ASSET units + 72 SYNCHRONIZED_PANEL units =
    1,992 unique descriptors, mapping to 3,360 scientific cells.
    """
    variants_by_family = _registered_variants_by_family(candidates_path)
    descriptors: list[ExecutionUnitDescriptor] = []
    for family_id in ALL_FAMILIES:
        unit_type = family_execution_unit_type(family_id)
        execution_unit_ids = FROZEN_PANEL_ORDER if unit_type == SINGLE_ASSET else (PANEL_EXECUTION_UNIT_ID,)
        for variant_id in variants_by_family[family_id]:
            for execution_unit_id in execution_unit_ids:
                for period_id in REGISTERED_PERIODS:
                    for cost_mode in COST_MODES:
                        descriptors.append(
                            ExecutionUnitDescriptor(family_id, variant_id, unit_type, execution_unit_id, period_id, cost_mode)
                        )
    single = sum(1 for d in descriptors if d.execution_unit_type == SINGLE_ASSET)
    panel = sum(1 for d in descriptors if d.execution_unit_type == SYNCHRONIZED_PANEL)
    if single != 1920 or panel != 72 or len(descriptors) != 1992:
        raise RunnerBlocked(f"registered execution plan count mismatch: single={single} panel={panel} total={len(descriptors)}")
    unique = {(d.family_id, d.variant_id, d.execution_unit_type, d.execution_unit_id, d.period_id, d.cost_mode) for d in descriptors}
    if len(unique) != len(descriptors):
        raise RunnerBlocked("registered execution plan contains duplicate descriptors")
    return descriptors


def scientific_cell_count(descriptors: Sequence[ExecutionUnitDescriptor] | None = None) -> int:
    descriptors = descriptors if descriptors is not None else enumerate_registered_execution_plan()
    return sum(1 if d.execution_unit_type == SINGLE_ASSET else len(FROZEN_PANEL_ORDER) for d in descriptors)


def _registered_variants_by_family(candidates_path: str) -> dict[str, list[str]]:
    rows = [json.loads(line) for line in open(candidates_path, encoding="utf-8") if line.strip()]
    v2 = [row for row in rows if row.get("candidate_id", "").startswith("CANDIDATE_BREADTH_V2_")]
    if len(v2) != 28 or any(row["event_type"] != "CANDIDATE_PROPOSED" for row in v2):
        raise RunnerBlocked("Breadth V2 catalog must contain exactly 28 proposed candidates")
    by_family: dict[str, list[str]] = {family: [] for family in ALL_FAMILIES}
    for row in v2:
        if row["registered_screen_id"] != REGISTERED_SCREEN_ID:
            raise RunnerBlocked(f"unregistered screen id: {row['registered_screen_id']}")
        by_family.setdefault(row["family_id"], []).append(row["variant_id"])
    if any(len(variants) != 4 for variants in by_family.values()):
        raise RunnerBlocked(f"unexpected Breadth V2 family variant counts: { {k: len(v) for k, v in by_family.items()} }")
    return by_family


def resolve_candidate(variant_id: str, candidates_path: str = "experiments/research/candidates.jsonl") -> dict[str, Any]:
    """Resolve one registered candidate by canonical variant_id.  Parameters are frozen."""
    rows = [json.loads(line) for line in open(candidates_path, encoding="utf-8") if line.strip()]
    matches = [row for row in rows if row.get("variant_id") == variant_id and row.get("candidate_id", "").startswith("CANDIDATE_BREADTH_V2_")]
    if len(matches) != 1:
        raise RunnerBlocked(f"variant_id does not resolve to exactly one registered Breadth V2 candidate: {variant_id}")
    candidate = matches[0]
    if candidate["registered_screen_id"] != REGISTERED_SCREEN_ID:
        raise RunnerBlocked(f"candidate is not registered under {REGISTERED_SCREEN_ID}")
    if candidate["registered_variant_denominator"] != REGISTERED_VARIANT_DENOMINATOR:
        raise RunnerBlocked("candidate registered_variant_denominator does not match the frozen 28-variant screen")
    if candidate["family_id"] not in ALL_FAMILIES:
        raise RunnerBlocked(f"unregistered Breadth V2 family: {candidate['family_id']}")
    return candidate


# ---------------------------------------------------------------------------
# Target-weight wiring: pure lookups into the strict input bundle's admitted
# observations.  No raw materializer files are re-read here.


def _closes_map(rows: Sequence[Mapping[str, Any]]) -> tuple[list[str], dict[str, float]]:
    times = [row["decision_time"] for row in rows]
    closes = {row["decision_time"]: float(row["close"]) for row in rows}
    return times, closes


def _window(times: Sequence[str], closes: Mapping[str, float], index_of: Mapping[str, int], t: str, length: int) -> list[float]:
    idx = index_of[t]
    if idx - length + 1 < 0:
        raise RunnerBlocked(f"insufficient admitted price history before {t}")
    return [closes[times[i]] for i in range(idx - length + 1, idx + 1)]


def _single_asset_target_fn(family_id: str, parameters: Mapping[str, Any], admitted_price_rows: Sequence[Mapping[str, Any]]) -> Callable[..., Any]:
    times, closes = _closes_map(admitted_price_rows)
    index_of = {t: i for i, t in enumerate(times)}
    state: dict[str, float] = {"prior_state": 0.0}

    if family_id in {"TIME_SERIES_MOMENTUM", "PRICE_BREAKOUT"}:
        length = int(parameters["lookback"]) + 1
    elif family_id == "MOVING_AVERAGE_TREND":
        length = int(parameters["slow"])
    elif family_id == "VOLATILITY_TARGETING":
        length = max(int(parameters["slow"]), int(parameters["realized_volatility_window"])) + 1
    else:
        raise RunnerBlocked(f"not a single-asset family: {family_id}")

    def target_fn(t: str, prices_at_t: Mapping[str, float], prior_weights: Mapping[str, float], equity: float) -> dict[str, float]:
        symbol = next(iter(prices_at_t))
        window = _window(times, closes, index_of, t, length)
        weight = strategies.target_weights(family_id, parameters, closes=window, prior_state=state["prior_state"])
        if family_id == "PRICE_BREAKOUT":
            state["prior_state"] = float(weight)
        return {symbol: float(weight)}

    return target_fn


def _panel_price_target_fn(family_id: str, parameters: Mapping[str, Any], admitted_price_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]]) -> Callable[..., Any]:
    length = int(parameters["lookback"]) + 1
    per_symbol = {symbol: _closes_map(rows) for symbol, rows in admitted_price_by_symbol.items()}
    index_of = {symbol: {t: i for i, t in enumerate(times)} for symbol, (times, _) in per_symbol.items()}

    def target_fn(t: str, prices_at_t: Mapping[str, float], prior_weights: Mapping[str, float], equity: float) -> dict[str, float]:
        closes_by_symbol = {}
        for symbol in FROZEN_PANEL_ORDER:
            times, closes = per_symbol[symbol]
            closes_by_symbol[symbol] = _window(times, closes, index_of[symbol], t, length)
        return strategies.target_weights(family_id, parameters, closes_by_symbol=closes_by_symbol, panel_order=FROZEN_PANEL_ORDER)

    return target_fn


def _panel_funding_target_fn(parameters: Mapping[str, Any], admitted_funding_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]]) -> Callable[..., Any]:
    window_events = int(parameters["funding_window_events"])
    per_symbol = {symbol: sorted(events, key=lambda e: e["funding_time_ms"]) for symbol, events in admitted_funding_by_symbol.items()}

    def target_fn(t: str, prices_at_t: Mapping[str, float], prior_weights: Mapping[str, float], equity: float) -> dict[str, float]:
        events_by_symbol = {}
        for symbol in FROZEN_PANEL_ORDER:
            eligible = [e for e in per_symbol[symbol] if e["admission_boundary"] <= t]
            if len(eligible) < window_events:
                raise RunnerBlocked(f"insufficient funding warmup at {t} for {symbol}")
            events_by_symbol[symbol] = [float(e["funding_rate"]) for e in eligible[-window_events:]]
        return strategies.target_weights("FUNDING_CARRY", parameters, events_by_symbol=events_by_symbol, panel_order=FROZEN_PANEL_ORDER)

    return target_fn


class _BuyAndHoldTarget:
    """Genuine buy-and-hold: one entry, zero turnover afterward, held through
    terminal liquidation.  Tracks its own implied quantity from the same
    inputs the kernel already supplies (price at t, pre-cost equity) -- this
    is a stateful strategy function, not a second accounting engine."""

    def __init__(self) -> None:
        self._quantity: float | None = None

    def __call__(self, t: str, prices_at_t: Mapping[str, float], prior_weights: Mapping[str, float], equity: float) -> dict[str, float]:
        symbol = next(iter(prices_at_t))
        price = prices_at_t[symbol]
        if self._quantity is None:
            self._quantity = equity / price
            return {symbol: 1.0}
        weight = (self._quantity * price / equity) if equity else 0.0
        return {symbol: weight}


def _flat_target_fn(symbols: Sequence[str]) -> Callable[..., Any]:
    def target_fn(t: str, prices_at_t: Mapping[str, float], prior_weights: Mapping[str, float], equity: float) -> dict[str, float]:
        return {symbol: 0.0 for symbol in symbols}

    return target_fn


def _benchmark_target_fn(family_id: str, symbols: Sequence[str], admitted_price_rows: Sequence[Mapping[str, Any]] | None) -> Callable[..., Any]:
    benchmark_id = BENCHMARK_MAP[family_id]
    if benchmark_id == "BUY_AND_HOLD":
        return _BuyAndHoldTarget()
    if benchmark_id == "FLAT":
        return _flat_target_fn(symbols)
    if benchmark_id == "UNSCALED_MA_24_96":
        if admitted_price_rows is None:
            raise RunnerBlocked("UNSCALED_MA_24_96 benchmark requires the candidate's own admitted price series")
        return _single_asset_target_fn("MOVING_AVERAGE_TREND", {"fast": 24, "slow": 96, "mode": "long_flat"}, admitted_price_rows)
    raise RunnerBlocked(f"unregistered benchmark: {benchmark_id}")


def _funding_events(admitted_funding_rows: Sequence[Mapping[str, Any]], symbol: str) -> list[FundingEvent]:
    events = []
    for row in admitted_funding_rows:
        events.append(
            FundingEvent(
                symbol=symbol,
                funding_time=row["admission_boundary"],
                funding_rate=float(row["funding_rate"]),
                source=row.get("source", "BREADTH_V2_INPUT_BUNDLE_V0"),
                coverage="COMPLETE",
                mark_price=row.get("mark_price"),
                rate_type=row.get("rate_type"),
            )
        )
    return events


def _price_series_from_bundle(admitted_price_rows: Sequence[Mapping[str, Any]], boundaries: Sequence[str]) -> PriceSeries:
    _, closes = _closes_map(admitted_price_rows)
    return PriceSeries(closes={t: closes[t] for t in boundaries if t in closes})


def execute_candidate_and_benchmark(*, family_id: str, variant_id: str, parameters: Mapping[str, Any], execution_unit_type: str, execution_unit_id: str, input_bundle: Mapping[str, Any], fee_bps: float, slippage_bps: float) -> tuple[Any, Any, list[str]]:
    """Run one candidate execution and its subordinate benchmark on the same
    frozen price/funding evidence, event clock, fee model, slippage model and
    terminal liquidation."""
    boundaries: list[str] = input_bundle["bundle_payload"]["boundaries"]
    symbols: list[str] = [execution_unit_id] if execution_unit_type == SINGLE_ASSET else list(FROZEN_PANEL_ORDER)

    prices = {s: _price_series_from_bundle(input_bundle["admitted_price"][s], boundaries) for s in symbols}
    funding_events: list[FundingEvent] = []
    for s in symbols:
        funding_events.extend(_funding_events(input_bundle["admitted_funding"][s], s))

    if execution_unit_type == SINGLE_ASSET:
        admitted_rows = input_bundle["admitted_price"][execution_unit_id]
        candidate_fn = _single_asset_target_fn(family_id, parameters, admitted_rows)
        benchmark_fn = _benchmark_target_fn(family_id, symbols, admitted_rows)
    else:
        admitted_rows = None
        if family_id == "FUNDING_CARRY":
            candidate_fn = _panel_funding_target_fn(parameters, input_bundle["admitted_funding"])
        else:
            candidate_fn = _panel_price_target_fn(family_id, parameters, input_bundle["admitted_price"])
        benchmark_fn = _benchmark_target_fn(family_id, symbols, admitted_rows)

    kernel = PortfolioKernel(fee_bps=fee_bps, slippage_bps=slippage_bps)
    candidate_result = kernel.execute(boundaries, prices, funding_events, candidate_fn, symbols)
    benchmark_kernel = PortfolioKernel(fee_bps=fee_bps, slippage_bps=slippage_bps)
    benchmark_result = benchmark_kernel.execute(boundaries, prices, funding_events, benchmark_fn, symbols)
    return candidate_result, benchmark_result, symbols


# ---------------------------------------------------------------------------
# Identities, receipt, scientific cells.


def _period_boundaries(period_id: str) -> tuple[str, str]:
    if period_id not in REGISTERED_PERIODS:
        raise RunnerBlocked(f"unregistered Breadth V2 period: {period_id}")
    return REGISTERED_PERIODS[period_id]


def _cost_assumption(cost_mode: str) -> dict[str, float]:
    if cost_mode not in COST_MODES:
        raise RunnerBlocked(f"unregistered Breadth V2 cost mode: {cost_mode}")
    return COST_MODES[cost_mode]


def _max_drawdown(equity_curve: Sequence[float]) -> float:
    peak = equity_curve[0]
    worst = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        worst = min(worst, (value - peak) / peak if peak else 0.0)
    return worst


def _single_asset_cell(symbol: str, candidate_result: Any, benchmark_result: Any) -> dict[str, Any]:
    candidate = candidate_result.contributions[symbol]
    benchmark = benchmark_result.contributions[symbol]
    candidate_net_return = candidate_result.final_pnl / candidate_result.initial_equity
    benchmark_net_return = benchmark_result.final_pnl / benchmark_result.initial_equity
    equity_curve = [row["equity_after_rebalance"] for row in candidate_result.boundary_path]
    final_equity = candidate_result.boundary_path[-1].get("final_equity") if candidate_result.boundary_path else None
    trade_count = sum(1 for row in candidate_result.boundary_path if row["turnover"] > 0.0)
    exposure_fraction = sum(1 for row in candidate_result.boundary_path if abs(row["target_weights"].get(symbol, 0.0)) > 0.0) / len(candidate_result.boundary_path)
    return {
        "symbol": symbol,
        "candidate_net_return": candidate_net_return,
        "benchmark_net_return": benchmark_net_return,
        "excess_return_vs_benchmark": candidate_net_return - benchmark_net_return,
        "price_pnl": candidate.price_pnl,
        "funding_pnl": candidate.funding_pnl,
        "fee_cost": candidate.fee_cost,
        "slippage_cost": candidate.slippage_cost,
        "maximum_drawdown": _max_drawdown(
            [candidate_result.initial_equity] + equity_curve
            + ([] if final_equity is None or final_equity == equity_curve[-1] else [final_equity])
        ),
        "turnover": candidate_result.turnover_notional,
        "exposure_fraction": exposure_fraction,
    }


def _panel_cells(candidate_result: Any, benchmark_result: Any) -> list[dict[str, Any]]:
    cells = []
    for symbol in FROZEN_PANEL_ORDER:
        candidate = candidate_result.contributions[symbol]
        benchmark = benchmark_result.contributions[symbol]
        cells.append({
            "symbol": symbol,
            "candidate_price_pnl": candidate.price_pnl,
            "candidate_funding_pnl": candidate.funding_pnl,
            "candidate_fee_cost": candidate.fee_cost,
            "candidate_slippage_cost": candidate.slippage_cost,
            "candidate_net_contribution": candidate.net_contribution,
            "benchmark_net_contribution": benchmark.net_contribution,
            "excess_contribution_vs_benchmark": candidate.net_contribution - benchmark.net_contribution,
        })
    candidate_sum = sum(cell["candidate_net_contribution"] for cell in cells)
    benchmark_sum = sum(cell["benchmark_net_contribution"] for cell in cells)
    if abs(candidate_sum - candidate_result.final_pnl) > 1e-9:
        raise RunnerBlocked("panel candidate contribution cells do not reconcile to portfolio final PnL")
    if abs(benchmark_sum - benchmark_result.final_pnl) > 1e-9:
        raise RunnerBlocked("panel benchmark contribution cells do not reconcile to portfolio final PnL")
    return cells


@dataclass(frozen=True)
class PreparedEvaluation:
    status: str
    trial_event: dict[str, Any] | None
    receipt: dict[str, Any] | None
    receipt_bytes: bytes | None
    candidate_path_rows: list[dict[str, Any]] | None
    benchmark_path_rows: list[dict[str, Any]] | None
    blocked_reason: str | None = None


def existing_breadth_v2_identities(root: Path) -> tuple[frozenset[str], frozenset[str]]:
    """Read-only scan of a ledger root's canonical trial history."""
    history = research_ledger.load_canonical_history(root)
    trial_ids = frozenset(event["trial_id"] for event in history.trials)
    evaluation_ids = frozenset(event["breadth_v2_evaluation_id"] for event in history.trials if event.get("breadth_v2_evaluation_id"))
    return trial_ids, evaluation_ids


def prepare_breadth_v2_evaluation(
    *,
    variant_id: str,
    execution_unit_type: str,
    execution_unit_id: str,
    period_id: str,
    cost_mode: str,
    input_bundle: Mapping[str, Any],
    research_intent: str = "SCREEN",
    candidates_path: str = "experiments/research/candidates.jsonl",
    repo_root: Path = Path("."),
    require_clean_source: bool = True,
    ledger_root: Path | None = None,
    existing_trial_ids: frozenset[str] = frozenset(),
    existing_evaluation_ids: frozenset[str] = frozenset(),
) -> PreparedEvaluation:
    """Stage A: pure except for reading frozen repo/ledger state.  Writes nothing."""
    if ledger_root is not None:
        ledger_trial_ids, ledger_evaluation_ids = existing_breadth_v2_identities(ledger_root)
        existing_trial_ids = existing_trial_ids | ledger_trial_ids
        existing_evaluation_ids = existing_evaluation_ids | ledger_evaluation_ids
    candidate = resolve_candidate(variant_id, candidates_path)
    family_id, parameters = candidate["family_id"], candidate["parameters"]
    if family_execution_unit_type(family_id) != execution_unit_type:
        raise RunnerBlocked("execution_unit_type does not match the candidate's registered family")
    if execution_unit_type == SINGLE_ASSET and execution_unit_id not in FROZEN_PANEL_ORDER:
        raise RunnerBlocked(f"unregistered single-asset execution_unit_id: {execution_unit_id}")
    if execution_unit_type == SYNCHRONIZED_PANEL and execution_unit_id != PANEL_EXECUTION_UNIT_ID:
        raise RunnerBlocked("panel execution_unit_id must be the frozen panel sentinel")

    period_start, period_end = _period_boundaries(period_id)
    cost = _cost_assumption(cost_mode)

    if input_bundle.get("status") != "READY":
        return PreparedEvaluation("BLOCKED", None, None, None, None, None, f"input bundle status: {input_bundle.get('status')}")
    payload = input_bundle["bundle_payload"]
    if payload.get("contract") != "BREADTH_V2_INPUT_BUNDLE_V0":
        raise RunnerBlocked("input bundle is not BREADTH_V2_INPUT_BUNDLE_V0")
    recomputed_bundle_sha = evaluation_input_bundle_sha256(
        instrument_contract_id=payload["instrument_contract_id"], symbols=payload["symbols"],
        boundaries=payload["boundaries"], decision_clock=payload["decision_clock"], assets=payload["assets"],
    )
    if recomputed_bundle_sha != input_bundle["evaluation_input_bundle_sha256"]:
        raise RunnerBlocked("evaluation_input_bundle_sha256 does not recompute from bundle_payload")
    if payload["boundaries"][0] != period_start or payload["boundaries"][-1] != period_end:
        raise RunnerBlocked("input bundle boundaries do not match the registered period")

    if require_clean_source:
        require_clean_relevant_source(repo_root)
    source_sha = relevant_source_sha256(repo_root)
    contract_digest_value = execution_contract_digest(repo_root)
    commit = repository_commit(repo_root)

    evaluation_id = breadth_v2_evaluation_id(
        registered_screen_id=REGISTERED_SCREEN_ID, variant_id=variant_id, execution_contract_digest=contract_digest_value,
        execution_unit_type=execution_unit_type, evaluation_input_bundle_sha256=input_bundle["evaluation_input_bundle_sha256"],
        period_id=period_id, cost_mode=cost_mode, fee_bps=cost["fee_bps"], slippage_bps=cost["slippage_bps"],
        instrument_contract_id=BINANCE_USDM_PERPETUAL_USDT_V1,
    )
    if evaluation_id in existing_evaluation_ids:
        raise RunnerBlocked(f"duplicate breadth_v2_evaluation_id: {evaluation_id}")

    ledger_symbol = execution_unit_id  # frozen sentinel for panels, exact symbol for single-asset
    trial_id = research_ledger.compute_trial_id_v2(
        variant_id=variant_id, instrument_contract_id=BINANCE_USDM_PERPETUAL_USDT_V1, symbol=ledger_symbol,
        input_sha256=input_bundle["evaluation_input_bundle_sha256"], evaluation_start=period_start, evaluation_end=period_end,
        fee_bps=cost["fee_bps"], slippage_bps=cost["slippage_bps"], funding_treatment=FUNDING_INCLUDED_PROVENANCE_BOUND,
        gap_policy="FAIL_CLOSED_NO_GAPS", expected_interval="1h",
    )
    if trial_id in existing_trial_ids and research_intent != "REPLICATION":
        raise RunnerBlocked(f"duplicate trial_id without REPLICATION intent: {trial_id}")

    candidate_result, benchmark_result, symbols = execute_candidate_and_benchmark(
        family_id=family_id, variant_id=variant_id, parameters=parameters, execution_unit_type=execution_unit_type,
        execution_unit_id=execution_unit_id, input_bundle=input_bundle, fee_bps=cost["fee_bps"], slippage_bps=cost["slippage_bps"],
    )

    candidate_path_rows = build_path(candidate_result)
    reconcile_path(candidate_path_rows, candidate_result, symbols)
    candidate_path_info = describe_path(candidate_path_rows)
    benchmark_path_rows = build_path(benchmark_result)
    reconcile_path(benchmark_path_rows, benchmark_result, symbols)
    benchmark_path_sha = path_digest(benchmark_path_rows)

    if execution_unit_type == SINGLE_ASSET:
        cells = [_single_asset_cell(execution_unit_id, candidate_result, benchmark_result)]
        cell_semantics = "SINGLE_ASSET_EVALUATION"
        compact_observation_count = len(candidate_path_rows)
        compact = {
            "observation_count": compact_observation_count,
            "trade_count": sum(1 for row in candidate_path_rows if row["turnover"] > 0.0),
            "exposure_fraction": cells[0]["exposure_fraction"],
            "net_return": cells[0]["candidate_net_return"],
            "total_cost": candidate_result.fee_cost + candidate_result.slippage_cost,
            "maximum_drawdown": cells[0]["maximum_drawdown"],
            "benchmark_net_return": cells[0]["benchmark_net_return"],
            "excess_return_vs_benchmark": cells[0]["excess_return_vs_benchmark"],
        }
    else:
        cells = _panel_cells(candidate_result, benchmark_result)
        cell_semantics = "PORTFOLIO_ASSET_CONTRIBUTION"
        equity_curve = [candidate_result.initial_equity] + [row["equity_after_rebalance"] for row in candidate_path_rows]
        final_equity = candidate_path_rows[-1].get("final_equity") if candidate_path_rows else None
        if final_equity is not None and final_equity != equity_curve[-1]:
            equity_curve.append(final_equity)
        compact = {
            "observation_count": len(candidate_path_rows),
            "trade_count": sum(1 for row in candidate_path_rows if row["turnover"] > 0.0),
            "exposure_fraction": sum(1 for row in candidate_path_rows if any(abs(w) > 0.0 for w in row["target_weights"].values())) / len(candidate_path_rows),
            "net_return": candidate_result.final_pnl / candidate_result.initial_equity,
            "total_cost": candidate_result.fee_cost + candidate_result.slippage_cost,
            "maximum_drawdown": _max_drawdown(equity_curve),
            "benchmark_net_return": benchmark_result.final_pnl / benchmark_result.initial_equity,
            "excess_return_vs_benchmark": (candidate_result.final_pnl - benchmark_result.final_pnl) / candidate_result.initial_equity,
        }

    receipt = {
        "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
        "registered_screen_id": REGISTERED_SCREEN_ID,
        "registered_variant_denominator": REGISTERED_VARIANT_DENOMINATOR,
        "registered_scientific_cell_denominator": REGISTERED_SCIENTIFIC_CELL_DENOMINATOR,
        "candidate_id": candidate["candidate_id"],
        "family_id": family_id,
        "variant_id": variant_id,
        "parameters": parameters,
        "trial_id": trial_id,
        "breadth_v2_evaluation_id": evaluation_id,
        "execution_contract_digest": contract_digest_value,
        "execution_unit_type": execution_unit_type,
        "execution_unit_id": execution_unit_id,
        "instrument_contract_id": BINANCE_USDM_PERPETUAL_USDT_V1,
        "instrument_contract_digest": instrument_contract_digest(BINANCE_USDM_PERPETUAL_USDT_V1),
        "period_id": period_id,
        "evaluation_range": {"start": period_start, "end": period_end},
        "cost_mode": cost_mode,
        "fee_bps": cost["fee_bps"],
        "slippage_bps": cost["slippage_bps"],
        "funding_treatment": FUNDING_INCLUDED_PROVENANCE_BOUND,
        "evaluation_input_bundle_sha256": input_bundle["evaluation_input_bundle_sha256"],
        "input_bundle_payload_digest": _canonical_sha(payload),
        "repository_commit": commit,
        "relevant_source_sha256": source_sha,
        "benchmark_id": BENCHMARK_MAP[family_id],
        "candidate_result": {
            "equity": candidate_result.equity, "initial_equity": candidate_result.initial_equity,
            "turnover_notional": candidate_result.turnover_notional, "fee_cost": candidate_result.fee_cost,
            "slippage_cost": candidate_result.slippage_cost, "funding_pnl": candidate_result.funding_pnl,
            "price_pnl": candidate_result.price_pnl, "final_pnl": candidate_result.final_pnl,
        },
        "benchmark_result": {
            "equity": benchmark_result.equity, "initial_equity": benchmark_result.initial_equity,
            "turnover_notional": benchmark_result.turnover_notional, "fee_cost": benchmark_result.fee_cost,
            "slippage_cost": benchmark_result.slippage_cost, "funding_pnl": benchmark_result.funding_pnl,
            "price_pnl": benchmark_result.price_pnl, "final_pnl": benchmark_result.final_pnl,
        },
        "bar_path_schema_version": candidate_path_info["bar_path_schema_version"],
        "bar_path_sha256": candidate_path_info["bar_path_sha256"],
        "bar_path_row_count": candidate_path_info["bar_path_row_count"],
        "bar_path_first_timestamp": candidate_path_info["bar_path_first_timestamp"],
        "bar_path_last_timestamp": candidate_path_info["bar_path_last_timestamp"],
        "benchmark_path_sha256": benchmark_path_sha,
        "scientific_cell_count": len(cells),
        "cell_semantics": cell_semantics,
        "scientific_cells": cells,
        "compact_metrics": compact,
    }
    receipt_bytes = json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    receipt_sha = _sha_bytes(receipt_bytes)

    trial_event = research_ledger.build_trial_completed_event(
        receipt={
            **receipt,
            "research_intent": research_intent,
            "symbol": ledger_symbol,
            "gap_policy": "FAIL_CLOSED_NO_GAPS",
            "expected_interval": "1h",
            "fee_assumption": {"fee_bps": cost["fee_bps"]},
            "slippage_assumption": {"slippage_bps": cost["slippage_bps"]},
            "input_sha256": input_bundle["evaluation_input_bundle_sha256"],
            "research_generation": research_ledger.CORPUS_GENERATION_V2,
            "canonical_family_id": family_ontology.resolve_family(family_id),
        },
        receipt_path=Path(f"breadth_v2_receipts/{receipt_sha}.json"),
        receipt_sha256=receipt_sha,
        metrics=compact,
    )
    trial_event["breadth_v2_evaluation_id"] = evaluation_id
    trial_event["evaluation_input_bundle_sha256"] = input_bundle["evaluation_input_bundle_sha256"]
    trial_event["execution_contract_digest"] = contract_digest_value
    trial_event["execution_unit_type"] = execution_unit_type
    trial_event["execution_unit_id"] = execution_unit_id
    trial_event["scientific_cell_count"] = len(cells)
    trial_event["cell_semantics"] = cell_semantics
    trial_event["event_id"] = research_ledger.event_id("event_trial", trial_event)

    return PreparedEvaluation("READY", trial_event, receipt, receipt_bytes, candidate_path_rows, benchmark_path_rows, None)


def record_breadth_v2_evaluation(prepared: PreparedEvaluation, *, root: Path) -> dict[str, Any]:
    """Stage B: explicit evidence storage, canonical event append, index rebuild, doctor."""
    if prepared.status != "READY" or prepared.trial_event is None:
        raise RunnerBlocked(f"refusing to record a non-READY evaluation: {prepared.status}")
    root.mkdir(parents=True, exist_ok=True)
    receipts_dir = root / "breadth_v2_receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipts_dir / f"{prepared.trial_event['receipt_sha256']}.json"
    if not receipt_path.exists():
        receipt_path.write_bytes(prepared.receipt_bytes)
    paths_dir = root / "breadth_v2_paths"
    paths_dir.mkdir(parents=True, exist_ok=True)
    for kind, rows in (("candidate", prepared.candidate_path_rows), ("benchmark", prepared.benchmark_path_rows)):
        sha = path_digest(rows)
        path_file = paths_dir / f"{sha}.jsonl"
        if not path_file.exists():
            path_file.write_bytes(serialize_path(rows))
    research_ledger.append_canonical_event(prepared.trial_event, root=root)
    issues = research_ledger.doctor(root)
    if issues:
        raise RunnerBlocked(f"ledger doctor failed after Breadth V2 append: {issues}")
    return prepared.trial_event
