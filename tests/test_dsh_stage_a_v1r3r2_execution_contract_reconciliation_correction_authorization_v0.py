from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
PHASE_ROOT = (
    ROOT
    / "experiments/research/qnty_agent_orchestration_control_contract_v0"
    / "dsh_stage_a_v1r3r2_execution_contract_reconciliation_correction_authorization_v0"
)
AUTH_PATH = PHASE_ROOT / "authorization.json"
EVIDENCE_PATH = PHASE_ROOT / "evidence_findings.md"
AUTH = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
PROJECT_ID = "DSH_STAGE_A_V1R3R2_EXECUTION_CONTRACT_RECONCILIATION_CORRECTION_AUTHORIZATION_V0"
CANONICAL_MASTER = "a87ecfda105b84669f3fef862496045284d0a655"
PR217_HEAD = "7fb7a70364727f99cd8f9da49552484e1b1aaea8"
H2_CI_PATH = "/var/tmp/qntylab-dsh-runtime-v0-final/source/apps/cli/lib/bin.js"
H2_WRONG_PATH = "/var/tmp/qntylab-dsh-runtime-v0-final/source/apps/cli/lib/bin0.js"


def _artifact_sha256() -> str:
    return hashlib.sha256(AUTH_PATH.read_bytes()).hexdigest()


def _project_record() -> dict[str, object]:
    registry = tomllib.loads(
        (ROOT / "docs/state/projects.toml").read_text(encoding="utf-8")
    )
    return next(item for item in registry["project"] if item["project_id"] == PROJECT_ID)


def _h2() -> dict[str, object]:
    return next(e for e in AUTH["invalidating_evidence"] if e["id"] == "H2")


def test_candidate_only_semantics_and_no_self_authorization() -> None:
    """1 + 2: candidate-only; branch-local artifact does NOT self-authorize."""
    assert AUTH["phase_state"] == "CANDIDATE_GOVERNANCE_ONLY"
    assert AUTH["phase_type"] == "governance_only_bounded_correction_authorization"
    assert AUTH["authority_level"] == "AUTHORIZED_IF_CANONICAL"
    assert AUTH["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert AUTH["authorization_effective"] == "AFTER_EXACT_CANONICAL_MERGE_ONLY"
    assert AUTH["successor_binding"]["effective_repair_authority"] is False
    assert AUTH["successor_binding"]["branch_local_candidate_does_not_self_authorize"] is True
    assert AUTH["successor_binding"]["future_repair_must_reconcile_canonical_source_again"] is True
    assert AUTH["authority_firewall"]["effective_repair_authority"] is False
    assert AUTH["authority_firewall"]["authorization_effective_before_canonical_merge"] is False


def test_canonical_base_is_exact() -> None:
    """3: canonical base is exactly canonical (full sha verified from git)."""
    identity = AUTH["canonical_source_identity"]
    assert identity["canonical_master"] == CANONICAL_MASTER
    assert identity["canonical_merge_pr"] == "PR #216"
    assert identity["canonical_drift_behavior"] == "STOP_SOURCE_CONFLICT"
    assert identity["git_wins_over_prompt_memory_or_handoff"] is True


def test_pr217_predecessor_head_is_exact() -> None:
    """4: PR #217 predecessor head is exact (no accidental alpha-digit swap)."""
    prior = AUTH["prior_candidate"]
    assert prior["sha"] == PR217_HEAD
    assert prior["pr_number"] == 217
    assert prior["merged"] is False
    assert prior["pr_state"] == "OPEN"
    assert prior["pr_draft"] is True


def test_future_correction_requires_canonical_merge_first() -> None:
    """5: future correction requires canonical merge of THIS authorization first."""
    assert AUTH["successor_binding"]["future_repair_requires_this_authorization_canonical_merge"] is True
    assert AUTH["next_action"] == "CANONICALIZE_THIS_THEN_BEGIN_ONE_BOUNDED_CORRECTION"
    assert AUTH["authority_firewall"]["effective_repair_authority"] is False
    assert AUTH["authority_firewall"]["authorization_effective_before_canonical_merge"] is False


def test_correction_scope_is_exactly_bounded() -> None:
    """6: correction scope is exact (no over-broad repair authority)."""
    allowed = AUTH["authorized_future_scope"]["allowed_operations"]
    assert allowed == [
        "RESTORE_HISTORICAL_CONTRACT_DIGESTS_BYTE_FOR_BYTE",
        "CREATE_CURRENT_GENERATION_EVIDENCE_AT_NEW_PATH",
        "IMPLEMENT_EXACT_COMMIT_CLAIM_SOURCE_SEAM",
        "REPAIR_CI_REPRODUCIBILITY",
        "UPDATE_FOCUSED_TESTS",
        "ONE_INDEPENDENT_TARGETED_HOSTILE_REVIEW",
        "AMEND_REPLACE_PR217_CANDIDATE",
    ]
    seam = AUTH["authorized_future_scope"]["operation_constraints"]["IMPLEMENT_EXACT_COMMIT_CLAIM_SOURCE_SEAM"]
    assert seam["if_then_gated"] is True
    assert seam["no_bytes_for_unknown_future_merge_sha"] is True
    assert seam["no_origin_or_master_identity_binding"] is True


def test_forbidden_operations_are_explicit() -> None:
    """7: forbidden ops include V0R7/V0R5/V0R6 replay/live/secret/claim/provider/Stage B."""
    forbidden = AUTH["authorized_future_scope"]["forbidden_operations"]
    for op in (
        "NO_V0R7",
        "NO_REPLAY_V0R5",
        "NO_REPLAY_V0R6",
        "NO_LIVE_AUTHORIZATION",
        "NO_REAL_SECRET_READ",
        "NO_CLAIM_CREATION",
        "NO_PROVIDER_CALL",
        "NO_SCIENTIFIC_EXECUTION",
        "NO_STAGE_B",
    ):
        assert op in forbidden


def test_live_counters_are_all_zero() -> None:
    """8: recorded live counters are zero on read; no live actions in this phase."""
    counters = AUTH["live_boundary_counters"]
    assert counters["real_secret_reads"] == 0
    assert counters["production_claims"] == 0
    assert counters["provider_calls"] == 0
    assert counters["live_dsh_invocations"] == 0
    assert counters["real_codex_turns"] == 0
    assert counters["real_claude_turns"] == 0
    assert counters["spend_usd"] == "0"


def test_registry_projection_matches_authorization_artifact() -> None:
    """9: registry projection matches the artifact keys/values."""
    record = _project_record()
    assert record["project_id"] == PROJECT_ID
    assert record["state"] == "PLANNED_NOT_AUTHORIZED"
    assert record["candidate_state"] == "ACTIVE_CANDIDATE"
    assert record["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert record["authorization_effective"] == "AFTER_EXACT_CANONICAL_MERGE_ONLY"
    assert record["effective_repair_authority"] is False
    assert record["implementation_authorized"] is False
    assert record["canonical_base_sha"] == CANONICAL_MASTER
    assert record["authorization_artifact_sha256"] == _artifact_sha256()


def test_h2_path_is_exact_and_not_bin0_js() -> None:
    """10: H2 path is exactly .../bin.js and NEVER bin0.js."""
    detail = _h2()["detail"]
    assert H2_CI_PATH in detail
    assert H2_WRONG_PATH not in detail
    raw_auth = AUTH_PATH.read_text(encoding="utf-8")
    raw_evidence = EVIDENCE_PATH.read_text(encoding="utf-8")
    assert H2_CI_PATH in raw_auth
    assert H2_CI_PATH in raw_evidence
    assert H2_WRONG_PATH not in raw_auth
    assert H2_WRONG_PATH not in raw_evidence