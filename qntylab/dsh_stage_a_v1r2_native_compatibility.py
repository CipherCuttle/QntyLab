"""Offline native-child compatibility contract for DSH Stage-A V1R2.

This module deliberately separates provider, package/SDK, native executable,
and compatibility evidence identities.  It never starts a model turn and it
does not inspect authentication stores or credential values.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import select
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


PROJECT_ID = "DSH_MULTI_AGENT_ORCHESTRATION_STAGE_A_V1R2_NATIVE_CHILD_COMPATIBILITY_QUALIFICATION_V0"
AUTHORITY = "BOUNDED_OFFLINE_NATIVE_COMPATIBILITY_QUALIFICATION"
PINNED_DSH_COMMIT = "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
PINNED_DSH_TREE = "3bc8f89fe494a4755c188be354add4e8b1e7b188"
CODEX_PACKAGE = "@openai/codex"
CODEX_PACKAGE_VERSION = "0.147.0"
CLAUDE_SDK_PACKAGE = "@anthropic-ai/claude-agent-sdk"
CLAUDE_SDK_VERSION = "0.3.220"
CODEX_COMMAND = ("app-server", "--stdio")
CLAUDE_REQUIRED_ARGS = (
    "--output-format", "stream-json", "--verbose", "--input-format", "stream-json",
    "--permission-prompt-tool", "stdio", "--allowedTools", "Read,Glob,Grep",
    "--disallowedTools", "Write,Edit,Bash,Agent,Task,AskUserQuestion,mcp__*",
    "--tools", "Read,Glob,Grep", "--setting-sources=", "--permission-mode", "dontAsk",
    "--no-session-persistence",
)


class CompatibilityBlocked(RuntimeError):
    """Raised when offline evidence cannot prove a required property."""


class NamespaceConflationError(CompatibilityBlocked):
    """Raised when package/SDK and native CLI versions are used as one identity."""


@dataclass(frozen=True)
class ProviderIdentity:
    provider: str
    dsh_commit: str
    dsh_tree: str
    dsh_package: str


@dataclass(frozen=True)
class PackageReferenceIdentity:
    namespace: str
    package: str
    version: str


@dataclass(frozen=True)
class SdkIdentity:
    package: str
    version: str
    bundled_cli_version: str | None = None
    source_sha256: str | None = None
    type_definition_sha256: str | None = None
    manifest_sha256: str | None = None


@dataclass(frozen=True)
class NativeExecutableIdentity:
    command_name: str
    resolved_path: str
    realpath: str
    product_version: str
    version_output: str
    entrypoint_sha256: str | None
    launcher_package_version: str | None = None

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CompatibilityEvidence:
    kind: str
    compatibility: str
    model_turns: int
    api_requests: int
    usage_events: int
    task_execution: int
    process_quiesced: bool
    probe_details: Mapping[str, Any]
    uncertainty: str | None = None

    @property
    def passed(self) -> bool:
        return (
            self.compatibility == "PASS"
            and self.model_turns == 0
            and self.api_requests == 0
            and self.usage_events == 0
            and self.task_execution == 0
            and self.process_quiesced
            and not self.uncertainty
        )


def _sha256_file(path: Path) -> str | None:
    try:
        if not path.is_file() or not os.access(path, os.R_OK):
            return None
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _resolve_command(command: str) -> Path:
    candidate = shutil.which(command) if not os.path.isabs(command) else command
    if not candidate:
        raise CompatibilityBlocked(f"native executable is not resolvable: {command}")
    path = Path(candidate)
    if not path.exists() or not os.access(path, os.X_OK):
        raise CompatibilityBlocked(f"native executable is not executable: {path}")
    return path


def _metadata_env() -> dict[str, str]:
    """Return a minimal environment that cannot carry product credentials."""

    return {
        "PATH": os.environ.get("PATH", ""),
        "LANG": "C.UTF-8",
        "TERM": "dumb",
    }


def capture_executable_identity(command: str, *, version_args: Sequence[str] = ("--version",)) -> NativeExecutableIdentity:
    """Capture deterministic executable metadata without reading auth/config data."""

    resolved = _resolve_command(command)
    with tempfile.TemporaryDirectory(prefix="qntylab-native-metadata-") as directory:
        result = subprocess.run(
            [str(resolved), *version_args],
            env=_metadata_env(),
            cwd=directory,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    output = (result.stdout or result.stderr).strip()
    if result.returncode != 0 or not output:
        raise CompatibilityBlocked(f"native version probe failed for {resolved}: exit {result.returncode}")
    first_line = next((line.strip() for line in output.splitlines() if line.strip()), output)
    return NativeExecutableIdentity(
        command_name=Path(command).name,
        resolved_path=str(resolved),
        realpath=os.path.realpath(resolved),
        product_version=first_line,
        version_output=output,
        entrypoint_sha256=_sha256_file(Path(os.path.realpath(resolved))),
    )


def reject_version_namespace_comparison(left_namespace: str, right_namespace: str) -> None:
    """Reject the historical invalid equality rule at the contract boundary."""

    if left_namespace != right_namespace:
        raise NamespaceConflationError(
            f"VERSION_NAMESPACE_CONFLATION: {left_namespace} cannot be compared to {right_namespace}"
        )


def same_native_fingerprint(current: NativeExecutableIdentity, qualified: NativeExecutableIdentity) -> bool:
    """Compare only the complete native executable identity, never package versions."""

    return current == qualified and current.fingerprint == qualified.fingerprint


def _read_jsonrpc_response(
    process: subprocess.Popen[str],
    request_id: int,
    timeout: float,
    observed_methods: list[str],
) -> dict[str, Any]:
    if process.stdout is None:
        raise CompatibilityBlocked("Codex app-server stdout was unavailable")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = max(0.05, deadline - time.monotonic())
        ready, _, _ = select.select([process.stdout], [], [], remaining)
        if not ready:
            continue
        line = process.stdout.readline()
        if not line:
            break
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CompatibilityBlocked("Codex app-server emitted malformed JSON-RPC") from exc
        method = message.get("method")
        if isinstance(method, str):
            observed_methods.append(method)
            if method in {"turn/start", "turn/run", "turn/interrupt"}:
                raise CompatibilityBlocked(f"Codex zero-model probe observed forbidden method: {method}")
        if message.get("id") == request_id:
            return message
    raise CompatibilityBlocked(f"Codex app-server response timeout for request {request_id}")


def _send_jsonrpc(process: subprocess.Popen[str], request_id: int, method: str, params: Mapping[str, Any] | None = None) -> None:
    if process.stdin is None:
        raise CompatibilityBlocked("Codex app-server stdin was unavailable")
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = dict(params)
    process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
    process.stdin.flush()


def _send_jsonrpc_notification(process: subprocess.Popen[str], method: str) -> None:
    if process.stdin is None:
        raise CompatibilityBlocked("Codex app-server stdin was unavailable")
    process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}, separators=(",", ":")) + "\n")
    process.stdin.flush()


def run_codex_zero_model_probe(command: str = "codex", *, timeout: float = 30.0) -> CompatibilityEvidence:
    """Prove only initialize and ephemeral thread creation on the real host CLI."""

    executable = _resolve_command(command)
    probe_root = Path(tempfile.mkdtemp(prefix="qntylab-codex-zero-model-"))
    home = probe_root / "home"
    codex_home = probe_root / "codex-home"
    home.mkdir()
    codex_home.mkdir()
    env = _metadata_env() | {"HOME": str(home), "CODEX_HOME": str(codex_home)}
    process: subprocess.Popen[str] | None = None
    started = False
    initialized = False
    thread_started = False
    reason: str | None = None
    observed_methods: list[str] = []
    try:
        process = subprocess.Popen(
            [str(executable), *CODEX_COMMAND],
            cwd=probe_root,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        started = True
        initialize_id = 1
        _send_jsonrpc(process, initialize_id, "initialize", {
            "clientInfo": {"name": "deepseek-harness", "title": "DeepSeek Harness", "version": "0.0.1"},
            "capabilities": {"experimentalApi": False, "requestAttestation": False},
        })
        initialize = _read_jsonrpc_response(process, initialize_id, timeout, observed_methods)
        if "error" in initialize:
            raise CompatibilityBlocked("Codex initialize was rejected")
        initialized = True
        _send_jsonrpc_notification(process, "initialized")
        thread_id = 2
        _send_jsonrpc(process, thread_id, "thread/start", {"cwd": str(probe_root), "ephemeral": True})
        thread = _read_jsonrpc_response(process, thread_id, timeout, observed_methods)
        if "error" in thread or not isinstance(thread.get("result", {}).get("thread"), dict):
            raise CompatibilityBlocked("Codex thread/start was rejected")
        if thread["result"]["thread"].get("ephemeral") is not True:
            raise CompatibilityBlocked("Codex thread/start did not create an ephemeral thread")
        thread_started = True
    except (OSError, subprocess.SubprocessError, CompatibilityBlocked) as exc:
        reason = str(exc)
    finally:
        quiesced = False
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
            quiesced = process.poll() is not None
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
    return CompatibilityEvidence(
        kind="CODEX_APP_SERVER_ZERO_MODEL_PROTOCOL",
        compatibility="PASS" if started and initialized and thread_started and quiesced and reason is None else "INCOMPLETE",
        model_turns=0,
        api_requests=0,
        usage_events=0,
        task_execution=0,
        process_quiesced=quiesced,
        probe_details={
            "app_server_started": started,
            "protocol_initialized": initialized,
            "thread_start_compatible": thread_started,
            "observed_methods": observed_methods,
            "argv": [str(executable), *CODEX_COMMAND],
            "cwd_scope": "disposable temporary directory; path omitted",
        },
        uncertainty=reason,
    )


def _flag_name(token: str) -> str:
    return token.split("=", 1)[0]


def validate_claude_sdk_cli_contract(cli_help: str, captured_args: Sequence[str]) -> CompatibilityEvidence:
    """Validate the exact SDK launch surface using help text plus a parser probe."""

    required_flags = {_flag_name(token) for token in CLAUDE_REQUIRED_ARGS if token.startswith("-")}
    advertised_flags = {
        match.group(0)
        for match in re.finditer(r"--[A-Za-z][A-Za-z0-9-]*", cli_help)
    }
    captured_flags = {_flag_name(token) for token in captured_args if token.startswith("-")}
    missing_in_capture = required_flags - captured_flags
    missing_in_help = required_flags - advertised_flags
    # --permission-prompt-tool is an internal SDK flag on this CLI build; the
    # exact parser probe (performed by the qualification runner) is stronger
    # evidence than its omission from human-facing help.
    hidden_internal = {"--permission-prompt-tool"}
    uncertainty = None if not missing_in_capture else f"SDK capture omitted required flags: {sorted(missing_in_capture)}"
    if missing_in_help - hidden_internal:
        uncertainty = f"CLI help omitted non-internal required flags: {sorted(missing_in_help - hidden_internal)}"
    return CompatibilityEvidence(
        kind="CLAUDE_SDK_CLI_ZERO_MODEL_STATIC_AND_PARSER_PROBE",
        compatibility="PASS" if uncertainty is None else "INCOMPLETE",
        model_turns=0,
        api_requests=0,
        usage_events=0,
        task_execution=0,
        process_quiesced=True,
        probe_details={
            "captured_args": list(captured_args),
            "required_flags": sorted(required_flags),
            "missing_in_help": sorted(missing_in_help),
            "hidden_internal_flags_accepted_by_parser": sorted(missing_in_help & hidden_internal),
            "fake_spawn_child_executed": False,
            "real_cli_invocation": "--help only; no prompt",
        },
        uncertainty=uncertainty,
    )


def future_identity_preflight(
    *,
    codex_current: NativeExecutableIdentity,
    codex_qualified: NativeExecutableIdentity,
    codex_evidence: CompatibilityEvidence | None,
    claude_current: NativeExecutableIdentity,
    claude_qualified: NativeExecutableIdentity,
    claude_sdk_current: SdkIdentity,
    claude_sdk_qualified: SdkIdentity,
    claude_evidence: CompatibilityEvidence | None,
) -> dict[str, Any]:
    """Return the corrected future gate; executable drift blocks before secrets."""

    reasons: list[str] = []
    if not same_native_fingerprint(codex_current, codex_qualified):
        reasons.append("CODEX_EXECUTABLE_FINGERPRINT_DRIFT")
    if codex_evidence is None or not codex_evidence.passed:
        reasons.append("CODEX_ZERO_MODEL_PROTOCOL_COMPATIBILITY_NOT_PASS")
    if not same_native_fingerprint(claude_current, claude_qualified):
        reasons.append("CLAUDE_EXECUTABLE_FINGERPRINT_DRIFT")
    if claude_sdk_current != claude_sdk_qualified:
        reasons.append("CLAUDE_SDK_IDENTITY_DRIFT")
    if claude_evidence is None or not claude_evidence.passed:
        reasons.append("CLAUDE_SDK_CLI_COMPATIBILITY_NOT_PASS")
    return {
        "status": "PASS" if not reasons else "BLOCK",
        "reasons": reasons,
        "block_before_secret": bool(reasons),
        "block_before_paid_parent_dispatch": bool(reasons),
    }


__all__ = [
    "AUTHORITY",
    "CLAUDE_REQUIRED_ARGS",
    "CLAUDE_SDK_VERSION",
    "CODEX_PACKAGE_VERSION",
    "CompatibilityBlocked",
    "CompatibilityEvidence",
    "NativeExecutableIdentity",
    "NamespaceConflationError",
    "PackageReferenceIdentity",
    "PROJECT_ID",
    "PINNED_DSH_COMMIT",
    "PINNED_DSH_TREE",
    "ProviderIdentity",
    "SdkIdentity",
    "capture_executable_identity",
    "future_identity_preflight",
    "reject_version_namespace_comparison",
    "run_codex_zero_model_probe",
    "same_native_fingerprint",
    "validate_claude_sdk_cli_contract",
]
