from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from qntylab.dsh_stage_a_v1r2_native_compatibility import (
    CLAUDE_REQUIRED_ARGS,
    CompatibilityEvidence,
    NativeExecutableIdentity,
    NamespaceConflationError,
    SdkIdentity,
    future_identity_preflight,
    reject_version_namespace_comparison,
    run_codex_zero_model_probe,
    same_native_fingerprint,
    validate_claude_sdk_cli_contract,
)
from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
V1R1_EVIDENCE = ROOT / (
    "experiments/research/qnty_agent_orchestration_control_contract_v0/"
    "dsh_multi_agent_orchestration_stage_a_v1r1_execution_v0/execution_evidence.json"
)
V1R2_QUALIFICATION = ROOT / (
    "experiments/research/qnty_agent_orchestration_control_contract_v0/"
    "dsh_multi_agent_orchestration_stage_a_v1r2_native_child_compatibility_qualification_v0/qualification.json"
)
V1R2_EXECUTION_PROJECT_ID = "DSH_MULTI_AGENT_ORCHESTRATION_STAGE_A_V1R2_EXECUTION_V0"
FAKE_CODEX = ROOT / "tests/fixtures/fake_codex_app_server_v0.py"


def _native(label: str, digest: str = "digest") -> NativeExecutableIdentity:
    return NativeExecutableIdentity(label, f"/bin/{label}", f"/bin/{label}", label, label, digest)


def _evidence(kind: str, **overrides: object) -> CompatibilityEvidence:
    values: dict[str, object] = {
        "kind": kind,
        "compatibility": "PASS",
        "model_turns": 0,
        "api_requests": 0,
        "usage_events": 0,
        "task_execution": 0,
        "process_quiesced": True,
        "probe_details": {},
    }
    values.update(overrides)
    return CompatibilityEvidence(**values)  # type: ignore[arg-type]


def test_package_and_native_versions_are_separate_identity_fields() -> None:
    native = _native("codex-cli 0.148.0")
    sdk = SdkIdentity("@anthropic-ai/claude-agent-sdk", "0.3.220", "2.1.220")

    assert native.product_version != sdk.version
    assert native.fingerprint != sdk.version


def test_executable_fingerprint_records_symlink_and_target(tmp_path: Path) -> None:
    target = tmp_path / "native-child"
    target.write_text("#!/bin/sh\nprintf 'native-child 1.0\\n'\n", encoding="utf-8")
    target.chmod(0o755)
    link = tmp_path / "child-link"
    link.symlink_to(target)

    from qntylab.dsh_stage_a_v1r2_native_compatibility import capture_executable_identity

    identity = capture_executable_identity(str(link))

    assert identity.resolved_path == str(link)
    assert identity.realpath == str(target)
    assert identity.entrypoint_sha256 is not None
    assert identity.product_version == "native-child 1.0"


@pytest.mark.parametrize(
    ("left", "right"),
    [("native_codex_cli", "@openai/codex_package"), ("native_claude_cli", "@anthropic-ai/claude-agent-sdk")],
)
def test_original_cross_namespace_equality_rule_is_rejected(left: str, right: str) -> None:
    with pytest.raises(NamespaceConflationError, match="VERSION_NAMESPACE_CONFLATION"):
        reject_version_namespace_comparison(left, right)


def test_codex_zero_model_probe_never_sends_turn_or_usage_request() -> None:
    with tempfile.TemporaryDirectory() as directory:
        fake = Path(directory) / "codex"
        shutil.copy2(FAKE_CODEX, fake)
        fake.chmod(fake.stat().st_mode | 0o111)
        evidence = run_codex_zero_model_probe(str(fake))

    assert evidence.passed
    assert evidence.probe_details["protocol_initialized"] is True
    assert evidence.probe_details["thread_start_compatible"] is True
    assert evidence.model_turns == evidence.api_requests == evidence.usage_events == evidence.task_execution == 0


def test_claude_exact_sdk_argv_contract_is_parser_checked() -> None:
    help_text = subprocess.run(["claude", "--help"], check=True, text=True, capture_output=True).stdout
    evidence = validate_claude_sdk_cli_contract(help_text, CLAUDE_REQUIRED_ARGS)

    assert evidence.passed
    assert evidence.probe_details["fake_spawn_child_executed"] is False
    assert evidence.probe_details["missing_in_help"] == ["--permission-prompt-tool"]


def test_native_fingerprint_drift_blocks_future_preflight() -> None:
    codex = _native("codex", "codex-digest")
    claude = _native("claude", "claude-digest")
    sdk = SdkIdentity("@anthropic-ai/claude-agent-sdk", "0.3.220", "2.1.220")
    result = future_identity_preflight(
        codex_current=replace(codex, entrypoint_sha256="modified"),
        codex_qualified=codex,
        codex_evidence=_evidence("codex"),
        claude_current=claude,
        claude_qualified=claude,
        claude_sdk_current=sdk,
        claude_sdk_qualified=sdk,
        claude_evidence=_evidence("claude"),
    )

    assert result == {
        "status": "BLOCK",
        "reasons": ["CODEX_EXECUTABLE_FINGERPRINT_DRIFT"],
        "block_before_secret": True,
        "block_before_paid_parent_dispatch": True,
    }


def test_same_fingerprint_and_compatibility_receipts_pass_identity_preflight() -> None:
    codex = _native("codex", "codex-digest")
    claude = _native("claude", "claude-digest")
    sdk = SdkIdentity("@anthropic-ai/claude-agent-sdk", "0.3.220", "2.1.220")

    result = future_identity_preflight(
        codex_current=codex,
        codex_qualified=codex,
        codex_evidence=_evidence("codex"),
        claude_current=claude,
        claude_qualified=claude,
        claude_sdk_current=sdk,
        claude_sdk_qualified=sdk,
        claude_evidence=_evidence("claude"),
    )

    assert result["status"] == "PASS"


@pytest.mark.parametrize(
    "evidence",
    [
        None,
        _evidence("codex", model_turns=1),
        _evidence("claude", api_requests=1),
        _evidence("claude", compatibility="INCOMPLETE", uncertainty="transport not proven"),
    ],
)
def test_missing_or_nonzero_model_evidence_fails_closed(evidence: CompatibilityEvidence | None) -> None:
    native = _native("native")
    sdk = SdkIdentity("@anthropic-ai/claude-agent-sdk", "0.3.220", "2.1.220")
    result = future_identity_preflight(
        codex_current=native,
        codex_qualified=native,
        codex_evidence=evidence if evidence is None or evidence.kind == "codex" else _evidence("codex"),
        claude_current=native,
        claude_qualified=native,
        claude_sdk_current=sdk,
        claude_sdk_qualified=sdk,
        claude_evidence=evidence if evidence is None or evidence.kind == "claude" else _evidence("claude"),
    )

    assert result["status"] == "BLOCK"
    assert result["block_before_secret"] is True


def test_historical_v1r1_execution_remains_closed_blocked_and_unconsumed() -> None:
    evidence = json.loads(V1R1_EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["terminal_outcome"] == "STAGE_A_V1R1_BLOCK_CHILD_INFRA"
    assert evidence["live"]["episode_consumed"] is False
    assert evidence["live"]["parent_request_attempts"] == 0
    assert evidence["live"]["codex_actual_calls"] == 0
    assert evidence["live"]["claude_actual_calls"] == 0
    assert evidence["closure"]["project_state_after"] == "CLOSED_BLOCKED"


def test_v1r2_qualification_closes_and_only_its_execution_successor_is_active() -> None:
    qualification = json.loads(V1R2_QUALIFICATION.read_text(encoding="utf-8"))
    _, _, registry = project_context.load_context_sources(ROOT)
    project = next(record for record in registry["project"] if record["project_id"] == qualification["project_id"])

    assert qualification["qualification"] == "CLOSED_PASS"
    assert qualification["governance"]["implementation_authorized_after_closure"] is False
    assert qualification["governance"]["active_project_after_closure"] == "NONE"
    assert qualification["governance"]["model_requests"] == 0
    assert qualification["governance"]["paid_requests"] == 0
    assert qualification["governance"]["fixture_runs"] == 0
    assert project["state"] == "CLOSED_PASS"
    assert project["implementation_authorized"] is False
    active = [record for record in registry["project"] if record["state"] == "ACTIVE"]
    assert [record["project_id"] for record in active] == [V1R2_EXECUTION_PROJECT_ID]
    assert active[0]["implementation_authorized"] is True
