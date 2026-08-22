import json
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r1_one_episode_live_execution_v0"
ACTIVATION = json.loads((ARTIFACT / "activation.json").read_text(encoding="utf-8"))


def test_activation_is_bound_to_canonical_authorization_and_master():
    canonical = ACTIVATION["canonicalization"]
    assert canonical["candidate_base_sha"] == "401a5a22a759673a99c66cc30c502279f9ed111b"
    assert canonical["canonical_predecessor_project_id"] == "DSH_STAGE_A_V1R3R1_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0"
    assert canonical["canonical_predecessor_pr"] == 178
    assert canonical["canonical_predecessor_merge"] == "401a5a22a759673a99c66cc30c502279f9ed111b"
    assert canonical["required_predecessor_state"] == "CLOSED_PASS"
    assert canonical["branch_local_candidate_does_not_self_authorize"] is True
    assert canonical["canonical_presence_required_before_execution"] is True


def test_claim_is_durable_and_precedes_provider_io():
    claim = ACTIVATION["claim_contract"]
    assert claim["claim_must_precede_adapter_io"] is True
    assert claim["claim_mechanism"] == "REMOTE_GIT_REF_PLUS_O_EXCL_RECEIPT"
    assert claim["remote_claim_ref"] == "refs/heads/qntylab-claims/dsh-stage-a-v1r3r1-one-episode-live-execution-v0"
    assert claim["remote_claim_ref_must_be_absent_before_activation"] is True
    assert claim["claim_write_must_complete_before_provider_io"] is True
    assert claim["temporary_in_memory_boolean_is_not_a_claim"] is True


def test_exact_runtime_parent_child_and_fixture_boundaries():
    runtime = ACTIVATION["runtime_identity"]
    assert runtime["commit"] == "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
    assert runtime["tree"] == "3bc8f89fe494a4755c188be354add4e8b1e7b188"
    assert runtime["tag"] == "dsh-v0.1.0-rc.7"
    assert runtime["qualified_launch_contract_digest"] == "4cd2734f229a97d4258ace4576f23f76f3d36aeef888a19fa61d2f4a7bff37d4"
    parent = ACTIVATION["parent_authority"]
    assert (parent["provider"], parent["model"], parent["route"]) == ("openai", "gpt-5-mini", "llm-pi-ai")
    assert parent["max_request_attempts"] == 8
    assert parent["llm_retries"] == parent["provider_retry"] == 0
    assert parent["automatic_continuation"] is False
    assert parent["max_tokens_per_request"] == 4096
    assert parent["max_total_spend_usd"] == 1.0
    child = ACTIVATION["child_authority"]
    assert child["model_facing_tools"] == ["subagent_codex", "subagent_claude_code"]
    assert child["generic_child_tools"] == []
    assert child["codex_calls_max"] == child["claude_calls_max"] == 2
    fixture = ACTIVATION["fixture"]
    assert fixture["fixture_id"] == "STAGE_A_BOUNDED_RETRY_V0"
    assert fixture["fixture_digest"] == "397ed055f2fb5cd14fd4c0b54fc21994c688f6cf56f07fb073d4e3257cd47552"
    assert fixture["mutable_paths"] == ["retry.py"]
    assert fixture["immutable_paths"] == ["TASK.md", "tests/test_retry.py"]


def test_activation_does_not_consume_episode_or_expand_authority():
    project = ACTIVATION["active_execution_project"]
    status = ACTIVATION["execution_status"]
    closure = ACTIVATION["closure_contract"]
    assert project["state"] == "ACTIVE"
    assert project["implementation_authorized"] is True
    assert project["implementation_completed"] is False
    assert project["authorized_live_episodes"] == 1
    assert project["episode_consumed"] is False
    assert project["second_episode_authorized"] is False
    assert project["whole_episode_retry_allowed"] is False
    assert project["execution_closure_pr_budget"] == 1
    assert status["episode_started"] is False
    assert status["episode_claimed"] is False
    assert status["episode_consumed"] is False
    assert status["secret_read"] is False
    assert status["paid_model_requests"] == 0
    assert status["spend_usd"] == 0.0
    assert closure["stage_b_authorized"] is False
    assert closure["qnty_runtime_authority"] == "NONE"
    assert closure["trading_authority"] == "NONE"
    assert closure["capital_authority"] == "NONE"
    assert closure["scientific_execution_authorized"] is False
    assert closure["qnty_agent_eval"] == "NOT_APPLICABLE"


def test_project_context_keeps_execution_closed_blocked_and_inactive():
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    active = [record for record in projects.values() if record["state"] == "ACTIVE"]
    assert active == []
    record = projects["DSH_STAGE_A_V1R3R1_ONE_EPISODE_LIVE_EXECUTION_V0"]
    assert record["state"] == "CLOSED_BLOCKED"
    assert record["implementation_authorized"] is False
    assert record["implementation_completed"] is True
    assert record["activation_authorized_after_canonicalization"] is True
    assert record["episode_consumed"] is False
    assert record["authorized_live_episodes"] == 1
    assert record["claim_must_precede_provider_io"] is True
    assert record["terminal_outcome"] == "BLOCK_CHILD_INFRA"
