#!/usr/bin/env python3
"""Frozen lab-only runner for the bounded Codex app-server write-path ladder.

One attempt per stage.  No retries.  The ladder stops at the first PASS -> FAIL
divergence and does not exercise downstream transports once the causal boundary
is localized.  D0 and D1 are controls: a control failure stops the phase.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from qntylab.subscription_backed_codex_app_server_write_path_diagnostic_v0 import (  # noqa: E402
    CODEX_BINARY,
    CODEX_HOME,
    DEFAULT_TURN_TIMEOUT_SECONDS,
    NO_TOOL_PROMPT,
    WRITE_PROMPT,
    TraceRecorder,
    build_workspace,
    destroy_workspace,
    first_divergence,
    fixture_state,
    no_tool_control_passed,
    route_passed,
    run_app_server_route,
    run_d0_host_control,
)
from qntylab.subscription_backed_product_execution_plumbing_v0 import (  # noqa: E402
    ProductInvocation,
    normalize_product_result,
    run_product_bridge,
    sha256_bytes,
    sha256_file,
    utc_now,
    workspace_snapshot,
    changed_paths,
)

BRIDGE = _HERE / "qntylab_native_codex_app_server_bridge_v0.py"
DSH_DRIVER = _HERE / "pinned_dsh_codex_route_driver_v0.mjs"
DSH_ROOT = Path("/home/swirky/DevHub/dsh-stage-a-provisioning-v0")
DSH_COMMIT = "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
DSH_TREE = "3bc8f89fe494a4755c188be354add4e8b1e7b188"
DSH_TAG = "dsh-v0.1.0-rc.7"
CODEX_VERSION = "codex-cli 0.147.0"
API_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY")

BRIDGE_TIMEOUT_SECONDS = DEFAULT_TURN_TIMEOUT_SECONDS + 60.0


def product_identity() -> dict:
    codex_version = subprocess.run(
        [CODEX_BINARY, "--version"], capture_output=True, text=True, check=False
    ).stdout.strip()
    dsh = {
        key: subprocess.run(
            ["git", "-C", str(DSH_ROOT), *args], capture_output=True, text=True, check=False
        ).stdout.strip()
        for key, args in {
            "commit": ["rev-parse", "HEAD"],
            "tree": ["rev-parse", "HEAD^{tree}"],
            "tag": ["tag", "--points-at", "HEAD"],
        }.items()
    }
    return {
        "codex_binary": CODEX_BINARY,
        "codex_version_observed": codex_version,
        "codex_version_expected": CODEX_VERSION,
        "codex_version_matches": codex_version == CODEX_VERSION,
        "codex_home": CODEX_HOME,
        "dsh_observed": dsh,
        "dsh_matches": (
            dsh["commit"] == DSH_COMMIT and dsh["tree"] == DSH_TREE and dsh["tag"] == DSH_TAG
        ),
        "api_key_presence": {name: bool(os.environ.get(name)) for name in API_KEYS},
        "api_key_gate": not any(os.environ.get(name) for name in API_KEYS),
    }


def run_native_bridge_route(workspace: Path) -> dict:
    """D3: the frozen QntyLab native bridge wrapper around the same transport."""

    before = workspace_snapshot(workspace)
    fixture_before = fixture_state(workspace)
    invocation = ProductInvocation(
        route="NATIVE",
        product="CODEX_PROFILE_A",
        profile=CODEX_HOME,
        cwd=workspace,
        workspace_scope=workspace,
        prompt=WRITE_PROMPT,
        approval_mode="never",
        sandbox_mode="workspace-write",
    )
    started_at = utc_now()
    raw = run_product_bridge(
        [sys.executable, str(BRIDGE)], invocation, timeout_seconds=BRIDGE_TIMEOUT_SECONDS
    )
    ended_at = utc_now()
    normalized = normalize_product_result(raw, require_output=True)
    after = workspace_snapshot(workspace)
    fixture_after = fixture_state(workspace)
    effect = fixture_before["class"] == "BEFORE" and fixture_after["class"] == "AFTER"
    inner = raw.get("routeReceipt") if isinstance(raw.get("routeReceipt"), dict) else {}
    return {
        "route": "D3_QNTY_NATIVE_BRIDGE",
        "started_at": started_at,
        "ended_at": ended_at,
        "bridge_path": str(BRIDGE),
        "bridge_sha256": sha256_file(BRIDGE),
        "bridge_argv": [sys.executable, str(BRIDGE)],
        "bridge_exit_code": raw.get("bridgeExitCode"),
        "declared_invocation": invocation.observable(),
        "normalized": {
            "status": normalized.status,
            "stop_reason": normalized.stop_reason,
            "error": normalized.error,
            "normal_disposal": normalized.normal_disposal,
        },
        "inner_route_receipt": inner,
        "trace_events": raw.get("traceEvents") or [],
        "api_key_presence": raw.get("apiKeyPresence"),
        "filesystem": {
            "fixture_before": fixture_before,
            "fixture_after": fixture_after,
            "changed_paths": changed_paths(before, after),
            "effect_observed": effect,
        },
        "passed": effect and changed_paths(before, after) == ["fixture.txt"],
    }


def run_dsh_route(workspace: Path, prompt_file: Path) -> dict:
    """D4: the pinned DSH Codex provider, only reached if D0-D3 all pass."""

    before = workspace_snapshot(workspace)
    fixture_before = fixture_state(workspace)
    invocation = ProductInvocation(
        route="DSH",
        product="CODEX_PROFILE_A",
        profile=CODEX_HOME,
        cwd=workspace,
        workspace_scope=workspace,
        prompt=WRITE_PROMPT,
        approval_mode="never",
        sandbox_mode="workspace-write",
    )
    os.environ["QNTYLAB_CODEX_BINDIR"] = str(Path(CODEX_BINARY).parent)
    os.environ["QNTYLAB_PROMPT_FILE"] = str(prompt_file)
    os.environ["QNTYLAB_TURN_TIMEOUT_MS"] = str(int(DEFAULT_TURN_TIMEOUT_SECONDS * 1000))
    os.environ["QNTYLAB_DSH_ROOT"] = str(DSH_ROOT)
    started_at = utc_now()
    raw = run_product_bridge(
        ["node", str(DSH_DRIVER)], invocation, timeout_seconds=BRIDGE_TIMEOUT_SECONDS
    )
    ended_at = utc_now()
    after = workspace_snapshot(workspace)
    fixture_after = fixture_state(workspace)
    effect = fixture_before["class"] == "BEFORE" and fixture_after["class"] == "AFTER"
    return {
        "route": "D4_PINNED_DSH_CODEX_PROVIDER",
        "started_at": started_at,
        "ended_at": ended_at,
        "driver_path": str(DSH_DRIVER),
        "driver_sha256": sha256_file(DSH_DRIVER),
        "driver_argv": ["node", str(DSH_DRIVER)],
        "driver_exit_code": raw.get("bridgeExitCode"),
        "declared_invocation": invocation.observable(),
        "dsh_receipt": {k: v for k, v in raw.items() if k not in {"stdoutSha256", "stderrSha256"}},
        "inconclusive_infra": raw.get("inconclusiveInfra"),
        "parent_llm_provider": raw.get("parentLlmProvider"),
        "parent_llm_request_count": raw.get("parentLlmRequestCount"),
        "filesystem": {
            "fixture_before": fixture_before,
            "fixture_after": fixture_after,
            "changed_paths": changed_paths(before, after),
            "effect_observed": effect,
        },
        "passed": effect and changed_paths(before, after) == ["fixture.txt"],
    }


def main() -> int:
    identity = product_identity()
    gates: dict[str, str] = {}
    receipts: dict[str, dict] = {}
    trace_path = _HERE / "sanitized_rpc_trace.jsonl"
    stopped_reason = None

    if not identity["codex_version_matches"] or not identity["api_key_gate"]:
        return _finish(identity, {"D0": "INCONCLUSIVE_INFRA"}, receipts,
                       "PRODUCT_IDENTITY_OR_CREDENTIAL_GATE_FAILED", trace_path)

    synthetic_root = Path(tempfile.mkdtemp(prefix="qntylab-write-path-diagnostic-"))
    prompt_file = synthetic_root / "write_prompt.txt"
    prompt_file.write_text(WRITE_PROMPT, encoding="utf-8")

    try:
        # ---- D0 host filesystem control --------------------------------
        d0 = run_d0_host_control(synthetic_root / "d0")
        receipts["D0"] = d0
        gates["D0"] = "PASS" if d0["passed"] else "FAIL"
        if not d0["passed"]:
            return _finish(identity, gates, receipts, "D0_HOST_CONTROL_FAILED", trace_path)

        # ---- D1 raw app-server no-tool control -------------------------
        ws = build_workspace(synthetic_root / "d1")
        recorder = TraceRecorder(route="D1_RAW_APP_SERVER_BASELINE")
        d1 = run_app_server_route(
            route="D1_RAW_APP_SERVER_BASELINE", workspace=ws, prompt=NO_TOOL_PROMPT,
            recorder=recorder, turn_timeout_seconds=DEFAULT_TURN_TIMEOUT_SECONDS,
        )
        d1["control_passed"] = no_tool_control_passed(d1)
        recorder.write_jsonl(trace_path)
        receipts["D1"] = d1
        gates["D1"] = "PASS" if d1["control_passed"] else "FAIL"
        destroy_workspace(ws)
        if not d1["control_passed"]:
            return _finish(identity, gates, receipts, "D1_RAW_APP_SERVER_CONTROL_FAILED", trace_path)

        # ---- D2 raw app-server explicit workspace write ----------------
        ws = build_workspace(synthetic_root / "d2")
        recorder = TraceRecorder(route="D2_RAW_APP_SERVER_WRITE")
        d2 = run_app_server_route(
            route="D2_RAW_APP_SERVER_WRITE", workspace=ws, prompt=WRITE_PROMPT,
            recorder=recorder, turn_timeout_seconds=DEFAULT_TURN_TIMEOUT_SECONDS,
        )
        d2["route_passed"] = route_passed(d2)
        recorder.write_jsonl(trace_path)
        receipts["D2"] = d2
        gates["D2"] = "PASS" if d2["route_passed"] else "FAIL"
        destroy_workspace(ws)
        if not d2["route_passed"]:
            gates["D3"] = gates["D4"] = "NOT_RUN_DUE_TO_EARLIER_DIVERGENCE"
            return _finish(identity, gates, receipts, "STOPPED_AT_D2_DIVERGENCE", trace_path)

        # ---- D3 QntyLab native bridge -----------------------------------
        ws = build_workspace(synthetic_root / "d3")
        d3 = run_native_bridge_route(ws)
        _append_trace(trace_path, "D3_QNTY_NATIVE_BRIDGE", d3.pop("trace_events", []))
        receipts["D3"] = d3
        gates["D3"] = "PASS" if d3["passed"] else "FAIL"
        destroy_workspace(ws)
        if not d3["passed"]:
            gates["D4"] = "NOT_RUN_DUE_TO_EARLIER_DIVERGENCE"
            return _finish(identity, gates, receipts, "STOPPED_AT_D3_DIVERGENCE", trace_path)

        # ---- D4 pinned DSH Codex provider -------------------------------
        ws = build_workspace(synthetic_root / "d4")
        d4 = run_dsh_route(ws, prompt_file)
        receipts["D4"] = d4
        gates["D4"] = (
            "INCONCLUSIVE_INFRA" if d4.get("inconclusive_infra")
            else ("PASS" if d4["passed"] else "FAIL")
        )
        destroy_workspace(ws)
        stopped_reason = "LADDER_COMPLETED"
    finally:
        for leftover in sorted(synthetic_root.glob("d*")):
            destroy_workspace(leftover)

    return _finish(identity, gates, receipts, stopped_reason or "LADDER_COMPLETED", trace_path)


def _append_trace(trace_path: Path, route: str, events: list) -> None:
    with trace_path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps({"route": route, **event}, sort_keys=True) + "\n")


def _finish(identity: dict, gates: dict, receipts: dict, reason: str, trace_path: Path) -> int:
    divergence = first_divergence(gates)
    (_HERE / "route_receipts.json").write_text(
        json.dumps({
            "schema_version": "codex-app-server-write-path-route-receipts-v0",
            "generated_at": utc_now(),
            "product_identity": identity,
            "gates": gates,
            "receipts": receipts,
        }, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    summary = {
        "schema_version": "codex-app-server-write-path-result-v0",
        "gates": gates,
        "first_divergence": divergence,
        "stopped_reason": reason,
        "retries_used": 0,
        "trace_path": str(trace_path),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
