#!/usr/bin/env python3
"""Frozen lab-only QntyLab native Codex app-server bridge (diagnostic route D3).

This file exists so the native bridge under test has committed, hashable bytes.
The predecessor qualification (PR #134) executed an ephemeral helper whose bytes
were never frozen; those bytes are unrecoverable, so this bridge is the frozen
native-bridge identity for this diagnostic and is not a byte-recovery of it.

It is deliberately thin.  It reuses the diagnostic's own app-server transport so
that the only variable changed between route D2 and route D3 is the QntyLab
native bridge wrapper itself: external subprocess execution, environment
sanitation, last-JSON-line receipt transport, and lifecycle normalization.

It prints exactly one JSON object on its final stdout line and never prints
credentials or assistant prose.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from qntylab.subscription_backed_codex_app_server_write_path_diagnostic_v0 import (  # noqa: E402
    CODEX_BINARY,
    CODEX_HOME,
    DEFAULT_TURN_TIMEOUT_SECONDS,
    WRITE_PROMPT,
    TraceRecorder,
    run_app_server_route,
)

BRIDGE_ROUTE = "D3_QNTY_NATIVE_BRIDGE"

_STOP_REASON = {
    "completed": "completed",
    "failed": "error",
    "interrupted": "aborted",
}


def _receipt(route_receipt: dict, recorder: TraceRecorder) -> dict:
    """Shape the route observation into the #134 native-bridge receipt contract."""

    turn_status = (route_receipt.get("turn") or {}).get("status")
    stop_reason = _STOP_REASON.get(turn_status, "timeout" if route_receipt["timeout_policy"]["timed_out"] else "missing")
    messages = route_receipt.get("agent_messages") or []
    output = f"agentMessageSha256:{messages[-1]['text_sha256']}" if messages else "NO_AGENT_MESSAGE"
    process = route_receipt.get("process") or {}
    return {
        "status": "COMPLETED" if turn_status == "completed" else "FAIL_CLOSED",
        "output": output,
        "lifecycle": {"ends": [{"stopReason": stop_reason}]},
        "processes": [{"signal": process.get("termination")}],
        "parentLlmProvider": "NONE",
        "parentLlmRequestCount": 0,
        "route": BRIDGE_ROUTE,
        "routeReceipt": route_receipt,
        "traceEvents": [event.as_dict() for event in recorder.events],
    }


def main() -> int:
    cwd = os.environ.get("QNTYLAB_PRODUCT_CWD")
    scope = os.environ.get("QNTYLAB_WORKSPACE_SCOPE")
    profile = os.environ.get("QNTYLAB_PROFILE") or CODEX_HOME
    if not cwd or not scope or Path(cwd).resolve() != Path(scope).resolve():
        print(json.dumps({"status": "FAIL_CLOSED", "output": "",
                          "error": "bridge cwd/scope binding is missing or divergent"}))
        return 2

    recorder = TraceRecorder(route=BRIDGE_ROUTE)
    try:
        route_receipt = run_app_server_route(
            route=BRIDGE_ROUTE,
            workspace=Path(cwd),
            prompt=WRITE_PROMPT,
            recorder=recorder,
            codex_binary=CODEX_BINARY,
            codex_home=profile,
            turn_timeout_seconds=DEFAULT_TURN_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 - the bridge must always emit a receipt
        print(json.dumps({
            "status": "FAIL_CLOSED", "output": "",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback_tail": traceback.format_exc().splitlines()[-1],
            "traceEvents": [event.as_dict() for event in recorder.events],
        }))
        return 1

    print(json.dumps(_receipt(route_receipt, recorder), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
