from __future__ import annotations

import json
from pathlib import Path

from qntylab.research_ledger import validate_candidate_event


ROOT = Path(__file__).resolve().parents[1]
REOPEN = ROOT / "experiments/research/h003_edge_falsification_v0/reopen_event.json"
DECISIONS = ROOT / "experiments/research/decisions.jsonl"
SPEC = ROOT / "experiments/specs/h003_edge_falsification_v0.json"

CANDIDATE_ID = "CANDIDATE_H003_MA_48_192_LONG_FLAT"
VARIANT_ID = "variant_00eb140f03a5f6ab40600160"
GRAVEYARD_EVENT_ID = "event_3206c7b09c089b274ca027a5"
EXPECTED_SHA = "64bdb27a31003b0de25f3802affa8b412143a50bc8a5b76a399924626b01174a"


def test_reopen_targets_exact_terminal_h003_decision_and_validates_schema() -> None:
    event = json.loads(REOPEN.read_text(encoding="utf-8"))
    validate_candidate_event(event)

    assert event["event_type"] == "CANDIDATE_REOPENED"
    assert event["candidate_id"] == CANDIDATE_ID
    assert event["variant_id"] == VARIANT_ID
    assert event["previous_decision_event_id"] == GRAVEYARD_EVENT_ID
    assert "DEFENSIVE_RISK" in event["reason"]
    assert EXPECTED_SHA in event["material_change"]
    assert "not superseded" in event["material_change"]
    assert "no economic rehabilitation" in event["material_change"]


def test_reopen_preserves_prior_negative_evidence_and_frozen_no_search_scope() -> None:
    decisions = [json.loads(line) for line in DECISIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    prior = next(event for event in decisions if event.get("event_id") == GRAVEYARD_EVENT_ID)
    assert prior["candidate_id"] == CANDIDATE_ID
    assert prior["variant_id"] == VARIANT_ID
    assert prior["status"] == "GRAVEYARDED"
    assert prior["scope"] == "EXACT_VARIANT"
    assert prior["reason_codes"] == ["FAILED_2023_HOLDOUT_MULTIPLE_GATES"]

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    assert spec["preregistration_id"] == "H003_EDGE_FALSIFICATION_V0"
    assert spec["registration_only"] is True
    assert spec["status"] == "REGISTERED_NOT_EXECUTED"
    assert spec["scope"]["strategy_variant_count"] == 1
    assert spec["scope"]["parameter_search_allowed"] is False
    assert spec["scope"]["neighbor_parameter_testing_allowed"] is False
    assert spec["scope"]["replacement_winner_selection_allowed"] is False


def test_reopen_grants_no_execution_authority() -> None:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))["authority"]
    assert spec["qnty_acceptance"] == "NONE"
    assert spec["qntyspot_policy"] == "NONE"
    assert spec["capital"] == "NONE"
    assert spec["signing"] == "NONE"
    assert spec["submission"] == "NONE"
    assert spec["live_trading"] == "FORBIDDEN"
    assert spec["paper_trading"] == "FORBIDDEN"
    assert spec["execution"] == "FORBIDDEN"
