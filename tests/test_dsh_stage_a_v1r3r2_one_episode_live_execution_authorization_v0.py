import hashlib
import json
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0"
AUTH = json.loads((ARTIFACT / "authorization.json").read_text(encoding="utf-8"))
QUALIFICATION = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_claude_hard_read_only_repair_and_requalification_v0/qualification.json"


def test_exact_v1r3r2_qualification_replaces_v1r3r1():
    assert hashlib.sha256(QUALIFICATION.read_bytes()).hexdigest() == AUTH["canonical_predecessor"]["qualification_sha256"]
    assert AUTH["canonical_predecessor"] == {
        "project_id": "DSH_STAGE_A_V1R3R2_CLAUDE_HARD_READ_ONLY_REPAIR_AND_REQUALIFICATION_V0",
        "pr": 181,
        "reviewed_head": "4ee6131ddcc39d4c677db1259cab2c23d7937379",
        "merge": "117df125266b028225aefdd87cebdfadc7ab3735",
        "required_state": "CLOSED_PASS",
        "qualification_sha256": "f25d9305cbfe106b1b7295088140e9b6f4c2f8e041692ebea7e8f63630988304",
        "binding_mismatch_behavior": "BLOCK_AUTH",
    }
    contract = AUTH["qualified_launch_contract"]
    assert contract["digest"] == "57162eb65a4177ae58c6b503110dfe802ae345c3e6e9c3963acd207f693fbcc1"
    assert contract["runtime_manifest_digest"] == "afcfa011de46bd9fccaa120b5612c24a5ace2b2c451591ddf8b67fb43a8ce321"
    assert contract["executable_identity_digest"] == "ae07ece34c88b3ebaebd7452df8d136c82935f9c8ec9df16a40e50a2582a2fd9"
    assert contract["launch_policy_digest"] == "34d5ceabbd89eaa7520cb5d5b69fa938a4cf15132b5c37e98382c4f6aab53f28"
    assert contract["repair_digests"] == {
        "codex": "f89bf5833956f3c4202ca88a9285e39658976b29605fc1b63b7c62ebdd07fcb3",
        "claude": "2b8277bf13e077651046e2527dc7aa092c3c9669cedc61eac1f742d9364a17e3",
    }
    assert contract["superseded_digests"] == {"4cd2734f229a97d4258ace4576f23f76f3d36aeef888a19fa61d2f4a7bff37d4": "V1R3R1_AUTHORITY_INCOMPATIBLE_WITH_V1R3R2_RUNTIME"}
    assert AUTH["v1r3r1_authority_compatible"] is False


def test_pinned_runtime_fixture_and_claude_policy_are_exact():
    assert AUTH["pinned_dsh_identity"] == {
        "repository": "deepseek-ai/deepseek-harness",
        "commit": "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca",
        "tree": "3bc8f89fe494a4755c188be354add4e8b1e7b188",
        "tag": "dsh-v0.1.0-rc.7",
        "moving_tag_or_branch_allowed": False,
        "later_commit_allowed": False,
    }
    assert AUTH["fixture"] == {
        "fixture_id": "STAGE_A_BOUNDED_RETRY_V0",
        "root": "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_multi_agent_orchestration_stage_a_authorization_v0/fixture",
        "fixture_digest": "397ed055f2fb5cd14fd4c0b54fc21994c688f6cf56f07fb073d4e3257cd47552",
        "fixture_digest_basis": "sha256 of canonical JSON for initial_file_digests_sha256",
        "initial_file_digests_sha256": {
            "fixture/TASK.md": "19571f8c70364e41ae8366cd07b0f56546845c8b3f43b04f93634f75f9a6a6ff",
            "fixture/retry.py": "f82a84088b76dd82ead87d5536f8120d62e7c4408c27fcbe59662155b5dd47ae",
            "fixture/tests/test_retry.py": "caf317035b37a6606ff7b2250cf0b1cc6a1e8db7660414bf280eda4ddee641ac",
        },
        "mutable_paths_in_disposable_copy": ["retry.py"],
        "immutable_paths": ["TASK.md", "tests/test_retry.py"],
        "outside_fixture_mutation_allowed": False,
        "fresh_disposable_copy_required": True,
    }
    claude = AUTH["child_execution_policies"]["claude"]
    assert claude["allowed_tools"] == ["Read", "Glob", "Grep"]
    assert claude["tools"] == ["Read", "Glob", "Grep"]
    assert claude["disallowed_tools"] == ["Write", "Edit", "Bash", "Agent", "Task", "mcp__*", "AskUserQuestion", "delegation"]
    assert all(claude[key] is False for key in ("write_allowed", "edit_allowed", "bash_allowed", "agent_allowed", "task_allowed", "mcp_allowed", "delegation_allowed", "ask_user_question_allowed"))
    assert claude["permission_mode"] == "dontAsk"
    assert claude["setting_sources"] == [] and claude["strict_mcp_config"] is True
    assert claude["mcp_servers"] == {} and claude["agents"] == {} and claude["plugins"] == [] and claude["persistence"] is False


def test_episode_budget_claim_and_authority_firewall_are_fail_closed():
    episode = AUTH["episode_authority"]
    parent = AUTH["parent_authority"]
    child = AUTH["child_authority"]
    assert episode["live_episodes_max"] == 1 and episode["episode_consumed_initial"] is False
    assert episode["second_episode_allowed"] is False and episode["whole_episode_retry_allowed"] is False
    assert parent["provider"] == "openai" and parent["model"] == "gpt-5-mini" and parent["route"] == "llm-pi-ai"
    assert parent["max_request_attempts"] == 8 and parent["max_tokens_per_request"] == 4096 and parent["max_total_spend_usd"] == 1.0
    assert parent["retry_policy"] == {"llm_retries": 0, "provider_retry": 0, "automatic_continuation": False}
    assert parent["attempt_9"] == "BLOCK_COST_BEFORE_PROVIDER_IO"
    assert child["model_facing_tools"] == ["subagent_codex", "subagent_claude_code"] and child["codex_calls_max"] == 2 and child["claude_calls_max"] == 2
    assert child["generic_child_tools"] == [] and child["alternate_delegation_routes"] == [] and child["background_delegation"] is False
    claim = AUTH["claim_contract"]
    assert claim["mechanism"] == "REMOTE_GIT_REF_PLUS_O_EXCL_RECEIPT"
    assert claim["remote_claim_ref"] == "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0"
    assert claim["remote_claim_create_only_fail_if_exists"] is True and claim["local_receipt_open_exclusive"] is True
    assert claim["both_complete_before_first_potentially_paid_parent_dispatch"] is True
    assert claim["partial_claim_behavior"] == "BLOCK_NEVER_REPLAY" and claim["crash_or_timeout_restores_authority"] is False
    assert claim["created_during_authorization_construction"] is False
    boundary = AUTH["governance_boundary"]
    assert boundary["stage_b_authorized"] is False and boundary["scientific_execution_authorized"] is False
    assert boundary["qnty_runtime_authority"] == "NONE" and boundary["trading_authority"] == "NONE" and boundary["capital_authority"] == "NONE"
    assert AUTH["qnty_agent_eval"] == "NOT_APPLICABLE"


def test_construction_has_no_secret_live_or_claim_side_effects():
    assert AUTH["secret_policy"]["authorization_phase_secret_read"] is False
    assert AUTH["secret_policy"]["secret_value_recorded"] is False
    assert AUTH["secret_policy"]["secret_derived_identifiers_recorded"] is False
    assert AUTH["receipt_schema"]["secret_material_allowed"] is False
    assert AUTH["construction_receipts"] == {
        "real_secret_read": False,
        "remote_claim_created": False,
        "local_claim_created": False,
        "dsh_invocations": 0,
        "public_model_requests": 0,
        "codex_real_child_turns": 0,
        "claude_real_child_turns": 0,
        "spend_usd": 0.0,
        "live_episodes": 0,
    }
    assert AUTH["wall_clock"] == {"live_episode_timeout_seconds": 1800, "timeout_allows_rerun": False}
    assert AUTH["execution_authority_after_construction"] == {
        "available": True,
        "state": "UNCONSUMED_ONE_EPISODE_AVAILABLE_IF_CANONICAL",
        "implementation_authorized": False,
        "implementation_completed": True,
        "active_project_after_closure": "NONE",
        "future_execution_result_recorded": False,
        "stage_b_requires_separate_decision": True,
    }


def test_project_registry_closes_construction_without_active_project():
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    assert [record for record in projects.values() if record["state"] == "ACTIVE"] == []
    record = projects[AUTH["project_id"]]
    assert record["state"] == "CLOSED_PASS"
    assert record["implementation_authorized"] is False and record["implementation_completed"] is True
    assert record["episode_consumed"] is False and record["authorized_live_episodes"] == 1
    assert record["second_episode_authorized"] is False
    assert record["stage_b_authorized"] is False and record["qnty_runtime_authority"] == "NONE"
    assert record["trading_authority"] == "NONE" and record["capital_authority"] == "NONE"
