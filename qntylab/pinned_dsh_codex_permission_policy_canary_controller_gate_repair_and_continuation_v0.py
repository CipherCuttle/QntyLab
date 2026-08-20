"""Continuation runner isolated from the consumed predecessor artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from qntylab import pinned_dsh_codex_terminal_error_permission_policy_forensics_v0 as controller


PHASE_ID = "PINNED_DSH_CODEX_PERMISSION_POLICY_CANARY_CONTROLLER_GATE_REPAIR_AND_CONTINUATION_V0"
ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_permission_policy_canary_controller_gate_repair_and_continuation_v0"
QUALIFICATION = ARTIFACT_DIR / "credential_gate_qualification.json"
HOSTILE_REVIEW = ARTIFACT_DIR / "hostile_implementation_review.md"


def _configure() -> None:
    # Reuse the frozen DSH request construction and receipt machinery while
    # keeping the consumed predecessor evidence and marker untouched.
    controller.PHASE_ID = PHASE_ID
    controller.ARTIFACT_DIR = ARTIFACT_DIR


def main(argv: list[str]) -> int:
    _configure()
    if argv == ["fake-diff"]:
        print(json.dumps(controller.build_fake_diff(), indent=2, sort_keys=True))
        return 0
    if argv == ["freeze"]:
        freeze = controller.create_pre_live_freeze()
        freeze.update({
            "controller_gate_qualification_sha256": controller.sha256_file(QUALIFICATION),
            "hostile_review_sha256": controller.sha256_file(HOSTILE_REVIEW),
            "receipt_schema": "pinned-dsh-permission-policy-canary-receipt-v0",
            "consumption_marker_semantics": "write immediately before product invocation; irrevocable; no retry after write",
        })
        controller.write_json(ARTIFACT_DIR / "prelive_freeze.json", freeze)
        print(json.dumps(freeze, indent=2, sort_keys=True))
        return 0
    if argv == ["run-live"]:
        print(json.dumps(controller.run_live(), indent=2, sort_keys=True))
        return 0
    raise SystemExit("usage: fake-diff | freeze | run-live")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
