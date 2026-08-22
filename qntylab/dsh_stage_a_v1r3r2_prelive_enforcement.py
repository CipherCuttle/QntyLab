"""Fail-closed prelive controls for the Stage-A V1R3R2 launch profile.

The module owns deterministic local enforcement only.  It never launches DSH,
Codex, Claude, or an LLM adapter, and it never reads provider credentials.
Callers must reserve here before crossing their native-child or parent-wire
boundary.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any


PROJECT_ID = "DSH_STAGE_A_V1R3R2_PRELIVE_EXECUTION_ENFORCEMENT_GAP_CLOSURE_V0"

CODEX_TOOL = "subagent_codex"
CLAUDE_TOOL = "subagent_claude_code"
ALLOWED_CHILD_TOOLS = frozenset({CODEX_TOOL, CLAUDE_TOOL})

PARENT_PROVIDER = "openai"
PARENT_MODEL = "gpt-5-mini"
MAX_PARENT_REQUEST_ATTEMPTS = 8
MAX_OUTPUT_TOKENS = 4096
MAX_MODEL_CONTEXT_TOKENS = 128_000
MAX_INPUT_TOKEN_UPPER_BOUND = MAX_MODEL_CONTEXT_TOKENS - MAX_OUTPUT_TOKENS
PARENT_OPENAI_AUTHORIZED_SPEND_CAP_USD = Decimal("1.00")

# Official OpenAI rates observed on 2026-08-22.  Reservations deliberately
# apply a frozen 4x uncertainty multiplier.  The cap therefore describes
# authorized spend under this frozen schedule, not total multi-model cash
# spend and not a promise about a future unpinned alias price.
PRICE_SCHEDULE_ID = "openai-gpt-5-mini-2026-08-22-4x-authorization-reserve-v0"
INPUT_USD_PER_MILLION = Decimal("0.25")
OUTPUT_USD_PER_MILLION = Decimal("2.00")
PRICE_UNCERTAINTY_MULTIPLIER = Decimal("4")

CHILD_SCHEMA = "dsh-stage-a-v1r3r2-prelive-child-state-v0"
PARENT_SCHEMA = "dsh-stage-a-v1r3r2-prelive-parent-budget-v0"
CLAIM_SCHEMA = "dsh-stage-a-v1r3r2-prelive-claim-v0"


class EnforcementBlocked(RuntimeError):
    """A pre-dispatch invariant could not be proven."""


class ChildDenied(EnforcementBlocked):
    """The requested native child transition is illegal."""


class ParentDenied(EnforcementBlocked):
    """The requested parent adapter dispatch is illegal or over budget."""


class ClaimBlocked(EnforcementBlocked):
    """The episode claim is present, partial, ambiguous, or could not be made."""


class ChildState(str, Enum):
    INITIAL = "INITIAL"
    INITIAL_CODEX_RUNNING = "INITIAL_CODEX_RUNNING"
    AFTER_INITIAL_CODEX = "AFTER_INITIAL_CODEX"
    CLAUDE_REVIEW_RUNNING = "CLAUDE_REVIEW_RUNNING"
    AFTER_REVIEW_NO_C_H = "AFTER_REVIEW_NO_C_H"
    AFTER_REVIEW_C_H = "AFTER_REVIEW_C_H"
    CODEX_REPAIR_RUNNING = "CODEX_REPAIR_RUNNING"
    AFTER_REPAIR = "AFTER_REPAIR"
    CLAUDE_REREVIEW_RUNNING = "CLAUDE_REREVIEW_RUNNING"
    AFTER_REREVIEW = "AFTER_REREVIEW"
    BLOCK_CHILD_INFRA = "BLOCK_CHILD_INFRA"


TERMINAL_CHILD_STATES = frozenset(
    {
        ChildState.AFTER_REVIEW_NO_C_H,
        ChildState.AFTER_REREVIEW,
        ChildState.BLOCK_CHILD_INFRA,
    }
)


@dataclass(frozen=True)
class ChildGrant:
    token: str
    tool_name: str
    role: str


@dataclass(frozen=True)
class ParentRequest:
    provider: str
    model: str
    agent_loop: bool
    purpose: str | None
    max_output_tokens: int
    input_token_upper_bound: int
    provider_internal_retries: int


@dataclass(frozen=True)
class ParentReservation:
    attempt: int
    input_token_upper_bound: int
    output_tokens_reserved: int
    authorized_cost_usd: str
    cumulative_authorized_spend_usd: str
    price_schedule_id: str


def _review(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ChildDenied("Claude review is not an object")
    expected = {"critical", "high", "medium", "low", "closure_blocking", "summary"}
    if set(value) != expected:
        raise ChildDenied("Claude review has an unexpected schema")
    normalized: dict[str, Any] = {}
    for bucket in ("critical", "high", "medium", "low"):
        findings = value[bucket]
        if not isinstance(findings, list):
            raise ChildDenied(f"Claude review bucket {bucket} is not a list")
        normalized_findings: list[dict[str, str]] = []
        for finding in findings:
            if not isinstance(finding, Mapping) or set(finding) != {"id", "summary"}:
                raise ChildDenied(f"Claude review bucket {bucket} is malformed")
            if not all(isinstance(finding[key], str) and finding[key].strip() for key in ("id", "summary")):
                raise ChildDenied(f"Claude review bucket {bucket} contains invalid text")
            normalized_findings.append({"id": finding["id"], "summary": finding["summary"]})
        normalized[bucket] = normalized_findings
    if type(value["closure_blocking"]) is not bool:
        raise ChildDenied("Claude review closure_blocking is not boolean")
    closure_blocking = bool(normalized["critical"] or normalized["high"])
    if value["closure_blocking"] != closure_blocking:
        raise ChildDenied("Claude review closure_blocking disagrees with Critical/High findings")
    if not isinstance(value["summary"], str) or not value["summary"].strip():
        raise ChildDenied("Claude review summary is empty")
    normalized["closure_blocking"] = closure_blocking
    normalized["summary"] = value["summary"]
    return normalized


class _DurableJson:
    """Small flock + fsync JSON owner used by both reservation machines."""

    def __init__(self, path: Path, schema: str, initial: Callable[[], dict[str, Any]]):
        self.path = Path(path)
        self.schema = schema
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self._thread_lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.locked():
            if not self.path.exists():
                self.write(initial())

    def locked(self):
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

    def read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EnforcementBlocked(f"durable state is unreadable: {self.path}") from exc
        if value.get("schema_version") != self.schema:
            raise EnforcementBlocked(f"durable state schema mismatch: {self.path}")
        return value

    def write(self, value: Mapping[str, Any]) -> None:
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            _fsync_directory(self.path.parent)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class StageAChildController:
    """Exact Stage-A transition gate persisted before raw provider start."""

    def __init__(self, state_path: Path):
        self._store = _DurableJson(state_path, CHILD_SCHEMA, self._initial)

    @staticmethod
    def _initial() -> dict[str, Any]:
        return {
            "schema_version": CHILD_SCHEMA,
            "state": ChildState.INITIAL.value,
            "active_call": None,
            "codex_calls_reserved": 0,
            "claude_calls_reserved": 0,
            "events": [],
            "terminal_outcome": None,
        }

    def snapshot(self) -> dict[str, Any]:
        with self._store.locked():
            return copy.deepcopy(self._store.read())

    def authorize(
        self,
        tool_name: str,
        *,
        provider_name: str,
        background: bool = False,
    ) -> ChildGrant:
        if tool_name not in ALLOWED_CHILD_TOOLS:
            raise ChildDenied(f"unsupported child tool: {tool_name!r}")
        expected_provider = "codex" if tool_name == CODEX_TOOL else "claude-code"
        if provider_name != expected_provider:
            raise ChildDenied(f"alternate child provider denied: {provider_name!r}")
        if background:
            raise ChildDenied("background delegation is denied")
        with self._store.locked():
            state = self._store.read()
            current = ChildState(state["state"])
            if state["active_call"] is not None or current in TERMINAL_CHILD_STATES:
                raise ChildDenied(f"child denied in {current.value}")
            if tool_name == CODEX_TOOL and current == ChildState.INITIAL:
                role = "codex_initial"
                target = ChildState.INITIAL_CODEX_RUNNING
            elif tool_name == CLAUDE_TOOL and current == ChildState.AFTER_INITIAL_CODEX:
                role = "claude_review"
                target = ChildState.CLAUDE_REVIEW_RUNNING
            elif tool_name == CODEX_TOOL and current == ChildState.AFTER_REVIEW_C_H:
                role = "codex_repair"
                target = ChildState.CODEX_REPAIR_RUNNING
            elif tool_name == CLAUDE_TOOL and current == ChildState.AFTER_REPAIR:
                role = "claude_rereview"
                target = ChildState.CLAUDE_REREVIEW_RUNNING
            else:
                raise ChildDenied(f"{tool_name} denied in {current.value}")
            counter = "codex_calls_reserved" if tool_name == CODEX_TOOL else "claude_calls_reserved"
            maximum = 2
            if int(state[counter]) >= maximum:
                raise ChildDenied(f"{tool_name} maximum {maximum} exhausted")
            state[counter] = int(state[counter]) + 1
            token = f"{role}-{len(state['events']) + 1}"
            state["active_call"] = {
                "token": token,
                "tool_name": tool_name,
                "provider_name": provider_name,
                "role": role,
            }
            self._event(state, "CHILD_RESERVED", target, token=token, role=role, tool_name=tool_name)
            self._store.write(state)
            return ChildGrant(token, tool_name, role)

    def complete(
        self,
        grant: ChildGrant,
        *,
        review_result: Mapping[str, Any] | None = None,
        status: str = "CHILD_COMPLETED",
    ) -> None:
        with self._store.locked():
            state = self._store.read()
            active = state["active_call"]
            if not isinstance(active, Mapping) or active.get("token") != grant.token:
                raise ChildDenied("child grant is inactive or already consumed")
            if active.get("tool_name") != grant.tool_name or active.get("role") != grant.role:
                raise ChildDenied("child grant binding mismatch")
            if status != "CHILD_COMPLETED":
                state["active_call"] = None
                state["terminal_outcome"] = "BLOCK_CHILD_INFRA"
                self._event(state, status, ChildState.BLOCK_CHILD_INFRA, token=grant.token)
                self._store.write(state)
                return
            try:
                if grant.role == "codex_initial":
                    target = ChildState.AFTER_INITIAL_CODEX
                elif grant.role == "claude_review":
                    review = _review(review_result)
                    target = (
                        ChildState.AFTER_REVIEW_C_H
                        if review["closure_blocking"]
                        else ChildState.AFTER_REVIEW_NO_C_H
                    )
                    state["review"] = review
                    if target == ChildState.AFTER_REVIEW_NO_C_H:
                        state["terminal_outcome"] = "PASS_NO_CRITICAL_HIGH"
                elif grant.role == "codex_repair":
                    target = ChildState.AFTER_REPAIR
                elif grant.role == "claude_rereview":
                    review = _review(review_result)
                    target = ChildState.AFTER_REREVIEW
                    state["review"] = review
                    state["terminal_outcome"] = (
                        "FAIL_REREVIEW_CRITICAL_HIGH"
                        if review["closure_blocking"]
                        else "PASS_AFTER_BOUNDED_REPAIR"
                    )
                else:  # pragma: no cover - roles are minted above.
                    raise ChildDenied(f"unknown child role: {grant.role}")
            except ChildDenied:
                state["active_call"] = None
                state["terminal_outcome"] = "BLOCK_CHILD_INFRA"
                self._event(state, "MALFORMED_REVIEW", ChildState.BLOCK_CHILD_INFRA, token=grant.token)
                self._store.write(state)
                raise
            state["active_call"] = None
            self._event(state, "CHILD_COMPLETED", target, token=grant.token, role=grant.role)
            self._store.write(state)

    @staticmethod
    def _event(state: dict[str, Any], event_type: str, target: ChildState, **details: Any) -> None:
        state["state"] = target.value
        state["events"].append(
            {
                "sequence": len(state["events"]) + 1,
                "event_type": event_type,
                "state": target.value,
                **details,
            }
        )


class ParentBudgetGate:
    """Crash-safe logical-request and authorized-spend reservation gate."""

    def __init__(self, state_path: Path):
        self._store = _DurableJson(state_path, PARENT_SCHEMA, self._initial)

    @staticmethod
    def _initial() -> dict[str, Any]:
        return {
            "schema_version": PARENT_SCHEMA,
            "attempts_reserved": 0,
            "authorized_spend_usd": "0",
            "reservations": [],
            "denials": [],
            "price_schedule_id": PRICE_SCHEDULE_ID,
        }

    def snapshot(self) -> dict[str, Any]:
        with self._store.locked():
            return copy.deepcopy(self._store.read())

    @staticmethod
    def validate(request: ParentRequest) -> None:
        if request.provider != PARENT_PROVIDER or request.model != PARENT_MODEL:
            raise ParentDenied("BLOCK_COST: unexpected parent provider/model route")
        if not request.agent_loop or request.purpose is not None:
            raise ParentDenied("BLOCK_COST: auxiliary or non-agent-loop route denied")
        if request.provider_internal_retries != 0:
            raise ParentDenied("BLOCK_COST: provider internal retries must equal zero")
        if not isinstance(request.max_output_tokens, int) or not 0 < request.max_output_tokens <= MAX_OUTPUT_TOKENS:
            raise ParentDenied(f"BLOCK_COST: max output tokens must be within 1..{MAX_OUTPUT_TOKENS}")
        if (
            not isinstance(request.input_token_upper_bound, int)
            or request.input_token_upper_bound < 0
            or request.input_token_upper_bound > MAX_INPUT_TOKEN_UPPER_BOUND
        ):
            raise ParentDenied(
                f"BLOCK_COST: input token upper bound exceeds {MAX_INPUT_TOKEN_UPPER_BOUND}"
            )

    @staticmethod
    def authorized_cost(input_token_upper_bound: int) -> Decimal:
        input_cost = Decimal(input_token_upper_bound) * INPUT_USD_PER_MILLION / Decimal(1_000_000)
        output_cost = Decimal(MAX_OUTPUT_TOKENS) * OUTPUT_USD_PER_MILLION / Decimal(1_000_000)
        return (input_cost + output_cost) * PRICE_UNCERTAINTY_MULTIPLIER

    def reserve(self, request: ParentRequest) -> ParentReservation:
        self.validate(request)
        with self._store.locked():
            state = self._store.read()
            if state.get("price_schedule_id") != PRICE_SCHEDULE_ID:
                raise ParentDenied("BLOCK_COST: price schedule identity drift")
            attempt = int(state["attempts_reserved"]) + 1
            current_spend = Decimal(str(state["authorized_spend_usd"]))
            request_cost = self.authorized_cost(request.input_token_upper_bound)
            next_spend = current_spend + request_cost
            denial: str | None = None
            if attempt > MAX_PARENT_REQUEST_ATTEMPTS:
                denial = "ATTEMPT_CEILING"
            elif next_spend > PARENT_OPENAI_AUTHORIZED_SPEND_CAP_USD:
                denial = "AUTHORIZED_SPEND_CAP"
            if denial is not None:
                state["denials"].append(
                    {
                        "attempt": attempt,
                        "reason": denial,
                        "would_reserve_usd": str(request_cost),
                        "would_total_usd": str(next_spend),
                    }
                )
                self._store.write(state)
                raise ParentDenied(f"BLOCK_COST: {denial} before adapter I/O")
            reservation = ParentReservation(
                attempt=attempt,
                input_token_upper_bound=request.input_token_upper_bound,
                output_tokens_reserved=MAX_OUTPUT_TOKENS,
                authorized_cost_usd=str(request_cost),
                cumulative_authorized_spend_usd=str(next_spend),
                price_schedule_id=PRICE_SCHEDULE_ID,
            )
            state["attempts_reserved"] = attempt
            state["authorized_spend_usd"] = str(next_spend)
            state["reservations"].append(asdict(reservation))
            self._store.write(state)
            return reservation


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_exclusive_json(path: Path, value: Mapping[str, Any]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        # Never compensate by deleting a partial claim artifact.
        raise
    _fsync_directory(path.parent)


class EpisodeClaim:
    """Create-only remote Git ref plus local O_EXCL receipt.

    An intent is durably written first.  Consequently every crash, timeout,
    partial result, or ambiguous push leaves evidence that blocks replay.
    """

    def __init__(self, state_dir: Path, *, remote: str, ref: str, source_repo: Path):
        self.state_dir = Path(state_dir)
        self.remote = remote
        self.ref = ref
        self.source_repo = Path(source_repo)
        self.intent_path = self.state_dir / "claim-intent.json"
        self.receipt_path = self.state_dir / "claim-receipt.json"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        if not ref.startswith("refs/heads/qntylab-claims/"):
            raise ClaimBlocked("claim ref is outside the create-only QntyLab claim namespace")

    def acquire(
        self,
        *,
        session_nonce: str,
        fault: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        if not session_nonce:
            raise ClaimBlocked("claim session nonce is empty")
        lock_path = self.state_dir / "claim.lock"
        with lock_path.open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                return self._acquire_locked(session_nonce=session_nonce, fault=fault)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _acquire_locked(
        self,
        *,
        session_nonce: str,
        fault: Callable[[str], None] | None,
    ) -> dict[str, Any]:
        local_present = self.intent_path.exists() or self.receipt_path.exists()
        remote_present = self.remote_exists()
        if local_present or remote_present:
            raise ClaimBlocked("BLOCK_NEVER_REPLAY: pre-existing, partial, or ambiguous claim state")
        source_head = self._git("rev-parse", "HEAD").stdout.strip()
        intent = {
            "schema_version": CLAIM_SCHEMA,
            "session_nonce": session_nonce,
            "remote": self.remote,
            "ref": self.ref,
            "source_head": source_head,
            "state": "INTENT_DURABLE",
        }
        _write_exclusive_json(self.intent_path, intent)
        if fault is not None:
            fault("after_intent")
        command = [
            "git",
            "-C",
            str(self.source_repo),
            "push",
            "--porcelain",
            f"--force-with-lease={self.ref}:",
            self.remote,
            f"{source_head}:{self.ref}",
        ]
        try:
            pushed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ClaimBlocked("BLOCK_NEVER_REPLAY: ambiguous remote claim result") from exc
        if pushed.returncode != 0:
            raise ClaimBlocked(
                "BLOCK_NEVER_REPLAY: remote create-only claim failed: "
                + (pushed.stderr or pushed.stdout).strip()
            )
        if fault is not None:
            fault("after_remote")
        receipt = {
            **intent,
            "state": "REMOTE_AND_LOCAL_COMPLETE",
            "remote_push_porcelain": pushed.stdout.strip(),
        }
        _write_exclusive_json(self.receipt_path, receipt)
        if fault is not None:
            fault("after_local")
        return receipt

    def remote_exists(self) -> bool:
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", self.remote, self.ref],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return True
        if result.returncode == 2:
            return False
        raise ClaimBlocked("BLOCK_NEVER_REPLAY: remote claim presence is ambiguous")

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", "-C", str(self.source_repo), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise ClaimBlocked(f"claim source Git command failed: {' '.join(args)}")
        return result


def _grant_from_args(args: argparse.Namespace) -> ChildGrant:
    return ChildGrant(args.token, args.tool, args.role)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qntylab.dsh_stage_a_v1r3r2_prelive_enforcement")
    sub = parser.add_subparsers(dest="command", required=True)

    child_authorize = sub.add_parser("authorize-child")
    child_authorize.add_argument("--state", required=True)
    child_authorize.add_argument("--tool", required=True)
    child_authorize.add_argument("--provider", required=True)
    child_authorize.add_argument("--background", action="store_true")

    child_complete = sub.add_parser("complete-child")
    child_complete.add_argument("--state", required=True)
    child_complete.add_argument("--token", required=True)
    child_complete.add_argument("--tool", required=True)
    child_complete.add_argument("--role", required=True)
    child_complete.add_argument("--status", default="CHILD_COMPLETED")
    child_complete.add_argument("--review-json")

    parent = sub.add_parser("reserve-parent")
    parent.add_argument("--state", required=True)
    parent.add_argument("--provider", required=True)
    parent.add_argument("--model", required=True)
    parent.add_argument("--agent-loop", required=True)
    parent.add_argument("--purpose")
    parent.add_argument("--max-output-tokens", required=True, type=int)
    parent.add_argument("--input-token-upper-bound", required=True, type=int)
    parent.add_argument("--provider-internal-retries", required=True, type=int)

    claim = sub.add_parser("claim")
    claim.add_argument("--state-dir", required=True)
    claim.add_argument("--remote", required=True)
    claim.add_argument("--ref", required=True)
    claim.add_argument("--source-repo", required=True)
    claim.add_argument("--session-nonce", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "authorize-child":
            grant = StageAChildController(Path(args.state)).authorize(
                args.tool,
                provider_name=args.provider,
                background=args.background,
            )
            print(json.dumps(asdict(grant), sort_keys=True))
        elif args.command == "complete-child":
            review = json.loads(args.review_json) if args.review_json is not None else None
            controller = StageAChildController(Path(args.state))
            controller.complete(
                _grant_from_args(args),
                review_result=review,
                status=args.status,
            )
            print(json.dumps(controller.snapshot(), sort_keys=True))
        elif args.command == "reserve-parent":
            reservation = ParentBudgetGate(Path(args.state)).reserve(
                ParentRequest(
                    provider=args.provider,
                    model=args.model,
                    agent_loop=args.agent_loop == "true",
                    purpose=args.purpose,
                    max_output_tokens=args.max_output_tokens,
                    input_token_upper_bound=args.input_token_upper_bound,
                    provider_internal_retries=args.provider_internal_retries,
                )
            )
            print(json.dumps(asdict(reservation), sort_keys=True))
        else:
            receipt = EpisodeClaim(
                Path(args.state_dir),
                remote=args.remote,
                ref=args.ref,
                source_repo=Path(args.source_repo),
            ).acquire(session_nonce=args.session_nonce)
            print(json.dumps(receipt, sort_keys=True))
        return 0
    except (EnforcementBlocked, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"qntylab prelive gate denied: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
