"""Crash-safe, pre-dispatch authority for the DSH Stage-A V1 phase.

This is deliberately a phase-local QntyLab gate, not a general orchestration
runtime.  It makes the native-provider seam explicit: callers must reserve an
exact child tool here before they can invoke a provider.  The gate never
starts DSH, Codex, Claude, or any other subprocess.
"""

from __future__ import annotations

import copy
import argparse
import fcntl
import json
import os
import sys
import tempfile
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable


SCHEMA_VERSION = "dsh-stage-a-v1-hard-orchestration-v0"
PROJECT_ID = "DSH_MULTI_AGENT_ORCHESTRATION_STAGE_A_V1_HARD_ORCHESTRATION_AUTHORIZATION_V0"
CANONICAL_PREDECESSOR = "6d9469aa8fc82381b124947f4518b6be7279a532"
FROZEN_FIXTURE_ID = "STAGE_A_BOUNDED_RETRY_V0"
PARENT_MODEL = "gpt-5-mini"
PARENT_MAX_SPEND_USD = 1.00
CHILD_INFRA_RETRIES = 0
MAX_CODEX_INITIAL = 1
MAX_CODEX_REPAIR = 1
MAX_CLAUDE_INITIAL = 1
MAX_CLAUDE_REREVIEW = 1
MAX_CODEX_TOTAL = 2
MAX_CLAUDE_TOTAL = 2
MAX_PARENT_REQUEST_ATTEMPTS = 8
MAX_RETRIES = 0

CODEX_TOOL = "subagent_codex"
CLAUDE_TOOL = "subagent_claude_code"
ALLOWED_TOOLS = frozenset({CODEX_TOOL, CLAUDE_TOOL})


class AuthorityState(str, Enum):
    PREPARED = "PREPARED"
    IMPLEMENT_REQUIRED = "IMPLEMENT_REQUIRED"
    IMPLEMENT_RUNNING = "IMPLEMENT_RUNNING"
    IMPLEMENT_RETURNED = "IMPLEMENT_RETURNED"
    TEST_REQUIRED = "TEST_REQUIRED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REVIEW_RUNNING = "REVIEW_RUNNING"
    REVIEW_RETURNED = "REVIEW_RETURNED"
    PASS = "PASS"
    REPAIR_REQUIRED = "REPAIR_REQUIRED"
    REPAIR_RUNNING = "REPAIR_RUNNING"
    REPAIR_RETURNED = "REPAIR_RETURNED"
    RETEST_REQUIRED = "RETEST_REQUIRED"
    REREVIEW_REQUIRED = "REREVIEW_REQUIRED"
    REREVIEW_RUNNING = "REREVIEW_RUNNING"
    REREVIEW_RETURNED = "REREVIEW_RETURNED"
    TERMINAL = "TERMINAL"
    BLOCK_CHILD_INFRA = "BLOCK_CHILD_INFRA"
    BLOCK_AUTH = "BLOCK_AUTH"
    BLOCK_COST = "BLOCK_COST"


class ChildLifecycle(str, Enum):
    CHILD_NOT_STARTED = "CHILD_NOT_STARTED"
    CHILD_STARTED = "CHILD_STARTED"
    CHILD_COMPLETED = "CHILD_COMPLETED"
    CHILD_FAILED = "CHILD_FAILED"
    CHILD_TIMEOUT = "CHILD_TIMEOUT"


class OrchestrationError(ValueError):
    """Base class for fail-closed controller errors."""


class AuthorizationDenied(OrchestrationError):
    """A requested child call is not legal at the current authority state."""


class ReviewValidationError(OrchestrationError):
    """A Claude result does not conform to the frozen machine schema."""


class StructuredEventError(OrchestrationError):
    """A purported structured event cannot be parsed safely."""


@dataclass(frozen=True)
class AuthorizationGrant:
    token: str
    tool_name: str
    role: str
    state: AuthorityState


_REVIEW_KEYS = frozenset({"critical", "high", "medium", "low", "closure_blocking", "summary"})
_FINDING_KEYS = frozenset({"id", "summary"})


def validate_review_result(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize the only review shape that can grant repair."""

    if not isinstance(value, Mapping) or set(value) != _REVIEW_KEYS:
        raise ReviewValidationError("review result has an unexpected schema")
    normalized: dict[str, Any] = {}
    for bucket in ("critical", "high", "medium", "low"):
        findings = value[bucket]
        if not isinstance(findings, list):
            raise ReviewValidationError(f"review bucket {bucket} is not a list")
        normalized_findings = []
        for finding in findings:
            if not isinstance(finding, Mapping) or set(finding) != _FINDING_KEYS:
                raise ReviewValidationError(f"review {bucket} finding is malformed")
            if not all(isinstance(finding[key], str) and finding[key].strip() for key in _FINDING_KEYS):
                raise ReviewValidationError(f"review {bucket} finding has invalid text")
            normalized_findings.append({"id": finding["id"], "summary": finding["summary"]})
        normalized[bucket] = normalized_findings
    if type(value["closure_blocking"]) is not bool:
        raise ReviewValidationError("closure_blocking must be a boolean")
    has_closure_finding = bool(normalized["critical"] or normalized["high"])
    if value["closure_blocking"] != has_closure_finding:
        raise ReviewValidationError("closure_blocking does not match Critical/High findings")
    if not isinstance(value["summary"], str) or not value["summary"].strip():
        raise ReviewValidationError("review summary must be non-empty text")
    normalized["closure_blocking"] = value["closure_blocking"]
    normalized["summary"] = value["summary"]
    return normalized


def parse_structured_tool_events(events: Iterable[str | Mapping[str, Any]]) -> list[str]:
    """Return exact names from authoritative ``type=tool/call`` events only.

    Catalogs, schemas, prompt text, reasoning, and streamed text are never
    searched.  A malformed line is rejected rather than silently treated as a
    call or silently dropped.
    """

    names: list[str] = []
    for item in events:
        if isinstance(item, str):
            try:
                event = json.loads(item)
            except json.JSONDecodeError as exc:
                raise StructuredEventError("event line is not valid JSON") from exc
        elif isinstance(item, Mapping):
            event = item
        else:
            raise StructuredEventError("event is neither JSON text nor an object")
        if not isinstance(event, Mapping):
            raise StructuredEventError("event JSON value is not an object")
        if event.get("type") != "tool/call":
            continue
        name = event.get("name")
        if not isinstance(name, str) or not name:
            raise StructuredEventError("tool/call event has no exact tool name")
        names.append(name)
    return names


def count_structured_tool_invocations(
    events: Iterable[str | Mapping[str, Any]], tool_name: str
) -> int:
    """Count exact structured invocations, never substrings."""

    return sum(name == tool_name for name in parse_structured_tool_events(events))


def _initial_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "state": AuthorityState.PREPARED.value,
        "budgets": {
            "codex_initial": False,
            "codex_repair": False,
            "claude_initial": False,
            "claude_rereview": False,
        },
        "active_call": None,
        "test_results": [],
        "review": None,
        "terminal_outcome": None,
        "events": [],
    }


def dispatch_authorized_child(
    controller: "HardOrchestrationController",
    tool_name: str,
    invoke: Callable[[AuthorizationGrant], Any],
) -> Any:
    """Authorize, then invoke exactly once; provider errors consume the grant.

    ``invoke`` is the native-provider/subprocess seam supplied by a later
    execution wrapper.  It cannot run when admission is denied.  A crash after
    admission but before ``invoke`` still leaves the persisted budget consumed.
    """

    grant = controller.pre_dispatch_authorize(tool_name)
    try:
        result = invoke(grant)
    except TimeoutError:
        controller.complete_child(grant, status=ChildLifecycle.CHILD_TIMEOUT)
        raise
    except BaseException:
        controller.complete_child(grant, status=ChildLifecycle.CHILD_FAILED)
        raise
    controller.complete_child(
        grant,
        review_result=result if tool_name == CLAUDE_TOOL else None,
    )
    return result


class HardOrchestrationController:
    """Persistent, fail-closed admission gate used immediately before spawn."""

    def __init__(self, state_path: Path | None = None):
        self.state_path = Path(state_path) if state_path is not None else None
        self._thread_lock = threading.RLock()
        if self.state_path is not None:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.lock_path = self.state_path.with_name(self.state_path.name + ".lock")
            if not self.state_path.exists():
                self._write_state(_initial_state())
        else:
            self.lock_path = None
            self._state = _initial_state()

    def snapshot(self) -> dict[str, Any]:
        with self._locked():
            return copy.deepcopy(self._read_state())

    @property
    def state(self) -> AuthorityState:
        return AuthorityState(self.snapshot()["state"])

    def prepare(self) -> None:
        def mutate(state: dict[str, Any]) -> None:
            if state["state"] == AuthorityState.PREPARED.value:
                self._transition(state, AuthorityState.IMPLEMENT_REQUIRED)

        self._mutate(mutate)

    def pre_dispatch_authorize(self, tool_name: str) -> AuthorizationGrant:
        """Reserve one exact child call before any native provider invocation."""

        if tool_name not in ALLOWED_TOOLS:
            raise AuthorizationDenied(f"unsupported delegation tool: {tool_name!r}")
        grant: AuthorizationGrant | None = None

        def mutate(state: dict[str, Any]) -> None:
            nonlocal grant
            current = AuthorityState(state["state"])
            if state["active_call"] is not None:
                raise AuthorizationDenied("a child is already running")
            if tool_name == CODEX_TOOL and current == AuthorityState.IMPLEMENT_REQUIRED:
                budget_key, role, running = "codex_initial", "codex_initial", AuthorityState.IMPLEMENT_RUNNING
            elif tool_name == CODEX_TOOL and current == AuthorityState.REPAIR_REQUIRED:
                budget_key, role, running = "codex_repair", "codex_repair", AuthorityState.REPAIR_RUNNING
            elif tool_name == CLAUDE_TOOL and current == AuthorityState.REVIEW_REQUIRED:
                budget_key, role, running = "claude_initial", "claude_initial", AuthorityState.REVIEW_RUNNING
            elif tool_name == CLAUDE_TOOL and current == AuthorityState.REREVIEW_REQUIRED:
                budget_key, role, running = "claude_rereview", "claude_rereview", AuthorityState.REREVIEW_RUNNING
            else:
                raise AuthorizationDenied(f"{tool_name} is denied in {current.value}")
            if state["budgets"][budget_key]:
                raise AuthorizationDenied(f"{role} budget is already consumed")
            state["budgets"][budget_key] = True
            token = f"{role}-{len(state['events']) + 1}"
            state["active_call"] = {
                "token": token,
                "tool_name": tool_name,
                "role": role,
                "lifecycle": ChildLifecycle.CHILD_STARTED.value,
            }
            self._transition(state, running, event_type="CHILD_STARTED", token=token, tool_name=tool_name)
            grant = AuthorizationGrant(token, tool_name, role, running)

        self._mutate(mutate)
        assert grant is not None
        return grant

    def complete_child(
        self,
        grant: AuthorizationGrant,
        *,
        status: ChildLifecycle = ChildLifecycle.CHILD_COMPLETED,
        review_result: Mapping[str, Any] | None = None,
    ) -> None:
        """Record completion; failures/timeouts consume budget and block."""

        if status == ChildLifecycle.CHILD_STARTED:
            raise OrchestrationError("a child cannot be completed with CHILD_STARTED")

        def mutate(state: dict[str, Any]) -> None:
            active = state["active_call"]
            if active is None or active["token"] != grant.token:
                raise AuthorizationDenied("child token is inactive or already consumed")
            if active["tool_name"] != grant.tool_name or active["role"] != grant.role:
                raise AuthorizationDenied("child token/tool binding mismatch")
            state["active_call"]["lifecycle"] = status.value
            if status in {ChildLifecycle.CHILD_FAILED, ChildLifecycle.CHILD_TIMEOUT}:
                state["active_call"] = None
                self._terminal(state, AuthorityState.BLOCK_CHILD_INFRA, "BLOCK_CHILD_INFRA", "CHILD_INFRA_FAILURE")
                return
            if status != ChildLifecycle.CHILD_COMPLETED:
                raise OrchestrationError(f"unsupported child status: {status.value}")
            if grant.role in {"claude_initial", "claude_rereview"}:
                try:
                    review = validate_review_result(review_result if review_result is not None else {})
                except ReviewValidationError:
                    state["active_call"] = None
                    self._terminal(state, AuthorityState.BLOCK_CHILD_INFRA, "BLOCK_CHILD_INFRA", "MALFORMED_REVIEW")
                    raise
                state["review"] = review
            role = grant.role
            state["active_call"] = None
            if role == "codex_initial":
                self._transition(state, AuthorityState.TEST_REQUIRED, event_type="IMPLEMENT_RETURNED", token=grant.token)
            elif role == "claude_initial":
                if state["review"]["closure_blocking"]:
                    self._transition(state, AuthorityState.REPAIR_REQUIRED, event_type="REVIEW_RETURNED", token=grant.token)
                elif not state["test_results"][0]["passed"]:
                    self._terminal(state, AuthorityState.TERMINAL, "FAIL_IMPLEMENTATION", "REVIEW_RETURNED")
                else:
                    self._transition(state, AuthorityState.PASS, event_type="REVIEW_RETURNED", token=grant.token)
            elif role == "codex_repair":
                self._transition(state, AuthorityState.RETEST_REQUIRED, event_type="REPAIR_RETURNED", token=grant.token)
            elif role == "claude_rereview":
                # A clean rereview cannot launder a failed retest into PASS.
                # The latest driver-owned retest is the authoritative
                # implementation result at this point in the state machine.
                if not state["test_results"][-1]["passed"]:
                    self._terminal(state, AuthorityState.TERMINAL, "FAIL_IMPLEMENTATION", "REREVIEW_RETURNED")
                elif state["review"]["closure_blocking"]:
                    self._terminal(state, AuthorityState.TERMINAL, "FAIL_REVIEW", "REREVIEW_RETURNED")
                else:
                    self._terminal(state, AuthorityState.TERMINAL, "PASS_AFTER_BOUNDED_REPAIR", "REREVIEW_RETURNED")
            else:  # pragma: no cover - role is minted by this controller only
                self._terminal(state, AuthorityState.BLOCK_AUTH, "BLOCK_AUTH", "UNKNOWN_ROLE")

        self._mutate(mutate)

    def record_driver_tests(self, *, passed: bool, retest: bool = False) -> None:
        """Record driver-owned fixture tests and unlock exactly one review step."""

        def mutate(state: dict[str, Any]) -> None:
            current = AuthorityState(state["state"])
            expected = AuthorityState.RETEST_REQUIRED if retest else AuthorityState.TEST_REQUIRED
            if current != expected:
                raise AuthorizationDenied(f"driver tests are not required in {current.value}")
            state["test_results"].append({"kind": "retest" if retest else "initial", "passed": bool(passed)})
            self._transition(
                state,
                AuthorityState.REREVIEW_REQUIRED if retest else AuthorityState.REVIEW_REQUIRED,
                event_type="RETEST_COMPLETED" if retest else "TEST_COMPLETED",
            )

        self._mutate(mutate)

    def seal_pass(self) -> None:
        def mutate(state: dict[str, Any]) -> None:
            if AuthorityState(state["state"]) != AuthorityState.PASS:
                raise AuthorizationDenied("only PASS can be sealed")
            self._terminal(state, AuthorityState.TERMINAL, "PASS", "PASS_SEALED")

        self._mutate(mutate)

    def _locked(self):
        controller = self

        class _Lock:
            def __enter__(self):
                controller._thread_lock.acquire()
                if controller.lock_path is not None:
                    self.handle = controller.lock_path.open("a+")
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
                return self

            def __exit__(self, exc_type, exc, tb):
                if controller.lock_path is not None:
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
                    self.handle.close()
                controller._thread_lock.release()

        return _Lock()

    def _read_state(self) -> dict[str, Any]:
        if self.state_path is None:
            return self._state
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OrchestrationError("controller state is unreadable") from exc
        if value.get("schema_version") != SCHEMA_VERSION or not isinstance(value.get("events"), list):
            raise OrchestrationError("controller state schema mismatch")
        for index, event in enumerate(value["events"], start=1):
            if event.get("sequence") != index:
                raise OrchestrationError("controller event sequence is not contiguous")
        return value

    def _write_state(self, state: dict[str, Any]) -> None:
        if self.state_path is None:
            self._state = state
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=self.state_path.name + ".", dir=self.state_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.state_path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def _mutate(self, mutation) -> None:
        with self._locked():
            state = self._read_state()
            before = copy.deepcopy(state)
            try:
                mutation(state)
            except Exception:
                # A malformed review and similar fail-closed paths deliberately
                # mutate authority to a blocker before raising.  Persist that
                # blocker; otherwise a restart could incorrectly reopen it.
                if state != before:
                    self._write_state(state)
                raise
            self._write_state(state)

    @staticmethod
    def _transition(state: dict[str, Any], target: AuthorityState, *, event_type: str = "STATE_TRANSITION", **payload: Any) -> None:
        sequence = len(state["events"]) + 1
        event = {"event_type": event_type, "sequence": sequence, "state": target.value, **payload}
        state["events"].append(event)
        state["state"] = target.value

    @classmethod
    def _terminal(cls, state: dict[str, Any], target: AuthorityState, outcome: str, event_type: str) -> None:
        state["terminal_outcome"] = outcome
        cls._transition(state, target, event_type=event_type, outcome=outcome)


def _controller_for_cli(state_path: str) -> HardOrchestrationController:
    controller = HardOrchestrationController(Path(state_path))
    if controller.state == AuthorityState.PREPARED:
        controller.prepare()
    return controller


def main(argv: list[str] | None = None) -> int:
    """Small JSON CLI used by the V1 profile's pre-provider gate adapter."""

    parser = argparse.ArgumentParser(prog="qntylab.dsh_stage_a_v1_hard_orchestration")
    parser.add_argument("--state", required=True, help="persisted authority checkpoint path")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare")
    authorize = subparsers.add_parser("authorize")
    authorize.add_argument("tool", choices=sorted(ALLOWED_TOOLS))
    complete = subparsers.add_parser("complete")
    complete.add_argument("--token", required=True)
    complete.add_argument("--tool", required=True, choices=sorted(ALLOWED_TOOLS))
    complete.add_argument("--role", required=True)
    complete.add_argument("--status", choices=[item.value for item in ChildLifecycle], default=ChildLifecycle.CHILD_COMPLETED.value)
    complete.add_argument("--review-json")
    tests = subparsers.add_parser("tests")
    tests.add_argument("--retest", action="store_true")
    tests.add_argument("--passed", action="store_true")
    tests.add_argument("--failed", action="store_true")

    args = parser.parse_args(argv)
    try:
        controller = _controller_for_cli(args.state)
        if args.command == "prepare":
            print(json.dumps(controller.snapshot(), sort_keys=True))
        elif args.command == "authorize":
            grant = controller.pre_dispatch_authorize(args.tool)
            print(json.dumps({"token": grant.token, "tool_name": grant.tool_name, "role": grant.role, "state": grant.state.value}, sort_keys=True))
        elif args.command == "complete":
            review_result = json.loads(args.review_json) if args.review_json is not None else None
            grant = AuthorizationGrant(args.token, args.tool, args.role, controller.state)
            controller.complete_child(grant, status=ChildLifecycle(args.status), review_result=review_result)
            print(json.dumps(controller.snapshot(), sort_keys=True))
        else:
            if args.passed == args.failed:
                raise OrchestrationError("tests requires exactly one of --passed or --failed")
            controller.record_driver_tests(passed=args.passed, retest=args.retest)
            print(json.dumps(controller.snapshot(), sort_keys=True))
        return 0
    except (OrchestrationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"qntylab gate denied: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised by the profile adapter
    raise SystemExit(main())
