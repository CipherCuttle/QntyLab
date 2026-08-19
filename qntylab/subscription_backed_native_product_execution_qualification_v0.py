"""Fail-closed native subscription-product qualification primitives.

This module is mechanical plumbing only.  It has no scientific, Qnty runtime,
trading, capital, or Stage-A authority.  Product prose never decides success.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import stat
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from qntylab.subscription_backed_codex_app_server_write_path_diagnostic_v0 import (
    AppServerClient,
    AppServerTimeout,
    TraceRecorder,
    approval_policy_class,
    sandbox_policy_class,
)


PROJECT_ID = "SUBSCRIPTION_BACKED_NATIVE_PRODUCT_EXECUTION_QUALIFICATION_V0"
SCHEMA_VERSION = "subscription-backed-native-product-role-receipt-v0"
CODEX_BINARY = "/home/swirky/.local/bin/codex"
CLAUDE_BINARY = "/usr/bin/claude"
PROFILE_A = "/home/swirky/.codex"
PROFILE_B = "/home/swirky/.codex-pro2"
FIXTURE_NAME = "fixture.txt"
FIXTURE_BEFORE_BYTES = b"BEFORE\n"
FIXTURE_TARGET_BYTES = b"AFTER\n"
API_KEY_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENROUTER_API_KEY",
)
ROLE_BINDINGS = {
    "BUILDER": ("CODEX_PROFILE_A", PROFILE_A, CODEX_BINARY),
    "INDEPENDENT_REVIEWER": ("CLAUDE_CODE_SUBSCRIPTION", "CLAUDE_AI_PRO_SUBSCRIPTION", CLAUDE_BINARY),
    "VERIFIER": ("CODEX_PROFILE_B", PROFILE_B, CODEX_BINARY),
}
ROLE_VERSIONS = {
    "BUILDER": "codex-cli 0.147.0",
    "INDEPENDENT_REVIEWER": "2.1.223 (Claude Code)",
    "VERIFIER": "codex-cli 0.147.0",
}

REVIEWER_KEYS = {
    "role",
    "verdict",
    "builder_task_satisfied",
    "changed_paths_match",
    "fixture_match",
    "unauthorized_writes",
    "reasons",
}
VERIFIER_KEYS = {
    "role",
    "verdict",
    "builder_result_valid",
    "reviewer_result_consistent",
    "workspace_matches_contract",
    "unauthorized_writes",
    "reasons",
}
RECEIPT_KEYS = {
    "schema_version",
    "role",
    "product",
    "profile",
    "binary_path",
    "binary_version",
    "subscription_backed",
    "cwd",
    "workspace_identity",
    "prompt_sha256",
    "prompt_template_sha256",
    "driver_sha256",
    "started_marker_sha256",
    "started_at",
    "finished_at",
    "timeout_seconds",
    "timed_out",
    "product_started",
    "process_exit",
    "lifecycle",
    "protocol",
    "effective_policy",
    "workspace",
    "qntylab_worktree",
    "api_key_gate",
    "structured_verdict",
    "machine_status",
    "failure_class",
}


class QualificationError(ValueError):
    """A malformed, stale, unsafe, or contradictory qualification artifact."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise QualificationError(f"hash target is not a regular file: {path}")
    return sha256_bytes(path.read_bytes())


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def strict_json_object(value: str | bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualificationError("output is not exactly one valid JSON value") from exc
    if not isinstance(parsed, dict):
        raise QualificationError("output JSON must be an object")
    return parsed


def _concrete_strings(values: Any, label: str) -> list[str]:
    if not isinstance(values, list) or any(not isinstance(item, str) or not item for item in values):
        raise QualificationError(f"{label} must be a list of non-empty strings")
    return list(values)


def parse_reviewer_verdict(value: str | bytes | Mapping[str, Any]) -> dict[str, Any]:
    data = dict(value) if isinstance(value, Mapping) else strict_json_object(value)
    if set(data) != REVIEWER_KEYS:
        raise QualificationError("reviewer verdict keys are not exact")
    if data["role"] != "INDEPENDENT_REVIEWER" or data["verdict"] not in {"PASS", "FAIL"}:
        raise QualificationError("reviewer role or verdict is invalid")
    checks = ("builder_task_satisfied", "changed_paths_match", "fixture_match")
    if any(type(data[key]) is not bool for key in checks):
        raise QualificationError("reviewer checks must be concrete booleans")
    unauthorized = _concrete_strings(data["unauthorized_writes"], "reviewer unauthorized_writes")
    if not isinstance(data["reasons"], list):
        raise QualificationError("reviewer reasons must be a list")
    reasons = _concrete_strings(data["reasons"], "reviewer reasons") if data["reasons"] else []
    all_true = all(data[key] is True for key in checks)
    if data["verdict"] == "PASS" and (not all_true or unauthorized or reasons):
        raise QualificationError("reviewer PASS contradicts its fields")
    if data["verdict"] == "FAIL" and not reasons:
        raise QualificationError("reviewer FAIL requires reasons")
    return {**data, "unauthorized_writes": unauthorized, "reasons": reasons}


def parse_verifier_verdict(value: str | bytes | Mapping[str, Any]) -> dict[str, Any]:
    data = dict(value) if isinstance(value, Mapping) else strict_json_object(value)
    if set(data) != VERIFIER_KEYS:
        raise QualificationError("verifier verdict keys are not exact")
    if data["role"] != "VERIFIER" or data["verdict"] not in {"PASS", "FAIL"}:
        raise QualificationError("verifier role or verdict is invalid")
    checks = ("builder_result_valid", "reviewer_result_consistent", "workspace_matches_contract")
    if any(type(data[key]) is not bool for key in checks):
        raise QualificationError("verifier checks must be concrete booleans")
    unauthorized = _concrete_strings(data["unauthorized_writes"], "verifier unauthorized_writes")
    if not isinstance(data["reasons"], list):
        raise QualificationError("verifier reasons must be a list")
    reasons = _concrete_strings(data["reasons"], "verifier reasons") if data["reasons"] else []
    all_true = all(data[key] is True for key in checks)
    if data["verdict"] == "PASS" and (not all_true or unauthorized or reasons):
        raise QualificationError("verifier PASS contradicts its fields")
    if data["verdict"] == "FAIL" and not reasons:
        raise QualificationError("verifier FAIL requires reasons")
    return {**data, "unauthorized_writes": unauthorized, "reasons": reasons}


def reviewer_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "role": {"const": "INDEPENDENT_REVIEWER"},
            "verdict": {"enum": ["PASS", "FAIL"]},
            "builder_task_satisfied": {"type": "boolean"},
            "changed_paths_match": {"type": "boolean"},
            "fixture_match": {"type": "boolean"},
            "unauthorized_writes": {"type": "array", "items": {"type": "string"}},
            "reasons": {"type": "array", "items": {"type": "string"}},
        },
        "required": sorted(REVIEWER_KEYS),
    }


def verifier_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "role": {"const": "VERIFIER"},
            "verdict": {"enum": ["PASS", "FAIL"]},
            "builder_result_valid": {"type": "boolean"},
            "reviewer_result_consistent": {"type": "boolean"},
            "workspace_matches_contract": {"type": "boolean"},
            "unauthorized_writes": {"type": "array", "items": {"type": "string"}},
            "reasons": {"type": "array", "items": {"type": "string"}},
        },
        "required": sorted(VERIFIER_KEYS),
    }


def api_key_presence(environment: Mapping[str, str] | None = None) -> dict[str, bool]:
    source = os.environ if environment is None else environment
    return {name: name in source for name in API_KEY_NAMES}


def sanitized_environment(
    environment: Mapping[str, str] | None = None,
    *,
    additions: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, bool]]:
    source = dict(os.environ if environment is None else environment)
    presence = api_key_presence(source)
    clean = {key: item for key, item in source.items() if key not in API_KEY_NAMES}
    if additions:
        if set(additions) & set(API_KEY_NAMES):
            raise QualificationError("API-key environment additions are forbidden")
        clean.update({str(key): str(item) for key, item in additions.items()})
    return clean, presence


def api_key_gate(presence: Mapping[str, bool]) -> str:
    if set(presence) != set(API_KEY_NAMES) or any(type(presence[name]) is not bool for name in API_KEY_NAMES):
        raise QualificationError("API-key presence map is malformed")
    return "PASS" if not any(presence.values()) else "FAIL"


def _snapshot_tree(root: Path, *, include_git: bool) -> dict[str, str]:
    root = Path(root).resolve(strict=True)
    if not root.is_dir() or Path(root).is_symlink():
        raise QualificationError("snapshot root must be a non-symlink directory")
    result: dict[str, str] = {}

    def visit(directory: Path, prefix: Path) -> None:
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                rel = prefix / entry.name
                if not include_git and rel.parts[0] == ".git":
                    continue
                info = entry.stat(follow_symlinks=False)
                mode = stat.S_IMODE(info.st_mode)
                key = rel.as_posix()
                if stat.S_ISLNK(info.st_mode):
                    result[key] = f"SYMLINK:{mode:o}:{os.readlink(entry.path)}"
                elif stat.S_ISDIR(info.st_mode):
                    result[key] = f"DIR:{mode:o}"
                    visit(Path(entry.path), rel)
                elif stat.S_ISREG(info.st_mode):
                    result[key] = f"FILE:{mode:o}:{sha256_file(Path(entry.path))}"
                else:
                    result[key] = f"SPECIAL:{mode:o}:{stat.S_IFMT(info.st_mode)}"

    visit(root, Path())
    return result


def workspace_snapshot(root: Path) -> dict[str, str]:
    return _snapshot_tree(root, include_git=False)


def git_metadata_snapshot(root: Path) -> dict[str, str]:
    all_entries = _snapshot_tree(root, include_git=True)
    return {key: value for key, value in all_entries.items() if key == ".git" or key.startswith(".git/")}


def snapshot_digest(snapshot: Mapping[str, str]) -> str:
    return sha256_bytes(canonical_json(dict(sorted(snapshot.items()))))


def changed_paths(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    return sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))


def _git(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ("git", "-c", "core.hooksPath=/dev/null", *args),
        cwd=Path(root),
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise QualificationError(f"git observation failed: {' '.join(args)}")
    return completed.stdout


def git_changed_paths(root: Path) -> list[str]:
    tracked = [item.decode("utf-8") for item in _git(root, "diff", "--name-only", "-z", "HEAD").split(b"\0") if item]
    untracked = [item.decode("utf-8") for item in _git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0") if item]
    return sorted(set(tracked + untracked))


def git_diff_bytes(root: Path) -> bytes:
    return _git(root, "diff", "--binary", "--no-ext-diff", "HEAD", "--")


def fixture_observation(root: Path) -> dict[str, Any]:
    target = Path(root) / FIXTURE_NAME
    if target.is_symlink() or not target.is_file():
        return {"present": False, "sha256": "ABSENT", "byte_length": 0, "hex": ""}
    data = target.read_bytes()
    return {"present": True, "sha256": sha256_bytes(data), "byte_length": len(data), "hex": data.hex()}


def workspace_identity(root: Path) -> dict[str, str]:
    root = Path(root).resolve(strict=True)
    identity = {
        "resolved_path": str(root),
        "initial_head": _git(root, "rev-parse", "HEAD").decode().strip(),
        "initial_workspace_digest": snapshot_digest(workspace_snapshot(root)),
        "initial_git_metadata_digest": snapshot_digest(git_metadata_snapshot(root)),
    }
    return {**identity, "identity_sha256": sha256_bytes(canonical_json(identity))}


def validate_workspace_boundary(workspace: Path, qntylab_root: Path) -> tuple[Path, Path]:
    raw_workspace = Path(workspace)
    raw_qntylab = Path(qntylab_root)
    if raw_workspace.is_symlink() or raw_qntylab.is_symlink():
        raise QualificationError("workspace roots may not be symlinks")
    workspace_resolved = raw_workspace.resolve(strict=True)
    qntylab_resolved = raw_qntylab.resolve(strict=True)
    if not workspace_resolved.is_dir() or not qntylab_resolved.is_dir():
        raise QualificationError("workspace roots must be directories")
    try:
        workspace_resolved.relative_to(qntylab_resolved)
    except ValueError:
        pass
    else:
        raise QualificationError("synthetic workspace must be outside QntyLab")
    if (workspace_resolved / ".git").is_symlink() or not (workspace_resolved / ".git").is_dir():
        raise QualificationError("synthetic workspace must have non-symlink Git metadata")
    return workspace_resolved, qntylab_resolved


def qntylab_snapshot(root: Path) -> dict[str, str]:
    root = Path(root).resolve(strict=True)
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    diff = _git(root, "diff", "--binary", "--no-ext-diff", "HEAD", "--")
    return {
        "head": _git(root, "rev-parse", "HEAD").decode().strip(),
        "status_sha256": sha256_bytes(status),
        "diff_sha256": sha256_bytes(diff),
        "combined_sha256": sha256_bytes(status + b"\0" + diff),
    }


def render_evidence_prompt(template: bytes, packet: Mapping[str, Any]) -> bytes:
    packet_bytes = canonical_json(packet)
    return template + b"\n" + sha256_bytes(packet_bytes).encode("ascii") + b"\n" + packet_bytes


def write_exclusive_json(path: Path, value: Mapping[str, Any]) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.parent.is_symlink():
        raise QualificationError("exclusive artifact path may not be a symlink")
    payload = canonical_json(value)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise QualificationError(f"attempt artifact already exists: {path.name}") from exc
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except Exception:
        raise
    return sha256_bytes(payload)


def read_json_file(path: Path) -> dict[str, Any]:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise QualificationError(f"JSON artifact is not a regular file: {path}")
    return strict_json_object(path.read_bytes())


def require_hashes(root: Path, expected: Mapping[str, str]) -> None:
    root = Path(root).resolve(strict=True)
    for raw_path, digest in expected.items():
        if not isinstance(raw_path, str) or not isinstance(digest, str) or len(digest) != 64:
            raise QualificationError("frozen hash map is malformed")
        candidate = root / raw_path
        try:
            candidate.resolve(strict=True).relative_to(root)
        except (OSError, ValueError) as exc:
            raise QualificationError(f"frozen path escapes repository: {raw_path}") from exc
        if sha256_file(candidate) != digest:
            raise QualificationError(f"frozen hash mismatch: {raw_path}")


class BoundAppServerClient(AppServerClient):
    """#135 transport with process-group disposal and exact raw turn binding."""

    def __init__(self, argv: Sequence[str], cwd: Path, env: Mapping[str, str], recorder: TraceRecorder) -> None:
        super().__init__(argv, cwd, env, recorder)
        self.raw_terminals: list[dict[str, Any]] = []
        self.raw_agent_messages: list[dict[str, Any]] = []

    def start(self) -> None:
        try:
            self._proc = subprocess.Popen(
                list(self.argv), cwd=str(self.cwd), env=self.env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as exc:
            raise QualificationError(f"app-server could not start: {exc}") from exc
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        self.recorder.record("PROCESS", "LIFECYCLE", None, [], {"event": "SPAWNED", "argv": list(self.argv), "cwd": str(self.cwd)})

    def _handle_notification(self, message: Mapping[str, Any]) -> None:
        method = str(message.get("method"))
        params = message.get("params") if isinstance(message.get("params"), Mapping) else {}
        if method == "turn/completed":
            turn = params.get("turn") if isinstance(params.get("turn"), Mapping) else {}
            self.raw_terminals.append({
                "thread_id": params.get("threadId"),
                "turn_id": turn.get("id"),
                "status": turn.get("status"),
            })
        if method == "item/completed":
            item = params.get("item") if isinstance(params.get("item"), Mapping) else {}
            if item.get("type") == "agentMessage" and isinstance(item.get("text"), str):
                self.raw_agent_messages.append({
                    "thread_id": params.get("threadId"),
                    "turn_id": params.get("turnId"),
                    "text": item["text"],
                })
        super()._handle_notification(message)

    def close(self, *, grace_seconds: float = 10.0) -> dict[str, Any]:
        if self._proc is None:
            return {"disposed": False, "termination": "NOT_STARTED", "exit_code": -1, "exit_signal": 0,
                    "stderr_bytes": 0, "stderr_sha256": sha256_bytes(b""), "non_json_stdout_lines": 0}
        proc = self._proc
        if proc.stdin and not proc.stdin.closed:
            try:
                proc.stdin.close()
            except OSError:
                pass
        termination = "ALREADY_EXITED"
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            termination = "SIGTERM_PROCESS_GROUP"
            try:
                proc.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                termination = "SIGKILL_PROCESS_GROUP"
                proc.wait(timeout=grace_seconds)
        code = proc.returncode if isinstance(proc.returncode, int) else -1
        disposal = {
            "disposed": True,
            "termination": termination,
            "exit_code": code if code >= 0 else -1,
            "exit_signal": -code if code < 0 else 0,
            "stderr_bytes": self._stderr_bytes,
            "stderr_sha256": self._stderr_digest.hexdigest(),
            "non_json_stdout_lines": self._non_json_lines,
        }
        self.recorder.record("PROCESS", "LIFECYCLE", None, [], {"event": "DISPOSED", **disposal})
        return disposal


def _workspace_receipt(
    root: Path,
    before: Mapping[str, str],
    git_before: Mapping[str, str],
    fixture_before: Mapping[str, Any],
) -> dict[str, Any]:
    after = workspace_snapshot(root)
    git_after = git_metadata_snapshot(root)
    fixture_after = fixture_observation(root)
    mutations = changed_paths(before, after)
    git_paths = git_changed_paths(root)
    return {
        "before_digest": snapshot_digest(before),
        "after_digest": snapshot_digest(after),
        "changed_paths": mutations,
        "git_changed_paths": git_paths,
        "git_diff_sha256": sha256_bytes(git_diff_bytes(root)),
        "fixture_before": dict(fixture_before),
        "fixture_after": fixture_after,
        "git_metadata_before_digest": snapshot_digest(git_before),
        "git_metadata_after_digest": snapshot_digest(git_after),
        "unauthorized_writes": sorted(set(mutations) - {FIXTURE_NAME}),
    }


def _base_receipt(
    *, role: str, version: str, cwd: Path, workspace_id: str, prompt: bytes,
    template_sha: str, driver_sha: str, marker_sha: str, started_at: str,
    finished_at: str, timeout_seconds: int, timed_out: bool, product_started: bool,
    process_exit: Mapping[str, Any], lifecycle: str, protocol: Mapping[str, Any],
    effective_policy: Mapping[str, Any], workspace: Mapping[str, Any],
    qntylab_before: Mapping[str, str], qntylab_after: Mapping[str, str],
    gate: str, structured: Mapping[str, Any], machine_status: str, failure_class: str,
) -> dict[str, Any]:
    product, profile, binary = ROLE_BINDINGS[role]
    return {
        "schema_version": SCHEMA_VERSION,
        "role": role,
        "product": product,
        "profile": profile,
        "binary_path": binary,
        "binary_version": version,
        "subscription_backed": True,
        "cwd": str(Path(cwd).resolve()),
        "workspace_identity": workspace_id,
        "prompt_sha256": sha256_bytes(prompt),
        "prompt_template_sha256": template_sha,
        "driver_sha256": driver_sha,
        "started_marker_sha256": marker_sha,
        "started_at": started_at,
        "finished_at": finished_at,
        "timeout_seconds": timeout_seconds,
        "timed_out": timed_out,
        "product_started": product_started,
        "process_exit": dict(process_exit),
        "lifecycle": lifecycle,
        "protocol": dict(protocol),
        "effective_policy": dict(effective_policy),
        "workspace": dict(workspace),
        "qntylab_worktree": {
            "before_digest": qntylab_before["combined_sha256"],
            "after_digest": qntylab_after["combined_sha256"],
            "mutations": [] if qntylab_before == qntylab_after else ["QNTYLAB_WORKTREE_CHANGED"],
        },
        "api_key_gate": gate,
        "structured_verdict": dict(structured),
        "machine_status": machine_status,
        "failure_class": failure_class,
    }


def _policy_for_role(role: str, workspace: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if role == "BUILDER":
        return (
            {"cwd": str(workspace), "ephemeral": True, "approvalPolicy": "never", "sandbox": "workspace-write"},
            {"type": "workspaceWrite", "writableRoots": [str(workspace)], "networkAccess": False},
        )
    if role == "VERIFIER":
        return (
            {"cwd": str(workspace), "ephemeral": True, "approvalPolicy": "never", "sandbox": "read-only"},
            {"type": "readOnly", "networkAccess": False},
        )
    raise QualificationError("Codex role is invalid")


def run_codex_role(
    *, role: str, workspace: Path, qntylab_root: Path, prompt: bytes,
    workspace_id: str, template_sha: str, driver_sha: str, marker_sha: str,
    binary_version: str = "codex-cli 0.147.0", timeout_seconds: int = 180,
    argv: Sequence[str] | None = None, environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Execute one exact Codex app-server role and return a sanitized receipt."""

    if role not in {"BUILDER", "VERIFIER"}:
        raise QualificationError("run_codex_role accepts only BUILDER or VERIFIER")
    workspace, qntylab_root = validate_workspace_boundary(workspace, qntylab_root)
    before = workspace_snapshot(workspace)
    git_before = git_metadata_snapshot(workspace)
    fixture_before = fixture_observation(workspace)
    qntylab_before = qntylab_snapshot(qntylab_root)
    started_at = utc_now()
    clean_env, presence = sanitized_environment(environment, additions={"CODEX_HOME": ROLE_BINDINGS[role][1]})
    gate = api_key_gate(presence)
    resolved_argv = tuple(argv or (CODEX_BINARY, "app-server", "--stdio"))
    recorder = TraceRecorder(route=role)
    client = BoundAppServerClient(resolved_argv, workspace, clean_env, recorder)
    product_started = False
    timed_out = False
    lifecycle = "NOT_STARTED"
    failure = "API_KEY_GATE_FAILURE" if gate == "FAIL" else "PRODUCT_START_FAILURE"
    expected_thread = ""
    expected_turn = ""
    effective: dict[str, Any] = {}
    process_exit: dict[str, Any] = {"disposed": False, "termination": "NOT_STARTED", "exit_code": -1, "exit_signal": 0}
    protocol: dict[str, Any] = {
        "argv": list(resolved_argv), "thread_sha256": "ABSENT", "turn_sha256": "ABSENT",
        "terminal_count": 0, "terminal_binding_valid": False, "terminal_status": "ABSENT",
        "approval_request_count": 0, "unsupported_request_count": 0,
        "agent_output_sha256": "ABSENT",
    }
    structured: dict[str, Any] = {"role": role, "verdict": "FAIL"}
    deadline = time.monotonic() + timeout_seconds

    try:
        if gate == "FAIL":
            lifecycle = "BLOCKED_BEFORE_PRODUCT_START"
        else:
            client.start()
            product_started = True
            lifecycle = "STARTED"
            initialize = client.request(
                "initialize", {"clientInfo": {"name": "qntylab-native-product-qualification", "version": "0"}},
                deadline=min(deadline, time.monotonic() + 60),
            )
            if not initialize["ok"]:
                failure = "RECEIPT_INTEGRITY_FAILURE"
                lifecycle = "INITIALIZE_FAILED"
            else:
                client.notify("initialized")
                thread_params, sandbox_policy = _policy_for_role(role, workspace)
                thread = client.request("thread/start", thread_params, deadline=min(deadline, time.monotonic() + 60))
                if not thread["ok"]:
                    failure = "RECEIPT_INTEGRITY_FAILURE"
                    lifecycle = "THREAD_START_FAILED"
                else:
                    result = thread["result"]
                    thread_obj = result.get("thread") if isinstance(result.get("thread"), Mapping) else {}
                    expected_thread = thread_obj.get("id") if isinstance(thread_obj.get("id"), str) else ""
                    sandbox = result.get("sandbox")
                    effective = {
                        "cwd": result.get("cwd") if isinstance(result.get("cwd"), str) else "ABSENT",
                        "approval_policy": approval_policy_class(result.get("approvalPolicy")),
                        "sandbox_class": sandbox_policy_class(sandbox),
                        "writable_roots": list(sandbox.get("writableRoots") or []) if isinstance(sandbox, Mapping) else [],
                        "runtime_workspace_roots": list(result.get("runtimeWorkspaceRoots") or []),
                        "network_access": sandbox.get("networkAccess") if isinstance(sandbox, Mapping) and type(sandbox.get("networkAccess")) is bool else "ABSENT",
                        "codex_home": (initialize["result"] or {}).get("codexHome") if isinstance(initialize.get("result"), Mapping) else "ABSENT",
                    }
                    if not expected_thread:
                        lifecycle = "THREAD_ID_MISSING"
                        failure = "RECEIPT_INTEGRITY_FAILURE"
                    else:
                        turn_params: dict[str, Any] = {
                            "threadId": expected_thread,
                            "cwd": str(workspace),
                            "approvalPolicy": "never",
                            "sandboxPolicy": sandbox_policy,
                            "runtimeWorkspaceRoots": [str(workspace)],
                            "input": [{"type": "text", "text": prompt.decode("utf-8")}],
                        }
                        if role == "VERIFIER":
                            turn_params["outputSchema"] = verifier_json_schema()
                        turn = client.request("turn/start", turn_params, deadline=deadline)
                        if not turn["ok"]:
                            lifecycle = "TURN_START_FAILED"
                            failure = "RECEIPT_INTEGRITY_FAILURE"
                        else:
                            turn_result = turn["result"]
                            turn_obj = turn_result.get("turn") if isinstance(turn_result.get("turn"), Mapping) else {}
                            expected_turn = turn_obj.get("id") if isinstance(turn_obj.get("id"), str) else (client.turn_id or "")
                            if not expected_turn:
                                lifecycle = "TURN_ID_MISSING"
                                failure = "RECEIPT_INTEGRITY_FAILURE"
                            else:
                                client.pump(deadline=deadline, until=lambda: bool(client.raw_terminals))
                                lifecycle = "TERMINAL_OBSERVED"
    except AppServerTimeout:
        timed_out = True
        lifecycle = "TIMED_OUT"
        failure = f"{role}_PRODUCT_FAILURE"
    except (QualificationError, OSError) as exc:
        lifecycle = f"FAIL_CLOSED_{type(exc).__name__}"
        failure = "RECEIPT_INTEGRITY_FAILURE" if product_started else "PRODUCT_START_FAILURE"
    finally:
        process_exit = client.close(grace_seconds=10.0)

    matching_terminals = [
        item for item in client.raw_terminals
        if item.get("thread_id") == expected_thread and item.get("turn_id") == expected_turn
    ]
    terminal_valid = len(client.raw_terminals) == 1 and len(matching_terminals) == 1
    terminal_status = matching_terminals[0].get("status") if matching_terminals else "ABSENT"
    matching_messages = [
        item for item in client.raw_agent_messages
        if item.get("thread_id") == expected_thread and item.get("turn_id") == expected_turn
    ]
    output_text = matching_messages[-1]["text"] if matching_messages else ""
    protocol = {
        "argv": list(resolved_argv),
        "thread_sha256": sha256_bytes(expected_thread.encode()) if expected_thread else "ABSENT",
        "turn_sha256": sha256_bytes(expected_turn.encode()) if expected_turn else "ABSENT",
        "terminal_count": len(client.raw_terminals),
        "terminal_binding_valid": terminal_valid,
        "terminal_status": str(terminal_status),
        "approval_request_count": len(client.approval_events),
        "unsupported_request_count": len(client.unsupported_server_requests),
        "agent_output_sha256": sha256_bytes(output_text.encode()) if output_text else "ABSENT",
    }
    if role == "VERIFIER" and output_text:
        try:
            structured = parse_verifier_verdict(output_text)
        except QualificationError:
            structured = {"role": "VERIFIER", "verdict": "FAIL"}
            failure = "RECEIPT_INTEGRITY_FAILURE"

    workspace_receipt = _workspace_receipt(workspace, before, git_before, fixture_before)
    qntylab_after = qntylab_snapshot(qntylab_root)
    roots = set(effective.get("writable_roots") or [])
    runtime_roots = set(effective.get("runtime_workspace_roots") or [])
    policy_common = (
        effective.get("cwd") == str(workspace)
        and effective.get("approval_policy") == "never"
        and effective.get("codex_home") == ROLE_BINDINGS[role][1]
        and effective.get("network_access") is False
    )
    if role == "BUILDER":
        policy_match = policy_common and effective.get("sandbox_class") == "workspaceWrite" and not (roots - {str(workspace)}) and runtime_roots == {str(workspace)}
        role_pass = (
            terminal_valid and terminal_status == "completed" and policy_match and not timed_out
            and gate == "PASS" and workspace_receipt["changed_paths"] == [FIXTURE_NAME]
            and workspace_receipt["git_changed_paths"] == [FIXTURE_NAME]
            and workspace_receipt["fixture_after"]["sha256"] == sha256_bytes(FIXTURE_TARGET_BYTES)
            and not workspace_receipt["unauthorized_writes"]
            and workspace_receipt["git_metadata_before_digest"] == workspace_receipt["git_metadata_after_digest"]
            and qntylab_before == qntylab_after
        )
        structured = {"role": "BUILDER", "verdict": "PASS" if role_pass else "FAIL"}
    else:
        policy_match = policy_common and effective.get("sandbox_class") == "readOnly" and roots == set() and runtime_roots == {str(workspace)}
        role_pass = (
            terminal_valid and terminal_status == "completed" and policy_match and not timed_out
            and gate == "PASS" and workspace_receipt["changed_paths"] == []
            and workspace_receipt["git_changed_paths"] == [FIXTURE_NAME]
            and workspace_receipt["fixture_after"]["sha256"] == sha256_bytes(FIXTURE_TARGET_BYTES)
            and workspace_receipt["git_metadata_before_digest"] == workspace_receipt["git_metadata_after_digest"]
            and qntylab_before == qntylab_after
            and structured.get("verdict") == "PASS"
        )
    effective["contract_match"] = policy_match
    if role_pass:
        failure = "NONE"
        lifecycle = "COMPLETED"
    elif failure == "PRODUCT_START_FAILURE" and product_started:
        failure = f"{role}_PRODUCT_FAILURE"
    return _base_receipt(
        role=role, version=binary_version, cwd=workspace, workspace_id=workspace_id,
        prompt=prompt, template_sha=template_sha, driver_sha=driver_sha, marker_sha=marker_sha,
        started_at=started_at, finished_at=utc_now(), timeout_seconds=timeout_seconds,
        timed_out=timed_out, product_started=product_started, process_exit=process_exit,
        lifecycle=lifecycle, protocol=protocol, effective_policy=effective,
        workspace=workspace_receipt, qntylab_before=qntylab_before, qntylab_after=qntylab_after,
        gate=gate, structured=structured, machine_status="PASS" if role_pass else "FAIL",
        failure_class=failure,
    )


def validate_role_receipt(
    receipt: Mapping[str, Any], *, role: str, workspace: Path, workspace_id: str,
    prompt_sha: str, template_sha: str, driver_sha: str, marker_sha: str,
) -> dict[str, Any]:
    data = dict(receipt)
    if set(data) != RECEIPT_KEYS:
        raise QualificationError("role receipt keys are not exact")
    if role not in ROLE_BINDINGS:
        raise QualificationError("expected role is unknown")
    product, profile, binary = ROLE_BINDINGS[role]
    exact = {
        "schema_version": SCHEMA_VERSION, "role": role, "product": product,
        "profile": profile, "binary_path": binary, "cwd": str(Path(workspace).resolve()),
        "workspace_identity": workspace_id, "prompt_sha256": prompt_sha,
        "prompt_template_sha256": template_sha, "driver_sha256": driver_sha,
        "started_marker_sha256": marker_sha,
    }
    if any(data.get(key) != item for key, item in exact.items()):
        raise QualificationError("role receipt binding mismatch")
    for key in ("binary_version", "started_at", "finished_at", "lifecycle", "api_key_gate", "machine_status", "failure_class"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise QualificationError(f"role receipt {key} is not concrete")
    if data["binary_version"] != ROLE_VERSIONS[role]:
        raise QualificationError("role receipt binary version mismatch")
    if data.get("subscription_backed") is not True or type(data.get("timeout_seconds")) is not int:
        raise QualificationError("role receipt identity or timeout is invalid")
    if type(data.get("timed_out")) is not bool or type(data.get("product_started")) is not bool:
        raise QualificationError("role receipt lifecycle booleans are invalid")
    for key in ("process_exit", "protocol", "effective_policy", "workspace", "qntylab_worktree", "structured_verdict"):
        if not isinstance(data.get(key), Mapping):
            raise QualificationError(f"role receipt {key} must be an object")
    if data["machine_status"] not in {"PASS", "FAIL"} or data["api_key_gate"] not in {"PASS", "FAIL"}:
        raise QualificationError("role receipt terminal enum is invalid")
    if data["machine_status"] == "PASS":
        if data["timed_out"] or not data["product_started"] or data["api_key_gate"] != "PASS" or data["lifecycle"] != "COMPLETED" or data["failure_class"] != "NONE":
            raise QualificationError("role PASS contradicts lifecycle")
        if data["qntylab_worktree"].get("mutations") != [] or data["workspace"].get("unauthorized_writes") != []:
            raise QualificationError("role PASS contradicts mutation evidence")
        if data["effective_policy"].get("contract_match") is not True:
            raise QualificationError("role PASS contradicts effective policy")
        process_exit = data["process_exit"]
        if not all(key in process_exit for key in ("termination", "exit_code", "exit_signal")):
            raise QualificationError("role PASS lacks concrete process exit evidence")
        if role == "INDEPENDENT_REVIEWER":
            process_ok = process_exit.get("termination") == "EXITED" and process_exit.get("exit_code") == 0 and process_exit.get("exit_signal") == 0
        else:
            process_ok = (
                (process_exit.get("termination") == "ALREADY_EXITED" and process_exit.get("exit_code") == 0)
                or (process_exit.get("termination") == "SIGTERM_PROCESS_GROUP" and process_exit.get("exit_signal") == signal.SIGTERM)
            )
        if not process_ok:
            raise QualificationError("role PASS contradicts process exit")
        if role == "BUILDER":
            if data["structured_verdict"] != {"role": "BUILDER", "verdict": "PASS"}:
                raise QualificationError("builder PASS verdict is malformed")
            if data["workspace"].get("changed_paths") != [FIXTURE_NAME] or data["workspace"].get("git_changed_paths") != [FIXTURE_NAME]:
                raise QualificationError("builder PASS contradicts changed paths")
        elif role == "INDEPENDENT_REVIEWER":
            parse_reviewer_verdict(data["structured_verdict"])
            if data["structured_verdict"].get("verdict") != "PASS" or data["workspace"].get("changed_paths") != []:
                raise QualificationError("reviewer PASS contradicts evidence")
        else:
            parse_verifier_verdict(data["structured_verdict"])
            if data["structured_verdict"].get("verdict") != "PASS" or data["workspace"].get("changed_paths") != []:
                raise QualificationError("verifier PASS contradicts evidence")
    return data


def overall_qualification_pass(receipts: Mapping[str, Mapping[str, Any]], attempts: Mapping[str, int]) -> bool:
    return (
        set(receipts) == set(ROLE_BINDINGS)
        and attempts == {role: 1 for role in ROLE_BINDINGS}
        and all(receipts[role].get("machine_status") == "PASS" for role in ROLE_BINDINGS)
        and all(receipts[role].get("api_key_gate") == "PASS" for role in ROLE_BINDINGS)
    )
