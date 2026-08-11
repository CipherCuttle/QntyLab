"""Reliable, deterministic invocation of the already-frozen Breadth V2 sealed
forward source materializers.

`BREADTH_V2_SEALED_OBSERVATION_ACTIVATION_V0`.  This module adds exactly one
missing mechanic: a way to actually *call*
``qntylab.binance_um_kline_1h.materialize`` and
``qntylab.binance_um_funding_settlement.materialize`` -- unchanged, by
reference -- on a schedule, catching up deterministically from whatever was
last materialized.  It performs no strategy execution, no PnL, no sealed
adjudication, and no input-bundle construction.  It does not change
``SEALED_T0``, the eligible families/variants, or any source contract.

Why this exists: before this module, both materializers existed and were
covered by unit tests, but nothing in the repository, in a crontab, or in a
systemd unit ever called them for the sealed forward window.  Calling this
module's :func:`sync_sealed_observation` (directly, or via its
``python -m`` entrypoint) from any external scheduler is the smallest seam
that turns "machinery capable of accumulating evidence" into "evidence
actually being accumulated" -- the scheduling itself is left external
(operator/cron/systemd), consistent with the frozen sealed forward contract,
which explicitly leaves real accumulation to "whatever process already runs
the general 1h kline materializer".
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

import requests

from . import binance_um_funding_settlement, binance_um_kline_1h
from .breadth_v2_input_bundle import PANEL_ORDER
from .breadth_v2_sealed import SEALED_T0

# The full sealed-forward source universe: the three single-asset variant
# symbols plus the frozen 20-asset panel.  Reused by reference, not
# reconstructed -- ``PANEL_ORDER`` is the same tuple ``breadth_v2_input_bundle``
# already freezes.
SINGLE_ASSET_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
SEALED_OBSERVATION_UNIVERSE = tuple(dict.fromkeys(SINGLE_ASSET_SYMBOLS + PANEL_ORDER))

PRICE_MANIFEST_SUFFIX = "-perp-1h-hourly-input-v0.json"
FUNDING_MANIFEST_SUFFIX = "-perp-funding-events-v0.json"

# Runs whose overall "did every symbol succeed" health can be checked without
# inspecting any economic quantity.
RUN_LOG_DIR = "data/receipts/breadth_v2_sealed_observation_sync_runs"


def _price_manifest_path(root: Path, symbol: str) -> Path:
    return root / "data" / "manifests" / f"{symbol}{PRICE_MANIFEST_SUFFIX}"


def _funding_manifest_path(root: Path, symbol: str) -> Path:
    return root / "data" / "manifests" / f"{symbol}{FUNDING_MANIFEST_SUFFIX}"


def safe_catch_up_end(as_of: datetime) -> datetime:
    """Latest UTC hour it is deterministically safe to request.

    Both materializers ("complete_archive_months_only") can only admit whole
    published archive months; the archive for a given calendar month is not
    published until after that month ends. Requesting anything in the
    still-open current month would make ``materialize`` treat every symbol as
    blocked (``SOURCE_OBJECT_ABSENT``) for the *entire* requested range, not
    just the missing tail. This function is the one place that boundary is
    computed, so every caller (real sync, tests) agrees on it.
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    as_of = as_of.astimezone(UTC)
    first_of_month = as_of.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return first_of_month - timedelta(hours=1)


def _resume_start(manifest_path: Path, last_timestamp_key: str) -> datetime:
    """Deterministic catch-up start: one hour after the last normalized
    timestamp already on disk for this exact materializer's own manifest, or
    ``SEALED_T0`` if none exists yet.

    Deliberately does not consult any other materializer's manifest (e.g. the
    unrelated, pre-existing ``qntylab.data`` bulk-history files): those are a
    different source identity and pre-date the sealed forward window. Nothing
    before ``SEALED_T0`` is ever treated as sealed-forward-observation
    coverage by this function.
    """
    if not manifest_path.exists():
        return SEALED_T0
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        last = manifest.get(last_timestamp_key)
        if not last:
            return SEALED_T0
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00")).astimezone(UTC)
    except (json.JSONDecodeError, ValueError, AttributeError):
        # A truncated/corrupt manifest (e.g. a prior run killed mid-write)
        # must not crash the batch. Falling back to SEALED_T0 is safe, not
        # silently-wrong: it can only cause a redundant re-request of an
        # already-covered range (idempotent, checksum-reverified), never a
        # skipped one.
        return SEALED_T0
    return max(last_dt + timedelta(hours=1), SEALED_T0)


MaterializeFn = Callable[..., dict[str, Any]]


def _invoke(
    materialize_fn: MaterializeFn,
    *,
    symbol: str,
    next_needed: datetime,
    end: datetime,
    root: Path,
    session: requests.Session | None,
) -> dict[str, Any]:
    """Call one materializer for one asset, failing closed.

    Two things matter here beyond the obvious call-through:

    1. If nothing new is due (``next_needed > end``) this makes zero calls
       and zero writes -- the idempotent no-op case.
    2. When something *is* due, the request always starts at ``SEALED_T0``,
       not at ``next_needed``. Both frozen materializers *overwrite* (not
       append) their on-disk raw CSV/JSONL and manifest on every call
       (``binance_um_kline_1h.materialize`` / ``binance_um_funding_settlement.
       materialize``, unmodified). Requesting only the incremental slice
       would make each run's raw/manifest file replace, not extend, the
       previous run's -- silently discarding earlier months' materialized
       data on disk. Requesting the full ``[SEALED_T0, end]`` range every
       time a new complete month is due means each successful run's on-disk
       artifact is the complete cumulative sealed-forward coverage so far;
       archive months already fetched are simply re-verified against their
       checksum, which is what "idempotent" already means for these
       materializers.
    """
    if next_needed > end:
        return {"status": "NOT_YET_DUE", "requested_start": None, "requested_end": None}
    start_stamp = SEALED_T0.isoformat().replace("+00:00", "Z")
    end_stamp = end.isoformat().replace("+00:00", "Z")
    try:
        result = materialize_fn(symbol, SEALED_T0, end, root, session=session)
    except Exception as exc:  # noqa: BLE001 - the materializers themselves do not
        # catch transport-level failures (non-404 HTTP errors, connection
        # resets, timeouts) from their own `requests` calls; this is the
        # fail-closed backstop so one symbol's transient network failure
        # is reported, not left to crash the rest of the batch.
        return {
            "status": "ACQUISITION_FAILED",
            "requested_start": start_stamp,
            "requested_end": end_stamp,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {"status": result["status"], "requested_start": start_stamp, "requested_end": end_stamp}


def _sync_one(
    *,
    symbol: str,
    root: Path,
    as_of: datetime,
    session: requests.Session | None,
    materialize_price: MaterializeFn,
    materialize_funding: MaterializeFn,
) -> dict[str, Any]:
    end = safe_catch_up_end(as_of)
    price_next = _resume_start(_price_manifest_path(root, symbol), "normalized_last_timestamp")
    funding_next = _resume_start(_funding_manifest_path(root, symbol), "normalized_last_funding_time")

    return {
        "symbol": symbol,
        "price": _invoke(materialize_price, symbol=symbol, next_needed=price_next, end=end, root=root, session=session),
        "funding": _invoke(materialize_funding, symbol=symbol, next_needed=funding_next, end=end, root=root, session=session),
    }


def sync_sealed_observation(
    root: Path,
    *,
    as_of: datetime | None = None,
    symbols: Sequence[str] | None = None,
    session: requests.Session | None = None,
    now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    materialize_price: MaterializeFn = binance_um_kline_1h.materialize,
    materialize_funding: MaterializeFn = binance_um_funding_settlement.materialize,
) -> dict[str, Any]:
    """Invoke the frozen materializers, once per symbol, for whatever
    complete-month range has not yet been materialized.

    ``materialize_price``/``materialize_funding`` default to the frozen,
    unmodified materializers (``binance_um_kline_1h.materialize`` /
    ``binance_um_funding_settlement.materialize``); tests inject fixtures
    with the same call signature instead of re-proving those already
    independently-tested modules.

    Idempotent: rerunning with no new complete months available yields
    ``NOT_YET_DUE`` for every symbol/asset and writes nothing new. Fails
    closed per symbol/asset: a materializer ``BLOCKED`` result is reported
    as ``BLOCKED``, never silently upgraded to success, and never aborts the
    remaining symbols in the batch.
    """
    as_of = as_of if as_of is not None else now_fn()
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    as_of = as_of.astimezone(UTC)
    resolved_symbols = tuple(symbols) if symbols is not None else SEALED_OBSERVATION_UNIVERSE
    client = session or requests.Session()

    results = [
        _sync_one(
            symbol=symbol,
            root=root,
            as_of=as_of,
            session=client,
            materialize_price=materialize_price,
            materialize_funding=materialize_funding,
        )
        for symbol in resolved_symbols
    ]

    run = {
        "contract_id": "BREADTH_V2_SEALED_OBSERVATION_ACTIVATION_V0",
        "sealed_t0": SEALED_T0.isoformat().replace("+00:00", "Z"),
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "safe_catch_up_end": safe_catch_up_end(as_of).isoformat().replace("+00:00", "Z"),
        "symbols": results,
        "all_succeeded": all(
            asset["status"] in {"MATERIALIZED_VERIFIED", "NOT_YET_DUE"}
            for row in results
            for asset in (row["price"], row["funding"])
        ),
    }

    log_dir = root / RUN_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = as_of.strftime("%Y%m%dT%H%M%SZ")
    (log_dir / f"{stamp}.json").write_text(json.dumps(run, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    return run


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Sync Breadth V2 sealed forward observation sources")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    run = sync_sealed_observation(args.root)
    print(json.dumps(run, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
