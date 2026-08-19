"""Bounded, lab-only diagnostic for the subscription-backed Codex app-server write path.

The module answers exactly one mechanical question: at which execution layer
does a trivial Profile-A workspace write first diverge from a known-good path?

It owns app-server process launch, bounded JSON-RPC transport, sanitized
observation, effective-policy extraction, workspace before/after machine truth,
and first-divergence classification.  It has no scientific, runtime, trading,
or capital authority, and it never mutates anything outside a disposable
workspace it created itself.

Sanitization contract: the trace records method names, parameter *key* names,
item/status classes, policy classes, paths, digests, and process disposal.  It
never records credentials, auth payloads, assistant prose, or raw stderr.
"""

from __future__ import annotations

import hashlib
import json
import queue
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from qntylab.subscription_backed_product_execution_plumbing_v0 import (
    QualificationError,
    canonical_json,
    changed_paths,
    sanitize_environment,
    sha256_bytes,
    snapshot_digest,
    utc_now,
    workspace_snapshot,
)

CODEX_BINARY = "/home/swirky/.local/bin/codex"
CODEX_HOME = "/home/swirky/.codex"
APP_SERVER_SUBCOMMAND = ("app-server", "--stdio")

CLIENT_NAME = "qntylab-codex-app-server-write-path-diagnostic"
CLIENT_VERSION = "0"

FIXTURE_NAME = "fixture.txt"
FIXTURE_BEFORE_BYTES = b"BEFORE\n"
FIXTURE_AFTER_BYTES = b"AFTER\n"

WRITE_PROMPT = (
    "In this disposable diagnostic repository, replace the exact contents of\n"
    "fixture.txt with:\n"
    "\n"
    "AFTER\n"
    "\n"
    "Do not modify any other file.\n"
    "Do not ask questions.\n"
    "Do not perform unrelated work.\n"
    "Stop after making that filesystem change.\n"
)
NO_TOOL_PROMPT = "Reply with exactly APP_SERVER_OK and do not use tools."
NO_TOOL_EXPECTED_TEXT = "APP_SERVER_OK"

DEFAULT_TURN_TIMEOUT_SECONDS = 300.0
DEFAULT_HANDSHAKE_TIMEOUT_SECONDS = 60.0

# Terminal distinctions required by the diagnostic contract.  A class is only
# emitted when the observed evidence mechanically supports it.
TERMINAL_CLASSES = (
    "STARTUP_FAILURE",
    "AUTH_FAILURE",
    "TURN_FAILED",
    "TURN_INTERRUPTED",
    "TURN_TIMEOUT",
    "APPROVAL_DENIED",
    "PERMISSION_DENIED",
    "WRITE_NOT_ATTEMPTED",
    "WRITE_ATTEMPT_OBSERVED",
    "WRITE_EFFECT_OBSERVED",
    "COMPLETED_NO_WRITE",
    "COMPLETED_WITH_WRITE",
)

# Server->client requests this diagnostic answers deterministically and
# unattended.  Every one is non-escalating: the diagnostic never grants a
# capability that the declared policy did not already provide.
APPROVAL_METHODS = {
    "item/commandExecution/requestApproval": "COMMAND_EXECUTION",
    "item/fileChange/requestApproval": "FILE_CHANGE",
    "item/permissions/requestApproval": "PERMISSIONS",
    "applyPatchApproval": "LEGACY_APPLY_PATCH",
    "execCommandApproval": "LEGACY_EXEC_COMMAND",
}
_UNATTENDED_REJECTION = "unattended write-path diagnostic declines escalation"

_ERROR_TEXT_LIMIT = 300


class AppServerTimeout(RuntimeError):
    """A bounded transport deadline elapsed before the awaited event."""


class _StartupAborted(RuntimeError):
    """Internal signal: the child never started, so no turn can be attempted."""


def classify_fixture_bytes(data: bytes) -> str:
    """Classify exact fixture bytes, tolerating one optional trailing newline.

    Only bytes decide.  Assistant prose never reaches this function.
    """

    normalized = data[:-1] if data.endswith(b"\n") else data
    if normalized == b"BEFORE":
        return "BEFORE"
    if normalized == b"AFTER":
        return "AFTER"
    return "OTHER"


def build_workspace(root: Path) -> Path:
    """Create one fresh byte-identical disposable Git workspace.

    Reset is by construction, never by editing a mutated workspace back.
    """

    root = Path(root)
    if root.exists():
        raise QualificationError("diagnostic workspace must not already exist")
    root.mkdir(parents=True)
    (root / FIXTURE_NAME).write_bytes(FIXTURE_BEFORE_BYTES)
    identity = (
        "-c", "user.name=QntyLab Diagnostic",
        "-c", "user.email=diagnostic@qntylab.invalid",
        "-c", "commit.gpgsign=false",
    )
    for argv in (
        ("git", "init", "-q", "-b", "main"),
        ("git", *identity, "add", FIXTURE_NAME),
        ("git", *identity, "commit", "-q", "-m", "diagnostic fixture"),
    ):
        completed = subprocess.run(argv, cwd=root, capture_output=True, check=False)
        if completed.returncode != 0:
            raise QualificationError(f"disposable workspace setup failed: {argv[0]} {argv[-1]}")
    return root


def destroy_workspace(root: Path) -> None:
    """Destroy a disposable workspace; never restore one in place."""

    root = Path(root)
    if root.exists():
        shutil.rmtree(root)


def fixture_state(root: Path) -> dict[str, Any]:
    """Machine truth for the fixture file: existence, exact digest, class."""

    path = Path(root) / FIXTURE_NAME
    if not path.is_file():
        return {"present": False, "sha256": None, "byte_length": None, "class": "ABSENT"}
    data = path.read_bytes()
    return {
        "present": True,
        "sha256": sha256_bytes(data),
        "byte_length": len(data),
        "class": classify_fixture_bytes(data),
    }


def _keys(value: Any) -> list[str]:
    return sorted(str(key) for key in value) if isinstance(value, Mapping) else []


_SECRET_SHAPED = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|[A-Za-z0-9_\-]{32,})")


def _scrub(text: str) -> str:
    """Replace credential-shaped runs before any product text is recorded."""

    return _SECRET_SHAPED.sub("[REDACTED]", text)


def _truncate(text: Any) -> str | None:
    if not isinstance(text, str):
        return None
    return _scrub(text[:_ERROR_TEXT_LIMIT])


def _hashed_id(value: Any) -> str | None:
    return sha256_bytes(str(value).encode()) if isinstance(value, str) and value else None


def sandbox_policy_class(value: Any) -> str:
    """Reduce a sandbox policy/mode to a recordable class name."""

    if isinstance(value, Mapping):
        return str(value.get("type", "UNKNOWN_OBJECT"))
    if isinstance(value, str):
        return value
    return "ABSENT"


def approval_policy_class(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return "granular" if "granular" in value else "UNKNOWN_OBJECT"
    return "ABSENT"


@dataclass(frozen=True)
class TraceEvent:
    at: str
    direction: str
    kind: str
    method: str | None
    param_keys: tuple[str, ...]
    detail: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "direction": self.direction,
            "kind": self.kind,
            "method": self.method,
            "param_keys": list(self.param_keys),
            "detail": dict(self.detail),
        }


@dataclass
class TraceRecorder:
    """Append-only sanitized trace."""

    route: str
    events: list[TraceEvent] = field(default_factory=list)

    def record(
        self,
        direction: str,
        kind: str,
        method: str | None,
        param_keys: Sequence[str],
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        self.events.append(
            TraceEvent(utc_now(), direction, kind, method, tuple(param_keys), dict(detail or {}))
        )

    def methods(self, kind: str) -> list[str]:
        return [event.method for event in self.events if event.kind == kind and event.method]

    def write_jsonl(self, path: Path, *, append: bool = True) -> None:
        mode = "a" if append else "w"
        with Path(path).open(mode, encoding="utf-8") as handle:
            for event in self.events:
                payload = {"route": self.route, **event.as_dict()}
                handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


class AppServerClient:
    """Bounded newline-delimited JSON-RPC client for `codex app-server --stdio`.

    Dedicated reader threads drain stdout and stderr so a chatty child can never
    deadlock the diagnostic on a full pipe.
    """

    def __init__(
        self,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str],
        recorder: TraceRecorder,
    ) -> None:
        self.argv = tuple(argv)
        self.cwd = Path(cwd)
        self.env = dict(env)
        self.recorder = recorder
        self._proc: subprocess.Popen[bytes] | None = None
        self._messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._responses: dict[int, Mapping[str, Any]] = {}
        self._next_id = 0
        self._stream_closed = False
        self._stderr_digest = hashlib.sha256()
        self._stderr_bytes = 0
        self._non_json_lines = 0
        self.approval_events: list[dict[str, Any]] = []
        self.unsupported_server_requests: list[str] = []
        self.turn_events: list[dict[str, Any]] = []
        self.item_events: list[dict[str, Any]] = []
        self.error_notifications: list[dict[str, Any]] = []
        self.agent_messages: list[dict[str, Any]] = []
        self.thread_id: str | None = None
        self.turn_id: str | None = None

    # -- process lifecycle -------------------------------------------------

    def start(self) -> None:
        try:
            self._proc = subprocess.Popen(
                list(self.argv),
                cwd=str(self.cwd),
                env=self.env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise QualificationError(f"app-server could not start: {exc}") from exc
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        self.recorder.record(
            "PROCESS", "LIFECYCLE", None, [],
            {"event": "SPAWNED", "argv": list(self.argv), "cwd": str(self.cwd)},
        )

    def _read_stdout(self) -> None:
        stdout = self._proc.stdout if self._proc else None
        if stdout is None:
            return
        for line in stdout:
            text = line.decode("utf-8", "replace").strip()
            if not text:
                continue
            try:
                self._messages.put(("MESSAGE", json.loads(text)))
            except json.JSONDecodeError:
                self._messages.put(("NON_JSON", len(line)))
        self._messages.put(("EOF", None))

    def _drain_stderr(self) -> None:
        stderr = self._proc.stderr if self._proc else None
        if stderr is None:
            return
        for chunk in iter(lambda: stderr.read(4096), b""):
            self._stderr_bytes += len(chunk)
            self._stderr_digest.update(chunk)

    def close(self, *, grace_seconds: float = 10.0) -> dict[str, Any]:
        if self._proc is None:
            return {"disposed": False}
        proc = self._proc
        if proc.stdin and not proc.stdin.closed:
            try:
                proc.stdin.close()
            except OSError:
                pass
        termination = "ALREADY_EXITED"
        if proc.poll() is None:
            proc.terminate()
            termination = "SIGTERM"
            try:
                proc.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                proc.kill()
                termination = "SIGKILL"
                proc.wait(timeout=grace_seconds)
        code = proc.returncode
        disposal = {
            "disposed": True,
            "termination": termination,
            "exit_code": code if isinstance(code, int) and code >= 0 else None,
            "exit_signal": -code if isinstance(code, int) and code < 0 else None,
            "stderr_bytes": self._stderr_bytes,
            "stderr_sha256": self._stderr_digest.hexdigest(),
            "non_json_stdout_lines": self._non_json_lines,
        }
        self.recorder.record("PROCESS", "LIFECYCLE", None, [], {"event": "DISPOSED", **disposal})
        return disposal

    @property
    def exited(self) -> bool:
        return self._proc is not None and self._proc.poll() is not None

    # -- transport ---------------------------------------------------------

    def _send(self, payload: Mapping[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise QualificationError("app-server stdin is unavailable")
        line = json.dumps(payload, separators=(",", ":")).encode() + b"\n"
        try:
            self._proc.stdin.write(line)
            self._proc.stdin.flush()
        except (BrokenPipeError, ValueError) as exc:
            raise QualificationError(f"app-server stdin closed: {type(exc).__name__}") from exc

    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = dict(params)
        self._send(payload)
        self.recorder.record("CLIENT_TO_SERVER", "NOTIFICATION", method, _keys(params))

    def request(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        deadline: float,
        detail: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)})
        self.recorder.record("CLIENT_TO_SERVER", "REQUEST", method, _keys(params), detail or {})
        self.pump(deadline=deadline, until=lambda: request_id in self._responses)
        message = self._responses.pop(request_id, None)
        if message is None:
            outcome = {
                "ok": False,
                "result": None,
                "error_code": None,
                "error_message": None,
                "transport": "STREAM_CLOSED_BEFORE_RESPONSE" if self._stream_closed else "NO_RESPONSE",
            }
            self.recorder.record("SERVER_TO_CLIENT", "RESPONSE", method, [], outcome)
            return outcome
        if "error" in message and message["error"] is not None:
            error = message["error"] if isinstance(message["error"], Mapping) else {}
            outcome = {
                "ok": False,
                "result": None,
                "error_code": error.get("code"),
                "error_message": _truncate(error.get("message")),
                "transport": "JSONRPC_ERROR",
            }
            self.recorder.record("SERVER_TO_CLIENT", "RESPONSE", method, [], outcome)
            return outcome
        result = message.get("result")
        outcome = {
            "ok": True,
            "result": result if isinstance(result, Mapping) else {},
            "error_code": None,
            "error_message": None,
            "transport": "OK",
        }
        self.recorder.record(
            "SERVER_TO_CLIENT", "RESPONSE", method, _keys(result), {"ok": True}
        )
        return outcome

    def pump(self, *, deadline: float, until: Callable[[], bool]) -> None:
        """Drive the message loop until `until` holds, the stream closes, or the deadline elapses."""

        while True:
            if until():
                return
            if self._stream_closed and self._messages.empty():
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AppServerTimeout("bounded app-server deadline elapsed")
            try:
                kind, payload = self._messages.get(timeout=min(remaining, 0.25))
            except queue.Empty:
                if self.exited and self._messages.empty():
                    self._stream_closed = True
                continue
            if kind == "EOF":
                self._stream_closed = True
                self.recorder.record("PROCESS", "LIFECYCLE", None, [], {"event": "STDOUT_EOF"})
                continue
            if kind == "NON_JSON":
                self._non_json_lines += 1
                self.recorder.record("SERVER_TO_CLIENT", "NON_JSON", None, [], {"bytes": payload})
                continue
            self._dispatch(payload)

    def _dispatch(self, message: Any) -> None:
        if not isinstance(message, Mapping):
            self._non_json_lines += 1
            return
        has_method = "method" in message
        has_id = "id" in message and message.get("id") is not None
        if has_method and has_id:
            self._handle_server_request(message)
        elif has_method:
            self._handle_notification(message)
        elif has_id:
            key = message["id"]
            if isinstance(key, int):
                self._responses[key] = message

    # -- server requests ---------------------------------------------------

    def _handle_server_request(self, message: Mapping[str, Any]) -> None:
        method = str(message.get("method"))
        params = message.get("params") if isinstance(message.get("params"), Mapping) else {}
        request_id = message["id"]
        result, detail = self._unattended_response(method, params)
        self.recorder.record("SERVER_TO_CLIENT", "SERVER_REQUEST", method, _keys(params), detail)
        if result is None:
            self.unsupported_server_requests.append(method)
            self._send({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": "unsupported in bounded write-path diagnostic"},
            })
            self.recorder.record(
                "CLIENT_TO_SERVER", "SERVER_RESPONSE", method, [], {"answer": "UNSUPPORTED_METHOD_ERROR"}
            )
            return
        self._send({"jsonrpc": "2.0", "id": request_id, "result": result})
        self.recorder.record(
            "CLIENT_TO_SERVER", "SERVER_RESPONSE", method, [], {"answer": detail.get("decision_class", "ANSWERED")}
        )

    def _unattended_response(
        self, method: str, params: Mapping[str, Any]
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        if method == "currentTime/read":
            return {"currentTimeAt": int(time.time())}, {"answer": "CURRENT_TIME"}
        approval_class = APPROVAL_METHODS.get(method)
        if approval_class is None:
            return None, {"answer": "UNSUPPORTED"}

        command = params.get("command")
        detail: dict[str, Any] = {
            "approval_class": approval_class,
            "cwd": params.get("cwd"),
            "reason_present": bool(params.get("reason")),
            "command_program": command[0] if isinstance(command, list) and command else None,
        }
        if method == "item/fileChange/requestApproval":
            detail["decision_class"] = "DECLINE_UNATTENDED"
            result: dict[str, Any] = {"decision": "decline"}
        elif method == "item/commandExecution/requestApproval":
            available = params.get("availableDecisions")
            offered = [item for item in available if isinstance(item, str)] if isinstance(available, list) else []
            decision = "decline" if "decline" in offered or not offered else ("cancel" if "cancel" in offered else "decline")
            detail["decision_class"] = f"{decision.upper()}_UNATTENDED"
            detail["offered_decisions"] = offered
            result = {"decision": decision}
        elif method == "item/permissions/requestApproval":
            detail["decision_class"] = "GRANT_NOTHING_UNATTENDED"
            result = {"permissions": {}, "scope": "turn"}
        else:
            detail["decision_class"] = "DENIED_UNATTENDED"
            result = {"decision": {"denied": {"rejection": _UNATTENDED_REJECTION}}}
        self.approval_events.append({"method": method, **detail})
        return result, detail

    # -- notifications -----------------------------------------------------

    def _handle_notification(self, message: Mapping[str, Any]) -> None:
        method = str(message.get("method"))
        params = message.get("params") if isinstance(message.get("params"), Mapping) else {}
        detail: dict[str, Any] = {}

        if method == "thread/started":
            thread = params.get("thread") if isinstance(params.get("thread"), Mapping) else {}
            detail = {"thread_sha256": _hashed_id(thread.get("id") or params.get("threadId"))}
        elif method in {"turn/started", "turn/completed"}:
            turn = params.get("turn") if isinstance(params.get("turn"), Mapping) else {}
            status = turn.get("status")
            error = turn.get("error") if isinstance(turn.get("error"), Mapping) else None
            if method == "turn/started" and isinstance(turn.get("id"), str):
                self.turn_id = turn["id"]
            detail = {
                "turn_sha256": _hashed_id(turn.get("id")),
                "thread_sha256": _hashed_id(params.get("threadId")),
                "status": status,
                "error_message": _truncate(error.get("message")) if error else None,
            }
            self.turn_events.append({"method": method, **detail})
        elif method in {"item/started", "item/completed"}:
            item = params.get("item") if isinstance(params.get("item"), Mapping) else {}
            item_type = item.get("type")
            detail = {"item_type": item_type, "status": item.get("status")}
            if item_type == "fileChange":
                changes = item.get("changes")
                detail["change_count"] = len(changes) if isinstance(changes, (list, Mapping)) else None
            elif item_type == "commandExecution":
                command = item.get("command")
                detail["command_program"] = command[0] if isinstance(command, list) and command else None
                detail["exit_code"] = item.get("exitCode")
                detail["cwd"] = item.get("cwd")
            elif item_type == "agentMessage" and method == "item/completed":
                text = item.get("text")
                if isinstance(text, str):
                    record = {
                        "text_sha256": sha256_bytes(text.encode()),
                        "text_length": len(text),
                        "matches_no_tool_control": text.strip() == NO_TOOL_EXPECTED_TEXT,
                    }
                    self.agent_messages.append(record)
                    detail.update(record)
            self.item_events.append({"method": method, **detail})
        elif method == "error":
            error = params.get("error") if isinstance(params.get("error"), Mapping) else {}
            detail = {
                "error_message": _truncate(error.get("message")),
                "will_retry": params.get("willRetry"),
            }
            self.error_notifications.append(detail)

        self.recorder.record("SERVER_TO_CLIENT", "NOTIFICATION", method, _keys(params), detail)

    def turn_terminal(self) -> Mapping[str, Any] | None:
        for event in reversed(self.turn_events):
            if event["method"] == "turn/completed":
                return event
        return None


# Narrow, explicitly-flagged markers used only to separate AUTH_FAILURE from
# other turn failures.  Inference from product error text is always recorded as
# an inference, never as a directly observed fact.
_AUTH_ERROR_MARKERS = (
    "not logged in",
    "unauthorized",
    "authentication",
    "auth error",
    "401",
    "login",
    "credential",
)


def _looks_like_auth_failure(*texts: str | None) -> bool:
    joined = " ".join(text.lower() for text in texts if isinstance(text, str))
    return any(marker in joined for marker in _AUTH_ERROR_MARKERS)


def classify_route(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Choose exactly one terminal class from positively supported evidence.

    A missing file never implies denial, and a timeout never implies absent
    write capability.  Each branch requires evidence that mechanically supports
    only that class.
    """

    startup_ok = bool(observation.get("startup_ok"))
    protocol_stage = observation.get("protocol_failure_stage")
    timed_out = bool(observation.get("timed_out"))
    turn_status = observation.get("turn_status")
    write_attempt = bool(observation.get("write_attempt_observed"))
    write_effect = bool(observation.get("filesystem_effect_observed"))
    approvals = list(observation.get("approval_events") or [])
    errors = list(observation.get("error_messages") or [])
    turn_error = observation.get("turn_error_message")

    auth_inferred = _looks_like_auth_failure(turn_error, *errors)

    if not startup_ok:
        return {
            "terminal_class": "STARTUP_FAILURE",
            "mechanism": "APP_SERVER_STARTUP_OR_HANDSHAKE_FAILED",
            "auth_failure_inferred_from_error_text": auth_inferred,
        }
    if protocol_stage:
        return {
            "terminal_class": "STARTUP_FAILURE",
            "mechanism": f"PROTOCOL_REJECTED_AT_{protocol_stage}",
            "auth_failure_inferred_from_error_text": auth_inferred,
        }
    if timed_out:
        # A directly observed deadline outranks any inference drawn from text.
        return {
            "terminal_class": "TURN_TIMEOUT",
            "mechanism": "BOUNDED_TURN_DEADLINE_ELAPSED_WITHOUT_TERMINAL_EVENT",
            "auth_failure_inferred_from_error_text": auth_inferred,
        }
    if auth_inferred and turn_status in {None, "failed"}:
        return {
            "terminal_class": "AUTH_FAILURE",
            "mechanism": "PRODUCT_ERROR_TEXT_INDICATES_AUTHENTICATION",
            "auth_failure_inferred_from_error_text": True,
        }
    if turn_status == "failed":
        return {
            "terminal_class": "TURN_FAILED",
            "mechanism": "PRODUCT_REPORTED_FAILED_TURN",
            "auth_failure_inferred_from_error_text": auth_inferred,
        }
    if turn_status == "interrupted":
        return {
            "terminal_class": "TURN_INTERRUPTED",
            "mechanism": "PRODUCT_REPORTED_INTERRUPTED_TURN",
            "auth_failure_inferred_from_error_text": auth_inferred,
        }
    if write_effect:
        return {
            "terminal_class": "COMPLETED_WITH_WRITE" if turn_status == "completed" else "WRITE_EFFECT_OBSERVED",
            "mechanism": "FILESYSTEM_BYTES_CHANGED_TO_TARGET",
            "auth_failure_inferred_from_error_text": auth_inferred,
        }
    permission_denied = [event for event in approvals if event.get("approval_class") == "PERMISSIONS"]
    if permission_denied:
        return {
            "terminal_class": "PERMISSION_DENIED",
            "mechanism": "PERMISSION_ESCALATION_REQUESTED_AND_NOT_GRANTED_UNATTENDED",
            "auth_failure_inferred_from_error_text": auth_inferred,
        }
    if approvals:
        return {
            "terminal_class": "APPROVAL_DENIED",
            "mechanism": "APPROVAL_REQUESTED_UNDER_DECLARED_POLICY_AND_DECLINED_UNATTENDED",
            "auth_failure_inferred_from_error_text": auth_inferred,
        }
    if write_attempt:
        return {
            "terminal_class": "WRITE_ATTEMPT_OBSERVED",
            "mechanism": "WRITE_TOOL_ITEM_OBSERVED_WITHOUT_TARGET_BYTES",
            "auth_failure_inferred_from_error_text": auth_inferred,
        }
    if turn_status == "completed":
        return {
            "terminal_class": "COMPLETED_NO_WRITE",
            "mechanism": "TURN_COMPLETED_WITHOUT_ANY_WRITE_TOOL_ITEM",
            "auth_failure_inferred_from_error_text": auth_inferred,
        }
    return {
        "terminal_class": "WRITE_NOT_ATTEMPTED",
        "mechanism": "NO_TERMINAL_TURN_EVENT_AND_NO_WRITE_TOOL_ITEM",
        "auth_failure_inferred_from_error_text": auth_inferred,
    }


def _write_attempt_observed(item_events: Sequence[Mapping[str, Any]]) -> bool:
    """A write attempt requires an explicit file-change tool item.

    A command-execution item is recorded as evidence but is not by itself a
    write attempt: a read-only command would otherwise be miscounted as one.
    """

    return any(event.get("item_type") == "fileChange" for event in item_events)


def _command_execution_observed(item_events: Sequence[Mapping[str, Any]]) -> bool:
    return any(event.get("item_type") == "commandExecution" for event in item_events)


def run_app_server_route(
    *,
    route: str,
    workspace: Path,
    prompt: str,
    recorder: TraceRecorder,
    argv: Sequence[str] | None = None,
    codex_binary: str = CODEX_BINARY,
    codex_home: str = CODEX_HOME,
    turn_timeout_seconds: float = DEFAULT_TURN_TIMEOUT_SECONDS,
    handshake_timeout_seconds: float = DEFAULT_HANDSHAKE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run exactly one bounded app-server turn against a disposable workspace.

    The effective policy is always sent explicitly, and the response's own
    effective policy fields are recorded so declared policy is never mistaken
    for effective policy.
    """

    workspace = Path(workspace).resolve()
    if not workspace.is_dir():
        raise QualificationError("diagnostic workspace does not exist")
    resolved_argv = tuple(argv) if argv else (codex_binary, *APP_SERVER_SUBCOMMAND)

    clean_env, api_key_presence = sanitize_environment(additions={"CODEX_HOME": codex_home})
    env_names = sorted(clean_env)

    before = workspace_snapshot(workspace)
    fixture_before = fixture_state(workspace)

    started_at = utc_now()
    client = AppServerClient(resolved_argv, workspace, clean_env, recorder)
    startup_ok = False
    protocol_failure_stage: str | None = None
    timed_out = False
    timeout_stage: str | None = None
    effective: dict[str, Any] = {}
    initialize_result: dict[str, Any] = {}
    thread_id: str | None = None
    sent_thread_params: dict[str, Any] = {}
    sent_turn_params: dict[str, Any] = {}
    startup_error: str | None = None

    try:
        try:
            client.start()
        except QualificationError as exc:
            # A child that cannot be spawned is still evidence, not an
            # exception the ladder has to guess about.
            startup_error = str(exc)
            raise _StartupAborted from exc
        deadline = time.monotonic() + handshake_timeout_seconds
        outcome = client.request(
            "initialize",
            {"clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION}},
            deadline=deadline,
        )
        if not outcome["ok"]:
            protocol_failure_stage = "INITIALIZE"
        else:
            startup_ok = True
            result = outcome["result"] or {}
            initialize_result = {
                "effective_codex_home": result.get("codexHome"),
                "platform_os": result.get("platformOs"),
                "user_agent_present": bool(result.get("userAgent")),
            }
            client.notify("initialized")

        if startup_ok and protocol_failure_stage is None:
            deadline = time.monotonic() + handshake_timeout_seconds
            thread_params = {
                "cwd": str(workspace),
                "ephemeral": True,
                "approvalPolicy": "never",
                "sandbox": "workspace-write",
            }
            sent_thread_params = dict(thread_params)
            outcome = client.request(
                "thread/start",
                thread_params,
                deadline=deadline,
                detail={
                    "requested_cwd": str(workspace),
                    "requested_approval_policy": "never",
                    "requested_sandbox_mode": "workspace-write",
                },
            )
            if not outcome["ok"]:
                protocol_failure_stage = "THREAD_START"
            else:
                result = outcome["result"] or {}
                thread = result.get("thread") if isinstance(result.get("thread"), Mapping) else {}
                thread_id = thread.get("id") if isinstance(thread.get("id"), str) else None
                client.thread_id = thread_id
                sandbox = result.get("sandbox")
                effective = {
                    "effective_cwd": result.get("cwd"),
                    "effective_approval_policy": approval_policy_class(result.get("approvalPolicy")),
                    "effective_sandbox_class": sandbox_policy_class(sandbox),
                    "effective_writable_roots": list(sandbox.get("writableRoots", []))
                    if isinstance(sandbox, Mapping) else [],
                    "effective_network_access": sandbox.get("networkAccess")
                    if isinstance(sandbox, Mapping) else None,
                    "effective_permission_profile": (
                        result["activePermissionProfile"].get("id")
                        if isinstance(result.get("activePermissionProfile"), Mapping) else None
                    ),
                    "effective_runtime_workspace_roots": list(result.get("runtimeWorkspaceRoots") or []),
                    "thread_ephemeral": thread.get("ephemeral"),
                    "model": result.get("model"),
                    "model_provider": result.get("modelProvider"),
                }
                recorder.record("OBSERVATION", "EFFECTIVE_POLICY", "thread/start", [], effective)
                if thread_id is None:
                    protocol_failure_stage = "THREAD_START_MISSING_ID"

        if startup_ok and protocol_failure_stage is None and thread_id:
            deadline = time.monotonic() + turn_timeout_seconds
            turn_params = {
                "threadId": thread_id,
                "cwd": str(workspace),
                "approvalPolicy": "never",
                "sandboxPolicy": {
                    "type": "workspaceWrite",
                    "writableRoots": [str(workspace)],
                    "networkAccess": False,
                },
                "input": [{"type": "text", "text": prompt}],
            }
            sent_turn_params = dict(turn_params)
            outcome = client.request(
                "turn/start",
                turn_params,
                deadline=deadline,
                detail={
                    "requested_cwd": str(workspace),
                    "requested_approval_policy": "never",
                    "requested_sandbox_class": "workspaceWrite",
                    "requested_writable_roots": [str(workspace)],
                    "requested_network_access": False,
                    "prompt_sha256": sha256_bytes(prompt.encode()),
                },
            )
            if not outcome["ok"]:
                protocol_failure_stage = "TURN_START"
            else:
                try:
                    client.pump(deadline=deadline, until=lambda: client.turn_terminal() is not None)
                except AppServerTimeout:
                    timed_out = True
                    timeout_stage = "TURN"
                if client.turn_terminal() is None and not timed_out:
                    protocol_failure_stage = "TURN_STREAM_CLOSED_BEFORE_TERMINAL"
    except _StartupAborted:
        pass
    except AppServerTimeout:
        timed_out = True
        timeout_stage = timeout_stage or "HANDSHAKE"
    finally:
        disposal = client.close()
        ended_at = utc_now()

    after = workspace_snapshot(workspace)
    fixture_after = fixture_state(workspace)
    changed = changed_paths(before, after)
    filesystem_effect = fixture_before["class"] == "BEFORE" and fixture_after["class"] == "AFTER"

    turn_sandbox = sent_turn_params.get("sandboxPolicy") or {}
    declared = {
        "thread_start_keys": sorted(sent_thread_params),
        "turn_start_keys": sorted(sent_turn_params),
        "approval_policy": sent_thread_params.get("approvalPolicy"),
        "thread_sandbox_mode": sent_thread_params.get("sandbox"),
        "turn_approval_policy": sent_turn_params.get("approvalPolicy"),
        "turn_sandbox_class": turn_sandbox.get("type"),
        "cwd": sent_turn_params.get("cwd") or sent_thread_params.get("cwd"),
        "writable_roots": list(turn_sandbox.get("writableRoots") or []),
        "network_access": turn_sandbox.get("networkAccess"),
    }
    parity = {
        "codex_home_requested": codex_home,
        "codex_home_effective": initialize_result.get("effective_codex_home"),
        "codex_home_matches": initialize_result.get("effective_codex_home") == codex_home,
        "cwd_matches": effective.get("effective_cwd") == str(workspace),
        "approval_policy_matches": (
            effective.get("effective_approval_policy") == declared["approval_policy"]
        ),
        "sandbox_class_matches": effective.get("effective_sandbox_class") == "workspaceWrite",
        "writable_root_covers_workspace": str(workspace) in (
            effective.get("effective_writable_roots") or []
        ),
        "thread_ephemeral": effective.get("thread_ephemeral"),
    }
    parity["all_match"] = bool(effective) and all(
        parity[key] for key in (
            "codex_home_matches", "cwd_matches", "approval_policy_matches",
            "sandbox_class_matches", "writable_root_covers_workspace",
        )
    )
    recorder.record("OBSERVATION", "POLICY_PARITY", None, [], parity)

    terminal = client.turn_terminal()
    observation = {
        "startup_ok": startup_ok,
        "protocol_failure_stage": protocol_failure_stage,
        "timed_out": timed_out,
        "turn_status": terminal.get("status") if terminal else None,
        "turn_error_message": terminal.get("error_message") if terminal else None,
        "error_messages": [event.get("error_message") for event in client.error_notifications],
        "write_attempt_observed": _write_attempt_observed(client.item_events),
        "command_execution_observed": _command_execution_observed(client.item_events),
        "filesystem_effect_observed": filesystem_effect,
        "approval_events": client.approval_events,
    }
    classification = classify_route(observation)

    receipt = {
        "route": route,
        "started_at": started_at,
        "ended_at": ended_at,
        "argv": list(resolved_argv),
        "cwd": str(workspace),
        "prompt_sha256": sha256_bytes(prompt.encode()),
        "codex_home_requested": codex_home,
        "timeout_policy": {
            "handshake_seconds": handshake_timeout_seconds,
            "turn_seconds": turn_timeout_seconds,
            "timed_out": timed_out,
            "timeout_stage": timeout_stage,
        },
        "environment": {
            "api_key_presence": api_key_presence,
            "removed_names": ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
                              "OPENROUTER_API_KEY", "GITHUB_TOKEN", "GH_TOKEN"],
            "inherited_name_count": len(env_names),
            "inherited_names_sha256": sha256_bytes(canonical_json(env_names)),
        },
        "handshake": initialize_result,
        "declared_policy": declared,
        "effective_policy": effective,
        "policy_parity": parity,
        "protocol_failure_stage": protocol_failure_stage,
        "startup_error": startup_error,
        "write_attempt_observed": observation["write_attempt_observed"],
        "command_execution_observed": observation["command_execution_observed"],
        "turn": {
            "status": observation["turn_status"],
            "error_message": observation["turn_error_message"],
            "terminal_observed": terminal is not None,
        },
        "approval_requests": client.approval_events,
        "unsupported_server_requests": sorted(set(client.unsupported_server_requests)),
        "items": client.item_events,
        "agent_messages": client.agent_messages,
        "error_notifications": client.error_notifications,
        "filesystem": {
            "fixture_before": fixture_before,
            "fixture_after": fixture_after,
            "before_digest": snapshot_digest(before),
            "after_digest": snapshot_digest(after),
            "changed_paths": changed,
            "effect_observed": filesystem_effect,
        },
        "process": disposal,
        "classification": classification,
    }
    recorder.record("OBSERVATION", "ROUTE_RECEIPT", route, [], {
        "terminal_class": classification["terminal_class"],
        "mechanism": classification["mechanism"],
        "filesystem_effect": filesystem_effect,
    })
    return receipt


def route_passed(receipt: Mapping[str, Any]) -> bool:
    """A write route passes only on machine filesystem truth plus a clean terminal."""

    classification = receipt.get("classification") or {}
    return (
        classification.get("terminal_class") == "COMPLETED_WITH_WRITE"
        and bool((receipt.get("filesystem") or {}).get("effect_observed"))
        and (receipt.get("filesystem") or {}).get("changed_paths") == [FIXTURE_NAME]
    )


def no_tool_control_passed(receipt: Mapping[str, Any]) -> bool:
    """D1 passes on a clean completed turn, the exact answer, and zero mutation."""

    filesystem = receipt.get("filesystem") or {}
    messages = receipt.get("agent_messages") or []
    return (
        (receipt.get("turn") or {}).get("status") == "completed"
        and any(message.get("matches_no_tool_control") for message in messages)
        and filesystem.get("changed_paths") == []
    )


def run_d0_host_control(root: Path) -> dict[str, Any]:
    """D0: prove the host itself can perform the exact fixture write.

    Reset is by destruction, never by editing the mutated workspace back.
    """

    root = Path(root)
    started_at = utc_now()
    workspace = build_workspace(root)
    initial = fixture_state(workspace)
    before = workspace_snapshot(workspace)
    (workspace / FIXTURE_NAME).write_bytes(FIXTURE_AFTER_BYTES)
    final = fixture_state(workspace)
    after = workspace_snapshot(workspace)
    changed = changed_paths(before, after)
    passed = (
        initial["class"] == "BEFORE"
        and final["class"] == "AFTER"
        and changed == [FIXTURE_NAME]
    )
    destroy_workspace(workspace)
    return {
        "route": "D0_HOST_FILESYSTEM",
        "started_at": started_at,
        "ended_at": utc_now(),
        "workspace_path_class": str(root.parent),
        "fixture_before": initial,
        "fixture_after": final,
        "changed_paths": changed,
        "workspace_destroyed": not workspace.exists(),
        "passed": passed,
    }


LADDER_STAGES = (
    ("D0", "D0_HOST_FILESYSTEM"),
    ("D1", "D1_RAW_APP_SERVER_BASELINE"),
    ("D2", "D2_RAW_APP_SERVER_WRITE"),
    ("D3", "D3_QNTY_NATIVE_BRIDGE"),
    ("D4", "D4_PINNED_DSH_CODEX_PROVIDER"),
)


def first_divergence(gates: Mapping[str, str]) -> str:
    """Return the first ladder stage that did not pass.

    `gates` maps stage keys (`D0`..`D4`) to `PASS`, `FAIL`,
    `NOT_RUN_DUE_TO_EARLIER_DIVERGENCE`, or `INCONCLUSIVE_INFRA`.
    """

    for key, name in LADDER_STAGES:
        state = gates.get(key)
        if state == "INCONCLUSIVE_INFRA":
            return "INCONCLUSIVE_INFRA"
        if state == "FAIL":
            return name
        if state != "PASS":
            # A skipped, missing, or unrecognised stage can never support
            # `NONE`, which would claim that every write path passed.
            return "UNKNOWN"
    return "NONE"
