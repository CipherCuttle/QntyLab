from __future__ import annotations

import json
import subprocess
from pathlib import Path

from qntylab.research_ledger import event_id, sha256_path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_BASE = "585267ec3b0b56107bd63d92919e27ae9ceb8ccb"
ANALYSIS = ROOT / "experiments/runs/h003_edge_falsification_v0/analysis.json"
INPUT_ATTESTATION = ROOT / "experiments/runs/h003_edge_falsification_v0/input_attestation.json"
EXECUTION_RECEIPT = ROOT / "experiments/runs/h003_edge_falsification_v0/execution_receipt.json"
PREREG = ROOT / "experiments/specs/h003_defensive_followup_v1.json"
OLD_HOLDOUT_REVIEW = ROOT / "experiments/research/summaries/focused_trend_validation_v1_2023_holdout_review.json"
OLD_HOLDOUT_CELLS = ROOT / "experiments/research/summaries/focused_trend_validation_v1_2023_holdout_cells.csv"
DECISIONS = ROOT / "experiments/research/decisions.jsonl"
OUTPUT = ROOT / "experiments/research/h003_defensive_followup_v1/decision_event.json"


def restore_from_base(path: str) -> None:
    data = subprocess.check_output(["git", "show", f"{CANONICAL_BASE}:{path}"], cwd=ROOT)
    target = ROOT / path
    target.write_bytes(data)


def main() -> None:
    # Remove the unmerged branch-local decision/index materialization before
    # writing the corrected event. Canonical master remains untouched.
    for path in (
        "experiments/research/decisions.jsonl",
        "experiments/research/state.json",
        "experiments/research/trial_index.json",
    ):
        restore_from_base(path)

    analysis = json.loads(ANALYSIS.read_text(encoding="utf-8"))
    if analysis.get("verdict") != "DEFENSIVE_EDGE_CANDIDATE" or analysis.get("trial_count") != 44:
        raise RuntimeError("unexpected H003 V0 evidence state")
    if analysis.get("prior_2023_failure_preserved") is not True:
        raise RuntimeError("prior 2023 failure preservation is not true")

    old_decisions = [json.loads(line) for line in DECISIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    old = next((row for row in old_decisions if row.get("event_id") == "event_3206c7b09c089b274ca027a5"), None)
    if old is None or old.get("status") != "GRAVEYARDED" or "FAILED_2023_HOLDOUT_MULTIPLE_GATES" not in old.get("reason_codes", []):
        raise RuntimeError("canonical prior H003 2023 failure evidence missing or mutated")

    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg.get("authorization_id") != "H003_DEFENSIVE_FOLLOWUP_V1":
        raise RuntimeError("unexpected follow-up preregistration")
    diagnostic = prereg.get("prior_exposed_retrospective_diagnostic", {})
    if diagnostic.get("prior_exposure_acknowledged") is not True or diagnostic.get("exact_h003_btc_eth_were_previously_evaluated") is not True:
        raise RuntimeError("BTC/ETH prior exposure is not frozen")
    if prereg.get("prospective_panel", {}).get("assets") != ["SOLUSDT", "BTCUSDT", "ETHUSDT"]:
        raise RuntimeError("unexpected prospective panel")

    evidence_paths = [
        "experiments/runs/h003_edge_falsification_v0/analysis.json",
        "experiments/runs/h003_edge_falsification_v0/input_attestation.json",
        "experiments/runs/h003_edge_falsification_v0/execution_receipt.json",
        "experiments/specs/h003_defensive_followup_v1.json",
        "experiments/research/summaries/focused_trend_validation_v1_2023_holdout_review.json",
        "experiments/research/summaries/focused_trend_validation_v1_2023_holdout_cells.csv",
    ]
    evidence_sha256 = {path: sha256_path(ROOT / path) for path in evidence_paths}

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
            "PRIOR_EXPOSED_RETROSPECTIVE_DIAGNOSTIC_ONLY",
            "PROSPECTIVE_MULTI_ASSET_CONFIRMATION_REQUIRED",
        ],
        "decision_note": "H003 V0 supports a narrow defensive/risk-adjusted mechanism candidate for the exact 48/192 long-flat variant. BTCUSDT and ETHUSDT are explicitly prior-exposed for this exact variant and any retrospective use is diagnostic only, not independent confirmation. The prior 2023 excess-return failure remains canonical. Genuine confirmation requires the frozen post-preregistration SOLUSDT/BTCUSDT/ETHUSDT paper-shadow panel. No Qnty, QntySpot, live-trading, capital, signing, or submission authority is granted.",
        "evidence_paths": evidence_paths,
        "evidence_sha256": evidence_sha256,
        "revisit_condition": "After this preregistration is merged, historical BTCUSDT/ETHUSDT may be run only as the frozen prior-exposed diagnostic with exact input attestation, and SOLUSDT/BTCUSDT/ETHUSDT may enter the frozen prospective paper-shadow panel from one Git-derived post-merge origin. No same-sample promotion, parameter search, asset-specific tuning, or downstream economic authority is authorized.",
        "recorded_at_utc": "2026-09-11T17:05:00Z",
    }
    payload["event_id"] = event_id("event_decision", payload)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(payload["event_id"])


if __name__ == "__main__":
    main()
