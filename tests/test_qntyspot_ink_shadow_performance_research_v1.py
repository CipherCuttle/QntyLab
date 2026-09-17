import json
import subprocess
import tomllib
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
AUTH_PATH = ROOT / "experiments/research/qntyspot_ink_shadow_performance_research_v1/authorization.json"
PREREG_PATH = ROOT / "experiments/research/qntyspot_ink_shadow_performance_v0/preregistration.json"
PROJECTS_PATH = ROOT / "docs/state/projects.toml"
PROJECT_ID = "QNTYSPOT_INK_SHADOW_PERFORMANCE_RESEARCH_V1"
ORDER_FLOW_ID = "QNTY_EDGE_ORDER_FLOW_PROSPECTIVE_V1_ACTIVATION"
HISTORICAL_DEV_ID = "QNTYSPOT_INK_SHADOW_PERFORMANCE_DEV_ACQUISITION_V0"
BASE_SHA = "67fc6f003875c5228333fd28511cc7ff76af0427"
PREREG_DIGEST = "27ce60c68133f40d9496df1db6009de07957ed8a9bd68b0715cc6c54fe05d18a"
QNTYSPOT_SOURCE = "b9a84c59bd43e7697ee970d2a7571647e5de4501"
POOL = "0xed11ed4b195e84ba9b74c4d6ce13b7a43b354264"
CUTOFF = "2026-08-25T17:02:37Z"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def project_rows():
    return tomllib.loads(PROJECTS_PATH.read_text(encoding="utf-8"))["project"]


def project(project_id: str):
    return next(row for row in project_rows() if row["project_id"] == project_id)


def test_stage_a_branch_descends_from_the_required_parallel_lane_base():
    assert subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_SHA, "HEAD"],
        cwd=ROOT,
        check=False,
    ).returncode == 0


def test_fresh_active_research_lane_coexists_with_order_flow_without_execution_authority_leak():
    rows = project_rows()
    ordinary_active = [row for row in rows if row["state"] == "ACTIVE"]
    active_research = [row for row in rows if row["state"] == "ACTIVE_RESEARCH"]
    assert [row["project_id"] for row in ordinary_active] == [ORDER_FLOW_ID]
    assert [row["project_id"] for row in active_research] == [PROJECT_ID]

    research = active_research[0]
    assert research["implementation_authorized"] is True
    assert research["implementation_completed"] is False
    assert research["trading_authority"] == "NONE"
    assert research["capital_authority"] == "NONE"
    assert research["signing_authority"] == "NONE"
    assert research["broadcast_authority"] == "NONE"

    validated = project_context.validate_projects_registry(
        ROOT,
        tomllib.loads(PROJECTS_PATH.read_text(encoding="utf-8")),
    )
    projection = project_context.execution_authority_projection(ROOT, validated)
    assert projection["issues"] == []
    assert projection["active_project"]["project_id"] == ORDER_FLOW_ID
    assert PROJECT_ID not in projection["identity_by_project"]


def test_context_projects_operational_and_research_actions_independently():
    data = project_context.context_data(ROOT)
    assert data["active_project"]["project_id"] == ORDER_FLOW_ID
    assert data["active_research_project"]["project_id"] == PROJECT_ID
    assert data["current_permitted_next_action"] == project(ORDER_FLOW_ID)["next_action"]
    assert data["current_permitted_research_action"] == project(PROJECT_ID)["next_action"]


def test_historical_preregistration_and_source_identity_are_bound_without_scientific_mutation():
    authorization = load_json(AUTH_PATH)
    prereg = load_json(PREREG_PATH)
    frozen = authorization["frozen_scientific_binding"]
    assert frozen["historical_preregistration_project_id"] == prereg["project_id"]
    assert frozen["historical_preregistration_digest"] == prereg["preregistration_digest"] == PREREG_DIGEST
    assert frozen["historical_preregistration_status"] == prereg["status"] == "PREREGISTERED_NOT_EXECUTED"
    assert frozen["qntyspot_source_commit"] == prereg["canonical_binding"]["qntyspot_source_commit"] == QNTYSPOT_SOURCE
    assert frozen["ink_chain_id"] == prereg["canonical_binding"]["ink_chain_id"] == 57073
    assert frozen["inkyswap_v2_pool"] == prereg["canonical_binding"]["inkyswap_v2_pool"] == POOL
    assert frozen["historical_cutoff_utc"] == prereg["historical_cutoff_utc"] == CUTOFF
    assert frozen["historical_activation_reused_as_template_only"] is True
    assert frozen["historical_project_row_revived"] is False
    assert frozen["scientific_design_mutation"] is False


def test_candidate_family_and_dev_outer_chronology_remain_frozen():
    authorization = load_json(AUTH_PATH)
    prereg = load_json(PREREG_PATH)
    candidate = authorization["candidate_contract"]
    chronology = authorization["chronology_contract"]
    assert candidate["candidate_count"] == prereg["candidate_family"]["candidate_count"] == 12
    assert candidate["spacing_S"] == prereg["candidate_family"]["cartesian_product"]["spacing_S"]
    assert candidate["profit_target_P"] == prereg["candidate_family"]["cartesian_product"]["profit_target_P"]
    assert candidate["candidate_family_mutation_authorized"] is False
    assert candidate["candidate_evaluation_authorized_in_stage_a"] is False
    assert candidate["selection_inputs"] == "DEV_ONLY"
    assert chronology["dev_end_formula"] == prereg["history_boundary"]["dev_end_formula"]
    assert chronology["dev_interval"] == prereg["history_boundary"]["dev_interval"]
    assert chronology["outer_interval"] == prereg["history_boundary"]["outer_interval"]
    assert chronology["outer_initial_access"] == prereg["outer_contract"]["initial_access"] == "INACCESSIBLE"
    assert chronology["outer_evaluation_limit"] == prereg["outer_contract"]["evaluation_limit"] == 1
    assert chronology["outer_rerun_authorized"] is False


def test_stage_b_contract_is_dev_only_and_source_qualification_fails_closed():
    authorization = load_json(AUTH_PATH)
    stage_b = authorization["stage_b_dev_acquisition_contract"]
    assert stage_b["effective_only_after_exact_canonical_merge"] is True
    assert "ACQUIRE_DEV_EVIDENCE_ONLY" in stage_b["allowed_operations"]
    assert "ACQUIRE_OUTER_DELIBERATELY" in stage_b["forbidden_operations"]
    assert "EVALUATE_CANDIDATES" in stage_b["forbidden_operations"]
    assert stage_b["performance_metrics_allowed"] is False
    assert "do not inspect or serialize economic values" in stage_b["unavoidable_provider_overfetch"]

    qualification = authorization["source_qualification_contract"]
    assert qualification["fail_closed_before_full_acquisition"] is True
    assert qualification["cross_provider_material_disagreement"] == "STOP_SOURCE_CONFLICT"
    assert qualification["reorg_or_canonical_block_ambiguity"] == "STOP_SOURCE_CONFLICT"
    assert qualification["provider_choice_basis"].endswith("never observed performance")


def test_research_ledger_and_future_transition_are_explicit_without_stage_a_mutation():
    authorization = load_json(AUTH_PATH)
    ledger = authorization["research_ledger_contract"]
    transition = authorization["future_transition_contract"]
    assert ledger["preflight_command"] == "python -m qntylab.research_ledger context"
    assert ledger["stage_a_ledger_mutation_authorized"] is False
    assert ledger["candidate_execution_requires_12_valid_ledger_identities_or_fresh_append_only_records"] is True
    assert ledger["lower_level_evaluator_bypass_authorized"] is False
    assert "Separate Git-backed authorization required" in transition["stage_c"]
    assert "exactly one OUTER evaluation" in transition["stage_d"]
    assert transition["outer_release_gate"] == ["SELECTED_CANDIDATE", "SELECTED_CANDIDATE_DIGEST"]
    assert transition["post_hoc_candidate_mutation_authorized"] is False


def test_stage_a_receipts_are_zero_and_all_live_authorities_are_none():
    authorization = load_json(AUTH_PATH)
    firewall = authorization["stage_a_firewall"]
    receipts = authorization["construction_receipts"]
    assert firewall["implementation_authorized"] is True
    assert firewall["implementation_completed"] is False
    for key in (
        "market_data_access_authorized",
        "scientific_execution_authorized",
        "candidate_evaluation_authorized",
        "outer_access_authorized",
        "research_ledger_mutation_authorized",
        "qntyspot_repository_mutation_authorized",
    ):
        assert firewall[key] is False
    for key in (
        "qntyspot_live_execution_authority",
        "qnty_trading_authority",
        "capital_authority",
        "signing_authority",
        "approval_authority",
        "broadcast_authority",
        "promotion_authority",
    ):
        assert firewall[key] == "NONE"
    assert receipts == {
        "market_network_count": 0,
        "market_data_acquisition_count": 0,
        "historical_outcome_read_count": 0,
        "backtest_count": 0,
        "strategy_test_count": 0,
        "outer_evaluation_count": 0,
        "research_ledger_state_changed": False,
        "qntyspot_changed": False,
        "order_flow_changed": False,
        "hetzner_touched": False,
    }


def test_archived_historical_dev_row_remains_archived_and_is_not_revived():
    historical = project(HISTORICAL_DEV_ID)
    assert historical["state"] == "ARCHIVED"
    assert historical["future_reactivation_requires_separate_git_backed_qntylab_authorization"] is True
    assert historical["market_data_acquisition_count"] == 0
    assert historical["backtest_count"] == 0
    assert historical["strategy_test_count"] == 0
    assert historical["outer_evaluation_count"] == 0


def test_project_row_binds_the_authorization_and_preserves_zero_execution_receipts():
    authorization = load_json(AUTH_PATH)
    row = project(PROJECT_ID)
    assert row["state"] == "ACTIVE_RESEARCH"
    assert row["authority_level"] == "BOUNDED_PARALLEL_RESEARCH_REAUTHORIZATION"
    assert row["historical_preregistration_digest"] == PREREG_DIGEST
    assert row["qntyspot_source_commit"] == QNTYSPOT_SOURCE
    assert row["candidate_count"] == 12
    assert row["outer_initial_access"] == "INACCESSIBLE"
    assert row["scientific_design_mutation"] is False
    assert row["market_data_acquisition_count"] == 0
    assert row["backtest_count"] == 0
    assert row["strategy_test_count"] == 0
    assert row["outer_evaluation_count"] == 0
    assert row["research_ledger_state_changed"] is False
    assert row["qntyspot_changed"] is False
    assert row["order_flow_changed"] is False
    assert row["hetzner_touched"] is False
    assert authorization["project_id"] == row["project_id"]
    assert "experiments/research/qntyspot_ink_shadow_performance_dev_acquisition_activation_v0/activation.json" not in row["authoritative_artifacts"]


def test_generated_roadmap_names_the_active_research_lane():
    expected = (
        "- `QntySpot Ink shadow performance research V1` — `ACTIVE_RESEARCH`. "
        + project(PROJECT_ID)["next_action"]
    )
    assert expected in project_context._roadmap_bytes(ROOT).decode("utf-8")
