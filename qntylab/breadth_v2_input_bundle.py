"""Strict, pure input identity for Breadth V2.

This module only admits authenticated, already-materialized fixture objects.  It
does not acquire data, run strategies, or persist bundles.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Sequence

from .breadth_v2_execution import DECISION_CLOCK_ID, INSTRUMENT_CONTRACT_ID, evaluation_input_bundle_sha256, registered_candidate_mappings

CONTRACT = "BREADTH_V2_INPUT_BUNDLE_V0"
PRICE_CONTRACT_VERSION = "BINANCE_USD_M_PERPETUAL_1H_MATERIALIZER_V0"
FUNDING_CONTRACT_VERSION = "BINANCE_USDM_FUNDING_SETTLEMENT_MATERIALIZER_V0"
PANEL_ORDER = (
    "BCHUSDT", "XRPUSDT", "LTCUSDT", "TRXUSDT", "ETCUSDT", "LINKUSDT",
    "XLMUSDT", "CHZUSDT", "SANDUSDT", "REEFUSDT", "CHRUSDT", "ALICEUSDT",
    "ONEUSDT", "API3USDT", "GMTUSDT", "APEUSDT", "OPUSDT", "INJUSDT",
    "LDOUSDT", "APTUSDT",
)
_ASSET_KEYS = frozenset({"price_parent_content", "price_content", "price_provenance", "funding_parent_content", "funding_content", "funding_provenance", "coverage"})
_PRICE_SOURCE_CACHE: dict[str, tuple[list[dict[str, str]], dict[str, Any], bytes]] = {}
_FUNDING_SOURCE_CACHE: dict[str, tuple[list[dict[str, Any]], dict[str, Any], bytes]] = {}
_PRICE_CLIP_CACHE: dict[tuple[str, str, str], tuple[list[dict[str, str]], bytes, list[str]]] = {}
_FUNDING_CLIP_CACHE: dict[tuple[str, str, int], tuple[list[dict[str, Any]], bytes, int]] = {}


class InputBundleBlocked(ValueError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(value: Any) -> str:
    return _sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode())


def _utc_hour(value: str | datetime) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("evaluation boundary must be timezone-aware UTC")
    value = value.astimezone(UTC)
    if value.minute or value.second or value.microsecond:
        raise ValueError("evaluation boundary must be exactly hour aligned")
    return value


def _stamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _event_ms(event: Mapping[str, Any]) -> int:
    value = event.get("funding_time_ms")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("funding_time_ms must be a non-negative integer")
    return value


def funding_admission_boundary(funding_time_ms: int) -> str:
    """Return the first UTC hourly boundary at or after an exact event time."""
    if not isinstance(funding_time_ms, int) or isinstance(funding_time_ms, bool) or funding_time_ms < 0:
        raise ValueError("funding_time_ms must be a non-negative integer")
    value = datetime.fromtimestamp(funding_time_ms / 1000, UTC)
    boundary = value.replace(minute=0, second=0, microsecond=0)
    if value != boundary:
        boundary += timedelta(hours=1)
    return _stamp(boundary)


def price_admission_boundary(source_open_time: str | datetime) -> str:
    """A 1h source bar's close is admitted one hour after its open."""
    value = _utc_hour(source_open_time)
    return _stamp(value + timedelta(hours=1))


def required_history_for_variant(family: str, parameters: Mapping[str, Any]) -> dict[str, int]:
    """Return only the observations required by the canonical strategy code."""
    family = str(family).upper()
    if family in {"TIME_SERIES_MOMENTUM", "PRICE_BREAKOUT", "CROSS_SECTIONAL_MOMENTUM", "CROSS_SECTIONAL_REVERSAL"}:
        n = int(parameters["lookback"]) + 1
        return {"required_price_closes": n, "required_funding_signal_events": 0}
    if family == "MOVING_AVERAGE_TREND":
        return {"required_price_closes": int(parameters["slow"]), "required_funding_signal_events": 0}
    if family == "FUNDING_CARRY":
        return {"required_price_closes": 1, "required_funding_signal_events": int(parameters["funding_window_events"])}
    if family == "VOLATILITY_TARGETING":
        return {"required_price_closes": max(96, int(parameters["realized_volatility_window"])) + 1, "required_funding_signal_events": 0}
    raise ValueError(f"unsupported Breadth V2 family: {family}")


def validate_registered_candidate_history(path: str = "experiments/research/candidates.jsonl") -> dict[str, dict[str, int]]:
    """Validate all 28 registrations without reading any result or outcome field."""
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    rows = [row for row in rows if row.get("candidate_id", "").startswith("CANDIDATE_BREADTH_V2_")]
    if len(rows) != 28 or any(row.get("event_type") != "CANDIDATE_PROPOSED" for row in rows):
        raise ValueError("Breadth V2 catalog must contain exactly 28 proposed candidates")
    registered_candidate_mappings(path)
    return {row["variant_id"]: required_history_for_variant(row["family_id"], row["parameters"]) for row in rows}


def _load_price(source: Mapping[str, Any], symbol: str) -> tuple[list[dict[str, str]], dict[str, Any], bytes]:
    manifest = source.get("manifest")
    raw = source.get("normalized_csv")
    if not isinstance(manifest, Mapping) or not isinstance(raw, (str, bytes)):
        raise InputBundleBlocked("BLOCKED_PRICE_COVERAGE", f"missing price artifact for {symbol}")
    raw_bytes = raw.encode() if isinstance(raw, str) else bytes(raw)
    cache_key = str(manifest.get("normalized_sha256"))
    if _sha_bytes(raw_bytes) != cache_key:
        raise InputBundleBlocked("BLOCKED_PRICE_COVERAGE", f"price parent SHA mismatch for {symbol}")
    cached = _PRICE_SOURCE_CACHE.get(cache_key)
    if cached is not None:
        return cached[0], dict(manifest), raw_bytes
    rows = list(csv.DictReader(io.StringIO(raw_bytes.decode("utf-8"))))
    expected = {"timestamp", "open", "high", "low", "close", "volume"}
    if not rows or set(rows[0]) != expected or any(set(row) != expected for row in rows):
        raise InputBundleBlocked("BLOCKED_PRICE_COVERAGE", f"invalid normalized price schema for {symbol}")
    timestamps = [row["timestamp"] for row in rows]
    if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
        raise InputBundleBlocked("BLOCKED_PRICE_COVERAGE", f"price timestamps are not unique and ordered for {symbol}")
    if manifest.get("gap_count") != 0:
        raise InputBundleBlocked("BLOCKED_PRICE_COVERAGE", f"price gap for {symbol}")
    result = (rows, dict(manifest), raw_bytes)
    _PRICE_SOURCE_CACHE[cache_key] = result
    return result


def _load_funding(source: Mapping[str, Any], symbol: str) -> tuple[list[dict[str, Any]], dict[str, Any], bytes]:
    manifest = source.get("manifest")
    raw = source.get("normalized_jsonl")
    if not isinstance(manifest, Mapping) or not isinstance(raw, (str, bytes)):
        raise InputBundleBlocked("BLOCKED_FUNDING_COVERAGE", f"missing funding artifact for {symbol}")
    raw_bytes = raw.encode() if isinstance(raw, str) else bytes(raw)
    cache_key = str(manifest.get("normalized_sha256"))
    if _sha_bytes(raw_bytes) != cache_key or manifest.get("coverage_status") != "COMPLETE":
        raise InputBundleBlocked("BLOCKED_FUNDING_COVERAGE", f"funding coverage or parent SHA mismatch for {symbol}")
    cached = _FUNDING_SOURCE_CACHE.get(cache_key)
    if cached is not None:
        return cached[0], dict(manifest), raw_bytes
    events = [json.loads(line) for line in raw_bytes.decode("utf-8").splitlines() if line]
    previous = -1
    seen: set[int] = set()
    for event in events:
        if event.get("symbol") != symbol or _event_ms(event) < previous or _event_ms(event) in seen:
            raise InputBundleBlocked("BLOCKED_FUNDING_COVERAGE", f"invalid funding source order for {symbol}")
        previous = event["funding_time_ms"]
        seen.add(event["funding_time_ms"])
    result = (events, dict(manifest), raw_bytes)
    _FUNDING_SOURCE_CACHE[cache_key] = result
    return result


def _asset_provenance(kind: str, manifest: Mapping[str, Any]) -> str:
    if kind == "price":
        payload = {key: manifest.get(key) for key in ("materializer_contract_version", "aggregate_source_receipt_digest", "normalized_sha256", "gap_count")}
    else:
        payload = {key: manifest.get(key) for key in ("materializer_contract_version", "archive_aggregate_source_receipt_digest", "rest_coverage_witness_digest", "coverage_reconciliation_digest", "coverage_status", "normalized_sha256")}
    if any(value is None for value in payload.values()):
        raise InputBundleBlocked("BLOCKED_PROVENANCE", f"incomplete {kind} provenance")
    return _sha(payload)


def build_input_bundle(*, evaluation_start: str | datetime, evaluation_end: str | datetime, symbols: Sequence[str], price_sources: Mapping[str, Mapping[str, Any]], funding_sources: Mapping[str, Mapping[str, Any]], family: str | None = None, parameters: Mapping[str, Any] | None = None, instrument_contract_id: str = INSTRUMENT_CONTRACT_ID) -> dict[str, Any]:
    """Build the sole strict asset mapping and canonical bundle payload."""
    if instrument_contract_id != INSTRUMENT_CONTRACT_ID:
        raise InputBundleBlocked("BLOCKED_INSTRUMENT_IDENTITY", "wrong instrument contract")
    start, end = _utc_hour(evaluation_start), _utc_hour(evaluation_end)
    if start > end:
        raise ValueError("evaluation_start must not exceed evaluation_end")
    boundaries = [_stamp(start + timedelta(hours=i)) for i in range(int((end - start).total_seconds() // 3600) + 1)]
    ordered_symbols = list(symbols)
    if len(set(ordered_symbols)) != len(ordered_symbols) or not ordered_symbols:
        raise InputBundleBlocked("BLOCKED_SYMBOL_ORDER", "symbols must be unique and ordered")
    if family and family.upper() in {"CROSS_SECTIONAL_MOMENTUM", "CROSS_SECTIONAL_REVERSAL", "FUNDING_CARRY"} and tuple(ordered_symbols) != PANEL_ORDER:
        raise InputBundleBlocked("BLOCKED_PANEL_COVERAGE", "fixed 20-member panel is incomplete or reordered")
    history = required_history_for_variant(family, parameters or {}) if family else {"required_price_closes": 1, "required_funding_signal_events": 0}
    assets: dict[str, dict[str, str]] = {}
    admitted_prices: dict[str, list[dict[str, str]]] = {}
    admitted_funding: dict[str, list[dict[str, Any]]] = {}
    diagnostics: dict[str, Any] = {"coverage": {}}
    for symbol in ordered_symbols:
        if symbol not in price_sources or symbol not in funding_sources:
            raise InputBundleBlocked("BLOCKED_PANEL_COVERAGE" if len(ordered_symbols) == len(PANEL_ORDER) else "BLOCKED_PRICE_COVERAGE", f"missing source for {symbol}")
        price_rows, price_manifest, price_bytes = _load_price(price_sources[symbol], symbol)
        funding_events, funding_manifest, funding_bytes = _load_funding(funding_sources[symbol], symbol)
        source_start = start - timedelta(hours=history["required_price_closes"])
        source_end = end - timedelta(hours=1)
        price_key = (str(price_manifest["normalized_sha256"]), _stamp(source_start), _stamp(source_end))
        cached_price = _PRICE_CLIP_CACHE.get(price_key)
        if cached_price is None:
            source_start_stamp, source_end_stamp = _stamp(source_start), _stamp(source_end)
            selected_prices = [row for row in price_rows if source_start_stamp <= row["timestamp"] <= source_end_stamp]
            expected = [_stamp(source_start + timedelta(hours=i)) for i in range(int((source_end - source_start).total_seconds() // 3600) + 1)]
            if [row["timestamp"] for row in selected_prices] != expected:
                raise InputBundleBlocked("BLOCKED_PRICE_COVERAGE", f"required price clip is incomplete for {symbol}")
            admitted_price_rows = [{"source_open_time": row["timestamp"], "decision_time": price_admission_boundary(row["timestamp"]), **{key: row[key] for key in ("open", "high", "low", "close", "volume")}} for row in selected_prices]
            price_content = ("".join(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n" for row in admitted_price_rows)).encode()
            cached_price = (admitted_price_rows, price_content, expected)
            _PRICE_CLIP_CACHE[price_key] = cached_price
        admitted_price_rows, price_content, expected = cached_price
        admitted_prices[symbol] = admitted_price_rows
        funding_key = (str(funding_manifest["normalized_sha256"]), _stamp(start), history["required_funding_signal_events"])
        cached_funding = _FUNDING_CLIP_CACHE.get(funding_key)
        if cached_funding is None:
            admission_rows = []
            for event in funding_events:
                admission = funding_admission_boundary(event["funding_time_ms"])
                if admission <= _stamp(end) and admission >= _stamp(start):
                    admission_rows.append({**event, "admission_boundary": admission})
            if history["required_funding_signal_events"]:
                warmup = [{**event, "admission_boundary": funding_admission_boundary(event["funding_time_ms"])} for event in funding_events if funding_admission_boundary(event["funding_time_ms"]) <= _stamp(start)]
                if len(warmup) < history["required_funding_signal_events"]:
                    raise InputBundleBlocked("BLOCKED_FUNDING_WARMUP", f"insufficient funding warmup for {symbol}")
                admission_rows = warmup[-history["required_funding_signal_events"]:] + admission_rows
            union = {(row["funding_time_ms"], row["funding_rate"], row["symbol"]): row for row in admission_rows}
            admitted_funding_rows = sorted(union.values(), key=lambda row: row["funding_time_ms"])
            funding_content = ("".join(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n" for row in admitted_funding_rows)).encode()
            cached_funding = (admitted_funding_rows, funding_content, len(admission_rows))
            _FUNDING_CLIP_CACHE[funding_key] = cached_funding
        admitted_funding_rows, funding_content, admission_count = cached_funding
        admitted_funding[symbol] = admitted_funding_rows
        assets[symbol] = {"price_parent_content": _sha_bytes(price_bytes), "price_content": _sha_bytes(price_content), "price_provenance": _asset_provenance("price", price_manifest), "funding_parent_content": _sha_bytes(funding_bytes), "funding_content": _sha_bytes(funding_content), "funding_provenance": _asset_provenance("funding", funding_manifest), "coverage": "COMPLETE"}
        diagnostics["coverage"][symbol] = {"price_source_clip": [expected[0], expected[-1]], "admitted_price_count": len(admitted_price_rows), "admitted_funding_count": admission_count}
    payload = {"contract": CONTRACT, "instrument_contract_id": INSTRUMENT_CONTRACT_ID, "symbols": ordered_symbols, "boundaries": boundaries, "decision_clock": DECISION_CLOCK_ID, "assets": assets}
    digest = evaluation_input_bundle_sha256(instrument_contract_id=INSTRUMENT_CONTRACT_ID, symbols=ordered_symbols, boundaries=boundaries, decision_clock=DECISION_CLOCK_ID, assets=assets)
    return {"status": "READY", "evaluation_input_bundle_sha256": digest, "bundle_payload": payload, "admitted_price": admitted_prices, "admitted_funding": admitted_funding, "coverage_diagnostics": diagnostics, "required_history": history}


build_breadth_v2_input_bundle = build_input_bundle
