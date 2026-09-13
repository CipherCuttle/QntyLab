"""Stateless execution relay for Order Flow Prospective V1.

Moves only the Binance network hop off U.S. GitHub-hosted runners. The frozen
scientific source, symbols, timestamp identity, row validity and no-backfill
contract remain unchanged. This module grants no persistence, scheduler,
evaluation, trading, or downstream authority.
"""
from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Any, Callable, Sequence

from . import order_flow_prospective_v1_recorder as recorder
from . import order_flow_prospective_v1_source as source


class RelayBlocked(ValueError):
    pass


FetchOne = Callable[..., Sequence[Sequence[Any]]]
_CACHE: dict[tuple[str, str], list[list[Any]]] = {}
_CACHE_LOCK = Lock()


def _now(value: str | datetime | None = None) -> datetime:
    return datetime.now(UTC) if value is None else recorder.parse_utc(value)


def _current_window(logical_close: str | datetime, *, as_of: str | datetime | None = None) -> datetime:
    try:
        close = recorder.hour(logical_close)
        recorder.classify_logical_close(close)
    except recorder.RecorderBlocked as exc:
        raise RelayBlocked(str(exc)) from exc
    now = _now(as_of)
    if now < close:
        raise RelayBlocked("logical close is not complete")
    if now >= close + recorder.RECORDING_WINDOW:
        raise RelayBlocked("recording window is closed; historical relay access forbidden")
    return close


def fetch_current_scientific_row(*, symbol: str, logical_close: str | datetime, as_of: str | datetime | None = None, fetcher: FetchOne | None = None) -> dict[str, Any]:
    if symbol not in recorder.PANEL:
        raise RelayBlocked(f"non-panel symbol rejected: {symbol}")
    close = _current_window(logical_close, as_of=as_of)
    close_text = recorder.stamp(close)
    key = (symbol, close_text)
    fetcher = fetcher or source.default_fetch_one
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is None:
            payload = [list(row) for row in fetcher(symbol=symbol, logical_close=close)]
            if len(payload) != 1:
                raise RelayBlocked("exact-hour source must return exactly one kline row")
            source.validate_probe_row(symbol=symbol, logical_close=close, raw_row=payload[0])
            _CACHE[key] = payload
            cached = payload
    return {
        "mode": "ORDER_FLOW_V1_EXECUTION_RELAY",
        "scientific_source": "BINANCE_USDM_FUTURES_REST",
        "endpoint_base": recorder.ENDPOINT_BASE,
        "endpoint_path": recorder.ENDPOINT_PATH,
        "symbol": symbol,
        "logical_close_utc": close_text,
        "rows": cached,
    }


def run_non_scientific_smoke(*, as_of: str | datetime | None = None, fetcher: FetchOne | None = None) -> dict[str, Any]:
    now = _now(as_of)
    close = now.replace(minute=0, second=0, microsecond=0)
    fetcher = fetcher or source.default_fetch_one
    symbols: list[str] = []
    for symbol in recorder.PANEL:
        payload = [list(row) for row in fetcher(symbol=symbol, logical_close=close)]
        if len(payload) != 1:
            raise RelayBlocked(f"smoke expected exactly one row for {symbol}")
        source.validate_probe_row(symbol=symbol, logical_close=close, raw_row=payload[0])
        symbols.append(symbol)
    return {
        "mode": "NON_SCIENTIFIC_FRANKFURT_SOURCE_SMOKE",
        "scientific_evidence": False,
        "logical_close_utc": recorder.stamp(close),
        "symbol_count": len(symbols),
        "symbols": symbols,
        "status": "PASS",
    }
