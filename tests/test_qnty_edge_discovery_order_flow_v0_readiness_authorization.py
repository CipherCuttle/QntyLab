import json
from pathlib import Path

from qntylab.research_ledger import load_canonical_history


ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "experiments/research/qnty_edge_discovery_order_flow_v0/execution/readiness_r1_authorization.json"
PREDECESSOR = ROOT / "experiments/research/qnty_edge_discovery_order_flow_v0/execution/authorization.json"
PREREG = ROOT / "experiments/specs/qnty_edge_discovery_order_flow_v0_preregistration.json"


def test_readiness_authorization_is_one_bounded_governance_phase() -> None:
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    predecessor = json.loads(PREDECESSOR.read_text(encoding="utf-8"))
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))

    assert auth["state"] == "CLOSED_PASS"
    assert auth["phase_type"] == "GOVERNANCE_ONLY"
    assert auth["authority_level"] == "GOVERNANCE_AUTHORIZATION_ONLY"
    assert auth["canonicalization"]["expected_predecessor_state"] == predecessor["state"] == "CLOSED_BLOCKED"
    assert auth["candidate_identity"]["candidate_id"] == prereg["ledger_action"]["candidate_id"]
    assert auth["candidate_identity"]["variant_id"] == prereg["ledger_action"]["variant_id"]
    assert auth["candidate_identity"]["proposal_event_id"] == prereg["ledger_action"]["event_id"]
    assert auth["frozen_contract_identity"]["preregistration_digest"] == prereg["preregistration_digest"]
    assert auth["candidate_identity"]["trial_completed_event"] is False


def test_readiness_authorization_preserves_scope_and_denies_effect_authority() -> None:
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    census = auth["expected_execution_census"]
    boundary = auth["authority_boundary"]
    later = auth["later_phase"]

    assert census["assets"] == 20
    assert census["scientific_asset_cost_cells"] == 40
    assert census["missing_cells_remain_in_denominator"] is True
    assert later["project_id"] == "QNTY_EDGE_DISCOVERY_ORDER_FLOW_V0_SOURCE_INPUT_AND_OPEN_EXECUTION_READINESS_R1"
    assert later["implementation_authorized"] is True
    assert later["scientific_execution_authorized"] is False
    assert boundary["implementation_authorized"] is False
    assert boundary["scientific_execution_authorized"] is False
    assert boundary["historical_outcome_access_authorized"] is False
    assert boundary["capital_authority"] == "NONE"
    assert boundary["downstream_authority"] == "NONE"


def test_outcome_firewall_and_ledger_invariant_are_closed() -> None:
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    firewall = auth["outcome_firewall"]
    invariant = auth["ledger_invariant"]

    assert all(value is False for value in firewall.values())
    assert invariant == {
        "new_candidate_proposed_events": 0,
        "new_candidate_reopened_events": 0,
        "new_trial_completed_events": 0,
        "exact_frozen_proposal_event_preserved": True,
    }

    history = load_canonical_history(ROOT / "experiments/research")
    target_events = [
        event
        for event in (*history.candidates, *history.decisions, *history.trials)
        if event.get("candidate_id") == auth["candidate_identity"]["candidate_id"]
        and event.get("variant_id") == auth["candidate_identity"]["variant_id"]
    ]
    assert [event["event_id"] for event in target_events if event["event_type"] == "CANDIDATE_PROPOSED"] == [
        auth["candidate_identity"]["proposal_event_id"]
    ]
    assert not any(event["event_type"] == "CANDIDATE_REOPENED" for event in target_events)
    assert not any(event["event_type"] == "TRIAL_COMPLETED" for event in target_events)
    assert len(history.trials) == 1874


def test_exactly_one_hostile_review_passed() -> None:
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    review = auth["hostile_review"]

    assert review["review_count"] == 1
    assert review["verdict"] == "PASS"
    assert review["critical_findings"] == 0
    assert review["high_findings"] == 0
    assert review["open_critical_findings"] == 0
    assert review["open_high_findings"] == 0
    assert review["targeted_rereview_used"] is False
