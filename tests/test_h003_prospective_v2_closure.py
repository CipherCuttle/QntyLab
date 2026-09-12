import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research/h003_defensive_followup_v1"
CLOSURE = BASE / "prospective_v2_closure.json"
LEDGER = BASE / "prospective_v2_terminal_ledger.jsonl"
RUNTIME = BASE / "prospective_source_v2_runtime.json"
WORKFLOW = ROOT / ".github/workflows/h003-prospective-operation-v2.yml"


def test_h003_v2_closure_preserves_exact_terminal_evidence() -> None:
    closure = json.loads(CLOSURE.read_text(encoding="utf-8"))
    ledger_bytes = LEDGER.read_bytes()
    lines = [line for line in ledger_bytes.decode("utf-8").splitlines() if line.strip()]

    assert closure["state"] == "CLOSED_BLOCKED"
    assert closure["closure_state"] == "BLOCKED_MISSED_RECORDING_WINDOW"
    assert closure["prospective_origin_utc"] == "2026-09-12T02:00:00Z"
    assert closure["recorded_hour_count"] == 0
    assert closure["terminal_blocked"] is True
    assert closure["backfill"] == "FORBIDDEN"
    assert closure["economic_verdict"] == "FORBIDDEN"
    assert closure["successor_requires_new_future_origin"] is True
    assert closure["successor_may_not_reuse_v2_campaign_identity"] is True
    assert len(lines) == 1
    assert hashlib.sha256(ledger_bytes).hexdigest() == closure["terminal_ledger_sha256"]

    event = json.loads(lines[0])
    assert event["event_digest"] == closure["terminal_event_digest"]
    assert event["event_type"] == "RECORDING_BLOCKED"
    assert event["payload"]["reason"] == "MISSED_ONE_HOUR_RECORDING_WINDOW"
    assert event["payload"]["through_logical_close_utc"] == closure["prospective_origin_utc"]
    assert event["payload"]["backfill"] == "FORBIDDEN"
    assert event["payload"]["economic_verdict"] == "FORBIDDEN"


def test_h003_v2_runtime_is_closed_and_unscheduled() -> None:
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    workflow_bytes = WORKFLOW.read_bytes()

    assert runtime["state"] == "CLOSED_BLOCKED"
    assert runtime["schedule_utc"] is None
    assert runtime["scheduler_active"] is False
    assert runtime["write_authority"] == "NONE_CLOSED"
    assert runtime["backfill"] == "FORBIDDEN"
    assert runtime["successor_requires_new_future_origin"] is True
    assert hashlib.sha256(workflow_bytes).hexdigest() == runtime["workflow_sha256"]


def test_h003_v2_workflow_is_manual_read_only_tombstone() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "contents: write" not in text
    assert text.count("contents: read") >= 2
    assert "Verify canonical H003 V2 terminal closure" in text
    assert "binance" not in lowered
    assert "curl " not in lowered
    assert "gh " not in lowered
    assert "h003_defensive_followup_v1_prospective_source_v2" not in text
