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
import re
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
from urllib.parse import urlsplit


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
CLAIM_NAMESPACE = "refs/heads/qntylab-claims/"
DIAGNOSTIC_CLAIM_NAMESPACE = "refs/heads/qntylab-diagnostics/claim-transport-v0/"
CLAIM_OUTCOMES = frozenset(
    {"COMMITTED", "CONFIRMED_NO_REMOTE_WRITE", "WRITE_STATE_UNKNOWN"}
)
CLAIM_DIAGNOSTIC_FIELDS = (
    "repository_identity",
    "credential_free_remote_identity",
    "target_ref",
    "expected_source_sha",
    "operation_stage",
    "process_exit_code",
    "timeout",
    "sanitized_stderr",
    "sanitized_stdout_if_useful",
    "remote_ref_state_before",
    "remote_ref_state_after",
    "expected_sha",
    "observed_sha",
    "local_intent_state",
    "local_receipt_state",
    "classification",
    "reason_code",
)


class EnforcementBlocked(RuntimeError):
    """A pre-dispatch invariant could not be proven."""


class ChildDenied(EnforcementBlocked):
    """The requested native child transition is illegal."""


class ParentDenied(EnforcementBlocked):
    """The requested parent adapter dispatch is illegal or over budget."""


class ClaimBlocked(EnforcementBlocked):
    """The episode claim is present, partial, ambiguous, or could not be made."""


def redact_diagnostic_text(value: str) -> str:
    """Redact credential-shaped values without retaining environment/config data."""

    redacted = str(value)
    redacted = re.sub(
        r"(?i)(https?://)([^/\s:@]+):([^/\s@]+)@",
        r"\1<REDACTED>@",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b(authorization|proxy-authorization)\s*:\s*(?:bearer|basic)\s+\S+",
        r"\1: <REDACTED>",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+",
        r"\1 <REDACTED>",
        redacted,
    )
    redacted = re.sub(
        r"(?i)([?&](?:access_token|api[_-]?key|auth|password|passwd|secret|token)=)[^&\s]+",
        r"\1<REDACTED>",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*([^\s,;}]+)",
        r"\1=<REDACTED>",
        redacted,
    )
    return redacted


def credential_free_remote_identity(remote: str) -> str:
    """Return a stable remote identity without userinfo, query, or fragments."""

    candidate = str(remote)
    parsed = urlsplit(candidate)
    if parsed.scheme and parsed.hostname:
        host = parsed.hostname
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        return f"{parsed.scheme}://{host}{parsed.path}"
    return redact_diagnostic_text(candidate.split("?", 1)[0].split("#", 1)[0])


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
    ``acquire_with_outcome`` adds evidence-calibrated transport classification;
    ``acquire`` retains the historic exception-based caller contract.
    """

    def __init__(
        self,
        state_dir: Path,
        *,
        remote: str,
        ref: str,
        source_repo: Path,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ):
        self.state_dir = Path(state_dir)
        self.remote = remote
        self.ref = ref
        self.source_repo = Path(source_repo)
        self.intent_path = self.state_dir / "claim-intent.json"
        self.receipt_path = self.state_dir / "claim-receipt.json"
        self._command_runner = command_runner or subprocess.run
        self._last_remote_observation: dict[str, Any] | None = None
        self.state_dir.mkdir(parents=True, exist_ok=True)
        if not (
            ref.startswith(CLAIM_NAMESPACE)
            or ref.startswith(DIAGNOSTIC_CLAIM_NAMESPACE)
        ):
            raise ClaimBlocked("claim ref is outside the create-only QntyLab claim namespace")

    def acquire(
        self,
        *,
        session_nonce: str,
        fault: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        outcome = self.acquire_with_outcome(
            session_nonce=session_nonce,
            fault=fault,
        )
        if outcome["classification"] != "COMMITTED" or "receipt" not in outcome:
            detail = outcome.get("detail") or outcome["reason_code"]
            raise ClaimBlocked(f"BLOCK_NEVER_REPLAY: {detail}")
        return outcome["receipt"]

    def acquire_with_outcome(
        self,
        *,
        session_nonce: str,
        fault: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Attempt one claim and return a deterministic, sanitized outcome.

        ``WRITE_STATE_UNKNOWN`` is deliberately returned instead of raising for
        transport ambiguity so callers can retain evidence and still fail
        closed.  The legacy ``acquire`` method converts every non-complete
        outcome into ``ClaimBlocked``.
        """

        if not session_nonce:
            raise ClaimBlocked("claim session nonce is empty")
        lock_path = self.state_dir / "claim.lock"
        with lock_path.open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                return self._acquire_locked_with_outcome(
                    session_nonce=session_nonce,
                    fault=fault,
                )
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _acquire_locked(
        self,
        *,
        session_nonce: str,
        fault: Callable[[str], None] | None,
    ) -> dict[str, Any]:
        """Compatibility wrapper for older internal callers."""

        outcome = self._acquire_locked_with_outcome(
            session_nonce=session_nonce,
            fault=fault,
        )
        if outcome["classification"] != "COMMITTED" or "receipt" not in outcome:
            detail = outcome.get("detail") or outcome["reason_code"]
            raise ClaimBlocked(f"BLOCK_NEVER_REPLAY: {detail}")
        return outcome["receipt"]

    def _acquire_locked_with_outcome(
        self,
        *,
        session_nonce: str,
        fault: Callable[[str], None] | None,
    ) -> dict[str, Any]:
        local_present = self.intent_path.exists() or self.receipt_path.exists()
        try:
            remote_present = self.remote_exists()
            before = self._last_remote_observation or self._remote_state(
                "ABSENT" if not remote_present else "PRESENT"
            )
        except ClaimBlocked as exc:
            before = self._last_remote_observation or self._remote_state("UNKNOWN")
            return self._outcome(
                classification="WRITE_STATE_UNKNOWN",
                reason_code="REMOTE_PRESENCE_AMBIGUOUS",
                detail=str(exc),
                expected_sha=None,
                before=before,
                after=before,
                process_exit_code=before.get("process_exit_code"),
                timeout=bool(before.get("timeout")),
                operation_stage="PRECHECK",
            )

        source_head = self._git("rev-parse", "HEAD").stdout.strip()
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", source_head):
            raise ClaimBlocked("claim source Git command returned an invalid HEAD SHA")

        if local_present:
            return self._outcome(
                classification="WRITE_STATE_UNKNOWN",
                reason_code="LOCAL_CLAIM_STATE_PRESENT",
                detail="pre-existing, partial, or ambiguous local claim state",
                expected_sha=source_head,
                before=before,
                after=before,
                process_exit_code=before.get("process_exit_code"),
                timeout=bool(before.get("timeout")),
                operation_stage="PRECHECK",
            )

        if remote_present:
            if before.get("sha") == source_head:
                return self._outcome(
                    classification="COMMITTED",
                    reason_code="REMOTE_ALREADY_COMMITTED",
                    detail="remote claim already points to the expected source SHA; no overwrite attempted",
                    expected_sha=source_head,
                    before=before,
                    after=before,
                    process_exit_code=None,
                    timeout=False,
                    operation_stage="PRECHECK",
                )
            return self._outcome(
                classification="WRITE_STATE_UNKNOWN",
                reason_code="REMOTE_REF_COLLISION",
                detail="remote claim ref exists at a different SHA; create-only invariant blocks overwrite",
                expected_sha=source_head,
                before=before,
                after=before,
                process_exit_code=None,
                timeout=False,
                operation_stage="PRECHECK",
            )

        intent = {
            "schema_version": CLAIM_SCHEMA,
            "session_nonce": session_nonce,
            "remote": credential_free_remote_identity(self.remote),
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
        pushed: subprocess.CompletedProcess[str] | None = None
        process_exit_code: int | None = None
        timed_out = False
        transport_detail = ""
        transport_stdout = ""
        transport_stderr = ""
        try:
            pushed = self._run_command(command)
            process_exit_code = pushed.returncode
            transport_stdout = pushed.stdout or ""
            transport_stderr = pushed.stderr or ""
            transport_detail = (pushed.stderr or pushed.stdout or "").strip()
            if pushed.returncode != 0:
                transport_detail = (
                    "remote create-only claim failed: " + transport_detail
                )
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            transport_detail = "remote create-only claim timed out: " + str(exc)
            transport_stderr = str(exc)
        except OSError as exc:
            transport_detail = "remote create-only claim failed: " + str(exc)
            transport_stderr = str(exc)

        if pushed is not None and pushed.returncode == 0 and fault is not None:
            fault("after_remote")

        after = self.remote_ref_state()
        after_sha = after.get("sha")
        if (
            after.get("state") == "PRESENT"
            and after_sha == source_head
            and pushed is not None
            and pushed.returncode == 0
        ):
            receipt = {
                **intent,
                "state": "REMOTE_AND_LOCAL_COMPLETE",
                "remote_push_porcelain": redact_diagnostic_text(
                    (pushed.stdout if pushed is not None else "").strip()
                ),
            }
            _write_exclusive_json(self.receipt_path, receipt)
            if fault is not None:
                fault("after_local")
            return self._outcome(
                classification="COMMITTED",
                reason_code=(
                    "REMOTE_REF_CONFIRMED_EXPECTED_SHA"
                    if pushed is not None and pushed.returncode == 0
                    else "REMOTE_REF_CONFIRMED_AFTER_NONZERO_TRANSPORT"
                ),
                detail=transport_detail,
                expected_sha=source_head,
                before=before,
                after=after,
                process_exit_code=process_exit_code,
                timeout=timed_out,
                operation_stage="LOCAL_RECEIPT",
                transport_stdout=transport_stdout,
                transport_stderr=transport_stderr,
                receipt=receipt,
            )

        if after.get("state") == "PRESENT" and after_sha == source_head:
            return self._outcome(
                classification="WRITE_STATE_UNKNOWN",
                reason_code="REMOTE_REF_CONFIRMED_BUT_ATTEMPT_NOT_CONFIRMED",
                detail=(
                    transport_detail
                    or "remote ref has the expected SHA, but this create-only attempt did not report success"
                ),
                expected_sha=source_head,
                before=before,
                after=after,
                process_exit_code=process_exit_code,
                timeout=timed_out,
                operation_stage="REMOTE_VERIFY",
                transport_stdout=transport_stdout,
                transport_stderr=transport_stderr,
            )

        if (
            before.get("state") == "ABSENT"
            and after.get("state") == "ABSENT"
            and (pushed is None or pushed.returncode != 0)
        ):
            return self._outcome(
                classification="CONFIRMED_NO_REMOTE_WRITE",
                reason_code="REMOTE_REF_ABSENT_BEFORE_AND_AFTER_FAILED_ATTEMPT",
                detail=(transport_detail or "remote create-only claim failed"),
                expected_sha=source_head,
                before=before,
                after=after,
                process_exit_code=process_exit_code,
                timeout=timed_out,
                operation_stage="REMOTE_VERIFY",
                transport_stdout=transport_stdout,
                transport_stderr=transport_stderr,
            )

        return self._outcome(
            classification="WRITE_STATE_UNKNOWN",
            reason_code="REMOTE_WRITE_OUTCOME_AMBIGUOUS",
            detail=(transport_detail or "remote claim write and independent verification disagree"),
            expected_sha=source_head,
            before=before,
            after=after,
            process_exit_code=process_exit_code,
            timeout=timed_out,
            operation_stage="REMOTE_VERIFY",
        )

    def _outcome(
        self,
        *,
        classification: str,
        reason_code: str,
        detail: str,
        expected_sha: str | None,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        process_exit_code: int | None,
        timeout: bool,
        operation_stage: str,
        transport_stdout: str | None = None,
        transport_stderr: str | None = None,
        receipt: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if classification not in CLAIM_OUTCOMES:
            raise ValueError(f"unsupported claim classification: {classification}")
        local_intent_state = "PRESENT" if self.intent_path.exists() else "ABSENT"
        local_receipt_state = "PRESENT" if self.receipt_path.exists() else "ABSENT"
        diagnostic = {
            "repository_identity": f"{self.source_repo.resolve()}@{expected_sha or 'UNKNOWN'}",
            "credential_free_remote_identity": credential_free_remote_identity(self.remote),
            "target_ref": self.ref,
            "expected_source_sha": expected_sha,
            "operation_stage": operation_stage,
            "process_exit_code": process_exit_code,
            "timeout": timeout,
            "sanitized_stderr": redact_diagnostic_text(
                str(
                    after.get("stderr", "")
                    if transport_stderr is None
                    else transport_stderr
                )
            ),
            "sanitized_stdout_if_useful": redact_diagnostic_text(
                str(
                    after.get("stdout", "")
                    if transport_stdout is None
                    else transport_stdout
                )
            ),
            "remote_ref_state_before": dict(before),
            "remote_ref_state_after": dict(after),
            "expected_sha": expected_sha,
            "observed_sha": after.get("sha"),
            "local_intent_state": local_intent_state,
            "local_receipt_state": local_receipt_state,
            "classification": classification,
            "reason_code": reason_code,
        }
        # Keep the contract mechanically visible if this evolves.
        if tuple(diagnostic)[: len(CLAIM_DIAGNOSTIC_FIELDS)] != CLAIM_DIAGNOSTIC_FIELDS:
            raise AssertionError("claim diagnostic field order drifted")
        result: dict[str, Any] = {
            "classification": classification,
            "reason_code": reason_code,
            "detail": redact_diagnostic_text(detail),
            "fail_closed": classification == "WRITE_STATE_UNKNOWN",
            "execution_authority_granted": False,
            "production_retry_granted": False,
            "diagnostic": diagnostic,
        }
        if receipt is not None:
            result["receipt"] = dict(receipt)
        return result

    def remote_ref_state(self) -> dict[str, Any]:
        """Read the exact target ref, retaining enough evidence to classify it."""

        return self._remote_ref_state()

    def _remote_ref_state(self) -> dict[str, Any]:
        try:
            result = self._run_command(
                ["git", "ls-remote", "--exit-code", self.remote, self.ref]
            )
        except subprocess.TimeoutExpired as exc:
            observation = self._remote_state(
                "UNKNOWN",
                process_exit_code=None,
                timeout=True,
                stderr=str(exc),
            )
            self._last_remote_observation = observation
            return observation
        except OSError as exc:
            observation = self._remote_state(
                "UNKNOWN",
                process_exit_code=None,
                timeout=False,
                stderr=str(exc),
            )
            self._last_remote_observation = observation
            return observation

        stdout = result.stdout or ""
        stderr = result.stderr or ""
        rows = [line.split() for line in stdout.splitlines() if line.split()]
        matching = [row for row in rows if len(row) >= 2 and row[1] == self.ref]
        if result.returncode == 0 and len(matching) == 1 and re.fullmatch(
            r"[0-9a-fA-F]{40,64}", matching[0][0]
        ):
            state = "PRESENT"
            sha = matching[0][0]
        elif result.returncode == 2 and not rows:
            state = "ABSENT"
            sha = None
        else:
            state = "UNKNOWN"
            sha = None
        observation = self._remote_state(
            state,
            sha=sha,
            process_exit_code=result.returncode,
            timeout=False,
            stdout=stdout,
            stderr=stderr,
        )
        self._last_remote_observation = observation
        return observation

    @staticmethod
    def _remote_state(
        state: str,
        *,
        sha: str | None = None,
        process_exit_code: int | None = None,
        timeout: bool = False,
        stdout: str = "",
        stderr: str = "",
    ) -> dict[str, Any]:
        return {
            "state": state,
            "sha": sha,
            "process_exit_code": process_exit_code,
            "timeout": timeout,
            "stdout": redact_diagnostic_text(stdout),
            "stderr": redact_diagnostic_text(stderr),
        }

    def remote_exists(self) -> bool:
        observation = self.remote_ref_state()
        if observation["state"] == "PRESENT":
            return True
        if observation["state"] == "ABSENT":
            return False
        raise ClaimBlocked("BLOCK_NEVER_REPLAY: remote claim presence is ambiguous")

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        result = self._run_command(["git", "-C", str(self.source_repo), *args])
        if result.returncode != 0:
            raise ClaimBlocked(f"claim source Git command failed: {' '.join(args)}")
        return result

    def _run_command(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return self._command_runner(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )


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
