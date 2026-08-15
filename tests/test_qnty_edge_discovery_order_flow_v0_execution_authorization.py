import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "experiments/research/qnty_edge_discovery_order_flow_v0/execution/authorization.json"
PREREG = ROOT / "experiments/specs/qnty_edge_discovery_order_flow_v0_preregistration.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_authorization_is_blocked_and_binds_frozen_preregistration() -> None:
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))

    assert auth["state"] == "CLOSED_BLOCKED"
    assert auth["authority_level"] == "HISTORICAL_SCIENTIFIC_EXECUTION_AUTHORIZATION_BLOCKED"
    assert auth["canonicalization"]["preregistration_json_sha256"] == _sha(PREREG)
    assert auth["canonicalization"]["preregistration_digest"] == prereg["preregistration_digest"]
    assert auth["candidate_identity"]["proposal_event_id"] == prereg["ledger_action"]["event_id"]
    assert auth["candidate_identity"]["trial_completed_event"] is False
    assert auth["candidate_identity"]["h010_reopened"] is False


def test_authorization_preserves_denominator_and_grants_no_effect_authority() -> None:
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    census = auth["expected_execution_census"]
    assert census["scientific_asset_cost_cells"] == 40
    assert census["assets"] == 20
    assert census["cost_modes"] == 2
    assert census["diagnostics_are_eligible_survivors"] is False
    assert census["execution_started"] is False

    boundary = auth["authority_boundary"]
    assert boundary["execution_authorized"] is False
    assert boundary["historical_outcome_access_authorized"] is False
    assert boundary["paper_or_live_trading_authorized"] is False
    assert boundary["capital_authority"] == "NONE"


def test_readiness_fails_closed_without_scientific_outputs() -> None:
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    readiness = auth["readiness"]
    assert readiness["source_semantics"]["buy_sell_partition_proven"] is False
    assert readiness["source_semantics"]["normalized_input_preserves_required_fields"] is False
    assert readiness["timing"]["existing_kernel_compatible"] is False
    assert readiness["execution_accounting"]["target_open_entry"] is False
    firewall = auth["outcome_firewall"]
    assert all(value is False for value in firewall.values())
