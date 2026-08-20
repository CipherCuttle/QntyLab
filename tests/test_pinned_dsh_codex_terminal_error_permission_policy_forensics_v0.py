import hashlib
import json
from pathlib import Path

from qntylab.pinned_dsh_codex_terminal_error_permission_policy_forensics_v0 import (
    AFTER,
    BEFORE,
    PROMPT,
    classify_live,
    historical_requests,
    intervention_b_requests,
    request_diff_artifact,
    semantic_request_delta,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_terminal_error_permission_policy_forensics_v0"


def test_fake_request_delta_is_exactly_one_semantic_change():
    artifact = request_diff_artifact()
    assert artifact["request_delta"] == [{
        "method": "thread/start",
        "path": "params.approvalPolicy",
        "before": "<ABSENT>",
        "after": "never",
    }]
    assert artifact["request_delta_count"] == 1
    assert artifact["request_delta_pass"] is True
    assert artifact["historical_shape"][1]["params"] == {"cwd": "<workspace>", "ephemeral": True}
    assert artifact["intervention_b_shape"][1]["params"]["approvalPolicy"] == "never"


def test_every_non_intervention_wire_and_prompt_field_matches():
    before = historical_requests()
    after = intervention_b_requests()
    assert before[0] == after[0]
    assert before[2] == after[2]
    assert before[2]["params"]["input"][0]["text"] == PROMPT
    assert before[2]["params"]["input"][0]["text_elements"] == []
    assert BEFORE == b"BEFORE\n"
    assert AFTER == b"AFTER\n"


def test_fake_captures_preserve_effective_policy_without_inventing_sandbox():
    artifact = request_diff_artifact()
    a_thread = artifact["fake_historical_capture"]["events"][3]
    b_thread = artifact["fake_intervention_b_capture"]["events"][3]
    assert a_thread["effective"]["approvalPolicy"] == "on-request"
    assert b_thread["effective"]["approvalPolicy"] == "never"
    assert a_thread["effective"]["sandbox"] is None
    assert b_thread["effective"]["sandbox"] is None
    assert a_thread["effective"]["runtimeWorkspaceRoots"] == []
    assert b_thread["effective"]["runtimeWorkspaceRoots"] == []


def test_classification_is_closed_and_fail_closed():
    base = {"prelive_gate": "PASS", "identity_gate": "PASS", "credential_gate": "PASS", "profile_a_config_mutated": False, "timeout": False}
    assert classify_live({**base, "fixture_before_class": "BEFORE", "fixture_after_class": "AFTER", "changed_paths": ["fixture.txt"], "unauthorized_changed_paths": [], "terminal_status": "completed"}) == "INTERVENTION_PASS"
    assert classify_live({**base, "fixture_before_class": "BEFORE", "fixture_after_class": "BEFORE", "changed_paths": [], "unauthorized_changed_paths": [], "terminal_status": "failed", "terminal_error_category": "same_as_historical_stopReason_error"}) == "SAME_FAILURE"
    assert classify_live({**base, "fixture_before_class": "BEFORE", "fixture_after_class": "BEFORE", "changed_paths": [], "unauthorized_changed_paths": [], "terminal_status": "completed", "turn_terminal_observed": True}) == "DIFFERENT_FAILURE"
    assert classify_live({**base, "fixture_before_class": "BEFORE", "fixture_after_class": "BEFORE", "changed_paths": [], "unauthorized_changed_paths": [], "terminal_status": "failed", "timeout": True}) == "INCONCLUSIVE_INFRA"
    assert classify_live({**base, "prelive_gate": "FAIL"}) == "PRELIVE_BLOCKED"


def test_patch_and_identity_contract_are_pinned():
    contract = json.loads((ARTIFACT / "implementation_contract.json").read_text(encoding="utf-8"))
    assert contract["intervention"]["semantic_delta_count"] == 1
    assert contract["product_identity"]["dsh_commit"] == "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
    assert contract["product_identity"]["dsh_tree"] == "3bc8f89fe494a4755c188be354add4e8b1e7b188"
    assert contract["product_identity"]["codex_version"] == "codex-cli 0.147.0"
    assert hashlib.sha256((ARTIFACT / "intervention.patch").read_bytes()).hexdigest()


def test_no_historical_or_secret_material_is_in_new_contract():
    text = "\n".join(path.read_text(encoding="utf-8") for path in ARTIFACT.glob("*.json"))
    assert "OPENAI_API_KEY_VALUE" not in text
    assert "Bearer ey" not in text
    assert "answer_key" not in text.lower()
