import json
from pathlib import Path

from qntylab.pinned_dsh_codex_terminal_error_permission_policy_forensics_v0 import (
    API_KEY_NAMES,
    credential_gate_status,
    credential_gate_status_from_environment,
    credential_presence,
)


ROOT = Path(__file__).resolve().parents[1]
CONTINUATION = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_permission_policy_canary_controller_gate_repair_and_continuation_v0"
PREDECESSOR = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_terminal_error_permission_policy_forensics_v0"


def _presence(*present: str) -> dict[str, bool]:
    return {name: name in present for name in API_KEY_NAMES}


def test_all_absent_is_allowed_and_old_truthiness_bug_is_repaired():
    presence = credential_presence({})
    assert presence == _presence()
    assert bool(presence) is True
    assert credential_gate_status(presence) == "PASS"


def test_each_credential_and_combinations_block():
    for name in API_KEY_NAMES:
        assert credential_gate_status(_presence(name)) == "BLOCK"
    assert credential_gate_status(_presence(API_KEY_NAMES[0], API_KEY_NAMES[1])) == "BLOCK"
    assert credential_gate_status(_presence(*API_KEY_NAMES)) == "BLOCK"


def test_malformed_presence_state_fails_closed():
    missing = _presence()
    del missing[API_KEY_NAMES[0]]
    assert credential_gate_status(missing) == "BLOCK_MALFORMED"
    non_boolean = _presence()
    non_boolean[API_KEY_NAMES[0]] = "false"
    assert credential_gate_status(non_boolean) == "BLOCK_MALFORMED"
    unexpected = _presence()
    unexpected["UNEXPECTED_CREDENTIAL"] = False
    assert credential_gate_status(unexpected) == "BLOCK_MALFORMED"


def test_repeated_evaluation_is_deterministic_and_environment_values_are_not_read():
    class PresenceOnlyEnvironment(dict):
        def __getitem__(self, key):
            raise AssertionError("credential value access is forbidden")

    environ = PresenceOnlyEnvironment({"OPENAI_API_KEY": "dummy-secret"})
    first = credential_presence(environ)
    second = credential_presence(environ)
    assert first == second == _presence("OPENAI_API_KEY")
    assert credential_gate_status_from_environment(environ) == "BLOCK"
    sanitized = json.dumps({"presence": first, "decision": credential_gate_status(first)}, sort_keys=True)
    assert "dummy-secret" not in sanitized


def test_continuation_reuses_exact_frozen_treatment_and_pins():
    predecessor = json.loads((PREDECESSOR / "fake_app_server_request_diff.json").read_text(encoding="utf-8"))
    assert predecessor["request_delta_count"] == 1
    assert predecessor["request_delta"] == [{
        "method": "thread/start",
        "path": "params.approvalPolicy",
        "before": "<ABSENT>",
        "after": "never",
    }]
    assert predecessor["dsh_identity"]["commit"] == "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
    assert predecessor["dsh_identity"]["tree"] == "3bc8f89fe494a4755c188be354add4e8b1e7b188"
    assert predecessor["dsh_identity"]["tag"] == "dsh-v0.1.0-rc.7"
    assert predecessor["codex_identity"]["version"] == "codex-cli 0.147.0"


def test_predecessor_artifacts_and_marker_are_not_reused_for_consumption():
    assert not (PREDECESSOR / "live_canary_consumed.marker").exists()
    assert not (CONTINUATION / "live_canary_consumed.marker").exists()
