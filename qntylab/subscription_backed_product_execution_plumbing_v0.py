"""Fail-closed, lab-only plumbing for subscription-backed product runs.

This module deliberately stops at transport, process, workspace, and result
normalization boundaries.  It has no scientific, trading, scheduling, or
runtime authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


API_KEY_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENROUTER_API_KEY",
)
FORBIDDEN_PARENT_FIELDS = ("parentLlmProvider", "parentLlmRequestCount")
SEVERITIES = ("NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL")


class QualificationError(ValueError):
    """A malformed or unsafe qualification input/result."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sanitize_environment(
    base: Mapping[str, str] | None = None,
    additions: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, bool]]:
    """Remove pay-per-token and common GitHub credentials without reading values."""

    source = dict(os.environ if base is None else base)
    presence = {name: bool(source.get(name)) for name in API_KEY_NAMES}
    presence.update({name: bool(source.get(name)) for name in ("GITHUB_TOKEN", "GH_TOKEN")})
    clean = {key: value for key, value in source.items() if key not in (*API_KEY_NAMES, "GITHUB_TOKEN", "GH_TOKEN")}
    if additions:
        if any(key in API_KEY_NAMES or key in {"GITHUB_TOKEN", "GH_TOKEN"} for key in additions):
            raise QualificationError("credential-shaped environment additions are forbidden")
        clean.update({str(key): str(value) for key, value in additions.items()})
    return clean, presence


@dataclass(frozen=True)
class ProductInvocation:
    route: str
    product: str
    profile: str
    cwd: Path
    workspace_scope: Path
    prompt: str
    approval_mode: str
    sandbox_mode: str
    environment_policy: str = "API_KEYS_REMOVED_GITHUB_CREDENTIALS_REMOVED"
    parent_llm_provider: str = "NONE"
    parent_llm_request_count: int = 0

    def validate(self) -> None:
        if self.route not in {"DSH", "NATIVE"}:
            raise QualificationError("unknown transport route")
        if self.product not in {"CODEX_PROFILE_A", "CODEX_PROFILE_B", "CLAUDE_CODE"}:
            raise QualificationError("unknown product/profile")
        profile_id = "A" if self.profile in {"A", "/home/swirky/.codex"} else "B" if self.profile in {"B", "/home/swirky/.codex-pro2"} else None
        if self.product == "CODEX_PROFILE_A" and profile_id != "A":
            raise QualificationError("Codex Profile A invocation has a mismatched profile")
        if self.product == "CODEX_PROFILE_B" and profile_id != "B":
            raise QualificationError("Codex Profile B invocation has a mismatched profile")
        cwd = self.cwd.resolve()
        scope = self.workspace_scope.resolve()
        if cwd != scope:
            raise QualificationError("cwd must equal the bounded workspace scope")
        if not scope.is_dir():
            raise QualificationError("workspace scope must be an existing directory")
        if not self.prompt:
            raise QualificationError("prompt must be non-empty")
        if self.approval_mode not in {"never", "default"}:
            raise QualificationError("approval mode is not an allowed bounded mode")
        if self.sandbox_mode != "workspace-write":
            raise QualificationError("qualification requires bounded workspace-write mode")
        if self.parent_llm_provider != "NONE" or self.parent_llm_request_count != 0:
            raise QualificationError("DSH parent LLM must be NONE with zero requests")

    def observable(self) -> dict[str, Any]:
        self.validate()
        return {
            "route": self.route,
            "product": self.product,
            "profile": self.profile,
            "cwd": str(self.cwd.resolve()),
            "workspace_scope": str(self.workspace_scope.resolve()),
            "approval_mode": self.approval_mode,
            "sandbox_mode": self.sandbox_mode,
            "environment_policy": self.environment_policy,
            "parent_llm_provider": self.parent_llm_provider,
            "parent_llm_request_count": self.parent_llm_request_count,
            "prompt_sha256": sha256_bytes(self.prompt.encode()),
        }


def compare_parity(dsh: Mapping[str, Any], native: Mapping[str, Any]) -> list[str]:
    """Compare corresponding settings, ignoring only transport ownership."""

    ignored = {"route", "transport", "transport_owner"}
    keys = (set(dsh) | set(native)) - ignored
    return sorted(key for key in keys if dsh.get(key) != native.get(key))


@dataclass(frozen=True)
class NormalizedProductResult:
    status: str
    output: str
    stop_reason: str
    error: str | None
    normal_disposal: bool


def _objects(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def normalize_product_result(raw: Mapping[str, Any], *, require_output: bool = True) -> NormalizedProductResult:
    """Normalize DSH/native receipts at one strict boundary.

    A claimed top-level COMPLETED is insufficient.  A positive terminal
    lifecycle event is required, and any lifecycle error wins over prose.
    """

    if not isinstance(raw, Mapping):
        return NormalizedProductResult("FAIL_CLOSED", "", "missing", "raw result is not an object", False)
    lifecycle = raw.get("lifecycle")
    ends = _objects(lifecycle.get("ends")) if isinstance(lifecycle, Mapping) else []
    stop_reasons = [str(item.get("stopReason")) for item in ends if "stopReason" in item]
    explicit_error = any(reason in {"error", "failed", "aborted", "cancelled"} for reason in stop_reasons)
    completed = any(reason == "completed" for reason in stop_reasons)
    output = raw.get("output", "")
    if not isinstance(output, str):
        output = ""
    error = raw.get("error")
    error_text = json.dumps(error, sort_keys=True) if error is not None else None
    process_items = _objects(raw.get("processes"))
    normal_disposal = completed and any(item.get("signal") == "SIGTERM" for item in process_items)

    if raw.get("parentLlmProvider", "NONE") != "NONE" or raw.get("parentLlmRequestCount", 0) != 0 or raw.get("dshParentServiceMounted") is True:
        return NormalizedProductResult("FAIL_CLOSED", output, "error", "DSH parent LLM activity was observed", normal_disposal)
    if raw.get("status") not in {"COMPLETED", "SUCCESS"}:
        return NormalizedProductResult("FAIL_CLOSED", output, "missing", "explicit successful top-level status is missing", False)
    if isinstance(raw.get("bridgeExitCode"), int) and raw["bridgeExitCode"] != 0:
        return NormalizedProductResult("ERROR", output, "error", "product bridge exited nonzero", normal_disposal)
    if explicit_error or error is not None:
        return NormalizedProductResult("ERROR", output, "error", error_text or "product lifecycle error", normal_disposal)
    if not completed:
        return NormalizedProductResult("FAIL_CLOSED", output, stop_reasons[-1] if stop_reasons else "missing", "explicit successful lifecycle is missing", False)
    if require_output and not output.strip():
        return NormalizedProductResult("FAIL_CLOSED", "", "completed", "successful lifecycle had empty output", normal_disposal)
    return NormalizedProductResult("COMPLETED", output, "completed", None, normal_disposal)


def _strict_json(text: str) -> Mapping[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise QualificationError("structured role output is empty")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise QualificationError("structured role output is malformed JSON") from exc
    if not isinstance(value, Mapping):
        raise QualificationError("structured role output must be a JSON object")
    return value


def parse_reviewer_output(text: str) -> dict[str, Any]:
    value = _strict_json(text)
    if set(value) != {"status", "highest_severity", "findings"}:
        raise QualificationError("reviewer keys are not exact")
    status = value["status"]
    severity = value["highest_severity"]
    findings = value["findings"]
    if status not in {"PASS", "REPAIR_REQUIRED"} or severity not in SEVERITIES or not isinstance(findings, list):
        raise QualificationError("reviewer terminal fields are invalid")
    normalized: list[dict[str, str]] = []
    for finding in findings:
        if not isinstance(finding, Mapping) or set(finding) != {"id", "severity", "path"}:
            raise QualificationError("reviewer finding shape is invalid")
        if not all(isinstance(finding[key], str) and finding[key] for key in ("id", "severity", "path")):
            raise QualificationError("reviewer finding field is invalid")
        if finding["severity"] not in SEVERITIES[1:]:
            raise QualificationError("reviewer finding severity is invalid")
        normalized.append({key: finding[key] for key in ("id", "severity", "path")})
    if status == "PASS" and (severity != "NONE" or normalized):
        raise QualificationError("reviewer PASS contradicts severity/findings")
    if status == "REPAIR_REQUIRED" and (severity == "NONE" or not normalized):
        raise QualificationError("reviewer repair state lacks severity/findings")
    if normalized and max(SEVERITIES.index(item["severity"]) for item in normalized) != SEVERITIES.index(severity):
        raise QualificationError("reviewer highest severity contradicts findings")
    return {"status": status, "highest_severity": severity, "findings": normalized}


def parse_verifier_output(text: str) -> dict[str, Any]:
    value = _strict_json(text)
    if set(value) != {"status", "checks", "diagnostics"}:
        raise QualificationError("verifier keys are not exact")
    if value["status"] not in {"PASS", "FAIL"} or not isinstance(value["checks"], Mapping) or not isinstance(value["diagnostics"], list):
        raise QualificationError("verifier terminal fields are invalid")
    checks = dict(value["checks"])
    if any(not isinstance(key, str) or not isinstance(item, str) for key, item in checks.items()):
        raise QualificationError("verifier checks must be string mappings")
    if value["status"] == "PASS" and value["diagnostics"]:
        raise QualificationError("verifier PASS contradicts diagnostics")
    if value["status"] == "FAIL" and not value["diagnostics"]:
        raise QualificationError("verifier FAIL lacks diagnostics")
    return {"status": value["status"], "checks": checks, "diagnostics": list(value["diagnostics"])}


def workspace_snapshot(root: Path) -> dict[str, str]:
    root = root.resolve()
    if not root.is_dir():
        raise QualificationError("workspace does not exist")
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.relative_to(root).parts:
            result[str(path.relative_to(root))] = sha256_file(path)
    return result


def snapshot_digest(snapshot: Mapping[str, str]) -> str:
    return sha256_bytes(canonical_json(dict(sorted(snapshot.items()))))


def changed_paths(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def enforce_allowed_changes(before: Mapping[str, str], after: Mapping[str, str], allowed: Sequence[str]) -> list[str]:
    allowed_set = set(allowed)
    changes = changed_paths(before, after)
    unauthorized = [path for path in changes if path not in allowed_set]
    if unauthorized:
        raise QualificationError(f"unauthorized workspace changes: {unauthorized}")
    return changes


@dataclass(frozen=True)
class TestStageResult:
    argv: tuple[str, ...]
    cwd: str
    started_at: str
    ended_at: str
    returncode: int | None
    stdout_sha256: str
    stderr_sha256: str
    timed_out: bool
    termination: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0 and not self.timed_out and self.termination == "EXITED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "argv": list(self.argv), "cwd": self.cwd, "started_at": self.started_at,
            "ended_at": self.ended_at, "returncode": self.returncode,
            "stdout_sha256": self.stdout_sha256, "stderr_sha256": self.stderr_sha256,
            "timed_out": self.timed_out, "termination": self.termination, "passed": self.passed,
        }


def run_test_command(argv: Sequence[str], cwd: Path, *, timeout_seconds: float = 120.0) -> TestStageResult:
    if isinstance(argv, (str, bytes)) or not argv or any(not isinstance(item, str) or not item for item in argv):
        raise QualificationError("test command must be a non-empty argv vector")
    cwd = cwd.resolve()
    if not cwd.is_dir():
        raise QualificationError("test cwd does not exist")
    started_at = utc_now()
    started = time.monotonic()
    timed_out = False
    termination = "EXITED"
    returncode: int | None
    stdout = b""
    stderr = b""
    try:
        completed = subprocess.run(list(argv), cwd=cwd, capture_output=True, timeout=timeout_seconds, check=False)
        returncode, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        termination = "TIMED_OUT"
        returncode = None
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
    except OSError as exc:
        raise QualificationError(f"test command could not start: {exc}") from exc
    ended_at = utc_now()
    _ = started  # retained to make the timing boundary explicit in review.
    return TestStageResult(tuple(argv), str(cwd), started_at, ended_at, returncode, sha256_bytes(stdout), sha256_bytes(stderr), timed_out, termination)


def run_product_bridge(argv: Sequence[str], invocation: ProductInvocation, *, timeout_seconds: float = 900.0) -> dict[str, Any]:
    """Run a fixed external product bridge and return only sanitized JSON data."""

    invocation.validate()
    clean_env, presence = sanitize_environment()
    clean_env["QNTYLAB_PRODUCT_CWD"] = str(invocation.cwd.resolve())
    clean_env["QNTYLAB_WORKSPACE_SCOPE"] = str(invocation.workspace_scope.resolve())
    clean_env["QNTYLAB_PROFILE"] = invocation.profile
    try:
        completed = subprocess.run(list(argv), cwd=invocation.cwd, env=clean_env, capture_output=True, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "FAIL_CLOSED", "output": "", "error": "bridge timeout", "apiKeyPresence": presence}
    try:
        bridge_text = completed.stdout.decode("utf-8")
        value = json.loads(next(line for line in reversed(bridge_text.splitlines()) if line.strip()))
    except (StopIteration, UnicodeDecodeError, json.JSONDecodeError):
        value = {"status": "FAIL_CLOSED", "output": "", "error": "bridge returned non-JSON output"}
    if not isinstance(value, dict):
        value = {"status": "FAIL_CLOSED", "output": "", "error": "bridge returned non-object JSON"}
    value["apiKeyPresence"] = presence
    value["bridgeExitCode"] = completed.returncode
    value["stdoutSha256"] = sha256_bytes(completed.stdout)
    value["stderrSha256"] = sha256_bytes(completed.stderr)
    return value


def assert_v1_consumed(record: Mapping[str, Any]) -> None:
    execution = record.get("execution")
    invariant = record.get("no_rerun_invariant")
    if not isinstance(execution, Mapping) or not isinstance(invariant, Mapping):
        raise QualificationError("canonical V1 consumed-state record is incomplete")
    if execution.get("episode_consumed") is not True or execution.get("authorized_episode_count") != 1:
        raise QualificationError("canonical V1 consumed-state changed")
    if invariant.get("second_episode_under_v1_allowed") is not False or invariant.get("rescue_rerun_allowed") is not False:
        raise QualificationError("canonical V1 rerun prohibition changed")
