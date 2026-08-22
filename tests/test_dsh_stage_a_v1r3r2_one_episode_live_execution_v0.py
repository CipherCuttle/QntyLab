import json
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_one_episode_live_execution_v0"
AUTHORIZATION = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0/authorization.json"
ACTIVATION = json.loads((ARTIFACT / "activation.json").read_text(encoding="utf-8"))
AUTH = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))


def test_activation_requires_canonical_pr_182_and_does_not_self_authorize():
    canonical = ACTIVATION["canonicalization"]
    assert canonical == {
        "candidate_base_sha": "0dbd9ee0dceb9c6dab9781816230b5518c1de490",
        "canonical_predecessor_project_id": "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0",
        "canonical_predecessor_pr": 182,
        "canonical_predecessor_reviewed_head": "cdf5282c4cae4dd219fad1dbe6020db475ad6381",
        "canonical_predecessor_merge": "0dbd9ee0dceb9c6dab9781816230b5518c1de490",
        "required_predecessor_state": "CLOSED_PASS",
        "branch_local_candidate_does_not_self_authorize": True,
        "canonical_presence_required_before_execution": True,
        "no_auto_merge": True,
        "effective_scope": "Exactly one later Stage-A V1R3R2 live episode and exactly one draft execution-closure PR; stop.",
    }
    assert ACTIVATION["phase_state"] == "ACTIVE_CANDIDATE"
    assert ACTIVATION["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert ACTIVATION["authorization_effective"] == "AFTER_CANONICAL_MERGE_ONLY"


def test_exact_v1r3r2_authority_is_bound_and_v1r3r1_is_rejected():
    runtime = ACTIVATION["runtime_identity"]
    assert runtime["qualified_launch_contract_digest"] == AUTH["qualified_launch_contract"]["digest"]
    assert runtime["runtime_manifest_digest"] == AUTH["qualified_launch_contract"]["runtime_manifest_digest"]
    assert runtime["executable_identity_digest"] == AUTH["qualified_launch_contract"]["executable_identity_digest"]
    assert runtime["launch_policy_digest"] == AUTH["qualified_launch_contract"]["launch_policy_digest"]
    assert runtime["codex_repair_digest"] == AUTH["qualified_launch_contract"]["repair_digests"]["codex"]
    assert runtime["claude_repair_digest"] == AUTH["qualified_launch_contract"]["repair_digests"]["claude"]
    assert runtime["superseded_digest_rejected"] == "4cd2734f229a97d4258ace4576f23f76f3d36aeef888a19fa61d2f4a7bff37d4"
    assert runtime["v1r3r1_authority_compatible"] is False
    assert runtime["commit"] == "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
    assert runtime["tree"] == "3bc8f89fe494a4755c188be354add4e8b1e7b188"
    assert runtime["tag"] == "dsh-v0.1.0-rc.7"


def test_post_merge_project_is_one_episode_only_and_activation_consumes_nothing():
    project = ACTIVATION["active_execution_project"]
    assert project["state"] == "ACTIVE"
    assert project["authority_level"] == "BOUNDED_ONE_EPISODE_DSH_STAGE_A_LIVE_EXECUTION_AND_CLOSURE"
    assert project["implementation_authorized"] is True
    assert project["implementation_completed"] is False
    assert project["authorized_live_episodes"] == 1
    assert project["episode_consumed"] is False
    assert project["second_episode_authorized"] is False
    assert project["whole_episode_retry_allowed"] is False
    assert project["execution_closure_pr_budget"] == 1
    assert project["activation_consumes_live_episode"] is False
    assert project["activation_consumes_execution_closure_pr_budget"] is False
    status = ACTIVATION["execution_status"]
    assert status["episode_started"] is False
    assert status["episode_claimed"] is False
    assert status["episode_consumed"] is False


def test_claim_ref_is_exact_and_claim_remains_absent():
    claim = ACTIVATION["claim_contract"]
    assert claim["claim_mechanism"] == "REMOTE_GIT_REF_PLUS_O_EXCL_RECEIPT"
    assert claim["remote_claim_ref"] == "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0"
    assert claim["remote_claim_create_only"] is True
    assert claim["remote_claim_fail_if_exists"] is True
    assert claim["remote_claim_force_update_forbidden"] is True
    assert claim["remote_claim_ref_must_be_absent_before_activation"] is True
    assert claim["local_receipt_creation"] == "O_EXCL under the disposable execution state directory"
    assert claim["claim_must_precede_adapter_io"] is True
    assert claim["claim_write_must_complete_before_provider_io"] is True
    assert claim["partial_claim_behavior"] == "BLOCK_NEVER_REPLAY"
    assert claim["created_during_activation_construction"] is False
    receipts = ACTIVATION["construction_receipts"]
    assert receipts["remote_claim_created"] is False
    assert receipts["local_claim_created"] is False


def test_parent_child_ceilings_and_claude_hard_read_only_policy_are_unchanged():
    parent = ACTIVATION["parent_authority"]
    assert (parent["provider"], parent["model"], parent["route"]) == ("openai", "gpt-5-mini", "llm-pi-ai")
    assert parent["max_request_attempts"] == 8
    assert parent["llm_retries"] == parent["provider_retry"] == 0
    assert parent["automatic_continuation"] is False
    assert parent["max_tokens_per_request"] == 4096
    assert parent["max_total_spend_usd"] == 1.0
    assert parent["attempt_9"] == "BLOCK_COST_BEFORE_PROVIDER_IO"
    child = ACTIVATION["child_authority"]
    assert child["model_facing_tools"] == ["subagent_codex", "subagent_claude_code"]
    assert child["generic_child_tools"] == []
    assert child["codex_calls_max"] == child["claude_calls_max"] == 2
    assert child["background_delegation"] is False
    claude = ACTIVATION["claude_policy"]
    assert claude["allowed_tools"] == ["Read", "Glob", "Grep"]
    assert claude["denied_tools"] == ["Write", "Edit", "Bash", "Agent", "Task", "mcp__*", "AskUserQuestion", "delegation"]
    assert all(claude[key] is False for key in ("write_allowed", "edit_allowed", "bash_allowed", "agent_allowed", "task_allowed", "mcp_allowed", "ask_user_question_allowed", "delegation_allowed"))
    assert claude["permission_mode"] == "dontAsk"
    assert claude["setting_sources"] == []
    assert claude["strict_mcp_config"] is True
    assert claude["mcp_servers"] == {}
    assert claude["agents"] == {}
    assert claude["plugins"] == []
    assert claude["persistence"] is False


def test_fixture_is_unchanged_and_workspace_is_disposable_only():
    fixture = ACTIVATION["fixture"]
    assert fixture["fixture_id"] == "STAGE_A_BOUNDED_RETRY_V0"
    assert fixture["fixture_digest"] == "397ed055f2fb5cd14fd4c0b54fc21994c688f6cf56f07fb073d4e3257cd47552"
    assert fixture["mutable_paths"] == ["retry.py"]
    assert fixture["immutable_paths"] == ["TASK.md", "tests/test_retry.py"]
    assert fixture["fresh_disposable_copy_required"] is True
    assert fixture["outside_fixture_mutation_allowed"] is False
    workspace = ACTIVATION["workspace_policy"]
    assert workspace["fresh_disposable_workspace_required"] is True
    assert workspace["session_cwd_must_equal_workspace"] is True
    assert workspace["realpath_symlink_aware_containment_required"] is True
    assert workspace["explicit_disposable_dsh_home_required"] is True
    assert workspace["ambient_dsh_home_forbidden"] is True
    assert workspace["qntylab_repository_mutation"] is False


def test_no_secret_model_dsh_spend_or_fixture_activity_and_downstream_denied():
    status = ACTIVATION["execution_status"]
    assert status["real_secret_read"] is False
    assert status["dsh_invocations"] == 0
    assert status["parent_requests"] == 0
    assert status["public_model_requests"] == 0
    assert status["codex_real_child_turns"] == 0
    assert status["claude_real_child_turns"] == 0
    assert status["spend_usd"] == 0.0
    assert status["fixture_mutations"] == 0
    firewall = ACTIVATION["authority_firewall"]
    assert firewall == {
        "stage_b_authorized": False,
        "qnty_runtime_authority": "NONE",
        "trading_authority": "NONE",
        "capital_authority": "NONE",
        "scientific_execution_authorized": False,
        "qnty_agent_eval": "NOT_APPLICABLE",
    }


def test_project_context_keeps_execution_closed_blocked_and_inactive():
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    active = [
        record
        for record in projects.values()
        if record["state"] == "ACTIVE"
        and record["project_id"] != "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R2R1"
    ]
    assert active == []
    record = projects["DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0"]
    assert record["state"] == "CLOSED_BLOCKED"
    assert record["implementation_authorized"] is False
    assert record["implementation_completed"] is True
    assert record["activation_authorized_after_canonicalization"] is True
    assert record["authorization_pr"] == 182
    assert record["authorization_merge_sha"] == "0dbd9ee0dceb9c6dab9781816230b5518c1de490"
    assert record["episode_consumed"] is False
    assert record["authorized_live_episodes"] == 1
    assert record["execution_closure_pr_budget"] == 1
    assert record["activation_consumes_live_episode"] is False
    assert record["activation_consumes_execution_closure_pr_budget"] is False
