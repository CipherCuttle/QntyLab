#!/usr/bin/env python3
"""Committed/hash-bound read-only Claude Code subscription reviewer driver."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qntylab.subscription_backed_native_product_execution_qualification_v0 import (  # noqa: E402
    CLAUDE_BINARY,
    FIXTURE_TARGET_BYTES,
    QualificationError,
    _base_receipt,
    _workspace_receipt,
    api_key_gate,
    canonical_json,
    fixture_observation,
    git_metadata_snapshot,
    parse_reviewer_verdict,
    qntylab_snapshot,
    reviewer_json_schema,
    sanitized_environment,
    sha256_bytes,
    strict_json_object,
    utc_now,
    validate_workspace_boundary,
    workspace_snapshot,
)

CLAUDE_VERSION = "2.1.223 (Claude Code)"


def frozen_argv(binary: str = CLAUDE_BINARY) -> list[str]:
    return [
        binary,
        "--print",
        "--output-format", "json",
        "--json-schema", canonical_json(reviewer_json_schema()).decode("utf-8").strip(),
        "--permission-mode", "plan",
        "--tools", "",
        "--safe-mode",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--mcp-config", '{"mcpServers":{}}',
    ]


def parse_claude_transport(stdout: bytes) -> dict[str, Any]:
    wrapper = strict_json_object(stdout)
    required = {"type", "subtype", "is_error", "structured_output"}
    if not required.issubset(wrapper):
        raise QualificationError("Claude transport result is missing required fields")
    if wrapper["type"] != "result" or wrapper["subtype"] != "success" or wrapper["is_error"] is not False:
        raise QualificationError("Claude transport lifecycle is not successful")
    if not isinstance(wrapper["structured_output"], Mapping):
        raise QualificationError("Claude structured_output is not an object")
    return parse_reviewer_verdict(wrapper["structured_output"])


def run_role(
    *,
    workspace: Path,
    qntylab_root: Path,
    prompt: bytes,
    workspace_identity: str,
    prompt_template_sha256: str,
    driver_sha256: str,
    started_marker_sha256: str,
    timeout_seconds: int = 180,
    argv: Sequence[str] | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    workspace, qntylab_root = validate_workspace_boundary(workspace, qntylab_root)
    before = workspace_snapshot(workspace)
    git_before = git_metadata_snapshot(workspace)
    fixture_before = fixture_observation(workspace)
    qntylab_before = qntylab_snapshot(qntylab_root)
    started_at = utc_now()
    clean_env, presence = sanitized_environment(environment)
    gate = api_key_gate(presence)
    resolved_argv = list(argv or frozen_argv())
    expected_argv = frozen_argv(resolved_argv[0])
    product_started = False
    timed_out = False
    lifecycle = "BLOCKED_BEFORE_PRODUCT_START" if gate == "FAIL" else "NOT_STARTED"
    failure = "API_KEY_GATE_FAILURE" if gate == "FAIL" else "PRODUCT_START_FAILURE"
    returncode = -1
    termination = "NOT_STARTED"
    stdout = b""
    stderr = b""
    structured: dict[str, Any] = {"role": "INDEPENDENT_REVIEWER", "verdict": "FAIL"}

    if gate == "PASS":
        try:
            process = subprocess.Popen(
                resolved_argv,
                cwd=workspace,
                env=clean_env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            product_started = True
            lifecycle = "STARTED"
            try:
                stdout, stderr = process.communicate(prompt, timeout=timeout_seconds)
                returncode = process.returncode if isinstance(process.returncode, int) else -1
                termination = "EXITED"
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                stdout = exc.stdout or b""
                stderr = exc.stderr or b""
                os.killpg(process.pid, signal.SIGTERM)
                termination = "SIGTERM_PROCESS_GROUP_AFTER_TIMEOUT"
                try:
                    more_stdout, more_stderr = process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    termination = "SIGKILL_PROCESS_GROUP_AFTER_TIMEOUT"
                    more_stdout, more_stderr = process.communicate(timeout=10)
                stdout += more_stdout or b""
                stderr += more_stderr or b""
                returncode = process.returncode if isinstance(process.returncode, int) else -1
                lifecycle = "TIMED_OUT"
                failure = "REVIEWER_PRODUCT_FAILURE"
        except OSError:
            lifecycle = "START_FAILED"
            failure = "PRODUCT_START_FAILURE"

    if product_started and not timed_out and returncode == 0:
        try:
            structured = parse_claude_transport(stdout)
            lifecycle = "COMPLETED"
        except QualificationError:
            lifecycle = "INVALID_STRUCTURED_RECEIPT"
            failure = "RECEIPT_INTEGRITY_FAILURE"
    elif product_started and not timed_out:
        lifecycle = "PROCESS_NONZERO"
        failure = "REVIEWER_PRODUCT_FAILURE"

    workspace_receipt = _workspace_receipt(workspace, before, git_before, fixture_before)
    qntylab_after = qntylab_snapshot(qntylab_root)
    policy_match = resolved_argv == expected_argv
    effective = {
        "permission_mode": "plan",
        "built_in_tools": "DISABLED",
        "mcp": "STRICT_EMPTY_CONFIGURATION",
        "safe_mode": True,
        "session_persistence": False,
        "observed_enforcement": "ARGV_ACCEPTED_AND_ZERO_MUTATION" if returncode == 0 and workspace_receipt["changed_paths"] == [] else "NOT_ESTABLISHED",
        "contract_match": policy_match,
    }
    role_pass = (
        lifecycle == "COMPLETED" and structured.get("verdict") == "PASS"
        and gate == "PASS" and not timed_out and product_started and returncode == 0
        and policy_match and workspace_receipt["changed_paths"] == []
        and workspace_receipt["git_changed_paths"] == ["fixture.txt"]
        and workspace_receipt["fixture_after"]["sha256"] == sha256_bytes(FIXTURE_TARGET_BYTES)
        and workspace_receipt["git_metadata_before_digest"] == workspace_receipt["git_metadata_after_digest"]
        and qntylab_before == qntylab_after
    )
    if role_pass:
        failure = "NONE"
    protocol = {
        "argv": ["<CLAUDE_BINARY>" if item == resolved_argv[0] else item for item in resolved_argv],
        "stdin_prompt_sha256": sha256_bytes(prompt),
        "stdout_sha256": sha256_bytes(stdout),
        "stderr_sha256": sha256_bytes(stderr),
        "structured_output_present": isinstance(structured, Mapping) and len(structured) == len({"role", "verdict", "builder_task_satisfied", "changed_paths_match", "fixture_match", "unauthorized_writes", "reasons"}),
    }
    process_exit = {
        "disposed": product_started,
        "termination": termination,
        "exit_code": returncode if returncode >= 0 else -1,
        "exit_signal": -returncode if returncode < 0 and product_started else 0,
    }
    return _base_receipt(
        role="INDEPENDENT_REVIEWER", version=CLAUDE_VERSION, cwd=workspace,
        workspace_id=workspace_identity, prompt=prompt, template_sha=prompt_template_sha256,
        driver_sha=driver_sha256, marker_sha=started_marker_sha256, started_at=started_at,
        finished_at=utc_now(), timeout_seconds=timeout_seconds, timed_out=timed_out,
        product_started=product_started, process_exit=process_exit, lifecycle=lifecycle,
        protocol=protocol, effective_policy=effective, workspace=workspace_receipt,
        qntylab_before=qntylab_before, qntylab_after=qntylab_after, gate=gate,
        structured=structured, machine_status="PASS" if role_pass else "FAIL",
        failure_class=failure,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--qntylab-root", type=Path, required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--workspace-identity", required=True)
    parser.add_argument("--prompt-template-sha256", required=True)
    parser.add_argument("--driver-sha256", required=True)
    parser.add_argument("--started-marker-sha256", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = run_role(
            workspace=args.workspace, qntylab_root=args.qntylab_root,
            prompt=args.prompt_file.read_bytes(), workspace_identity=args.workspace_identity,
            prompt_template_sha256=args.prompt_template_sha256,
            driver_sha256=args.driver_sha256, started_marker_sha256=args.started_marker_sha256,
            timeout_seconds=args.timeout_seconds,
        )
    except (OSError, QualificationError) as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "error_class": type(exc).__name__}, sort_keys=True))
        return 2
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["machine_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
