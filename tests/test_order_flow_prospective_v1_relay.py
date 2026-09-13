from datetime import UTC, datetime, timedelta

import pytest

from qntylab import order_flow_prospective_v1_recorder as recorder
from qntylab.order_flow_prospective_v1_relay import RelayBlocked, fetch_current_scientific_row, run_non_scientific_smoke


def _row(symbol: str, logical_close):
    return [recorder.synthetic_row(symbol=symbol, logical_close=logical_close)]


def test_relay_allows_only_current_open_recording_window() -> None:
    close = recorder.hour(recorder.FIRST_WARMUP_CLOSE)
    calls = []

    def fetcher(*, symbol, logical_close):
        calls.append((symbol, recorder.stamp(logical_close)))
        return _row(symbol, logical_close)

    result = fetch_current_scientific_row(
        symbol="BTCUSDT",
        logical_close=close,
        as_of=close + timedelta(minutes=10),
        fetcher=fetcher,
    )
    assert result["symbol"] == "BTCUSDT"
    assert result["logical_close_utc"] == recorder.stamp(close)
    assert result["endpoint_base"] == recorder.ENDPOINT_BASE
    assert result["endpoint_path"] == recorder.ENDPOINT_PATH
    assert len(result["rows"]) == 1
    assert calls == [("BTCUSDT", recorder.stamp(close))]


def test_relay_rejects_historical_or_future_access_without_fetch() -> None:
    close = recorder.hour(recorder.FIRST_WARMUP_CLOSE)
    calls = []

    def forbidden_fetcher(**kwargs):
        calls.append(kwargs)
        raise AssertionError("provider must not be contacted")

    with pytest.raises(RelayBlocked, match="not complete"):
        fetch_current_scientific_row(
            symbol="BTCUSDT",
            logical_close=close,
            as_of=close - timedelta(seconds=1),
            fetcher=forbidden_fetcher,
        )
    with pytest.raises(RelayBlocked, match="historical relay access forbidden"):
        fetch_current_scientific_row(
            symbol="BTCUSDT",
            logical_close=close,
            as_of=close + timedelta(hours=1),
            fetcher=forbidden_fetcher,
        )
    assert calls == []


def test_relay_rejects_non_panel_symbol() -> None:
    close = recorder.hour(recorder.FIRST_WARMUP_CLOSE)
    with pytest.raises(RelayBlocked, match="non-panel symbol"):
        fetch_current_scientific_row(
            symbol="DOGEUSDT",
            logical_close=close,
            as_of=close + timedelta(minutes=1),
            fetcher=lambda **_: [],
        )


def test_non_scientific_smoke_exposes_no_market_values() -> None:
    as_of = datetime(2026, 9, 13, 1, 30, tzinfo=UTC)
    close = as_of.replace(minute=0, second=0, microsecond=0)

    result = run_non_scientific_smoke(
        as_of=as_of,
        fetcher=lambda *, symbol, logical_close: _row(symbol, logical_close),
    )
    assert result == {
        "mode": "NON_SCIENTIFIC_FRANKFURT_SOURCE_SMOKE",
        "scientific_evidence": False,
        "logical_close_utc": recorder.stamp(close),
        "symbol_count": 5,
        "symbols": list(recorder.PANEL),
        "status": "PASS",
    }
