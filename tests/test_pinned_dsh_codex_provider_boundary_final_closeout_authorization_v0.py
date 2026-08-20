import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_provider_boundary_final_closeout_authorization_v0"


def auth():
    return json.loads((ARTIFACT / "authorization.json").read_text(encoding="utf-8"))


def test_exact_pr162_binding_and_historical_immutability():
    value = auth()
    gate = value["canonical_merge_gate"]
    assert gate["predecessor_pr"] == 162
    assert gate["predecessor_canonical_master"] == "623b60a844f37f63a879f94fbc1ff542a8a4d625"
    assert value["historical_predecessors"]["d"]["merge_sha"] == gate["predecessor_canonical_master"]
    assert value["historical_predecessors"]["c"]["classification"] == "INCONCLUSIVE_INFRA"
    assert value["historical_predecessors"]["d"]["classification"] == "PROFILE_MUTATED_RECORDED"
    assert all(value["historical_predecessors"][key]["immutable"] for key in ("b", "c", "profile_forensics", "d_authorization", "d"))


def test_one_later_phase_contains_forensics_repair_tests_review_and_closure():
    mission = auth()["mission"]
    assert mission["later_project_id"] == "PINNED_DSH_CODEX_PROVIDER_BOUNDARY_FINAL_CLOSEOUT_V0"
    assert all(mission[key] is True for key in (
        "includes_same_phase_read_only_trust_forensics",
        "includes_permanent_provider_boundary_repair",
        "includes_offline_deterministic_tests",
        "includes_one_independent_hostile_review",
        "includes_operational_closure",
        "must_open_one_draft_implementation_closure_pr",
        "must_stop_after_that_pr",
    ))


def test_hard_pr_budget_has_no_follow_on_forensic_or_authorization_pr():
    budget = auth()["hard_pr_budget"]
    assert budget["current_authorization_pr"] == 163
    assert budget["later_implementation_closeout_pr"] == 164
    assert budget["later_implementation_prs_authorized"] == 1
    assert budget["later_separate_forensic_prs_authorized"] == 0
    assert budget["later_additional_authorization_prs_authorized"] == 0
    assert budget["maximum_additional_prs_from_pr162"] == 2
    assert budget["investigation_closes_after_later_pr_merge"] is True


def test_d_request_contract_and_repair_contract_are_exact():
    value = auth()
    contract = value["frozen_successful_contract"]
    assert contract["request_digest_c"] == "26b4f3cadef2d03ed9b0a8f2bc4b30e99bc1a970daca1a26a333dec1eeafd44b"
    assert contract["request_digest_d"] == contract["request_digest_c"]
    assert contract["c_to_d_product_request_delta_count"] == 0
    assert contract["required_thread_start"] == {"approvalPolicy": "never", "sandbox": "workspace-write"}
    assert contract["preserve_thread_start"] == ["cwd", "ephemeral"]
    assert len(contract["repair_relative_delta"]) == 2
    assert contract["no_other_product_semantic_delta"] is True


def test_zero_live_authority_in_both_authorization_and_later_phase():
    boundary = auth()["governance_boundary"]
    assert boundary["authorization_phase_dsh_invocations"] == 0
    assert boundary["authorization_phase_codex_invocations"] == 0
    assert boundary["authorization_phase_live_product_invocations"] == 0
    assert boundary["authorization_phase_canaries"] == 0
    assert boundary["later_live_dsh_invocations"] == 0
    assert boundary["later_live_codex_invocations"] == 0
    assert boundary["later_canaries"] == 0
    assert boundary["later_retries"] == 0


def test_trust_forensics_are_read_only_and_do_not_gate_repair():
    forensic = auth()["later_trust_forensics"]
    assert forensic["authorized"] is True
    assert forensic["read_only"] is True
    assert forensic["must_happen_before_repair"] is True
    assert forensic["must_not_gate_repair"] is True
    assert forensic["repair_proceeds_under_all_q4_outcomes"] is True
    assert forensic["no_dsh_invocation"] is True
    assert forensic["no_codex_invocation"] is True
    assert forensic["no_canary"] is True
    assert set(forensic["allowed_q4_values"]) == {
        "TRUST_DIFFERENTIAL_EXCLUDED",
        "TRUST_IS_LOAD_BEARING_COVARIATE",
        "JOINT_MECHANISM_SUPPORTED",
        "TRUST_TIMING_UNRECOVERABLE",
    }


def test_repair_is_actual_provider_boundary_and_offline_only():
    repair = auth()["later_permanent_repair"]
    assert repair["authorized"] is True
    assert repair["must_target_actual_pinned_dsh_provider_boundary"] is True
    assert repair["test_only_overlay_insufficient"] is True
    assert repair["required_outgoing_thread_start"] == {"approvalPolicy": "never", "sandbox": "workspace-write"}
    assert repair["required_existing_fields_preserved"] == ["cwd", "ephemeral"]
    assert repair["must_fail_closed_if_policy_construction_malformed"] is True
    assert repair["offline_only"] is True


def test_offline_test_requirements_cover_no_extra_semantics_and_no_live_process():
    requirements = auth()["offline_test_requirements"]
    joined = " ".join(requirements)
    for required in (
        "actual provider emits approvalPolicy never",
        "actual provider emits sandbox workspace-write",
        "no new initialize capability or experimental field",
        "no runtimeWorkspaceRoots, writableRoots, or turn/start sandboxPolicy",
        "no live DSH/Codex process spawned",
        "malformed provider policy fails closed",
    ):
        assert required in joined


def test_profile_trust_and_credential_mutations_are_prohibited():
    boundary = auth()["governance_boundary"]
    assert boundary["profile_mutation_authorized"] is False
    assert boundary["trust_mutation_authorized"] is False
    assert boundary["codex_home_mutation_authorized"] is False
    assert boundary["api_keys_authorized"] is False
    assert boundary["pay_per_token_authorized"] is False
    assert boundary["parent_model_requests"] == 0


def test_frozen_identities_and_historical_d_facts_are_preserved():
    value = auth()
    identities = value["frozen_product_identities"]
    assert identities["dsh_commit"] == "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
    assert identities["dsh_tree"] == "3bc8f89fe494a4755c188be354add4e8b1e7b188"
    assert identities["dsh_tag"] == "dsh-v0.1.0-rc.7"
    assert identities["codex_version"] == "codex-cli 0.147.0"
    assert identities["codex_binary_sha256"] == "cb0a15567e9a60a5820d54b0f6ae86d504dc3805c1eab21a47f70e3eb7b73a40"
    assert value["historical_predecessors"]["d"]["write_success"] is True
    assert value["historical_predecessors"]["d"]["changed_paths"] == ["fixture.txt"]
    assert value["historical_predecessors"]["d"]["unauthorized_writes"] == []


def test_final_outcomes_both_close_investigation_and_blocked_does_not_grant_new_pr():
    outcomes = auth()["frozen_final_outcomes"]
    assert set(outcomes) == {"CLOSED_PASS_SANDBOX_STRONGLY_SUPPORTED", "CLOSED_PASS_CONSERVATIVE_REPAIR", "BLOCKED_IMPLEMENTATION"}
    assert outcomes["BLOCKED_IMPLEMENTATION"]["no_automatic_new_pr_authority"] is True
    assert auth()["canonical_merge_gate"]["later_expected_pr"] == 164


def test_no_historical_reclassification_or_downstream_authority():
    value = auth()
    boundary = value["governance_boundary"]
    assert boundary["historical_reclassification_authorized"] is False
    assert boundary["scientific_execution_authorized"] is False
    assert boundary["qnty_runtime_authority"] == "NONE"
    assert boundary["trading_authority"] == "NONE"
    assert boundary["capital_authority"] == "NONE"
    assert boundary["downstream_authority"] == "NONE"
    assert value["active_project_after_closure"] == "NONE"


def test_review_policy_and_evaluator_are_frozen():
    value = auth()
    assert value["qnty_agent_eval"] == "NO_MATCH"
    assert value["review_policy"] == {
        "authorization_hostile_review_count": 1,
        "later_hostile_review_count": 1,
        "targeted_rereview_only_if_critical_or_high_repair": True,
        "medium_low_do_not_restart": True,
    }


def test_authorization_has_no_live_or_mutating_operations_in_its_own_phase():
    boundary = auth()["governance_boundary"]
    assert all(boundary[key] == 0 for key in (
        "authorization_phase_dsh_invocations",
        "authorization_phase_codex_invocations",
        "authorization_phase_live_product_invocations",
        "authorization_phase_canaries",
        "later_live_dsh_invocations",
        "later_live_codex_invocations",
        "later_canaries",
        "later_retries",
    ))
