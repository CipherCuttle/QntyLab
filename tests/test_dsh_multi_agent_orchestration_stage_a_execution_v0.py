import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_multi_agent_orchestration_stage_a_execution_v0"


def evidence():
    return json.loads((ARTIFACT / "execution_evidence.json").read_text(encoding="utf-8"))


def test_bound_to_canonical_authorization():
    value = evidence()
    auth = value["canonical_authorization"]
    assert auth["pr"] == 165
    assert auth["merge_commit"] == "1924bd4d4e8bd589ffde4887c5f8893c6c95496a"
    assert value["h04_prelive_repair"]["status"] == "COMPLETE"
    assert value["h04_prelive_repair"]["max_retries"] == 0


def test_all_four_offline_gates_passed_before_any_live_call():
    gates = evidence()["offline_gates"]
    for key in ("gate_a_provider_identity", "gate_b_composition_identity", "gate_c_package_resolution", "gate_d_ambient_override_exclusion"):
        assert gates[key].startswith("PASS"), key


def test_secret_handling_claims_are_narrowly_scoped_not_a_global_never_exposed_claim():
    # M-01: a prior version of this artifact claimed the secret was globally
    # "never exposed," which was false -- the user had already pasted the
    # temporary credential into chat before this execution began. The
    # honest, supportable claim is scoped to what Stage-A execution tooling
    # itself did, not a claim about the credential's entire history.
    secret = evidence()["secret_handling"]
    assert secret["preexisting_chat_exposure_acknowledged"] is True
    assert secret["secret_value_exposed_by_stage_a_execution_tooling"] is False
    assert secret["secret_value_committed_or_persisted_in_stage_a_artifacts"] is False
    assert "value_ever_exposed_in_transcript_or_artifact" not in secret


def test_no_literal_secret_value_appears_anywhere_in_serialized_evidence():
    text = json.dumps(evidence())
    assert "sk-" not in text
    closure_text = (ARTIFACT / "closure.md").read_text(encoding="utf-8")
    assert "sk-" not in closure_text


def test_episode_consumed_and_no_second_episode_authorized():
    value = evidence()
    assert value["live_episode"]["episode_consumed"] is True
    assert value["termination"]["episode_number"] == 1
    assert value["termination"]["second_episode_authorized"] is False
    assert value["no_second_episode_authorized"] is True
    assert value["no_stage_b_authorized"] is True


def test_step_and_retry_budgets_held():
    live = evidence()["live_episode"]
    assert live["parent_step_count"] == 8
    assert live["parent_step_count"] <= 8
    assert live["parent_retry_event_count"] == 0
    assert live["parent_retry_started_event_count"] == 0


def test_spend_stayed_far_under_ceiling():
    live = evidence()["live_episode"]
    assert live["parent_estimated_spend_usd"] < live["parent_conservative_max_spend_usd"]
    assert live["parent_conservative_max_spend_usd"] < 1.00


def test_codex_call_budget_was_exceeded_and_is_the_recorded_cause():
    live = evidence()["live_episode"]
    assert live["codex_tool_calls_observed"] == 3
    assert live["claude_tool_calls_observed"] == 0
    value = evidence()
    assert value["termination"]["reason"] == "PARENT_CALL_BUDGET_VIOLATION"


def test_fixture_was_never_mutated():
    live = evidence()["live_episode"]
    files = live["fixture_files_after_termination"]
    assert files["retry.py_matches_frozen_stub"] is True
    assert files["retry.py_sha256"] == "f82a84088b76dd82ead87d5536f8120d62e7c4408c27fcbe59662155b5dd47ae"


def test_kill_trigger_false_positive_is_disclosed_not_hidden():
    value = evidence()
    note = value["termination"]["false_positive_in_original_kill_trigger"]
    assert "subagent_fork" in note
    assert "substring" in note.lower()


def test_terminal_outcome_is_block_parent_infra_and_matches_frozen_taxonomy():
    value = evidence()
    assert value["terminal_outcome"] == "BLOCK_PARENT_INFRA"
    assert value["terminal_outcome"] in {
        "PASS",
        "PASS_AFTER_BOUNDED_REPAIR",
        "FAIL_IMPLEMENTATION",
        "FAIL_REVIEW",
        "BLOCK_CHILD_INFRA",
        "BLOCK_PARENT_INFRA",
        "BLOCK_AUTH",
        "BLOCK_COST",
    }


def test_no_scientific_or_downstream_authority_granted():
    value = evidence()
    assert value["no_stage_b_authorized"] is True
    assert value["no_second_episode_authorized"] is True


def test_workspace_boundary_was_not_violated():
    assert evidence()["live_episode"]["workspace_boundary_violation"] is False


def test_child_credential_isolation_documented_from_pinned_source():
    note = evidence()["secret_handling"]["child_isolation_verified_from_pinned_source"]
    assert "scrubbedParentEnv" in note
    assert "KEY|PASSWORD|SECRET|TOKEN" in note


def test_closure_narrative_exists_and_states_the_same_outcome():
    text = (ARTIFACT / "closure.md").read_text(encoding="utf-8")
    assert "BLOCK_PARENT_INFRA" in text
    assert "No second episode is authorized" in text or "no second episode is authorized" in text.lower()
