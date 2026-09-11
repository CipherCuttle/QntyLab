from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qntylab.research_ledger import compute_trial_id


ROOT = Path(__file__).resolve().parents[1]
PREREG_PATH = ROOT / "experiments/specs/h003_defensive_followup_v1.json"
V0_AUTH_PATH = ROOT / "experiments/specs/h003_edge_falsification_v0_trial_authorization.json"

CANDIDATE_ID = "CANDIDATE_H003_MA_48_192_LONG_FLAT"
VARIANT_ID = "variant_00eb140f03a5f6ab40600160"
AUTHORIZATION_ID = "H003_DEFENSIVE_FOLLOWUP_V1_ACTIVATION"
RESEARCH_INTENT = "FOLLOW_UP"
EXPECTED_INTERVAL = "1h"
GAP_POLICY = "REJECT"

ASSETS: tuple[dict[str, Any], ...] = (
    {
        "symbol": "BTCUSDT",
        "raw_input_sha256": "6dcc8c6293f24e2e91957b286a96d9b87fd646e4b57c846495bd41d1aa225b65",
        "normalized_2023_input_sha256": "08d5649e86743e9485fb55a3978b96f7b0b5483b33223534d52d4fe0a745d10e",
        "raw_manifest_path": "data/manifests/BTCUSDT-1h.json",
        "normalized_2023_path": "data/derived/focused_trend_validation_v1/BTCUSDT-spot-1h-2023-halt-normalized.csv",
        "normalized_2023_manifest_path": "data/derived/focused_trend_validation_v1/BTCUSDT-spot-1h-2023-halt-normalized.manifest.json",
    },
    {
        "symbol": "ETHUSDT",
        "raw_input_sha256": "3584c161874dc3b8d8f9961901e5abaadebe32a1aaba6d321106b8ccb1f61187",
        "normalized_2023_input_sha256": "a3cfb7733aad701b43fd383ac32f52252d229d2275147698449b2007bdff0d40",
        "raw_manifest_path": "data/manifests/ETHUSDT-1h.json",
        "normalized_2023_path": "data/derived/focused_trend_validation_v1/ETHUSDT-spot-1h-2023-halt-normalized.csv",
        "normalized_2023_manifest_path": "data/derived/focused_trend_validation_v1/ETHUSDT-spot-1h-2023-halt-normalized.manifest.json",
    },
)

COST_MODES: tuple[dict[str, Any], ...] = (
    {"id": "zero_cost_diagnostic", "fee_bps": 0, "slippage_bps": 0},
    {"id": "baseline", "fee_bps": 10, "slippage_bps": 0},
    {"id": "stress", "fee_bps": 10, "slippage_bps": 10},
    {"id": "severe_stress", "fee_bps": 10, "slippage_bps": 20},
)

# Same causal window geometry as H003_EDGE_FALSIFICATION_V0. The only changed
# endpoint is the last frozen block, which is clipped to the exact BTC/ETH
# historical snapshot end. BLOCK_2021_SEGMENT_04 remains excluded because it
# has only 121 closes, below the 193-close causal warm-up requirement.
WINDOWS: tuple[dict[str, Any], ...] = (
    {"id": "BLOCK_2021_SEGMENT_01", "evaluation_start": "2021-01-01T00:00:00Z", "evaluation_end": "2021-02-11T03:00:00Z", "input_kind": "raw"},
    {"id": "BLOCK_2021_SEGMENT_02", "evaluation_start": "2021-02-11T05:00:00Z", "evaluation_end": "2021-03-06T01:00:00Z", "input_kind": "raw"},
    {"id": "BLOCK_2021_SEGMENT_03", "evaluation_start": "2021-03-06T03:00:00Z", "evaluation_end": "2021-04-20T01:00:00Z", "input_kind": "raw"},
    {"id": "BLOCK_2021_SEGMENT_05", "evaluation_start": "2021-04-25T08:00:00Z", "evaluation_end": "2021-08-13T01:00:00Z", "input_kind": "raw"},
    {"id": "BLOCK_2021_SEGMENT_06", "evaluation_start": "2021-08-13T06:00:00Z", "evaluation_end": "2021-09-29T06:00:00Z", "input_kind": "raw"},
    {"id": "BLOCK_2021_SEGMENT_07", "evaluation_start": "2021-09-29T09:00:00Z", "evaluation_end": "2021-12-31T23:00:00Z", "input_kind": "raw"},
    {"id": "BLOCK_2022", "evaluation_start": "2021-12-23T23:00:00Z", "evaluation_end": "2022-12-31T23:00:00Z", "input_kind": "raw"},
    {"id": "BLOCK_2023_KNOWN_HOLDOUT", "evaluation_start": "2022-12-02T00:00:00Z", "evaluation_end": "2023-12-31T23:00:00Z", "input_kind": "normalized_2023"},
    {"id": "BLOCK_2024", "evaluation_start": "2023-12-23T23:00:00Z", "evaluation_end": "2024-12-31T23:00:00Z", "input_kind": "raw"},
    {"id": "BLOCK_2025", "evaluation_start": "2024-12-23T23:00:00Z", "evaluation_end": "2025-12-31T23:00:00Z", "input_kind": "raw"},
    {"id": "BLOCK_2026_TO_FREEZE", "evaluation_start": "2025-12-23T23:00:00Z", "evaluation_end": "2026-07-28T18:00:00Z", "input_kind": "raw"},
)

EXCLUDED_WINDOWS = (
    {
        "id": "BLOCK_2021_SEGMENT_04",
        "evaluation_start": "2021-04-20T04:00:00Z",
        "evaluation_end": "2021-04-25T04:00:00Z",
        "reason": "121_CLOSES_LT_193_MINIMUM",
    },
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def _validate_frozen_inputs() -> None:
    prereg = _load_json(PREREG_PATH)
    if prereg.get("authorization_id") != "H003_DEFENSIVE_FOLLOWUP_V1":
        raise RuntimeError("unexpected H003 defensive follow-up preregistration")
    if prereg.get("activation_boundary", {}).get("generic_trial_execution_authorized") is not False:
        raise RuntimeError("preregistration is not fail closed")
    if prereg.get("prospective_panel", {}).get("assets") != ["SOLUSDT", "BTCUSDT", "ETHUSDT"]:
        raise RuntimeError("prospective panel identity changed")
    diagnostic = prereg.get("prior_exposed_retrospective_diagnostic", {})
    if diagnostic.get("prior_exposure_acknowledged") is not True:
        raise RuntimeError("historical BTC/ETH prior exposure not acknowledged")
    rows = {row["symbol"]: row for row in diagnostic.get("assets", [])}
    if set(rows) != {"BTCUSDT", "ETHUSDT"}:
        raise RuntimeError("diagnostic asset set changed")
    for asset in ASSETS:
        row = rows[asset["symbol"]]
        if row.get("raw_sha256") != asset["raw_input_sha256"]:
            raise RuntimeError(f"raw input identity changed: {asset['symbol']}")
        if row.get("normalized_2023_sha256") != asset["normalized_2023_input_sha256"]:
            raise RuntimeError(f"normalized 2023 input identity changed: {asset['symbol']}")
        if row.get("historical_end") != "2026-07-28T18:00:00Z" or row.get("expected_rows") != 48821:
            raise RuntimeError(f"frozen snapshot boundary changed: {asset['symbol']}")

    # Ensure the activation window geometry remains exactly inherited from V0
    # through 2025, rather than being selected after seeing BTC/ETH history.
    v0 = _load_json(V0_AUTH_PATH)
    v0_windows = {row["id"]: row for row in v0["metadata"]["windows"]}
    for window in WINDOWS:
        prior = v0_windows[window["id"]]
        if prior["evaluation_start"] != window["evaluation_start"]:
            raise RuntimeError(f"window start drift: {window['id']}")
        if window["id"] != "BLOCK_2026_TO_FREEZE" and prior["evaluation_end"] != window["evaluation_end"]:
            raise RuntimeError(f"window end drift: {window['id']}")


def diagnostic_trial_rows() -> list[dict[str, Any]]:
    _validate_frozen_inputs()
    rows: list[dict[str, Any]] = []
    for asset in ASSETS:
        for window in WINDOWS:
            input_sha256 = (
                asset["normalized_2023_input_sha256"]
                if window["input_kind"] == "normalized_2023"
                else asset["raw_input_sha256"]
            )
            for cost in COST_MODES:
                trial_id = compute_trial_id(
                    variant_id=VARIANT_ID,
                    symbol=asset["symbol"],
                    input_sha256=input_sha256,
                    evaluation_start=window["evaluation_start"],
                    evaluation_end=window["evaluation_end"],
                    fee_bps=float(cost["fee_bps"]),
                    slippage_bps=float(cost["slippage_bps"]),
                    gap_policy=GAP_POLICY,
                    expected_interval=EXPECTED_INTERVAL,
                )
                rows.append(
                    {
                        "trial_id": trial_id,
                        "symbol": asset["symbol"],
                        "window_id": window["id"],
                        "evaluation_start": window["evaluation_start"],
                        "evaluation_end": window["evaluation_end"],
                        "input_kind": window["input_kind"],
                        "input_sha256": input_sha256,
                        "cost_mode": cost["id"],
                        "fee_bps": cost["fee_bps"],
                        "slippage_bps": cost["slippage_bps"],
                    }
                )
    if len(rows) != 88 or len({row["trial_id"] for row in rows}) != 88:
        raise RuntimeError("expected exactly 88 unique diagnostic trial IDs")
    return rows


def build_authorization_contract(*, reopen_event_id: str) -> dict[str, Any]:
    rows = diagnostic_trial_rows()
    return {
        "schema_version": "1.0.0",
        "authorization_id": AUTHORIZATION_ID,
        "reopen_event_id": reopen_event_id,
        "candidate_id": CANDIDATE_ID,
        "variant_id": VARIANT_ID,
        "allowed_research_intents": [RESEARCH_INTENT],
        "authorized_trial_ids": [row["trial_id"] for row in rows],
        "metadata": {
            "preregistration_id": "H003_DEFENSIVE_FOLLOWUP_V1",
            "purpose": "PRIOR_EXPOSED_RETROSPECTIVE_DIAGNOSTIC_ONLY",
            "confirmation_authority": "NONE",
            "strategy_id": "H003_moving_average",
            "strategy_version": "existing-qntylab-strategies-v1",
            "parameters": {"fast": 48, "slow": 192, "mode": "long_flat"},
            "expected_interval": EXPECTED_INTERVAL,
            "gap_policy": GAP_POLICY,
            "minimum_pre_reporting_closes": 193,
            "excluded_windows": list(EXCLUDED_WINDOWS),
            "windows": [dict(window) for window in WINDOWS],
            "cost_modes": [dict(cost) for cost in COST_MODES],
            "assets": [dict(asset) for asset in ASSETS],
            "diagnostic_trials": rows,
            "prospective_recorder": {
                "status": "ARMED_BUT_INACTIVE_PENDING_ORIGIN_ARTIFACT",
                "assets": ["SOLUSDT", "BTCUSDT", "ETHUSDT"],
                "market": "Binance Spot",
                "timeframe": "1h",
                "origin_rule": "next whole UTC hour strictly after activation merge commit timestamp",
                "origin": None,
                "market_data_recording_authorized": False,
                "signal_recording_authorized": False,
                "economic_verdict_authorized": False,
                "origin_artifact_requires_separate_git_commit": True,
            },
            "authority": {
                "qntylab_only": True,
                "historical_diagnostic": "EXACT_88_TRIAL_IDS_ONLY",
                "prospective_recorder": "ARMED_BUT_INACTIVE_PENDING_ORIGIN_ARTIFACT",
                "qnty_acceptance": "NONE",
                "qntyspot_policy": "NONE",
                "live_execution": "FORBIDDEN",
                "capital": "NONE",
                "signing": "NONE",
                "submission": "NONE",
            },
        },
    }
