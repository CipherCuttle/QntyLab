from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RECONCILIATION_PATH = ROOT / "experiments/research/h003_defensive_followup_v1/timing_semantics_reconciliation_v1.json"
TRIAL_INDEX_PATH = ROOT / "experiments/research/trial_index.json"

CANDIDATE_ID = "CANDIDATE_H003_MA_48_192_LONG_FLAT"
VARIANT_ID = "variant_00eb140f03a5f6ab40600160"
FAMILY_ID = "moving_average_trend"
AUTHORIZATION_ID = "H003_DEFENSIVE_FOLLOWUP_V1_PROSPECTIVE_REOPEN_V2"
REOPEN_EVENT_ID = "event_reopen_h003_defensive_followup_v1_prospective_v2"
PREVIOUS_DECISION_EVENT_ID = "event_decision_232206a8b9e45a253b952b3e"
RECONCILIATION_SHA256 = "aff7b50c424d0ef85b9bc59aa541b8c52c5f71681370668ffbebb344a9960ca3"
SCHEMA_COMPATIBILITY_ANCHOR_TRIAL_ID = "trial_0266a97d15efec0c22cf6884"
ORIGIN_ARTIFACT_PATH = "experiments/research/h003_defensive_followup_v1/prospective_origin_v2.json"
ORIGIN_SAFETY_LEAD_HOURS = 6


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def validate_frozen_inputs() -> None:
    reconciliation = _load_json(RECONCILIATION_PATH)
    if sha256_bytes(RECONCILIATION_PATH.read_bytes()) != RECONCILIATION_SHA256:
        raise RuntimeError("H003 timing reconciliation SHA changed")
    if reconciliation.get("candidate_id") != CANDIDATE_ID or reconciliation.get("variant_id") != VARIANT_ID:
        raise RuntimeError("H003 timing reconciliation identity changed")
    if reconciliation.get("finding", {}).get("status") != "CONFIRMED_IMPLEMENTATION_PREREG_DIVERGENCE":
        raise RuntimeError("H003 timing reconciliation no longer records the confirmed divergence")
    if reconciliation.get("prospective_semantics", {}).get("selected_semantics") != "ORIGINALLY_PREREGISTERED_INTENDED_SEMANTICS":
        raise RuntimeError("H003 prospective semantics selection changed")
    if reconciliation.get("origin_reconciliation", {}).get("backfill_from_2026_09_11T18_00_00Z") != "FORBIDDEN":
        raise RuntimeError("PR #266 origin backfill prohibition changed")

    trial_index = _load_json(TRIAL_INDEX_PATH)
    anchor = trial_index.get("trials", {}).get(SCHEMA_COMPATIBILITY_ANCHOR_TRIAL_ID)
    if not isinstance(anchor, dict) or anchor.get("variant_id") != VARIANT_ID:
        raise RuntimeError("schema compatibility anchor must remain an already-completed exact-variant trial")


def build_authorization_contract() -> dict[str, Any]:
    validate_frozen_inputs()
    return {
        "schema_version": "1.0.0",
        "authorization_id": AUTHORIZATION_ID,
        "reopen_event_id": REOPEN_EVENT_ID,
        "candidate_id": CANDIDATE_ID,
        "variant_id": VARIANT_ID,
        "allowed_research_intents": ["FOLLOW_UP"],
        "authorized_trial_ids": [SCHEMA_COMPATIBILITY_ANCHOR_TRIAL_ID],
        "metadata": {
            "purpose": "PROSPECTIVE_SHADOW_RECORDER_ONLY",
            "trial_execution_authority": "NONE",
            "schema_compatibility_anchor": {
                "trial_id": SCHEMA_COMPATIBILITY_ANCHOR_TRIAL_ID,
                "status": "ALREADY_COMPLETED_NON_EXECUTABLE",
                "reason": "Research-ledger contract schema 1.0 requires at least one trial ID. This exact-variant ID is already canonical-completed; FOLLOW_UP duplicate enforcement makes it non-executable, REPLICATION is not an allowed intent, and no other trial ID is authorized.",
            },
            "reconciliation": {
                "path": "experiments/research/h003_defensive_followup_v1/timing_semantics_reconciliation_v1.json",
                "sha256": RECONCILIATION_SHA256,
                "legacy_historical_semantics": "LEGACY_H003_ONE_EXTRA_BAR_DELAY",
                "prospective_semantics": "ORIGINALLY_PREREGISTERED_INTENDED_SEMANTICS",
                "historical_evidence_rewrite": "FORBIDDEN",
                "historical_result_rerun_to_choose_semantics": "FORBIDDEN",
                "pr266_origin_backfill": "FORBIDDEN",
            },
            "prospective_recorder": {
                "status": "ARMED_BUT_INACTIVE_PENDING_VALID_ORIGIN_V2_ARTIFACT",
                "assets": ["SOLUSDT", "BTCUSDT", "ETHUSDT"],
                "market": "Binance Spot",
                "timeframe": "1h",
                "parameters": {"fast": 48, "slow": 192, "mode": "long_flat", "leverage": 1.0},
                "causal_rule": "completed bar t computes sign(MA48-MA192) and that decision owns t->t+1 exactly once",
                "origin": None,
                "origin_artifact_path": ORIGIN_ARTIFACT_PATH,
                "origin_rule_id": "H003_PROSPECTIVE_ORIGIN_V2_GIT_LEAD_6H",
                "origin_rule": "first whole UTC hour at or after prospective-reopen merge timestamp plus 6 hours",
                "origin_safety_lead_hours": ORIGIN_SAFETY_LEAD_HOURS,
                "origin_source": "Git merge metadata only; market data and outcomes forbidden",
                "conditional_recording_authority": "ACTIVE_ONLY_WHEN_ORIGIN_ARTIFACT_IS_CANONICAL_AND_VALIDATES_AGAINST_THIS_CONTRACT",
                "late_origin_artifact_behavior": "BLOCK_AND_REISSUE_FUTURE_ORIGIN_NO_BACKFILL",
                "market_data_recording_authorized": False,
                "signal_recording_authorized": False,
                "integrity_receipt_recording_authorized": False,
                "economic_verdict_authorized": False,
                "minimum_maturity_calendar_days": 180,
                "minimum_genuine_state_changes_per_asset": 2,
                "maximum_regime_coverage_calendar_days": 365,
            },
            "authority": {
                "qntylab_only": True,
                "historical_trial_execution": "NONE",
                "prospective_recorder": "CONDITIONAL_PENDING_VALID_ORIGIN_V2_ARTIFACT",
                "qnty_acceptance": "NONE",
                "qntyspot_policy": "NONE",
                "live_execution": "FORBIDDEN",
                "capital": "NONE",
                "signing": "NONE",
                "submission": "NONE",
            },
        },
    }


def build_reopen_event(*, contract_sha256: str, recorded_at_utc: str) -> dict[str, Any]:
    validate_frozen_inputs()
    return {
        "event_id": REOPEN_EVENT_ID,
        "event_type": "CANDIDATE_REOPENED",
        "candidate_id": CANDIDATE_ID,
        "variant_id": VARIANT_ID,
        "previous_decision_event_id": PREVIOUS_DECISION_EVENT_ID,
        "reason": "Reopen only the prospective shadow-recorder setup after the confirmed timing-semantics reconciliation; historical trial execution and PR #266-origin backfill remain forbidden.",
        "material_change": "Binds prospective intended t->t+1 semantics, a fail-closed recorder-only contract, and a Git-derived future-origin rule with six hours of fixed safety lead. Recording remains inactive until a separately committed origin-v2 artifact validates against this active contract.",
        "recorded_at_utc": recorded_at_utc,
        "authorization_contract_path": "experiments/specs/h003_defensive_followup_v1_prospective_reopen_v2.json",
        "authorization_contract_sha256": contract_sha256,
    }
