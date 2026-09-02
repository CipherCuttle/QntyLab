import hashlib
import json
import subprocess
import tomllib
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
ACTIVATION_PATH = ROOT / "experiments/research/qntyspot_ink_shadow_performance_dev_acquisition_activation_v0/activation.json"
PREREG_PATH = ROOT / "experiments/research/qntyspot_ink_shadow_performance_v0/preregistration.json"
PROJECTS_PATH = ROOT / "docs/state/projects.toml"
PROJECT_ID = "QNTYSPOT_INK_SHADOW_PERFORMANCE_DEV_ACQUISITION_ACTIVATION_V0"
FUTURE_PHASE = "QNTYSPOT_INK_SHADOW_PERFORMANCE_DEV_ACQUISITION_V0"
PARENT_PROJECT = "QNTYSPOT_INK_SHADOW_PERFORMANCE_V0"
EXPECTED_CANONICAL_BASE = "3ef188452f077f246870dd647253b49c4a6691d3"
ACTIVATION_CANONICAL_BASE = "3617633b4f88d3669ab58229aa9ca9bf5c2bee9e"
PREREG_CANDIDATE_SHA = "74b1afb5bf49aadbf8e58caff58b7f31e387c918"
PREREG_DIGEST = "27ce60c68133f40d9496df1db6009de07957ed8a9bd68b0715cc6c54fe05d18a"
QNTYSPOT_SOURCE = "b9a84c59bd43e7697ee970d2a7571647e5de4501"
CUTOFF = "2026-08-25T17:02:37Z"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def projects():
    registry = tomllib.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    return registry["project"]


def project_record(project_id=PROJECT_ID):
    return next(row for row in projects() if row["project_id"] == project_id)


def test_canonical_master_and_preregistration_are_exact():
    assert subprocess.run(["git", "rev-parse", "origin/master"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip() == EXPECTED_CANONICAL_BASE
    assert subprocess.run(["git", "merge-base", "--is-ancestor", PREREG_CANDIDATE_SHA, EXPECTED_CANONICAL_BASE], cwd=ROOT, check=False).returncode == 0
    prereg = load(PREREG_PATH)
    assert prereg["project_id"] == "QNTYSPOT_INK_SHADOW_PERFORMANCE_V0_PREREGISTRATION"
    assert prereg["status"] == "PREREGISTERED_NOT_EXECUTED"
    assert prereg["preregistration_digest"] == PREREG_DIGEST
    assert prereg["canonical_binding"]["qntyspot_source_commit"] == QNTYSPOT_SOURCE
    assert prereg["historical_cutoff_utc"] == CUTOFF


def test_frozen_identity_and_family_are_unchanged():
    activation = load(ACTIVATION_PATH)
    prereg = load(PREREG_PATH)
    frozen = activation["frozen_scientific_identity"]
    binding = prereg["canonical_binding"]
    assert frozen["ink_chain_id"] == 57073
    assert frozen["base_token"] == binding["base_token"]
    assert frozen["quote_token"] == binding["quote_token"]
    assert frozen["inkyswap_v2_factory"] == binding["inkyswap_v2_factory"]
    assert frozen["inkyswap_v2_pool"] == binding["inkyswap_v2_pool"]
    assert frozen["candidate_family_count"] == len(prereg["candidate_family"]["candidates"]) == 12
    assert prereg["history_boundary"]["dev_end_formula"] == "T0 + floor(0.60 * (T1 - T0))"
    assert prereg["history_boundary"]["dev_interval"] == "[T0, DEV_END]"
    assert prereg["history_boundary"]["outer_interval"] == "(DEV_END, T1]"


def test_exactly_one_future_phase_and_dev_only_scope():
    activation = load(ACTIVATION_PATH)
    future = activation["authorized_future_phase"]
    assert future["project_id"] == FUTURE_PHASE
    assert future["exactly_one_future_phase"] is True
    assert future["future_phase_count"] == 1
    assert future["allowed_operations"] == [
        "SOURCE_QUALIFICATION",
        "ESTABLISH_T0_OUTCOME_BLIND",
        "COMPUTE_DEV_END",
        "ACQUIRE_DEV_EVIDENCE_ONLY",
        "ACQUIRE_DEV_GAS_RECEIPTS_AS_PREREGISTERED",
        "BUILD_DEV_INTEGRITY_MANIFEST",
    ]
    assert future["forbidden_operations"] == [
        "ACQUIRE_OUTER", "INSPECT_OUTER", "EVALUATE_CANDIDATES", "SELECT_CANDIDATE",
        "FREEZE_WINNER", "BACKTEST_OUTER", "FINAL_PERFORMANCE_CLASSIFICATION",
        "TRADING", "CAPITAL", "SIGNING", "APPROVAL", "BROADCAST", "PROMOTION",
    ]
    assert future["outer_remains_inaccessible"] is True


def test_source_qualification_boundary_and_manifest_contract_are_fail_closed():
    activation = load(ACTIVATION_PATH)
    qualification = activation["source_qualification_contract"]
    assert qualification["fail_closed_before_full_acquisition"] is True
    assert qualification["provider_choice_basis"].startswith("technical capability")
    assert qualification["cross_provider_material_disagreement"] == "STOP_SOURCE_CONFLICT"
    assert qualification["reorg_or_canonical_block_ambiguity"] == "STOP_SOURCE_CONFLICT"
    scope = activation["dev_acquisition_scope"]
    assert scope["outcome_blind_source_selection"] is True
    assert scope["broadening_for_interesting_extra_data"] is False
    assert scope["chart_or_derivative_price_substitution"] is False
    assert activation["manifest_contract"]["performance_metrics_allowed"] is False


def test_dev_boundary_and_outer_firewall_are_explicit():
    activation = load(ACTIVATION_PATH)
    boundary = activation["dev_boundary_contract"]
    assert boundary["t0_outcome_blind"] is True
    assert boundary["t0_selection_by_returns_or_candidate_behavior"] is False
    assert boundary["t1"] == CUTOFF
    assert boundary["minimum_history_days"] == {"total_calendar_history": 30, "dev": 18, "outer": 12}
    outer = activation["outer_firewall"]
    assert outer["outer_data_acquired"] is False
    assert outer["outer_outcome_inspected"] is False
    assert outer["outer_evaluation_count"] == 0
    assert "do not inspect or serialize economic values" in outer["unavoidable_overfetch"]


def test_branch_firewall_receipts_and_authorities_are_zero_or_none():
    activation = load(ACTIVATION_PATH)
    firewall = activation["branch_firewall"]
    for key in (
        "scientific_execution_authorized", "market_data_access_authorized",
        "historical_economic_outcome_inspection_authorized", "backtest_authorized",
        "strategy_test_authorized", "research_ledger_mutation_authorized",
        "qntyspot_changed", "research_ledger_state_changed",
    ):
        assert firewall[key] is False
    for key in ("trading_authority", "capital_authority", "qntyspot_execution_authority", "signing_authority", "approval_authority", "broadcast_authority", "promotion_authority"):
        assert firewall[key] == "NONE"
    receipts = activation["construction_receipts"]
    assert all(value == 0 or value is False for value in receipts.values())
    assert receipts["market_network_count"] == 0
    assert receipts["market_data_acquisition_count"] == 0
    assert receipts["historical_outcome_read_count"] == 0
    assert receipts["backtest_count"] == 0
    assert receipts["strategy_test_count"] == 0


def test_future_activation_requires_exact_merge_and_does_not_self_authorize():
    activation = load(ACTIVATION_PATH)
    gate = activation["canonicalization"]
    assert gate["expected_canonical_base_sha"] == ACTIVATION_CANONICAL_BASE
    assert gate["preregistration_candidate_sha"] == PREREG_CANDIDATE_SHA
    assert gate["preregistration_canonical_merge"] == ACTIVATION_CANONICAL_BASE
    assert gate["candidate_branch_is_authority"] is False
    assert gate["branch_local_candidate_does_not_self_authorize"] is True
    assert gate["exact_candidate_commit_must_be_ancestor_of_canonical_master"] is True
    assert gate["activation_effective_on_branch"] is False
    assert gate["effective_only_after_exact_canonical_merge"] is True
    assert gate["effective_only_in_fresh_clean_worktree_from_origin_master"] is True


def test_registry_binding_and_review_receipt_are_exact():
    activation = load(ACTIVATION_PATH)
    project = project_record()
    assert activation["phase_state"] == "PLANNED_NOT_AUTHORIZED"
    assert activation["candidate_state"] == "ACTIVE_CANDIDATE"
    transition = activation["canonical_state_transition"]
    assert transition == {
        "candidate_phase_state": "PLANNED_NOT_AUTHORIZED",
        "canonical_phase_state": "CLOSED_PASS",
        "successor_project_id": FUTURE_PHASE,
        "canonical_successor_state": "ACTIVE",
        "exactly_one_successor": True,
        "effective_only_after_exact_canonical_merge": True,
        "effective_only_in_fresh_clean_worktree_from_origin_master": True,
    }
    assert project["state"] == "CLOSED_PASS"
    assert project["candidate_state"] == "CANONICAL_TERMINAL_EFFECTIVE"
    assert project["canonicalization_status"] == "EXACT_CANONICAL_MERGE_TRANSITION_DECLARED"
    assert project["implementation_authorized"] is False
    assert project["canonical_base_sha"] == ACTIVATION_CANONICAL_BASE
    assert project["canonical_preregistration_digest"] == PREREG_DIGEST
    assert project["future_phase_project_id"] == FUTURE_PHASE
    assert project["future_phase_count"] == 1
    assert project["qntyspot_source_commit"] == QNTYSPOT_SOURCE
    assert project["historical_data_cutoff_utc"] == CUTOFF
    assert project["market_data_access_authorized"] is False
    assert project["scientific_execution_authorized"] is False
    assert project["backtest_authorized"] is False
    assert project["strategy_test_authorized"] is False
    assert project["research_ledger_mutation_authorized"] is False
    assert project["trading_authority"] == "NONE"
    assert project["capital_authority"] == "NONE"
    assert project["hostile_review_count"] == activation["review_policy"]["hostile_review_count"] == 1
    assert project["targeted_governance_rereview_used"] is True
    assert project["targeted_governance_rereview_count"] == activation["review_policy"]["targeted_rereview_count"] == 1
    assert project["targeted_governance_rereview_verdict"] == "PASS_NO_CRITICAL_HIGH"
    assert project["hostile_review_verdict"] == "PASS"
    receipt = (ACTIVATION_PATH.parent / "hostile_governance_review.md").read_text(encoding="utf-8")
    assert receipt.count("HOSTILE_REVIEW = PASS") == 1
    assert "Critical findings: 0" in receipt
    assert "High findings: 0" in receipt


def test_activation_and_registry_do_not_mutate_scientific_or_ledger_state():
    activation = load(ACTIVATION_PATH)
    assert activation["frozen_scientific_identity"]["scientific_design_mutation"] is False
    assert activation["branch_firewall"]["research_ledger_state_changed"] is False
    assert activation["branch_firewall"]["qntyspot_changed"] is False
    ledger_diff = subprocess.run(["git", "diff", "--name-only", "HEAD", "--", "experiments/research/ledger"], cwd=ROOT, text=True, capture_output=True, check=True).stdout
    qntyspot_diff = subprocess.run(["git", "diff", "--name-only", "HEAD", "--", "qntyspot"], cwd=ROOT, text=True, capture_output=True, check=True).stdout
    assert ledger_diff == ""
    assert qntyspot_diff == ""


def test_activation_artifact_is_present_and_digestable():
    assert hashlib.sha256(ACTIVATION_PATH.read_bytes()).hexdigest()


def test_historical_transition_is_preserved_while_current_successor_is_archived():
    registry = projects()
    successors = [row for row in registry if row["project_id"] == FUTURE_PHASE]
    assert len(successors) == 1
    successor = successors[0]
    assert successor["state"] == "ARCHIVED"
    assert successor["historical_canonical_state"] == "ACTIVE"
    assert successor["historical_activation_receipt_preserved"] is True
    assert project_record(PARENT_PROJECT)["state"] == "CLOSED_PASS"
    parent_next_action = project_record(PARENT_PROJECT)["next_action"]
    assert FUTURE_PHASE in parent_next_action
    assert "create the separate" not in parent_next_action.lower()
    assert "exact canonical merge" in parent_next_action
    assert "fresh clean worktree" in parent_next_action
    assert [row for row in registry if row["state"] == "ACTIVE"] == []


def test_successor_binding_and_authority_ceiling_are_exact():
    successor = project_record(FUTURE_PHASE)
    assert successor["project_id"] == FUTURE_PHASE
    assert successor["governing_activation_project_id"] == PROJECT_ID
    assert successor["parent_project_id"] == PARENT_PROJECT
    assert successor["canonical_preregistration_digest"] == PREREG_DIGEST
    assert successor["qntyspot_source_commit"] == QNTYSPOT_SOURCE
    assert successor["historical_data_cutoff_utc"] == CUTOFF
    assert successor["permitted_operations"] == [
        "SOURCE_QUALIFICATION", "ESTABLISH_T0_OUTCOME_BLIND", "COMPUTE_DEV_END",
        "ACQUIRE_DEV_EVIDENCE_ONLY", "ACQUIRE_DEV_GAS_RECEIPTS_AS_PREREGISTERED",
        "BUILD_DEV_INTEGRITY_MANIFEST",
    ]
    assert successor["forbidden_operations"] == [
        "ACQUIRE_OUTER", "INSPECT_OUTER", "EVALUATE_CANDIDATES", "SELECT_CANDIDATE",
        "FREEZE_WINNER", "BACKTEST_OUTER", "FINAL_PERFORMANCE_CLASSIFICATION",
        "TRADING", "CAPITAL", "SIGNING", "APPROVAL", "BROADCAST", "PROMOTION",
    ]
    assert successor["implementation_authorized"] is False
    assert successor["scientific_execution_authorized"] is False
    assert successor["market_data_access_authorized"] is False
    assert successor["historical_economic_outcome_inspection_authorized"] is False
    assert successor["backtest_authorized"] is False
    assert successor["strategy_test_authorized"] is False
    assert successor["research_ledger_mutation_authorized"] is False
    for key in (
        "trading_authority", "capital_authority", "signing_authority",
        "approval_authority", "broadcast_authority", "promotion_authority",
        "qntyspot_execution_authority",
    ):
        assert successor[key] == "NONE"


def test_active_dev_authority_repair_is_narrow_and_preserves_all_receipts():
    successor = project_record(FUTURE_PHASE)
    assert successor["permitted_operations"] == [
        "SOURCE_QUALIFICATION", "ESTABLISH_T0_OUTCOME_BLIND", "COMPUTE_DEV_END",
        "ACQUIRE_DEV_EVIDENCE_ONLY", "ACQUIRE_DEV_GAS_RECEIPTS_AS_PREREGISTERED",
        "BUILD_DEV_INTEGRITY_MANIFEST",
    ]
    assert successor["forbidden_operations"] == [
        "ACQUIRE_OUTER", "INSPECT_OUTER", "EVALUATE_CANDIDATES", "SELECT_CANDIDATE",
        "FREEZE_WINNER", "BACKTEST_OUTER", "FINAL_PERFORMANCE_CLASSIFICATION",
        "TRADING", "CAPITAL", "SIGNING", "APPROVAL", "BROADCAST", "PROMOTION",
    ]
    assert successor["outer_data_acquired"] is False
    assert successor["outer_outcome_inspected"] is False
    assert successor["outer_evaluation_count"] == 0
    assert successor["market_network_count"] == 0
    assert successor["market_data_acquisition_count"] == 0
    assert successor["historical_outcome_read_count"] == 0
    assert successor["backtest_count"] == 0
    assert successor["strategy_test_count"] == 0
    assert successor["research_ledger_state_changed"] is False
    assert successor["qntyspot_changed"] is False
    assert successor["canonical_preregistration_digest"] == PREREG_DIGEST
    assert successor["qntyspot_source_commit"] == QNTYSPOT_SOURCE
    assert successor["historical_data_cutoff_utc"] == CUTOFF


def test_successor_outer_firewall_and_construction_receipts_remain_zero():
    successor = project_record(FUTURE_PHASE)
    assert successor["outer_data_acquired"] is False
    assert successor["outer_outcome_inspected"] is False
    assert successor["outer_evaluation_count"] == 0
    for key in (
        "market_network_count", "market_data_acquisition_count", "historical_outcome_read_count",
        "backtest_count", "strategy_test_count",
    ):
        assert successor[key] == 0
    assert successor["research_ledger_state_changed"] is False
    assert successor["qntyspot_changed"] is False


def test_archived_successor_is_not_project_context_active_authority():
    _, _, registry = project_context.load_context_sources(ROOT)
    validated = project_context.validate_projects_registry(ROOT, registry)
    projection = project_context.execution_authority_projection(ROOT, validated)
    assert projection["issues"] == []
    assert projection["active_project"] is None


def test_scientific_research_ledger_and_qntyspot_bytes_are_unchanged():
    assert subprocess.run(
        ["git", "diff", "--quiet", EXPECTED_CANONICAL_BASE, "HEAD", "--", "qntylab/qntyspot_ink_shadow_performance_prereg_v0.py", PREREG_PATH.relative_to(ROOT)],
        cwd=ROOT,
        check=False,
    ).returncode == 0
    for pathspec in ("experiments/research/ledger", "qntyspot"):
        assert subprocess.run(
            ["git", "diff", "--name-only", EXPECTED_CANONICAL_BASE, "HEAD", "--", pathspec],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        ).stdout == ""


def test_exactly_one_targeted_rereview_passed_without_repeating_hostile_review():
    rereview = (ACTIVATION_PATH.parent / "targeted_rereview.md").read_text(encoding="utf-8")
    assert rereview.count("TARGETED_REREVIEW = PASS") == 1
    assert rereview.count("CRITICAL = 0") == 1
    assert rereview.count("HIGH = 0") == 1
    assert "canonical state transition" in rereview.lower()
    assert "parent continuation" in rereview.lower()
    assert "branch-local self-authorization" in rereview.lower()
    assert "outer firewall" in rereview.lower()
