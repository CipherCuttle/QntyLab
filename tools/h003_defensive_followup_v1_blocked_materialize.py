from __future__ import annotations

import json
import subprocess
from pathlib import Path

from qntylab.research_ledger import event_id, sha256_path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_BASE = "585267ec3b0b56107bd63d92919e27ae9ceb8ccb"
PREREG = ROOT / "experiments/specs/h003_defensive_followup_v1.json"
ANALYSIS = ROOT / "experiments/runs/h003_edge_falsification_v0/analysis.json"
DECISIONS = ROOT / "experiments/research/decisions.jsonl"
OUTPUT = ROOT / "experiments/research/h003_defensive_followup_v1/decision_event.json"


def restore(path: str) -> None:
    (ROOT / path).write_bytes(subprocess.check_output(["git", "show", f"{CANONICAL_BASE}:{path}"], cwd=ROOT))


def main() -> None:
    for path in ("experiments/research/decisions.jsonl", "experiments/research/state.json", "experiments/research/trial_index.json"):
        restore(path)

    analysis = json.loads(ANALYSIS.read_text(encoding="utf-8"))
    if analysis.get("verdict") != "DEFENSIVE_EDGE_CANDIDATE" or analysis.get("trial_count") != 44 or analysis.get("prior_2023_failure_preserved") is not True:
        raise RuntimeError("unexpected H003 V0 evidence state")
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    boundary = prereg.get("activation_boundary", {})
    if boundary.get("governance_state_after_this_preregistration") != "BLOCKED" or boundary.get("generic_trial_execution_authorized") is not False:
        raise RuntimeError("follow-up activation boundary is not fail closed")

    old = next((json.loads(line) for line in DECISIONS.read_text(encoding="utf-8").splitlines() if line.strip() and json.loads(line).get("event_id") == "event_3206c7b09c089b274ca027a5"), None)
    if old is None or old.get("status") != "GRAVEYARDED" or "FAILED_2023_HOLDOUT_MULTIPLE_GATES" not in old.get("reason_codes", []):
        raise RuntimeError("canonical prior H003 2023 failure missing")

    evidence_paths = [
        "experiments/runs/h003_edge_falsification_v0/analysis.json",
        "experiments/runs/h003_edge_falsification_v0/input_attestation.json",
        "experiments/runs/h003_edge_falsification_v0/execution_receipt.json",
        "experiments/specs/h003_defensive_followup_v1.json",
        "experiments/research/summaries/focused_trend_validation_v1_2023_holdout_review.json",
        "experiments/research/summaries/focused_trend_validation_v1_2023_holdout_cells.csv",
    ]
    payload = {
        "event_type": "DECISION_RECORDED",
        "candidate_id": "CANDIDATE_H003_MA_48_192_LONG_FLAT",
        "family_id": "moving_average_trend",
        "variant_id": "variant_00eb140f03a5f6ab40600160",
        "status": "BLOCKED",
        "scope": "EXACT_VARIANT",
        "reason_codes": [
            "DEFENSIVE_EDGE_CANDIDATE",
            "RISK_ADJUSTED_BENEFIT_OBSERVED",
            "ABSOLUTE_RETURN_SUPERIORITY_NOT_ESTABLISHED",
            "PRIOR_2023_HOLDOUT_FAILURE_PRESERVED",
            "PRIOR_EXPOSED_RETROSPECTIVE_DIAGNOSTIC_ONLY",
            "FOLLOWUP_PREREGISTERED_AWAITING_ACTIVATION",
            "NO_GENERIC_TRIAL_AUTHORITY",
        ],
        "decision_note": "H003 V0 supports a narrow defensive/risk-adjusted mechanism candidate for the exact 48/192 long-flat variant, but the variant is BLOCKED pending a separate scoped activation. BTCUSDT and ETHUSDT are prior-exposed and may only be used as retrospective diagnostics after explicit activation; genuine confirmation requires a post-activation SOLUSDT/BTCUSDT/ETHUSDT paper-shadow panel. The prior 2023 excess-return failure remains canonical. This decision grants no generic trial, shadow, Qnty, QntySpot, live-trading, capital, signing, or submission authority.",
        "evidence_paths": evidence_paths,
        "evidence_sha256": {path: sha256_path(ROOT / path) for path in evidence_paths},
        "revisit_condition": "A separate Git-backed CANDIDATE_REOPENED activation must authorize the exact historical diagnostic trial matrix and prospective recorder, bind a post-activation origin, and preserve all H003_DEFENSIVE_FOLLOWUP_V1 invariants before any execution or shadow recording begins.",
        "recorded_at_utc": "2026-09-11T17:12:00Z",
    }
    payload["event_id"] = event_id("event_decision", payload)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(payload["event_id"])

if __name__ == "__main__":
    main()
