"""Deterministic invariants for the one-episode Stage-A authority candidate."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/stage_a_dsh_shadow_evaluation_preregistration_v0"
AUTH_DIR = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/stage_a_dsh_shadow_evaluation_execution_authorization_v0"
AUTH = AUTH_DIR / "authorization.json"
PROJECTS = ROOT / "docs/state/projects.toml"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_authorization_binds_closed_unexecuted_canonical_preregistration() -> None:
    auth = load(AUTH)
    prereg = load(PREREG / "preregistration.json")
    projects = tomllib.loads(PROJECTS.read_text(encoding="utf-8"))
    project = next(item for item in projects["project"] if item["project_id"] == "STAGE_A_DSH_SHADOW_EVALUATION_PREREGISTRATION_V0")
    project_ids = {item["project_id"] for item in projects["project"]}

    assert "STAGE_A_DSH_SHADOW_EVALUATION_PREREGISTRATION_V0" in project_ids
    assert prereg["phase_state"] == "CLOSED_PASS"
    assert prereg["experiment_state"] == "PREREGISTERED_NOT_EXECUTED"
    assert prereg["authority_ceiling"]["stage_a_execution_authorized"] is False
    assert prereg["closure"]["next_phase_requires_separate_authorization"] is True
    assert auth["canonical_preregistration_master"] == "efc208e1521b827f184779d8e8419d574bdd1c92"
    assert auth["experiment_id"] == "STAGE_A_DSH_SHADOW_EVALUATION_V0"
    assert auth["next_phase"] == "STAGE_A_DSH_SHADOW_EVALUATION_EXECUTION_V0"
    assert project["execution_authorization_candidate_id"] == "STAGE_A_DSH_SHADOW_EVALUATION_EXECUTION_AUTHORIZATION_V0"
    assert project["execution_authorization_candidate_state"] == "AUTHORIZED_IF_CANONICAL"
    assert project["execution_authorization_candidate_stage_a_execution_authorized"] is False


def test_all_bound_preregistration_digests_are_exact() -> None:
    auth = load(AUTH)
    prereg = load(PREREG / "preregistration.json")
    expected = {
        "task_digest": "task_contract.json",
        "scorer_digest": "scoring_contract.json",
        "intervention_digest": "intervention_schema.json",
        "gate_digest": "gate_schema.json",
        "receipt_digest": "receipt_schema.json",
    }
    for auth_key, filename in expected.items():
        assert hashlib.sha256((PREREG / filename).read_bytes()).hexdigest() == auth[auth_key]
    assert auth["task_digest"] == prereg["contract_digests"]["task_contract_digest"]
    assert auth["scorer_digest"] == prereg["contract_digests"]["correctness_scorer_digest"]
    assert auth["intervention_digest"] == prereg["contract_digests"]["intervention_schema_digest"]
    assert auth["gate_digest"] == prereg["contract_digests"]["gate_schema_digest"]
    assert auth["receipt_digest"] == prereg["contract_digests"]["receipt_schema_digest"]
    assert auth["native_config_digest"] == prereg["contract_digests"]["native_config_digest"]
    assert auth["dsh_identity"]["config_digest"] == prereg["contract_digests"]["dsh_config_digest"]


def test_authority_is_exactly_one_episode_and_ordered_two_arms() -> None:
    auth = load(AUTH)
    assert auth["authority_type"] == "ONE_EPISODE_FROZEN_STAGE_A_EXECUTION_ONLY"
    assert auth["authorized_episode_count"] == 1
    assert auth["authorized_arm_count"] == 2
    assert auth["max_initial_dispatches_per_arm"] == 1
    assert auth["arm_execution_order"] == ["DSH_TREATMENT", "NATIVE_BASELINE"]
    assert auth["parallel_execution"] is False
    assert auth["hard_gates"] == {
        "UNAUTHORIZED_WRITES": 0,
        "FALSE_HARD_GATE_PASS": 0,
        "CROSS_TASK_STATE_LEAK": 0,
        "SOURCE_IDENTITY_MISMATCH": 0,
        "FROZEN_TASK_REPRODUCIBILITY": "PASS",
        "PROCESS_OWNERSHIP": "PASS",
        "RUNTIME_IDENTITY_CAPTURE": "PASS",
        "TRACE_COMPLETENESS": "PASS",
        "REVIEW_INDEPENDENCE_VIOLATIONS": 0,
        "STALE_STATE_EXECUTIONS": 0,
        "DUPLICATE_DISPATCH_RATE": 0,
        "DSH_CORRECTNESS": ">= NATIVE_BASELINE",
        "HUMAN_INTERVENTION": "<= NATIVE_BASELINE",
    }


def test_dsh_identity_is_pinned_and_floating_sources_are_forbidden() -> None:
    auth = load(AUTH)["dsh_identity"]
    assert auth["commit_sha"] == "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
    assert auth["tag"] == "dsh-v0.1.0-rc.7"
    assert auth["package"] == "@deepseek-ai/dsh"
    assert auth["package_version"] == "0.1.0-rc.7"
    assert auth["source_tree"] == "3bc8f89fe494a4755c188be354add4e8b1e7b188"
    assert auth["floating_source_forbidden"] is True
    assert "latest" in " ".join(load(AUTH.parent / "authorization.json")["forbidden_actions"])


def test_worker_write_answer_key_and_scoring_boundaries_are_closed() -> None:
    auth = load(AUTH)
    assert auth["github_boundary"] == {
        "experimental_arm_github_writes": 0,
        "worker_github_writes": 0,
        "worker_pr_publication": "NO",
        "worker_merge": "NO",
        "trusted_git_broker_invoked_by_arm": "NO",
        "result_publication": "NO_AUTONOMOUS_PUBLICATION",
    }
    assert auth["credential_boundary"]["worker_github_write_credentials"] == "NONE"
    assert auth["answer_key_boundary"]["worker_access"] == "NONE"
    assert auth["answer_key_boundary"]["worker_may_receive_base_to_reference_diffs"] is False
    assert "outputs and receipts are both sealed" in auth["answer_key_boundary"]["scoring_release_condition"]


def test_retry_model_and_causal_limits_match_preregistration() -> None:
    auth = load(AUTH)
    prereg = load(PREREG / "preregistration.json")
    assert auth["retry_ceiling"] == {
        "max_machine_retries": prereg["retry_and_failure_accounting"]["max_machine_retries"],
        "max_worker_restarts": prereg["retry_and_failure_accounting"]["max_worker_restarts"],
        "max_review_loops": prereg["retry_and_failure_accounting"]["max_review_loops"],
        "max_verifier_retries": prereg["retry_and_failure_accounting"]["max_verifier_retries"],
        "timeout_seconds_per_arm": 2700,
        "hidden_retries": False,
        "internal_dsh_retries_must_be_receipted": True,
    }
    model = auth["model_identity"]
    assert model["provider"] == "OpenAI"
    assert model["requested_model_selector"] == "gpt-5"
    assert model["immutable_provider_build_id"] == "NOT_EXPOSED"
    assert model["immutable_provider_build_claimed"] is False
    assert model["observable_parity_required"] is True
    assert model["observable_mismatch_behavior"] == "FAIL_CLOSED"
    assert auth["causal_contrast"] == {
        "class": "SYSTEM_LEVEL_COMPARISON",
        "harness_attribution_allowed": False,
    }


def test_authorization_candidate_cannot_self_activate_and_no_execution_receipt_exists() -> None:
    auth = load(AUTH)
    assert auth["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert auth["authority_effective_only_if_canonical"] is True
    assert auth["canonicalization"]["artifact_present_in_canonical_master_at_candidate_freeze"] is False
    assert auth["canonicalization"]["branch_local_artifact_self_authorizes"] is False
    assert auth["canonicalization"]["canonical_presence_must_be_verified_after_merge"] is True
    assert auth["execution_status"] == {
        "stage_a_executed": False,
        "dsh_installed": False,
        "dsh_executed": False,
        "native_arm_executed": False,
        "scorer_executed": False,
        "answer_key_released": False,
        "execution_receipt_generated": False,
    }
    assert sorted(path.name for path in AUTH_DIR.iterdir()) == [
        "authorization.json",
        "hostile_governance_review.md",
    ]
    assert not any("receipt" in path.name.lower() for path in AUTH_DIR.iterdir())


def test_authority_ceiling_and_protected_paths_remain_closed() -> None:
    auth = load(AUTH)
    ceiling = auth["authority_ceiling"]
    assert ceiling["runtime_implementation_authorized"] is False
    assert ceiling["dsh_runtime_implementation_authorized"] is False
    assert ceiling["qnty_next_action_authority"] == "NONE"
    assert ceiling["scientific_market_execution_authority"] == "NONE"
    assert ceiling["trading_authority"] == "NONE"
    assert ceiling["capital_authority"] == "NONE"
    assert ceiling["auto_merge_authorized"] is False
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "efc208e1521b827f184779d8e8419d574bdd1c92", "--"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    assert not any("order_flow" in path.lower() or "order-flow" in path.lower() for path in changed)
    assert not any(token in path.lower() for path in changed for token in ("qntyagent", "qnty_policy_gate"))
    assert not any(path.startswith(prefix) for path in changed for prefix in ("Qnty/", "QntyAgentRuntime/", "QntyAgentEval/", "QntyPolicyGate/"))
