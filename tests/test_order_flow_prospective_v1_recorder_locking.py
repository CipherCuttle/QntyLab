from datetime import UTC, datetime, timedelta
import inspect
from pathlib import Path

from qntylab.order_flow_prospective_v1_recorder import (
    EvidenceLedger,
    FIRST_WARMUP_CLOSE,
    synthetic_batch,
)


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def test_exact_data_retry_keeps_first_observation_timestamp(tmp_path: Path) -> None:
    close = _utc(FIRST_WARMUP_CLOSE)
    rows = synthetic_batch(close)
    ledger = EvidenceLedger(tmp_path)

    first = ledger.record_batch(
        logical_close=close,
        rows=rows,
        observed_at=close + timedelta(minutes=7),
    )
    retried = ledger.record_batch(
        logical_close=close,
        rows=rows,
        observed_at=close + timedelta(minutes=8),
    )

    assert retried == first
    assert retried["payload"]["observed_at_utc"] == "2026-09-15T00:07:00Z"
    assert len(ledger.events()) == 1


def test_decision_and_append_paths_are_inside_exclusive_lock() -> None:
    record_source = inspect.getsource(EvidenceLedger.record_batch)
    missed_source = inspect.getsource(EvidenceLedger.mark_missed)
    lock_source = inspect.getsource(EvidenceLedger._exclusive_lock)

    assert "with self._exclusive_lock():" in record_source
    assert "with self._exclusive_lock():" in missed_source
    assert "fcntl.LOCK_EX" in lock_source
    assert "fcntl.LOCK_UN" in lock_source
