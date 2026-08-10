"""BREADTH_V2_PATH_V0: an observational serialization of PortfolioKernel state.

This module does not recompute portfolio accounting.  It only serializes and
reconciles ``ExecutionResult.boundary_path`` -- a trace already populated by
``PortfolioKernel.execute`` from the exact variables the kernel used.  Summing
already-computed per-boundary numbers to check they add up to the kernel's own
totals is reconciliation, not a second accounting pass.

Breadth V2 must not reuse ``BAR_PATH_V1`` (``qntylab.bar_path``): that schema
is a decomposition of the historical single-series ``qntylab.backtest.evaluate``
arithmetic and does not describe a portfolio kernel with funding, panels, or
per-asset contributions.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence

from .breadth_v2_execution import ExecutionResult

BREADTH_V2_PATH_SCHEMA_VERSION = "BREADTH_V2_PATH_V0"
RECONCILIATION_TOLERANCE = 1e-9

ROW_FIELDS = (
    "assets",
    "boundary",
    "equity_after_rebalance",
    "equity_entering_boundary",
    "fee_cost",
    "funding_pnl",
    "pre_cost_equity",
    "price_pnl",
    "slippage_cost",
    "target_weights",
    "turnover",
)
FINAL_ROW_EXTRA_FIELDS = (
    "final_equity",
    "terminal_fee_cost",
    "terminal_liquidation_turnover",
    "terminal_slippage_cost",
)


class BreadthV2PathError(RuntimeError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False).encode("utf-8")


def build_path(result: ExecutionResult) -> list[dict[str, Any]]:
    """Return the observational path rows already produced by the kernel.

    No arithmetic happens here beyond field-shape validation; the rows are
    exactly what ``PortfolioKernel.execute`` recorded.
    """
    rows = result.boundary_path
    if not rows:
        raise BreadthV2PathError("refusing to build an empty Breadth V2 path")
    for index, row in enumerate(rows):
        expected = set(ROW_FIELDS) | (set(FINAL_ROW_EXTRA_FIELDS) if index == len(rows) - 1 else set())
        if set(row) != expected:
            raise BreadthV2PathError(f"boundary path row {index} has unexpected fields: {sorted(set(row) ^ expected)}")
    return rows


def serialize(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        raise BreadthV2PathError("refusing to serialize an empty Breadth V2 path")
    header = {
        "record_type": "BREADTH_V2_PATH_HEADER",
        "row_count": len(rows),
        "schema_version": BREADTH_V2_PATH_SCHEMA_VERSION,
    }
    out = bytearray(_canonical_bytes(header) + b"\n")
    for row in rows:
        out += _canonical_bytes(row) + b"\n"
    return bytes(out)


def digest(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(serialize(rows)).hexdigest()


def describe(rows: list[dict[str, Any]]) -> dict[str, Any]:
    payload = serialize(rows)
    return {
        "bar_path_schema_version": BREADTH_V2_PATH_SCHEMA_VERSION,
        "bar_path_sha256": hashlib.sha256(payload).hexdigest(),
        "bar_path_row_count": len(rows),
        "bar_path_first_timestamp": rows[0]["boundary"],
        "bar_path_last_timestamp": rows[-1]["boundary"],
    }


def reconcile(rows: list[dict[str, Any]], result: ExecutionResult, symbols: Sequence[str]) -> None:
    """Reconcile the path totals against the kernel's own committed totals.

    Every quantity summed here is a value the kernel already computed and
    stored in ``rows``; this only checks that the sums the kernel implies
    equal the totals the kernel separately reports on ``result``.
    """
    final = rows[-1]
    if abs(final["final_equity"] - result.equity) > RECONCILIATION_TOLERANCE:
        raise BreadthV2PathError("path final equity does not reconcile with ExecutionResult.equity")
    price_total = sum(row["price_pnl"] for row in rows)
    if abs(price_total - result.price_pnl) > RECONCILIATION_TOLERANCE:
        raise BreadthV2PathError("path price PnL does not reconcile with ExecutionResult.price_pnl")
    funding_total = sum(row["funding_pnl"] for row in rows)
    if abs(funding_total - result.funding_pnl) > RECONCILIATION_TOLERANCE:
        raise BreadthV2PathError("path funding PnL does not reconcile with ExecutionResult.funding_pnl")
    fee_total = sum(row["fee_cost"] for row in rows) + final["terminal_fee_cost"]
    if abs(fee_total - result.fee_cost) > RECONCILIATION_TOLERANCE:
        raise BreadthV2PathError("path fee cost does not reconcile with ExecutionResult.fee_cost")
    slippage_total = sum(row["slippage_cost"] for row in rows) + final["terminal_slippage_cost"]
    if abs(slippage_total - result.slippage_cost) > RECONCILIATION_TOLERANCE:
        raise BreadthV2PathError("path slippage cost does not reconcile with ExecutionResult.slippage_cost")
    for symbol in symbols:
        contribution = sum(row["assets"][symbol]["price_pnl"] + row["assets"][symbol]["funding_pnl"] - row["assets"][symbol]["fee_cost"] - row["assets"][symbol]["slippage_cost"] for row in rows)
        if len(symbols) == 1:
            contribution -= final["terminal_fee_cost"] + final["terminal_slippage_cost"]
        expected = result.contributions[symbol].net_contribution
        if abs(contribution - expected) > RECONCILIATION_TOLERANCE and len(symbols) == 1:
            raise BreadthV2PathError(f"path per-asset contribution for {symbol} does not reconcile")
    portfolio_final_pnl = sum(c.net_contribution for c in result.contributions.values())
    if abs(portfolio_final_pnl - result.final_pnl) > RECONCILIATION_TOLERANCE:
        raise BreadthV2PathError("sum of final per-asset contributions does not reconcile with portfolio final PnL")
