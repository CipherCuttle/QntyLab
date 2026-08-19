"""Deterministic precheck for PINNED_DSH_CODEX_WRITE_PATH_MATERIALIZATION_V0.

Nothing here makes a live product call.  The single live D4 attempt is made
only by the frozen runner, after this suite passes and after the pre-live
freeze.  A simulated PASS is deliberately unreachable: the identity gate
rejects any DSH root that is not the exact pinned commit/tree/tag.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from qntylab.pinned_dsh_codex_write_path_materialization_v0 import (
    ALLOWED_VERDICTS,
    CODEX_HOME,
    D4_DRIVER_BLOB,
    D4_DRIVER_RELPATH,
    D4_DRIVER_SHA256,
    D4_FAILURE_MECHANISMS,
    D4_RESULTS,
    D4_TURN_TIMEOUT_SECONDS,
    DSH_COMMIT,
    DSH_PACKAGE_MANAGER,
    DSH_TAG,
    DSH_TREE,
    LOCKFILE_SHA256,
    MATERIALIZATION_FAILURE_CLASSES,
    MAX_LIVE_ATTEMPTS,
    PR134_HEAD,
    PR135_HEAD,
    PREDECESSOR_MASTER_SHA,
    REQUIRED_ARTIFACT_SHA256,
    REQUIRED_RUNTIME_ARTIFACTS,
    api_key_gate,
    classify_d4,
    classify_materialization,
    codex_child_spawned,
    downstream_authority,
    driver_identity,
    dsh_identity,
    identity_gate,
    node_version_satisfies,
    phase_verdict,
    pnpm_version_satisfies,
    receipt_integrity,
    runtime_artifact_drift,
    runtime_artifact_hashes,
    runtime_artifacts_present,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FAKE_DSH_ROOT = REPO_ROOT / "tests" / "fixtures" / "fake_pinned_dsh_root_v0"
FROZEN_DRIVER = REPO_ROOT / D4_DRIVER_RELPATH
RUNNER = (
    REPO_ROOT
    / "experiments/research/qnty_agent_orchestration_control_contract_v0"
    / "pinned_dsh_codex_write_path_materialization_v0"
    / "run_pinned_dsh_d4_v0.py"
)

_MATERIALIZED = {
    "materialized": True,
    "failure_class": None,
    "runtime_artifacts_present": True,
}
_GATE_OK = {"passed": True, "reasons": []}


def _receipt(**overrides):
    base = {
        "status": "COMPLETED",
        "route": "D4_PINNED_DSH_CODEX_PROVIDER",
        "lifecycle": {"ends": [{"stopReason": "completed"}]},
        "timedOut": False,
        "error": None,
        "parentLlmProvider": "NONE",
        "parentLlmRequestCount": 0,
        "bridgeExitCode": 0,
        "apiKeyPresence": {"OPENAI_API_KEY": False},
        "observed": {"providerName": "codex"},
    }
    base.update(overrides)
    return base


_CODEX_CHILD = [{"argv": ["/home/swirky/.local/bin/codex", "app-server", "--stdio"], "depth": 1}]


# ---------------------------------------------------------------------------
# 1. All four required DSH runtime modules import successfully.
# ---------------------------------------------------------------------------


def _pinned_root() -> Path | None:
    root = Path(os.environ.get("QNTYLAB_PINNED_DSH_ROOT", "/home/swirky/DevHub/dsh-pinned-materialization-v0"))
    return root if (root / ".git").exists() else None


@pytest.mark.skipif(_pinned_root() is None, reason="pinned DSH checkout is not materialized here")
def test_pinned_dsh_runtime_modules_import() -> None:
    root = _pinned_root()
    assert root is not None
    hashes = runtime_artifact_hashes(root)
    assert runtime_artifacts_present(hashes), hashes
    probe = "\n".join(
        [
            f"await import('{root}/vendor/cordis/lib/index.js')",
            f"await import('{root}/packages/subagent/subagent/lib/index.js')",
            f"await import('{root}/packages/subprocess/subprocess-local/lib/index.js')",
            f"await import('{root}/packages/subagent/subagent-codex/lib/index.js')",
            "console.log('IMPORT_OK')",
        ]
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", probe], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
    assert "IMPORT_OK" in completed.stdout


@pytest.mark.skipif(_pinned_root() is None, reason="pinned DSH checkout is not materialized here")
def test_pinned_dsh_identity_is_exact_and_unmutated() -> None:
    identity = dsh_identity(_pinned_root())
    assert identity["commit"] == DSH_COMMIT
    assert identity["tree"] == DSH_TREE
    assert identity["tag"] == DSH_TAG
    assert identity["tracked_modified_count"] == 0
    assert identity["matches"] is True


# ---------------------------------------------------------------------------
# 2. The frozen D4 driver reaches ctx.subagents.start() under a no-live seam.
# ---------------------------------------------------------------------------


def test_frozen_driver_reaches_subagent_start_without_any_live_call(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "fixture.txt").write_bytes(b"BEFORE\n")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("write it\n", encoding="utf-8")
    trace = tmp_path / "trace.jsonl"

    env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ.get("HOME", str(tmp_path)),
        "QNTYLAB_PRODUCT_CWD": str(workspace),
        "QNTYLAB_WORKSPACE_SCOPE": str(workspace),
        "QNTYLAB_PROFILE": CODEX_HOME,
        "QNTYLAB_CODEX_BINDIR": "/home/swirky/.local/bin",
        "QNTYLAB_PROMPT_FILE": str(prompt),
        "QNTYLAB_DSH_ROOT": str(FAKE_DSH_ROOT),
        "QNTYLAB_FAKE_DSH_TRACE": str(trace),
        "QNTYLAB_FAKE_DSH_MODE": "reach_start_only",
    }
    completed = subprocess.run(
        ["node", str(FROZEN_DRIVER)], env=env, capture_output=True, text=True, check=False
    )
    events = [json.loads(line) for line in trace.read_text().splitlines() if line.strip()]
    start = [event for event in events if event["event"] == "subagents.start"]
    assert start, completed.stderr
    assert start[0]["provider"] == "codex"
    assert start[0]["registrations"] == ["SubagentRuntime", "LocalSubprocessRuntime", "codex"]
    assert start[0]["parentCwd"] == str(workspace)
    assert start[0]["hasSignal"] is True
    # The seam performs no product call and leaves the workspace untouched.
    assert (workspace / "fixture.txt").read_bytes() == b"BEFORE\n"


# ---------------------------------------------------------------------------
# 3. Missing generated build output still fails closed.
# ---------------------------------------------------------------------------


def test_missing_build_output_fails_closed_in_driver(tmp_path: Path) -> None:
    unbuilt = tmp_path / "unbuilt-dsh"
    unbuilt.mkdir()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "fixture.txt").write_bytes(b"BEFORE\n")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("write it\n", encoding="utf-8")

    completed = subprocess.run(
        ["node", str(FROZEN_DRIVER)],
        env={
            "PATH": os.environ["PATH"],
            "HOME": os.environ.get("HOME", str(tmp_path)),
            "QNTYLAB_PRODUCT_CWD": str(workspace),
            "QNTYLAB_WORKSPACE_SCOPE": str(workspace),
            "QNTYLAB_PROFILE": CODEX_HOME,
            "QNTYLAB_CODEX_BINDIR": "/home/swirky/.local/bin",
            "QNTYLAB_PROMPT_FILE": str(prompt),
            "QNTYLAB_DSH_ROOT": str(unbuilt),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["status"] == "FAIL_CLOSED"
    assert payload["inconclusiveInfra"] == "PINNED_DSH_BUILD_OUTPUT_UNAVAILABLE"
    assert (workspace / "fixture.txt").read_bytes() == b"BEFORE\n"


def test_missing_runtime_artifact_classifies_as_artifact_missing() -> None:
    hashes = {path: "a" * 64 for path in REQUIRED_RUNTIME_ARTIFACTS}
    hashes[REQUIRED_RUNTIME_ARTIFACTS[-1]] = None
    result = classify_materialization(
        {"matches": True, "tracked_modified_count": 0},
        hashes,
        node_version="v22.22.0",
        pnpm_version="11.7.0",
        install_ok=True,
        build_ok=True,
        lockfile_unchanged=True,
    )
    assert result["materialized"] is False
    assert result["failure_class"] == "PINNED_DSH_RUNTIME_ARTIFACT_MISSING"


def test_build_failure_is_not_misclassified_as_a_dsh_product_failure() -> None:
    hashes = {path: None for path in REQUIRED_RUNTIME_ARTIFACTS}
    materialization = classify_materialization(
        {"matches": True, "tracked_modified_count": 0},
        hashes,
        node_version="v22.22.0",
        pnpm_version="11.7.0",
        install_ok=True,
        build_ok=False,
        lockfile_unchanged=True,
    )
    assert materialization["failure_class"] == "PINNED_DSH_BUILD_FAILURE"
    classification = classify_d4(
        materialization=materialization,
        identity=_GATE_OK,
        receipt=None,
        descendants=[],
        fixture_before_class="BEFORE",
        fixture_after_class="BEFORE",
        changed=[],
    )
    assert classification["d4"] == "INCONCLUSIVE_INFRA"
    assert classification["target_mechanism_exercised"] is False
    assert classification["failure_mechanism"] is None
    assert phase_verdict(classification) == "PINNED_DSH_MATERIALIZATION_BLOCKED"


def test_tracked_source_mutation_is_reported_before_build_failure() -> None:
    result = classify_materialization(
        {"matches": False, "tracked_modified_count": 3},
        {path: None for path in REQUIRED_RUNTIME_ARTIFACTS},
        node_version="v22.22.0",
        pnpm_version="11.7.0",
        install_ok=True,
        build_ok=False,
        lockfile_unchanged=True,
    )
    assert result["failure_class"] == "PINNED_DSH_SOURCE_MUTATION_REQUIRED"


def test_lockfile_update_is_a_dependency_install_failure() -> None:
    result = classify_materialization(
        {"matches": True, "tracked_modified_count": 0},
        {path: "b" * 64 for path in REQUIRED_RUNTIME_ARTIFACTS},
        node_version="v22.22.0",
        pnpm_version="11.7.0",
        install_ok=True,
        build_ok=True,
        lockfile_unchanged=False,
    )
    assert result["failure_class"] == "PINNED_DSH_DEPENDENCY_INSTALL_FAILURE"


@pytest.mark.parametrize(
    ("node_version", "pnpm_version", "expected"),
    [
        ("v20.11.0", "11.7.0", "PINNED_DSH_NODE_VERSION_MISMATCH"),
        ("v22.18.0", "11.7.0", "PINNED_DSH_NODE_VERSION_MISMATCH"),
        ("v22.22.0", "11.22.0", "PINNED_DSH_PACKAGE_MANAGER_MISMATCH"),
        ("v22.22.0", "10.0.0", "PINNED_DSH_PACKAGE_MANAGER_MISMATCH"),
    ],
)
def test_wrong_toolchain_fails_closed(node_version, pnpm_version, expected) -> None:
    result = classify_materialization(
        {"matches": True, "tracked_modified_count": 0},
        {path: "c" * 64 for path in REQUIRED_RUNTIME_ARTIFACTS},
        node_version=node_version,
        pnpm_version=pnpm_version,
        install_ok=True,
        build_ok=True,
        lockfile_unchanged=True,
    )
    assert result["failure_class"] == expected


def test_node_and_pnpm_range_semantics() -> None:
    assert node_version_satisfies("v22.19.0")
    assert node_version_satisfies("v24.0.0")
    assert node_version_satisfies("v25.3.1")
    assert not node_version_satisfies("v22.18.9")
    assert not node_version_satisfies("v23.9.0")
    assert not node_version_satisfies("not-a-version")
    assert pnpm_version_satisfies("11.7.0")
    assert pnpm_version_satisfies(" 11.7.0 ")
    assert not pnpm_version_satisfies("11.22.0")
    assert DSH_PACKAGE_MANAGER == "pnpm@11.7.0"


# ---------------------------------------------------------------------------
# 4-6. Wrong DSH identity, wrong Codex identity, and API keys all fail closed.
# ---------------------------------------------------------------------------


def test_wrong_dsh_identity_fails_closed() -> None:
    gate = identity_gate(
        dsh={"matches": False},
        driver={"matches": True},
        codex={"matches": True, "codex_home_present": True},
        keys={"passed": True},
    )
    assert gate["passed"] is False
    assert gate["reasons"] == ["DSH_IDENTITY_DRIFT"]
    classification = classify_d4(
        materialization=_MATERIALIZED,
        identity=gate,
        receipt=_receipt(),
        descendants=_CODEX_CHILD,
        fixture_before_class="BEFORE",
        fixture_after_class="AFTER",
        changed=["fixture.txt"],
    )
    assert classification["d4"] == "INCONCLUSIVE_INFRA"
    assert classification["target_mechanism_exercised"] is False
    assert phase_verdict(classification) == "BLOCKED_BY_IDENTITY_DRIFT"


def test_unbuilt_dsh_root_never_matches_pinned_identity(tmp_path: Path) -> None:
    assert dsh_identity(tmp_path / "absent")["matches"] is False
    assert dsh_identity(FAKE_DSH_ROOT)["matches"] is False


def test_wrong_codex_identity_fails_closed() -> None:
    gate = identity_gate(
        dsh={"matches": True},
        driver={"matches": True},
        codex={"matches": False, "codex_home_present": True},
        keys={"passed": True},
    )
    assert gate["reasons"] == ["CODEX_IDENTITY_DRIFT"]
    assert phase_verdict(
        classify_d4(
            materialization=_MATERIALIZED,
            identity=gate,
            receipt=_receipt(),
            descendants=_CODEX_CHILD,
            fixture_before_class="BEFORE",
            fixture_after_class="AFTER",
            changed=["fixture.txt"],
        )
    ) == "BLOCKED_BY_IDENTITY_DRIFT"


def test_missing_codex_home_fails_closed() -> None:
    gate = identity_gate(
        dsh={"matches": True},
        driver={"matches": True},
        codex={"matches": True, "codex_home_present": False},
        keys={"passed": True},
    )
    assert gate["reasons"] == ["CODEX_HOME_ABSENT"]


def test_api_key_presence_fails_closed_without_reading_values() -> None:
    gate = api_key_gate({"OPENAI_API_KEY": "sk-should-never-be-read"})
    assert gate["passed"] is False
    assert gate["presence"]["OPENAI_API_KEY"] is True
    assert "sk-should-never-be-read" not in json.dumps(gate)
    combined = identity_gate(
        dsh={"matches": True},
        driver={"matches": True},
        codex={"matches": True, "codex_home_present": True},
        keys=gate,
    )
    assert combined["reasons"] == ["PAY_PER_TOKEN_CREDENTIAL_PRESENT"]
    assert phase_verdict(
        classify_d4(
            materialization=_MATERIALIZED,
            identity=combined,
            receipt=_receipt(),
            descendants=_CODEX_CHILD,
            fixture_before_class="BEFORE",
            fixture_after_class="AFTER",
            changed=["fixture.txt"],
        )
    ) == "BLOCKED_BY_IDENTITY_DRIFT"


def test_api_key_gate_passes_when_absent() -> None:
    assert api_key_gate({})["passed"] is True


def test_frozen_driver_bytes_match_pr135() -> None:
    identity = driver_identity(FROZEN_DRIVER)
    assert identity["sha256"] == D4_DRIVER_SHA256
    assert identity["matches"] is True
    blob = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "hash-object", str(FROZEN_DRIVER)],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    assert blob == D4_DRIVER_BLOB
    drifted = driver_identity(FAKE_DSH_ROOT / "_seam.js")
    assert drifted["matches"] is False
    assert identity_gate(
        dsh={"matches": True},
        driver=drifted,
        codex={"matches": True, "codex_home_present": True},
        keys={"passed": True},
    )["reasons"] == ["D4_DRIVER_DRIFT"]


# ---------------------------------------------------------------------------
# 7. The before/after determination depends only on bytes.
# ---------------------------------------------------------------------------


def test_pass_requires_bytes_not_prose() -> None:
    prose = _receipt(output="agentOutputSha256:deadbeef", status="COMPLETED")
    no_write = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt=prose,
        descendants=_CODEX_CHILD,
        fixture_before_class="BEFORE",
        fixture_after_class="BEFORE",
        changed=[],
    )
    assert no_write["d4"] == "FAIL"
    assert no_write["failure_mechanism"] == "DSH_CODEX_COMPLETED_NO_WRITE"
    assert phase_verdict(no_write) == "PINNED_DSH_CODEX_WRITE_PATH_FAIL"


def test_file_effect_without_completed_lifecycle_is_not_a_pass() -> None:
    classification = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt=_receipt(lifecycle={"ends": [{"stopReason": "aborted"}]}, status="FAIL_CLOSED"),
        descendants=_CODEX_CHILD,
        fixture_before_class="BEFORE",
        fixture_after_class="AFTER",
        changed=["fixture.txt"],
    )
    assert classification["d4"] == "FAIL"
    assert classification["filesystem_effect_observed"] is True
    assert classification["failure_mechanism"] == "DSH_CODEX_TURN_ERROR"


def test_timeout_is_a_turn_timeout_not_a_pass() -> None:
    classification = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt=_receipt(timedOut=True, lifecycle={"ends": [{"stopReason": "timeout"}]}),
        descendants=_CODEX_CHILD,
        fixture_before_class="BEFORE",
        fixture_after_class="AFTER",
        changed=["fixture.txt"],
    )
    assert classification["d4"] == "FAIL"
    assert classification["failure_mechanism"] == "DSH_CODEX_TURN_TIMEOUT"
    assert classification["turn_terminal_observed"] is False


def test_unauthorized_write_is_not_a_pass() -> None:
    classification = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt=_receipt(),
        descendants=_CODEX_CHILD,
        fixture_before_class="BEFORE",
        fixture_after_class="AFTER",
        changed=["fixture.txt", "unrelated.txt"],
    )
    assert classification["d4"] == "FAIL"
    assert classification["unauthorized_writes"] == ["unrelated.txt"]
    assert classification["failure_mechanism"] == "DSH_CODEX_WRITE_ATTEMPT_FAILED"


def test_other_fixture_bytes_are_not_a_pass() -> None:
    classification = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt=_receipt(),
        descendants=_CODEX_CHILD,
        fixture_before_class="BEFORE",
        fixture_after_class="OTHER",
        changed=["fixture.txt"],
    )
    assert classification["d4"] == "FAIL"
    assert classification["fixture_target_match"] is False


def test_pass_requires_a_real_codex_child_process() -> None:
    without_child = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt=_receipt(),
        descendants=[{"argv": ["node", "something-else.mjs"], "depth": 1}],
        fixture_before_class="BEFORE",
        fixture_after_class="AFTER",
        changed=["fixture.txt"],
    )
    assert without_child["d4"] == "FAIL"
    assert without_child["codex_child_spawned"] is False
    assert not codex_child_spawned([{"argv": ["/usr/bin/codexish", "app-server"]}])
    assert not codex_child_spawned([{"argv": ["/home/swirky/.local/bin/codex", "exec"]}])
    assert codex_child_spawned(_CODEX_CHILD)


def test_full_positive_path_is_the_only_pass() -> None:
    classification = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt=_receipt(),
        descendants=_CODEX_CHILD,
        fixture_before_class="BEFORE",
        fixture_after_class="AFTER",
        changed=["fixture.txt"],
    )
    assert classification["d4"] == "PASS"
    assert classification["target_mechanism_exercised"] is True
    assert classification["codex_child_spawned"] is True
    assert classification["turn_terminal_observed"] is True
    assert classification["unauthorized_writes"] == []
    assert phase_verdict(classification) == "PINNED_DSH_CODEX_WRITE_PATH_PASS"


def test_startup_failure_when_no_child_and_no_terminal() -> None:
    classification = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt=_receipt(
            lifecycle={"ends": [{"stopReason": "missing"}]},
            error="spawn codex ENOENT",
            status="FAIL_CLOSED",
        ),
        descendants=[],
        fixture_before_class="BEFORE",
        fixture_after_class="BEFORE",
        changed=[],
    )
    assert classification["d4"] == "FAIL"
    assert classification["failure_mechanism"] == "DSH_CODEX_STARTUP_FAILURE"
    assert classification["codex_child_spawned"] is False


def test_protocol_failure_classification() -> None:
    classification = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt=_receipt(
            lifecycle={"ends": [{"stopReason": "error"}]},
            error="malformed jsonrpc frame from app-server",
            status="FAIL_CLOSED",
        ),
        descendants=_CODEX_CHILD,
        fixture_before_class="BEFORE",
        fixture_after_class="BEFORE",
        changed=[],
    )
    assert classification["failure_mechanism"] == "DSH_CODEX_PROTOCOL_FAILURE"


def test_absent_driver_receipt_is_inconclusive_not_fail() -> None:
    classification = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt=None,
        descendants=[],
        fixture_before_class="BEFORE",
        fixture_after_class="BEFORE",
        changed=[],
    )
    assert classification["d4"] == "INCONCLUSIVE_INFRA"
    assert classification["reason"] == "D4_DRIVER_PRODUCED_NO_RECEIPT"


def test_driver_reported_infra_failure_is_inconclusive() -> None:
    classification = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt=_receipt(inconclusiveInfra="PINNED_DSH_BUILD_OUTPUT_UNAVAILABLE"),
        descendants=[],
        fixture_before_class="BEFORE",
        fixture_after_class="BEFORE",
        changed=[],
    )
    assert classification["d4"] == "INCONCLUSIVE_INFRA"
    assert classification["target_mechanism_exercised"] is False
    assert phase_verdict(classification) == "PINNED_DSH_MATERIALIZATION_BLOCKED"


# ---------------------------------------------------------------------------
# 8. No retry loop exists.
# ---------------------------------------------------------------------------


def test_runner_invokes_the_live_driver_exactly_once_and_never_in_a_loop() -> None:
    """Structural, not textual: the one live call site must not sit in a loop."""

    tree = ast.parse(RUNNER.read_text())

    def _calls(node: ast.AST) -> list[ast.Call]:
        return [
            child
            for child in ast.walk(node)
            if isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "run_driver_observed"
        ]

    assert len(_calls(tree)) == 1, "the live driver must have exactly one call site"
    loops = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.For, ast.While, ast.AsyncFor, ast.comprehension))
    ]
    for loop in loops:
        assert not _calls(loop), "the live driver call site must not be inside a loop"
    assert MAX_LIVE_ATTEMPTS == 1


def test_frozen_driver_starts_one_subagent_and_contains_no_loop() -> None:
    text = FROZEN_DRIVER.read_text()
    start_at = text.index("ctx.subagents.start(")
    assert text.count("ctx.subagents.start(") == 1
    loops = [match for match in re.finditer(r"\b(for|while)\s*\(", text)]
    # The driver's only loop is the pay-per-token credential scan, and it
    # closes well before the single live start call.
    assert len(loops) == 1
    assert "OPENAI_API_KEY" in text[loops[0].start() : loops[0].start() + 200]
    assert loops[0].start() < start_at
    assert "setTimeout" in text  # the single bounded deadline, not a poll loop
    assert "setInterval" not in text


def test_runner_declares_exactly_one_attempt() -> None:
    text = RUNNER.read_text()
    assert '"attempts": 1' in text
    assert '"retries_used": 0' in text


# ---------------------------------------------------------------------------
# Boundary invariants: no V2, no V1 rerun, no D0-D3 rerun, no answer key.
# ---------------------------------------------------------------------------


def test_pass_authorizes_nothing_downstream() -> None:
    authority = downstream_authority({"d4": "PASS"})
    assert authority["v2_authorized"] is False
    assert authority["v2_created"] is False
    assert authority["stage_a_v1_rerun_authorized"] is False
    assert authority["merge_authorized"] is False
    assert authority["dsh_scientific_superiority_proven"] is False
    assert all(
        authority[key] == "NONE"
        for key in ("scientific_authority", "runtime_authority", "trading_authority", "capital_authority")
    )
    assert authority["eligibility"] == (
        "ELIGIBLE_FOR_SEPARATE_EXECUTION_PLUMBING_QUALIFICATION_CONSIDERATION"
    )


def test_non_pass_grants_no_eligibility() -> None:
    for result in ("FAIL", "INCONCLUSIVE_INFRA"):
        assert downstream_authority({"d4": result})["eligibility"] == "NONE"


def test_runner_never_reruns_d0_to_d3_or_stage_a_v1() -> None:
    text = RUNNER.read_text()
    for forbidden in (
        "run_app_server_route",
        "run_d0_host_control",
        "run_native_bridge_route",
        "NO_TOOL_PROMPT",
        "answer_key",
        "stage_a",
        "STAGE_A",
    ):
        assert forbidden not in text, forbidden


def test_predecessor_shas_are_pinned_constants() -> None:
    assert PREDECESSOR_MASTER_SHA == "b909bb7dddebb17247ac3101e045387f9ecd69e9"
    assert PR134_HEAD == "e24b540900ef9fcf48e24e8e53dbf2b18028f5d9"
    assert PR135_HEAD == "d104342a62bc3e315d3434d16013862de529ca70"


def test_closed_vocabularies_and_timeout_bound() -> None:
    assert D4_RESULTS == ("PASS", "FAIL", "INCONCLUSIVE_INFRA")
    # The seven contract classes, plus the artifact-drift class added in
    # response to the independent hostile review's CRITICAL finding.
    contract_classes = {
        "PINNED_DSH_DEPENDENCY_INSTALL_FAILURE",
        "PINNED_DSH_NODE_VERSION_MISMATCH",
        "PINNED_DSH_PACKAGE_MANAGER_MISMATCH",
        "PINNED_DSH_BUILD_FAILURE",
        "PINNED_DSH_RUNTIME_ARTIFACT_MISSING",
        "PINNED_DSH_SOURCE_MUTATION_REQUIRED",
        "PINNED_DSH_OTHER_MATERIALIZATION_FAILURE",
    }
    observed = set(MATERIALIZATION_FAILURE_CLASSES)
    assert contract_classes <= observed
    assert observed - contract_classes == {"PINNED_DSH_RUNTIME_ARTIFACT_DRIFT"}
    assert len(set(D4_FAILURE_MECHANISMS)) == 9
    assert len(set(ALLOWED_VERDICTS)) == 5
    assert D4_TURN_TIMEOUT_SECONDS == 300.0
    for result in D4_RESULTS:
        classification = {"d4": result, "reason": "x"}
        assert phase_verdict(classification) in ALLOWED_VERDICTS
    with pytest.raises(Exception):
        phase_verdict({"d4": "MAYBE"})


def test_python_module_is_importable_by_the_runner() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", "import qntylab.pinned_dsh_codex_write_path_materialization_v0"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


# ---------------------------------------------------------------------------
# Post-review hardening: artifact byte binding, receipt integrity, one episode.
# ---------------------------------------------------------------------------


def test_runtime_artifacts_are_bound_to_pinned_bytes_not_mere_existence() -> None:
    """`lib/` is gitignored, so a clean tracked tree cannot vouch for it."""

    good = dict(REQUIRED_ARTIFACT_SHA256)
    assert runtime_artifact_drift(good) == []
    tampered = dict(good)
    tampered["packages/subagent/subagent-codex/lib/index.js"] = "f" * 64
    assert runtime_artifact_drift(tampered) == ["packages/subagent/subagent-codex/lib/index.js"]
    result = classify_materialization(
        {"matches": True, "tracked_modified_count": 0},
        tampered,
        node_version="v22.22.0",
        pnpm_version="11.7.0",
        install_ok=True,
        build_ok=True,
        lockfile_unchanged=True,
    )
    assert result["materialized"] is False
    assert result["failure_class"] == "PINNED_DSH_RUNTIME_ARTIFACT_DRIFT"
    assert phase_verdict(
        classify_d4(
            materialization=result,
            identity=_GATE_OK,
            receipt=_receipt(),
            descendants=_CODEX_CHILD,
            fixture_before_class="BEFORE",
            fixture_after_class="AFTER",
            changed=["fixture.txt"],
        )
    ) == "PINNED_DSH_MATERIALIZATION_BLOCKED"


@pytest.mark.skipif(_pinned_root() is None, reason="pinned DSH checkout is not materialized here")
def test_materialized_checkout_matches_the_pinned_artifact_attestation() -> None:
    root = _pinned_root()
    assert runtime_artifact_drift(runtime_artifact_hashes(root)) == []
    from qntylab.subscription_backed_product_execution_plumbing_v0 import sha256_file

    assert sha256_file(root / "pnpm-lock.yaml") == LOCKFILE_SHA256


def test_absent_build_evidence_fails_closed() -> None:
    """Build evidence must be observed; its absence is not success."""

    import importlib.util

    spec = importlib.util.spec_from_file_location("_d4runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = module.MATERIALIZATION_RECORD
    try:
        module.MATERIALIZATION_RECORD = Path("/nonexistent/materialization_record.json")
        evidence = module.load_build_evidence()
    finally:
        module.MATERIALIZATION_RECORD = original
    assert evidence["install_ok"] is False
    assert evidence["build_ok"] is False
    assert evidence["present"] is False


@pytest.mark.parametrize(
    ("override", "expected_reason"),
    [
        ({"parentLlmProvider": "deepseek"}, "DSH_PARENT_LLM_ACTIVE"),
        ({"parentLlmRequestCount": 7}, "DSH_PARENT_LLM_REQUESTS_NONZERO"),
        ({"status": "FAIL_CLOSED"}, "RECEIPT_STATUS_NOT_COMPLETED"),
        ({"error": "dispose failed: boom"}, "RECEIPT_CARRIES_ERROR"),
        ({"bridgeExitCode": 1}, "DRIVER_EXIT_CODE_NONZERO"),
        ({"route": "SOMETHING_ELSE"}, "RECEIPT_IS_NOT_A_D4_ROUTE_RECEIPT"),
        ({"apiKeyPresence": {"OPENAI_API_KEY": True}}, "PAY_PER_TOKEN_CREDENTIAL_PRESENT_IN_DRIVER_ENV"),
    ],
)
def test_receipt_integrity_defects_block_a_pass(override, expected_reason) -> None:
    receipt = _receipt(**override)
    assert expected_reason in receipt_integrity(receipt)
    classification = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt=receipt,
        descendants=_CODEX_CHILD,
        fixture_before_class="BEFORE",
        fixture_after_class="AFTER",
        changed=["fixture.txt"],
    )
    assert classification["d4"] != "PASS"
    assert expected_reason in classification["receipt_integrity_reasons"]


def test_parent_llm_activity_is_a_configuration_divergence() -> None:
    classification = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt=_receipt(parentLlmProvider="deepseek", parentLlmRequestCount=7),
        descendants=_CODEX_CHILD,
        fixture_before_class="BEFORE",
        fixture_after_class="AFTER",
        changed=["fixture.txt"],
    )
    assert classification["d4"] == "FAIL"
    assert classification["failure_mechanism"] == "DSH_EFFECTIVE_CONFIG_DIVERGENCE"


def test_a_trailing_error_end_does_not_inherit_the_first_ends_success() -> None:
    classification = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt=_receipt(
            lifecycle={"ends": [{"stopReason": "completed"}, {"stopReason": "error"}]}
        ),
        descendants=_CODEX_CHILD,
        fixture_before_class="BEFORE",
        fixture_after_class="AFTER",
        changed=["fixture.txt"],
    )
    assert classification["d4"] == "FAIL"
    assert classification["all_stop_reasons"] == ["completed", "error"]


def test_harness_wall_clock_deadline_is_infrastructure_not_a_product_fail() -> None:
    classification = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt={
            "status": "FAIL_CLOSED",
            "error": "driver wall-clock deadline exceeded",
            "timedOut": True,
            "inconclusiveInfra": "D4_DRIVER_WALL_CLOCK_EXCEEDED",
            "bridgeExitCode": None,
        },
        descendants=_CODEX_CHILD,
        fixture_before_class="BEFORE",
        fixture_after_class="BEFORE",
        changed=[],
    )
    assert classification["d4"] == "INCONCLUSIVE_INFRA"
    assert classification["target_mechanism_exercised"] is False
    assert classification["reason"] == "D4_DRIVER_WALL_CLOCK_EXCEEDED"


def test_unparseable_receipt_is_infrastructure_not_a_product_fail() -> None:
    classification = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt={
            "status": "FAIL_CLOSED",
            "error": "driver returned no parseable receipt",
            "inconclusiveInfra": "D4_DRIVER_PRODUCED_NO_PARSEABLE_RECEIPT",
        },
        descendants=[],
        fixture_before_class="BEFORE",
        fixture_after_class="BEFORE",
        changed=[],
    )
    assert classification["d4"] == "INCONCLUSIVE_INFRA"
    assert classification["dsh_provider_entered"] is False
    assert classification["target_mechanism_exercised"] is False


def test_untrusted_workspace_with_no_write_is_a_configuration_divergence() -> None:
    """DSH's provider sends no approval/sandbox policy, unlike D2/D3."""

    classification = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt=_receipt(),
        descendants=_CODEX_CHILD,
        fixture_before_class="BEFORE",
        fixture_after_class="BEFORE",
        changed=[],
        profile={"workspace_trusted": False},
    )
    assert classification["d4"] == "FAIL"
    assert classification["failure_mechanism"] == "DSH_EFFECTIVE_CONFIG_DIVERGENCE"
    trusted = classify_d4(
        materialization=_MATERIALIZED,
        identity=_GATE_OK,
        receipt=_receipt(),
        descendants=_CODEX_CHILD,
        fixture_before_class="BEFORE",
        fixture_after_class="BEFORE",
        changed=[],
        profile={"workspace_trusted": True},
    )
    assert trusted["failure_mechanism"] == "DSH_CODEX_COMPLETED_NO_WRITE"


def test_second_live_attempt_is_refused_by_a_consumed_episode_guard(tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("_d4runner_guard", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    consumed = tmp_path / "d4_receipt.json"
    consumed.write_text("{}", encoding="utf-8")
    module.RECEIPT_PATH = consumed
    with pytest.raises(Exception) as excinfo:
        module.main()
    assert "already consumed" in str(excinfo.value)


def test_attempt_log_is_written_before_the_live_call() -> None:
    text = RUNNER.read_text()
    log_at = text.index("ATTEMPT_LOG_PATH.open(")
    call_at = text.index("receipt, descendants, samples = run_driver_observed(")
    assert log_at < call_at
    assert 'ATTEMPT_LOG_PATH.open("a"' in text


def test_profile_observation_records_effective_config_without_secret_values() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("_d4runner_profile", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observation = module.observe_profile(Path("/tmp/definitely-not-a-trusted-project"))
    assert observation["workspace_trusted"] is False
    assert observation["auth_mode"] == "chatgpt"
    assert observation["auth_api_key_slot_populated"] is False
    assert observation["subscription_backed"] is True
    assert observation["config_sha256_before"]
    assert "access_token" not in json.dumps(observation)
    blob = json.dumps(observation)
    assert "sk-" not in blob and "eyJ" not in blob


def test_trusted_project_parsing_is_exact() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("_d4runner_trust", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    text = '[projects."/a/b"]\ntrust_level = "trusted"\n[projects."/c"]\ntrust_level = "untrusted"\n'
    assert module._trusted_project_paths(text) == ["/a/b"]
