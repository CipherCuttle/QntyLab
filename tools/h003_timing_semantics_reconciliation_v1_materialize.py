from __future__ import annotations

import json
from pathlib import Path

from qntylab import research_ledger


ROOT = Path(__file__).resolve().parents[1]
EVENT_PATH = ROOT / "experiments/research/h003_defensive_followup_v1/timing_semantics_reconciliation_decision_event.json"
DECISIONS_PATH = ROOT / "experiments/research/decisions.jsonl"


def main() -> None:
    event = json.loads(EVENT_PATH.read_text(encoding="utf-8"))
    event_id = event["event_id"]

    existing = DECISIONS_PATH.read_text(encoding="utf-8")
    if f'"event_id":"{event_id}"' not in existing:
        research_ledger.append_canonical_event(event)
    else:
        issues = research_ledger.doctor()
        if issues:
            raise RuntimeError("; ".join(issues))


if __name__ == "__main__":
    main()
