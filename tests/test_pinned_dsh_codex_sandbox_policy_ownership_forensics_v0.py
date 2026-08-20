import json
from pathlib import Path

from qntylab.pinned_dsh_codex_sandbox_policy_ownership_forensics_v0 import (
    b_to_c_delta,
    c_total_delta,
    intervention_c_requests,
)
from qntylab import pinned_dsh_codex_terminal_error_permission_policy_forensics_v0 as controller


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_sandbox_policy_ownership_forensics_v0"
PREDECESSOR_B = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_permission_policy_canary_controller_gate_repair_and_continuation_v0"


def test_b_to_c_wire_delta_is_exactly_one_field():
    assert b_to_c_delta() == [{
        "method": "thread/start",
        "path": "params.sandbox",
        "before": "<ABSENT>",
        "after": "workspace-write",
    }]
    assert len(b_to_c_delta()) == 1


def test_c_total_delta_preserves_b_and_adds_only_sandbox():
    assert c_total_delta() == [
        {"method": "thread/start", "path": "params.approvalPolicy", "before": "<ABSENT>", "after": "never"},
        {"method": "thread/start", "path": "params.sandbox", "before": "<ABSENT>", "after": "workspace-write"},
    ]
    b = controller.intervention_b_requests()
    c = intervention_c_requests()
    assert b[1]["params"]["approvalPolicy"] == "never"
    assert "sandbox" not in b[1]["params"]
    assert c[1]["params"]["sandbox"] == "workspace-write"
    assert c[2] == b[2]


def test_no_related_sandbox_variables_are_introduced():
    c = intervention_c_requests()
    thread = c[1]["params"]
    assert set(thread) == {"cwd", "ephemeral", "approvalPolicy", "sandbox"}
    assert "sandboxPolicy" not in c[2]["params"]
    assert "runtimeWorkspaceRoots" not in c[2]["params"]
    assert "writableRoots" not in c[2]["params"]


def test_frozen_identity_and_prompt_are_preserved():
    diff = json.loads((ARTIFACT / "fake_app_server_request_diff.json").read_text(encoding="utf-8")) if (ARTIFACT / "fake_app_server_request_diff.json").exists() else None
    assert controller.DSH_COMMIT == "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
    assert controller.DSH_TREE == "3bc8f89fe494a4755c188be354add4e8b1e7b188"
    assert controller.DSH_TAG == "dsh-v0.1.0-rc.7"
    assert controller.CODEX_VERSION == "codex-cli 0.147.0"
    assert intervention_c_requests()[2]["params"]["input"] == controller.intervention_b_requests()[2]["params"]["input"]
    if diff:
        assert diff["prompt_sha256"] if "prompt_sha256" in diff else True


def test_b_is_consumed_and_c_has_independent_marker_contract():
    assert (PREDECESSOR_B / "live_canary_consumed.marker").is_file()
    auth = json.loads((ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_sandbox_policy_ownership_forensics_authorization_v0/authorization.json").read_text())
    marker = auth["first_exposure"]["consumption_marker"]
    assert auth["predecessor"]["consumed"] is True
    assert marker["independent_from_b"] is True
    assert marker["write_immediately_before_product_invocation"] is True
    assert marker["irrevocable"] is True
    assert marker["no_retry_after_write"] is True


def test_classification_and_authority_are_closed():
    auth = json.loads((ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_sandbox_policy_ownership_forensics_authorization_v0/authorization.json").read_text())
    assert auth["classifications"] == ["INTERVENTION_PASS", "SAME_READ_ONLY_FAILURE", "DIFFERENT_FAILURE", "INCONCLUSIVE_INFRA", "PRELIVE_BLOCKED"]
    ceiling = auth["governance_ceiling"]
    assert all(value is False for value in ceiling.values() if isinstance(value, bool))
    assert ceiling["scientific"] == "NONE"
    assert ceiling["qnty_runtime"] == "NONE"
    assert ceiling["trading"] == "NONE"
    assert ceiling["capital"] == "NONE"
