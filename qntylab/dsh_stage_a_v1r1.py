"""Offline Stage-A V1R1 runtime-hardening primitives.

The module owns only deterministic, fail-closed qualification controls.  It
does not start DSH, a model, Codex, Claude, or the Stage-A fixture.
"""

from __future__ import annotations

import copy
import fcntl
import json
import os
import tempfile
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping


PROJECT_ID = "DSH_MULTI_AGENT_ORCHESTRATION_STAGE_A_V1R1_BOOTSTRAP_AND_RUNTIME_HARDENING_AUTHORIZATION_V0"
PINNED_DSH_COMMIT = "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
PINNED_DSH_TREE = "3bc8f89fe494a4755c188be3544e8b1e7b188"
PARENT_PROVIDER = "openai"
PARENT_MODEL = "gpt-5-mini"
PARENT_MAX_TOKENS = 4096
PARENT_RETRY_MAX = 0
PARENT_MAX_ATTEMPTS = 8
PARENT_SPEND_CEILING_USD = 1.00
CHILD_TOOLS = ("subagent_codex", "subagent_claude_code")


class V1R1Blocked(RuntimeError):
    """Raised when a V1R1 invariant cannot be proven."""


class CostBlocked(V1R1Blocked):
    """A parent request was rejected before adapter dispatch."""


class LifecycleBlocked(V1R1Blocked):
    """A raw provider was absent or replaced after authorization."""


class SettlementKind(str, Enum):
    RAW_START_FAILED = "RAW_START_FAILED"
    RAW_RESULT_FAILED = "RAW_RESULT_FAILED"
    REVIEW_PARSE_FAILED = "REVIEW_PARSE_FAILED"
    GATE_COMPLETE_FAILED = "GATE_COMPLETE_FAILED"
    DISPOSE_FAILED = "DISPOSE_FAILED"
    CHILD_TIMEOUT = "CHILD_TIMEOUT"
    MALFORMED_REVIEW = "MALFORMED_REVIEW"
    CHILD_COMPLETED = "CHILD_COMPLETED"


@dataclass(frozen=True)
class ParentRequest:
    """The only request envelope admitted by the Stage-A parent gate."""

    provider: str
    model: str
    max_tokens: int
    retry_max: int
    agent_loop: bool
    purpose: str | None = None


class ParentLlmBudgetGate:
    """Crash-safe reservation gate for paid parent requests.

    A reservation is persisted before the caller may invoke its adapter.  A
    process crash therefore consumes capacity rather than replenishing it.
    ``flock`` serializes independent DSH/plugin processes, while the in-process
    lock avoids re-entrant races in tests and same-process callers.
    """

    SCHEMA = "dsh-stage-a-v1r1-parent-budget-v0"

    def __init__(self, state_path: Path):
        self.state_path = Path(state_path)
        self.lock_path = self.state_path.with_name(self.state_path.name + ".lock")
        self._thread_lock = threading.RLock()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with self._locked():
            if not self.state_path.exists():
                self._write(self._initial())

    def reserve(self, request: ParentRequest) -> int:
        self._validate_route(request)
        reserved: int | None = None

        def mutate(state: dict[str, Any]) -> None:
            nonlocal reserved
            attempts = int(state["attempts_reserved"])
            if attempts >= PARENT_MAX_ATTEMPTS:
                raise CostBlocked("BLOCK_COST: parent request attempt ceiling exhausted")
            reserved = attempts + 1
            state["attempts_reserved"] = reserved
            state["reservations"].append({"attempt": reserved, "route": "parent-agent-loop"})

        self._mutate(mutate)
        assert reserved is not None
        return reserved

    def snapshot(self) -> dict[str, Any]:
        with self._locked():
            return copy.deepcopy(self._read())

    @staticmethod
    def _validate_route(request: ParentRequest) -> None:
        if (
            request.provider != PARENT_PROVIDER
            or request.model != PARENT_MODEL
            or request.max_tokens != PARENT_MAX_TOKENS
            or request.retry_max != PARENT_RETRY_MAX
            or not request.agent_loop
            or request.purpose is not None
        ):
            raise CostBlocked("BLOCK_COST: unexpected or auxiliary OpenAI route")

    def _initial(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA,
            "attempts_reserved": 0,
            "max_attempts": PARENT_MAX_ATTEMPTS,
            "spend_ceiling_usd": PARENT_SPEND_CEILING_USD,
            "reservations": [],
        }

    def _locked(self):
        owner = self

        class Lock:
            def __enter__(self):
                owner._thread_lock.acquire()
                self.handle = owner.lock_path.open("a+")
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
                return self

            def __exit__(self, exc_type, exc, tb):
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
                self.handle.close()
                owner._thread_lock.release()

        return Lock()

    def _read(self) -> dict[str, Any]:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise V1R1Blocked("parent budget state is unreadable") from exc
        if state.get("schema_version") != self.SCHEMA:
            raise V1R1Blocked("parent budget schema mismatch")
        if not isinstance(state.get("reservations"), list):
            raise V1R1Blocked("parent budget reservations are malformed")
        return state

    def _write(self, state: Mapping[str, Any]) -> None:
        fd, name = tempfile.mkstemp(prefix=self.state_path.name + ".", dir=self.state_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self.state_path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _mutate(self, mutation: Callable[[dict[str, Any]], None]) -> None:
        with self._locked():
            state = self._read()
            mutation(state)
            self._write(state)


class ProviderLifecycleMirror:
    """Event-first raw-provider mirror used by the gated provider plugin."""

    def __init__(self, raw_name: str, gated_name: str):
        self.raw_name = raw_name
        self.gated_name = gated_name
        self.raw: object | None = None
        self.gated: object | None = None
        self.mounts = 0
        self.unmounts = 0

    def attach(self, current: Mapping[str, object], mount: Callable[[object], object], unmount: Callable[[object], None]) -> None:
        """Register listeners conceptually before inspecting current presence."""

        self._mount_callback = mount
        self._unmount_callback = unmount
        if self.raw is None and self.raw_name in current:
            self._mount(current[self.raw_name], self._mount_callback)

    def added(self, name: str, provider: object) -> None:
        if name != self.raw_name or self.raw is not None:
            return
        self._mount(provider, self._mount_callback)

    def removed(self, name: str) -> None:
        if name != self.raw_name or self.raw is None:
            return
        old = self.gated
        self.raw = None
        self.gated = None
        self.unmounts += 1
        if old is not None:
            self._unmount_callback(old)

    def assert_current(self, current: object | None) -> object:
        if self.raw is None or current is not self.raw:
            raise LifecycleBlocked("BLOCK_CHILD_INFRA: raw provider disappeared or was replaced")
        return self.raw

    def _mount(self, provider: object, mount: Callable[[object], object]) -> None:
        self.raw = provider
        self.gated = mount(provider)
        self.mounts += 1


class SettlementMachine:
    """Single-terminal settlement with explicit failure classification."""

    def __init__(self):
        self.terminal: SettlementKind | None = None

    def settle(self, kind: SettlementKind) -> bool:
        if self.terminal is not None:
            return False
        self.terminal = kind
        return True


READ_ONLY_REVIEW_TOOLS = frozenset({"Read", "Glob", "Grep"})
MUTATING_REVIEW_TOOLS = frozenset({"Write", "Edit", "Bash", "Agent", "Task", "mcp__*"})


def validate_claude_review_policy(policy: Mapping[str, Any]) -> None:
    """Reject any SDK policy that can expose mutation, delegation, or MCP."""

    if set(policy.get("tools", ())) != READ_ONLY_REVIEW_TOOLS:
        raise V1R1Blocked("Claude reviewer tools are not exactly Read/Glob/Grep")
    disallowed = set(policy.get("disallowedTools", ()))
    if not MUTATING_REVIEW_TOOLS.issubset(disallowed):
        raise V1R1Blocked("Claude reviewer mutation/delegation tools are not denied")
    if policy.get("settingSources") != [] or policy.get("persistSession") is not False:
        raise V1R1Blocked("Claude reviewer host/project settings or persistence are enabled")
    if policy.get("mcpServers") not in (None, {}):
        raise V1R1Blocked("Claude reviewer MCP is enabled")


REQUIRED_BOOT = {
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


def qualify_boot(observed: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic readiness receipt or raise fail-closed."""

    for key, expected in REQUIRED_BOOT.items():
        if observed.get(key) != expected:
            raise V1R1Blocked(f"BOOT_READY failed: {key}={observed.get(key)!r}, expected {expected!r}")
    return dict(REQUIRED_BOOT)


__all__ = [
    "CHILD_TOOLS",
    "CostBlocked",
    "LifecycleBlocked",
    "PARENT_MAX_ATTEMPTS",
    "PARENT_MAX_TOKENS",
    "PARENT_MODEL",
    "PARENT_PROVIDER",
    "PARENT_RETRY_MAX",
    "ParentLlmBudgetGate",
    "ParentRequest",
    "ProviderLifecycleMirror",
    "REQUIRED_BOOT",
    "SettlementKind",
    "SettlementMachine",
    "V1R1Blocked",
    "qualify_boot",
    "validate_claude_review_policy",
]
