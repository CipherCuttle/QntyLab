from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PREREG_PATH = ROOT / "experiments/specs/h003_defensive_followup_v1.json"
PROSPECTIVE_REOPEN_CONTRACT_PATH = ROOT / "experiments/specs/h003_defensive_followup_v1_prospective_reopen_v2.json"
RECONCILIATION_PATH = ROOT / "experiments/research/h003_defensive_followup_v1/timing_semantics_reconciliation_v1.json"
STATE_PATH = ROOT / "experiments/research/state.json"

CANDIDATE_ID = "CANDIDATE_H003_MA_48_192_LONG_FLAT"
VARIANT_ID = "variant_00eb140f03a5f6ab40600160"
ARTIFACT_ID = "H003_DEFENSIVE_FOLLOWUP_V1_PROSPECTIVE_ORIGIN_V2"
PROSPECTIVE_REOPEN_AUTHORIZATION_ID = "H003_DEFENSIVE_FOLLOWUP_V1_PROSPECTIVE_REOPEN_V2"
PROSPECTIVE_REOPEN_EVENT_ID = "event_reopen_h003_defensive_followup_v1_prospective_v2"
PROSPECTIVE_REOPEN_MERGE_SHA = "9b34521d5f346408f0b18a0b45ec0973132c0b29"
PROSPECTIVE_REOPEN_MERGE_UTC = "2026-09-11T19:41:40Z"
ORIGIN_RULE_ID = "H003_PROSPECTIVE_ORIGIN_V2_GIT_LEAD_6H"
ORIGIN_SAFETY_LEAD_HOURS = 6
EXPECTED_ORIGIN_UTC = "2026-09-12T02:00:00Z"
OLD_PR266_ORIGIN_UTC = "2026-09-11T18:00:00Z"
PREREG_SHA256 = "d56da275c4339163c77cd6e5599f151964be6f61323124f9f72d98e3974f44ca"
PROSPECTIVE_REOPEN_CONTRACT_SHA256 = "baf49e3aed9a82b38e3e42e5ed936c72d23510887700d0e6c0b0ac03264ae1db"
RECONCILIATION_SHA256 = "aff7b50c424d0ef85b9bc59aa541b8c52c5f71681370668ffbebb344a9960ca3"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC)


def first_whole_hour_at_or_after(value: datetime) -> datetime:
    utc = value.astimezone(UTC)
    whole = utc.replace(minute=0, second=0, microsecond=0)
    return whole if utc == whole else whole + timedelta(hours=1)


def derive_origin(merge_timestamp_utc: str, *, lead_hours: int = ORIGIN_SAFETY_LEAD_HOURS) -> datetime:
    if lead_hours < 1:
        raise ValueError("lead_hours must be positive")
    return first_whole_hour_at_or_after(parse_utc(merge_timestamp_utc) + timedelta(hours=lead_hours))


def validate_authority_inputs() -> None:
    expected_hashes = {
        PREREG_PATH: PREREG_SHA256,
        PROSPECTIVE_REOPEN_CONTRACT_PATH: PROSPECTIVE_REOPEN_CONTRACT_SHA256,
        RECONCILIATION_PATH: RECONCILIATION_SHA256,
    }
    for path, expected in expected_hashes.items():
        actual = sha256_path(path)
        if actual != expected:
            raise RuntimeError(f"frozen source hash changed: {path}: {actual}")

    contract = _load_json(PROSPECTIVE_REOPEN_CONTRACT_PATH)
    if contract.get("authorization_id") != PROSPECTIVE_REOPEN_AUTHORIZATION_ID:
        raise RuntimeError("unexpected prospective reopen authorization")
    if contract.get("reopen_event_id") != PROSPECTIVE_REOPEN_EVENT_ID:
        raise RuntimeError("unexpected prospective reopen event")
    if contract.get("candidate_id") != CANDIDATE_ID or contract.get("variant_id") != VARIANT_ID:
        raise RuntimeError("prospective reopen identity changed")
    if contract.get("metadata", {}).get("trial_execution_authority") != "NONE":
        raise RuntimeError("prospective reopen unexpectedly grants trial execution")
    recorder = contract.get("metadata", {}).get("prospective_recorder", {})
    if recorder.get("status") != "ARMED_BUT_INACTIVE_PENDING_VALID_ORIGIN_V2_ARTIFACT":
        raise RuntimeError("prospective recorder is not pending origin-v2")
    if recorder.get("origin") is not None:
        raise RuntimeError("prospective reopen contract unexpectedly has an origin")
    for key in (
        "market_data_recording_authorized",
        "signal_recording_authorized",
        "integrity_receipt_recording_authorized",
        "economic_verdict_authorized",
    ):
        if recorder.get(key) is not False:
            raise RuntimeError(f"prospective reopen must remain inactive before origin-v2: {key}")
    if recorder.get("conditional_recording_authority") != "ACTIVE_ONLY_WHEN_ORIGIN_ARTIFACT_IS_CANONICAL_AND_VALIDATES_AGAINST_THIS_CONTRACT":
        raise RuntimeError("conditional recording authority changed")

    state = _load_json(STATE_PATH)
    variant = state.get("variants", {}).get(VARIANT_ID, {})
    if variant.get("active_reopen_event_id") != PROSPECTIVE_REOPEN_EVENT_ID:
        raise RuntimeError("prospective reopen is not the active canonical ledger generation")
    if variant.get("reopen_authorization_contract_path") != "experiments/specs/h003_defensive_followup_v1_prospective_reopen_v2.json":
        raise RuntimeError("active ledger contract path changed")
    if variant.get("reopen_authorization_contract_sha256") != PROSPECTIVE_REOPEN_CONTRACT_SHA256:
        raise RuntimeError("active ledger contract hash changed")
    if variant.get("latest_decision_event_id") is not None:
        raise RuntimeError("prospective reopen unexpectedly has a later terminal decision")

    reconciliation = _load_json(RECONCILIATION_PATH)
    if reconciliation.get("prospective_semantics", {}).get("selected_semantics") != "ORIGINALLY_PREREGISTERED_INTENDED_SEMANTICS":
        raise RuntimeError("prospective semantics selection changed")
    if reconciliation.get("origin_reconciliation", {}).get("backfill_from_2026_09_11T18_00_00Z") != "FORBIDDEN":
        raise RuntimeError("PR #266 backfill prohibition changed")


def build_origin_artifact() -> dict[str, Any]:
    validate_authority_inputs()
    origin = derive_origin(PROSPECTIVE_REOPEN_MERGE_UTC)
    expected_origin = parse_utc(EXPECTED_ORIGIN_UTC)
    if origin != expected_origin:
        raise RuntimeError(f"derived origin changed: {origin.isoformat()}")
    first_owned_end = origin + timedelta(hours=1)
    maturity = origin + timedelta(days=180)
    regime_deadline = origin + timedelta(days=365)

    return {
        "schema_version": "2.0.0",
        "artifact_id": ARTIFACT_ID,
        "candidate_id": CANDIDATE_ID,
        "variant_id": VARIANT_ID,
        "prospective_reopen_authorization_id": PROSPECTIVE_REOPEN_AUTHORIZATION_ID,
        "prospective_reopen_event_id": PROSPECTIVE_REOPEN_EVENT_ID,
        "source_contracts": {
            "preregistration_path": "experiments/specs/h003_defensive_followup_v1.json",
            "preregistration_sha256": PREREG_SHA256,
            "prospective_reopen_contract_path": "experiments/specs/h003_defensive_followup_v1_prospective_reopen_v2.json",
            "prospective_reopen_contract_sha256": PROSPECTIVE_REOPEN_CONTRACT_SHA256,
            "timing_reconciliation_path": "experiments/research/h003_defensive_followup_v1/timing_semantics_reconciliation_v1.json",
            "timing_reconciliation_sha256": RECONCILIATION_SHA256,
        },
        "prospective_reopen_merge_sha": PROSPECTIVE_REOPEN_MERGE_SHA,
        "prospective_reopen_merge_committed_at_utc": PROSPECTIVE_REOPEN_MERGE_UTC,
        "origin_rule_id": ORIGIN_RULE_ID,
        "origin_rule": "first whole UTC hour at or after prospective-reopen merge timestamp plus 6 hours",
        "origin_safety_lead_hours": ORIGIN_SAFETY_LEAD_HOURS,
        "prospective_origin_utc": origin.isoformat().replace("+00:00", "Z"),
        "superseded_pr266_origin": {
            "prospective_origin_utc": OLD_PR266_ORIGIN_UTC,
            "ownership_status": "NONE_AUTHORIZED",
            "backfill": "FORBIDDEN",
            "reason": "PR #266 origin elapsed before its artifact was canonical and lacked the canonical research-ledger activation transition; H003_TIMING_SEMANTICS_RECONCILIATION_V1 rejected it for owned prospective observations.",
        },
        "panel": {
            "assets": ["SOLUSDT", "BTCUSDT", "ETHUSDT"],
            "market": "Binance Spot",
            "timeframe": "1h",
        },
        "strategy": {
            "strategy_id": "H003_moving_average",
            "strategy_version": "existing-qntylab-strategies-v1",
            "fast": 48,
            "slow": 192,
            "mode": "long_flat",
            "leverage": 1.0,
        },
        "prospective_semantics_implementation": {
            "module": "qntylab.h003_defensive_followup_v1_prospective_reopen",
            "position_function": "prospective_h003_positions",
            "owned_return_function": "prospective_h003_owned_return_path",
            "authority_merge_sha": PROSPECTIVE_REOPEN_MERGE_SHA,
            "legacy_shifted_strategy_path_for_prospective_use": "FORBIDDEN",
        },
        "return_ownership": {
            "completed_bar_relation_owns_next_one_bar_return_exactly_once": True,
            "pre_origin_closes_may_initialize_state_only": True,
            "pre_origin_return_or_transition_cost_in_metrics": False,
            "owned_return_requires_ending_bar_timestamp_strictly_greater_than_origin": True,
            "first_possible_owned_return_end_utc": first_owned_end.isoformat().replace("+00:00", "Z"),
            "second_causal_shift": "FORBIDDEN",
        },
        "maturity": {
            "minimum_calendar_days_before_economic_verdict": 180,
            "earliest_calendar_maturity_utc": maturity.isoformat().replace("+00:00", "Z"),
            "minimum_genuine_position_state_changes_per_asset": 2,
            "maximum_calendar_days_for_regime_coverage_gate": 365,
            "regime_coverage_deadline_utc": regime_deadline.isoformat().replace("+00:00", "Z"),
            "insufficient_regime_coverage_verdict": "INCONCLUSIVE_INSUFFICIENT_REGIME_COVERAGE",
            "interim_economic_verdict": "FORBIDDEN",
        },
        "recorder_authority": {
            "authority_derivation": "ACTIVE_V2_LEDGER_REOPEN_CONTRACT_AND_CANONICAL_VALID_ORIGIN_V2_ARTIFACT_REQUIRED_TOGETHER",
            "status_after_this_artifact_is_canonical": "ACTIVE_PROSPECTIVE_SHADOW_RECORDING",
            "recording_may_begin_only_after_artifact_is_canonical": True,
            "origin_artifact_must_be_canonical_before_origin": True,
            "late_artifact_behavior": "BLOCK_AND_REISSUE_FUTURE_ORIGIN_NO_BACKFILL",
            "paper_shadow_only": True,
            "market_data_recording_authorized": True,
            "signal_recording_authorized": True,
            "integrity_receipt_recording_authorized": True,
            "economic_performance_verdict_before_maturity_forbidden": True,
            "parameter_changes_forbidden": True,
            "asset_changes_forbidden": True,
            "qnty_acceptance": "NONE",
            "qntyspot_policy": "NONE",
            "live_execution": "FORBIDDEN",
            "capital": "NONE",
            "signing": "NONE",
            "submission": "NONE",
        },
        "materialization_integrity": {
            "derived_from_git_metadata_only": True,
            "market_data_accessed_to_choose_origin": False,
            "strategy_result_accessed_to_choose_origin": False,
            "origin_may_not_be_moved_for_market_or_strategy_outcomes": True,
            "if_artifact_becomes_canonical_at_or_after_origin": "INVALID_BLOCK_AND_REISSUE_FUTURE_ORIGIN_NO_BACKFILL",
        },
    }
