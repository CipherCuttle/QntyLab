"""Fixture-only implementation qualification for the frozen JH01 V1 recorder.

This module has no HTTP client, scheduler, evaluator, or Qnty dependency.  A
future activation artifact is deliberately required before a real V1 origin
can enter the source or forecast path.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from hashlib import sha256
import inspect
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import jh01_rv_persistence_incremental_forecast_value_prereg_v1 as prereg
from .jh01_v1_bootstrap_source_range_contract_repair_v0 import derive_bootstrap_source_range


PROJECT_ID = "JH01_RV_PERSISTENCE_INCREMENTAL_FORECAST_VALUE_V1_PROSPECTIVE_RECORDER_AND_INPUT_MATERIALIZATION_IMPLEMENTATION_V0"
EXPERIMENT_ID = prereg.EXPERIMENT_ID
CANDIDATE_ID = prereg.CANDIDATE_ID
INTERVAL = "1h"
HORIZON_HOURS = 24
FIRST_LIVE_ORIGIN = datetime(2026, 9, 15, tzinfo=UTC)
LAST_LIVE_ORIGIN = datetime(2027, 9, 14, tzinfo=UTC)


class RecorderBlocked(ValueError):
    """The frozen recorder contract rejects a requested operation."""


class OriginState(str, Enum):
    ORIGIN_PRECHECK = "ORIGIN_PRECHECK"
    SOURCE_MATERIALIZED = "SOURCE_MATERIALIZED"
    FORECAST_COMPUTED = "FORECAST_COMPUTED"
    ARTIFACT_FROZEN = "ARTIFACT_FROZEN"
    PUBLICATION_IN_PROGRESS = "PUBLICATION_IN_PROGRESS"
    PUBLICATION_AUTHORITATIVE = "PUBLICATION_AUTHORITATIVE"
    ATTESTATION_ACQUIRED = "ATTESTATION_ACQUIRED"
    RETENTION_PACKAGE_FROZEN = "RETENTION_PACKAGE_FROZEN"
    OFFLINE_REVERIFIED = "OFFLINE_REVERIFIED"
    ORIGIN_COMPLETE = "ORIGIN_COMPLETE"
    BLOCKED = "BLOCKED"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def _stamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise RecorderBlocked("UTC-aware timestamp required")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        raise RecorderBlocked("UTC-aware timestamp required")
    parsed = parsed.astimezone(UTC)
    if parsed.minute or parsed.second or parsed.microsecond:
        raise RecorderBlocked("hour-aligned timestamp required")
    return parsed


def frozen_contract(root: Path) -> dict[str, Any]:
    artifact = prereg.load_preregistration(root)
    prereg.validate(artifact)
    repair = json.loads((root / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/bootstrap_source_range_contract_repair_v0.json").read_text())
    if repair["state"] != "CLOSED_PASS" or repair["repair"]["repaired_first_required_source_close"] != "2025-08-15T00:00:00Z":
        raise RecorderBlocked("corrected bootstrap repair unavailable")
    if repair["historical_predecessor"]["historical_first_required_bar_close"] == repair["repair"]["repaired_first_required_source_close"]:
        raise RecorderBlocked("obsolete boundary was not superseded")
    return {"preregistration": artifact, "repair": repair}


def implementation_identity() -> str:
    """Bind artifacts to the actual module source, never a caller-provided SHA."""
    return sha256(Path(inspect.getsourcefile(implementation_identity) or __file__).read_bytes()).hexdigest()


def required_origins() -> tuple[datetime, ...]:
    values = tuple(FIRST_LIVE_ORIGIN + timedelta(days=index) for index in range(365))
    if values[-1] != LAST_LIVE_ORIGIN:
        raise RecorderBlocked("frozen schedule drift")
    return values


def origin_identity(origin: datetime) -> str:
    return digest({"project_id": PROJECT_ID, "candidate_id": CANDIDATE_ID, "v1_preregistration_digest": "bdb85130cae75e9f156db9aa1fd955d7f565a3714ae091871d5ac4447c1ec27b", "forecast_origin_utc": _stamp(origin)})


@dataclass(frozen=True)
class Bar:
    symbol: str
    logical_close: datetime
    close: float
    raw_row: tuple[Any, ...]
    completed: bool = True


def validate_bars(bars: Sequence[Bar], *, panel: Sequence[str], origin: datetime, first_required_close: datetime) -> tuple[Bar, ...]:
    if tuple(panel) != tuple(panel) or len(panel) != 20 or len(set(panel)) != 20:
        raise RecorderBlocked("wrong ordered panel")
    seen: set[tuple[str, datetime]] = set()
    by_symbol: dict[str, list[Bar]] = {symbol: [] for symbol in panel}
    for bar in bars:
        if bar.symbol not in by_symbol or len(bar.raw_row) != 12 or not bar.completed:
            raise RecorderBlocked("malformed, open, or wrong-symbol bar")
        close = _utc(bar.logical_close)
        try:
            open_ms, raw_close, close_ms = int(bar.raw_row[0]), float(bar.raw_row[4]), int(bar.raw_row[6])
        except (TypeError, ValueError) as exc:
            raise RecorderBlocked("malformed Binance 12-field kline") from exc
        if open_ms != int((close - timedelta(hours=1)).timestamp() * 1000) or close_ms != int((close - timedelta(milliseconds=1)).timestamp() * 1000) or not math.isfinite(raw_close) or raw_close != bar.close:
            raise RecorderBlocked("provider timestamp or close does not map to logical close")
        if close > origin:
            raise RecorderBlocked("future source bar")
        if close < first_required_close or not math.isfinite(bar.close) or bar.close <= 0:
            raise RecorderBlocked("invalid source close")
        key = (bar.symbol, close)
        if key in seen:
            raise RecorderBlocked("duplicate logical close")
        seen.add(key); by_symbol[bar.symbol].append(bar)
    for symbol, rows in by_symbol.items():
        if not rows:
            raise RecorderBlocked(f"missing source symbol: {symbol}")
        rows.sort(key=lambda item: item.logical_close)
        if rows[0].logical_close != first_required_close or rows[-1].logical_close != origin:
            raise RecorderBlocked(f"source coverage boundary mismatch: {symbol}")
        if any(right.logical_close - left.logical_close != timedelta(hours=1) for left, right in zip(rows, rows[1:])):
            raise RecorderBlocked(f"source gap: {symbol}")
    return tuple(sorted(bars, key=lambda item: (item.logical_close, panel.index(item.symbol))))


def source_manifest(bars: Sequence[Bar], *, panel: Sequence[str], origin: datetime, first_required_close: datetime) -> dict[str, Any]:
    ordered = validate_bars(bars, panel=panel, origin=origin, first_required_close=first_required_close)
    rows = [{"symbol": bar.symbol, "interval": INTERVAL, "logical_close_utc": _stamp(bar.logical_close), "provider": "Binance USD-M", "raw_row_sha256": sha256(canonical_bytes(bar.raw_row)).hexdigest()} for bar in ordered]
    value = {"ordered_20_symbol_panel": list(panel), "ordered_20_symbol_panel_digest": digest(list(panel)), "interval": INTERVAL, "first_required_source_close": _stamp(first_required_close), "maximum_source_bar_close_utc": _stamp(max(bar.logical_close for bar in ordered)), "origin_utc": _stamp(origin), "rows": rows}
    return {**value, "source_data_manifest_sha256": digest(value)}


def _prices(bars: Sequence[Bar], panel: Sequence[str]) -> dict[str, dict[datetime, float]]:
    result = {symbol: {} for symbol in panel}
    for bar in bars:
        result[bar.symbol][bar.logical_close] = bar.close
    return result


def market_return(prices: Mapping[str, Mapping[datetime, float]], panel: Sequence[str], close: datetime) -> float:
    prior = close - timedelta(hours=1)
    try:
        returns = [math.log(prices[symbol][close] / prices[symbol][prior]) for symbol in panel]
    except KeyError as exc:
        raise RecorderBlocked("required return close missing") from exc
    return sum(returns) / len(returns)


def rv24_prior(prices: Mapping[str, Mapping[datetime, float]], panel: Sequence[str], origin: datetime) -> float:
    return math.sqrt(sum(market_return(prices, panel, origin - timedelta(hours=index)) ** 2 for index in range(24)))


def rv24_future(prices: Mapping[str, Mapping[datetime, float]], panel: Sequence[str], origin: datetime) -> float:
    return math.sqrt(sum(market_return(prices, panel, origin + timedelta(hours=index)) ** 2 for index in range(1, 25)))


def eligible_training_origins(origin: datetime) -> tuple[datetime, ...]:
    if origin not in required_origins():
        raise RecorderBlocked("origin outside frozen schedule")
    latest = origin - timedelta(days=2)  # o + 24h < t; equality at t is excluded.
    values = tuple(FIRST_LIVE_ORIGIN - timedelta(days=366) + timedelta(days=index) for index in range((latest - (FIRST_LIVE_ORIGIN - timedelta(days=366))).days + 1))
    if any(item + timedelta(hours=24) >= origin for item in values):
        raise RecorderBlocked("strict training cutoff violated")
    return values


def _ols(rows: Sequence[tuple[Sequence[float], float]]) -> tuple[float, tuple[float, ...]]:
    # Small deterministic normal-equation solver with an intercept; fixture scope only.
    width = len(rows[0][0]) + 1
    matrix = [[0.0] * (width + 1) for _ in range(width)]
    for features, target in rows:
        x = [1.0, *features]
        for i in range(width):
            for j in range(width): matrix[i][j] += x[i] * x[j]
            matrix[i][-1] += x[i] * target
    for column in range(width):
        pivot = max(range(column, width), key=lambda row: abs(matrix[row][column]))
        if abs(matrix[pivot][column]) < 1e-14: raise RecorderBlocked("singular frozen OLS fixture")
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        scale = matrix[column][column]; matrix[column] = [cell / scale for cell in matrix[column]]
        for row in range(width):
            if row != column:
                scale = matrix[row][column]; matrix[row] = [left - scale * right for left, right in zip(matrix[row], matrix[column])]
    solved = tuple(matrix[index][-1] for index in range(width))
    return solved[0], solved[1:]


def compute_models(bars: Sequence[Bar], *, panel: Sequence[str], origin: datetime) -> dict[str, Any]:
    prices = _prices(bars, panel); training = eligible_training_origins(origin)
    if origin == FIRST_LIVE_ORIGIN and len(training) != 365:
        raise RecorderBlocked("initial training count must equal 365")
    prior = {item: rv24_prior(prices, panel, item) for item in (*training, origin)}
    target = {item: rv24_future(prices, panel, item) for item in training}
    candidate_rows = [((prior[item],), target[item]) for item in training]
    c_alpha, (c_beta,) = _ols(candidate_rows)
    b3_rows = []
    for item in training:
        window = [prior.get(item - timedelta(days=lag)) or rv24_prior(prices, panel, item - timedelta(days=lag)) for lag in range(30)]
        b3_rows.append(((window[0], sum(window[:7]) / 7, sum(window) / 30), target[item]))
    b3_alpha, b3_coefficients = _ols(b3_rows)
    current_window = [prior.get(origin - timedelta(days=lag)) or rv24_prior(prices, panel, origin - timedelta(days=lag)) for lag in range(30)]
    c_raw = c_alpha + c_beta * prior[origin]
    b3_raw = b3_alpha + sum(coef * value for coef, value in zip(b3_coefficients, (current_window[0], sum(current_window[:7]) / 7, sum(current_window) / 30)))
    return {"C_JH01": {"alpha": c_alpha, "beta": c_beta, "raw_forecast": c_raw, "floored_forecast": max(0.0, c_raw)}, "B0": {"forecast": max(0.0, sum(target.values()) / len(target))}, "B1": {"forecast": prior[origin]}, "B3": {"alpha": b3_alpha, "daily_coefficient": b3_coefficients[0], "weekly_coefficient": b3_coefficients[1], "monthly_coefficient": b3_coefficients[2], "raw_forecast": b3_raw, "floored_forecast": max(0.0, b3_raw)}, "training_origin_count": len(training), "training_first_origin": _stamp(training[0]), "training_last_origin": _stamp(training[-1])}


def build_forecast_artifact(root: Path, bars: Sequence[Bar], *, origin: datetime, qualification_mode: bool, real_v1_activation_authorized: bool = False) -> dict[str, Any]:
    if not qualification_mode and not real_v1_activation_authorized:
        raise RecorderBlocked("REAL_V1_ACTIVATION_REQUIRED")
    contract = frozen_contract(root); preregistration = contract["preregistration"]; repair = contract["repair"]
    panel = preregistration["frozen_target"]["ordered_20_symbol_panel"]
    first_required = _utc(repair["repair"]["repaired_first_required_source_close"])
    manifest = source_manifest(bars, panel=panel, origin=origin, first_required_close=first_required)
    models = compute_models(bars, panel=panel, origin=origin)
    artifact = {"project_id": PROJECT_ID, "experiment_id": EXPERIMENT_ID, "candidate_id": CANDIDATE_ID, "v1_preregistration_digest": preregistration["preregistration_digest"], "forecast_origin_utc": _stamp(origin), "ordered_20_symbol_panel": panel, "ordered_20_symbol_panel_digest": digest(panel), "target_horizon_identity": "RV24_FUTURE_24H", "source_provider_contract_identity": "BINANCE_USD_M_PERPETUAL_1H_LOGICAL_CLOSE", "first_required_source_close": _stamp(first_required), "maximum_source_bar_close_utc": manifest["maximum_source_bar_close_utc"], "training_target_cutoff_exclusive_utc": _stamp(origin), "source_data_manifest_identity": manifest["source_data_manifest_sha256"], "source_data_manifest_sha256": manifest["source_data_manifest_sha256"], "model_implementation_identity_digest": implementation_identity(), "nonnegative_floor_application": "AFTER_FORECAST_MAX_0", "persistence_mechanism": "GITHUB_IMMUTABLE_RELEASE_V0R3_QUALIFIED", "qualification_mode": qualification_mode, **models}
    return {**artifact, "forecast_artifact_canonical_digest": digest(artifact)}


def recover_publication(existing: Mapping[str, str] | None, artifact: Mapping[str, Any]) -> str:
    expected = artifact["forecast_artifact_canonical_digest"]
    if existing is None: return "PUBLICATION_MAY_PROCEED"
    if existing.get("state") == "AMBIGUOUS": raise RecorderBlocked("ambiguous remote release")
    if existing.get("origin_identity") != origin_identity(_utc(artifact["forecast_origin_utc"])): raise RecorderBlocked("wrong existing origin")
    if existing.get("artifact_digest") == expected: return "IDEMPOTENT_AUTHORITATIVE_RECOVERY"
    raise RecorderBlocked("same origin different digest")


def retention_package(path: Path, *, forecast: Mapping[str, Any], release_metadata: Mapping[str, Any], bundle: bytes, trusted_root: bytes) -> dict[str, Any]:
    path.mkdir(parents=True, exist_ok=True)
    files = {"forecast.json": canonical_bytes(forecast), "release_metadata.json": canonical_bytes(release_metadata), "release_attestation.sigstore.json": bundle, "trusted_root.jsonl": trusted_root}
    for name, content in files.items(): (path / name).write_bytes(content)
    manifest = {"files": {name: sha256(content).hexdigest() for name, content in files.items()}, "timing_authority": "V0R3 verified Sigstore bundle plus signer, signed predicate/subjects, and GitHub TSA; release_metadata is informational only"}
    (path / "retention_manifest.json").write_bytes(canonical_bytes(manifest))
    return manifest


def verify_retention_package(path: Path) -> None:
    manifest = json.loads((path / "retention_manifest.json").read_text())
    expected = {name: sha256((path / name).read_bytes()).hexdigest() for name in manifest["files"]}
    if expected != manifest["files"]: raise RecorderBlocked("retention package digest mismatch")
    forecast = json.loads((path / "forecast.json").read_text())
    if forecast.get("forecast_artifact_canonical_digest") != digest({key: value for key, value in forecast.items() if key != "forecast_artifact_canonical_digest"}): raise RecorderBlocked("forecast artifact digest mismatch")
