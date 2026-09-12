from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from qntylab import jfp_v3_shadow as r2
from qntylab import jfp_v3_shadow_r3 as r3


ORIGIN = datetime(2026, 1, 1, tzinfo=UTC)


class CaptureRequester:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __call__(self, method, endpoint, params):
        self.calls.append((method, endpoint, dict(params)))
        return json.dumps(self.rows).encode()


def _rows_for_close_window(start: datetime, end: datetime):
    rows = []
    when = start - timedelta(hours=1)
    while when <= end - timedelta(hours=1):
        rows.append(
            [
                int(when.timestamp() * 1000),
                "100",
                "101",
                "99",
                "100.5",
            ]
        )
        when += timedelta(hours=1)
    return rows


def test_r3_feature_transport_queries_provider_open_times_for_logical_close_window():
    start = ORIGIN - timedelta(hours=24)
    end = ORIGIN
    requester = CaptureRequester(_rows_for_close_window(start, end))
    transport = r3.BinanceUmTransport(requester)

    _raw, source_id, bars = transport.bars("BTCUSDT", start, end)

    assert source_id == "binance-futures-klines"
    assert requester.calls == [
        (
            "GET",
            r3.BinanceUmTransport.OHLCV_ENDPOINT,
            {
                "symbol": "BTCUSDT",
                "interval": "1h",
                "startTime": int((start - timedelta(hours=1)).timestamp() * 1000),
                "endTime": int((end - timedelta(hours=1)).timestamp() * 1000),
            },
        )
    ]
    assert len(bars) == 25
    assert bars[0]["close_time"] == r2.stamp(start)
    assert bars[-1]["close_time"] == r2.stamp(end)
    assert all(r2.parse_stamp(row["close_time"]) <= end for row in bars)


def test_r3_outcome_transport_preserves_origin_through_origin_plus_24h_close_grid():
    start = ORIGIN
    end = ORIGIN + timedelta(hours=24)
    requester = CaptureRequester(_rows_for_close_window(start, end))
    transport = r3.BinanceUmTransport(requester)

    _raw, _source_id, bars = transport.bars("ETHUSDT", start, end)

    assert len(bars) == 25
    assert [row["close_time"] for row in bars] == [
        r2.stamp(start + timedelta(hours=index)) for index in range(25)
    ]


def test_r2_frozen_transport_demonstrates_the_shift_that_r3_repairs():
    start = ORIGIN - timedelta(hours=24)
    end = ORIGIN
    requester = CaptureRequester(
        _rows_for_close_window(start + timedelta(hours=1), end + timedelta(hours=1))
    )
    transport = r2.BinanceUmTransport(requester)

    _raw, _source_id, bars = transport.bars("BTCUSDT", start, end)

    assert requester.calls[0][2]["startTime"] == int(start.timestamp() * 1000)
    assert requester.calls[0][2]["endTime"] == int(end.timestamp() * 1000)
    assert bars[0]["close_time"] == r2.stamp(start + timedelta(hours=1))
    assert bars[-1]["close_time"] == r2.stamp(end + timedelta(hours=1))


def test_r3_manifest_binds_new_identity_without_mutating_r2():
    identity = r3.implementation_identity()
    assert identity["implementation_digest"] == "07132f8f75596da62c237235a79b5f5492a2ba62fd1817d2e3f5a0f7ba488555"
    assert r3.R2_CANONICAL_MERGE == "bc4f3a327f23d057da1ad970e9eeb7ed2fe10c91"
    assert r3.R2_IMPLEMENTATION_DIGEST == "3f80bcd2dd60aaae6e1307883cca2e996f631f7bbc3b76037eafef8450167e2b"


def test_r3_repair_is_inert_until_explicit_activation_or_collection():
    assert not (r3.ROOT / "data/jfp_v3_shadow/events.jsonl").exists()
