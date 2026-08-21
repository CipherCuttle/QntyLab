from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from qntylab.dsh_stage_a_v1r1 import (
    CHILD_TOOLS,
    CostBlocked,
    LifecycleBlocked,
    PARENT_MAX_ATTEMPTS,
    PARENT_MAX_TOKENS,
    PARENT_MODEL,
    PARENT_PROVIDER,
    PARENT_RETRY_MAX,
    ParentLlmBudgetGate,
    ParentRequest,
    ProviderLifecycleMirror,
    SettlementKind,
    SettlementMachine,
    V1R1Blocked,
    qualify_boot,
    validate_claude_review_policy,
)


def parent_request(**overrides) -> ParentRequest:
    values = dict(
        provider=PARENT_PROVIDER,
        model=PARENT_MODEL,
        max_tokens=PARENT_MAX_TOKENS,
        retry_max=PARENT_RETRY_MAX,
        agent_loop=True,
    )
    values.update(overrides)
    return ParentRequest(**values)


def test_parent_budget_allows_eight_and_denies_ninth_before_dispatch(tmp_path: Path):
    gate = ParentLlmBudgetGate(tmp_path / "parent.json")
    assert [gate.reserve(parent_request()) for _ in range(PARENT_MAX_ATTEMPTS)] == list(range(1, 9))
    with pytest.raises(CostBlocked, match="BLOCK_COST"):
        gate.reserve(parent_request())
    assert gate.snapshot()["attempts_reserved"] == 8


def test_parent_budget_rejects_auxiliary_and_wrong_route(tmp_path: Path):
    gate = ParentLlmBudgetGate(tmp_path / "parent.json")
    with pytest.raises(CostBlocked):
        gate.reserve(parent_request(purpose="session-title"))
    with pytest.raises(CostBlocked):
        gate.reserve(parent_request(provider="deepseek-official"))
    with pytest.raises(CostBlocked):
        gate.reserve(parent_request(agent_loop=False))


def test_parent_budget_parallel_reservation_cannot_exceed_cap(tmp_path: Path):
    gate = ParentLlmBudgetGate(tmp_path / "parent.json")
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: _reserve(gate), range(16)))
    allowed = sorted(value for value in results if value is not None)
    assert allowed == list(range(1, 9))
    assert sum(value is None for value in results) == 8


def _reserve(gate: ParentLlmBudgetGate) -> int | None:
    try:
        return gate.reserve(parent_request())
    except CostBlocked:
        return None


def test_parent_reservation_survives_restart(tmp_path: Path):
    path = tmp_path / "parent.json"
    ParentLlmBudgetGate(path).reserve(parent_request())
    restarted = ParentLlmBudgetGate(path)
    assert restarted.snapshot()["attempts_reserved"] == 1
    assert restarted.reserve(parent_request()) == 2


def test_provider_lifecycle_is_event_first_and_mounts_once():
    raw = object()
    mirror = ProviderLifecycleMirror("codex", "gated-codex")
    mounted = []
    removed = []
    mirror.attach({}, lambda value: mounted.append(value) or object(), removed.append)
    mirror.added("codex", raw)
    mirror.added("codex", object())
    assert mirror.mounts == 1 and mounted == [raw]
    mirror.removed("codex")
    assert mirror.unmounts == 1 and len(removed) == 1
    mirror.added("codex", raw)
    assert mirror.mounts == 2


def test_provider_identity_replacement_blocks_start():
    first = object()
    second = object()
    mirror = ProviderLifecycleMirror("codex", "gated-codex")
    mirror.attach({"codex": first}, lambda value: value, lambda _: None)
    with pytest.raises(LifecycleBlocked, match="BLOCK_CHILD_INFRA"):
        mirror.assert_current(second)


def test_settlement_is_single_terminal_and_preserves_malformed_review():
    settlement = SettlementMachine()
    assert settlement.settle(SettlementKind.MALFORMED_REVIEW)
    assert not settlement.settle(SettlementKind.CHILD_TIMEOUT)
    assert settlement.terminal == SettlementKind.MALFORMED_REVIEW


def test_claude_policy_is_exactly_read_only():
    validate_claude_review_policy({
        "tools": ["Read", "Glob", "Grep"],
        "disallowedTools": ["Write", "Edit", "Bash", "Agent", "Task", "mcp__*"],
        "settingSources": [],
        "persistSession": False,
        "mcpServers": {},
    })
    with pytest.raises(V1R1Blocked):
        validate_claude_review_policy({
            "tools": ["Read", "Glob", "Grep", "Bash"],
            "disallowedTools": [],
            "settingSources": [],
            "persistSession": False,
        })


def test_boot_readiness_and_negative_controls():
    observed = {
        "PLUGIN_TREE_SETTLED": "YES",
        "RAW_CODEX_PROVIDER_REGISTERED": "YES",
        "RAW_CLAUDE_PROVIDER_REGISTERED": "YES",
        "GATED_CODEX_PROVIDER_REGISTERED": "YES",
        "GATED_CLAUDE_PROVIDER_REGISTERED": "YES",
        "MODEL_FACING_CHILD_TOOLS": list(CHILD_TOOLS),
        "GENERIC_CHILD_TOOLS": [],
        "BACKGROUND_DELEGATION": "DISABLED",
        "PARENT_LLM_BUDGET_GATE_ACTIVE": "YES",
        "AUXILIARY_OPENAI_ROUTES": [],
        "PARENT_MODEL_ROUTE": "openai / gpt-5-mini",
        "RETRY_MAX": 0,
        "MAX_TOKENS": 4096,
        "NO_MODEL_REQUESTS": "YES",
        "NO_CHILD_SPAWNS": "YES",
        "BOOT_READY": "YES",
    }
    assert qualify_boot(observed)["BOOT_READY"] == "YES"
    observed["GENERIC_CHILD_TOOLS"] = ["tool-workflow"]
    with pytest.raises(V1R1Blocked):
        qualify_boot(observed)
