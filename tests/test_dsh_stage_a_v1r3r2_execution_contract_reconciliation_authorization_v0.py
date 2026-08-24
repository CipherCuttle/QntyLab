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
    assert record["state"] == "PLANNED_NOT_AUTHORIZED"
    assert record["candidate_state"] == "ACTIVE_CANDIDATE"
    assert record["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert record["authorization_effective"] == "AFTER_EXACT_CANONICAL_MERGE_ONLY"
    assert record["effective_repair_authority"] is False
    assert record["implementation_authorized"] is False
    assert record["canonical_base_sha"] == CANONICAL_MASTER
    assert record["canonical_predecessor_project_id"] == PREDECESSOR_ID
    assert record["canonical_predecessor_required_state"] == "CLOSED_BLOCKED"
    assert record["canonical_predecessor_terminal_outcome"] == PREDECESSOR_OUTCOME
    assert record["future_repair_project_id"] == REPAIR_ID
    assert record["authorization_artifact_sha256"] == (
        "16fb32c8cfe55a87ddd61be21c018dfa44dce907fc7ee95649cdf5922e03d072"
    )

    _, _, registry = project_context.load_context_sources(ROOT)
    validated = project_context.validate_projects_registry(ROOT, registry)
    projection = project_context.execution_authority_projection(ROOT, validated)
    assert projection["issues"] == []
    assert projection["active_project"] is None

    roadmap = (ROOT / "docs/CURRENT_ROADMAP.md").read_text(encoding="utf-8")
    assert "DSH Stage-A V1R3R2 execution contract reconciliation authorization V0" in roadmap
    assert "ACTIVE_CANDIDATE: This authorization is effective only after exact canonical merge." in roadmap
    assert "RUN_V0R7" not in roadmap
    assert "RUN_LIVE_DSH" not in roadmap
    assert "REPLAY_V0R5" not in roadmap
    assert "REPLAY_V0R6" not in roadmap