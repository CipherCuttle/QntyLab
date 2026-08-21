from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from qntylab.dsh_stage_a_v1_hard_orchestration import (
    CLAUDE_TOOL,
    CODEX_TOOL,
    CHILD_INFRA_RETRIES,
    MAX_PARENT_REQUEST_ATTEMPTS,
    MAX_RETRIES,
    PARENT_MAX_SPEND_USD,
    PARENT_MODEL,
    AuthorityState,
    AuthorizationDenied,
    ChildLifecycle,
    HardOrchestrationController,
    ReviewValidationError,
    count_structured_tool_invocations,
    dispatch_authorized_child,
    validate_review_result,
)


def review(*, critical: bool = False) -> dict:
    return {
        "critical": [{"id": "C-1", "summary": "closure blocker"}] if critical else [],
        "high": [],
        "medium": [],
        "low": [],
        "closure_blocking": critical,
        "summary": "hostile review result",
    }


def prepared(tmp_path: Path) -> HardOrchestrationController:
    controller = HardOrchestrationController(tmp_path / "authority.json")
    controller.prepare()
    return controller


def test_initial_codex_is_allowed_once_and_second_call_while_running_is_denied(tmp_path):
    controller = prepared(tmp_path)
    grant = controller.pre_dispatch_authorize(CODEX_TOOL)
    assert grant.role == "codex_initial"
    assert controller.state == AuthorityState.IMPLEMENT_RUNNING
    with pytest.raises(AuthorizationDenied):
        controller.pre_dispatch_authorize(CODEX_TOOL)


def test_codex_after_completion_before_claude_and_claude_before_codex_completion_are_denied(tmp_path):
    controller = prepared(tmp_path)
    grant = controller.pre_dispatch_authorize(CODEX_TOOL)
    with pytest.raises(AuthorizationDenied):
        controller.pre_dispatch_authorize(CLAUDE_TOOL)
    controller.complete_child(grant)
    with pytest.raises(AuthorizationDenied):
        controller.pre_dispatch_authorize(CODEX_TOOL)
    assert controller.state == AuthorityState.TEST_REQUIRED


def test_initial_claude_is_allowed_once_only_in_review_required(tmp_path):
    controller = prepared(tmp_path)
    with pytest.raises(AuthorizationDenied):
        controller.pre_dispatch_authorize(CLAUDE_TOOL)
    grant = controller.pre_dispatch_authorize(CODEX_TOOL)
    controller.complete_child(grant)
    controller.record_driver_tests(passed=True)
    review_grant = controller.pre_dispatch_authorize(CLAUDE_TOOL)
    assert review_grant.role == "claude_initial"
    with pytest.raises(AuthorizationDenied):
        controller.pre_dispatch_authorize(CLAUDE_TOOL)


def test_no_critical_high_finding_has_no_repair_authority_and_pass_is_terminal(tmp_path):
    controller = prepared(tmp_path)
    codex = controller.pre_dispatch_authorize(CODEX_TOOL)
    controller.complete_child(codex)
    controller.record_driver_tests(passed=True)
    claude = controller.pre_dispatch_authorize(CLAUDE_TOOL)
    controller.complete_child(claude, review_result=review())
    assert controller.state == AuthorityState.PASS
    with pytest.raises(AuthorizationDenied):
        controller.pre_dispatch_authorize(CODEX_TOOL)
    controller.seal_pass()
    assert controller.state == AuthorityState.TERMINAL
    with pytest.raises(AuthorizationDenied):
        controller.pre_dispatch_authorize(CLAUDE_TOOL)


def test_repair_requires_validated_claude_critical_high_and_rereview_requires_retest(tmp_path):
    controller = prepared(tmp_path)
    codex = controller.pre_dispatch_authorize(CODEX_TOOL)
    controller.complete_child(codex)
    controller.record_driver_tests(passed=False)
    claude = controller.pre_dispatch_authorize(CLAUDE_TOOL)
    controller.complete_child(claude, review_result=review(critical=True))
    assert controller.state == AuthorityState.REPAIR_REQUIRED
    repair = controller.pre_dispatch_authorize(CODEX_TOOL)
    controller.complete_child(repair)
    with pytest.raises(AuthorizationDenied):
        controller.pre_dispatch_authorize(CLAUDE_TOOL)
    controller.record_driver_tests(passed=True, retest=True)
    rereview = controller.pre_dispatch_authorize(CLAUDE_TOOL)
    controller.complete_child(rereview, review_result=review())
    assert controller.snapshot()["terminal_outcome"] == "PASS_AFTER_BOUNDED_REPAIR"
    assert controller.state == AuthorityState.TERMINAL


@pytest.mark.parametrize(
    ("retest_passed", "rereview_critical", "expected"),
    [
        (False, False, "FAIL_IMPLEMENTATION"),
        (False, True, "FAIL_IMPLEMENTATION"),
        (True, True, "FAIL_REVIEW"),
        (True, False, "PASS_AFTER_BOUNDED_REPAIR"),
    ],
)
def test_rereview_cannot_turn_failed_retest_into_pass(tmp_path, retest_passed, rereview_critical, expected):
    controller = prepared(tmp_path)
    codex = controller.pre_dispatch_authorize(CODEX_TOOL)
    controller.complete_child(codex)
    controller.record_driver_tests(passed=False)
    claude = controller.pre_dispatch_authorize(CLAUDE_TOOL)
    controller.complete_child(claude, review_result=review(critical=True))
    repair = controller.pre_dispatch_authorize(CODEX_TOOL)
    controller.complete_child(repair)
    controller.record_driver_tests(passed=retest_passed, retest=True)
    rereview = controller.pre_dispatch_authorize(CLAUDE_TOOL)
    controller.complete_child(rereview, review_result=review(critical=rereview_critical))
    assert controller.snapshot()["terminal_outcome"] == expected


@pytest.mark.parametrize(
    "tool_name",
    [
        "subagent",
        "subagent_fork",
        "workflow",
        "ralph",
        "subagent_codex_v1",
        "tool-subagent-codex",
    ],
)
def test_generic_fork_and_alias_bypasses_fail_closed(tmp_path, tool_name):
    controller = prepared(tmp_path)
    with pytest.raises(AuthorizationDenied):
        controller.pre_dispatch_authorize(tool_name)


def test_alternate_delegation_routes_are_denied_before_any_provider_callable(tmp_path):
    controller = prepared(tmp_path)
    alternate_names = ("subagent", "subagent_fork", "workflow", "ralph")
    for name in alternate_names:
        with pytest.raises(AuthorizationDenied):
            dispatch_authorized_child(controller, name, lambda _grant: pytest.fail("alternate route executed"))

    codex = controller.pre_dispatch_authorize(CODEX_TOOL)
    for name in alternate_names:
        with pytest.raises(AuthorizationDenied):
            dispatch_authorized_child(controller, name, lambda _grant: pytest.fail("alternate route executed"))
    controller.complete_child(codex)
    controller.record_driver_tests(passed=True)
    claude = controller.pre_dispatch_authorize(CLAUDE_TOOL)
    for name in alternate_names:
        with pytest.raises(AuthorizationDenied):
            dispatch_authorized_child(controller, name, lambda _grant: pytest.fail("alternate route executed"))
    controller.complete_child(claude, review_result=review())
    controller.seal_pass()
    for name in alternate_names:
        with pytest.raises(AuthorizationDenied):
            dispatch_authorized_child(controller, name, lambda _grant: pytest.fail("alternate route executed"))


def test_malformed_review_blocks_child_infra_and_grants_no_repair(tmp_path):
    controller = prepared(tmp_path)
    codex = controller.pre_dispatch_authorize(CODEX_TOOL)
    controller.complete_child(codex)
    controller.record_driver_tests(passed=True)
    claude = controller.pre_dispatch_authorize(CLAUDE_TOOL)
    with pytest.raises(ReviewValidationError):
        controller.complete_child(claude, review_result={"closure_blocking": True})
    assert controller.state == AuthorityState.BLOCK_CHILD_INFRA
    with pytest.raises(AuthorizationDenied):
        controller.pre_dispatch_authorize(CODEX_TOOL)


def test_timeout_consumes_budget_and_does_not_retry(tmp_path):
    controller = prepared(tmp_path)
    grant = controller.pre_dispatch_authorize(CODEX_TOOL)
    controller.complete_child(grant, status=ChildLifecycle.CHILD_TIMEOUT)
    assert controller.state == AuthorityState.BLOCK_CHILD_INFRA
    with pytest.raises(AuthorizationDenied):
        controller.pre_dispatch_authorize(CODEX_TOOL)


def test_structural_parser_ignores_catalog_reasoning_prompt_and_stream_text():
    events = [
        {"type": "tool/schema", "name": "subagent_fork"},
        {"type": "catalog", "text": "subagent_fork"},
        {"type": "reasoning", "text": "subagent_fork"},
        {"type": "prompt", "text": "subagent_fork"},
        {"type": "stream", "text": "subagent_fork"},
        {"type": "tool/call", "name": "subagent_codex"},
    ]
    assert count_structured_tool_invocations(events, "subagent_fork") == 0
    assert count_structured_tool_invocations(events, "subagent_codex") == 1


def test_structural_parser_reads_jsonl_without_substring_matching():
    lines = [
        json.dumps({"type": "stream", "text": '"name":"subagent_fork"'}),
        json.dumps({"type": "tool/call", "name": "subagent_claude_code"}),
    ]
    assert count_structured_tool_invocations(lines, "subagent_fork") == 0
    assert count_structured_tool_invocations(lines, CLAUDE_TOOL) == 1


def test_crash_replay_preserves_started_budget_and_completion_checkpoint(tmp_path):
    path = tmp_path / "authority.json"
    controller = HardOrchestrationController(path)
    controller.prepare()
    grant = controller.pre_dispatch_authorize(CODEX_TOOL)
    restarted = HardOrchestrationController(path)
    with pytest.raises(AuthorizationDenied):
        restarted.pre_dispatch_authorize(CODEX_TOOL)
    restarted.complete_child(grant)
    restored = HardOrchestrationController(path)
    assert restored.state == AuthorityState.TEST_REQUIRED
    restored.record_driver_tests(passed=True)
    claude = restored.pre_dispatch_authorize(CLAUDE_TOOL)
    restored.complete_child(claude, review_result=review(critical=True))
    restored_again = HardOrchestrationController(path)
    assert restored_again.state == AuthorityState.REPAIR_REQUIRED
    with pytest.raises(AuthorizationDenied):
        restored_again.pre_dispatch_authorize(CLAUDE_TOOL)


def test_duplicate_completion_and_terminal_replay_cannot_replenish_or_resurrect(tmp_path):
    controller = prepared(tmp_path)
    grant = controller.pre_dispatch_authorize(CODEX_TOOL)
    controller.complete_child(grant)
    with pytest.raises(AuthorizationDenied):
        controller.complete_child(grant)
    controller.record_driver_tests(passed=True)
    claude = controller.pre_dispatch_authorize(CLAUDE_TOOL)
    controller.complete_child(claude, review_result=review())
    controller.seal_pass()
    before = controller.snapshot()
    with pytest.raises(AuthorizationDenied):
        controller.pre_dispatch_authorize(CODEX_TOOL)
    assert controller.snapshot() == before


def test_authorization_and_provider_start_are_serialized(tmp_path):
    controller = prepared(tmp_path)
    results = []

    def reserve():
        try:
            results.append(controller.pre_dispatch_authorize(CODEX_TOOL))
        except AuthorizationDenied:
            results.append(None)

    threads = [threading.Thread(target=reserve) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(result is not None for result in results) == 1
    assert controller.snapshot()["budgets"]["codex_initial"] is True


def test_provider_wrapper_never_invokes_denied_child_and_consumes_provider_failure(tmp_path):
    controller = prepared(tmp_path)
    calls = []
    with pytest.raises(AuthorizationDenied):
        dispatch_authorized_child(controller, CLAUDE_TOOL, lambda grant: calls.append(grant))
    assert calls == []
    result = dispatch_authorized_child(controller, CODEX_TOOL, lambda grant: calls.append(grant.token) or "done")
    assert result == "done"
    assert controller.state == AuthorityState.TEST_REQUIRED

    controller.record_driver_tests(passed=True)
    with pytest.raises(RuntimeError):
        dispatch_authorized_child(controller, CLAUDE_TOOL, lambda grant: (_ for _ in ()).throw(RuntimeError("provider")))
    assert controller.state == AuthorityState.BLOCK_CHILD_INFRA


def test_review_schema_requires_critical_high_to_match_closure_flag():
    valid = review(critical=True)
    assert validate_review_result(valid)["closure_blocking"] is True
    invalid = {**valid, "closure_blocking": False}
    with pytest.raises(ReviewValidationError):
        validate_review_result(invalid)


def test_later_execution_controls_remain_frozen_and_authorization_spend_is_zero():
    assert PARENT_MODEL == "gpt-5-mini"
    assert MAX_RETRIES == 0
    assert CHILD_INFRA_RETRIES == 0
    assert MAX_PARENT_REQUEST_ATTEMPTS == 8
    assert PARENT_MAX_SPEND_USD == 1.00


def test_frozen_fixture_is_referenced_without_modification():
    fixture = Path("experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_multi_agent_orchestration_stage_a_authorization_v0/fixture")
    assert (fixture / "TASK.md").is_file()
    assert "STAGE_A_BOUNDED_RETRY_V0" in (fixture / "TASK.md").read_text(encoding="utf-8")
    assert "NotImplementedError" in (fixture / "retry.py").read_text(encoding="utf-8")
