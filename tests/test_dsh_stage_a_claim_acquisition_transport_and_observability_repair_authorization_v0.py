from __future__ import annotations

import json
import tomllib
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
PHASE_ROOT = (
    ROOT
    / "experiments/research/qnty_agent_orchestration_control_contract_v0"
    / "dsh_stage_a_claim_acquisition_transport_and_observability_repair_authorization_v0"
)
AUTH = json.loads((PHASE_ROOT / "authorization.json").read_text(encoding="utf-8"))
PROJECT_ID = "DSH_STAGE_A_CLAIM_ACQUISITION_TRANSPORT_AND_OBSERVABILITY_REPAIR_AUTHORIZATION_V0"
REPAIR_ID = "DSH_STAGE_A_CLAIM_ACQUISITION_TRANSPORT_AND_OBSERVABILITY_REPAIR_V0"
CANONICAL_MASTER = "b9cfcb41e1cff199da77f68b347ef912866c2ed1"
PREDECESSOR_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R5"
PREDECESSOR_OUTCOME = "V0R5_LIVE_EPISODE_CLOSED_BLOCK_NEVER_REPLAY"


def _project_record() -> dict[str, object]:
    registry = tomllib.loads(
        (ROOT / "docs/state/projects.toml").read_text(encoding="utf-8")
    )
    return next(item for item in registry["project"] if item["project_id"] == PROJECT_ID)


def test_authorization_is_bound_to_exact_closed_v0r5_predecessor() -> None:
    identity = AUTH["canonical_source_identity"]
    assert identity["canonical_master"] == CANONICAL_MASTER
    assert identity["canonical_merge_parents"] == [
        "8c348e3f559a191ef70cd7afa63d9b5fc2fce819",
        "ec004b17fd23afbab1a72bb38779e8648079eb51",
    ]
    assert identity["predecessor_project_id"] == PREDECESSOR_ID
    assert identity["predecessor_merge"] == CANONICAL_MASTER
    assert identity["predecessor_required_state"] == "CLOSED_BLOCKED"
    assert identity["predecessor_terminal_outcome"] == PREDECESSOR_OUTCOME
    assert AUTH["authorization_effective"] == "AFTER_EXACT_CANONICAL_MERGE_ONLY"
    assert AUTH["successor_binding"]["future_repair_project_id"] == REPAIR_ID
    assert AUTH["successor_binding"]["effective_repair_authority"] is False
    assert AUTH["successor_binding"]["branch_local_candidate_does_not_self_authorize"] is True


def test_future_scope_is_narrow_and_production_claims_are_forbidden() -> None:
    scope = AUTH["future_repair_scope"]
    assert scope["diagnostic_namespace_prefix"] == (
        "refs/heads/qntylab-diagnostics/claim-transport-v0/"
    )
    assert scope["diagnostic_refs_must_be_fresh_and_disposable"] is True
    assert scope["production_claim_namespace_mutation_allowed"] is False
    assert scope["v0r5_replay_allowed"] is False
    assert scope["v0r6_creation_allowed"] is False

    protected = AUTH["protected_historical_v0r5"]
    assert protected["remote_claim_ref_mutation_allowed"] is False
    assert protected["local_state_mutation_allowed"] is False
    assert protected["intent_delete_allowed"] is False
    assert protected["lock_delete_allowed"] is False
    assert protected["receipt_repair_allowed"] is False
    assert protected["replay_allowed"] is False
    assert protected["second_episode_allowed"] is False

    ontology = AUTH["claim_outcome_ontology"]
    assert set(ontology) == {
        "COMMITTED",
        "CONFIRMED_NO_REMOTE_WRITE",
        "WRITE_STATE_UNKNOWN",
    }
    assert ontology["WRITE_STATE_UNKNOWN"]["fail_closed"] is True
    assert ontology["CONFIRMED_NO_REMOTE_WRITE"]["production_retry_granted"] is False


def test_observability_redaction_and_zero_activity_firewall_are_explicit() -> None:
    contract = AUTH["observability_contract"]
    assert contract["operation_stages"] == [
        "PRECHECK",
        "LOCAL_INTENT",
        "REMOTE_WRITE_ATTEMPT",
        "REMOTE_VERIFY",
        "LOCAL_RECEIPT",
    ]
    redaction = contract["credential_redaction"]
    assert redaction["deterministic"] is True
    assert redaction["tested"] is True
    assert all(
        redaction[field] is False
        for field in (
            "retain_passwords",
            "retain_tokens",
            "retain_authorization_headers",
            "retain_credential_helper_contents",
            "retain_secret_environment_values",
            "retain_embedded_credentials_in_urls",
            "dump_full_environment",
            "dump_full_git_config",
        )
    )

    assert AUTH["diagnostic_network_authority"]["authorization_phase_network_writes"] == 0
    assert AUTH["forbidden_authority"]["secret_read_authorized"] is False
    assert AUTH["forbidden_authority"]["provider_io_authorized"] is False
    assert AUTH["forbidden_authority"]["model_execution_authorized"] is False
    assert AUTH["forbidden_authority"]["live_dsh_authorized"] is False
    assert AUTH["construction_receipts"] == {
        "secret_reads": 0,
        "diagnostic_network_writes": 0,
        "production_claim_writes": 0,
        "dsh_invocations": 0,
        "provider_requests": 0,
        "real_model_calls": 0,
        "codex_turns": 0,
        "claude_turns": 0,
        "v0r5_mutations": 0,
        "v0r6_created": False,
        "spend_usd": "0",
    }


def test_registry_and_generated_roadmap_bind_the_completed_repair_transition() -> None:
    record = _project_record()
    assert record["state"] == "CLOSED_PASS"
    assert record["candidate_state"] == "CANONICAL_AUTHORIZATION_EFFECTIVE"
    assert record["implementation_authorized"] is False
    assert record["implementation_completed"] is True
    assert record["canonicalization_status"] == "EXACT_CANONICAL_MERGE_VERIFIED"
    assert record["repair_authority_was_effective"] is True
    assert record["authorization_effective"] == "AFTER_EXACT_CANONICAL_MERGE_ONLY"
    assert record["effective_repair_authority"] is False
    assert record["future_repair_project_id"] == REPAIR_ID
    assert record["canonical_base_sha"] == CANONICAL_MASTER
    assert record["canonical_authorization_merge"] == "36e3085c18a747e3755097c97915f61f289d0835"
    assert record["diagnostic_positive_create"] == "COMMITTED"
    assert record["diagnostic_duplicate_control"] == "NO_OVERWRITE"
    assert record["diagnostic_confirmed_no_write"] == "CONFIRMED_NO_REMOTE_WRITE"
    assert record["diagnostic_unknown_control"] == "WRITE_STATE_UNKNOWN_FAIL_CLOSED"
    assert record["historical_root_cause_status"] == "HISTORICAL_ROOT_CAUSE_UNRESOLVED"
    assert record["hostile_review_count"] == 1
    assert record["hostile_governance_critical_total"] == 0
    assert record["hostile_governance_high_total"] == 0

    _, _, registry = project_context.load_context_sources(ROOT)
    validated = project_context.validate_projects_registry(ROOT, registry)
    projection = project_context.execution_authority_projection(ROOT, validated)
    assert projection["issues"] == []
    assert projection["active_project"] is None

    roadmap = (ROOT / "docs/CURRENT_ROADMAP.md").read_text(encoding="utf-8")
    assert "DSH Stage-A claim acquisition transport and observability repair authorization V0" in roadmap
    assert "CLOSED_PASS: Stop after this one bounded claim transport and observability repair candidate." in roadmap
    assert "Historical V0R5 replay" in roadmap
    assert "RUN_V0R6" not in roadmap
    assert "RUN_LIVE_DSH" not in roadmap
    assert "REPLAY_V0R5" not in roadmap
