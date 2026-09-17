import json
import subprocess
import tomllib
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_PATH = ROOT / "docs/state/projects.toml"
AUTH_PATH = ROOT / "experiments/research/qntyspot_ink_shadow_performance_dev_acquisition_research_v1/authorization.json"
STAGE_A_ID = "QNTYSPOT_INK_SHADOW_PERFORMANCE_RESEARCH_V1"
STAGE_B_ID = "QNTYSPOT_INK_SHADOW_PERFORMANCE_DEV_ACQUISITION_RESEARCH_V1"
ORDER_FLOW_ID = "QNTY_EDGE_ORDER_FLOW_PROSPECTIVE_V1_ACTIVATION"
HISTORICAL_DEV_ID = "QNTYSPOT_INK_SHADOW_PERFORMANCE_DEV_ACQUISITION_V0"
BASE_SHA = "ea2dd02964c2e91196bb153a212ec0f8aae50b42"
PREREG_DIGEST = "27ce60c68133f40d9496df1db6009de07957ed8a9bd68b0715cc6c54fe05d18a"


def rows():
    return tomllib.loads(PROJECTS_PATH.read_text(encoding="utf-8"))["project"]


def project(project_id: str):
    return next(row for row in rows() if row["project_id"] == project_id)


def authorization():
    return json.loads(AUTH_PATH.read_text(encoding="utf-8"))


def test_stage_b_branch_descends_from_exact_stage_a_canonical_merge():
    assert subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_SHA, "HEAD"],
        cwd=ROOT,
        check=False,
    ).returncode == 0


def test_research_lane_rotates_from_closed_stage_a_to_one_active_stage_b():
    registry = rows()
    ordinary_active = [row for row in registry if row["state"] == "ACTIVE"]
    active_research = [row for row in registry if row["state"] == "ACTIVE_RESEARCH"]
    assert [row["project_id"] for row in ordinary_active] == [ORDER_FLOW_ID]
    assert [row["project_id"] for row in active_research] == [STAGE_B_ID]

    stage_a = project(STAGE_A_ID)
    stage_b = project(STAGE_B_ID)
    assert stage_a["state"] == "CLOSED_PASS"
    assert stage_a["implementation_authorized"] is False
    assert stage_a["implementation_completed"] is True
    assert stage_a["superseded_by"] == [STAGE_B_ID]
    assert stage_b["supersedes"] == [STAGE_A_ID]
    assert stage_b["implementation_authorized"] is True
    assert stage_b["implementation_completed"] is False

    validated = project_context.validate_projects_registry(
        ROOT, tomllib.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    )
    projection = project_context.execution_authority_projection(ROOT, validated)
    assert projection["issues"] == []
    assert projection["active_project"]["project_id"] == ORDER_FLOW_ID
    assert STAGE_A_ID not in projection["identity_by_project"]
    assert STAGE_B_ID not in projection["identity_by_project"]


def test_stage_b_authority_is_canonicalization_gated_and_branch_network_receipts_are_zero():
    auth = authorization()
    row = project(STAGE_B_ID)
    assert auth["project_id"] == row["project_id"] == STAGE_B_ID
    assert auth["canonicalization"]["required_base_sha"] == row["required_base_sha"] == BASE_SHA
    assert auth["canonicalization"]["candidate_branch_is_authority"] is False
    assert auth["canonicalization"]["effective_only_after_exact_canonical_merge"] is True
    assert auth["canonicalization"]["runtime_requires_clean_worktree"] is True
    assert auth["canonicalization"]["runtime_refresh_origin_master_before_check"] is True
    assert auth["canonicalization"]["runtime_head_must_equal_refreshed_origin_master"] is True
    assert auth["canonicalization"]["runtime_required_base_must_be_ancestor"] is True
    assert auth["canonicalization"]["runtime_exact_reviewed_candidate_must_be_ancestor"] is True
    assert auth["source_qualification_contract"]["network_execution_effective_only_after_exact_canonical_merge"] is True
    assert auth["implementation_contract"]["real_network_execution_in_this_candidate_pr"] is False
    assert row["activation_effective_on_branch"] is False
    assert row["market_network_count"] == 0
    assert row["market_data_acquisition_count"] == 0
    assert row["historical_outcome_read_count"] == 0
    assert row["outer_evaluation_count"] == 0
    assert row["source_qualification_receipt_present"] is False
    assert row["dev_dataset_present"] is False
    assert row["dev_manifest_present"] is False


def test_frozen_science_and_outer_firewall_are_preserved():
    auth = authorization()
    frozen = auth["frozen_scientific_binding"]
    assert frozen["preregistration_digest"] == PREREG_DIGEST
    assert frozen["candidate_count"] == 12
    assert frozen["dev_end_formula"] == "T0 + floor(0.60 * (T1 - T0))"
    assert frozen["dev_interval"] == "[T0, DEV_END]"
    assert frozen["outer_interval"] == "(DEV_END, T1]"
    assert frozen["scientific_design_mutation"] is False
    assert frozen["minimum_history_days"] == {"total_calendar_history": 30, "dev": 18, "outer": 12}
    assert frozen["insufficient_history_state"] == "INSUFFICIENT_HISTORY"

    outer = auth["outer_firewall"]
    assert outer["initial_access"] == "INACCESSIBLE"
    assert outer["deliberate_outer_request_authorized"] is False
    assert "no source request may deliberately retrieve economic observations" in outer["request_boundary"]
    assert "DEV_END" in outer["request_boundary"]
    assert outer["preferred_query_boundary"] == "terminate economic ranges at or before DEV_END"
    assert outer["outer_economic_value_inspection_authorized"] is False
    assert outer["outer_serialization_authorized"] is False
    assert outer["outer_evaluation_authorized"] is False
    assert outer["outer_evaluation_count"] == 0

    dev = auth["dev_acquisition_contract"]
    assert dev["enabled_only_after_source_qualification_pass"] is True
    assert "ACQUIRE_DEV_EVIDENCE_ONLY" in dev["allowed_operations"]
    assert "ACQUIRE_OUTER_DELIBERATELY" in dev["forbidden_operations"]
    assert "EVALUATE_CANDIDATES" in dev["forbidden_operations"]
    assert dev["performance_metrics_allowed"] is False
    assert "later DEV acquisition only" in dev["unavoidable_provider_overfetch"]


def test_source_qualification_is_outcome_blind_fail_closed_and_dev_bounded_before_economic_probe():
    auth = authorization()
    source = auth["source_qualification_contract"]
    assert source["outcome_blind"] is True
    assert source["provider_choice_basis"].endswith("never observed performance")
    assert source["t1_access_class"] == "BLOCK_METADATA_ONLY_BEFORE_DEV_BOUNDARY_EXISTS"
    assert "one block at a time" in source["t0_method"]
    assert source["dev_end_must_be_computed_before_multi_block_economic_query"] is True
    assert source["economic_request_boundary"] == (
        "no Sync-log or transaction-receipt request may deliberately target a block after DEV_END"
    )
    assert source["provider_overreturn_beyond_requested_dev_range"].startswith("STOP_SOURCE_CONFLICT")
    assert source["raw_economic_log_values_may_be_decoded_during_qualification"] is False
    assert source["qualification_receipt_may_serialize_raw_log_data"] is False
    assert source["cross_provider_material_disagreement"] == "STOP_SOURCE_CONFLICT"
    assert source["reorg_or_canonical_block_ambiguity"] == "STOP_SOURCE_CONFLICT"
    assert source["silent_truncation_or_nondeterminism"] == "STOP_SOURCE_CONFLICT"
    assert source["full_dev_log_identity_coverage_required"] is True
    assert source["canonical_log_block_binding_required"] is True
    assert source["receipt_transaction_and_block_binding_required"] is True
    assert source["cross_provider_material_identity_includes_dev_log_digest"] is True
    assert source["receipt_gas_fields_required"] == ["gasUsed", "effectiveGasPrice"]


def test_candidate_evaluation_ledger_mutation_and_live_authorities_remain_forbidden():
    auth = authorization()
    assert auth["research_ledger_contract"]["mutation_authorized"] is False
    assert auth["research_ledger_contract"]["candidate_evaluation_authorized"] is False
    receipts = auth["authority_and_receipts"]
    assert receipts["backtest_count"] == 0
    assert receipts["strategy_test_count"] == 0
    assert receipts["research_ledger_state_changed"] is False
    assert receipts["qntyspot_changed"] is False
    assert receipts["order_flow_changed"] is False
    assert receipts["hetzner_touched"] is False
    for key in (
        "qntyspot_execution_authority",
        "trading_authority",
        "capital_authority",
        "signing_authority",
        "approval_authority",
        "broadcast_authority",
        "promotion_authority",
    ):
        assert receipts[key] == "NONE"


def test_archived_v0_dev_project_is_not_revived():
    historical = project(HISTORICAL_DEV_ID)
    assert historical["state"] == "ARCHIVED"
    assert historical["implementation_authorized"] is False
    assert authorization()["predecessor_contract"]["historical_dev_project_revived"] is False


def test_context_exposes_stage_b_only_as_research_not_execution_authority():
    data = project_context.context_data(ROOT)
    assert data["active_project"]["project_id"] == ORDER_FLOW_ID
    assert data["active_research_project"]["project_id"] == STAGE_B_ID
    assert data["current_permitted_next_action"] == project(ORDER_FLOW_ID)["next_action"]
    assert data["current_permitted_research_action"] == project(STAGE_B_ID)["next_action"]
