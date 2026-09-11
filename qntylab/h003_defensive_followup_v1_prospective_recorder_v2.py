"""Fixture-only H003 prospective shadow recorder V2.

This module deliberately binds no network transport, scheduler, publication
surface, evaluator, Qnty authority, or QntySpot authority.  It turns already
materialized Binance Spot 1h kline rows into deterministic source manifests
and chained shadow signal receipts after re-validating the canonical H003 V2
ledger/origin authority.

The operational source adapter is a later, separate phase.  No economic
performance metric or interim verdict is computed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Sequence

import numpy as np

from .h003_defensive_followup_v1_origin_v2 import (
    EXPECTED_ORIGIN_UTC,
    build_origin_artifact,
    parse_utc,
    validate_artifact_canonicalization_time,
)
from .h003_defensive_followup_v1_prospective_reopen import (
    CANDIDATE_ID,
    REOPEN_EVENT_ID,
    VARIANT_ID,
    prospective_h003_positions,
)


ROOT = Path(__file__).resolve().parents[1]
ORIGIN_ARTIFACT_RELATIVE_PATH = "experiments/research/h003_defensive_followup_v1/prospective_origin_v2.json"
ORIGIN_ARTIFACT_PATH = ROOT / ORIGIN_ARTIFACT_RELATIVE_PATH
ORIGIN_V2_CANONICAL_MERGE_SHA = "1e9fb3afd2f63f663c12f288dea62b2f446d017d"
ORIGIN_V2_CANONICAL_MERGE_UTC = "2026-09-11T20:06:36Z"
PANEL = ("SOLUSDT", "BTCUSDT", "ETHUSDT")
INTERVAL = "1h"
FAST = 48
SLOW = 192
HOUR_MS = 3_600_000
SPOT_SOURCE_ID = "Binance Spot public 1h kline 12-field contract"
NETWORK_TRANSPORT = "UNBOUND_FIXTURE_ONLY"


class RecorderBlocked(ValueError):
    """The H003 prospective recorder rejects an authority or data boundary."""


@dataclass(frozen=True)
class SpotBar:
    symbol: str
    open_time_utc: datetime
    logical_close_utc: datetime
    close: float
    raw_row: tuple[Any, ...]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def _stamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise RecorderBlocked("timezone-aware timestamp required")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _hour(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise RecorderBlocked("timezone-aware timestamp required")
    value = value.astimezone(UTC)
    if value.minute or value.second or value.microsecond:
        raise RecorderBlocked("hour-aligned timestamp required")
    return value


def _git_text(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RecorderBlocked(f"canonical Git authority unavailable: {' '.join(args)}") from exc


def validate_recorder_authority(root: Path = ROOT) -> dict[str, Any]:
    """Re-derive recorder authority from canonical Git and frozen artifacts.

    The canonicalization timestamp is never caller supplied.  It is read from
    the fixed PR #269 merge commit, verified against the frozen timestamp, and
    passed through the strict-before-origin guard.  The exact origin artifact
    bytes at that merge commit must equal the current checked-out artifact.
    """
    origin_path = root / ORIGIN_ARTIFACT_RELATIVE_PATH
    artifact = json.loads(origin_path.read_text(encoding="utf-8"))
    if artifact != build_origin_artifact():
        raise RecorderBlocked("origin-v2 artifact no longer matches its canonical builder")

    merge_timestamp = _git_text(root, "show", "-s", "--format=%cI", ORIGIN_V2_CANONICAL_MERGE_SHA)
    if parse_utc(merge_timestamp) != parse_utc(ORIGIN_V2_CANONICAL_MERGE_UTC):
        raise RecorderBlocked("origin-v2 canonical merge timestamp changed")
    canonicalized = validate_artifact_canonicalization_time(merge_timestamp)

    try:
        committed_bytes = subprocess.check_output(
            ["git", "show", f"{ORIGIN_V2_CANONICAL_MERGE_SHA}:{ORIGIN_ARTIFACT_RELATIVE_PATH}"],
            cwd=root,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RecorderBlocked("canonical origin artifact is unavailable from its merge commit") from exc
    if committed_bytes != origin_path.read_bytes():
        raise RecorderBlocked("checked-out origin artifact differs from canonical merge bytes")

    try:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ORIGIN_V2_CANONICAL_MERGE_SHA, "HEAD"],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RecorderBlocked("current checkout does not descend from canonical origin-v2 merge") from exc

    authority = artifact.get("recorder_authority", {})
    if authority.get("unconditional_recording_authority") is not False:
        raise RecorderBlocked("origin artifact unexpectedly grants unconditional recording authority")
    if authority.get("canonicalization_time_guard_function") != "validate_artifact_canonicalization_time":
        raise RecorderBlocked("origin canonicalization guard binding changed")
    if artifact.get("candidate_id") != CANDIDATE_ID or artifact.get("variant_id") != VARIANT_ID:
        raise RecorderBlocked("origin artifact candidate identity changed")
    if artifact.get("prospective_reopen_event_id") != REOPEN_EVENT_ID:
        raise RecorderBlocked("origin artifact ledger generation changed")

    return {
        "origin_v2_canonical_merge_sha": ORIGIN_V2_CANONICAL_MERGE_SHA,
        "origin_v2_canonicalized_at_utc": _stamp(canonicalized),
        "prospective_origin_utc": EXPECTED_ORIGIN_UTC,
        "reopen_event_id": REOPEN_EVENT_ID,
        "candidate_id": CANDIDATE_ID,
        "variant_id": VARIANT_ID,
    }


def first_required_logical_close() -> datetime:
    return parse_utc(EXPECTED_ORIGIN_UTC) - timedelta(hours=SLOW - 1)


def spot_bar_from_row(symbol: str, row: Sequence[Any]) -> SpotBar:
    """Map one exact Binance Spot 1h 12-field row to a logical close."""
    if symbol not in PANEL:
        raise RecorderBlocked(f"non-panel symbol rejected: {symbol}")
    if len(row) != 12:
        raise RecorderBlocked("Binance Spot kline row must contain exactly 12 fields")
    try:
        open_ms = int(row[0])
        close_value = float(row[4])
        close_ms = int(row[6])
    except (TypeError, ValueError) as exc:
        raise RecorderBlocked("malformed Binance Spot kline row") from exc
    if open_ms % HOUR_MS:
        raise RecorderBlocked("Spot kline open time is not hour aligned")
    if close_ms != open_ms + HOUR_MS - 1:
        raise RecorderBlocked("Spot kline is not an exact 1h interval")
    if not math.isfinite(close_value) or close_value <= 0:
        raise RecorderBlocked("Spot kline close must be finite and positive")
    opened = datetime.fromtimestamp(open_ms / 1000, UTC)
    logical_close = datetime.fromtimestamp((close_ms + 1) / 1000, UTC)
    if logical_close != opened + timedelta(hours=1):
        raise RecorderBlocked("provider timestamps do not map to the logical close")
    return SpotBar(symbol, opened, logical_close, close_value, tuple(row))


def validate_bars(bars: Sequence[SpotBar], *, through_logical_close: datetime) -> tuple[SpotBar, ...]:
    through = _hour(through_logical_close)
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    if through < origin:
        raise RecorderBlocked("prospective recorder cannot emit before origin")
    first = first_required_logical_close()
    expected_count = int((through - first).total_seconds() // 3600) + 1
    by_symbol: dict[str, list[SpotBar]] = {symbol: [] for symbol in PANEL}
    seen: set[tuple[str, datetime]] = set()

    for bar in bars:
        if bar.symbol not in by_symbol:
            raise RecorderBlocked(f"non-panel symbol rejected: {bar.symbol}")
        if bar.logical_close_utc < first or bar.logical_close_utc > through:
            raise RecorderBlocked("bar outside exact required warmup/recording window")
        if bar.open_time_utc + timedelta(hours=1) != bar.logical_close_utc:
            raise RecorderBlocked("bar logical-close mapping changed")
        key = (bar.symbol, bar.logical_close_utc)
        if key in seen:
            raise RecorderBlocked("duplicate symbol/logical-close row")
        seen.add(key)
        by_symbol[bar.symbol].append(bar)

    for symbol in PANEL:
        rows = sorted(by_symbol[symbol], key=lambda item: item.logical_close_utc)
        if len(rows) != expected_count:
            raise RecorderBlocked(f"incomplete source coverage for {symbol}")
        if rows[0].logical_close_utc != first or rows[-1].logical_close_utc != through:
            raise RecorderBlocked(f"source coverage boundary mismatch for {symbol}")
        for left, right in zip(rows, rows[1:]):
            if right.logical_close_utc - left.logical_close_utc != timedelta(hours=1):
                raise RecorderBlocked(f"source gap for {symbol}")

    return tuple(sorted(bars, key=lambda item: (item.logical_close_utc, PANEL.index(item.symbol))))


def build_source_manifest(bars: Sequence[SpotBar], *, through_logical_close: datetime) -> dict[str, Any]:
    ordered = validate_bars(bars, through_logical_close=through_logical_close)
    value = {
        "source_contract": SPOT_SOURCE_ID,
        "network_transport": NETWORK_TRANSPORT,
        "market": "Binance Spot",
        "interval": INTERVAL,
        "ordered_panel": list(PANEL),
        "first_required_logical_close_utc": _stamp(first_required_logical_close()),
        "through_logical_close_utc": _stamp(_hour(through_logical_close)),
        "rows": [
            {
                "symbol": bar.symbol,
                "logical_close_utc": _stamp(bar.logical_close_utc),
                "raw_row_sha256": sha256(canonical_bytes(bar.raw_row)).hexdigest(),
            }
            for bar in ordered
        ],
    }
    return {**value, "source_manifest_sha256": digest(value)}


def build_signal_receipts(
    bars: Sequence[SpotBar],
    *,
    through_logical_close: datetime,
    previous_chain_sha256: str | None = None,
) -> tuple[dict[str, Any], ...]:
    ordered = validate_bars(bars, through_logical_close=through_logical_close)
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    by_symbol = {symbol: [bar for bar in ordered if bar.symbol == symbol] for symbol in PANEL}
    positions: dict[tuple[str, datetime], float] = {}
    for symbol, rows in by_symbol.items():
        close = np.asarray([bar.close for bar in rows], dtype=float)
        path = prospective_h003_positions(close)
        for bar, position in zip(rows, path):
            positions[(symbol, bar.logical_close_utc)] = float(position)

    chain = previous_chain_sha256
    receipts: list[dict[str, Any]] = []
    for bar in ordered:
        if bar.logical_close_utc < origin:
            continue
        position = positions[(bar.symbol, bar.logical_close_utc)]
        receipt_body = {
            "schema_version": "1.0.0",
            "record_class": "H003_PROSPECTIVE_SHADOW_SIGNAL_FACT",
            "candidate_id": CANDIDATE_ID,
            "variant_id": VARIANT_ID,
            "reopen_event_id": REOPEN_EVENT_ID,
            "origin_v2_canonical_merge_sha": ORIGIN_V2_CANONICAL_MERGE_SHA,
            "prospective_origin_utc": EXPECTED_ORIGIN_UTC,
            "market": "Binance Spot",
            "symbol": bar.symbol,
            "interval": INTERVAL,
            "logical_close_utc": _stamp(bar.logical_close_utc),
            "close_raw_row_sha256": sha256(canonical_bytes(bar.raw_row)).hexdigest(),
            "position": position,
            "state": "LONG" if position > 0 else "FLAT",
            "owned_interval_start_utc": _stamp(bar.logical_close_utc),
            "owned_interval_end_utc": _stamp(bar.logical_close_utc + timedelta(hours=1)),
            "position_changed_from_previous_prospective_bar": (
                False
                if bar.logical_close_utc == origin
                else position != positions[(bar.symbol, bar.logical_close_utc - timedelta(hours=1))]
            ),
            "economic_performance_metric": "NOT_COMPUTED",
            "interim_economic_verdict": "FORBIDDEN",
            "live_execution": "FORBIDDEN",
            "qnty_acceptance": "NONE",
            "qntyspot_policy": "NONE",
            "previous_receipt_sha256": chain,
        }
        receipt_sha = digest(receipt_body)
        receipt = {**receipt_body, "receipt_sha256": receipt_sha}
        receipts.append(receipt)
        chain = receipt_sha
    if not receipts:
        raise RecorderBlocked("no prospective receipts emitted")
    return tuple(receipts)


def build_fixture_bundle(
    bars: Sequence[SpotBar],
    *,
    through_logical_close: datetime,
    previous_chain_sha256: str | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    authority = validate_recorder_authority(root)
    manifest = build_source_manifest(bars, through_logical_close=through_logical_close)
    receipts = build_signal_receipts(
        bars,
        through_logical_close=through_logical_close,
        previous_chain_sha256=previous_chain_sha256,
    )
    value = {
        "schema_version": "1.0.0",
        "implementation_scope": "FIXTURE_ONLY_NO_NETWORK_NO_SCHEDULER_NO_ECONOMIC_VERDICT",
        "authority": authority,
        "source_manifest": manifest,
        "receipts": list(receipts),
        "receipt_chain_tip_sha256": receipts[-1]["receipt_sha256"],
        "network_transport": NETWORK_TRANSPORT,
        "economic_verdict": "FORBIDDEN",
        "publication": "NONE",
        "live_execution": "FORBIDDEN",
    }
    return {**value, "bundle_sha256": digest(value)}


__all__ = [
    "FAST",
    "INTERVAL",
    "NETWORK_TRANSPORT",
    "ORIGIN_V2_CANONICAL_MERGE_SHA",
    "ORIGIN_V2_CANONICAL_MERGE_UTC",
    "PANEL",
    "RecorderBlocked",
    "SLOW",
    "SPOT_SOURCE_ID",
    "SpotBar",
    "build_fixture_bundle",
    "build_signal_receipts",
    "build_source_manifest",
    "first_required_logical_close",
    "spot_bar_from_row",
    "validate_bars",
    "validate_recorder_authority",
]
