#!/usr/bin/env python3
"""Deterministic fake `codex app-server --stdio` used only by local tests.

It speaks the same newline-delimited JSON-RPC surface as the pinned 0.147
protocol so the diagnostic transport can be exercised without any product
call.  Scenario selection is argv-driven and fully deterministic.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

SCENARIO = sys.argv[1] if len(sys.argv) > 1 else "no_tool"
OBSERVED_PATH = os.environ.get("FAKE_APP_SERVER_OBSERVED")

THREAD_ID = "thread-fake-0001"
TURN_ID = "turn-fake-0001"


def send(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def notify(method: str, params: dict) -> None:
    send({"jsonrpc": "2.0", "method": method, "params": params})


def record_observed(name: str, params: dict) -> None:
    if not OBSERVED_PATH:
        return
    with open(OBSERVED_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"method": name, "params": params}, sort_keys=True) + "\n")


def turn_object(status: str, error: dict | None = None) -> dict:
    turn = {"id": TURN_ID, "items": [], "status": status}
    if error is not None:
        turn["error"] = error
    return turn


def emit_write(cwd: str) -> None:
    """Emit a fileChange item and perform the real byte change."""

    notify("item/started", {
        "threadId": THREAD_ID, "turnId": TURN_ID,
        "item": {"id": "item-1", "type": "fileChange", "status": "inProgress", "changes": {}},
    })
    Path(cwd, "fixture.txt").write_bytes(b"AFTER\n")
    notify("item/completed", {
        "threadId": THREAD_ID, "turnId": TURN_ID, "completedAtMs": 0,
        "item": {"id": "item-1", "type": "fileChange", "status": "completed",
                 "changes": {"fixture.txt": {"update": {}}}},
    })


def emit_agent_message(text: str) -> None:
    notify("item/completed", {
        "threadId": THREAD_ID, "turnId": TURN_ID, "completedAtMs": 0,
        "item": {"id": "item-msg", "type": "agentMessage", "text": text},
    })


def run_turn(params: dict) -> None:
    cwd = params.get("cwd") or os.getcwd()
    notify("turn/started", {"threadId": THREAD_ID, "turn": turn_object("inProgress")})

    if SCENARIO == "stall":
        while True:
            time.sleep(0.05)

    if SCENARIO == "approval_then_no_write":
        response = request_approval("item/fileChange/requestApproval", {
            "threadId": THREAD_ID, "turnId": TURN_ID, "itemId": "item-1",
            "startedAtMs": 0, "reason": "sandbox denied write",
        })
        record_observed("approval_response", response)
        emit_agent_message("declined")
        notify("turn/completed", {"threadId": THREAD_ID, "turn": turn_object("completed")})
        return

    if SCENARIO == "permission_then_no_write":
        response = request_approval("item/permissions/requestApproval", {
            "threadId": THREAD_ID, "turnId": TURN_ID, "itemId": "item-1",
            "startedAtMs": 0, "cwd": cwd, "permissions": {},
        })
        record_observed("permission_response", response)
        notify("turn/completed", {"threadId": THREAD_ID, "turn": turn_object("completed")})
        return

    if SCENARIO == "write":
        emit_write(cwd)
        emit_agent_message("done")
        notify("turn/completed", {"threadId": THREAD_ID, "turn": turn_object("completed")})
        return

    if SCENARIO == "wrong_bytes":
        Path(cwd, "fixture.txt").write_bytes(b"WRONG\n")
        notify("turn/completed", {"threadId": THREAD_ID, "turn": turn_object("completed")})
        return

    if SCENARIO == "extra_write":
        emit_write(cwd)
        Path(cwd, "extra.txt").write_bytes(b"UNAUTHORIZED\n")
        notify("turn/completed", {"threadId": THREAD_ID, "turn": turn_object("completed")})
        return

    if SCENARIO == "deleted_file":
        Path(cwd, "fixture.txt").unlink()
        notify("turn/completed", {"threadId": THREAD_ID, "turn": turn_object("completed")})
        return

    if SCENARIO == "wrong_thread":
        notify("turn/completed", {"threadId": "thread-wrong", "turn": turn_object("completed")})
        return

    if SCENARIO == "wrong_turn":
        wrong = turn_object("completed")
        wrong["id"] = "turn-wrong"
        notify("turn/completed", {"threadId": THREAD_ID, "turn": wrong})
        return

    if params.get("outputSchema") is not None:
        if SCENARIO == "verifier_mutation":
            Path(cwd, "verifier-write.txt").write_bytes(b"forbidden\n")
        if SCENARIO == "verifier_malformed":
            emit_agent_message("PASS")
        elif SCENARIO == "verifier_wrong_role":
            emit_agent_message(json.dumps({
                "role": "BUILDER", "verdict": "PASS",
                "builder_result_valid": True, "reviewer_result_consistent": True,
                "workspace_matches_contract": True, "unauthorized_writes": [], "reasons": [],
            }, separators=(",", ":")))
        elif SCENARIO == "verifier_fail":
            emit_agent_message(json.dumps({
                "role": "VERIFIER", "verdict": "FAIL",
                "builder_result_valid": False, "reviewer_result_consistent": True,
                "workspace_matches_contract": True, "unauthorized_writes": [],
                "reasons": ["builder evidence is invalid"],
            }, separators=(",", ":")))
        else:
            emit_agent_message(json.dumps({
                "role": "VERIFIER", "verdict": "PASS",
                "builder_result_valid": True, "reviewer_result_consistent": True,
                "workspace_matches_contract": True, "unauthorized_writes": [], "reasons": [],
            }, separators=(",", ":")))
        notify("turn/completed", {"threadId": THREAD_ID, "turn": turn_object("completed")})
        return

    if SCENARIO == "attempt_without_effect":
        notify("item/completed", {
            "threadId": THREAD_ID, "turnId": TURN_ID, "completedAtMs": 0,
            "item": {"id": "item-1", "type": "fileChange", "status": "failed", "changes": {}},
        })
        notify("turn/completed", {"threadId": THREAD_ID, "turn": turn_object("completed")})
        return

    if SCENARIO == "prose_lies_about_write":
        emit_agent_message("I have replaced fixture.txt with AFTER.")
        notify("turn/completed", {"threadId": THREAD_ID, "turn": turn_object("completed")})
        return

    if SCENARIO == "turn_failed":
        notify("error", {"threadId": THREAD_ID, "turnId": TURN_ID,
                         "error": {"message": "model stream broke"}, "willRetry": False})
        notify("turn/completed", {"threadId": THREAD_ID,
                                  "turn": turn_object("failed", {"message": "model stream broke"})})
        return

    if SCENARIO == "auth_failure":
        notify("turn/completed", {"threadId": THREAD_ID,
                                  "turn": turn_object("failed", {"message": "401 unauthorized: not logged in"})})
        return

    emit_agent_message("APP_SERVER_OK")
    notify("turn/completed", {"threadId": THREAD_ID, "turn": turn_object("completed")})


_pending_server_request = {"id": 9000}


def request_approval(method: str, params: dict) -> dict:
    """Issue a server->client request and block for the client's answer."""

    _pending_server_request["id"] += 1
    request_id = _pending_server_request["id"]
    send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
    while True:
        line = sys.stdin.readline()
        if not line:
            return {}
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("id") == request_id:
            return message.get("result") if isinstance(message.get("result"), dict) else {"error": True}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = message.get("method")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        request_id = message.get("id")

        if method is not None and request_id is not None:
            record_observed(method, params)

        if method == "initialize":
            if SCENARIO == "initialize_reject":
                send({"jsonrpc": "2.0", "id": request_id,
                      "error": {"code": -32602, "message": "initialize rejected"}})
                return
            send({"jsonrpc": "2.0", "id": request_id, "result": {
                "codexHome": os.environ.get("CODEX_HOME", "/unset"),
                "platformFamily": "unix", "platformOs": "linux",
                "userAgent": "fake-app-server/0",
            }})
        elif method == "initialized":
            continue
        elif method == "thread/start":
            if SCENARIO == "thread_start_reject":
                send({"jsonrpc": "2.0", "id": request_id,
                      "error": {"code": -32602, "message": "unknown field `sandbox`"}})
                return
            sandbox_mode = params.get("sandbox")
            effective_sandbox = (
                {"type": "workspaceWrite", "writableRoots": [params.get("cwd")], "networkAccess": False}
                if sandbox_mode == "workspace-write"
                else {"type": "readOnly", "networkAccess": False}
            )
            if SCENARIO == "effective_policy_downgrade":
                effective_sandbox = {"type": "readOnly", "networkAccess": False}
            send({"jsonrpc": "2.0", "id": request_id, "result": {
                "thread": {"id": THREAD_ID, "ephemeral": params.get("ephemeral") is True},
                "cwd": params.get("cwd"), "model": "fake-model", "modelProvider": "fake",
                "approvalPolicy": params.get("approvalPolicy", "on-request"),
                "approvalsReviewer": "user",
                "sandbox": effective_sandbox,
                "runtimeWorkspaceRoots": [params.get("cwd")],
            }})
            notify("thread/started", {"threadId": THREAD_ID, "thread": {"id": THREAD_ID}})
        elif method == "turn/start":
            send({"jsonrpc": "2.0", "id": request_id, "result": {"turn": turn_object("inProgress")}})
            run_turn(params)
            if SCENARIO != "stall":
                return
        elif request_id is not None:
            send({"jsonrpc": "2.0", "id": request_id,
                  "error": {"code": -32601, "message": "unknown method"}})


if __name__ == "__main__":
    main()
