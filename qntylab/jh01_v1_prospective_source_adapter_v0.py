"""Unbound operational source adapter for the frozen JH01 V1 campaign.

Authority: ``jh01_v1_pre_origin_source_authority_resolution_v0.json`` verdict
``JH01_V1_EXISTING_CAMPAIGN_REPAIR_AUTHORIZED``, change classification
``UNBOUND_OPERATIONAL_ADAPTER``.  This module owns no validation authority of
its own: historical bulk admission is delegated to the frozen
``bars_from_authenticated_archive`` and final admission of the composed bar
set is delegated to the frozen ``validate_bars``.  The frozen recorder and
wrapper modules are not modified.

Source policy (single venue, single endpoint, fail closed):
- immutable historical months come from authenticated data.binance.vision
  monthly archives (one admitted helper, never exclusive);
- only required closes unavailable from completed monthly archives are
  acquired through first-party Binance USD-M REST
  (``https://fapi.binance.com/fapi/v1/klines``, interval exactly ``"1h"``);
- no current/open bar, no future close, no imputation, no row dropping, no
  alternate venue or provider fallback.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import Any, Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import jh01_v1_prospective_recorder_implementation_v0 as recorder


REST_ENDPOINT = "https://fapi.binance.com/fapi/v1/klines"
INTERVAL = "1h"
HOUR_MS = 3_600_000
ARCHIVE_ZIP_URL = "https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/1h/{symbol}-1h-{year:04d}-{month:02d}.zip"


class SourceAdapterBlocked(ValueError):
    """The unbound source adapter contract rejects a requested acquisition."""


FetchKlines = Callable[..., Sequence[Sequence[Any]]]
ArchiveProvider = Callable[..., tuple[bytes, str] | None]


def frozen_panel() -> tuple[str, ...]:
    """Exact frozen 20-symbol panel, read from the frozen recorder constants."""
    return recorder._frozen_panel()


def _hour_ms(value: datetime) -> int:
    if value.tzinfo is None:
        raise SourceAdapterBlocked("UTC-aware timestamp required")
    value = value.astimezone(UTC)
    if value.minute or value.second or value.microsecond:
        raise SourceAdapterBlocked("hour-aligned timestamp required")
    return int(value.timestamp() * 1000)


def request_bounds(*, first_required_close: datetime, origin: datetime) -> tuple[int, int]:
    """Deterministic REST window: open of the first required close through the
    close boundary of the origin bar.  The adapter never requests beyond the
    origin logical boundary."""
    start_ms = _hour_ms(first_required_close) - HOUR_MS
    end_ms = _hour_ms(origin) - 1
    if end_ms <= start_ms:
        raise SourceAdapterBlocked("empty required source window")
    return start_ms, end_ms


def rest_bar_from_row(
    symbol: str,
    row: Sequence[Any],
    *,
    first_required_close: datetime,
    origin: datetime,
) -> recorder.Bar:
    """Translate one exact Binance USD-M 12-field kline row into the frozen
    Bar representation, preserving the provider close-time mapping exactly.

    Frozen mapping: for logical close ``L`` the raw row carries
    ``open_ms == L - 1h`` and ``close_ms == L - 1ms``; hence
    ``L == close_time + 1ms``.  A row whose close time lies beyond the origin
    logical boundary (including the currently open bar) is rejected, never
    silently dropped.
    """
    if symbol not in frozen_panel():
        raise SourceAdapterBlocked(f"non-panel symbol rejected: {symbol}")
    if len(row) != 12:
        raise SourceAdapterBlocked("REST kline row is not a 12-field Binance kline")
    try:
        open_ms, close_time = int(row[0]), int(row[6])
        close_value = float(row[4])
    except (TypeError, ValueError) as exc:
        raise SourceAdapterBlocked("malformed REST kline row") from exc
    if close_time - open_ms != HOUR_MS - 1:
        raise SourceAdapterBlocked("REST kline row is not an exact 1h interval")
    if open_ms % HOUR_MS:
        raise SourceAdapterBlocked("REST kline open time violates hour alignment")
    logical_close = datetime.fromtimestamp((close_time + 1) / 1000, UTC)
    if _hour_ms(logical_close) - HOUR_MS != open_ms or close_time != _hour_ms(logical_close) - 1:
        raise SourceAdapterBlocked("REST kline timestamps do not map to the frozen logical close")
    if logical_close > origin:
        raise SourceAdapterBlocked("open or future REST kline beyond origin boundary")
    if logical_close < first_required_close:
        raise SourceAdapterBlocked("REST kline before first required close")
    if close_value != close_value or close_value in (float("inf"), float("-inf")) or close_value <= 0:
        raise SourceAdapterBlocked("invalid REST close price")
    return recorder.Bar(symbol, logical_close, close_value, tuple(row))


def completed_archive_months(*, first_required_close: datetime, origin: datetime) -> tuple[tuple[int, int], ...]:
    """Calendar months fully before the month containing the due origin."""
    start = (first_required_close - timedelta(hours=1)).astimezone(UTC)
    year, month = start.year, start.month
    result: list[tuple[int, int]] = []
    while (year, month) < (origin.year, origin.month):
        result.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return tuple(result)


def default_fetch_klines(
    *,
    symbol: str,
    start_ms: int,
    end_ms: int,
    interval: str = INTERVAL,
    timeout: float = 30.0,
    opener=urlopen,
) -> list[list[Any]]:
    """Real HTTPS GET against the single admitted USD-M futures endpoint.
    Fails closed on any transport or payload error; no fallback exists."""
    if interval != INTERVAL:
        raise SourceAdapterBlocked("REST interval must be exactly '1h'")
    rows: list[list[Any]] = []
    cursor = start_ms
    while cursor <= end_ms:
        query = urlencode({"symbol": symbol, "interval": INTERVAL, "startTime": cursor, "endTime": end_ms, "limit": 1000})
        request = Request(f"{REST_ENDPOINT}?{query}", headers={"User-Agent": "QntyLab-JH01-SourceAdapter/1"})
        try:
            with opener(request, timeout=timeout) as response:
                if response.status != 200:
                    raise SourceAdapterBlocked(f"Binance REST rejected request: HTTP {response.status}")
                page = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError) as exc:
            raise SourceAdapterBlocked(f"Binance REST transport failure: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise SourceAdapterBlocked("Binance REST returned malformed JSON") from exc
        if not isinstance(page, list):
            raise SourceAdapterBlocked("Binance REST returned non-array payload")
        rows.extend(page)
        if len(page) < 1000:
            break
        last_open = int(page[-1][0])
        if last_open <= cursor - HOUR_MS:
            break
        cursor = last_open + HOUR_MS
    return rows


def default_archive_provider(
    *,
    symbol: str,
    year: int,
    month: int,
    timeout: float = 120.0,
    opener=urlopen,
) -> tuple[bytes, str] | None:
    """Download one authenticated monthly archive plus its published CHECKSUM.
    Returns ``None`` when the archive object is absent (404); any other
    failure fails closed."""
    base = ARCHIVE_ZIP_URL.format(symbol=symbol, year=year, month=month)
    try:
        with opener(Request(base, headers={"User-Agent": "QntyLab-JH01-SourceAdapter/1"}), timeout=timeout) as response:
            if response.status == 404:
                return None
            if response.status != 200:
                raise SourceAdapterBlocked(f"archive download rejected: HTTP {response.status}")
            zip_bytes = response.read()
        with opener(Request(base + ".CHECKSUM", headers={"User-Agent": "QntyLab-JH01-SourceAdapter/1"}), timeout=timeout) as response:
            if response.status != 200:
                raise SourceAdapterBlocked("archive CHECKSUM unavailable")
            checksum_text = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise SourceAdapterBlocked(f"archive transport failure: {exc}") from exc
    return zip_bytes, checksum_text


def materialize_origin_bars(
    *,
    origin: datetime,
    first_required_close: datetime,
    archive_provider: ArchiveProvider | None = None,
    fetch_klines: FetchKlines | None = None,
) -> tuple[recorder.Bar, ...]:
    """Compose authenticated archive bars plus the same-hour REST tail and
    delegate final admission to the frozen ``validate_bars``.

    Composition policy: authenticated archive bars take precedence; REST rows
    mapping to already-archive-covered logical closes are skipped so the
    frozen validator never sees duplicates.  Nothing else is filtered,
    imputed, or normalized.
    """
    archive_provider = archive_provider or default_archive_provider
    fetch_klines = fetch_klines or default_fetch_klines
    panel = frozen_panel()
    start_ms, end_ms = request_bounds(first_required_close=first_required_close, origin=origin)
    hours = (_hour_ms(origin) - _hour_ms(first_required_close)) // HOUR_MS + 1
    all_closes = [first_required_close + timedelta(hours=index) for index in range(hours)]
    months = completed_archive_months(first_required_close=first_required_close, origin=origin)
    combined: list[recorder.Bar] = []
    for symbol in panel:
        covered: set[datetime] = set()
        for year, month in months:
            provided = archive_provider(symbol=symbol, year=year, month=month)
            if provided is None:
                continue
            zip_bytes, checksum_text = provided
            for bar in recorder.bars_from_authenticated_archive(
                symbol=symbol, year=year, month=month, zip_bytes=zip_bytes, checksum_text=checksum_text
            ):
                if bar.logical_close < first_required_close or bar.logical_close > origin:
                    continue  # outside the required window; coverage boundaries stay exact
                combined.append(bar)
                covered.add(bar.logical_close)
        uncovered = [close for close in all_closes if close not in covered]
        if uncovered:
            tail_start_ms = _hour_ms(uncovered[0]) - HOUR_MS
            for row in fetch_klines(symbol=symbol, start_ms=tail_start_ms, end_ms=end_ms, interval=INTERVAL):
                bar = rest_bar_from_row(symbol, row, first_required_close=first_required_close, origin=origin)
                if bar.logical_close in covered:
                    continue  # authenticated archive precedence over the REST tail
                combined.append(bar)
    return recorder.validate_bars(combined, panel=panel, origin=origin, first_required_close=first_required_close)


__all__ = [
    "ARCHIVE_ZIP_URL", "ArchiveProvider", "FetchKlines", "INTERVAL", "REST_ENDPOINT",
    "SourceAdapterBlocked", "completed_archive_months", "default_archive_provider",
    "default_fetch_klines", "frozen_panel", "materialize_origin_bars", "request_bounds",
    "rest_bar_from_row",
]
