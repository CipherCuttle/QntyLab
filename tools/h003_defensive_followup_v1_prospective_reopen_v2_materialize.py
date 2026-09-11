from __future__ import annotations

import json
from pathlib import Path

from qntylab import research_ledger
from qntylab.h003_defensive_followup_v1_prospective_reopen import (
    REOPEN_EVENT_ID,
    build_authorization_contract,
    build_reopen_event,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "experiments/specs/h003_defensive_followup_v1_prospective_reopen_v2.json"
EVENT_PATH = ROOT / "experiments/research/h003_defensive_followup_v1/prospective_reopen_v2_event.json"
CANDIDATES_PATH = ROOT / "experiments/research/candidates.jsonl"
TRIAL_INDEX_PATH = ROOT / "experiments/research/trial_index.json"
RECORDED_AT_UTC = "2026-09-11T19:08:00Z"


def _write_canonical(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(research_ledger.canonical_bytes(value) + b"\n")


def _trial_ids() -> set[str]:
    value = json.loads(TRIAL_INDEX_PATH.read_text(encoding="utf-8"))
    return set(value["trials"])


def main() -> None:
    trial_ids_before = _trial_ids()

    contract = build_authorization_contract()
    _write_canonical(CONTRACT_PATH, contract)
    contract_sha256 = research_ledger.sha256_path(CONTRACT_PATH)

    event = build_reopen_event(contract_sha256=contract_sha256, recorded_at_utc=RECORDED_AT_UTC)
    _write_canonical(EVENT_PATH, event)

    existing = CANDIDATES_PATH.read_text(encoding="utf-8")
    if f'"event_id":"{REOPEN_EVENT_ID}"' not in existing:
        research_ledger.append_canonical_event(event)
    else:
        issues = research_ledger.doctor()
        if issues:
            raise RuntimeError("; ".join(issues))

    state = json.loads((ROOT / "experiments/research/state.json").read_text(encoding="utf-8"))
    variant = state["variants"][event["variant_id"]]
    # Canonical replay applies historical TRIAL_COMPLETED events after the reopen,
    # so this already-tested variant deterministically renders as SCREENING. That
    # status is historical replay metadata, not evidence that this generation ran
    # a trial; execution authority remains the active reopen contract below.
    if variant.get("status") != "SCREENING" or variant.get("active_reopen_event_id") != REOPEN_EVENT_ID:
        raise RuntimeError(f"prospective reopen did not materialize as the active fail-closed generation: {variant!r}")
    if variant.get("latest_decision_event_id") is not None:
        raise RuntimeError("prospective reopen unexpectedly retained a terminal decision")

    trial_ids_after = _trial_ids()
    if trial_ids_after != trial_ids_before:
        raise RuntimeError("prospective-only reopen changed the canonical trial index")


if __name__ == "__main__":
    main()
