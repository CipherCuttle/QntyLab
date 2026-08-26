from __future__ import annotations

import json
import tomllib
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
PHASE_ROOT = (
    ROOT
    / "experiments/research/qnty_agent_orchestration_control_contract_v0"
    / "dsh_stage_a_v1r3r2_execution_contract_reconciliation_authorization_v0"
)
AUTH = json.loads((PHASE_ROOT / "authorization.json").read_text(encoding="utf-8"))
PROJECT_ID = "DSH_STAGE_A_V1R3R2_EXECUTION_CONTRACT_RECONCILIATION_AUTHORIZATION_V0"
REPAIR_ID = "DSH_STAGE_A_V1R3R2_EXECUTION_CONTRACT_RECONCILIATION_V0"
CANONICAL_MASTER = "ded772d59c6135689ac4bda8878979721855a955"
PREDECESSOR_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R6"
PREDECESSOR_OUTCOME = "V0R6_LIVE_EPISODE_CLOSED_BLOCKED_NO_REPLAY"


def _project_record() -> dict[str, object]:
    registry = tomllib.loads(
        (ROOT / "docs/state/projects.toml").read_text(encoding="utf-8")
    )
    return next(item for item in registry["project"] if item["project_id"] == PROJECT_ID)


def test_authorization_is_candidate_only_and_does_not_self_authorize() -> None:
    assert AUTH["phase_state"] == "ACTIVE_CANDIDATE"
    assert AUTH["phase_type"] == "GOVERNANCE_ONLY_BOUNDED_REPAIR_AUTHORIZATION"
    assert AUTH["authority_level"] == "AUTHORIZED_IF_CANONICAL"
    assert AUTH["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert AUTH["authorization_effective"] == "AFTER_EXACT_CANONICAL_MERGE_ONLY"
    assert AUTH["successor_binding"]["effective_repair_authority"] is False
    assert AUTH["successor_binding"]["branch_local_candidate_does_not_self_authorize"] is True
    assert AUTH["successor_binding"]["future_repair_must_reconcile_canonical_source_again"] is True
    assert AUTH["canonicalization"]["branch_local_artifact_does_not_self_authorize"] is True
    assert AUTH["canonicalization"]["canonical_presence_required_before_implementation"] is True
    assert AUTH["canonicalization"]["no_auto_merge"] is True


def test_authorization_binds_to_exact_canonical_base_and_closed_v0r6_predecessor() -> None:
    identity = AUTH["canonical_source_identity"]
    assert identity["canonical_master"] == CANONICAL_MASTER
    assert identity["canonical_merge_parents"] == [
        "4195433872140634784c404f88fa0c70a6bcfd11",
        "3dc9b1d28d2170fde33c09ba123ce81209acb505",
    ]
    assert identity["predecessor_project_id"] == PREDECESSOR_ID
    assert identity["predecessor_required_state"] == "CLOSED_BLOCKED"
    assert identity["predecessor_terminal_outcome"] == PREDECESSOR_OUTCOME
    assert identity["canonical_drift_behavior"] == "STOP_SOURCE_CONFLICT"
    assert identity["git_wins_over_prompt_memory_or_handoff"] is True
    assert AUTH["canonicalization"]["candidate_base_sha"] == CANONICAL_MASTER
    assert AUTH["reconciliation"]["origin_master"] == CANONICAL_MASTER


def test_live_boundary_counters_are_all_zero() -> None:
    counters = AUTH["live_boundary_counters"]
    assert counters == {
        "real_secret_reads": 0,
        "production_claims": 0,
        "provider_calls": 0,
        "live_dsh_invocations": 0,
        "real_codex_turns": 0,
        "real_claude_turns": 0,
        "spend_usd": "0",
    }
    assert AUTH["construction_receipts"] == {
        "secret_reads": 0,
        "production_claim_writes": 0,
        "diagnostic_claim_writes": 0,
        "dsh_invocations": 0,
        "provider_requests": 0,
        "real_model_calls": 0,
        "codex_turns": 0,
        "claude_turns": 0,
        "v0r6_mutations": 0,
        "v0r7_created": False,
        "spend_usd": "0",
    }


def test_forbidden_scope_is_explicit() -> None:
    forbidden = AUTH["future_repair_scope"]["forbidden_operations"]
    for op in (
        "REPLAY_V0R5",
        "REPLAY_V0R6",
        "CREATE_V0R7",
        "START_ANOTHER_STAGE_A_LIVE_EPISODE",
        "STAGE_B",
        "SCIENTIFIC_EXECUTION",
        "QNTY_RUNTIME",
        "QNTY_PROMOTION",
        "TRADING",
        "CAPITAL",
        "BROADER_PRODUCTION_USE",
    ):
        assert op in forbidden

    assert AUTH["future_repair_scope"]["production_claim_namespace_mutation_allowed"] is False
    assert AUTH["future_repair_scope"]["v0r5_replay_allowed"] is False
    assert AUTH["future_repair_scope"]["v0r6_replay_allowed"] is False
    assert AUTH["future_repair_scope"]["v0r7_creation_allowed"] is False

    protected = AUTH["protected_historical_v0r6"]
    assert protected["project_id"] == PREDECESSOR_ID
    assert protected["terminal_state"] == PREDECESSOR_OUTCOME
    assert protected["remote_claim_ref_mutation_allowed"] is False
    assert protected["local_state_mutation_allowed"] is False
    assert protected["replay_allowed"] is False
    assert protected["second_episode_allowed"] is False

    forbidden_authority = AUTH["forbidden_authority"]
    assert forbidden_authority["secret_read_authorized"] is False
    assert forbidden_authority["provider_io_authorized"] is False
    assert forbidden_authority["live_dsh_authorized"] is False
    assert forbidden_authority["v0r7_authorized"] is False
    assert forbidden_authority["v0r5_replay_authorized"] is False
    assert forbidden_authority["v0r6_replay_authorized"] is False
    assert forbidden_authority["stage_b_authorized"] is False
    assert forbidden_authority["scientific_execution_authorized"] is False
    assert forbidden_authority["trading_authorized"] is False
    assert forbidden_authority["capital_authority"] == "NONE"
    assert forbidden_authority["promotion_authority"] == "NONE"
    assert forbidden_authority["broader_production_authority"] == "NONE"


def test_registry_and_generated_roadmap_bind_the_candidate() -> None:
    record = _project_record()
    assert record["state"] == "CLOSED_PASS"
    assert record["candidate_state"] == "CANONICAL_AUTHORIZATION_EFFECTIVE"
    assert record["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert record["authorization_effective"] == "AFTER_EXACT_CANONICAL_MERGE_ONLY"
    assert record["canonicalization_status"] == "EXACT_CANONICAL_MERGE_VERIFIED"
    assert record["canonical_authorization_merge"] == "3a0e1aa15c6c5d01a93dd7e3460dd3a736c46474"
    assert record["canonical_authorization_merge_parents"] == [
        "abdaf42f67038ef970b2c233ad80baa1643ea6de",
        "8ee3a671bc9be1d55811e701d0a2b82f3e1d39ee",
    ]
    assert record["repair_authority_was_effective"] is True
    assert record["implementation_completed"] is True
    assert record["effective_repair_authority"] is False
    assert record["implementation_authorized"] is False
    assert record["canonical_base_sha"] == CANONICAL_MASTER
    assert record["canonical_predecessor_project_id"] == PREDECESSOR_ID
    assert record["canonical_predecessor_required_state"] == "CLOSED_BLOCKED"
    assert record["canonical_predecessor_terminal_outcome"] == PREDECESSOR_OUTCOME
    assert record["future_repair_project_id"] == REPAIR_ID
    assert record["authorization_artifact_sha256"] == (
        "ee20d5165ebda69fb7f78d3e0a046705ded3f2abe8340800596b991db94438d1"
    )

    _, _, registry = project_context.load_context_sources(ROOT)
    validated = project_context.validate_projects_registry(ROOT, registry)
    projection = project_context.execution_authority_projection(ROOT, validated)
    assert projection["issues"] == []
    assert projection["active_project"] is None

    roadmap = (ROOT / "docs/CURRENT_ROADMAP.md").read_text(encoding="utf-8")
    assert "DSH Stage-A V1R3R2 execution contract reconciliation authorization V0" in roadmap
    assert "CLOSED_PASS: reconciliation is canonical and terminal" in roadmap
    assert "DSH Stage-A V1R3R2 execution contract reconciliation authorization V0" not in roadmap.split("## Queued — not authorized")[1].split("## ")[0]
    assert "RUN_V0R7" not in roadmap
    assert "RUN_LIVE_DSH" not in roadmap
    assert "REPLAY_V0R5" not in roadmap
    assert "REPLAY_V0R6" not in roadmap


# ---------------------------------------------------------------------------
# Focused tests for the bounded authorization-candidate correction (defects 1-3)
# ---------------------------------------------------------------------------

# The exact 25-item class-level reconciliation scope the future repair phase is
# authorized to perform, NON-LIVE, as closure of the frozen execution-contract
# reconciliation objective.
REQUIRED_ALLOWED_OPERATIONS = [
    "RECONCILE_CANONICAL_SOURCE_AGAIN_BEFORE_ANY_REPAIR",
    "RECONSTRUCT_COMPLETE_EXECUTION_DEPENDENCY_DAG",
    "SEPARATE_HISTORICAL_VERIFICATION_FROM_CURRENT_CONTRACT_DERIVATION",
    "COMPUTE_REVERSE_TRANSITIVE_INVALIDATION_MECHANICALLY",
    "CREATE_NEW_CURRENT_GENERATION_CONTRACT_ARTIFACTS_WHERE_REQUIRED",
    "PRESERVE_HISTORICAL_A392_50BD_AND_V0R5_V0R6_EVIDENCE_IMMUTABLE",
    "REWIRE_PREPARE_PRODUCTION_LAUNCH_AND_DIRECTLY_RELATED_PRODUCTION_CONTRACT_SELECTION_TO_CURRENT_CONTRACT_ROOT",
    "REWIRE_COMPOSITE_AND_IMMEDIATE_PRE_SPAWN_VERIFICATION_TO_CURRENT_CONTRACT_ROOT",
    "REMOVE_STALE_HISTORICAL_CONTRACT_PATHS_FROM_CURRENT_PRODUCTION_TRUTH",
    "ESTABLISH_EXACTLY_ONE_EPISODECLAIM_ACQUISITION_OWNER",
    "VERIFY_AND_FREEZE_EXECUTABLE_SECRET_CLAIM_BUDGET_PROVIDER_CHILD_STATE_MACHINE",
    "ENSURE_PROVIDER_IO_CANNOT_PRECEDE_CLAIM_COMMITTED",
    "BIND_CLAIM_SOURCE_TO_EXACT_IMMUTABLE_COMMIT_SHA_WITH_SEPARATE_CANONICALITY_AND_REVOCATION_CHECKS",
    "VERIFY_CLEAN_SOURCE_AND_WORKTREE_SEMANTICS_BEFORE_IRREVERSIBLE_CLAIM_BOUNDARY",
    "VERIFY_ACTUAL_CURRENT_NODE_PYTHON_CODEX_CLAUDE_EXECUTABLE_IDENTITIES",
    "DETERMINISTICALLY_VERIFY_OR_REMATERIALIZE_PINNED_DSH_RUNTIME_FROM_CANONICAL_RESOLVED_INPUTS_NON_LIVE",
    "REPAIR_RUNTIME_AND_ACTION_TIME_CONTRACT_SELECTION_IF_REQUIRED_BY_RECONCILIATION",
    "MAKE_DIRECTLY_REQUIRED_PROJECT_CONTEXT_PROJECTION_CHANGES",
    "MAKE_DIRECTLY_REQUIRED_CI_CHANGES_TO_DISTINGUISH_CANDIDATE_HEAD_SYNTHETIC_PR_MERGE_RESULT_CANONICAL_MASTER",
    "ADD_DEPENDENCY_CLOSURE_UNAFFECTED_NODE_AND_ACTION_TIME_PARITY_TESTS",
    "RUN_COMPLETE_PRODUCTION_EQUIVALENT_NON_SECRET_PREFLIGHT",
    "PERFORM_EXACTLY_ONE_INDEPENDENT_HOSTILE_SECURITY_REVIEW",
    "REPAIR_CRITICAL_OR_HIGH_ONLY",
    "PERFORM_AT_MOST_ONE_TARGETED_REREVIEW_IF_SUCH_REPAIR_OCCURRED",
    "CREATE_ONE_CANDIDATE_COMMIT_AND_ONE_DRAFT_IMPLEMENTATION_PR",
]


def test_no_future_repair_stop_condition_forbids_authorized_execution_contract_implementation() -> None:
    """DEFECT 1: the repaired authorization must not prohibit the implementation it authorizes."""
    stops = AUTH["stop_conditions"]
    assert "STOP_IF_REPAIRATION_WOULD_TOUCH_RUNTIME_OR_CONTRACT_IMPLEMENTATION" not in stops
    assert "STOP_IF_SCOPE_WIDENS_BEYOND_AUTHORIZED_EXECUTION_CONTRACT_RECONCILIATION" in stops
    assert "STOP_IF_HISTORICAL_ARTIFACT_OR_LIVE_BOUNDARY_WOULD_BE_MUTATED" in stops
    # The future repair is explicitly permitted to modify the execution-contract
    # implementation and directly related production preparation/verification
    # machinery, so no stop condition may name that as a forbidden touch.
    allowed = AUTH["future_repair_scope"]["allowed_operations"]
    assert "REPAIR_RUNTIME_AND_ACTION_TIME_CONTRACT_SELECTION_IF_REQUIRED_BY_RECONCILIATION" in allowed
    assert "REWIRE_PREPARE_PRODUCTION_LAUNCH_AND_DIRECTLY_RELATED_PRODUCTION_CONTRACT_SELECTION_TO_CURRENT_CONTRACT_ROOT" in allowed


def test_required_class_level_allowed_operations_are_explicitly_represented() -> None:
    """DEFECT 2: the 25-item class-level reconciliation scope is explicit, not digest-only."""
    allowed = AUTH["future_repair_scope"]["allowed_operations"]
    assert len(allowed) == 25
    for op in REQUIRED_ALLOWED_OPERATIONS:
        assert op in allowed, f"missing required allowed operation: {op}"


def test_runtime_verification_rematerialization_is_non_live_bounded_support() -> None:
    """Runtime verify/rematerialize is allowed only as NON-LIVE bounded support for reconciliation."""
    allowed = AUTH["future_repair_scope"]["allowed_operations"]
    assert "DETERMINISTICALLY_VERIFY_OR_REMATERIALIZE_PINNED_DSH_RUNTIME_FROM_CANONICAL_RESOLVED_INPUTS_NON_LIVE" in allowed
    # The operation name itself carries the NON_LIVE bound; no live authority is granted.
    assert AUTH["forbidden_authority"]["live_dsh_authorized"] is False
    assert AUTH["forbidden_authority"]["model_execution_authorized"] is False
    assert AUTH["forbidden_authority"]["codex_authorized"] is False
    assert AUTH["forbidden_authority"]["claude_authorized"] is False
    assert AUTH["live_boundary_counters"]["live_dsh_invocations"] == 0


def test_production_contract_selection_rewiring_is_authorized() -> None:
    """The future repair may rewire production contract selection to the CURRENT contract root."""
    allowed = AUTH["future_repair_scope"]["allowed_operations"]
    assert "REWIRE_PREPARE_PRODUCTION_LAUNCH_AND_DIRECTLY_RELATED_PRODUCTION_CONTRACT_SELECTION_TO_CURRENT_CONTRACT_ROOT" in allowed
    assert "REWIRE_COMPOSITE_AND_IMMEDIATE_PRE_SPAWN_VERIFICATION_TO_CURRENT_CONTRACT_ROOT" in allowed
    assert "REMOVE_STALE_HISTORICAL_CONTRACT_PATHS_FROM_CURRENT_PRODUCTION_TRUTH" in allowed


def test_claim_ownership_and_source_binding_reconciliation_is_authorized() -> None:
    """Claim ownership/source-binding reconciliation is authorized as part of the class-level repair."""
    allowed = AUTH["future_repair_scope"]["allowed_operations"]
    assert "ESTABLISH_EXACTLY_ONE_EPISODECLAIM_ACQUISITION_OWNER" in allowed
    assert "BIND_CLAIM_SOURCE_TO_EXACT_IMMUTABLE_COMMIT_SHA_WITH_SEPARATE_CANONICALITY_AND_REVOCATION_CHECKS" in allowed
    assert "VERIFY_CLEAN_SOURCE_AND_WORKTREE_SEMANTICS_BEFORE_IRREVERSIBLE_CLAIM_BOUNDARY" in allowed
    assert "ENSURE_PROVIDER_IO_CANNOT_PRECEDE_CLAIM_COMMITTED" in allowed


def test_historical_evidence_mutation_remains_forbidden() -> None:
    """Historical a392/50bd and V0R5/V0R6 evidence remains immutable."""
    allowed = AUTH["future_repair_scope"]["allowed_operations"]
    assert "PRESERVE_HISTORICAL_A392_50BD_AND_V0R5_V0R6_EVIDENCE_IMMUTABLE" in allowed
    protected = AUTH["protected_historical_v0r6"]
    assert protected["remote_claim_ref_mutation_allowed"] is False
    assert protected["local_state_mutation_allowed"] is False
    assert protected["replay_allowed"] is False
    assert protected["second_episode_allowed"] is False
    assert AUTH["future_repair_scope"]["v0r5_replay_allowed"] is False
    assert AUTH["future_repair_scope"]["v0r6_replay_allowed"] is False


def test_live_boundary_remains_zero_and_forbidden() -> None:
    """The live boundary remains zero/forbidden; no live authority is granted."""
    assert AUTH["live_boundary_counters"] == {
        "real_secret_reads": 0,
        "production_claims": 0,
        "provider_calls": 0,
        "live_dsh_invocations": 0,
        "real_codex_turns": 0,
        "real_claude_turns": 0,
        "spend_usd": "0",
    }
    assert AUTH["forbidden_authority"]["secret_read_authorized"] is False
    assert AUTH["forbidden_authority"]["provider_io_authorized"] is False
    assert AUTH["forbidden_authority"]["live_dsh_authorized"] is False
    assert AUTH["forbidden_authority"]["v0r7_authorized"] is False
    assert AUTH["authority_firewall"]["effective_repair_authority"] is False
    assert AUTH["authority_firewall"]["authorization_effective_before_canonical_merge"] is False


def test_candidate_branch_identity_matches_actual_pr_branch_semantics() -> None:
    """DEFECT 3: the artifact records the actual PR #216 head branch, not a false name."""
    recorded = AUTH["canonicalization"]["candidate_branch"]
    assert recorded == "agent/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r6-closure-task9"
    # The exact commit SHA and canonical base remain authoritative over branch naming.
    assert AUTH["canonicalization"]["candidate_base_sha"] == CANONICAL_MASTER
    assert AUTH["canonical_source_identity"]["canonical_master"] == CANONICAL_MASTER


def test_one_candidate_commit_and_one_draft_pr_are_closure_not_ambiguous_premature_stop() -> None:
    """Closure permits one candidate commit AND one draft PR, not an ambiguous commit-OR-PR stop."""
    stops = AUTH["stop_conditions"]
    assert "STOP_AFTER_ONE_CANDIDATE_COMMIT_AND_DRAFT_PR" in stops
    assert "STOP_AFTER_ONE_CANDIDATE_COMMIT_OR_DRAFT_PR" not in stops
    assert AUTH["successor_binding"]["future_repair_terminal_stop"] == "STOP_AFTER_ONE_CANDIDATE_COMMIT_AND_DRAFT_PR"
    allowed = AUTH["future_repair_scope"]["allowed_operations"]
    assert "CREATE_ONE_CANDIDATE_COMMIT_AND_ONE_DRAFT_IMPLEMENTATION_PR" in allowed