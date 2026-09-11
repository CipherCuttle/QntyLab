from __future__ import annotations

import json
import subprocess
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest

from qntylab.h003_defensive_followup_v1_origin_v2 import (
    EXPECTED_ORIGIN_UTC,
    OLD_PR266_ORIGIN_UTC,
    ORIGIN_SAFETY_LEAD_HOURS,
    PROSPECTIVE_REOPEN_MERGE_SHA,
    PROSPECTIVE_REOPEN_MERGE_UTC,
    PROSPECTIVE_REOPEN_EVENT_ID,
    PROSPECTIVE_REOPEN_CONTRACT_SHA256,
    VARIANT_ID,
    build_origin_artifact,
    derive_origin,
    parse_utc,
    validate_artifact_canonicalization_time,
)
from qntylab.h003_defensive_followup_v1_prospective_reopen import (
    prospective_h003_owned_return_path,
    prospective_h003_positions,
)


ROOT = Path(__file__).resolve().parents[1]
ORIGIN_PATH = ROOT / "experiments/research/h003_defensive_followup_v1/prospective_origin_v2.json"
STATE_PATH = ROOT / "experiments/research/state.json"
CONTRACT_PATH = ROOT / "experiments/specs/h003_defensive_followup_v1_prospective_reopen_v2.json"


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_origin_v2_is_exact_git_only_derivation_from_reopen_merge() -> None:
    git_timestamp = subprocess.check_output(
        ["git", "show", "-s", "--format=%cI", PROSPECTIVE_REOPEN_MERGE_SHA],
        cwd=ROOT,
        text=True,
    ).strip()
    assert parse_utc(git_timestamp) == parse_utc(PROSPECTIVE_REOPEN_MERGE_UTC)

    derived = derive_origin(git_timestamp)
    assert derived == parse_utc(EXPECTED_ORIGIN_UTC)
    assert ORIGIN_SAFETY_LEAD_HOURS == 6
    assert derived >= parse_utc(git_timestamp) + timedelta(hours=6)
    assert derived.minute == derived.second == derived.microsecond == 0

    artifact = _load(ORIGIN_PATH)
    assert artifact == build_origin_artifact()
    integrity = artifact["materialization_integrity"]
    assert integrity["derived_from_git_metadata_only"] is True
    assert integrity["market_data_accessed_to_choose_origin"] is False
    assert integrity["strategy_result_accessed_to_choose_origin"] is False
    assert integrity["origin_may_not_be_moved_for_market_or_strategy_outcomes"] is True
    assert integrity["canonicalization_time_proof_required_before_recording"] is True


def test_origin_v2_canonicalization_deadline_is_executable_and_fail_closed() -> None:
    origin = parse_utc(EXPECTED_ORIGIN_UTC)
    before = origin - timedelta(microseconds=1)
    assert validate_artifact_canonicalization_time(before.isoformat()) == before

    with pytest.raises(RuntimeError, match="BLOCK_AND_REISSUE_FUTURE_ORIGIN_NO_BACKFILL"):
        validate_artifact_canonicalization_time(EXPECTED_ORIGIN_UTC)
    with pytest.raises(RuntimeError, match="BLOCK_AND_REISSUE_FUTURE_ORIGIN_NO_BACKFILL"):
        validate_artifact_canonicalization_time((origin + timedelta(seconds=1)).isoformat())

    authority = _load(ORIGIN_PATH)["recorder_authority"]
    assert authority["status_after_this_artifact_is_canonical"] == "CONDITIONAL_PROSPECTIVE_SHADOW_RECORDING_REQUIRES_CANONICALIZATION_TIME_GUARD"
    assert authority["canonicalization_time_guard_function"] == "validate_artifact_canonicalization_time"
    assert authority["recording_authority_requires_canonicalization_timestamp_strictly_before_origin"] is True
    assert authority["unconditional_recording_authority"] is False
    assert authority["market_data_recording_authorized_if_guard_passes"] is True
    assert authority["signal_recording_authorized_if_guard_passes"] is True
    assert authority["integrity_receipt_recording_authorized_if_guard_passes"] is True


def test_origin_v2_requires_active_exact_ledger_contract_not_dual_authority() -> None:
    artifact = _load(ORIGIN_PATH)
    state = _load(STATE_PATH)
    contract = _load(CONTRACT_PATH)
    variant = state["variants"][VARIANT_ID]

    assert variant["active_reopen_event_id"] == PROSPECTIVE_REOPEN_EVENT_ID
    assert variant["reopen_authorization_contract_sha256"] == PROSPECTIVE_REOPEN_CONTRACT_SHA256
    assert variant["latest_decision_event_id"] is None
    assert contract["metadata"]["trial_execution_authority"] == "NONE"

    pending = contract["metadata"]["prospective_recorder"]
    assert pending["status"] == "ARMED_BUT_INACTIVE_PENDING_VALID_ORIGIN_V2_ARTIFACT"
    assert pending["origin"] is None
    assert pending["conditional_recording_authority"] == "ACTIVE_ONLY_WHEN_ORIGIN_ARTIFACT_IS_CANONICAL_AND_VALIDATES_AGAINST_THIS_CONTRACT"
    assert pending["market_data_recording_authorized"] is False
    assert pending["signal_recording_authorized"] is False
    assert pending["integrity_receipt_recording_authorized"] is False

    authority = artifact["recorder_authority"]
    assert authority["authority_derivation"] == "ACTIVE_V2_LEDGER_REOPEN_CONTRACT_AND_CANONICAL_VALID_ORIGIN_V2_ARTIFACT_REQUIRED_TOGETHER"
    assert authority["recording_may_begin_only_after_artifact_is_canonical"] is True
    assert authority["origin_artifact_must_be_canonical_before_origin"] is True
    assert authority["late_artifact_behavior"] == "BLOCK_AND_REISSUE_FUTURE_ORIGIN_NO_BACKFILL"


def test_old_pr266_origin_is_rejected_and_cannot_backfill() -> None:
    artifact = _load(ORIGIN_PATH)
    old = artifact["superseded_pr266_origin"]
    assert old["prospective_origin_utc"] == OLD_PR266_ORIGIN_UTC == "2026-09-11T18:00:00Z"
    assert old["ownership_status"] == "NONE_AUTHORIZED"
    assert old["backfill"] == "FORBIDDEN"
    assert parse_utc(artifact["prospective_origin_utc"]) > parse_utc(OLD_PR266_ORIGIN_UTC)


def test_origin_v2_binds_executable_one_step_prospective_semantics() -> None:
    artifact = _load(ORIGIN_PATH)
    implementation = artifact["prospective_semantics_implementation"]
    assert implementation["position_function"] == "prospective_h003_positions"
    assert implementation["owned_return_function"] == "prospective_h003_owned_return_path"
    assert implementation["legacy_shifted_strategy_path_for_prospective_use"] == "FORBIDDEN"

    # Same discriminating one-bar LONG pulse used by the timing reconciliation:
    # completed row 192 owns 192->193 exactly once; row 193 is FLAT so the
    # following return is unowned.
    close = np.r_[np.full(144, 0.5), np.full(48, 0.4), 5.2, 0.01, 1.0]
    position = prospective_h003_positions(close)
    owned = prospective_h003_owned_return_path(close)
    assert position[192] == 1.0
    assert position[193] == 0.0
    assert np.isclose(owned[192], close[193] / close[192] - 1.0)
    assert owned[193] == 0.0

    ownership = artifact["return_ownership"]
    assert ownership["completed_bar_relation_owns_next_one_bar_return_exactly_once"] is True
    assert ownership["pre_origin_closes_may_initialize_state_only"] is True
    assert ownership["pre_origin_return_or_transition_cost_in_metrics"] is False
    assert ownership["owned_return_requires_ending_bar_timestamp_strictly_greater_than_origin"] is True
    assert ownership["first_possible_owned_return_end_utc"] == "2026-09-12T03:00:00Z"
    assert ownership["second_causal_shift"] == "FORBIDDEN"


def test_origin_v2_freezes_maturity_and_shadow_only_authority() -> None:
    artifact = _load(ORIGIN_PATH)
    assert artifact["panel"] == {
        "assets": ["SOLUSDT", "BTCUSDT", "ETHUSDT"],
        "market": "Binance Spot",
        "timeframe": "1h",
    }
    assert artifact["strategy"] == {
        "strategy_id": "H003_moving_average",
        "strategy_version": "existing-qntylab-strategies-v1",
        "fast": 48,
        "slow": 192,
        "mode": "long_flat",
        "leverage": 1.0,
    }

    maturity = artifact["maturity"]
    assert maturity["minimum_calendar_days_before_economic_verdict"] == 180
    assert maturity["earliest_calendar_maturity_utc"] == "2027-03-11T02:00:00Z"
    assert maturity["minimum_genuine_position_state_changes_per_asset"] == 2
    assert maturity["maximum_calendar_days_for_regime_coverage_gate"] == 365
    assert maturity["regime_coverage_deadline_utc"] == "2027-09-12T02:00:00Z"
    assert maturity["interim_economic_verdict"] == "FORBIDDEN"

    authority = artifact["recorder_authority"]
    assert authority["status_after_this_artifact_is_canonical"] == "CONDITIONAL_PROSPECTIVE_SHADOW_RECORDING_REQUIRES_CANONICALIZATION_TIME_GUARD"
    assert authority["paper_shadow_only"] is True
    assert authority["market_data_recording_authorized_if_guard_passes"] is True
    assert authority["signal_recording_authorized_if_guard_passes"] is True
    assert authority["integrity_receipt_recording_authorized_if_guard_passes"] is True
    assert authority["economic_performance_verdict_before_maturity_forbidden"] is True
    assert authority["parameter_changes_forbidden"] is True
    assert authority["asset_changes_forbidden"] is True
    assert authority["qnty_acceptance"] == "NONE"
    assert authority["qntyspot_policy"] == "NONE"
    assert authority["live_execution"] == "FORBIDDEN"
    assert authority["capital"] == "NONE"
    assert authority["signing"] == "NONE"
    assert authority["submission"] == "NONE"
