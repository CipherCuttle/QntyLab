"""Deterministic per-bar path emission and content-addressed storage (Seam 3).

V1 trials retained nine scalar metrics per cell and nothing else, which blocks
family distinctness diagnostics, any risk-adjusted metric, and every multiplicity
diagnostic that needs matched per-bar differentials.  V2 trials emit a per-bar
path prospectively.  Historical trials are NOT backfilled -- V1 stays a
summary-only corpus generation.

Accounting semantics are taken verbatim from ``qntylab.backtest.evaluate``; this
module decomposes that existing arithmetic, it does not introduce a second
accounting model.  For row ``i`` of ``N-1`` rows over ``N`` evaluation bars:

    asset_return[i]            = close[i+1] / close[i] - 1
    position_before_return[i]  = position[i]
    gross_strategy_return[i]   = position[i] * asset_return[i]
    turnover[i]                = abs(position[i+1] - position[i])
    fee_cost[i]                = turnover[i] * fee_bps / 10_000
    slippage_cost[i]           = turnover[i] * slippage_bps / 10_000
    net_strategy_return[i]     = gross - fee - slippage - funding
    cumulative_return[i]       = prod(1 + net[:i+1]) - 1

The combined ``fee_cost + slippage_cost`` reproduces ``evaluate``'s single
``fees`` term exactly, so a bar path can never double-count costs relative to the
committed scalar metrics.  ``verify_against_metrics`` asserts that.

COST CHARGE TIMING -- read before analysing turnover or cost attribution.  Row
``i`` reports the position *held* over period ``i`` (``position[i]``) and, in the
same row, the cost of transitioning *into* ``position[i+1]``.  Those are two
different instants deliberately kept on one row because that is exactly what
``evaluate`` does; this module reproduces the committed accounting rather than
correcting it.  Consequently ``turnover``/``fee_cost``/``slippage_cost`` on row
``i`` describe the trade at the *end* of period ``i``, not a trade that produced
``position_before_return``.  A per-bar analysis that attributes cost to the
position shown on the same row will misattribute by one bar.

Bytes live outside Git.  The run receipt commits only the digest and shape, so
scientific identity depends on the digest, not on a filesystem location.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np

BAR_PATH_SCHEMA_VERSION = "BAR_PATH_V1"
EVIDENCE_ROOT_ENV = "QNTYLAB_EVIDENCE_ROOT"
DEFAULT_EVIDENCE_ROOT = Path.home() / ".qntylab" / "evidence"

BAR_PATH_FIELDS = (
    "timestamp",
    "position_before_return",
    "asset_return",
    "gross_strategy_return",
    "turnover",
    "fee_cost",
    "slippage_cost",
    "funding_cost",
    "net_strategy_return",
    "cumulative_return",
)

# Tolerance for reconciling the compounded path against committed scalar metrics.
# Both sides are float64 over the same arithmetic, so drift is pure accumulation
# order, not a modelling difference.
RECONCILIATION_TOLERANCE = 1e-9


class BarPathError(RuntimeError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def evidence_root() -> Path:
    override = os.environ.get(EVIDENCE_ROOT_ENV)
    return Path(override) if override else DEFAULT_EVIDENCE_ROOT


def build_bar_path(
    *,
    timestamps: list[str],
    close: np.ndarray,
    position: np.ndarray,
    fee_bps: float,
    slippage_bps: float,
    funding_cost_per_bar: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    """Build the per-bar path for one evaluation window.

    ``timestamps``, ``close`` and ``position`` are the evaluation-window series
    (warmup already stripped) and must be the exact arrays passed to the metrics
    computation, so the path and the scalars describe the same run.
    """
    if len(close) != len(position) or len(timestamps) != len(close):
        raise BarPathError("timestamps, close and position must be the same length")
    if len(close) < 3:
        raise BarPathError("matching close/position series of at least 3 required")
    if not np.all(np.isfinite(close)) or not np.all(np.isfinite(position)):
        raise BarPathError("non-finite close or position values")

    returns = close[1:] / close[:-1] - 1
    held = position[:-1]
    changes = np.abs(np.diff(position))
    gross = held * returns
    fee = changes * float(fee_bps) / 10_000.0
    slippage = changes * float(slippage_bps) / 10_000.0
    if funding_cost_per_bar is None:
        funding = np.zeros(len(returns), dtype=float)
    else:
        funding = np.asarray(funding_cost_per_bar, dtype=float)
        if len(funding) != len(returns):
            raise BarPathError("funding_cost_per_bar must have one entry per return period")
        if not np.all(np.isfinite(funding)):
            raise BarPathError("non-finite funding cost")
    net = gross - fee - slippage - funding
    cumulative = np.cumprod(1.0 + net) - 1.0

    rows: list[dict[str, Any]] = []
    for index in range(len(returns)):
        rows.append(
            {
                "timestamp": timestamps[index],
                "position_before_return": float(held[index]),
                "asset_return": float(returns[index]),
                "gross_strategy_return": float(gross[index]),
                "turnover": float(changes[index]),
                "fee_cost": float(fee[index]),
                "slippage_cost": float(slippage[index]),
                "funding_cost": float(funding[index]),
                "net_strategy_return": float(net[index]),
                "cumulative_return": float(cumulative[index]),
            }
        )
    for row in rows:
        for value in row.values():
            if isinstance(value, float) and not np.isfinite(value):
                raise BarPathError("non-finite bar-path value")
    return rows


def serialize(rows: list[dict[str, Any]]) -> bytes:
    """Canonical byte serialization: one sorted-key JSON object per line.

    Deterministic for identical inputs -- ``json.dumps`` emits shortest
    round-trip float representations, and key order is fixed by ``sort_keys``.
    """
    if not rows:
        raise BarPathError("refusing to serialize an empty bar path")
    header = {
        "field_order": list(BAR_PATH_FIELDS),
        "record_type": "BAR_PATH_HEADER",
        "row_count": len(rows),
        "schema_version": BAR_PATH_SCHEMA_VERSION,
    }
    out = bytearray(_canonical_bytes(header) + b"\n")
    for row in rows:
        if set(row) != set(BAR_PATH_FIELDS):
            raise BarPathError(f"bar-path row fields must be exactly {list(BAR_PATH_FIELDS)}")
        out += _canonical_bytes(row) + b"\n"
    return bytes(out)


def digest(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(serialize(rows)).hexdigest()


def verify_against_metrics(rows: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    """Reconcile the path against the committed scalar metrics.

    Guards the two failure modes that matter: cost double-counting (path costs
    must sum to the committed ``total_cost``) and a path that describes a
    different run than the metrics (terminal compounded return must match
    ``net_return``).
    """
    if len(rows) != int(metrics["observation_count"]):
        raise BarPathError(
            f"bar-path row count {len(rows)} does not match observation_count {metrics['observation_count']}"
        )
    path_cost = sum(row["fee_cost"] + row["slippage_cost"] for row in rows)
    if abs(path_cost - float(metrics["total_cost"])) > RECONCILIATION_TOLERANCE:
        raise BarPathError(
            f"bar-path cost {path_cost!r} does not reconcile with committed total_cost {metrics['total_cost']!r}"
        )
    if abs(rows[-1]["cumulative_return"] - float(metrics["net_return"])) > RECONCILIATION_TOLERANCE:
        raise BarPathError(
            f"bar-path terminal cumulative_return {rows[-1]['cumulative_return']!r} does not reconcile "
            f"with committed net_return {metrics['net_return']!r}"
        )
    if "gross_return" in metrics:
        path_gross = 1.0
        for row in rows:
            path_gross *= 1.0 + row["gross_strategy_return"]
        if abs((path_gross - 1.0) - float(metrics["gross_return"])) > RECONCILIATION_TOLERANCE:
            raise BarPathError(
                f"bar-path compounded gross {path_gross - 1.0!r} does not reconcile with committed "
                f"gross_return {metrics['gross_return']!r}"
            )
    turnover_trades = sum(1 for row in rows if row["turnover"] != 0.0)
    if turnover_trades != int(metrics["trade_count"]):
        raise BarPathError(
            f"bar-path non-zero turnover count {turnover_trades} does not match trade_count {metrics['trade_count']}"
        )


def store_path_for_digest(bar_path_sha256: str, root: Path | None = None) -> Path:
    if len(bar_path_sha256) != 64 or not all(char in "0123456789abcdef" for char in bar_path_sha256):
        raise BarPathError(f"invalid bar-path digest: {bar_path_sha256!r}")
    base = root or evidence_root()
    return base / "bar_paths" / BAR_PATH_SCHEMA_VERSION / bar_path_sha256[:2] / f"{bar_path_sha256}.jsonl"


def store(rows: list[dict[str, Any]], root: Path | None = None) -> dict[str, Any]:
    """Write the path to content-addressed storage outside Git and describe it.

    Returns exactly the fields the run receipt commits.  A digest that already
    exists is left untouched -- identical content is identical evidence.
    """
    payload = serialize(rows)
    bar_path_sha256 = hashlib.sha256(payload).hexdigest()
    target = store_path_for_digest(bar_path_sha256, root)
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != bar_path_sha256:
            raise BarPathError(f"content-addressed collision or corruption at {target}")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".jsonl.partial")
        temporary.write_bytes(payload)
        temporary.replace(target)
    return {
        "bar_path_schema_version": BAR_PATH_SCHEMA_VERSION,
        "bar_path_sha256": bar_path_sha256,
        "bar_path_row_count": len(rows),
        "bar_path_first_timestamp": rows[0]["timestamp"],
        "bar_path_last_timestamp": rows[-1]["timestamp"],
    }


def load(bar_path_sha256: str, root: Path | None = None) -> list[dict[str, Any]]:
    target = store_path_for_digest(bar_path_sha256, root)
    if not target.exists():
        raise BarPathError(f"bar path not present in evidence store: {bar_path_sha256}")
    payload = target.read_bytes()
    if hashlib.sha256(payload).hexdigest() != bar_path_sha256:
        raise BarPathError(f"bar path digest mismatch on read: {bar_path_sha256}")
    lines = payload.decode("utf-8").splitlines()
    header = json.loads(lines[0])
    if header.get("schema_version") != BAR_PATH_SCHEMA_VERSION:
        raise BarPathError(f"unsupported bar-path schema: {header.get('schema_version')!r}")
    rows = [json.loads(line) for line in lines[1:] if line.strip()]
    if len(rows) != header["row_count"]:
        raise BarPathError("bar-path row count does not match header")
    return rows
