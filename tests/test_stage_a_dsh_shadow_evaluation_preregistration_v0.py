"""Deterministic Stage-A DSH shadow preregistration invariants."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/stage_a_dsh_shadow_evaluation_preregistration_v0"


def load(name: str) -> dict:
    return json.loads((REG / name).read_text())


def test_canonical_predecessor_and_preregistration_state() -> None:
    prereg = load("preregistration.json")
    assert prereg["bootstrap"]["predecessor_state"] == "CLOSED_PASS"
    assert prereg["bootstrap"]["predecessor_reopen_trigger_present"] is False
    assert prereg["phase_state"] == "CLOSED_PASS"
    assert prereg["experiment_state"] == "PREREGISTERED_NOT_EXECUTED"
    assert prereg["authority_ceiling"]["runtime_implementation_authorized"] is False
    assert prereg["authority_ceiling"]["dsh_runtime_implementation_authorized"] is False
    assert prereg["authority_ceiling"]["stage_a_execution_authorized"] is False


def test_fixture_and_answer_key_firewall_are_exact() -> None:
    fixture = load("preregistration.json")["historical_fixture"]
    assert fixture["agent_visible_base"] == "1b93858857daddacd1795cf980edb3d562eabc77"
    assert fixture["sealed_reviewed_reference"] == "73a0bacd4b244f9b83967612ad92d4eb474bbcc7"
    assert fixture["sealed_post_merge_reference"] == "c5ea1b735172527a98febad9c3165fd2e9a4bf77"
    firewall = fixture["answer_key_firewall"]
    assert firewall["answer_key_visible_to_workers"] is False
    assert firewall["answer_key_visible_to_scorer_post_termination"] is True
    assert firewall["workers_may_receive_base_to_reference_diffs"] is False


def test_dsh_identity_is_immutable_and_non_ambiguous() -> None:
    identity = load("preregistration.json")["dsh_upstream_identity"]
    assert identity["identity_status"] == "RESOLVED"
    assert identity["owner"] == "deepseek-ai"
    assert identity["repository"] == "deepseek-harness"
    assert identity["commit_sha"] == "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
    assert identity["tag_or_release"] == "dsh-v0.1.0-rc.7"
    assert identity["package_name"] == "@deepseek-ai/dsh"
    assert identity["package_version"] == "0.1.0-rc.7"
    assert identity["license"] == "MIT"
    assert len(identity["source_tree_id"]) == 40


def test_task_bytes_and_models_are_shared() -> None:
    prereg = load("preregistration.json")
    task = load("task_contract.json")
    assert prereg["task_contract"]["native_task_digest"] == prereg["task_contract"]["dsh_task_digest"]
    assert len(prereg["task_contract"]["native_task_digest"]) == 64
    assert prereg["task_contract"]["native_task_digest_equals_dsh_task_digest"] is True
    assert prereg["model_identities"]["native_and_dsh_role_model_identity_equal"] is True
    assert prereg["causal_contrast_class"]["classification"] == "SYSTEM_LEVEL_COMPARISON"
    assert prereg["causal_contrast_class"]["harness_attribution_allowed"] is False


def test_scoring_intervention_gates_and_receipt_are_machine_defined() -> None:
    prereg = load("preregistration.json")
    scoring = load("scoring_contract.json")
    intervention = load("intervention_schema.json")
    gates = load("gate_schema.json")
    receipt = load("receipt_schema.json")
    assert len(scoring["required_propositions"]) >= 1
    assert scoring["correctness_comparator"] == {
        "score_definition": "correctness_score = 1 if all required propositions pass and hard_failure_count == 0, else 0",
        "comparison": "DSH_CORRECTNESS >= NATIVE_BASELINE",
        "scoring_weights": "NONE",
        "arm_specific_exceptions": "NONE",
        "immutable_after_dispatch": True,
    }
    assert intervention["ambiguity_rule"] == "FAIL_CLOSED"
    assert intervention["event_types"]
    assert len(gates["gates"]) == 13
    assert {gate["gate_id"] for gate in gates["gates"]} == {
        "UNAUTHORIZED_WRITES", "FALSE_HARD_GATE_PASS", "CROSS_TASK_STATE_LEAK", "SOURCE_IDENTITY_MISMATCH",
        "FROZEN_TASK_REPRODUCIBILITY", "PROCESS_OWNERSHIP", "RUNTIME_IDENTITY_CAPTURE", "TRACE_COMPLETENESS",
        "REVIEW_INDEPENDENCE_VIOLATIONS", "STALE_STATE_EXECUTIONS", "DUPLICATE_DISPATCH_RATE",
        "DSH_CORRECTNESS_GE_NATIVE_BASELINE", "HUMAN_INTERVENTION_LE_NATIVE_BASELINE",
    }
    assert all(gate["measurement_function"] and gate["pass_condition"] and gate["fail_condition"] for gate in gates["gates"])
    assert all(gate["missing_evidence_behavior"] == "FAIL_CLOSED" for gate in gates["gates"])
    assert "task_admission" not in [event.lower() for event in receipt["required_event_classes"]] or "TASK_ADMISSION" in receipt["required_event_classes"]


def test_retry_isolation_and_zero_write_boundary_are_frozen() -> None:
    prereg = load("preregistration.json")
    retry = prereg["retry_and_failure_accounting"]
    assert retry["max_machine_retries"] == 2
    assert retry["max_worker_restarts"] == 1
    assert retry["max_review_loops"] == 1
    assert retry["max_verifier_retries"] == 1
    assert retry["unlimited_hidden_retries"] is False
    assert prereg["isolation"]["cross_arm_state_sharing"] == "NONE"
    boundary = prereg["git_and_github_boundary"]
    assert boundary["stage_a_github_writes"] == 0
    assert boundary["stage_a_github_write_credentials"] == "NONE"
    assert boundary["stage_a_pr_publication"] == "NO"
    assert boundary["stage_a_merge"] == "NO"


def test_tie_policy_cannot_authorize_runtime() -> None:
    prereg = load("preregistration.json")
    tie = prereg["tie_policy"]
    assert "PASS_NO_INCREMENTAL_VALUE" in tie["pass_no_incremental_value"]
    assert "separate" in tie["runtime_escalation"]
    assert prereg["closure"]["next_phase_requires_separate_authorization"] is True


def test_order_flow_and_runtime_paths_are_absent_from_phase_diff() -> None:
    names = subprocess.run(
        ["git", "diff", "--name-only", "a013c5f63c5c70cebef396236de99498d09028d9"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    forbidden_fragments = ("order_flow", "qnty_agent_runtime", "qntyagenteval", "qntypolicygate", "dispatcher", "scheduler", "daemon", "broker")
    assert not [path for path in names if any(fragment in path.lower() for fragment in forbidden_fragments)]
    assert "qntylab/project_context.py" not in names


def test_arm_order_is_hash_derived_and_task_is_not_answer_key_bearing() -> None:
    prereg = load("preregistration.json")
    order = prereg["arm_execution_order"]
    derived = sorted(
        order["derived_digests"],
        key=lambda arm: hashlib.sha256(("STAGE_A_DSH_SHADOW_EVALUATION_V0:" + arm).encode()).hexdigest(),
    )
    assert order["derived_order"] == derived
    task_text = (REG / "task_contract.json").read_text()
    assert "73a0bacd4b244f9b83967612ad92d4eb474bbcc7" not in task_text
    assert "c5ea1b735172527a98febad9c3165fd2e9a4bf77" not in task_text
