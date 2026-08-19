from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from qntylab.subscription_backed_codex_app_server_write_path_diagnostic_v0 import (
    FIXTURE_AFTER_BYTES,
    FIXTURE_BEFORE_BYTES,
    FIXTURE_NAME,
    NO_TOOL_PROMPT,
    TERMINAL_CLASSES,
    WRITE_PROMPT,
    TraceRecorder,
    build_workspace,
    classify_fixture_bytes,
    classify_route,
    destroy_workspace,
    first_divergence,
    fixture_state,
    no_tool_control_passed,
    route_passed,
    run_app_server_route,
    run_d0_host_control,
)

FAKE = Path(__file__).parent / "fixtures" / "fake_codex_app_server_v0.py"


def fake_argv(scenario: str) -> list[str]:
    return [sys.executable, str(FAKE), scenario]


def run_scenario(scenario: str, workspace: Path, *, prompt: str = WRITE_PROMPT, **kwargs) -> dict:
    recorder = TraceRecorder(route=scenario)
    receipt = run_app_server_route(
        route=scenario,
        workspace=workspace,
        prompt=prompt,
        recorder=recorder,
        argv=fake_argv(scenario),
        **kwargs,
    )
    receipt["_recorder"] = recorder
    return receipt


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    return build_workspace(tmp_path / "ws")


# -- fixture contract -----------------------------------------------------


def test_fixture_bytes_are_exact_and_classified():
    assert FIXTURE_BEFORE_BYTES == b"BEFORE\n"
    assert FIXTURE_AFTER_BYTES == b"AFTER\n"
    assert classify_fixture_bytes(b"BEFORE\n") == "BEFORE"
    assert classify_fixture_bytes(b"BEFORE") == "BEFORE"
    assert classify_fixture_bytes(b"AFTER\n") == "AFTER"
    assert classify_fixture_bytes(b"AFTER") == "AFTER"
    assert classify_fixture_bytes(b"after") == "OTHER"
    assert classify_fixture_bytes(b"AFTER\n\n") == "OTHER"
    assert classify_fixture_bytes(b"") == "OTHER"


def test_build_workspace_is_a_fresh_git_repo_and_refuses_reuse(tmp_path: Path):
    root = build_workspace(tmp_path / "ws")
    assert (root / FIXTURE_NAME).read_bytes() == FIXTURE_BEFORE_BYTES
    assert (root / ".git").is_dir()
    assert fixture_state(root)["class"] == "BEFORE"
    with pytest.raises(Exception):
        build_workspace(root)
    destroy_workspace(root)
    assert not root.exists()


def test_d0_host_control_passes_and_destroys_its_workspace(tmp_path: Path):
    result = run_d0_host_control(tmp_path / "d0")
    assert result["passed"] is True
    assert result["fixture_before"]["class"] == "BEFORE"
    assert result["fixture_after"]["class"] == "AFTER"
    assert result["changed_paths"] == [FIXTURE_NAME]
    assert result["workspace_destroyed"] is True


# -- T1 JSON-RPC sequencing ----------------------------------------------


def test_t1_full_rpc_sequence_is_driven_and_write_is_observed(workspace: Path):
    receipt = run_scenario("write", workspace)
    methods = [event.method for event in receipt["_recorder"].events if event.kind == "REQUEST"]
    assert methods == ["initialize", "thread/start", "turn/start"]
    notifications = [event.method for event in receipt["_recorder"].events if event.kind == "NOTIFICATION"]
    assert "initialized" in notifications
    assert "turn/started" in notifications
    assert "turn/completed" in notifications
    assert any(m in notifications for m in ("item/started", "item/completed"))
    assert receipt["turn"]["status"] == "completed"
    assert receipt["classification"]["terminal_class"] == "COMPLETED_WITH_WRITE"
    assert receipt["filesystem"]["effect_observed"] is True
    assert route_passed(receipt) is True


def test_t1_handshake_records_effective_codex_home(workspace: Path, monkeypatch):
    monkeypatch.setenv("IRRELEVANT_MARKER", "1")
    receipt = run_scenario("write", workspace, codex_home="/home/swirky/.codex")
    assert receipt["handshake"]["effective_codex_home"] == "/home/swirky/.codex"


# -- T2 timeout -----------------------------------------------------------


def test_t2_stalled_turn_is_a_timeout_and_never_a_denial(workspace: Path):
    receipt = run_scenario("stall", workspace, turn_timeout_seconds=2.0)
    classification = receipt["classification"]
    assert classification["terminal_class"] == "TURN_TIMEOUT"
    assert classification["terminal_class"] not in {"COMPLETED_WITH_WRITE", "COMPLETED_NO_WRITE"}
    assert "WRITE_DENIED" not in classification["mechanism"]
    assert "WRITE_CAPABILITY_ABSENT" not in classification["mechanism"]
    assert receipt["timeout_policy"]["timed_out"] is True
    assert receipt["timeout_policy"]["timeout_stage"] == "TURN"
    assert receipt["turn"]["terminal_observed"] is False
    assert route_passed(receipt) is False


def test_t2_timeout_still_disposes_the_child_process(workspace: Path):
    receipt = run_scenario("stall", workspace, turn_timeout_seconds=2.0)
    assert receipt["process"]["disposed"] is True
    assert receipt["process"]["termination"] in {"SIGTERM", "SIGKILL"}


# -- T3 approval / permission visibility ----------------------------------


def test_t3_file_change_approval_is_recorded_and_answered_not_swallowed(workspace: Path):
    receipt = run_scenario("approval_then_no_write", workspace)
    assert len(receipt["approval_requests"]) == 1
    event = receipt["approval_requests"][0]
    assert event["approval_class"] == "FILE_CHANGE"
    assert event["decision_class"] == "DECLINE_UNATTENDED"
    server_requests = [e for e in receipt["_recorder"].events if e.kind == "SERVER_REQUEST"]
    answers = [e for e in receipt["_recorder"].events if e.kind == "SERVER_RESPONSE"]
    assert len(server_requests) == 1 and len(answers) == 1
    assert receipt["classification"]["terminal_class"] == "APPROVAL_DENIED"
    assert route_passed(receipt) is False


def test_t3_permission_escalation_grants_nothing(workspace: Path):
    receipt = run_scenario("permission_then_no_write", workspace)
    event = receipt["approval_requests"][0]
    assert event["approval_class"] == "PERMISSIONS"
    assert event["decision_class"] == "GRANT_NOTHING_UNATTENDED"
    assert receipt["classification"]["terminal_class"] == "PERMISSION_DENIED"


# -- T4 terminal distinction ----------------------------------------------


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("write", "COMPLETED_WITH_WRITE"),
        ("stall", "TURN_TIMEOUT"),
        ("approval_then_no_write", "APPROVAL_DENIED"),
        ("permission_then_no_write", "PERMISSION_DENIED"),
        ("attempt_without_effect", "WRITE_ATTEMPT_OBSERVED"),
        ("prose_lies_about_write", "COMPLETED_NO_WRITE"),
        ("turn_failed", "TURN_FAILED"),
        ("auth_failure", "AUTH_FAILURE"),
        ("initialize_reject", "STARTUP_FAILURE"),
        ("thread_start_reject", "STARTUP_FAILURE"),
    ],
)
def test_t4_terminal_classes_are_distinguished(scenario, expected, tmp_path: Path):
    ws = build_workspace(tmp_path / scenario)
    receipt = run_scenario(scenario, ws, turn_timeout_seconds=2.0, handshake_timeout_seconds=10.0)
    assert receipt["classification"]["terminal_class"] == expected
    assert receipt["classification"]["terminal_class"] in TERMINAL_CLASSES


def test_t4_protocol_rejection_names_the_stage(tmp_path: Path):
    ws = build_workspace(tmp_path / "reject")
    receipt = run_scenario("thread_start_reject", ws, handshake_timeout_seconds=10.0)
    assert receipt["protocol_failure_stage"] == "THREAD_START"
    assert receipt["classification"]["mechanism"] == "PROTOCOL_REJECTED_AT_THREAD_START"


def test_a_read_only_command_is_not_counted_as_a_write_attempt(workspace: Path):
    from qntylab.subscription_backed_codex_app_server_write_path_diagnostic_v0 import (
        _command_execution_observed,
        _write_attempt_observed,
    )

    items = [{"item_type": "commandExecution", "command_program": "ls", "exit_code": 0}]
    assert _write_attempt_observed(items) is False
    assert _command_execution_observed(items) is True
    assert _write_attempt_observed([{"item_type": "fileChange"}]) is True


def test_startup_failure_yields_a_receipt_instead_of_an_exception(workspace: Path):
    recorder = TraceRecorder(route="missing-binary")
    receipt = run_app_server_route(
        route="missing-binary",
        workspace=workspace,
        prompt=WRITE_PROMPT,
        recorder=recorder,
        argv=["/nonexistent/codex-binary-for-diagnostic"],
        handshake_timeout_seconds=5.0,
        turn_timeout_seconds=5.0,
    )
    assert receipt["classification"]["terminal_class"] == "STARTUP_FAILURE"
    assert receipt["startup_error"]
    assert receipt["filesystem"]["changed_paths"] == []


def test_credential_shaped_error_text_is_scrubbed_before_recording():
    from qntylab.subscription_backed_codex_app_server_write_path_diagnostic_v0 import _truncate

    scrubbed = _truncate("failed with token sk-abcdefghijklmnop and more")
    assert "sk-abcdefghijklmnop" not in scrubbed
    assert "[REDACTED]" in scrubbed
    assert _truncate("plain short message") == "plain short message"


def test_t4_classifier_never_invents_a_class_without_evidence():
    empty = classify_route({"startup_ok": True})
    assert empty["terminal_class"] == "WRITE_NOT_ATTEMPTED"
    assert empty["auth_failure_inferred_from_error_text"] is False
    timeout_only = classify_route({"startup_ok": True, "timed_out": True})
    assert timeout_only["terminal_class"] == "TURN_TIMEOUT"


# -- T5 workspace machine truth -------------------------------------------


def test_t5_assistant_prose_can_never_produce_a_pass(workspace: Path):
    receipt = run_scenario("prose_lies_about_write", workspace)
    assert receipt["turn"]["status"] == "completed"
    assert receipt["agent_messages"], "the fake asserted a write in prose"
    assert receipt["filesystem"]["fixture_after"]["class"] == "BEFORE"
    assert receipt["filesystem"]["effect_observed"] is False
    assert receipt["classification"]["terminal_class"] == "COMPLETED_NO_WRITE"
    assert route_passed(receipt) is False


def test_t5_pass_requires_only_the_fixture_to_change(workspace: Path):
    receipt = run_scenario("write", workspace)
    assert receipt["filesystem"]["changed_paths"] == [FIXTURE_NAME]
    receipt["filesystem"]["changed_paths"] = [FIXTURE_NAME, "stray.txt"]
    assert route_passed(receipt) is False


def test_t5_agent_prose_is_stored_only_as_a_digest(workspace: Path):
    receipt = run_scenario("prose_lies_about_write", workspace)
    message = receipt["agent_messages"][0]
    assert set(message) == {"text_sha256", "text_length", "matches_no_tool_control"}
    blob = json.dumps(receipt, default=str)
    assert "I have replaced fixture.txt" not in blob


# -- T6 exact effective request -------------------------------------------


def test_t6_requests_carry_the_pinned_explicit_policy_fields(workspace: Path, tmp_path, monkeypatch):
    observed = tmp_path / "observed.jsonl"
    monkeypatch.setenv("FAKE_APP_SERVER_OBSERVED", str(observed))
    run_scenario("write", workspace)
    rows = [json.loads(line) for line in observed.read_text().splitlines()]
    by_method = {row["method"]: row["params"] for row in rows}

    thread = by_method["thread/start"]
    assert thread["cwd"] == str(workspace)
    assert thread["ephemeral"] is True
    assert thread["approvalPolicy"] == "never"
    assert thread["sandbox"] == "workspace-write"

    turn = by_method["turn/start"]
    assert turn["cwd"] == str(workspace)
    assert turn["approvalPolicy"] == "never"
    assert turn["sandboxPolicy"] == {
        "type": "workspaceWrite",
        "writableRoots": [str(workspace)],
        "networkAccess": False,
    }
    assert turn["input"] == [{"type": "text", "text": WRITE_PROMPT}]


def test_t6_effective_policy_is_read_back_and_not_assumed(workspace: Path):
    receipt = run_scenario("write", workspace, codex_home="/home/swirky/.codex")
    effective = receipt["effective_policy"]
    assert effective["effective_approval_policy"] == "never"
    assert effective["effective_sandbox_class"] == "workspaceWrite"
    assert effective["effective_writable_roots"] == [str(workspace)]
    assert effective["effective_cwd"] == str(workspace)
    assert effective["thread_ephemeral"] is True

    parity = receipt["policy_parity"]
    assert parity["all_match"] is True
    assert parity["codex_home_matches"] is True
    assert parity["cwd_matches"] is True
    assert parity["approval_policy_matches"] is True
    assert parity["sandbox_class_matches"] is True
    assert parity["writable_root_covers_workspace"] is True


def test_t6_declared_policy_is_derived_from_the_request_actually_sent(workspace: Path):
    receipt = run_scenario("write", workspace)
    declared = receipt["declared_policy"]
    assert declared["thread_start_keys"] == ["approvalPolicy", "cwd", "ephemeral", "sandbox"]
    assert declared["turn_start_keys"] == [
        "approvalPolicy", "cwd", "input", "sandboxPolicy", "threadId",
    ]
    assert declared["writable_roots"] == [str(workspace)]
    assert declared["network_access"] is False


def test_t6_effective_policy_downgrade_is_visible_in_the_receipt(tmp_path: Path):
    ws = build_workspace(tmp_path / "downgrade")
    receipt = run_scenario("effective_policy_downgrade", ws, turn_timeout_seconds=5.0)
    assert receipt["declared_policy"]["thread_sandbox_mode"] == "workspace-write"
    assert receipt["effective_policy"]["effective_sandbox_class"] == "readOnly"
    # Declared parity must never be reported as effective parity.
    assert receipt["policy_parity"]["sandbox_class_matches"] is False
    assert receipt["policy_parity"]["all_match"] is False


def test_wrong_codex_home_is_detected_rather_than_assumed(workspace: Path):
    receipt = run_scenario("write", workspace, codex_home="/home/swirky/.codex-pro2")
    assert receipt["handshake"]["effective_codex_home"] == "/home/swirky/.codex-pro2"
    assert receipt["policy_parity"]["codex_home_matches"] is True
    receipt["policy_parity"]["codex_home_effective"] = "/somewhere/else"
    assert receipt["policy_parity"]["codex_home_requested"] == "/home/swirky/.codex-pro2"


# -- D1 control -----------------------------------------------------------


def test_d1_no_tool_control_requires_the_exact_answer_and_zero_mutation(workspace: Path):
    receipt = run_scenario("no_tool", workspace, prompt=NO_TOOL_PROMPT)
    assert no_tool_control_passed(receipt) is True
    assert receipt["filesystem"]["changed_paths"] == []
    assert receipt["agent_messages"][0]["matches_no_tool_control"] is True


def test_d1_control_fails_when_the_answer_differs(workspace: Path):
    receipt = run_scenario("prose_lies_about_write", workspace, prompt=NO_TOOL_PROMPT)
    assert no_tool_control_passed(receipt) is False


# -- ladder / sanitization ------------------------------------------------


def test_first_divergence_stops_at_the_first_failure():
    assert first_divergence({"D0": "PASS", "D1": "PASS", "D2": "FAIL"}) == "D2_RAW_APP_SERVER_WRITE"
    assert first_divergence({"D0": "PASS", "D1": "PASS", "D2": "PASS", "D3": "FAIL"}) == "D3_QNTY_NATIVE_BRIDGE"
    assert first_divergence({k: "PASS" for k in ("D0", "D1", "D2", "D3", "D4")}) == "NONE"
    assert first_divergence({"D0": "PASS", "D1": "INCONCLUSIVE_INFRA"}) == "INCONCLUSIVE_INFRA"
    assert first_divergence({}) == "UNKNOWN"


def test_first_divergence_never_claims_none_from_an_incomplete_ladder():
    # `NONE` asserts that every write path passed, so a skipped, missing, or
    # unrecognised stage must degrade to UNKNOWN rather than fail open.
    assert first_divergence({"D0": "PASS", "D2": "NOT_RUN_DUE_TO_EARLIER_DIVERGENCE"}) == "UNKNOWN"
    assert first_divergence({"D0": "PASS", "D1": "PASS", "D2": "PASS", "D3": "PASS"}) == "UNKNOWN"
    assert first_divergence({"D0": "PASS", "D1": "PASS", "D2": "PASS", "D3": "PASS", "D4": "?"}) == "UNKNOWN"


def test_api_key_gate_is_recorded_and_keys_are_removed(workspace: Path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-never-be-read")
    receipt = run_scenario("write", workspace)
    assert receipt["environment"]["api_key_presence"]["OPENAI_API_KEY"] is True
    assert "OPENAI_API_KEY" in receipt["environment"]["removed_names"]
    blob = json.dumps(receipt, default=str)
    assert "must-never-be-read" not in blob


def test_trace_records_parameter_key_names_not_values(workspace: Path, tmp_path: Path):
    receipt = run_scenario("write", workspace)
    recorder = receipt["_recorder"]
    request = next(e for e in recorder.events if e.kind == "REQUEST" and e.method == "turn/start")
    assert set(request.param_keys) == {"threadId", "cwd", "approvalPolicy", "sandboxPolicy", "input"}
    assert "prompt_sha256" in request.detail
    trace = tmp_path / "trace.jsonl"
    recorder.write_jsonl(trace, append=False)
    rows = [json.loads(line) for line in trace.read_text().splitlines()]
    assert rows and all("route" in row and "at" in row for row in rows)
    assert WRITE_PROMPT not in trace.read_text()


def test_unknown_server_requests_are_refused_not_ignored(workspace: Path):
    from qntylab.subscription_backed_codex_app_server_write_path_diagnostic_v0 import AppServerClient

    recorder = TraceRecorder(route="unit")
    client = AppServerClient(("true",), workspace, {}, recorder)
    result, detail = client._unattended_response("mcpServer/elicitation/request", {})
    assert result is None and detail["answer"] == "UNSUPPORTED"
    result, detail = client._unattended_response("currentTime/read", {"threadId": "t"})
    assert isinstance(result, dict) and "currentTimeAt" in result
    result, detail = client._unattended_response("execCommandApproval", {"command": ["bash", "-lc", "x"]})
    assert result == {"decision": {"denied": {"rejection": "unattended write-path diagnostic declines escalation"}}}
    assert detail["command_program"] == "bash"
