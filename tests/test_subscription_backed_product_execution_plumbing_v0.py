from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from qntylab.subscription_backed_product_execution_plumbing_v0 import (
    ProductInvocation,
    QualificationError,
    assert_v1_consumed,
    changed_paths,
    compare_parity,
    enforce_allowed_changes,
    normalize_product_result,
    parse_reviewer_output,
    parse_verifier_output,
    run_test_command,
    sanitize_environment,
    snapshot_digest,
    workspace_snapshot,
)


def _raw(*, stop_reason: str = "completed", output: str = "ok", **extra: object) -> dict:
    return {
        "status": "COMPLETED",
        "output": output,
        "lifecycle": {"ends": [{"provider": "codex", "stopReason": stop_reason}]},
        **extra,
    }


def test_error_never_becomes_completed_and_empty_output_fails_closed() -> None:
    assert normalize_product_result(_raw()).status == "COMPLETED"
    assert normalize_product_result(_raw(stop_reason="error", output="")).status == "ERROR"
    assert normalize_product_result(_raw(stop_reason="error", output="claimed success")).status == "ERROR"
    assert normalize_product_result(_raw(output="")).status == "FAIL_CLOSED"
    assert normalize_product_result({"status": "COMPLETED", "output": "ok"}).status == "FAIL_CLOSED"
    assert normalize_product_result(_raw(bridgeExitCode=2)).status == "ERROR"
    assert normalize_product_result(_raw(parentLlmProvider="deepseek")).status == "FAIL_CLOSED"


def test_successful_lifecycle_and_expected_disposal_sigterm_are_distinguished() -> None:
    result = normalize_product_result(_raw(processes=[{"signal": "SIGTERM"}]))
    assert result.status == "COMPLETED"
    assert result.normal_disposal is True
    failed = normalize_product_result(_raw(stop_reason="error", output="", processes=[{"signal": "SIGTERM"}]))
    assert failed.status == "ERROR"


def test_role_parsers_are_exact_and_fail_closed() -> None:
    review = json.dumps({
        "status": "REPAIR_REQUIRED",
        "highest_severity": "HIGH",
        "findings": [{"id": "Q-001", "severity": "HIGH", "path": "repair_target.txt"}],
    })
    assert parse_reviewer_output(review)["status"] == "REPAIR_REQUIRED"
    assert parse_reviewer_output(json.dumps({"status": "PASS", "highest_severity": "NONE", "findings": []}))["status"] == "PASS"
    verifier = json.dumps({"status": "PASS", "checks": {"fixture.txt": "AFTER"}, "diagnostics": []})
    assert parse_verifier_output(verifier)["status"] == "PASS"
    for malformed in (
        "",
        "not json",
        json.dumps({"status": "PASS", "highest_severity": "HIGH", "findings": []}),
        json.dumps({"status": "PASS", "highest_severity": "NONE", "findings": [{"id": "Q", "severity": "HIGH", "path": "x"}]}),
        json.dumps({"status": "PASS", "checks": {}, "diagnostics": ["product ERROR"]}),
    ):
        with pytest.raises(QualificationError):
            (parse_reviewer_output(malformed) if "highest_severity" in malformed or malformed in {"", "not json"} else parse_verifier_output(malformed))


def test_workspace_digest_and_unauthorized_changes(tmp_path: Path) -> None:
    (tmp_path / "fixture.txt").write_bytes(b"BEFORE")
    before = workspace_snapshot(tmp_path)
    (tmp_path / "fixture.txt").write_bytes(b"AFTER")
    after = workspace_snapshot(tmp_path)
    assert changed_paths(before, after) == ["fixture.txt"]
    assert snapshot_digest(before) != snapshot_digest(after)
    assert enforce_allowed_changes(before, after, ["fixture.txt"]) == ["fixture.txt"]
    (tmp_path / "unauthorized.txt").write_bytes(b"NO")
    with pytest.raises(QualificationError):
        enforce_allowed_changes(before, workspace_snapshot(tmp_path), ["fixture.txt"])


def test_test_stage_executes_argv_and_detects_failure(tmp_path: Path) -> None:
    positive = run_test_command([sys.executable, "-c", "raise SystemExit(0)"], tmp_path)
    negative = run_test_command([sys.executable, "-c", "raise SystemExit(3)"], tmp_path)
    assert positive.passed is True
    assert positive.returncode == 0
    assert positive.termination == "EXITED"
    assert negative.passed is False
    assert negative.returncode == 3
    with pytest.raises(QualificationError):
        run_test_command("python -c 'exit(0)'", tmp_path)  # type: ignore[arg-type]


def test_scope_cwd_profile_and_parity_are_enforced(tmp_path: Path) -> None:
    invocation = ProductInvocation("DSH", "CODEX_PROFILE_A", "A", tmp_path, tmp_path, "prompt", "never", "workspace-write")
    invocation.validate()
    native = ProductInvocation("NATIVE", "CODEX_PROFILE_A", "A", tmp_path, tmp_path, "prompt", "never", "workspace-write")
    assert compare_parity(invocation.observable(), native.observable()) == []
    with pytest.raises(QualificationError):
        ProductInvocation("DSH", "CODEX_PROFILE_B", "A", tmp_path, tmp_path, "prompt", "never", "workspace-write").validate()
    with pytest.raises(QualificationError):
        ProductInvocation("DSH", "CODEX_PROFILE_A", "A", tmp_path / "child", tmp_path, "prompt", "never", "workspace-write").validate()


def test_api_key_gate_and_dsh_parent_llm_gate() -> None:
    env, presence = sanitize_environment({"OPENAI_API_KEY": "secret", "PATH": "/bin"})
    assert presence["OPENAI_API_KEY"] is True
    assert "OPENAI_API_KEY" not in env
    with pytest.raises(QualificationError):
        ProductInvocation("DSH", "CODEX_PROFILE_A", "A", Path("/tmp"), Path("/tmp"), "x", "never", "workspace-write", parent_llm_provider="codex").validate()


def test_v1_consumed_state_cannot_be_rearmed() -> None:
    record = {
        "execution": {"episode_consumed": True, "authorized_episode_count": 1},
        "no_rerun_invariant": {"second_episode_under_v1_allowed": False, "rescue_rerun_allowed": False},
    }
    assert_v1_consumed(record)
    record["no_rerun_invariant"]["rescue_rerun_allowed"] = True
    with pytest.raises(QualificationError):
        assert_v1_consumed(record)
