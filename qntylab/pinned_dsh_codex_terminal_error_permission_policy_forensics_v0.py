"""Bounded pinned-DSH permission-policy causal diagnostic.

The module owns only deterministic request-shape construction, fake-server
validation, evidence sanitization, and the single crash-safe canary controller.
It never runs historical A and has no retry path.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping


PHASE_ID = "PINNED_DSH_CODEX_TERMINAL_ERROR_PERMISSION_POLICY_FORENSICS_V0"
ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_terminal_error_permission_policy_forensics_v0"
AUTH_DIR = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_terminal_error_permission_policy_forensics_authorization_v0"
DSH_REPOSITORY = "deepseek-ai/deepseek-harness"
DSH_COMMIT = "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
DSH_TREE = "3bc8f89fe494a4755c188be354add4e8b1e7b188"
DSH_TAG = "dsh-v0.1.0-rc.7"
CODEX_BINARY = Path("/home/swirky/.local/bin/codex")
CODEX_VERSION = "codex-cli 0.147.0"
CODEX_HOME = Path("/home/swirky/.codex")
FROZEN_DSH_ROOT = Path("/home/swirky/DevHub/dsh-pinned-materialization-v0")
FROZEN_DSH_DRIVER = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/subscription_backed_codex_app_server_write_path_diagnostic_v0/pinned_dsh_codex_route_driver_v0.mjs"
WRAPPER = ARTIFACT_DIR / "codex_stdio_capture_wrapper.mjs"
PATCH = ARTIFACT_DIR / "intervention.patch"
PROMPT = (
    "In this disposable diagnostic repository, replace the exact contents of\n"
    "fixture.txt with:\n"
    "\n"
    "AFTER\n"
    "\n"
    "Do not modify any other file.\n"
    "Do not ask questions.\n"
    "Do not perform unrelated work.\n"
    "Stop after making that filesystem change.\n"
)
API_KEY_NAMES = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY")
GITHUB_CREDENTIAL_NAMES = ("GITHUB_TOKEN", "GH_TOKEN")
BEFORE = b"BEFORE\n"
AFTER = b"AFTER\n"


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def historical_requests(workspace: str = "<workspace>", thread_id: str = "<thread-id>") -> list[dict[str, Any]]:
    return [
        {
            "method": "initialize",
            "params": {
                "clientInfo": {"name": "deepseek-harness", "title": "DeepSeek Harness", "version": "0.0.1"},
                "capabilities": {"experimentalApi": False, "requestAttestation": False},
            },
        },
        {"method": "thread/start", "params": {"cwd": workspace, "ephemeral": True}},
        {
            "method": "turn/start",
            "params": {
                "threadId": thread_id,
                "input": [{"type": "text", "text": PROMPT, "text_elements": []}],
            },
        },
    ]


def intervention_b_requests(workspace: str = "<workspace>", thread_id: str = "<thread-id>") -> list[dict[str, Any]]:
    value = copy.deepcopy(historical_requests(workspace, thread_id))
    value[1]["params"]["approvalPolicy"] = "never"
    return value


def _delta(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    absent = "<ABSENT>"
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        result: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after)):
            child = f"{path}.{key}" if path else str(key)
            result.extend(_delta(before.get(key, absent), after.get(key, absent), child))
        return result
    if isinstance(before, list) and isinstance(after, list):
        if before == after:
            return []
        return [{"path": path, "before": before, "after": after}]
    if before != after:
        return [{"path": path, "before": before, "after": after}]
    return []


def semantic_request_delta(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if [item["method"] for item in before] != [item["method"] for item in after]:
        return [{"method": "<METHOD_SEQUENCE>", "path": "methods", "before": [x["method"] for x in before], "after": [x["method"] for x in after]}]
    result: list[dict[str, Any]] = []
    for left, right in zip(before, after):
        for item in _delta(left["params"], right["params"], "params"):
            result.append({"method": left["method"], **item})
    return result


def expected_delta() -> list[dict[str, Any]]:
    return [{"method": "thread/start", "path": "params.approvalPolicy", "before": "<ABSENT>", "after": "never"}]


def fake_app_server_capture(requests: list[dict[str, Any]]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for index, request in enumerate(requests, start=1):
        method = request["method"]
        params = request["params"]
        events.append({"direction": "request", "sequence": index, "method": method, "params": params, "status": "accepted"})
        if method == "initialize":
            events.append({"direction": "response", "sequence": index, "method": method, "status": "PASS", "http_status": None})
        elif method == "thread/start":
            events.append({
                "direction": "response", "sequence": index, "method": method, "status": "PASS", "http_status": None,
                "effective": {
                    "cwd": params["cwd"],
                    "approvalPolicy": params.get("approvalPolicy", "on-request"),
                    "sandbox": None,
                    "runtimeWorkspaceRoots": [],
                    "writableRoots": [],
                },
            })
        elif method == "turn/start":
            events.append({"direction": "response", "sequence": index, "method": method, "status": "PASS", "turn_id": "<turn-id>", "http_status": None})
            events.append({"direction": "event", "method": "turn/completed", "status": "completed", "error": None})
        else:
            events.append({"direction": "response", "sequence": index, "method": method, "status": "FAIL", "error_category": "UNSUPPORTED_METHOD"})
    return {"schema_version": "fake-pinned-dsh-app-server-capture-v0", "events": events}


def request_diff_artifact() -> dict[str, Any]:
    before = historical_requests()
    after = intervention_b_requests()
    delta = semantic_request_delta(before, after)
    return {
        "schema_version": "pinned-dsh-permission-policy-request-diff-v0",
        "phase_id": PHASE_ID,
        "historical_shape": before,
        "intervention_b_shape": after,
        "request_delta": delta,
        "expected_request_delta": expected_delta(),
        "request_delta_pass": delta == expected_delta(),
        "request_delta_count": len(delta),
        "fake_historical_capture": fake_app_server_capture(before),
        "fake_intervention_b_capture": fake_app_server_capture(after),
        "prompt_sha256": sha256_bytes(PROMPT.encode()),
        "dsh_identity": {"repository": DSH_REPOSITORY, "commit": DSH_COMMIT, "tree": DSH_TREE, "tag": DSH_TAG},
        "codex_identity": {"version": CODEX_VERSION, "home": str(CODEX_HOME)},
        "environment_semantics": {"api_key_values_read": False, "model_changed": False, "identity_changed": False},
    }


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        text = value
        for name in API_KEY_NAMES + GITHUB_CREDENTIAL_NAMES:
            text = text.replace(name, f"<{name}>")
        for marker in ("Bearer ", "bearer "):
            while marker in text:
                start = text.find(marker) + len(marker)
                end = len(text)
                for separator in (" ", "\n", "\"", "'", ","):
                    found = text.find(separator, start)
                    if found >= 0:
                        end = min(end, found)
                text = text[:start] + "<REDACTED>" + text[end:]
        return text[:300]
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items() if str(key).lower() not in {"authorization", "cookie", "token", "api_key", "apikey"}}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def credential_presence(environ: Mapping[str, str] | None = None) -> dict[str, bool]:
    source = os.environ if environ is None else environ
    return {name: name in source for name in API_KEY_NAMES}


def profile_config_hash() -> str | None:
    path = CODEX_HOME / "config.toml"
    return sha256_file(path) if path.is_file() else None


def workspace_snapshot(workspace: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(workspace.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        result[str(path.relative_to(workspace))] = sha256_file(path)
    return result


def changed_paths(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def normalize_observed_requests(events: list[dict[str, Any]], workspace: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for event in events:
        if event.get("direction") != "request" or event.get("method") not in {"initialize", "thread/start", "turn/start"}:
            continue
        item = copy.deepcopy(event)
        params = item.get("params", {})
        if params.get("cwd") == str(workspace):
            params["cwd"] = "<workspace>"
        if params.get("threadId"):
            params["threadId"] = "<thread-id>"
        for block in params.get("input", []):
            if isinstance(block, Mapping) and block.get("text") == PROMPT:
                block["text"] = PROMPT
        item["params"] = params
        item.pop("id", None)
        item.pop("jsonrpc", None)
        item.pop("direction", None)
        item.pop("sequence", None)
        item.pop("status", None)
        result.append(item)
    return result


def classify_live(receipt: Mapping[str, Any]) -> str:
    if receipt.get("prelive_gate") != "PASS":
        return "PRELIVE_BLOCKED"
    if receipt.get("identity_gate") != "PASS" or receipt.get("credential_gate") != "PASS":
        return "INCONCLUSIVE_INFRA"
    if receipt.get("profile_a_config_mutated"):
        return "INCONCLUSIVE_INFRA"
    if receipt.get("timeout"):
        return "INCONCLUSIVE_INFRA"
    if receipt.get("fixture_before_class") == "BEFORE" and receipt.get("fixture_after_class") == "AFTER" and receipt.get("changed_paths") == ["fixture.txt"] and receipt.get("unauthorized_changed_paths") == [] and receipt.get("terminal_status") == "completed":
        return "INTERVENTION_PASS"
    if receipt.get("terminal_error_category") == "same_as_historical_stopReason_error" and receipt.get("changed_paths") == []:
        return "SAME_FAILURE"
    if receipt.get("turn_terminal_observed") and receipt.get("changed_paths") != ["fixture.txt"]:
        return "DIFFERENT_FAILURE"
    return "INCONCLUSIVE_INFRA"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_fake_diff() -> dict[str, Any]:
    artifact = request_diff_artifact()
    if not artifact["request_delta_pass"]:
        raise RuntimeError("PRELIVE_FAIL: request delta is not exactly one approvalPolicy field")
    write_json(ARTIFACT_DIR / "fake_app_server_request_diff.json", artifact)
    return artifact


def create_pre_live_freeze() -> dict[str, Any]:
    diff = json.loads((ARTIFACT_DIR / "fake_app_server_request_diff.json").read_text(encoding="utf-8"))
    if diff["request_delta"] != expected_delta():
        raise RuntimeError("PRELIVE_FAIL: fake request diff mismatch")
    import subprocess as _subprocess
    head = _subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    freeze = {
        "schema_version": "pinned-dsh-permission-policy-prelive-freeze-v0",
        "phase_id": PHASE_ID,
        "frozen_candidate_head": head,
        "frozen_at": "PRELIVE_FREEZE_TIME_RECORDED_AT_COMMIT",
        "request_delta": expected_delta(),
        "request_delta_digest": sha256_bytes(canonical(expected_delta()).encode()),
        "fake_diff_sha256": sha256_file(ARTIFACT_DIR / "fake_app_server_request_diff.json"),
        "implementation_source_sha256": sha256_file(Path(__file__)),
        "intervention_patch_sha256": sha256_file(PATCH),
        "frozen_dsh_driver_sha256": sha256_file(FROZEN_DSH_DRIVER),
        "dsh_identity": {"repository": DSH_REPOSITORY, "commit": DSH_COMMIT, "tree": DSH_TREE, "tag": DSH_TAG},
        "codex_identity": {"binary": str(CODEX_BINARY), "version": CODEX_VERSION, "binary_sha256": sha256_file(CODEX_BINARY), "home": str(CODEX_HOME)},
        "prompt_sha256": sha256_bytes(PROMPT.encode()),
        "live_attempts_authorized": 1,
        "live_attempts_consumed": 0,
        "prelive_gate": "PASS",
        "immutable_after_commit": True,
    }
    write_json(ARTIFACT_DIR / "prelive_freeze.json", freeze)
    return freeze


def _read_trace(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def run_live() -> dict[str, Any]:
    freeze_path = ARTIFACT_DIR / "prelive_freeze.json"
    marker = ARTIFACT_DIR / "live_canary_consumed.marker"
    if marker.exists():
        raise RuntimeError("PRELIVE_BLOCKED: live canary marker already exists")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    diff = json.loads((ARTIFACT_DIR / "fake_app_server_request_diff.json").read_text(encoding="utf-8"))
    if freeze["request_delta"] != expected_delta() or diff["request_delta"] != expected_delta():
        raise RuntimeError("PRELIVE_BLOCKED: request delta gate failed")
    if credential_presence():
        raise RuntimeError("PRELIVE_BLOCKED: pay-per-token credential present")
    if sha256_file(CODEX_BINARY) != freeze["codex_identity"]["binary_sha256"] or CODEX_VERSION != freeze["codex_identity"]["version"]:
        raise RuntimeError("PRELIVE_BLOCKED: Codex identity drift")
    if not FROZEN_DSH_ROOT.is_dir() or not FROZEN_DSH_DRIVER.is_file():
        raise RuntimeError("PRELIVE_BLOCKED: pinned DSH materialization unavailable")
    control = Path(tempfile.mkdtemp(prefix="qntylab-pinned-dsh-permission-control-"))
    workspace = Path(tempfile.mkdtemp(prefix="qntylab-pinned-dsh-permission-b-"))
    dsh_copy = Path(tempfile.mkdtemp(prefix="qntylab-pinned-dsh-permission-dsh-")) / "dsh"
    shutil.copytree(FROZEN_DSH_ROOT, dsh_copy, symlinks=True)
    patch_result = subprocess.run(["git", "-C", str(dsh_copy), "apply", str(PATCH)], capture_output=True, text=True, check=False)
    if patch_result.returncode != 0:
        raise RuntimeError("PRELIVE_BLOCKED: intervention patch did not apply")
    fixture = workspace / "fixture.txt"
    fixture.write_bytes(BEFORE)
    subprocess.run(["git", "-C", str(workspace), "init", "-q"], check=True)
    before = workspace_snapshot(workspace)
    config_before = profile_config_hash()
    trace = control / "rpc-trace.jsonl"
    prompt_file = control / "prompt.txt"
    prompt_file.write_text(PROMPT, encoding="utf-8")
    wrapper_dir = control / "bin"
    wrapper_dir.mkdir()
    shutil.copy2(WRAPPER, wrapper_dir / "codex")
    (wrapper_dir / "codex").chmod(0o755)
    marker.write_text("CONSUMED_BEFORE_PRODUCT_EXECUTION\n", encoding="utf-8")
    env = os.environ.copy()
    for name in API_KEY_NAMES + GITHUB_CREDENTIAL_NAMES:
        env.pop(name, None)
    env.update({
        "QNTYLAB_PRODUCT_CWD": str(workspace),
        "QNTYLAB_WORKSPACE_SCOPE": str(workspace),
        "QNTYLAB_PROFILE": str(CODEX_HOME),
        "QNTYLAB_CODEX_BINDIR": str(wrapper_dir),
        "QNTYLAB_PROMPT_FILE": str(prompt_file),
        "QNTYLAB_TURN_TIMEOUT_MS": "300000",
        "QNTYLAB_DSH_ROOT": str(dsh_copy),
        "QNTYLAB_REAL_CODEX_BINARY": str(CODEX_BINARY),
        "QNTYLAB_RPC_TRACE": str(trace),
    })
    started = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    try:
        completed = subprocess.run(["node", str(FROZEN_DSH_DRIVER)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=360, check=False)
        child_returncode = completed.returncode
        child_stdout = completed.stdout
        child_stderr = completed.stderr
        timed_out = False
    except subprocess.TimeoutExpired as error:
        child_returncode = None
        child_stdout = (error.stdout or b"").decode(errors="replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
        child_stderr = (error.stderr or b"").decode(errors="replace") if isinstance(error.stderr, bytes) else (error.stderr or "")
        timed_out = True
    ended = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    after = workspace_snapshot(workspace)
    config_after = profile_config_hash()
    events = _read_trace(trace)
    observed_requests = normalize_observed_requests(events, workspace)
    expected_observed = intervention_b_requests()
    expected_observed_events = [{"method": item["method"], "params": item["params"]} for item in expected_observed]
    request_shape_pass = observed_requests == expected_observed_events
    terminal_events = [event for event in events if event.get("method") == "turn/completed"]
    terminal = terminal_events[-1] if terminal_events else {}
    terminal_turn = terminal.get("params", {}).get("turn", {}) if isinstance(terminal.get("params"), Mapping) else {}
    turn_error = terminal_turn.get("error") if isinstance(terminal_turn, Mapping) else None
    terminal_status = terminal_turn.get("status") if isinstance(terminal_turn, Mapping) else None
    if not terminal_status and child_returncode != 0:
        terminal_status = "failed"
    terminal_error_category = None
    if turn_error:
        terminal_error_category = "same_as_historical_stopReason_error" if turn_error else None
        if isinstance(turn_error, Mapping) and turn_error.get("codexErrorInfo"):
            terminal_error_category = str(turn_error["codexErrorInfo"])
    if not terminal_error_category and terminal_status == "failed":
        terminal_error_category = "same_as_historical_stopReason_error"
    paths = changed_paths(before, after)
    receipt = {
        "schema_version": "pinned-dsh-permission-policy-canary-receipt-v0",
        "phase_id": PHASE_ID,
        "attempted": True,
        "started_at": started,
        "ended_at": ended,
        "consumed_marker": str(marker),
        "product_identity": {"dsh_base_commit": DSH_COMMIT, "dsh_base_tree": DSH_TREE, "dsh_tag": DSH_TAG, "codex_version": CODEX_VERSION, "codex_binary_sha256": sha256_file(CODEX_BINARY), "subscription_backed": True},
        "request_shape_digest": sha256_bytes(canonical(expected_observed).encode()),
        "request_shape_pass": request_shape_pass,
        "initialize_request_observed": any(event.get("direction") == "request" and event.get("method") == "initialize" for event in events),
        "thread_start_request_observed": any(event.get("direction") == "request" and event.get("method") == "thread/start" for event in events),
        "turn_start_request_observed": any(event.get("direction") == "request" and event.get("method") == "turn/start" for event in events),
        "turn_id_observed": any(
            isinstance(event.get("result"), Mapping)
            and isinstance(event["result"].get("turn"), Mapping)
            and event["result"]["turn"].get("id")
            for event in events
            if event.get("id") is not None
        ),
        "turn_started_observed": any(event.get("method") == "turn/started" for event in events),
        "turn_terminal_observed": bool(terminal_events),
        "terminal_status": terminal_status,
        "terminal_error_category": terminal_error_category,
        "terminal_error_message_sanitized": _sanitize(turn_error.get("message") if isinstance(turn_error, Mapping) else None),
        "jsonrpc_error_code": next((event.get("error", {}).get("code") for event in events if isinstance(event.get("error"), Mapping)), None),
        "http_status": next((event.get("http_status") for event in events if event.get("http_status") is not None), None),
        "tool_call_start_observed": any(event.get("method") in {"item/started", "item/started"} for event in events),
        "approval_request_observed": any("requestApproval" in str(event.get("method")) for event in events),
        "sandbox_denial_observed": "sandbox" in str(terminal_error_category).lower(),
        "terminal_lifecycle_event": terminal,
        "child_exit_status": child_returncode,
        "timeout": timed_out,
        "fixture_before_sha256": sha256_bytes(BEFORE),
        "fixture_after_sha256": sha256_file(fixture),
        "fixture_before_class": "BEFORE" if before.get("fixture.txt") == sha256_bytes(BEFORE) else "OTHER",
        "fixture_after_class": "AFTER" if fixture.read_bytes() == AFTER else "BEFORE" if fixture.read_bytes() == BEFORE else "OTHER",
        "changed_paths": paths,
        "unauthorized_changed_paths": sorted(set(paths) - {"fixture.txt"}),
        "stderr_sha256": sha256_bytes(child_stderr.encode()),
        "stdout_event_stream_sha256": sha256_bytes(child_stdout.encode()),
        "profile_a_config_hash_before": config_before,
        "profile_a_config_hash_after": config_after,
        "profile_a_config_mutated": config_before != config_after,
        "prelive_gate": "PASS" if request_shape_pass else "FAIL",
        "identity_gate": "PASS",
        "credential_gate": "PASS",
        "driver_output_status": "JSON_LAST_LINE_PRESENT" if child_stdout.strip() else "MISSING",
        "driver_exit_code": child_returncode,
        "classification": None,
    }
    receipt["classification"] = classify_live(receipt)
    write_json(ARTIFACT_DIR / "live_canary_receipt.json", _sanitize(receipt))
    return receipt


def main(argv: list[str]) -> int:
    if argv == ["fake-diff"]:
        print(json.dumps(build_fake_diff(), indent=2, sort_keys=True))
        return 0
    if argv == ["freeze"]:
        print(json.dumps(create_pre_live_freeze(), indent=2, sort_keys=True))
        return 0
    if argv == ["run-live"]:
        print(json.dumps(run_live(), indent=2, sort_keys=True))
        return 0
    raise SystemExit("usage: fake-diff | freeze | run-live")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
