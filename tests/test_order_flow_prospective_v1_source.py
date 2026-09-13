from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from qntylab import order_flow_prospective_v1_recorder as recorder
from qntylab.order_flow_prospective_v1_source import (
    ENDPOINT_BASE,
    ENDPOINT_PATH,
    PANEL,
    SourceBlocked,
    default_fetch_one,
    fetch_scientific_batch,
    request_spec,
    run_non_scientific_live_probe,
    stage_due_hour,
    validate_probe_row,
    validate_recorder_qualification,
)


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def test_recorder_qualification_pass_receipt_binds_exact_foundation() -> None:
    result = validate_recorder_qualification()
    assert result["recorder_merge_sha"] == "5043c4e311980ec7b655be8f93f97b91b845c2ff"
    assert result["qualification_run_id"] == 34730310188
    assert result["qualification_asset_sha256"] == "61878def8d673e38f0417062a43d328c79805cd4883bc9b40875e1b6a41fc8bc"


def test_request_spec_is_exact_for_scientific_hour() -> None:
    close = _utc(recorder.FIRST_WARMUP_CLOSE)
    spec = request_spec(close, symbol="BTCUSDT")
    assert spec["endpoint_base"] == ENDPOINT_BASE
    assert spec["endpoint_path"] == ENDPOINT_PATH
    assert spec["params"] == {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "startTime": int((close - timedelta(hours=1)).timestamp() * 1000),
        "endTime": int(close.timestamp() * 1000) - 1,
        "limit": 1,
    }


def test_default_fetch_one_uses_exact_query_and_shape() -> None:
    close = _utc(recorder.FIRST_WARMUP_CLOSE)
    expected = recorder.synthetic_row(symbol="BTCUSDT", logical_close=close)
    seen = {}

    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            import json
            return json.dumps([expected]).encode()

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return Response()

    payload = default_fetch_one(symbol="BTCUSDT", logical_close=close, opener=opener)
    assert payload == [expected]
    parsed = urlparse(seen["url"])
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == f"{ENDPOINT_BASE}{ENDPOINT_PATH}"
    query = parse_qs(parsed.query)
    assert query == {
        "symbol": ["BTCUSDT"],
        "interval": ["1h"],
        "startTime": [str(int((close - timedelta(hours=1)).timestamp() * 1000))],
        "endTime": [str(int(close.timestamp() * 1000) - 1)],
        "limit": ["1"],
    }


def test_provider_shape_and_timestamp_mismatch_fail_closed() -> None:
    close = _utc(recorder.FIRST_WARMUP_CLOSE)
    row = recorder.synthetic_row(symbol="BTCUSDT", logical_close=close)
    assert validate_probe_row(symbol="BTCUSDT", logical_close=close, raw_row=row)["status"] == "SHAPE_TIMESTAMP_PASS"

    bad = list(row)
    bad[6] = int(close.timestamp() * 1000)
    with pytest.raises(SourceBlocked, match="timestamp identity mismatch"):
        validate_probe_row(symbol="BTCUSDT", logical_close=close, raw_row=bad)

    with pytest.raises(SourceBlocked, match="exactly 12"):
        validate_probe_row(symbol="BTCUSDT", logical_close=close, raw_row=row[:-1])


def test_scientific_batch_requires_exact_five_provider_rows() -> None:
    close = _utc(recorder.FIRST_WARMUP_CLOSE)
    observed = close + timedelta(minutes=4)

    def fetcher(*, symbol, logical_close):
        return [recorder.synthetic_row(symbol=symbol, logical_close=logical_close)]

    rows = fetch_scientific_batch(
        logical_close=close,
        observed_at=observed,
        fetcher=fetcher,
        clock=lambda: observed,
    )
    assert tuple(rows) == PANEL

    def empty_fetcher(*, symbol, logical_close):
        return []

    with pytest.raises(SourceBlocked, match="exactly one row"):
        fetch_scientific_batch(
            logical_close=close,
            observed_at=observed,
            fetcher=empty_fetcher,
            clock=lambda: observed,
        )


def test_acquisition_crossing_deadline_marks_missed_and_stops_fetching(tmp_path: Path) -> None:
    close = _utc(recorder.FIRST_WARMUP_CLOSE)
    observed = close + timedelta(minutes=59)
    ledger = recorder.EvidenceLedger(tmp_path)
    calls = []
    ticks = iter((observed, close + timedelta(hours=1, seconds=1)))

    def clock():
        return next(ticks)

    def fetcher(*, symbol, logical_close):
        calls.append(symbol)
        return [recorder.synthetic_row(symbol=symbol, logical_close=logical_close)]

    event = stage_due_hour(
        ledger,
        logical_close=close,
        observed_at=observed,
        fetcher=fetcher,
        clock=clock,
    )

    assert event["event_type"] == "WINDOW_MISSED"
    assert event["payload"]["detected_at_utc"] == "2026-09-15T01:00:01Z"
    assert calls == ["BTCUSDT"]
    assert tuple(item["event_type"] for item in ledger.events()) == ("WINDOW_MISSED",)


def test_late_hour_marks_missed_without_contacting_provider(tmp_path: Path) -> None:
    close = _utc(recorder.FIRST_WARMUP_CLOSE)
    ledger = recorder.EvidenceLedger(tmp_path)
    calls = []

    def forbidden_fetcher(**kwargs):
        calls.append(kwargs)
        raise AssertionError("provider must not be contacted for missed window")

    event = stage_due_hour(
        ledger,
        logical_close=close,
        observed_at=close + timedelta(hours=1),
        fetcher=forbidden_fetcher,
    )
    assert event["event_type"] == "WINDOW_MISSED"
    assert calls == []


def test_live_probe_returns_no_price_volume_or_feature_values() -> None:
    as_of = datetime(2026, 9, 13, 1, 30, tzinfo=UTC)
    close = as_of.replace(minute=0, second=0, microsecond=0)

    def fetcher(*, symbol, logical_close):
        return [recorder.synthetic_row(symbol=symbol, logical_close=logical_close)]

    result = run_non_scientific_live_probe(as_of=as_of, fetcher=fetcher)
    assert result == {
        "mode": "NON_SCIENTIFIC_SOURCE_QUALIFICATION",
        "scientific_evidence": False,
        "logical_close_utc": "2026-09-13T01:00:00Z",
        "symbol_count": 5,
        "symbols": list(PANEL),
        "status": "PASS",
    }
    serialized = str(result).lower()
    assert "price" not in serialized
    assert "volume" not in serialized
    assert "imbalance" not in serialized
