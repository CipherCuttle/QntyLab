from __future__ import annotations

import hashlib
import json
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_multi_agent_orchestration_stage_a_v1r1_live_execution_authorization_and_activation_v0"
AUTH = json.loads((ARTIFACT / "authorization.json").read_text(encoding="utf-8"))
PROJECT_ID = "DSH_MULTI_AGENT_ORCHESTRATION_STAGE_A_V1R1_EXECUTION_V0"
PREDECESSOR_ID = "DSH_MULTI_AGENT_ORCHESTRATION_STAGE_A_V1R1_BOOTSTRAP_AND_RUNTIME_HARDENING_AUTHORIZATION_V0"


def test_authorization_artifact_is_canonical_one_episode_activation():
    assert AUTH["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert AUTH["authorization_effective"] == "AFTER_CANONICAL_MERGE_ONLY"
    assert AUTH["active_execution_project"] == {
        "state": "ACTIVE",
        "authority_level": "BOUNDED_ONE_EPISODE_DSH_V1R1_EXECUTION_AND_CLOSURE",
        "phase_type": "BOUNDED_LIVE_INFRASTRUCTURE_EXECUTION",
        "implementation_authorized": True,
        "implementation_completed": False,
        "episode_consumed": False,
        "authorized_live_episodes": 1,
        "second_v1r1_episode_authorized": False,
        "execution_closure_pr_budget": 1,
        "activation_consumes_live_episode": False,
        "activation_consumes_execution_closure_pr_budget": False,
    }


def test_project_context_closes_execution_project_after_terminal_outcome():
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    record = projects[PROJECT_ID]
    assert record["state"] == "CLOSED_BLOCKED"
    assert record["implementation_authorized"] is False
    assert record["implementation_completed"] is True
    assert record["episode_consumed"] is False
    assert record["second_v1r1_episode_authorized"] is False
    assert record["stage_b_authorized"] is False
    assert record["active_project_after_closure"] == "NONE"


def test_project_context_preserves_closed_qualified_predecessor():
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    predecessor = projects[PREDECESSOR_ID]
    assert predecessor["state"] == "CLOSED_PASS"
    assert predecessor["implementation_authorized"] is False
    assert predecessor["implementation_completed"] is True
    assert predecessor["canonical_predecessor_pr"] == 169
    assert predecessor["canonical_predecessor_merge"] == "64cd87fc2f28a59f9c7670c73d6e0af04e0fba7a"


def test_exact_predecessor_binding_and_qualification_digest():
    predecessor = AUTH["canonical_predecessor"]
    assert predecessor["pr"] == 170
    assert predecessor["reviewed_head"] == "1443d89f2f12f37dff777d2de05563698a2dce6b"
    assert predecessor["merge"] == "e9c7a889747fd3a978f241e12448570b4634db81"
    receipt = ROOT / AUTH["qualification_receipt"]["path"]
    assert hashlib.sha256(receipt.read_bytes()).hexdigest() == AUTH["qualification_receipt"]["sha256"]
    assert AUTH["qualification_receipt"]["qualification"] == "QUALIFIED_OFFLINE_BOOT_READY"
    assert AUTH["qualification_receipt"]["boot_ready"] == "YES"


def test_parent_budget_and_child_authority_are_frozen():
    parent = AUTH["parent_authority"]
    assert parent["provider"] == "openai"
    assert parent["model"] == "gpt-5-mini"
    assert parent["max_request_attempts"] == 8
    assert parent["retry_max"] == 0
    assert parent["max_tokens"] == 4096
    assert parent["spend_ceiling_usd"] <= 1.0
    assert parent["auxiliary_routes"] == []

    child = AUTH["child_authority"]
    assert child["model_facing_tools"] == ["subagent_codex", "subagent_claude_code"]
    assert child["gated_providers"] == ["qntylab-gated-codex", "qntylab-gated-claude-code"]
    assert child["raw_model_facing_routes"] is False
    assert child["generic_child_tools"] == []
    assert child["background_delegation"] is False
    assert child["child_infra_retries"] == 0


def test_no_authority_leakage_or_live_activity_in_this_phase():
    firewall = AUTH["authority_firewall"]
    assert firewall["benchmark_suite_authorized"] is False
    assert firewall["scientific_execution_authorized"] is False
    assert firewall["qnty_agent_eval"] == "NOT_APPLICABLE"
    assert firewall["qnty_runtime_authority"] == "NONE"
    assert firewall["trading_authority"] == "NONE"
    assert firewall["capital_authority"] == "NONE"
    assert firewall["stage_b_authorized"] is False
    assert firewall["live_openai_calls_this_phase"] == 0
    assert firewall["live_dsh_calls_this_phase"] == 0
    assert firewall["live_codex_calls_this_phase"] == 0
    assert firewall["live_claude_calls_this_phase"] == 0
    assert firewall["spend_usd_this_phase"] == 0.0
    assert AUTH["execution_status"]["future_execution_result_recorded"] is False


def test_project_context_next_action_is_bounded_and_no_second_episode():
    data = project_context.context_data(ROOT)
    assert data["active_project"]["project_id"] == "DSH_MULTI_AGENT_ORCHESTRATION_STAGE_A_V1R2_EXECUTION_V0"
    assert data["current_permitted_next_action"].startswith("Execute exactly one Stage-A V1R2 live episode")


def test_codex_claude_and_prelive_boundaries_are_fail_closed():
    codex = AUTH["codex_contract"]
    assert codex["modifiable_paths"] == ["retry.py"]
    assert codex["immutable_paths"] == ["TASK.md", "tests/test_retry.py"]
    assert codex["repository_mutation"] is False
    assert codex["approval_policy"] == "never"
    assert codex["sandbox"] == "workspace-write"
    assert codex["ephemeral"] is True

    claude = AUTH["claude_contract"]
    assert claude["allowed_tools"] == ["Read", "Glob", "Grep"]
    assert set(["Write", "Edit", "Bash", "Agent", "Task", "mcp__*"]).issubset(claude["disallowed_tools"])
    assert claude["persist_session"] is False
    assert claude["setting_sources"] == []
    assert claude["malformed_review_terminal"] == "BLOCK_CHILD_INFRA"

    prelive = AUTH["prelive"]
    assert prelive["boot_ready"] == "YES"
    assert prelive["model_requests"] == 0
    assert prelive["child_spawns"] == 0
    assert prelive["secret_read_before_prelive_pass"] is False
    assert prelive["runtime_repair_allowed"] is False


def test_authorization_phase_does_not_consume_episode_or_closure_budget():
    status = AUTH["execution_status"]
    assert status["episode_started"] is False
    assert status["authorization_pr_consumes_live_episode"] is False
    assert status["authorization_pr_consumes_execution_closure_pr_budget"] is False
