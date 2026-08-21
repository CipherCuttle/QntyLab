from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_multi_agent_orchestration_stage_a_v1r1_execution_v0/execution_evidence.json"


def test_blocked_stage_a_v1r1_evidence_is_sanitized_and_pre_dispatch() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["terminal_outcome"] == "STAGE_A_V1R1_BLOCK_CHILD_INFRA"
    assert evidence["prelive"]["boot_ready"] == "YES"
    assert evidence["native_preflight"]["compatibility"] == "INCOMPATIBLE"
    assert evidence["native_preflight"]["paid_parent_dispatch_attempted"] is False
    assert evidence["live"]["episode_consumed"] is False
    assert evidence["live"]["parent_request_attempts"] == 0
    assert evidence["live"]["codex_actual_calls"] == 0
    assert evidence["live"]["claude_actual_calls"] == 0
    assert evidence["fixture"]["pre_hashes"] == evidence["fixture"]["post_hashes"]
    assert evidence["fixture"]["mutation_scope"] == "NONE"
    assert evidence["secret_statement"]["secret_gate"] == "NOT_READ_NATIVE_PREFLIGHT_FAILED"
    assert evidence["secret_statement"]["secret_value_exposed_by_stage_a_v1r1_execution_tooling"] is False
    assert evidence["secret_statement"]["secret_value_committed_or_persisted_in_stage_a_v1r1_artifacts"] is False
