from __future__ import annotations

import json
from pathlib import Path

import pytest

from qntylab.h003_defensive_followup_v1_prospective_reopen import (
    AUTHORIZATION_ID,
    ORIGIN_ARTIFACT_PATH,
    ORIGIN_SAFETY_LEAD_HOURS,
    REOPEN_EVENT_ID,
    SCHEMA_COMPATIBILITY_ANCHOR_TRIAL_ID,
    VARIANT_ID,
    build_authorization_contract,
)
from qntylab.research_ledger import LedgerError, preflight, sha256_path


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_ROOT = ROOT / "experiments/research"
CONTRACT_PATH = ROOT / "experiments/specs/h003_defensive_followup_v1_prospective_reopen_v2.json"
EVENT_PATH = ROOT / "experiments/research/h003_defensive_followup_v1/prospective_reopen_v2_event.json"
STATE_PATH = RESEARCH_ROOT / "state.json"
TRIAL_INDEX_PATH = RESEARCH_ROOT / "trial_index.json"


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_contract_is_recorder_only_and_anchor_is_already_completed() -> None:
    contract = build_authorization_contract()
    assert contract["authorization_id"] == AUTHORIZATION_ID
    assert contract["authorized_trial_ids"] == [SCHEMA_COMPATIBILITY_ANCHOR_TRIAL_ID]
    assert contract["allowed_research_intents"] == ["FOLLOW_UP"]
    assert contract["metadata"]["trial_execution_authority"] == "NONE"
    assert "historical TRIAL_COMPLETED events" in contract["metadata"]["ledger_replay_status_note"]

    anchor = _load(TRIAL_INDEX_PATH)["trials"][SCHEMA_COMPATIBILITY_ANCHOR_TRIAL_ID]
    assert anchor["variant_id"] == VARIANT_ID
    assert contract["metadata"]["schema_compatibility_anchor"]["status"] == "ALREADY_COMPLETED_NON_EXECUTABLE"


def test_recorder_stays_inactive_until_valid_origin_v2() -> None:
    recorder = build_authorization_contract()["metadata"]["prospective_recorder"]
    assert recorder["status"] == "ARMED_BUT_INACTIVE_PENDING_VALID_ORIGIN_V2_ARTIFACT"
    assert recorder["origin"] is None
    assert recorder["origin_artifact_path"] == ORIGIN_ARTIFACT_PATH
    assert recorder["origin_safety_lead_hours"] == ORIGIN_SAFETY_LEAD_HOURS == 6
    assert recorder["late_origin_artifact_behavior"] == "BLOCK_AND_REISSUE_FUTURE_ORIGIN_NO_BACKFILL"
    assert recorder["market_data_recording_authorized"] is False
    assert recorder["signal_recording_authorized"] is False
    assert recorder["integrity_receipt_recording_authorized"] is False
    assert recorder["economic_verdict_authorized"] is False


def test_reconciliation_and_pr266_backfill_remain_frozen() -> None:
    reconciliation = build_authorization_contract()["metadata"]["reconciliation"]
    assert reconciliation["legacy_historical_semantics"] == "LEGACY_H003_ONE_EXTRA_BAR_DELAY"
    assert reconciliation["prospective_semantics"] == "ORIGINALLY_PREREGISTERED_INTENDED_SEMANTICS"
    assert reconciliation["historical_evidence_rewrite"] == "FORBIDDEN"
    assert reconciliation["historical_result_rerun_to_choose_semantics"] == "FORBIDDEN"
    assert reconciliation["pr266_origin_backfill"] == "FORBIDDEN"


def test_materialized_reopen_is_exact_and_all_new_trials_fail_closed() -> None:
    if not CONTRACT_PATH.exists() or not EVENT_PATH.exists():
        pytest.skip("prospective reopen v2 is materialized by the bounded workflow")
    contract = _load(CONTRACT_PATH)
    event = _load(EVENT_PATH)
    variant = _load(STATE_PATH)["variants"][VARIANT_ID]

    assert contract == build_authorization_contract()
    assert event["event_id"] == REOPEN_EVENT_ID
    assert event["authorization_contract_sha256"] == sha256_path(CONTRACT_PATH)
    # Replay processes historical trial events after reopens, so an already-tried
    # variant is labeled SCREENING. Authority still comes only from the active
    # reopen contract; this does not mean a new-generation trial ran.
    assert variant["status"] == "SCREENING"
    assert variant["latest_decision_event_id"] is None
    assert variant["active_reopen_event_id"] == REOPEN_EVENT_ID
    assert variant["reopen_authorization_contract_path"] == "experiments/specs/h003_defensive_followup_v1_prospective_reopen_v2.json"

    config = {
        "candidate_id": "CANDIDATE_H003_MA_48_192_LONG_FLAT",
        "strategy_id": "H003_moving_average",
        "strategy_version": "existing-qntylab-strategies-v1",
        "parameters": {"fast": 48, "slow": 192, "mode": "long_flat"},
        "funding_boundary_mode": "NOT_APPLICABLE",
        "expected_interval": "1h",
        "gap_policy": "REJECT",
        "evaluation_start": "2026-09-01T00:00:00Z",
        "evaluation_end": "2026-09-02T00:00:00Z",
        "fee_bps": 0,
        "slippage_bps": 0,
        "research_intent": "FOLLOW_UP",
    }
    with pytest.raises(LedgerError, match="trial not authorized by active reopen contract"):
        preflight(config=config, symbol="SOLUSDT", input_sha256="0" * 64, root=RESEARCH_ROOT)


def test_no_downstream_authority_is_created() -> None:
    authority = build_authorization_contract()["metadata"]["authority"]
    assert authority["historical_trial_execution"] == "NONE"
    assert authority["qnty_acceptance"] == "NONE"
    assert authority["qntyspot_policy"] == "NONE"
    assert authority["live_execution"] == "FORBIDDEN"
    assert authority["capital"] == "NONE"
    assert authority["signing"] == "NONE"
    assert authority["submission"] == "NONE"
