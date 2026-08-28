"""Synthetic, network-free fixtures for JH01 V1 source-adapter/caller tests.

Fabricates exact 12-field Binance USD-M kline rows and authenticated monthly
archive ZIP bytes in memory.  Nothing here touches the real campaign state
directory or performs any network access.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import io
import json
from pathlib import Path
from typing import Any
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PANEL = tuple(json.loads(
    (ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/preregistration.json").read_text()
)["frozen_target"]["ordered_20_symbol_panel"])
FIRST_REQUIRED = datetime(2025, 8, 15, tzinfo=UTC)
ORIGIN = datetime(2026, 9, 15, tzinfo=UTC)
REQUIRED_CLOSE_COUNT = int((ORIGIN - FIRST_REQUIRED).total_seconds() // 3600) + 1

_ARCHIVE_CACHE: dict[tuple[str, int, int], tuple[bytes, str]] = {}
_REST_CACHE: dict[str, list[list[Any]]] = {}


def price(symbol_index: int, close: datetime) -> str:
    hours = int((close - FIRST_REQUIRED).total_seconds() // 3600)
    value = 100 + symbol_index + (hours % 89) * 0.5 + ((hours + symbol_index) % 13) * 0.05
    return f"{value:.4f}"


def kline_row(close: datetime, symbol_index: int, *, open_shift_ms: int = 0, close_override_ms: int | None = None) -> list[Any]:
    open_ms = int((close - timedelta(hours=1)).timestamp() * 1000) + open_shift_ms
    close_ms = open_ms + 3_599_999 if close_override_ms is None else close_override_ms
    value = price(symbol_index, close)
    return [open_ms, value, value, value, value, "1", close_ms, "1", 1, "1", "1", "0"]


def month_closes(year: int, month: int) -> list[datetime]:
    """Closes whose hourly open falls inside the calendar month."""
    following = datetime(year + 1, 1, 1, tzinfo=UTC) if month == 12 else datetime(year, month + 1, 1, tzinfo=UTC)
    closes: list[datetime] = []
    cursor = datetime(year, month, 1, tzinfo=UTC)
    while cursor < following:
        closes.append(cursor + timedelta(hours=1))
        cursor += timedelta(hours=1)
    return closes


def archive_zip_bytes(symbol: str, year: int, month: int) -> tuple[bytes, str]:
    """Authenticated monthly archive fixture: one CSV member plus CHECKSUM text."""
    key = (symbol, year, month)
    if key not in _ARCHIVE_CACHE:
        filename = f"{symbol}-1h-{year}-{month:02d}.zip"
        member = f"{symbol}-1h-{year}-{month:02d}.csv"
        symbol_index = PANEL.index(symbol)
        lines = ["open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore"]
        for close in month_closes(year, month):
            lines.append(",".join(str(field) for field in kline_row(close, symbol_index)))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(member, "\n".join(lines) + "\n")
        data = buffer.getvalue()
        _ARCHIVE_CACHE[key] = (data, f"{sha256(data).hexdigest()}  {filename}")
    return _ARCHIVE_CACHE[key]


def rest_tail_rows(symbol: str) -> list[list[Any]]:
    """Same-hour REST tail fixture: every September close through the origin."""
    key = (symbol,)
    if key not in _REST_CACHE:
        symbol_index = PANEL.index(symbol)
        rows: list[list[Any]] = []
        close = datetime(2026, 9, 1, tzinfo=UTC)
        while close <= ORIGIN:
            rows.append(kline_row(close, symbol_index))
            close += timedelta(hours=1)
        _REST_CACHE[key] = rows
    return _REST_CACHE[key]


def synthetic_archive_provider(missing_months: frozenset[tuple[int, int]] = frozenset()):
    def provider(*, symbol: str, year: int, month: int) -> tuple[bytes, str] | None:
        if (year, month) in missing_months:
            return None
        return archive_zip_bytes(symbol, year, month)
    return provider


def synthetic_fetch_klines(
    *,
    omit_symbols: frozenset[str] = frozenset(),
    drop_opens: dict[str, set[int]] | None = None,
    capture: list[dict[str, Any]] | None = None,
    mutate=None,
):
    def fetch(*, symbol: str, start_ms: int, end_ms: int, interval: str) -> list[list[Any]]:
        if capture is not None:
            capture.append({"symbol": symbol, "start_ms": start_ms, "end_ms": end_ms, "interval": interval})
        if symbol in omit_symbols:
            return []
        rows = [list(row) for row in rest_tail_rows(symbol) if start_ms <= int(row[0]) <= end_ms]
        if drop_opens and symbol in drop_opens:
            rows = [row for row in rows if int(row[0]) not in drop_opens[symbol]]
        if mutate is not None:
            rows = mutate(symbol, rows)
        return rows
    return fetch
