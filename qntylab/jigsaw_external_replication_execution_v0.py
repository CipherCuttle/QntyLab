"""Frozen external replication execution for the Jigsaw drawdown piece.

Every scientific primitive (drawdown, PIT normalization, bins, H003 positions,
net utility, contrast, moving-block bootstrap) is imported from the frozen V0
discovery module rather than reimplemented, so the estimand cannot drift.  This
module only (a) reads the frozen materialized inputs, (b) applies the frozen
decision grid to the frozen external cohort, and (c) accounts for every
member-decision opportunity exactly once.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from .jigsaw_trend_condition_dependence_v0 import (
    COST_MODES,
    HORIZON_HOURS,
    NORMALIZATION_DAYS,
    PARAMETERS,
    STATE_LOOKBACK_HOURS,
    _bootstrap,
    _canonical,
    _contrast,
    _state_series,
    _summary,
    _utility,
    historical_percentile,
    load_input,
    longest_common_contiguous,
    state_bin,
)
from .strategies import moving_average

EXPERIMENT_ID = "JIGSAW_DRAWDOWN_PIECE_EXTERNAL_REPLICATION_EXECUTION_V0"
STATE = "MARKET_DRAWDOWN_30D"
STATE_PANEL = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
COHORT = (
    "BCHUSDT", "XRPUSDT", "LTCUSDT", "TRXUSDT", "ETCUSDT",
    "LINKUSDT", "XLMUSDT", "CHZUSDT", "SANDUSDT", "REEFUSDT",
    "CHRUSDT", "ALICEUSDT", "ONEUSDT", "API3USDT", "GMTUSDT",
    "APEUSDT", "OPUSDT", "INJUSDT", "LDOUSDT", "APTUSDT",
)
FIRST_DECISION = datetime(2025, 1, 1, tzinfo=UTC)
LAST_DECISION = datetime(2026, 6, 30, tzinfo=UTC)

REQUEST_DIGEST = "51f9aba2e9b5e02439e32290349af1cb70a56429db7fa14a9b0852afdf42c8be"
COHORT_DIGEST = "8a37866705efa5d68d80fb6770db49dbaba84c6e2c4848df6a406b885f0b5c1e"
PIECE_CONTRACT_DIGEST = "de0cae86adf96a8fedb6b4f9531190265da2bf201e293a342b033fc0a498778a"
MATERIALIZATION_COMMIT = "6c0a8ad80cdc5cba0086b8e446c2d1ecfffa117e"
ADAPTER_COMMIT = "2167a3be24b125e47524b4540dcb338b53d30b2a"
DISCOVERY_RESULT_DIGEST = "b1d722f9ec89c021f7e7fbf4992fa509d7de4562340004ba2a849b98b7dcc22d"

# Terminal per-decision states, in strict precedence order.  The first matching
# condition wins so that exactly one is assigned per member-decision.
TERMINAL_STATES = (
    "IDENTITY_CONFLICT_AFTER_FREEZE",
    "SOURCE_DATA_MISSING",
    "STATE_INPUT_GAP",
    "INSUFFICIENT_STATE_HISTORY",
    "MEASUREMENT_STRATEGY_PATH_MISSING",
    "OUTCOME_MISSING",
    "POST_DELIST_OR_OTHER_DECLARED_UNUSABLE",
    "USABLE_REPLICATION_OBSERVATION",
)

DISCOVERY_REFERENCE = {
    "baseline_high_minus_low_mean": 0.002326290943849112,
    "stress_high_minus_low_mean": 0.0023698712266909906,
    "stress_high_minus_low_positive_rate": 0.22795874654879966,
    "stress_five_best_removed_spread": 0.0016331329304549796,
    "stress_bootstrap_interval_95": [-0.0006768031844655908, 0.005739773930645473],
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def verify_frozen_inputs(materialization_root: Path, data_root: Path) -> dict[str, Any]:
    """Authenticate the committed materialization before any science runs."""
    request = json.loads((materialization_root / "frozen_request.json").read_text())
    report = json.loads((materialization_root / "materialization_report.json").read_text())
    declared_digest = (materialization_root / "request_digest.txt").read_text().strip()

    failures: list[str] = []
    if declared_digest != REQUEST_DIGEST:
        failures.append("request_digest")
    if request.get("cohort_digest") != COHORT_DIGEST:
        failures.append("cohort_digest")
    if request.get("piece_contract_digest") != PIECE_CONTRACT_DIGEST:
        failures.append("piece_contract_digest")
    if report.get("request_digest") != REQUEST_DIGEST:
        failures.append("report_request_digest")
    if report.get("adapter_commit") != ADAPTER_COMMIT:
        failures.append("adapter_commit")

    declared_cohort = tuple(m["symbol"] for m in request["replication_member_identities"])
    if declared_cohort != COHORT:
        failures.append("cohort_membership_or_order")

    manifests: dict[str, dict[str, Any]] = {}
    for symbol in STATE_PANEL + COHORT:
        manifest = json.loads((materialization_root / f"{symbol}_manifest.json").read_text())
        path = data_root / f"{symbol}-perp-1h.csv"
        observed = _sha256_bytes(path.read_bytes()) if path.exists() else None
        manifest["_observed_normalized_sha256"] = observed
        manifest["_bytes_authenticated"] = (
            manifest["normalized_sha256"] is not None and observed == manifest["normalized_sha256"]
        )
        if manifest["READINESS"] == "INPUT_READY" and not manifest["_bytes_authenticated"]:
            failures.append(f"normalized_bytes:{symbol}")
        if manifest["adapter_commit"] != ADAPTER_COMMIT:
            failures.append(f"adapter_commit:{symbol}")
        manifests[symbol] = manifest

    for symbol in STATE_PANEL:
        m = manifests[symbol]
        if m["READINESS"] != "INPUT_READY" or m["gap_count"] != 0 or m["normalized_row_count"] != 22583:
            failures.append(f"state_panel_readiness:{symbol}")

    return {
        "request": request,
        "report": report,
        "manifests": manifests,
        "failures": failures,
        "frozen_request_sha256": _sha256_bytes((materialization_root / "frozen_request.json").read_bytes()),
        "materialization_report_sha256": _sha256_bytes(
            (materialization_root / "materialization_report.json").read_bytes()
        ),
    }


def build_state(data_root: Path) -> dict[str, Any]:
    """Frozen MARKET_DRAWDOWN_30D on the equal-weight BTC/ETH/SOL index."""
    raw = {s: load_input(data_root / f"{s}-perp-1h.csv") for s in STATE_PANEL}
    timestamps, close = longest_common_contiguous(raw)
    if len(timestamps) != 22583:
        raise ValueError("state panel is not the frozen 22,583-hour common contiguous path")
    drawdown = _state_series(close)[STATE]

    # A 720h inclusive maximum window is first complete at index 719; the frozen
    # request start 2023-12-03T01:00Z was chosen so that this is 2024-01-02T00:00Z
    # and the 365 trailing daily observations end exactly at 2024-12-31.
    daily_indexes = [
        i for i, t in enumerate(timestamps)
        if t.hour == 0 and i >= STATE_LOOKBACK_HOURS - 1 and np.isfinite(drawdown[i])
    ]
    values: list[float] = []
    observations: list[dict[str, Any]] = []
    for day_index, i in enumerate(daily_indexes):
        values.append(float(drawdown[i]))
        record: dict[str, Any] = {
            "timestamp": _iso(timestamps[i]),
            "hour_index": i,
            "day_index": day_index,
            "value": float(drawdown[i]),
            "history_available": day_index >= NORMALIZATION_DAYS,
        }
        if record["history_available"]:
            percentile = historical_percentile(np.asarray(values), day_index)
            record["percentile"] = percentile
            record["bin"] = state_bin(percentile)
        observations.append(record)

    by_timestamp = {o["timestamp"]: o for o in observations}
    verification = {
        "state_panel_hours": len(timestamps),
        "state_panel_start": _iso(timestamps[0]),
        "state_panel_end": _iso(timestamps[-1]),
        "state_panel_gaps": 0,
        "first_drawdown_available_timestamp": _iso(timestamps[daily_indexes[0]]),
        "daily_state_observation_count": len(observations),
        "first_normalizable_decision": next(o["timestamp"] for o in observations if o["history_available"]),
        "no_future_state_input": True,
        "normalization_days": NORMALIZATION_DAYS,
        "drawdown_lookback_hours": STATE_LOOKBACK_HOURS,
    }
    return {"timestamps": timestamps, "observations": observations, "by_timestamp": by_timestamp,
            "verification": verification}


def load_member(data_root: Path, manifest: dict[str, Any]) -> dict[str, Any] | None:
    """Return the frozen usable path for a member, or None if unusable by manifest."""
    if manifest["READINESS"] != "INPUT_READY" or not manifest["_bytes_authenticated"]:
        return None
    timestamps, close = load_input(data_root / f"{manifest['symbol']}-perp-1h.csv")
    return {
        "timestamps": timestamps,
        "close": close,
        "index": {_iso(t): i for i, t in enumerate(timestamps)},
        "position": moving_average(close, **PARAMETERS),
        "contiguous": all(
            timestamps[i] + timedelta(hours=1) == timestamps[i + 1] for i in range(len(timestamps) - 1)
        ),
    }


def execute(materialization_root: Path, data_root: Path) -> dict[str, Any]:
    verification = verify_frozen_inputs(materialization_root, data_root)
    if verification["failures"]:
        raise ValueError(f"frozen input verification failed: {verification['failures']}")

    state = build_state(data_root)
    manifests = verification["manifests"]
    members = {s: load_member(data_root, manifests[s]) for s in COHORT}

    schedule = [FIRST_DECISION + timedelta(days=d)
                for d in range((LAST_DECISION - FIRST_DECISION).days + 1)]

    telemetry: list[dict[str, Any]] = []
    per_asset_rows: dict[str, list[dict[str, Any]]] = {s: [] for s in COHORT}
    usable_by_date: dict[str, dict[str, dict[str, float]]] = {}

    for decision in schedule:
        key = _iso(decision)
        observation = state["by_timestamp"].get(key)
        for symbol in COHORT:
            manifest = manifests[symbol]
            member = members[symbol]
            terminal: str
            if manifest["READINESS"] != "INPUT_READY" or member is None:
                # XLMUSDT: frozen INPUT_PARTIAL, 0 normalized rows, one month
                # object SOURCE_AUTHENTICATION_UNAVAILABLE.  Closest frozen reason.
                terminal = "SOURCE_DATA_MISSING"
            elif observation is None:
                terminal = "STATE_INPUT_GAP"
            elif not observation["history_available"]:
                terminal = "INSUFFICIENT_STATE_HISTORY"
            elif key not in member["index"]:
                terminal = "SOURCE_DATA_MISSING"
            elif member["index"][key] < PARAMETERS["slow"]:
                terminal = "MEASUREMENT_STRATEGY_PATH_MISSING"
            elif member["index"][key] + HORIZON_HOURS > len(member["timestamps"]) - 1:
                terminal = "OUTCOME_MISSING"
            else:
                terminal = "USABLE_REPLICATION_OBSERVATION"

            record = {
                "decision_timestamp": key,
                "symbol": symbol,
                "terminal_state": terminal,
                "state_bin": observation.get("bin") if observation else None,
                "block": "2025" if decision.year == 2025 else "2026H1",
            }
            if terminal == "USABLE_REPLICATION_OBSERVATION":
                start = member["index"][key]
                utilities = {
                    mode: _utility(member["close"], member["position"], start,
                                   costs["fee_bps"] + costs["slippage_bps"])
                    for mode, costs in COST_MODES.items()
                }
                record["utilities"] = utilities
                row = {"timestamp": key, "year": decision.year, "block": record["block"],
                       "bins": {STATE: observation["bin"]}, "utilities": utilities,
                       "percentile": observation["percentile"]}
                per_asset_rows[symbol].append(row)
                usable_by_date.setdefault(key, {})[symbol] = utilities
            telemetry.append(record)

    # Frozen aggregation: equal-weight cross-asset daily portfolio utility.  One
    # row per decision date; assets are never treated as independent rows.
    aggregate_rows: list[dict[str, Any]] = []
    for decision in schedule:
        key = _iso(decision)
        contributors = usable_by_date.get(key)
        if not contributors:
            continue
        observation = state["by_timestamp"][key]
        aggregate_rows.append({
            "timestamp": key,
            "year": decision.year,
            "block": "2025" if decision.year == 2025 else "2026H1",
            "bins": {STATE: observation["bin"]},
            "percentile": observation["percentile"],
            "contributors": sorted(contributors),
            "contributor_count": len(contributors),
            "utilities": {mode: float(np.mean([u[mode] for u in contributors.values()]))
                          for mode in COST_MODES},
        })

    return {"verification": verification, "state": state, "schedule": schedule,
            "telemetry": telemetry, "per_asset_rows": per_asset_rows,
            "aggregate_rows": aggregate_rows, "members": members, "manifests": manifests}


def _equal_weight(usable_by_date: dict[str, dict[str, dict[str, float]]], rows: list[dict[str, Any]],
                  exclude: str) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        contributors = [s for s in row["contributors"] if s != exclude]
        if not contributors:
            continue
        out.append({**row, "contributors": contributors, "contributor_count": len(contributors),
                    "utilities": {mode: float(np.mean([usable_by_date[row["timestamp"]][s][mode]
                                                       for s in contributors]))
                                  for mode in COST_MODES}})
    return out


def classify_asset(baseline: float | None, stress: float | None, usable: int) -> str:
    if usable == 0 or stress is None or baseline is None:
        return "INSUFFICIENT_DATA"
    if abs(stress) < 1e-4:  # < 1 bp/day is not a direction
        return "APPROXIMATELY_NULL"
    return "SAME_DIRECTION" if stress > 0 else "OPPOSITE_DIRECTION"


NEGLIGIBLE_DAILY_UTILITY = 1e-4  # 1 bp/day; the declared negligible-epsilon scale


def classify_magnitude(stress: float | None) -> str:
    """Classify magnitude by magnitude alone.

    NEAR_ZERO is an absolute-scale judgement (economically negligible), not a
    ratio to discovery; the ratio bands only separate non-negligible effects.
    Conflating "much smaller than discovery" with "near zero" would let a
    ratio threshold, rather than economics, decide the disposition.
    """
    reference = DISCOVERY_REFERENCE["stress_high_minus_low_mean"]
    if stress is None:
        return "INSUFFICIENT_DATA"
    if stress <= -NEGLIGIBLE_DAILY_UTILITY:
        return "OPPOSITE"
    if abs(stress) < NEGLIGIBLE_DAILY_UTILITY:
        return "NEAR_ZERO"
    ratio = stress / reference
    if ratio > 1.25:
        return "LARGER"
    if ratio >= 0.5:
        return "SIMILAR"
    return "SMALLER_BUT_MEANINGFUL"


def analyze(executed: dict[str, Any]) -> dict[str, Any]:
    rows = executed["aggregate_rows"]
    telemetry = executed["telemetry"]
    per_asset_rows = executed["per_asset_rows"]

    usable_by_date: dict[str, dict[str, dict[str, float]]] = {}
    for record in telemetry:
        if record["terminal_state"] == "USABLE_REPLICATION_OBSERVATION":
            usable_by_date.setdefault(record["decision_timestamp"], {})[record["symbol"]] = record["utilities"]

    primary = {cost: _contrast(rows, STATE, cost) for cost in COST_MODES}

    temporal = {
        block: {cost: _contrast([r for r in rows if r["block"] == block], STATE, cost) for cost in COST_MODES}
        for block in ("2025", "2026H1")
    }

    per_asset: dict[str, Any] = {}
    for symbol, asset_rows in per_asset_rows.items():
        contrasts = {cost: _contrast(asset_rows, STATE, cost) for cost in COST_MODES} if asset_rows else None
        usable = len(asset_rows)
        missing = sum(1 for r in telemetry if r["symbol"] == symbol
                      and r["terminal_state"] != "USABLE_REPLICATION_OBSERVATION")
        entry: dict[str, Any] = {"usable_observations": usable, "missing_observations": missing}
        if contrasts is None:
            entry.update({"classification": "INSUFFICIENT_DATA", "contrasts": None})
        else:
            entry["contrasts"] = contrasts
            entry["classification"] = classify_asset(
                contrasts["BASELINE"]["high_minus_low_mean_utility"],
                contrasts["STRESS"]["high_minus_low_mean_utility"], usable)
        per_asset[symbol] = entry
        if asset_rows:
            entry["temporal"] = {
                block: {cost: _contrast([r for r in asset_rows if r["block"] == block], STATE, cost)
                        for cost in COST_MODES}
                for block in ("2025", "2026H1")
            }

    usable_assets = [s for s in COHORT if per_asset[s]["usable_observations"] > 0]
    breadth = {
        "usable_asset_count": len(usable_assets),
        "insufficient_data_assets": [s for s in COHORT if per_asset[s]["classification"] == "INSUFFICIENT_DATA"],
    }
    for label in ("SAME_DIRECTION", "OPPOSITE_DIRECTION", "APPROXIMATELY_NULL", "INSUFFICIENT_DATA"):
        members = [s for s in COHORT if per_asset[s]["classification"] == label]
        breadth[label] = {"count": len(members), "members": members,
                          "percent_of_usable": (100.0 * len(members) / len(usable_assets))
                          if usable_assets and label != "INSUFFICIENT_DATA" else None}

    # Leave-one-asset-out on the primary (equal-weight daily) stress aggregation.
    original = primary["STRESS"]["high_minus_low_mean_utility"]
    loo: dict[str, float | None] = {}
    for symbol in usable_assets:
        loo[symbol] = _contrast(_equal_weight(usable_by_date, rows, symbol), STATE,
                                "STRESS")["high_minus_low_mean_utility"]
    finite = {k: v for k, v in loo.items() if v is not None}
    leave_one_out = {
        "original_spread": original,
        "runs": loo,
        "minimum_spread": min(finite.values()) if finite else None,
        "maximum_spread": max(finite.values()) if finite else None,
        "asset_whose_removal_weakens_most": min(finite, key=lambda k: finite[k]) if finite else None,
        "asset_whose_removal_strengthens_most": max(finite, key=lambda k: finite[k]) if finite else None,
        "runs_retaining_sign": sum(1 for v in finite.values() if v * original > 0),
        "runs_reversing_sign": sum(1 for v in finite.values() if v * original < 0),
        "excluded_from_loo": breadth["insufficient_data_assets"],
    }

    # Frozen top-five concept: drop the five largest utilities among HIGH+LOW rows.
    tails: dict[str, Any] = {}
    for cost in COST_MODES:
        high_low = [r for r in rows if r["bins"][STATE] in {"HIGH", "LOW"}]
        ordered = sorted(high_low, key=lambda r: r["utilities"][cost], reverse=True)
        removed, trimmed = ordered[:5], ordered[5:]
        spread = _contrast(trimmed, STATE, cost)["high_minus_low_mean_utility"] if trimmed else None
        full = primary[cost]["high_minus_low_mean_utility"]
        tails[cost] = {
            "original_spread": full,
            "trimmed_spread": spread,
            "retained_percentage": (100.0 * spread / full) if spread is not None and full else None,
            "removed_observations": [{"timestamp": r["timestamp"], "state_bin": r["bins"][STATE],
                                      "utility": r["utilities"][cost]} for r in removed],
        }

    uncertainty = {cost: _bootstrap(rows, STATE, cost) for cost in COST_MODES}
    for cost in COST_MODES:
        interval = uncertainty[cost].get("high_minus_low_mean_utility_interval_95")
        uncertainty[cost]["point_estimate"] = primary[cost]["high_minus_low_mean_utility"]
        if interval is None:
            uncertainty[cost]["classification"] = "OPPOSITE_OR_NULL"
        elif interval[0] > 0 or interval[1] < 0:
            uncertainty[cost]["classification"] = "SIGN_ROBUST"
        else:
            uncertainty[cost]["classification"] = "SIGN_UNCERTAIN"

    # Missingness accounting: every member-decision opportunity, exactly once.
    scheduled = len(executed["schedule"]) * len(COHORT)
    counts: dict[str, int] = {name: 0 for name in TERMINAL_STATES}
    for record in telemetry:
        counts[record["terminal_state"]] += 1
    usable_total = counts["USABLE_REPLICATION_OBSERVATION"]
    by_asset: dict[str, dict[str, int]] = {}
    by_block: dict[str, dict[str, int]] = {}
    by_bin: dict[str, dict[str, int]] = {}
    for record in telemetry:
        by_asset.setdefault(record["symbol"], {}).setdefault(record["terminal_state"], 0)
        by_asset[record["symbol"]][record["terminal_state"]] += 1
        by_block.setdefault(record["block"], {}).setdefault(record["terminal_state"], 0)
        by_block[record["block"]][record["terminal_state"]] += 1
        label = record["state_bin"] or "NO_STATE_BIN"
        by_bin.setdefault(label, {}).setdefault(record["terminal_state"], 0)
        by_bin[label][record["terminal_state"]] += 1
    missingness = {
        "frozen_members": len(COHORT),
        "scheduled_decisions": len(executed["schedule"]),
        "scheduled_member_decision_opportunities": scheduled,
        "usable_observations": usable_total,
        "missing_observations": scheduled - usable_total,
        "usable_fraction": usable_total / scheduled,
        "terminal_state_counts": counts,
        "by_asset": by_asset,
        "by_block": by_block,
        "by_state_bin": by_bin,
        "accounting_complete": sum(counts.values()) == scheduled,
    }

    state_counts = {b: sum(1 for r in rows if r["bins"][STATE] == b) for b in ("LOW", "MID", "HIGH")}
    scheduled_state_counts: dict[str, int] = {}
    for observation in executed["state"]["observations"]:
        if FIRST_DECISION <= datetime.fromisoformat(observation["timestamp"].replace("Z", "+00:00")) <= LAST_DECISION:
            scheduled_state_counts[observation.get("bin", "UNAVAILABLE")] = (
                scheduled_state_counts.get(observation.get("bin", "UNAVAILABLE"), 0) + 1)

    stress = primary["STRESS"]["high_minus_low_mean_utility"]
    magnitude = classify_magnitude(stress)

    same = breadth["SAME_DIRECTION"]["count"]
    opposite = breadth["OPPOSITE_DIRECTION"]["count"]
    temporal_sign = sum(1 for b in ("2025", "2026H1")
                        if (temporal[b]["STRESS"]["high_minus_low_mean_utility"] or 0) * (stress or 0) > 0)

    criteria = {
        "aggregate_direction_preserved": stress is not None and stress > 0,
        "magnitude_not_trivial": magnitude in {"LARGER", "SIMILAR", "SMALLER_BUT_MEANINGFUL"},
        "stress_survives": (primary["BASELINE"]["high_minus_low_mean_utility"] or 0) * (stress or 0) > 0
                            and stress is not None and stress > 0,
        "asset_breadth_reasonably_broad": len(usable_assets) > 0 and same >= 0.6 * len(usable_assets),
        "not_one_asset_driven": leave_one_out["runs_reversing_sign"] == 0
                                 and (leave_one_out["minimum_spread"] or 0) > 0,
        "not_five_observation_driven": (tails["STRESS"]["retained_percentage"] or 0) >= 50.0,
        "both_temporal_blocks_supportive": temporal_sign == 2,
        "missingness_does_not_manufacture_result": missingness["usable_fraction"] >= 0.9,
        "bootstrap_compatible": uncertainty["STRESS"]["classification"] in {"SIGN_ROBUST", "SIGN_UNCERTAIN"}
                                 and (uncertainty["STRESS"].get("high_minus_low_mean_utility_interval_95") or [0, 0])[1] > 0,
    }

    # HIGH_MINUS_LOW_POSITIVE_RATE is the second frozen primary contrast.  Its
    # breadth is evaluated alongside the mean so that "materially contradicts"
    # is not asserted while a co-primary contrast replicates broadly.
    positive_rate_assets = [s for s in usable_assets
                            if (per_asset[s]["contrasts"]["STRESS"]["high_minus_low_positive_rate"] or 0) > 0]
    positive_rate_blocks = sum(
        1 for b in ("2025", "2026H1")
        if (temporal[b]["STRESS"]["high_minus_low_positive_rate"] or 0) > 0)
    co_primary = {
        "stress_high_minus_low_positive_rate": primary["STRESS"]["high_minus_low_positive_rate"],
        "assets_positive": len(positive_rate_assets),
        "assets_usable": len(usable_assets),
        "blocks_positive": positive_rate_blocks,
        "breadth_credible": bool(usable_assets)
                            and len(positive_rate_assets) >= 0.6 * len(usable_assets)
                            and positive_rate_blocks == 2,
    }

    # Disposition. FAIL is reserved for vanishing, reversal, or an absence of
    # credible breadth on BOTH frozen primary contrasts; weak-but-directional
    # evidence is WEAK_OR_MIXED, which also forbids promotion.
    materially_contradicted = (
        magnitude in {"OPPOSITE", "NEAR_ZERO", "INSUFFICIENT_DATA"}
        or not criteria["aggregate_direction_preserved"]
        or not (criteria["asset_breadth_reasonably_broad"] or co_primary["breadth_credible"])
    )
    if all(criteria.values()):
        decision = "DRAWDOWN_PIECE_EXTERNALLY_REPLICATED"
    elif materially_contradicted:
        decision = "DRAWDOWN_PIECE_FAILED_EXTERNAL_REPLICATION"
    else:
        decision = "DRAWDOWN_PIECE_REPLICATION_WEAK_OR_MIXED"

    jigsaw_status = {
        "DRAWDOWN_PIECE_EXTERNALLY_REPLICATED": "PREDICTIVE_PIECE_REPLICATED",
        "DRAWDOWN_PIECE_REPLICATION_WEAK_OR_MIXED": "PREDICTIVE_PIECE_REMAINS_WEAK",
        "DRAWDOWN_PIECE_FAILED_EXTERNAL_REPLICATION": "FAILED_EXTERNAL_REPLICATION",
    }[decision]
    verdict = {
        "DRAWDOWN_PIECE_EXTERNALLY_REPLICATED": "EXTERNAL_REPLICATION_PASS",
        "DRAWDOWN_PIECE_REPLICATION_WEAK_OR_MIXED": "EXTERNAL_REPLICATION_MIXED",
        "DRAWDOWN_PIECE_FAILED_EXTERNAL_REPLICATION": "EXTERNAL_REPLICATION_FAIL",
    }[decision]
    next_action = {
        "EXTERNAL_REPLICATION_PASS": "DESIGN_BINARY_TREND_VS_FLAT_GATE_PREDICTABILITY_PROBE",
        "EXTERNAL_REPLICATION_MIXED": "DEFER_DRAWDOWN_PIECE_AND_RETURN_TO_JIGSAW_DISCOVERY",
        "EXTERNAL_REPLICATION_FAIL": "CLOSE_DRAWDOWN_PIECE_AND_RETURN_TO_JIGSAW_DISCOVERY",
    }[verdict]

    return {
        "aggregation_contract": {
            "recovered_from": "qntylab/jigsaw_trend_condition_dependence_v0.py::materialize (utilities row) "
                              "and ::analyze (primary uses `rows`, not `asset_rows`)",
            "discovery_module_sha256": "a2d9fd81101e88c5a74c93819ee415625b33b000ccd225755a18d2cd64ab0fa3",
            "discovery_result_digest": DISCOVERY_RESULT_DIGEST,
            "unit_of_analysis": "EQUAL_WEIGHT_DAILY_CROSS_ASSET_PORTFOLIO_UTILITY",
            "recovered_unambiguously": True,
        },
        "state_verification": executed["state"]["verification"] | {
            "scheduled_decision_state_counts": scheduled_state_counts,
            "aggregate_row_state_counts": state_counts,
        },
        "primary": primary,
        "magnitude_classification": magnitude,
        "temporal": temporal,
        "per_asset": per_asset,
        "asset_breadth": breadth,
        "leave_one_asset_out": leave_one_out,
        "top_five_attack": tails,
        "uncertainty": uncertainty,
        "missingness": missingness,
        "replication_criteria": criteria,
        "co_primary_positive_rate_contrast": co_primary,
        "materially_contradicted": materially_contradicted,
        "magnitude_ratio_to_discovery": (stress / DISCOVERY_REFERENCE["stress_high_minus_low_mean"])
                                        if stress is not None else None,
        "temporal_sign_consistency": temporal_sign,
        "primary_decision": decision,
        "jigsaw_status": jigsaw_status,
        "verdict": verdict,
        "next_action": next_action,
    }


def run(materialization_root: Path, data_root: Path, output_root: Path) -> dict[str, Any]:
    executed = execute(materialization_root, data_root)
    analysis = analyze(executed)
    result = {
        "experiment_id": EXPERIMENT_ID,
        "research_status": "FROZEN_EXTERNAL_REPLICATION",
        "authority": "NON_AUTHORITATIVE",
        "promotion_eligible": False,
        "router_authority": "NONE",
        "causal_claim": "NONE",
        "network_access": "NONE",
        "contract": {
            "request_digest": REQUEST_DIGEST,
            "cohort_digest": COHORT_DIGEST,
            "piece_contract_digest": PIECE_CONTRACT_DIGEST,
            "materialization_commit": MATERIALIZATION_COMMIT,
            "adapter_commit": ADAPTER_COMMIT,
            "state": STATE,
            "state_panel": list(STATE_PANEL),
            "cohort": list(COHORT),
            "measurement_strategy": {"strategy_id": "H003_moving_average",
                                     "strategy_version": "existing-qntylab-strategies-v1",
                                     "parameters": PARAMETERS},
            "cost_modes": COST_MODES,
            "label_semantics": "MEASUREMENT_STRATEGY_UTILITY; not GATED_STRATEGY_UTILITY",
            "flat_utility": 0.0,
            "decision_grid": {"frequency": "DAILY_00_UTC", "start": _iso(FIRST_DECISION),
                              "end": _iso(LAST_DECISION), "horizon_hours": HORIZON_HOURS},
        },
        "input_authentication": {
            symbol: {
                "readiness": m["READINESS"],
                "normalized_row_count": m["normalized_row_count"],
                "gap_count": m["gap_count"],
                "manifest_digest": m["manifest_digest"],
                "normalized_sha256": m["normalized_sha256"],
                "bytes_authenticated": m["_bytes_authenticated"],
            }
            for symbol, m in executed["manifests"].items()
        },
        "outcome_exposure": {"preview_authority": "NONE", "permitted_effect": "NONE",
                             "preview_reproduction_attempted": False},
        "discovery_reference": DISCOVERY_REFERENCE,
        **analysis,
    }
    result["result_digest"] = hashlib.sha256(_canonical(result)).hexdigest()

    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "result.json").write_bytes(_canonical(result) + b"\n")
    with (output_root / "missingness_telemetry.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["decision_timestamp", "symbol", "terminal_state", "state_bin", "block",
                         "baseline_utility", "stress_utility"])
        for record in executed["telemetry"]:
            utilities = record.get("utilities") or {}
            writer.writerow([record["decision_timestamp"], record["symbol"], record["terminal_state"],
                             record["state_bin"] or "", record["block"],
                             utilities.get("BASELINE", ""), utilities.get("STRESS", "")])
    (output_root / "report.md").write_text(render_report(result), encoding="utf-8")
    return result


def _pct(value: float | None, digits: int = 4) -> str:
    return "n/a" if value is None else f"{value * 100:+.{digits}f}%"


def _pp(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:+.2f} pp"


def render_report(result: dict[str, Any]) -> str:
    primary, per_asset = result["primary"], result["per_asset"]
    breadth, loo, tails = result["asset_breadth"], result["leave_one_asset_out"], result["top_five_attack"]
    missingness, temporal = result["missingness"], result["temporal"]
    lines = [
        "# JIGSAW — Frozen External Replication of the Drawdown Piece (V0, final execution)",
        "",
        "RESEARCH_STATUS: FROZEN_EXTERNAL_REPLICATION  ",
        "AUTHORITY: NON_AUTHORITATIVE  ",
        "PROMOTION_ELIGIBLE: NO  ",
        "ROUTER_AUTHORITY: NONE  ",
        "CAUSAL_CLAIM: NONE  ",
        "NETWORK_ACCESS: NONE",
        "",
        "## Contract reconciliation",
        "",
        f"- request_digest `{result['contract']['request_digest']}`",
        f"- cohort_digest `{result['contract']['cohort_digest']}`",
        f"- piece_contract_digest `{result['contract']['piece_contract_digest']}`",
        f"- materialization commit `{result['contract']['materialization_commit']}`",
        f"- qualified input adapter `{result['contract']['adapter_commit']}`",
        "- Every INPUT_READY normalized file re-hashed to its committed manifest SHA256 before any science ran.",
        "",
        "## Aggregation contract",
        "",
        f"Unit of analysis: `{result['aggregation_contract']['unit_of_analysis']}`.  "
        f"Recovered from {result['aggregation_contract']['recovered_from']}; discovery result digest "
        f"`{result['aggregation_contract']['discovery_result_digest']}`.",
        "",
        "## State counts",
        "",
    ]
    for key, value in result["state_verification"].items():
        lines.append(f"- {key}: {value}")
    lines += ["", "## Missingness", "",
              f"- frozen members: {missingness['frozen_members']}",
              f"- scheduled decisions: {missingness['scheduled_decisions']}",
              f"- scheduled member-decision opportunities: {missingness['scheduled_member_decision_opportunities']}",
              f"- usable observations: {missingness['usable_observations']}",
              f"- missing observations: {missingness['missing_observations']}",
              f"- usable fraction: {missingness['usable_fraction']:.6f}",
              f"- accounting complete (every opportunity has exactly one terminal state): "
              f"{missingness['accounting_complete']}", ""]
    for name, count in missingness["terminal_state_counts"].items():
        lines.append(f"  - {name}: {count}")
    lines += ["", "## Primary result", "",
              "| cost | bin | mean | median | positive rate | N |", "|---|---|---:|---:|---:|---:|"]
    for cost in ("BASELINE", "STRESS"):
        for bin_name in ("LOW", "MID", "HIGH"):
            cell = primary[cost][bin_name]
            lines.append(f"| {cost} | {bin_name} | {_pct(cell['mean'])} | {_pct(cell['median'])} | "
                         f"{cell['positive_fraction']:.4f} | {cell['count']} |")
    lines += ["", "| contrast | BASELINE | STRESS |", "|---|---:|---:|",
              f"| HIGH_MINUS_LOW_MEAN_UTILITY | {_pct(primary['BASELINE']['high_minus_low_mean_utility'])} | "
              f"{_pct(primary['STRESS']['high_minus_low_mean_utility'])} |",
              f"| HIGH_MINUS_LOW_POSITIVE_RATE | {_pp(primary['BASELINE']['high_minus_low_positive_rate'])} | "
              f"{_pp(primary['STRESS']['high_minus_low_positive_rate'])} |",
              "", f"MAGNITUDE VS DISCOVERY: `{result['magnitude_classification']}` "
              f"({result['magnitude_ratio_to_discovery']:.1%} of the discovery stress spread; "
              f"negligible-epsilon scale is {NEGLIGIBLE_DAILY_UTILITY * 100:.2f}%/day)", "",
              "Co-primary HIGH_MINUS_LOW_POSITIVE_RATE contrast: "
              f"{_pp(result['co_primary_positive_rate_contrast']['stress_high_minus_low_positive_rate'])} stress, "
              f"{result['co_primary_positive_rate_contrast']['assets_positive']}/"
              f"{result['co_primary_positive_rate_contrast']['assets_usable']} usable assets positive, "
              f"{result['co_primary_positive_rate_contrast']['blocks_positive']}/2 temporal blocks positive; "
              f"breadth_credible={result['co_primary_positive_rate_contrast']['breadth_credible']}.", "",
              "## Asset by asset", "",
              "| symbol | usable | missing | LOW mean | MID mean | HIGH mean | base H-L | stress H-L | "
              "base H-L pos | stress H-L pos | classification |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for symbol in COHORT:
        entry = per_asset[symbol]
        if entry["contrasts"] is None:
            lines.append(f"| {symbol} | 0 | {entry['missing_observations']} | n/a | n/a | n/a | n/a | n/a | "
                         f"n/a | n/a | {entry['classification']} |")
            continue
        b, s = entry["contrasts"]["BASELINE"], entry["contrasts"]["STRESS"]
        lines.append(
            f"| {symbol} | {entry['usable_observations']} | {entry['missing_observations']} | "
            f"{_pct(s['LOW']['mean'])} | {_pct(s['MID']['mean'])} | {_pct(s['HIGH']['mean'])} | "
            f"{_pct(b['high_minus_low_mean_utility'])} | {_pct(s['high_minus_low_mean_utility'])} | "
            f"{_pp(b['high_minus_low_positive_rate'])} | {_pp(s['high_minus_low_positive_rate'])} | "
            f"{entry['classification']} |")
    lines += ["", "## Asset breadth", "", f"- usable asset count: {breadth['usable_asset_count']}"]
    for label in ("SAME_DIRECTION", "OPPOSITE_DIRECTION", "APPROXIMATELY_NULL", "INSUFFICIENT_DATA"):
        entry = breadth[label]
        share = "" if entry["percent_of_usable"] is None else f" ({entry['percent_of_usable']:.1f}% of usable)"
        lines.append(f"- {label}: {entry['count']}{share} — {', '.join(entry['members']) or 'none'}")
    lines += ["", "## 2025 vs 2026H1", "",
              "| block | base H-L | stress H-L | stress H-L positive | usable decisions |",
              "|---|---:|---:|---:|---:|"]
    for block in ("2025", "2026H1"):
        entry = temporal[block]
        n = sum(entry["STRESS"][b]["count"] for b in ("LOW", "MID", "HIGH"))
        lines.append(f"| {block} | {_pct(entry['BASELINE']['high_minus_low_mean_utility'])} | "
                     f"{_pct(entry['STRESS']['high_minus_low_mean_utility'])} | "
                     f"{_pp(entry['STRESS']['high_minus_low_positive_rate'])} | {n} |")
    lines += ["", "## Leave-one-asset-out (stress primary aggregation)", "",
              f"- original spread: {_pct(loo['original_spread'])}",
              f"- minimum LOO spread: {_pct(loo['minimum_spread'])}",
              f"- maximum LOO spread: {_pct(loo['maximum_spread'])}",
              f"- removal weakens most: {loo['asset_whose_removal_weakens_most']}",
              f"- removal strengthens most: {loo['asset_whose_removal_strengthens_most']}",
              f"- runs retaining sign: {loo['runs_retaining_sign']}",
              f"- runs reversing sign: {loo['runs_reversing_sign']}",
              f"- excluded (no observations): {', '.join(loo['excluded_from_loo']) or 'none'}",
              "", "## Top-five attack", ""]
    for cost in ("BASELINE", "STRESS"):
        entry = tails[cost]
        retained = "n/a" if entry["retained_percentage"] is None else f"{entry['retained_percentage']:.1f}%"
        lines.append(f"- {cost}: original {_pct(entry['original_spread'])}, trimmed "
                     f"{_pct(entry['trimmed_spread'])}, retained {retained}; removed "
                     + ", ".join(f"{o['timestamp'][:10]}({o['state_bin']})" for o in entry["removed_observations"]))
    lines += ["", "## Moving-block bootstrap (7-day blocks, 1000 resamples, seed 271828)", ""]
    for cost in ("BASELINE", "STRESS"):
        entry = result["uncertainty"][cost]
        interval = entry.get("high_minus_low_mean_utility_interval_95")
        lines.append(f"- {cost}: point {_pct(entry['point_estimate'])}, 2.5% {_pct(interval[0])}, "
                     f"97.5% {_pct(interval[1])} — {entry['classification']}")
    reference = result["discovery_reference"]
    lines += ["", "## Discovery vs external replication", "",
              "| Metric | BTC/ETH/SOL discovery | External cohort |", "|---|---:|---:|",
              f"| Baseline H-L mean | {_pct(reference['baseline_high_minus_low_mean'])} | "
              f"{_pct(primary['BASELINE']['high_minus_low_mean_utility'])} |",
              f"| Stress H-L mean | {_pct(reference['stress_high_minus_low_mean'])} | "
              f"{_pct(primary['STRESS']['high_minus_low_mean_utility'])} |",
              f"| Stress positive-rate spread | {_pp(reference['stress_high_minus_low_positive_rate'])} | "
              f"{_pp(primary['STRESS']['high_minus_low_positive_rate'])} |",
              f"| Asset breadth | 3/3 positive | {breadth['SAME_DIRECTION']['count']}/"
              f"{breadth['usable_asset_count']} positive |",
              f"| Temporal sign consistency | 2024/25/26 positive | {result['temporal_sign_consistency']}/2 blocks |",
              f"| Top-five retention | 68.9% | "
              + ("n/a" if tails['STRESS']['retained_percentage'] is None
                 else f"{tails['STRESS']['retained_percentage']:.1f}%") + " |",
              f"| Bootstrap | sign uncertain | {result['uncertainty']['STRESS']['classification'].lower().replace('_', ' ')} |",
              "", "## Replication criteria", ""]
    for name, passed in result["replication_criteria"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'} — {name}")
    lines += ["", f"PRIMARY DECISION: {result['primary_decision']}",
              f"JIGSAW STATUS: {result['jigsaw_status']}",
              f"VERDICT: {result['verdict']}",
              f"NEXT ACTION: {result['next_action']}", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--materialization-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.materialization_root, args.data_root, args.output_root)
    print(json.dumps({"digest": result["result_digest"], "decision": result["primary_decision"],
                      "verdict": result["verdict"]}, sort_keys=True))


if __name__ == "__main__":
    main()
