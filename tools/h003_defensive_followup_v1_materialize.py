from __future__ import annotations

import json
from pathlib import Path

from qntylab.research_ledger import event_id, sha256_path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "experiments/runs/h003_edge_falsification_v0/analysis.json"
INPUT_ATTESTATION = ROOT / "experiments/runs/h003_edge_falsification_v0/input_attestation.json"
EXECUTION_RECEIPT = ROOT / "experiments/runs/h003_edge_falsification_v0/execution_receipt.json"
PREREG = ROOT / "experiments/specs/h003_defensive_followup_v1.json"
OLD_HOLDOUT = ROOT / "experiments/research/summaries/focused_trend_validation_v1_2023_holdout_review.json"
DECISIONS = ROOT / "experiments/research/decisions.jsonl"
OUTPUT = ROOT / "experiments/research/h003_defensive_followup_v1/decision_event.json"


def main() -> None:
    analysis = json.loads(ANALYSIS.read_text(encoding="utf-8"))
    if analysis.get("verdict") != "DEFENSIVE_EDGE_CANDIDATE":
        raise RuntimeError("H003 V0 verdict is not DEFENSIVE_EDGE_CANDIDATE")
    if analysis.get("trial_count") != 44:
        raise RuntimeError("H003 V0 trial count is not 44")
    if analysis.get("prior_2023_failure_preserved") is not True:
        raise RuntimeError("prior 2023 failure preservation is not true")

    old_decisions = [json.loads(line) for line in DECISIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    old = next((row for row in old_decisions if row.get("event_id") == "event_3206c7b09c089b274ca027a5"), None)
    if old is None or old.get("status") != "GRAVEYARDED" or "FAILED_2023_HOLDOUT_MULTIPLE_GATES" not in old.get("reason_codes", []):
        raise RuntimeError("canonical prior H003 2023 failure evidence missing or mutated")

    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg.get("authorization_id") != "H003_DEFENSIVE_FOLLOWUP_V1":
        raise RuntimeError("unexpected follow-up preregistration")

    evidence_paths = [
        "experiments/runs/h003_edge_falsification_v0/analysis.json",
        "experiments/runs/h003_edge_falsification_v0/input_attestation.json",
        "experiments/runs/h003_edge_falsification_v0/execution_receipt.json",
        "experiments/specs/h003_defensive_followup_v1.json",
        "experiments/research/summaries/focused_trend_validation_v1_2023_holdout_review.json",
    ]
    evidence_sha256 = {
        path: sha256_path(ROOT / path)
        for path in evidence_paths
    }

    payload = {
        "event_type": "DECISION_RECORDED",
        "candidate_id": "CANDIDATE_H003_MA_48_192_LONG_FLAT",
        "family_id": "moving_average_trend",
        "variant_id": "variant_00eb140f03a5f6ab40600160",
        "status": "FOLLOW_UP",
        "scope": "EXACT_VARIANT",
        "reason_codes": [
            "DEFENSIVE_EDGE_CANDIDATE",
            "RISK_ADJUSTED_BENEFIT_OBSERVED",
            "ABSOLUTE_RETURN_SUPERIORITY_NOT_ESTABLISHED",
            "PRIOR_2023_HOLDOUT_FAILURE_PRESERVED",
            "CROSS_ASSET_AND_PROSPECTIVE_REPLICATION_REQUIRED"
        ],
        "decision_note": "H003 V0 supports a narrow defensive/risk-adjusted mechanism candidate for the exact 48/192 long-flat variant. This does not rehabilitate the prior 2023 holdout failure as an excess-return claim, does not establish absolute-return superiority, and grants no Qnty, QntySpot, paper/live trading, capital, signing, or submission authority. Only the frozen H003_DEFENSIVE_FOLLOWUP_V1 cross-asset replication and prospective SOL paper/shadow observation may continue without a new authorization.",
        "evidence_paths": evidence_paths,
        "evidence_sha256": evidence_sha256,
        "revisit_condition": "Execute only the frozen BTCUSDT/ETHUSDT cross-asset replication after preregistration merge and activate the prospective SOL paper/shadow observation from a Git-derived post-merge origin. No same-sample SOL rerun, parameter search, asset-specific tuning, or downstream economic authority is authorized.",
        "recorded_at_utc": "2026-09-11T17:00:00Z",
    }
    payload["event_id"] = event_id("event_decision", payload)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(payload["event_id"])


if __name__ == "__main__":
    main()
