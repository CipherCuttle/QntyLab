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
RECORDED_AT_UTC = "2026-09-11T19:08:00Z"


def _write_canonical(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(research_ledger.canonical_bytes(value) + b"\n")


def main() -> None:
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
    if variant.get("status") != "PROPOSED" or variant.get("active_reopen_event_id") != REOPEN_EVENT_ID:
        raise RuntimeError(f"prospective reopen did not materialize as the active fail-closed generation: {variant!r}")


if __name__ == "__main__":
    main()
