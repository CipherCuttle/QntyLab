import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_sandbox_policy_ownership_forensics_authorization_v0"
PREDECESSOR = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_permission_policy_canary_controller_gate_repair_and_continuation_v0"


def load_auth():
    return json.loads((ARTIFACT / "authorization.json").read_text(encoding="utf-8"))


def test_exact_predecessor_binding_and_consumption():
    auth = load_auth()
    predecessor = auth["predecessor"]
    assert predecessor["pr"] == 156
    assert predecessor["merge_sha"] == "55a076f3be0ebbb99225b4f5b64b29e7a16e40ad"
    assert predecessor["classification"] == "DIFFERENT_FAILURE"
    assert predecessor["consumed"] is True
    assert predecessor["product_invocations"] == 1
    assert predecessor["retries"] == 0
    assert auth["first_exposure"]["predecessor_b_exposures"] == 1
    assert auth["first_exposure"]["predecessor_b_consumed"] == 1
    assert auth["first_exposure"]["predecessor_b_retries"] == 0
    assert auth["first_exposure"]["c_is_not_a_b_retry"] is True


def test_predecessor_evidence_and_jsonrpc_uncertainty_are_preserved():
    predecessor = load_auth()["predecessor"]
    assert predecessor["expected_write_occurred"] is False
    assert predecessor["fixture_before_sha256"] == predecessor["fixture_after_sha256"]
    assert predecessor["changed_paths"] == []
    assert predecessor["unauthorized_writes"] == []
    assert predecessor["write_attempt_observed"] is True
    assert predecessor["workspace_read_only_observed"] is True
    assert predecessor["approval_request_observed"] is False
    assert predecessor["sandbox_denial_observed"] is False
    assert predecessor["timeout"] is False
    assert predecessor["child_exit"] == 0
    assert predecessor["jsonrpc_32600"] == {
        "source_stage": "UNKNOWN",
        "fatal": "UNKNOWN",
        "precedes_read_only_message": "UNKNOWN",
        "causally_explains_no_write": "NOT_PROVEN",
        "reason": "canonical receipt retained only the aggregate code and not the originating event",
    }


def test_pins_and_b_treatment_are_exact():
    auth = load_auth()
    identity = auth["frozen_product_identity"]
    assert identity["dsh_repository"] == "deepseek-ai/deepseek-harness"
    assert identity["dsh_commit"] == "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
    assert identity["dsh_tree"] == "3bc8f89fe494a4755c188be354add4e8b1e7b188"
    assert identity["dsh_tag"] == "dsh-v0.1.0-rc.7"
    assert identity["codex_version"] == "codex-cli 0.147.0"
    b = auth["frozen_b_treatment"]
    assert b["request_delta_count_from_historical_a"] == 1
    assert b["request_delta"] == [{
        "method": "thread/start",
        "path": "params.approvalPolicy",
        "before": "<ABSENT>",
        "after": "never",
    }]
    assert b["prompt_task_unchanged"] is True


def test_b_to_c_is_exactly_one_sandbox_delta():
    c = load_auth()["authorized_b_to_c_intervention"]
    assert c["request_delta_count_from_b"] == 1
    assert c["request_delta"] == [{
        "method": "thread/start",
        "path": "params.sandbox",
        "before": "<ABSENT>",
        "after": "workspace-write",
    }]
    assert c["thread_start_sandbox_field"] == "sandbox"
    assert c["thread_start_sandbox_value"] == "workspace-write"
    assert c["turn_start_sandbox_policy_authorized"] is False
    assert c["treatment_variable_stacking_beyond_c"] is False
    assert len(c["c_total_known_deltas_from_historical_a"]) == 2


def test_d3_comparison_justifies_sandbox_hypothesis():
    basis = load_auth()["forensic_basis"]
    assert basis["known_good_d3_sandbox_explicit"] is True
    assert basis["known_good_d3_thread_start_sandbox"] == "workspace-write"
    assert basis["known_good_d3_effective_sandbox_class"] == "workspaceWrite"
    assert basis["b_sandbox_explicit"] is False
    assert basis["b_read_only_observed"] is True
    assert basis["sandbox_ownership_next_hypothesis_justified"] is True


def test_exposure_marker_and_governance_ceiling():
    auth = load_auth()
    boundary = auth["first_exposure"]["consumption_marker"]
    assert boundary["independent_from_b"] is True
    assert boundary["write_immediately_before_product_invocation"] is True
    assert boundary["irrevocable"] is True
    assert boundary["crash_after_write_means_consumed"] is True
    assert boundary["no_retry_after_write"] is True
    ceiling = auth["governance_ceiling"]
    assert all(value is False for key, value in ceiling.items() if isinstance(value, bool))
    assert ceiling["scientific"] == "NONE"
    assert ceiling["qnty_runtime"] == "NONE"
    assert ceiling["trading"] == "NONE"
    assert ceiling["capital"] == "NONE"
    assert auth["frozen_product_identity"]["api_keys_authorized"] is False
    assert auth["frozen_product_identity"]["pay_per_token_authorized"] is False


def test_authorization_is_canonical_merge_gated_and_no_marker_is_mutated():
    auth = load_auth()
    assert auth["authorization_effective"] == "AFTER_CANONICAL_MERGE_ONLY"
    assert auth["phase_state"] == "CLOSED_PASS"
    assert auth["active_project_after_closure"] == "NONE"
    assert (PREDECESSOR / "live_canary_consumed.marker").is_file()
