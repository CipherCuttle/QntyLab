"""Single-exposure C runner: frozen B plus explicit thread/start sandbox ownership."""

from __future__ import annotations

import copy
import glob
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from qntylab import pinned_dsh_codex_terminal_error_permission_policy_forensics_v0 as controller


PHASE_ID = "PINNED_DSH_CODEX_SANDBOX_POLICY_OWNERSHIP_FORENSICS_V0"
ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_sandbox_policy_ownership_forensics_v0"
PATCH = ARTIFACT_DIR / "intervention_c.patch"
QUALIFICATION = ARTIFACT_DIR / "request_qualification.json"
HOSTILE_REVIEW = ARTIFACT_DIR / "hostile_implementation_review.md"


def intervention_c_requests(workspace: str = "<workspace>", thread_id: str = "<thread-id>") -> list[dict[str, Any]]:
    value = copy.deepcopy(controller.intervention_b_requests(workspace, thread_id))
    value[1]["params"]["sandbox"] = "workspace-write"
    return value


def c_total_delta() -> list[dict[str, Any]]:
    return controller.semantic_request_delta(controller.historical_requests(), intervention_c_requests())


def b_to_c_delta() -> list[dict[str, Any]]:
    return controller.semantic_request_delta(controller.intervention_b_requests(), intervention_c_requests())


def fake_c_capture(requests: list[dict[str, Any]]) -> dict[str, Any]:
    capture = controller.fake_app_server_capture(requests)
    for event in capture["events"]:
        if event.get("method") == "thread/start" and event.get("direction") == "response":
            event["effective"]["sandbox"] = "workspaceWrite"
    return capture


def build_fake_diff() -> dict[str, Any]:
    historical = controller.historical_requests()
    b = controller.intervention_b_requests()
    c = intervention_c_requests()
    from_a = controller.semantic_request_delta(historical, c)
    from_b = controller.semantic_request_delta(b, c)
    expected_b_to_c = [{
        "method": "thread/start",
        "path": "params.sandbox",
        "before": "<ABSENT>",
        "after": "workspace-write",
    }]
    if from_b != expected_b_to_c:
        raise RuntimeError("PRELIVE_BLOCKED: B-to-C request delta is not exactly one sandbox field")
    artifact = {
        "schema_version": "pinned-dsh-sandbox-policy-request-diff-v0",
        "phase_id": PHASE_ID,
        "historical_a_shape": historical,
        "intervention_b_shape": b,
        "intervention_c_shape": c,
        "request_delta_from_a": from_a,
        "request_delta_count_from_a": len(from_a),
        "request_delta": from_a,
        "request_delta_count": len(from_a),
        "request_delta_from_b": from_b,
        "request_delta_count_from_b": len(from_b),
        "expected_request_delta_from_b": expected_b_to_c,
        "request_delta_pass": from_b == expected_b_to_c,
        "prompt_sha256": controller.sha256_bytes(controller.PROMPT.encode()),
        "fake_historical_a_capture": controller.fake_app_server_capture(historical),
        "fake_intervention_b_capture": controller.fake_app_server_capture(b),
        "fake_intervention_c_capture": fake_c_capture(c),
        "dsh_identity": {"repository": controller.DSH_REPOSITORY, "commit": controller.DSH_COMMIT, "tree": controller.DSH_TREE, "tag": controller.DSH_TAG},
        "codex_identity": {"version": controller.CODEX_VERSION, "home": str(controller.CODEX_HOME)},
        "environment_semantics": {"api_key_values_read": False, "model_changed": False, "identity_changed": False, "prompt_changed": False},
    }
    controller.write_json(ARTIFACT_DIR / "fake_app_server_request_diff.json", artifact)
    return artifact


def _configure() -> None:
    controller.PHASE_ID = PHASE_ID
    controller.ARTIFACT_DIR = ARTIFACT_DIR
    controller.PATCH = PATCH
    controller.intervention_b_requests = intervention_c_requests
    controller.expected_delta = c_total_delta


def freeze() -> dict[str, Any]:
    _configure()
    freeze_value = controller.create_pre_live_freeze()
    freeze_value.update({
        "b_predecessor_receipt": "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_permission_policy_canary_controller_gate_repair_and_continuation_v0/live_canary_receipt.json",
        "b_to_c_request_delta": b_to_c_delta(),
        "b_to_c_request_delta_count": len(b_to_c_delta()),
        "request_qualification_sha256": controller.sha256_file(QUALIFICATION),
        "hostile_review_sha256": controller.sha256_file(HOSTILE_REVIEW),
        "receipt_schema": "pinned-dsh-sandbox-policy-ownership-canary-receipt-v0",
        "consumption_marker_semantics": "write immediately before product invocation; independent from B; irrevocable; no retry",
        "live_attempts_authorized": 1,
        "live_attempts_consumed": 0,
    })
    controller.write_json(ARTIFACT_DIR / "prelive_freeze.json", freeze_value)
    return freeze_value


def run_live() -> dict[str, Any]:
    _configure()
    real_run = controller.subprocess.run

    def apply_intervention_with_patch_tool(args: Any, *run_args: Any, **run_kwargs: Any) -> Any:
        if isinstance(args, list) and len(args) >= 4 and args[:3] == ["git", "-C", args[2]] and args[3] == "apply":
            dsh_copy = Path(args[2])
            return real_run(
                ["patch", "-p1", "-d", str(dsh_copy)],
                input=PATCH.read_text(encoding="utf-8"),
                *run_args,
                **run_kwargs,
            )
        return real_run(args, *run_args, **run_kwargs)

    controller.subprocess.run = apply_intervention_with_patch_tool
    try:
        receipt = controller.run_live()
    finally:
        controller.subprocess.run = real_run

    trace_candidates = [Path(item) for item in glob.glob("/tmp/qntylab-pinned-dsh-permission-control-*/rpc-trace.jsonl")]
    trace_path = max(trace_candidates, key=lambda item: item.stat().st_mtime_ns) if trace_candidates else None
    events = controller._read_trace(trace_path) if trace_path else []

    def contains_text(value: Any, needle: str) -> bool:
        if isinstance(value, str):
            return needle in value.lower()
        if isinstance(value, Mapping):
            return any(contains_text(item, needle) for item in value.values())
        if isinstance(value, list):
            return any(contains_text(item, needle) for item in value)
        return False

    turn_started_ordinals = [index for index, event in enumerate(events, start=1) if event.get("method") == "turn/started"]
    read_only_ordinals = [index for index, event in enumerate(events, start=1) if contains_text(event, "workspace is read-only")]
    errors: list[dict[str, Any]] = []
    for ordinal, event in enumerate(events, start=1):
        error = event.get("error")
        if not isinstance(error, Mapping):
            continue
        method = event.get("method") or event.get("request_method")
        stage = method if method in {"initialize", "thread/start", "turn/start"} else "terminal/other"
        errors.append({
            "event_ordinal": ordinal,
            "stage": stage,
            "method": method,
            "code": error.get("code"),
            "message": controller._sanitize(error.get("message")),
            "before_turn_started": bool(turn_started_ordinals and ordinal < turn_started_ordinals[0]),
        })
    code_32600 = [item for item in errors if item.get("code") == -32600]
    if code_32600 and read_only_ordinals:
        precedes_read_only: Any = code_32600[0]["event_ordinal"] < read_only_ordinals[0]
    else:
        precedes_read_only = "UNKNOWN"
    forensics = {
        "jsonrpc_errors": errors,
        "jsonrpc_32600_source_stage": code_32600[0]["stage"] if code_32600 else "UNKNOWN",
        "jsonrpc_32600_fatal": "NO" if code_32600 and receipt.get("turn_started_observed") and receipt.get("turn_terminal_observed") else "UNKNOWN",
        "jsonrpc_32600_event_ordinal": code_32600[0]["event_ordinal"] if code_32600 else "UNKNOWN",
        "jsonrpc_32600_precedes_read_only_message": precedes_read_only,
        "read_only_message_observed": bool(read_only_ordinals),
        "trace_event_count": len(events),
    }
    receipt.update(forensics)
    receipt["authorization_project"] = "PINNED_DSH_CODEX_SANDBOX_POLICY_OWNERSHIP_FORENSICS_AUTHORIZATION_V0"
    receipt["authorization_canonical"] = True
    receipt["predecessor_b_pr"] = 156
    receipt["predecessor_b_consumed"] = True
    receipt["b_predecessor_receipt"] = "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_permission_policy_canary_controller_gate_repair_and_continuation_v0/live_canary_receipt.json"
    receipt["implementation_phase"] = PHASE_ID
    receipt["b_to_c_request_delta"] = b_to_c_delta()
    receipt["b_to_c_request_delta_count"] = len(b_to_c_delta())
    receipt["receipt_schema"] = "pinned-dsh-sandbox-policy-ownership-canary-receipt-v0"
    receipt["product_invocation_count"] = 1
    if receipt.get("prelive_gate") != "PASS":
        classification = "PRELIVE_BLOCKED"
    elif receipt.get("identity_gate") != "PASS" or receipt.get("credential_gate") != "PASS" or receipt.get("profile_a_config_mutated") or receipt.get("timeout"):
        classification = "INCONCLUSIVE_INFRA"
    elif receipt.get("fixture_before_class") == "BEFORE" and receipt.get("fixture_after_class") == "AFTER" and receipt.get("changed_paths") == ["fixture.txt"] and receipt.get("unauthorized_changed_paths") == [] and receipt.get("terminal_status") == "completed":
        classification = "INTERVENTION_PASS"
    elif receipt.get("read_only_message_observed") and receipt.get("fixture_after_class") == "BEFORE" and receipt.get("changed_paths") == []:
        classification = "SAME_READ_ONLY_FAILURE"
    elif receipt.get("turn_terminal_observed") and receipt.get("changed_paths") != ["fixture.txt"]:
        classification = "DIFFERENT_FAILURE"
    else:
        classification = "INCONCLUSIVE_INFRA"
    receipt["classification"] = classification
    receipt["causal_update"] = {
        "INTERVENTION_PASS": "SANDBOX_OWNERSHIP_STRONGLY_CAUSALLY_SUPPORTED",
        "SAME_READ_ONLY_FAILURE": "SANDBOX_OWNERSHIP_HYPOTHESIS_FALSIFIED",
        "DIFFERENT_FAILURE": "SANDBOX_OWNERSHIP_AFFECTS_PATH_BUT_IS_INSUFFICIENT",
        "INCONCLUSIVE_INFRA": "NO_VALID_CAUSAL_COMPARISON",
        "PRELIVE_BLOCKED": "NO_CAUSAL_UPDATE",
    }[classification]
    receipt["root_cause_claim_strength"] = "STRONGLY_CAUSALLY_SUPPORTED" if classification == "INTERVENTION_PASS" else "NOT_PROVEN"
    receipt["phase_id"] = PHASE_ID
    receipt["sandbox_requested"] = "workspace-write"
    receipt["approval_policy_requested"] = "never"
    receipt["b_to_c_request_delta"] = b_to_c_delta()
    receipt["b_to_c_request_delta_count"] = len(b_to_c_delta())
    receipt["receipt_schema"] = "pinned-dsh-sandbox-policy-ownership-canary-receipt-v0"
    controller.write_json(ARTIFACT_DIR / "live_canary_receipt.json", controller._sanitize(receipt))
    return receipt


def main(argv: list[str]) -> int:
    if argv == ["fake-diff"]:
        print(json.dumps(build_fake_diff(), indent=2, sort_keys=True))
        return 0
    if argv == ["freeze"]:
        print(json.dumps(freeze(), indent=2, sort_keys=True))
        return 0
    if argv == ["run-live"]:
        print(json.dumps(run_live(), indent=2, sort_keys=True))
        return 0
    raise SystemExit("usage: fake-diff | freeze | run-live")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
