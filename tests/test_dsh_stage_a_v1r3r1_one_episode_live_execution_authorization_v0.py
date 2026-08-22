import hashlib
import json
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r1_one_episode_live_execution_authorization_v0"
AUTH = json.loads((ARTIFACT / "authorization.json").read_text(encoding="utf-8"))
QUALIFICATION = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r1_real_runtime_qualification_v0/qualification.json"


def test_canonical_predecessor_and_qualified_digest_are_exact_and_current():
    assert AUTH["canonical_predecessor"] == {
        "project_id": "DSH_STAGE_A_V1R3R1_REAL_RUNTIME_QUALIFICATION_V0",
        "pr": 177,
        "reviewed_head": "17a7c2b9df724b4bf09b6eab5c1e40ae21a5ebd8",
        "merge": "57bf0ec0072077cc32055300c516133fff0b7c20",
        "required_state": "CLOSED_PASS",
        "qualification_sha256": "85a345c2d1a9c3517b55a8fbb4bccf78855217dab9e32586c2771f10b1e86c31",
        "binding_mismatch_behavior": "BLOCK_AUTH",
    }
    assert hashlib.sha256(QUALIFICATION.read_bytes()).hexdigest() == AUTH["canonical_predecessor"]["qualification_sha256"]
    contract = AUTH["qualified_launch_contract"]
    assert contract["digest"] == "4cd2734f229a97d4258ace4576f23f76f3d36aeef888a19fa61d2f4a7bff37d4"
    assert contract["superseded_digests"]["3bf649f5cbdd96dcc0edf91cd7dfb88b3245ff3617518c9d5da3dfbd5a01a18e"] == "SUPERSEDED_INVALID_DIGEST_CANONICALIZATION"
    assert contract["mismatch_behavior"] == "BLOCK_BEFORE_SECRET_READ_AND_MODEL_IO"


def test_exact_dsh_runtime_and_executable_identities_are_bound():
    assert AUTH["pinned_dsh_identity"] == {
        "repository": "deepseek-ai/deepseek-harness",
        "commit": "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca",
        "tree": "3bc8f89fe494a4755c188be354add4e8b1e7b188",
        "tag": "dsh-v0.1.0-rc.7",
        "moving_tag_or_branch_allowed": False,
        "later_commit_allowed": False,
    }
    identity = AUTH["runtime_identity"]
    for key in ("node_executable_digest", "python_executable_digest", "pnpm_executable_digest", "codex_executable_digest", "claude_executable_digest"):
        assert len(identity[key]) == 64
    assert identity["claude_sdk"] == {
        "package": "@anthropic-ai/claude-agent-sdk",
        "version": "0.3.220",
        "package_json_digest": "1c9d0905f64e126850efe4fc4e7244c604a0855de8d4c82aff78da6f1988bd08",
    }


def test_episode_parent_and_child_limits_are_fail_closed():
    episode = AUTH["episode_authority"]
    parent = AUTH["parent_authority"]
    child = AUTH["child_authority"]
    assert episode["live_episodes_max"] == 1
    assert episode["episode_consumed_initial"] is False
    assert episode["second_episode_allowed"] is False
    assert episode["claim_must_precede_adapter_io"] is True
    assert parent["provider"] == "openai" and parent["model"] == "gpt-5-mini"
    assert parent["max_request_attempts"] == 8
    assert parent["retry_policy"] == {"llm_retries": 0, "provider_retry": 0, "automatic_continuation": False}
    assert parent["max_tokens_per_request"] == 4096
    assert parent["max_total_spend_usd"] == 1.0
    assert parent["attempt_9"] == "BLOCK_COST_BEFORE_PROVIDER_IO"
    assert child["model_facing_tools"] == ["subagent_codex", "subagent_claude_code"]
    assert child["codex_calls_max"] == 2 and child["claude_calls_max"] == 2
    assert child["generic_child_tools"] == []
    assert child["alternate_delegation_routes"] == []


def test_fixture_workspace_secret_order_and_authority_firewall_are_frozen():
    fixture = AUTH["fixture"]
    assert fixture["fixture_id"] == "STAGE_A_BOUNDED_RETRY_V0"
    assert fixture["mutable_paths_in_disposable_copy"] == ["retry.py"]
    assert fixture["outside_fixture_mutation_allowed"] is False
    assert fixture["fixture_digest"] == "397ed055f2fb5cd14fd4c0b54fc21994c688f6cf56f07fb073d4e3257cd47552"
    assert set(fixture["initial_file_digests_sha256"]) == {"fixture/TASK.md", "fixture/retry.py", "fixture/tests/test_retry.py"}
    for relative, expected in fixture["initial_file_digests_sha256"].items():
        assert hashlib.sha256((ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_multi_agent_orchestration_stage_a_authorization_v0" / relative).read_bytes()).hexdigest() == expected
    workspace = AUTH["workspace_policy"]
    assert workspace["fresh_disposable_workspace_required"] is True
    assert workspace["session_cwd_must_equal_workspace"] is True
    assert workspace["explicit_disposable_dsh_home_required"] is True
    assert workspace["ambient_dsh_home_forbidden"] is True
    assert AUTH["prelive_gate"]["secret_read_required"] is False
    assert AUTH["prelive_gate"]["secret_read_allowed_only_after_all_non_secret_gates"] is True
    boundary = AUTH["governance_boundary"]
    assert boundary["live_execution_during_authorization_phase"] is False
    assert boundary["authorization_phase_paid_model_calls"] == 0
    assert boundary["authorization_phase_spend_usd"] == 0.0


def test_no_stage_b_or_downstream_authority_and_receipt_has_no_secret_material():
    boundary = AUTH["governance_boundary"]
    assert boundary["stage_b_authorized"] is False
    assert boundary["scientific_execution_authorized"] is False
    assert boundary["qnty_runtime_authority"] == "NONE"
    assert boundary["trading_authority"] == "NONE"
    assert boundary["capital_authority"] == "NONE"
    assert AUTH["qnty_agent_eval"] == "NOT_APPLICABLE"
    assert AUTH["receipt_schema"]["secret_material_allowed"] is False
    artifact_text = (ARTIFACT / "authorization.json").read_text(encoding="utf-8")
    assert "sk-" not in artifact_text
    assert "secret_derived_identifiers_recorded" in artifact_text
    assert AUTH["wall_clock"]["live_episode_timeout_seconds"] == 1800


def test_project_registry_has_closed_construction_and_no_active_project():
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    assert [record for record in projects.values() if record["state"] == "ACTIVE"] == []
    record = projects[AUTH["project_id"]]
    assert record["state"] == "CLOSED_PASS"
    assert record["implementation_authorized"] is False
    assert record["implementation_completed"] is True
    assert record["episode_consumed"] is False
    assert record["authorized_live_episodes"] == 1
    assert record["activation_consumes_live_episode"] is False
    assert record["activation_consumes_execution_closure_pr_budget"] is False
    assert record["stage_b_authorized"] is False
    assert record["qnty_runtime_authority"] == "NONE"
    assert record["trading_authority"] == "NONE"
    assert record["capital_authority"] == "NONE"
