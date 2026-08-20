import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_terminal_error_permission_policy_forensics_authorization_v0"


def load(name: str) -> dict:
    return json.loads((ARTIFACT / name).read_text(encoding="utf-8"))


def test_authorization_is_single_variable_and_bounded():
    value = load("authorization.json")
    assert value["phase_state"] == "CLOSED_PASS"
    assert value["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert value["scope"]["live_intervention_b_canaries"] == 1
    assert value["scope"]["retry_count"] == 0
    assert value["causal_intervention"]["allowed_wire_delta"] == [{
        "method": "thread/start",
        "path": "params.approvalPolicy",
        "before": "<ABSENT>",
        "after": "never",
    }]
    assert value["causal_intervention"]["forbidden_additions"]


def test_identities_and_predecessor_firewall_are_frozen():
    value = load("authorization.json")
    assert value["canonical_master"] == "502a4e02993f1d23f3cb91bc0d70044ebccaa79c"
    assert value["dsh_identity"] == {
        "repository": "deepseek-ai/deepseek-harness",
        "commit": "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca",
        "tree": "3bc8f89fe494a4755c188be354add4e8b1e7b188",
        "tag": "dsh-v0.1.0-rc.7",
        "package_version": "0.1.0-rc.7",
        "floating_source_forbidden": True,
        "source_mutation_rule": "Only the explicitly recorded one-field intervention patch may differ in the disposable canary copy; the frozen checkout is never modified.",
    }
    assert value["codex_identity"]["version"] == "codex-cli 0.147.0"
    assert value["predecessor_integrity"]["pr137_result_mutation"] is False
    assert value["predecessor_integrity"]["pr141_result_mutation"] is False
    assert value["authority_ceiling"]["stage_a"] is False
    assert value["authority_ceiling"]["v0r3"] is False


def test_governance_review_has_no_open_critical_or_high():
    review = (ARTIFACT / "hostile_governance_review.md").read_text(encoding="utf-8")
    assert "| Critical | None." in review
    assert "| High | None." in review
