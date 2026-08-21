from __future__ import annotations

import hashlib
import json
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_multi_agent_orchestration_stage_a_v1r2_live_execution_authorization_and_activation_v0"
AUTH = json.loads((ARTIFACT / "authorization.json").read_text(encoding="utf-8"))
PROJECT_ID = "DSH_MULTI_AGENT_ORCHESTRATION_STAGE_A_V1R2_EXECUTION_V0"
QUALIFICATION = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_multi_agent_orchestration_stage_a_v1r2_native_child_compatibility_qualification_v0/qualification.json"


def test_exact_predecessor_and_qualification_binding():
    predecessor = AUTH["canonical_predecessor"]
    assert predecessor == {
        "project_id": "DSH_MULTI_AGENT_ORCHESTRATION_STAGE_A_V1R2_NATIVE_CHILD_COMPATIBILITY_QUALIFICATION_V0",
        "pr": 173,
        "reviewed_head": "d44d87ce974b7cb691a199aef79b68cf84bb768f",
            "merge": "c795f2233afe97b2fccbda41e62695cb8a2f84b5",
        "required_state": "CLOSED_PASS",
        "required_qualification": "V1R2_NATIVE_CHILD_COMPATIBILITY_CLOSED_PASS",
        "root_cause_correction": "VERSION_NAMESPACE_CONFLATION",
        "binding_mismatch_behavior": "BLOCK_AUTH",
    }
    receipt = AUTH["qualification_receipt"]
    assert hashlib.sha256(QUALIFICATION.read_bytes()).hexdigest() == receipt["sha256"]
    assert receipt["qualification"] == "CLOSED_PASS"
    assert receipt["codex_compatibility"] == "PASS"
    assert receipt["claude_compatibility"] == "PASS"
    assert receipt["version_namespace_equality"] == "NEVER_USED"


def test_exact_native_fingerprints_and_sdk_identity():
    identity = AUTH["compatibility_identity"]
    qualification = json.loads(QUALIFICATION.read_text(encoding="utf-8"))["future_live_preflight"]
    assert identity["codex_native_fingerprint"] == "fce6ecefe03ff72403f124456e4976a4a251ede6d1c74a820843ad1e7ee517a6"
    assert identity["claude_native_fingerprint"] == "8939d4b139759c12f240fdcba81661b5e8d59d53f769722baab001dea3f8180b"
    assert identity["claude_sdk_package"] == "@anthropic-ai/claude-agent-sdk"
    assert identity["claude_sdk_version"] == "0.3.220"
    assert identity["version_namespace_equality"] == "NEVER_USED"
    assert identity["semver_tolerance"] is False
    assert identity["codex_native_fingerprint"] == qualification["codex_executable_fingerprint"]
    assert identity["claude_native_fingerprint"] == qualification["claude_executable_fingerprint"]
    assert {"package": identity["claude_sdk_package"], "version": identity["claude_sdk_version"]} == qualification["claude_sdk_identity"]
    assert identity["version_namespace_equality"] == qualification["version_namespace_equality"]


def test_exactly_one_active_execution_project_and_activation_state():
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    active = [record for record in projects.values() if record["state"] == "ACTIVE"]
    assert [record["project_id"] for record in active] == [PROJECT_ID]
    record = projects[PROJECT_ID]
    assert record["implementation_authorized"] is True
    assert record["implementation_completed"] is False
    assert record["episode_consumed"] is False
    assert record["authorized_live_episodes"] == 1
    assert record["second_v1r2_episode_authorized"] is False
    assert record["execution_closure_pr_budget"] == 1
    assert record["activation_consumes_live_episode"] is False
    assert record["activation_consumes_execution_closure_pr_budget"] is False


def test_parent_child_budgets_and_hard_boundaries():
    parent = AUTH["parent_authority"]
    assert parent["max_request_attempts"] == 8
    assert parent["retry_max"] == 0
    assert parent["max_tokens"] == 4096
    assert parent["spend_ceiling_usd"] <= 1.0
    assert parent["auxiliary_routes"] == []
    child = AUTH["child_authority"]
    assert child["model_facing_tools"] == ["subagent_codex", "subagent_claude_code"]
    assert child["gated_providers"] == ["qntylab-gated-codex", "qntylab-gated-claude-code"]
    assert child["raw_providers_present"] == ["codex", "claude-code"]
    assert child["generic_child_tools"] == []
    assert child["background_delegation"] is False
    assert AUTH["child_order_and_budget"]["codex_total_max"] == 2
    assert AUTH["child_order_and_budget"]["claude_total_max"] == 2


def test_prelive_fingerprint_drift_blocks_before_secret_or_dispatch():
    prelive = AUTH["prelive"]
    assert prelive["boot_ready"] == "YES"
    assert prelive["plugin_tree_settled"] == "YES"
    assert prelive["model_requests"] == 0
    assert prelive["child_spawns"] == 0
    assert prelive["secret_read_before_prelive_pass"] is False
    assert prelive["recompute_native_fingerprints_after_prelive"] is True
    assert prelive["fingerprint_drift_action"] == ["BLOCK BEFORE SECRET", "BLOCK BEFORE PAID DISPATCH", "REQUIRE OFFLINE REQUALIFICATION"]


def test_authority_firewall_and_governance_phase_are_zero_activity():
    firewall = AUTH["authority_firewall"]
    assert firewall["stage_b_authorized"] is False
    assert firewall["scientific_execution_authorized"] is False
    assert firewall["qnty_agent_eval"] == "NOT_APPLICABLE"
    assert firewall["qnty_runtime_authority"] == "NONE"
    assert firewall["trading_authority"] == "NONE"
    assert firewall["capital_authority"] == "NONE"
    assert firewall["live_openai_calls_this_phase"] == 0
    assert firewall["live_dsh_calls_this_phase"] == 0
    assert firewall["live_codex_calls_this_phase"] == 0
    assert firewall["live_claude_calls_this_phase"] == 0
    assert firewall["stage_a_fixture_runs_this_phase"] == 0
    assert firewall["spend_usd_this_phase"] == 0.0
    assert AUTH["execution_status"]["future_execution_result_recorded"] is False


def test_claude_is_hard_read_only_and_authorization_does_not_consume_budgets():
    claude = AUTH["claude_contract"]
    assert claude["allowed_tools"] == ["Read", "Glob", "Grep"]
    assert set(["Write", "Edit", "Bash", "Agent", "Task", "MCP", "delegation"]).issubset(claude["disallowed_tools"])
    assert claude["persist_session"] is False
    assert claude["setting_sources"] == []
    assert claude["malformed_review_terminal"] == "BLOCK_CHILD_INFRA"
    status = AUTH["execution_status"]
    assert status["episode_started"] is False
    assert status["authorization_pr_consumes_live_episode"] is False
    assert status["authorization_pr_consumes_execution_closure_pr_budget"] is False
