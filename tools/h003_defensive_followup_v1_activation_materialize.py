from __future__ import annotations

import json
from pathlib import Path

from qntylab.h003_defensive_followup_v1_activation import (
    AUTHORIZATION_ID,
    CANDIDATE_ID,
    VARIANT_ID,
    build_authorization_contract,
)
from qntylab.research_ledger import sha256_path


ROOT = Path(__file__).resolve().parents[1]
AUTH_PATH = ROOT / "experiments/specs/h003_defensive_followup_v1_activation.json"
REOPEN_PATH = ROOT / "experiments/research/h003_defensive_followup_v1/activation_reopen_event.json"
PREREG_PATH = ROOT / "experiments/specs/h003_defensive_followup_v1.json"
DECISION_PATH = ROOT / "experiments/research/h003_defensive_followup_v1/decision_event.json"
REOPEN_EVENT_ID = "event_reopen_h003_defensive_followup_v1_activation"
PREVIOUS_DECISION_EVENT_ID = "event_decision_663334b58c3697ef37dd2e09"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    decision = json.loads(DECISION_PATH.read_text(encoding="utf-8"))
    if prereg.get("authorization_id") != "H003_DEFENSIVE_FOLLOWUP_V1":
        raise RuntimeError("unexpected preregistration")
    if decision.get("event_id") != PREVIOUS_DECISION_EVENT_ID or decision.get("status") != "BLOCKED":
        raise RuntimeError("activation does not target the canonical blocked decision")
    if decision.get("candidate_id") != CANDIDATE_ID or decision.get("variant_id") != VARIANT_ID:
        raise RuntimeError("activation target identity mismatch")

    contract = build_authorization_contract(reopen_event_id=REOPEN_EVENT_ID)
    if contract["authorization_id"] != AUTHORIZATION_ID or len(contract["authorized_trial_ids"]) != 88:
        raise RuntimeError("unexpected activation authorization contract")
    write_json(AUTH_PATH, contract)

    reopen = {
        "event_type": "CANDIDATE_REOPENED",
        "candidate_id": CANDIDATE_ID,
        "variant_id": VARIANT_ID,
        "previous_decision_event_id": PREVIOUS_DECISION_EVENT_ID,
        "reason": "ACTIVATE_FROZEN_H003_DEFENSIVE_FOLLOWUP_V1",
        "material_change": "The exact H003 48/192 defensive-edge candidate now has a merged, result-blind H003_DEFENSIVE_FOLLOWUP_V1 contract. This activation authorizes only 88 precomputed prior-exposed BTCUSDT/ETHUSDT retrospective diagnostic trial IDs under the frozen windows/costs and arms, but does not start, the future SOLUSDT/BTCUSDT/ETHUSDT paper-shadow recorder. BTC/ETH history cannot create confirmatory support. The recorder remains ARMED_BUT_INACTIVE_PENDING_ORIGIN_ARTIFACT with no market-data or signal recording authority until a separate post-merge Git-derived origin artifact is canonical. The prior 2023 excess-return failure remains negative evidence. No Qnty, QntySpot, live execution, capital, signing, or submission authority is created.",
        "authorization_contract_path": "experiments/specs/h003_defensive_followup_v1_activation.json",
        "authorization_contract_sha256": sha256_path(AUTH_PATH),
        "recorded_at_utc": "2026-09-11T17:22:00Z",
        "event_id": REOPEN_EVENT_ID,
    }
    write_json(REOPEN_PATH, reopen)
    print(json.dumps({
        "authorization_id": AUTHORIZATION_ID,
        "authorized_trial_count": len(contract["authorized_trial_ids"]),
        "reopen_event_id": REOPEN_EVENT_ID,
        "contract_sha256": reopen["authorization_contract_sha256"],
        "prospective_recorder_status": contract["metadata"]["prospective_recorder"]["status"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
