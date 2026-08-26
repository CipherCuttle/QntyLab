from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_ROOT = (
    ROOT
    / "experiments/research/qnty_agent_orchestration_control_contract_v0"
    / "dsh_stage_a_v1r3r2_production_claim_owner_integration_correction_authorization_v0"
)
AUTH_PATH = PHASE_ROOT / "authorization.json"
AUTHORITY_NOTE_PATH = PHASE_ROOT / "authority_note.md"
AUTH = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
PROJECT_ID = "DSH_STAGE_A_V1R3R2_PRODUCTION_CLAIM_OWNER_INTEGRATION_CORRECTION_AUTHORIZATION_V0"
CANONICAL_MASTER = "07f97f4c645c35bf7a17593ca093e50789c4d620"
PR217_HEAD = "f5e41c2c24009b66ff906e14fbd439a3d9754a48"
PRE_REPAIR_ROOT = "a31eb46"

AUTHORIZED_OPERATIONS = [
    "PROPAGATE_RESOLVED_CLAIM_BINDING_FROM_PRODUCTION_PREPARATION",
    "EXTEND_STAGE_A_LAUNCHER_CLAIM_BINDING_TRANSPORT",
    "EXTEND_CORDIS_PARENT_ENFORCEMENT_CONFIG_BINDING",
    "EXTEND_PARENT_ENFORCEMENT_CONFIG_SCHEMA",
    "EXTEND_GUARD_CLAIM_CLI_ARGUMENT_WIRING",
    "ADD_REAL_PRODUCTION_OWNER_END_TO_END_OFFLINE_TEST",
    "ADD_REAL_PRODUCTION_OWNER_TEST_TO_CI",
    "REPAIR_STALE_CLAIM_SOURCE_DOCUMENTATION",
    "MECHANICALLY_REDERIVE_CURRENT_EXECUTION_CONTRACT_ROOT_AND_DEPENDENTS",
    "AMEND_REPLACE_PR217_SINGLE_CANDIDATE",
    "RUN_ONE_INDEPENDENT_HOSTILE_REVIEW",
    "FIX_CRITICAL_HIGH_ONCE_IF_REQUIRED",
    "RUN_AT_MOST_ONE_TARGETED_REREVIEW_IF_C_H_REPAIR_OCCURRED",
]


def _artifact_sha256() -> str:
    return hashlib.sha256(AUTH_PATH.read_bytes()).hexdigest()


def _project_record() -> dict[str, object]:
    registry = tomllib.loads(
        (ROOT / "docs/state/projects.toml").read_text(encoding="utf-8")
    )
    return next(item for item in registry["project"] if item["project_id"] == PROJECT_ID)


def test_candidate_only_semantics_and_no_self_authorization() -> None:
    """Candidate-only; branch-local artifact does NOT self-authorize."""
    assert AUTH["phase_state"] == "CANDIDATE_GOVERNANCE_ONLY"
    assert AUTH["phase_type"] == "governance_only_bounded_correction_authorization"
    assert AUTH["authority_level"] == "AUTHORIZED_IF_CANONICAL"
    assert AUTH["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert AUTH["authorization_effective"] == "AFTER_EXACT_CANONICAL_MERGE_ONLY"
    firewall = AUTH["authority_firewall"]
    assert firewall["effective_repair_authority"] is False
    assert firewall["authorization_effective_before_canonical_merge"] is False
    assert firewall["implementation_authorized_on_branch"] is False
    assert firewall["branch_local_artifact_does_not_self_authorize"] is True


def test_canonical_base_is_exact() -> None:
    """Canonical base binds exactly 07f97f4c645c35bf7a17593ca093e50789c4d620."""
    identity = AUTH["canonical_source_identity"]
    assert identity["canonical_master"] == CANONICAL_MASTER
    assert identity["canonical_ref"] == "origin/master"
    assert identity["canonical_drift_behavior"] == "STOP_SOURCE_CONFLICT"
    assert identity["git_wins_over_prompt_memory_or_handoff"] is True


def test_pr217_predecessor_head_is_exact() -> None:
    """Blocked predecessor binds exactly PR #217, f5e41c2c24009b66ff906e14fbd439a3d9754a48."""
    prior = AUTH["prior_candidate"]
    assert prior["sha"] == PR217_HEAD
    assert prior["pr_number"] == 217
    assert prior["merged"] is False
    assert prior["pr_state"] == "OPEN"
    assert prior["pr_draft"] is True
    assert prior["terminal_stop"] == "PR217_CORRECTION_BLOCKED"
    assert prior["budget_consumed_action"] == "REPAIR_AND_REREVIEW_BUDGET_EXHAUSTED"
    assert prior["effective_repair_authority_at_prior_candidate"] is False


def test_future_correction_requires_canonical_merge_first() -> None:
    """Future implementation requires canonical merge of THIS authorization first."""
    assert AUTH["next_action"] == "CANONICALIZE_THIS_THEN_BEGIN_ONE_BOUNDED_PRODUCTION_CLAIM_OWNER_INTEGRATION_CORRECTION"
    firewall = AUTH["authority_firewall"]
    assert firewall["effective_repair_authority"] is False
    assert firewall["authorization_effective_before_canonical_merge"] is False


def test_authorized_operations_are_exactly_the_13() -> None:
    """The authorized future operations are exactly the frozen list of 13, in order."""
    allowed = AUTH["authorized_future_scope"]["allowed_operations"]
    assert allowed == AUTHORIZED_OPERATIONS


def test_production_binding_model_is_two_provenance_classes() -> None:
    """No static current root as universal future authority; no static NOT_REVOKED default."""
    binding = AUTH["authorized_future_scope"]["production_binding_model"]
    assert binding["two_provenance_classes"]["A"].startswith("RESOLVED_PRODUCTION_IDENTITY")
    assert "executionContractRoot" in binding["two_provenance_classes"]["A"]
    assert "runtimeIdentityDigest" in binding["two_provenance_classes"]["A"]
    assert "executableIdentityDigest" in binding["two_provenance_classes"]["A"]
    assert binding["two_provenance_classes"]["B"].startswith("FUTURE_LIVE_AUTHORITY_IDENTITY")
    assert "authorizedExecutionSourceSha" in binding["two_provenance_classes"]["B"]
    assert "revocation" in binding["two_provenance_classes"]["B"]
    assert binding["no_static_current_root_as_universal_authority"] is True
    assert binding["no_static_not_revoked_default"] is True
    assert binding["all_values_byte_value_identical_across_transport"] is True
    assert binding["no_layer_may_silently_substitute"] is True


def test_dependency_invalidation_does_not_freeze_pre_repair_root() -> None:
    """a31eb46... is the current pre-repair root only, never the required post-repair root."""
    constraint = AUTH["authorized_future_scope"]["operation_constraints"][
        "MECHANICALLY_REDERIVE_CURRENT_EXECUTION_CONTRACT_ROOT_AND_DEPENDENTS"
    ]
    assert "POST_REPAIR_CURRENT_ROOT" in constraint["semantics"]
    assert "a31eb46" in constraint["semantics"]
    assert "pre-repair root only" in constraint["semantics"]
    assert "Do NOT freeze a31eb46" in constraint["semantics"]


def test_end_to_end_offline_test_is_mandatory() -> None:
    """Positive proof + negative controls through the REAL production owner are mandatory."""
    e2e = AUTH["authorized_future_scope"]["operation_constraints"][
        "ADD_REAL_PRODUCTION_OWNER_END_TO_END_OFFLINE_TEST"
    ]
    semantics = e2e["semantics"]
    assert "actual Python claim invocation" in semantics
    assert "NOT_REVOKED" in semantics
    assert "missing source SHA -> BLOCK" in semantics
    assert "missing execution root -> BLOCK" in semantics
    assert "wrong execution root -> BLOCK" in semantics
    assert "missing revocation proof -> BLOCK" in semantics
    assert "REVOKED -> BLOCK" in semantics
    assert "SUPERSEDED -> BLOCK" in semantics
    assert "wrong runtime identity -> BLOCK" in semantics
    assert "wrong executable identity -> BLOCK" in semantics
    assert "transport substitution" in semantics
    assert "before claim COMMITTED" in semantics


def test_ci_gate_requirement_is_explicit() -> None:
    """The real production-owner test MUST run in GitHub candidate-head CI."""
    ci = AUTH["authorized_future_scope"]["operation_constraints"]["ADD_REAL_PRODUCTION_OWNER_TEST_TO_CI"]
    assert ci["target"] == ".github/workflows/project-context.yml"
    assert "candidate-head CI" in ci["semantics"]
    assert "executable CI regression gate" in ci["semantics"]


def test_authorized_implementation_paths_are_present_and_bounded() -> None:
    """The authorized implementation paths bind the real production claim-owner chain."""
    raw = AUTH_PATH.read_text(encoding="utf-8")
    for path_fragment in (
        "preparation/prepare-production-launch.mjs",
        "launcher/qntylab-launch-dsh.mjs",
        "profile/cordis.patch.yml",
        "profile/qntylab-stage-a-parent-enforcement/lib/index.js",
        "profile/qntylab-stage-a-parent-enforcement/lib/guard.mjs",
        "prelive-enforcement.test.mjs",
        "claim-source-model.md",
        ".github/workflows/project-context.yml",
    ):
        # The exact fragments appear in either the operation constraints or the
        # authority note; assert presence across both canonical governance bytes.
        combined = raw + AUTHORITY_NOTE_PATH.read_text(encoding="utf-8")
        assert path_fragment in combined, path_fragment


def test_forbidden_operations_are_explicit() -> None:
    """Forbidden ops include merge/V0R7/live/secret/claim/provider/Stage B/new PR/hardcode."""
    forbidden = AUTH["authorized_future_scope"]["forbidden_operations"]
    for op in (
        "NO_MERGE",
        "NO_V0R7",
        "NO_LIVE_AUTHORIZATION",
        "NO_SCIENTIFIC_EXECUTION",
        "NO_REAL_SECRET_READ",
        "NO_CLAIM_CREATION",
        "NO_PROVIDER_CALL",
        "NO_REPLAY_V0R5",
        "NO_REPLAY_V0R6",
        "NO_STAGE_B",
        "NO_NEW_IMPLEMENTATION_PR",
        "NO_HARDCODED_FUTURE_MERGE_SHA",
        "NO_ORIGIN_OR_MASTER_IDENTITY_BINDING",
        "NO_UNCONDITIONAL_NOT_REVOKED_DEFAULT",
        "NO_MUTATION_OF_HISTORICAL_ARTIFACTS",
    ):
        assert op in forbidden


def test_live_counters_are_all_zero() -> None:
    """Recorded live counters are zero on read; no live actions in this phase."""
    counters = AUTH["live_firewall"]
    assert counters["real_secret_reads"] == 0
    assert counters["production_claims"] == 0
    assert counters["provider_calls"] == 0
    assert counters["live_dsh_invocations"] == 0
    assert counters["real_codex_turns"] == 0
    assert counters["real_claude_turns"] == 0
    assert counters["spend_usd"] == "0"
    receipts = AUTH["construction_receipts"]
    assert receipts["secret_reads"] == 0
    assert receipts["production_claim_writes"] == 0
    assert receipts["dsh_invocations"] == 0
    assert receipts["provider_requests"] == 0
    assert receipts["v0r7_created"] is False
    assert receipts["spend_usd"] == "0"


def test_historical_firewall_is_byte_identical() -> None:
    """Historical artifacts must remain byte-identical; only deterministic derivation may move current-generation evidence."""
    firewall = AUTH["historical_firewall"]
    assert "historical composite contract.json" in firewall["byte_identical_required"]
    assert "historical composite digests.json" in firewall["byte_identical_required"]
    assert "historical successor_contract.json" in firewall["byte_identical_required"]
    assert "V0R5 evidence" in firewall["byte_identical_required"]
    assert "V0R6 evidence" in firewall["byte_identical_required"]
    assert "prior execution receipts" in firewall["byte_identical_required"]
    assert firewall["current_generation_evidence_changeable_only_by_deterministic_derivation"] is True


def test_registry_projection_matches_authorization_artifact() -> None:
    """Registry projection matches the artifact keys/values."""
    record = _project_record()
    assert record["project_id"] == PROJECT_ID
    assert record["state"] == "CLOSED_PASS"
    assert record["candidate_state"] == "CANONICAL_AUTHORIZATION_EFFECTIVE"
    assert record["canonicalization_status"] == "EXACT_CANONICAL_MERGE_VERIFIED"
    assert record["canonical_authorization_merge"] == "3a0e1aa15c6c5d01a93dd7e3460dd3a736c46474"
    assert record["repair_authority_was_effective"] is True
    assert record["implementation_completed"] is True
    assert record["implementation_project_id"] == "DSH_STAGE_A_V1R3R2_PRODUCTION_CLAIM_OWNER_INTEGRATION_CORRECTION_V0"
    assert record["implementation_project_state"] == "CLOSED_PASS"
    assert record["implementation_candidate_sha"] == "8ee3a671bc9be1d55811e701d0a2b82f3e1d39ee"
    assert record["implementation_canonical_merge"] == "3a0e1aa15c6c5d01a93dd7e3460dd3a736c46474"
    assert record["current_execution_contract_root"] == "cf1aff079d56428753bf8f58f1848839da35cfb9f75104fc1fd03cd13056c1e2"
    assert record["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert record["authorization_effective"] == "AFTER_EXACT_CANONICAL_MERGE_ONLY"
    assert record["effective_repair_authority"] is False
    assert record["implementation_authorized"] is False
    assert record["canonical_base_sha"] == CANONICAL_MASTER
    assert record["canonical_predecessor_pr"] == 217
    assert record["canonical_predecessor_merge"] == PR217_HEAD
    assert record["canonical_predecessor_terminal_outcome"] == "PR217_CORRECTION_BLOCKED"
    assert record["authorization_artifact_sha256"] == _artifact_sha256()


def test_roadmap_projection_includes_the_project() -> None:
    """The generated roadmap (rendered from the registry) includes the project as CLOSED_PASS, not queued."""
    roadmap = (ROOT / "docs/CURRENT_ROADMAP.md").read_text(encoding="utf-8")
    assert PROJECT_ID in roadmap or "production claim-owner integration correction authorization" in roadmap
    assert "CLOSED_PASS" in roadmap
    queued_block = roadmap.split("## Queued — not authorized")[1].split("## Closed / stale")[0]
    assert "production claim-owner integration correction authorization" not in queued_block


def test_authority_note_mirrors_artifact() -> None:
    """The human-readable authority note exists and carries the same core bindings."""
    note = AUTHORITY_NOTE_PATH.read_text(encoding="utf-8")
    assert CANONICAL_MASTER in note
    assert PR217_HEAD in note
    assert "PR217_CORRECTION_BLOCKED" in note
    assert "does **not** self-authorize" in note
    assert "AFTER_EXACT_CANONICAL_MERGE_ONLY" in note


def test_artifact_exists() -> None:
    """The authoritative artifact must exist at the documented path."""
    assert AUTH_PATH.is_file()
    assert AUTHORITY_NOTE_PATH.is_file()
