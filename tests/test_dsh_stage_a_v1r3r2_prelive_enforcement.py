from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

import pytest

from qntylab.dsh_stage_a_v1r3r2_prelive_enforcement import (
    CLAUDE_TOOL,
    CODEX_TOOL,
    MAX_INPUT_TOKEN_UPPER_BOUND,
    MAX_OUTPUT_TOKENS,
    PRICE_SCHEDULE_ID,
    ChildDenied,
    ChildState,
    EpisodeClaim,
    ParentBudgetGate,
    ParentDenied,
    ParentRequest,
    StageAChildController,
    ClaimBlocked,
)


def review(*, critical: bool = False, high: bool = False) -> dict[str, object]:
    return {
        "critical": [{"id": "C-01", "summary": "critical"}] if critical else [],
        "high": [{"id": "H-01", "summary": "high"}] if high else [],
        "medium": [],
        "low": [],
        "closure_blocking": critical or high,
        "summary": "hostile review",
    }


def parent_request(**overrides: object) -> ParentRequest:
    values: dict[str, object] = {
        "provider": "openai",
        "model": "gpt-5-mini",
        "agent_loop": True,
        "purpose": None,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "input_token_upper_bound": 100,
        "provider_internal_retries": 0,
    }
    values.update(overrides)
    return ParentRequest(**values)  # type: ignore[arg-type]


def test_child_clean_review_path_is_terminal_and_never_invokes_third_child(tmp_path: Path) -> None:
    controller = StageAChildController(tmp_path / "child.json")
    codex = controller.authorize(CODEX_TOOL, provider_name="codex")
    controller.complete(codex)
    claude = controller.authorize(CLAUDE_TOOL, provider_name="claude-code")
    controller.complete(claude, review_result=review())

    snapshot = controller.snapshot()
    assert snapshot["state"] == ChildState.AFTER_REVIEW_NO_C_H.value
    assert snapshot["terminal_outcome"] == "PASS_NO_CRITICAL_HIGH"
    assert snapshot["codex_calls_reserved"] == snapshot["claude_calls_reserved"] == 1
    with pytest.raises(ChildDenied):
        controller.authorize(CODEX_TOOL, provider_name="codex")
    with pytest.raises(ChildDenied):
        controller.authorize(CLAUDE_TOOL, provider_name="claude-code")


def test_child_repair_path_allows_exactly_two_of_each_and_then_terminal(tmp_path: Path) -> None:
    controller = StageAChildController(tmp_path / "child.json")
    initial = controller.authorize(CODEX_TOOL, provider_name="codex")
    controller.complete(initial)
    hostile = controller.authorize(CLAUDE_TOOL, provider_name="claude-code")
    controller.complete(hostile, review_result=review(high=True))
    repair = controller.authorize(CODEX_TOOL, provider_name="codex")
    controller.complete(repair)
    rereview = controller.authorize(CLAUDE_TOOL, provider_name="claude-code")
    controller.complete(rereview, review_result=review())

    snapshot = controller.snapshot()
    assert snapshot["state"] == ChildState.AFTER_REREVIEW.value
    assert snapshot["terminal_outcome"] == "PASS_AFTER_BOUNDED_REPAIR"
    assert snapshot["codex_calls_reserved"] == snapshot["claude_calls_reserved"] == 2
    with pytest.raises(ChildDenied):
        controller.authorize(CODEX_TOOL, provider_name="codex")
    with pytest.raises(ChildDenied):
        controller.authorize(CLAUDE_TOOL, provider_name="claude-code")


@pytest.mark.parametrize(
    ("tool", "provider", "background"),
    [
        (CLAUDE_TOOL, "claude-code", False),
        (CODEX_TOOL, "alternate-codex", False),
        ("subagent", "codex", False),
        ("subagent_fork", "codex", False),
        (CODEX_TOOL, "codex", True),
    ],
)
def test_wrong_first_transition_generic_alternate_and_background_routes_are_denied(
    tmp_path: Path, tool: str, provider: str, background: bool
) -> None:
    controller = StageAChildController(tmp_path / "child.json")
    with pytest.raises(ChildDenied):
        controller.authorize(tool, provider_name=provider, background=background)
    assert controller.snapshot()["codex_calls_reserved"] == 0
    assert controller.snapshot()["claude_calls_reserved"] == 0


def test_duplicate_initial_repair_without_findings_and_rereview_without_repair_are_denied(
    tmp_path: Path,
) -> None:
    controller = StageAChildController(tmp_path / "child.json")
    initial = controller.authorize(CODEX_TOOL, provider_name="codex")
    with pytest.raises(ChildDenied):
        controller.authorize(CODEX_TOOL, provider_name="codex")
    controller.complete(initial)
    with pytest.raises(ChildDenied):
        controller.authorize(CODEX_TOOL, provider_name="codex")
    hostile = controller.authorize(CLAUDE_TOOL, provider_name="claude-code")
    controller.complete(hostile, review_result=review())
    with pytest.raises(ChildDenied):
        controller.authorize(CODEX_TOOL, provider_name="codex")
    with pytest.raises(ChildDenied):
        controller.authorize(CLAUDE_TOOL, provider_name="claude-code")


def test_crash_after_child_reservation_consumes_transition_and_restart_fails_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "child.json"
    first = StageAChildController(path)
    first.authorize(CODEX_TOOL, provider_name="codex")

    restarted = StageAChildController(path)
    with pytest.raises(ChildDenied):
        restarted.authorize(CODEX_TOOL, provider_name="codex")
    with pytest.raises(ChildDenied):
        restarted.authorize(CLAUDE_TOOL, provider_name="claude-code")
    assert restarted.snapshot()["codex_calls_reserved"] == 1


def test_parent_attempt_nine_is_denied_without_a_ninth_reservation(tmp_path: Path) -> None:
    gate = ParentBudgetGate(tmp_path / "parent.json")
    for expected in range(1, 9):
        assert gate.reserve(parent_request()).attempt == expected
    with pytest.raises(ParentDenied, match="ATTEMPT_CEILING"):
        gate.reserve(parent_request())
    snapshot = gate.snapshot()
    assert snapshot["attempts_reserved"] == 8
    assert len(snapshot["reservations"]) == 8
    assert snapshot["denials"][-1]["attempt"] == 9


def test_parent_token_cap_route_retry_and_auxiliary_controls_fail_before_reservation(
    tmp_path: Path,
) -> None:
    gate = ParentBudgetGate(tmp_path / "parent.json")
    invalid = [
        parent_request(max_output_tokens=MAX_OUTPUT_TOKENS + 1),
        parent_request(input_token_upper_bound=MAX_INPUT_TOKEN_UPPER_BOUND + 1),
        parent_request(provider="other"),
        parent_request(model="other"),
        parent_request(agent_loop=False),
        parent_request(purpose="session-title"),
        parent_request(provider_internal_retries=1),
    ]
    for request in invalid:
        with pytest.raises(ParentDenied):
            gate.reserve(request)
    assert gate.snapshot()["attempts_reserved"] == 0


def test_parent_budget_reserves_input_and_full_output_and_exhausts_before_dispatch(
    tmp_path: Path,
) -> None:
    gate = ParentBudgetGate(tmp_path / "parent.json")
    reservations = [
        gate.reserve(parent_request(input_token_upper_bound=MAX_INPUT_TOKEN_UPPER_BOUND))
        for _ in range(6)
    ]
    with pytest.raises(ParentDenied, match="AUTHORIZED_SPEND_CAP"):
        gate.reserve(parent_request(input_token_upper_bound=MAX_INPUT_TOKEN_UPPER_BOUND))

    assert all(item.output_tokens_reserved == MAX_OUTPUT_TOKENS for item in reservations)
    assert all(item.price_schedule_id == PRICE_SCHEDULE_ID for item in reservations)
    snapshot = gate.snapshot()
    assert snapshot["attempts_reserved"] == 6
    assert len(snapshot["reservations"]) == 6
    assert snapshot["denials"][-1]["reason"] == "AUTHORIZED_SPEND_CAP"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def claim_fixture(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "claim-remote.git"
    source = tmp_path / "source"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    (source / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(source, "add", "seed.txt")
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "-c",
            "user.name=claim-test",
            "-c",
            "user.email=claim-test@example.invalid",
            "commit",
            "-qm",
            "seed",
        ],
        check=True,
    )
    return remote, source


def _claim(tmp_path: Path, state: str = "state", suffix: str = "fresh") -> EpisodeClaim:
    remote, source = claim_fixture(tmp_path)
    return EpisodeClaim(
        tmp_path / state,
        remote=str(remote),
        ref=f"refs/heads/qntylab-claims/offline-test-{suffix}",
        source_repo=source,
    )


def test_claim_fresh_remote_and_local_succeeds_then_restart_blocks_replay(tmp_path: Path) -> None:
    claim = _claim(tmp_path)
    receipt = claim.acquire(session_nonce="session-1")
    assert receipt["state"] == "REMOTE_AND_LOCAL_COMPLETE"
    assert claim.receipt_path.is_file()
    assert claim.remote_exists() is True
    with pytest.raises(ClaimBlocked, match="BLOCK_NEVER_REPLAY"):
        EpisodeClaim(
            claim.state_dir,
            remote=claim.remote,
            ref=claim.ref,
            source_repo=claim.source_repo,
        ).acquire(session_nonce="session-2")


def test_claim_remote_already_present_and_local_already_present_both_block(tmp_path: Path) -> None:
    remote_claim = _claim(tmp_path / "remote-case", suffix="remote-present")
    remote_claim.acquire(session_nonce="winner")
    contender = EpisodeClaim(
        tmp_path / "remote-case/other-state",
        remote=remote_claim.remote,
        ref=remote_claim.ref,
        source_repo=remote_claim.source_repo,
    )
    with pytest.raises(ClaimBlocked, match="BLOCK_NEVER_REPLAY"):
        contender.acquire(session_nonce="loser")

    local_claim = _claim(tmp_path / "local-case", suffix="local-present")
    local_claim.receipt_path.write_text(json.dumps({"partial": True}), encoding="utf-8")
    with pytest.raises(ClaimBlocked, match="BLOCK_NEVER_REPLAY"):
        local_claim.acquire(session_nonce="loser")
    assert local_claim.remote_exists() is False


def test_claim_simultaneous_contenders_have_exactly_one_remote_winner(tmp_path: Path) -> None:
    remote, source = claim_fixture(tmp_path)
    ref = "refs/heads/qntylab-claims/offline-test-concurrent"
    claims = [
        EpisodeClaim(tmp_path / f"state-{index}", remote=str(remote), ref=ref, source_repo=source)
        for index in range(2)
    ]
    outcomes: list[str] = []

    def run(index: int) -> None:
        try:
            claims[index].acquire(session_nonce=f"session-{index}")
            outcomes.append("won")
        except ClaimBlocked:
            outcomes.append("blocked")

    threads = [threading.Thread(target=run, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["blocked", "won"]
    assert claims[0].remote_exists() is True


@pytest.mark.parametrize("stage", ["after_intent", "after_remote"])
def test_claim_crash_or_ambiguous_result_never_reenables_transition(
    tmp_path: Path, stage: str
) -> None:
    claim = _claim(tmp_path, suffix=stage)

    def fault(current: str) -> None:
        if current == stage:
            raise RuntimeError(f"simulated crash at {stage}")

    with pytest.raises(RuntimeError, match="simulated crash"):
        claim.acquire(session_nonce="session-1", fault=fault)
    with pytest.raises(ClaimBlocked, match="BLOCK_NEVER_REPLAY"):
        EpisodeClaim(
            claim.state_dir,
            remote=claim.remote,
            ref=claim.ref,
            source_repo=claim.source_repo,
        ).acquire(session_nonce="session-2")


def test_claim_local_success_then_remote_failure_shape_blocks_without_remote_write(tmp_path: Path) -> None:
    claim = _claim(tmp_path, suffix="local-only")
    claim.receipt_path.write_text(
        json.dumps({"schema_version": "partial-local-success"}),
        encoding="utf-8",
    )
    with pytest.raises(ClaimBlocked, match="BLOCK_NEVER_REPLAY"):
        claim.acquire(session_nonce="session-1")
    assert claim.remote_exists() is False


def test_claim_durable_intent_then_actual_remote_push_failure_blocks_restart(tmp_path: Path) -> None:
    _remote, source = claim_fixture(tmp_path)

    class MissingRemoteClaim(EpisodeClaim):
        def remote_exists(self) -> bool:
            return False

    claim = MissingRemoteClaim(
        tmp_path / "state",
        remote=str(tmp_path / "missing-remote.git"),
        ref="refs/heads/qntylab-claims/offline-test-remote-failure",
        source_repo=source,
    )
    with pytest.raises(ClaimBlocked, match="remote create-only claim failed"):
        claim.acquire(session_nonce="session-1")
    assert claim.intent_path.is_file()
    assert not claim.receipt_path.exists()
    with pytest.raises(ClaimBlocked, match="BLOCK_NEVER_REPLAY"):
        claim.acquire(session_nonce="session-2")


def test_claim_ambiguous_remote_presence_blocks_without_writing_local_state(tmp_path: Path) -> None:
    _remote, source = claim_fixture(tmp_path)
    claim = EpisodeClaim(
        tmp_path / "state",
        remote=str(tmp_path / "unreadable-remote.git"),
        ref="refs/heads/qntylab-claims/offline-test-ambiguous-presence",
        source_repo=source,
    )
    with pytest.raises(ClaimBlocked, match="remote claim presence is ambiguous"):
        claim.acquire(session_nonce="session-1")
    assert not claim.intent_path.exists()
    assert not claim.receipt_path.exists()
    with pytest.raises(ClaimBlocked, match="remote claim presence is ambiguous"):
        claim.acquire(session_nonce="session-2")
