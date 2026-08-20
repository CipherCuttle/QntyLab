import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_clean_c_replication_authorization_v0"


def load_auth():
    return json.loads((ARTIFACT / "authorization.json").read_text(encoding="utf-8"))


def _clean_confirmation_allowed(receipt):
    return all([
        receipt["product_invocation_count"] == 1,
        receipt["dsh_identity_exact"] is True,
        receipt["codex_identity_exact"] is True,
        receipt["prompt_identity_exact"] is True,
        receipt["c_to_d_product_request_delta_count"] == 0,
        receipt["approval_policy"] == "never",
        receipt["sandbox"] == "workspace-write",
        receipt["effective_sandbox"] in ("workspaceWrite", "NOT_OBSERVABLE"),
        receipt["turn_started"] is True,
        receipt["terminal_completed"] is True,
        receipt["timeout"] is False,
        receipt["expected_fixture_write"] is True,
        receipt["changed_paths"] == ["fixture.txt"],
        receipt["unauthorized_writes"] == [],
        receipt["read_only_message"] is False,
        receipt["sandbox_denial"] is False,
        receipt["approval_request"] is False,
        receipt["profile_hash_before"] == receipt["profile_hash_after"],
    ])


def _sample_receipt(**overrides):
    receipt = {
        "product_invocation_count": 1,
        "dsh_identity_exact": True,
        "codex_identity_exact": True,
        "prompt_identity_exact": True,
        "c_to_d_product_request_delta_count": 0,
        "approval_policy": "never",
        "sandbox": "workspace-write",
        "effective_sandbox": "workspaceWrite",
        "turn_started": True,
        "terminal_completed": True,
        "timeout": False,
        "expected_fixture_write": True,
        "changed_paths": ["fixture.txt"],
        "unauthorized_writes": [],
        "read_only_message": False,
        "sandbox_denial": False,
        "approval_request": False,
        "profile_hash_before": "same",
        "profile_hash_after": "same",
    }
    receipt.update(overrides)
    return receipt


def test_exact_governing_pr160_binding_and_immutable_pr158_result():
    auth = load_auth()
    assert auth["canonical_merge_gate"]["required_origin_master"] == "74b6bae8fcf7f08af7b1c7ecdd740925a0eef5c5"
    assert auth["canonical_merge_gate"]["canonical_verified_at_authorization"] is True
    assert auth["canonical_merge_gate"]["effective_only_when_ancestor_of_canonical_master"] is True
    assert auth["governing_predecessor_forensics"]["pr"] == 160
    assert auth["governing_predecessor_forensics"]["merge_sha"] == "74b6bae8fcf7f08af7b1c7ecdd740925a0eef5c5"
    assert auth["governing_predecessor_forensics"]["classification"] == "PARTIAL_CONFOUNDER"
    assert auth["c_predecessor"]["pr"] == 158
    assert auth["c_predecessor"]["merge_sha"] == "89952634622f2480eebb8f695360379272bd01ea"
    assert auth["c_predecessor"]["classification"] == "INCONCLUSIVE_INFRA"
    assert auth["c_predecessor"]["classification_immutable"] is True
    assert auth["governance_boundary"]["historical_reclassification_authorized"] is False


def test_c_is_consumed_and_write_success_is_frozen():
    c = load_auth()["c_predecessor"]
    assert c["consumed"] is True
    assert c["product_invocations"] == 1
    assert c["retries"] == 0
    assert c["write_success"] is True
    assert c["changed_paths"] == ["fixture.txt"]
    assert c["unauthorized_writes"] == []


def test_frozen_identities_prompt_and_c_treatment_are_exact():
    auth = load_auth()
    identities = auth["frozen_product_identities"]
    assert identities["dsh"] == {
        "repository": "deepseek-ai/deepseek-harness",
        "commit": "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca",
        "tree": "3bc8f89fe494a4755c188be354add4e8b1e7b188",
        "tag": "dsh-v0.1.0-rc.7",
    }
    assert identities["codex"]["version"] == "0.147.0"
    assert identities["codex"]["binary_sha256"] == "cb0a15567e9a60a5820d54b0f6ae86d504dc3805c1eab21a47f70e3eb7b73a40"
    assert identities["prompt_sha256"] == "5998d2259d56942c071536866262fa7a7b72c1780ae41137b8e0de1aafef8683"
    assert auth["frozen_c_request"]["product_semantics"]["approvalPolicy"] == "never"
    assert auth["frozen_c_request"]["product_semantics"]["sandbox"] == "workspace-write"


def test_c_to_d_delta_is_zero_and_load_bearing():
    d = load_auth()["frozen_d_request"]
    assert d["c_to_d_product_request_delta_count"] == 0
    assert d["delta_count_is_load_bearing"] is True
    assert d["any_nonzero_delta"] == "PRELIVE_BLOCKED"


def test_one_exposure_zero_retries_and_irrevocable_consumption():
    budget = load_auth()["later_live_budget"]
    assert budget["d_live_exposures_authorized"] == 1
    assert budget["d_retries_authorized"] == 0
    marker = budget["consumed_marker"]
    assert marker["independent"] is True
    assert marker["irrevocable"] is True
    assert set(marker["outcomes_that_consume"]) == {"SUCCESS", "FAILURE", "TIMEOUT", "CRASH", "INFRASTRUCTURE_FAILURE"}
    assert marker["retry_after_marker"] is False


def test_authorization_phase_has_zero_live_authority_and_no_mutation():
    boundary = load_auth()["governance_boundary"]
    assert boundary["authorization_phase_live_product_invocations"] == 0
    assert boundary["authorization_phase_dsh_invocations"] == 0
    assert boundary["authorization_phase_codex_invocations"] == 0
    assert boundary["authorization_phase_canaries"] == 0
    assert boundary["profile_a_mutation_authorized"] is False
    assert boundary["treatment_mutation_authorized"] is False
    assert boundary["profile_restoration_authorized"] is False
    assert boundary["codex_home_mutation_authorized"] is False


def test_profile_baseline_hash_is_exact_and_must_gate_prelive():
    baseline = load_auth()["authorization_profile_baseline"]
    assert baseline["authorization_profile_hash"] == "cb07d9468bb9f7e21b3cc507b20f31a6bffbc8328ef5b250bd7f9a12141ab6c7"
    assert baseline["expected_profile_hash_from_pr160"] == baseline["authorization_profile_hash"]
    assert baseline["profile_baseline_match"] is True
    assert baseline["raw_content_recorded"] is False
    assert load_auth()["later_prelive_gates"]["profile_hash_prelive_must_equal_authorization_hash"] is True


def test_authorization_phase_profile_immutability_proof_is_stable():
    proof = load_auth()["authorization_phase_profile_immutability"]
    assert proof["profile_hash_start"] == proof["profile_hash_end_observed_before_commit"]
    assert proof["profile_mutated_by_authorization_phase"] is False
    assert proof["equality_required"] is True


def test_raw_snapshots_are_ephemeral_and_cannot_enter_git_or_model():
    observation = load_auth()["observation_only_delta"]
    assert observation["is_product_treatment"] is False
    assert observation["raw_snapshot_policy"] == "EPHEMERAL_LOCAL_ONLY"
    assert observation["raw_bytes_may_be_printed"] is False
    assert observation["raw_bytes_may_be_committed"] is False
    assert observation["raw_bytes_may_be_serialized"] is False
    assert observation["raw_bytes_may_be_sent_to_model"] is False
    assert observation["remove_ephemeral_copies_after_sanitized_evidence"] is True


def test_secret_values_and_paid_routes_are_prohibited():
    auth = load_auth()
    safety = auth["secret_safety"]
    assert safety["secret_values_recorded"] is False
    assert safety["secret_values_authorized"] is False
    assert safety["api_keys_authorized"] is False
    assert safety["redaction_required_before_serialization"] is True
    boundary = auth["governance_boundary"]
    assert boundary["api_keys_authorized"] is False
    assert boundary["pay_per_token_authorized"] is False
    assert boundary["parent_model_requests"] == 0


def test_clean_pass_requires_positive_stable_profile_and_write_evidence():
    assert _clean_confirmation_allowed(_sample_receipt()) is True
    assert _clean_confirmation_allowed(_sample_receipt(profile_hash_after="changed")) is False
    assert _clean_confirmation_allowed(_sample_receipt(expected_fixture_write=False)) is False
    assert _clean_confirmation_allowed(_sample_receipt(changed_paths=[])) is False


def test_profile_mutation_can_never_be_clean_confirmation():
    rules = load_auth()["frozen_outcome_classes"]
    assert rules["CLEAN_CONFIRMATION_PASS"]["profile_mutation_disqualifies"] is True
    assert rules["PROFILE_MUTATED_RECORDED"]["condition"] == "PROFILE_SHA256_BEFORE != PROFILE_SHA256_AFTER"
    assert rules["PROFILE_MUTATED_RECORDED"]["required_action"].endswith("NO RETRY")


def test_stable_profile_failed_write_cannot_be_clean_confirmation():
    rules = load_auth()["frozen_outcome_classes"]
    assert "EXPECTED_WRITE = NO" in rules["WRITE_FAILURE_WITH_STABLE_PROFILE"]["condition"]
    assert _clean_confirmation_allowed(_sample_receipt(expected_fixture_write=False)) is False


def test_no_downstream_authority_and_exact_merge_gate():
    auth = load_auth()
    boundary = auth["governance_boundary"]
    assert auth["authorization_effective"] == "AFTER_CANONICAL_MERGE_ONLY"
    assert auth["phase_state"] == "CLOSED_PASS"
    assert boundary["scientific_execution_authorized"] is False
    assert boundary["qnty_runtime_authority"] == "NONE"
    assert boundary["trading_authority"] == "NONE"
    assert boundary["capital_authority"] == "NONE"
    assert boundary["downstream_authority"] == "NONE"
    assert auth["qnty_agent_eval"] == "NO_MATCH"
    assert auth["active_project_after_closure"] == "NONE"


def test_no_alternate_profile_or_treatment_loopholes():
    boundary = load_auth()["governance_boundary"]
    for key in (
        "trust_mutation_authorized",
        "sandbox_mutation_authorized",
        "approval_policy_mutation_authorized",
        "writable_roots_mutation_authorized",
        "runtime_workspace_roots_mutation_authorized",
        "alternate_codex_home_authorized",
        "alternate_profile_authorized",
        "rerun_b_authorized",
        "rerun_c_authorized",
    ):
        assert boundary[key] is False
