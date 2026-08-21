from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / (
    "experiments/research/qnty_agent_orchestration_control_contract_v0/"
    "dsh_multi_agent_orchestration_stage_a_v1r2_execution_v0/execution_evidence.json"
)
CLOSURE = EVIDENCE.with_name("closure.md")


def test_v1r2_blocked_evidence_is_sanitized_and_pre_dispatch() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["terminal_outcome"] == "STAGE_A_V1R2_BLOCK_PARENT_INFRA"
    assert evidence["prelive"]["boot_ready"] == "YES"
    assert evidence["prelive"]["secret_gate"] == "PASS"
    assert evidence["prelive"]["secret_read_before_prelive_pass"] is False
    assert evidence["live"]["first_paid_parent_dispatch"] is False
    assert evidence["live"]["parent_request_attempts"] == 0
    assert evidence["live"]["codex_actual_calls"] == 0
    assert evidence["live"]["claude_actual_calls"] == 0
    assert evidence["live"]["estimated_spend_usd"] == 0.0
    assert evidence["live"]["episode_consumed"] is False
    assert evidence["fixture"]["pre_hashes"] == evidence["fixture"]["post_hashes"]
    assert evidence["fixture"]["mutation_scope"] == "NONE"
    assert evidence["secrecy"]["secret_value_exposed_by_stage_a_v1r2_execution_tooling"] is False
    assert evidence["secrecy"]["secret_value_committed_or_persisted_in_stage_a_v1r2_artifacts"] is False
    assert "OPENAI_API_KEY" not in EVIDENCE.read_text(encoding="utf-8")
    assert "tsx" in CLOSURE.read_text(encoding="utf-8")


def test_v1r2_closure_retired_authority_without_successor() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    closure = evidence["closure"]

    assert closure["project_state_after"] == "CLOSED_BLOCKED"
    assert closure["implementation_authorized_after"] is False
    assert closure["implementation_completed_after"] is True
    assert closure["authorized_live_episodes_after"] == 0
    assert closure["second_v1r2_episode_authorized"] is False
    assert closure["stage_b_authorized"] is False
    assert closure["active_project_after"] == "NONE"
