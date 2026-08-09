"""Minimal Binance USDⓈ-M public-archive adapter: bytes -> provenance-bound Capture.

Scope is deliberately narrow: construct the deterministic official archive
path, download/read the daily trades ZIP and its published ``.CHECKSUM``,
verify SHA-256 AND the checksum record's own claimed filename, unzip and
parse the one expected CSV with every row structurally validated, and build
a ``qntylab.market_observation.Capture`` of ``MarketObservation`` rows bound
to a caller-supplied, stable ``InstrumentIdentity``.

This module terminates at Capture + MarketObservation. It never touches
``qntylab.lifecycle`` (no ``EvidenceEvent``, no ``state_at``/``eligible_at``
call, no lifecycle claim of any kind). A missing archive is missing
*evidence*, not a NOT_TRADABLE claim: callers get ``None`` and must resolve
that through ``observed_at(None, ...) == UNKNOWN``, exactly as the frozen
MarketObservation fixture already established.

Instrument identity is never inferred from capture-local data. This adapter
does not discover lifecycle identity; it verifies an artifact, parses it,
checks the artifact belongs to a caller-supplied ``InstrumentIdentity``, and
emits evidence for that identity. A capture-local "first trade seen in this
archive" timestamp is not, and must never become, an instrument-instance
identity boundary -- the same continuous instrument parsed from two
different daily archives must yield the same ``instrument_instance_id``.

Fail-closed, no partial-capture semantics: any structural problem (checksum
mismatch, checksum/filename mismatch, unreadable ZIP, malformed CSV,
malformed timestamp, unexpected file layout, invalid symbol, identity
mismatch) raises ``ValueError`` rather than skip bad rows and continue --
consistent with the existing archive-consuming conventions in
``qntylab.data`` / ``qntylab.acquire_v2``.
"""
from __future__ import annotations

import csv
import hashlib
import re
import zipfile
from datetime import UTC, datetime
from io import BytesIO, TextIOWrapper

import requests

from .market_observation import Capture, InstrumentIdentity, MarketObservation

ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/daily/trades"

# Frozen market/contract vocabulary; matches the InstrumentIdentity fields
# already exercised by tests/test_market_observation.py (S1/S2). Do not
# invent a second naming convention.
MARKET = "usd-m"
CONTRACT_TYPE = "perpetual"
VENUE = "binance"

# Binance UM futures daily "trades" archive CSV columns, header-less:
# id, price, qty, quote_qty, time(ms), is_buyer_maker
_EXPECTED_COLUMNS = 6
_TIME_COLUMN = 4

# The one legitimate header row some (older) archives ship, in the exact
# published column order. Only this exact row, and only in position 0, is
# ever treated as a header. Anything else non-numeric is a malformed row.
_EXPECTED_HEADER = ["id", "price", "qty", "quote_qty", "time", "is_buyer_maker"]

# Bare Binance USD-M symbol grammar: non-empty, ASCII, uppercase letters and
# digits only. No normalization -- callers must already supply the canonical
# form. This is not a general URL sanitizer; it is the smallest gate that
# keeps a symbol from being anything other than a single path segment.
_SYMBOL_RE = re.compile(r"^[A-Z0-9]+$")

_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _validate_symbol(symbol: str) -> None:
    if not isinstance(symbol, str) or not _SYMBOL_RE.fullmatch(symbol):
        raise ValueError(f"invalid Binance UM symbol: {symbol!r}")


def archive_paths(symbol: str, date: str) -> dict[str, str]:
    """Deterministic official archive path/filenames for one symbol/date.

    Validates ``symbol`` (bare, uppercase, alphanumeric) before any path
    interpolation -- a rejected symbol never reaches a URL or source key.

    No adaptive discovery: this is a pure string construction from the
    already-established archive layout (``data/futures/um/daily/trades``),
    the same family used by ``qntylab.data.ARCHIVE_URL`` / ``qntylab.archive_index``
    for the monthly-klines case.
    """
    _validate_symbol(symbol)
    filename = f"{symbol}-trades-{date}.zip"
    zip_url = f"{ARCHIVE_BASE}/{symbol}/{filename}"
    return {
        "filename": filename,
        "zip_url": zip_url,
        "checksum_url": zip_url + ".CHECKSUM",
        # Deterministic source_key: the exact official artifact identity.
        # Same archive artifact -> same key; different symbol/date -> different
        # key. Never a mutable local temp path.
        "source_key": f"data/futures/um/daily/trades/{symbol}/{filename}",
    }


def _validate_identity(symbol: str, identity: InstrumentIdentity) -> None:
    """Fail closed unless the caller-supplied identity actually matches this
    request's namespace. No adapter-side identity discovery: the identity is
    trusted only after it agrees exactly with what was asked for."""
    if not isinstance(identity, InstrumentIdentity):
        raise ValueError(f"invalid identity: {identity!r}")
    if identity.symbol != symbol:
        raise ValueError(f"identity symbol {identity.symbol!r} does not match requested symbol {symbol!r}")
    if identity.market != MARKET:
        raise ValueError(f"identity market {identity.market!r} != {MARKET!r}")
    if identity.contract_type != CONTRACT_TYPE:
        raise ValueError(f"identity contract_type {identity.contract_type!r} != {CONTRACT_TYPE!r}")


def _canonical_timestamp(ms: int) -> str:
    """Deterministic UTC ms-epoch -> frozen YYYY-MM-DDTHH:MM:SSZ conversion.

    Truncates to whole seconds (the precision MarketObservation's frozen
    representation can carry). This is a deliberate, analyzed collapse, not a
    silent one: several trades landing in the same second are evidence for
    the same underlying claim -- "was at least one authenticated matching
    market observation present at t" -- so they collapse to one
    MarketObservation for that timestamp (see module docstring / section 14
    of the acquisition-adapter spec). No nearest-second matching, no
    timezone guessing, no tolerance: this is exact floor-to-second
    conversion of an exact source timestamp.
    """
    if not isinstance(ms, int) or ms < 0:
        raise ValueError(f"malformed trade timestamp: {ms!r}")
    whole_seconds = ms // 1000
    try:
        stamp = datetime.fromtimestamp(whole_seconds, UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f"unrepresentable trade timestamp: {ms!r}") from exc
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _verify_checksum(zip_bytes: bytes, checksum_text: str, filename: str, source_key: str) -> str:
    """Verify BOTH halves of authentication: the checksum record's own
    claimed filename must equal the expected archive filename, AND its
    digest must equal the actual downloaded bytes' SHA-256. Either mismatch
    -- or a checksum record that doesn't parse as the official
    ``<hex64>  <filename>`` format -- fails closed.
    """
    fields = checksum_text.strip().split()
    if len(fields) != 2:
        raise ValueError(f"malformed published checksum for {source_key}: {checksum_text!r}")
    expected_digest, recorded_filename = fields
    if not _HEX64_RE.fullmatch(expected_digest):
        raise ValueError(f"malformed checksum digest for {source_key}: {expected_digest!r}")
    recorded_filename = recorded_filename.lstrip("*")  # sha256sum "binary mode" marker, if present
    if recorded_filename != filename:
        raise ValueError(
            f"checksum filename mismatch for {source_key}: expected {filename!r}, got {recorded_filename!r}"
        )
    actual = hashlib.sha256(zip_bytes).hexdigest()
    expected_digest = expected_digest.lower()
    if expected_digest != actual:
        raise ValueError(f"checksum mismatch for {source_key}: expected {expected_digest}, got {actual}")
    return actual


def _parse_trade_rows(zip_bytes: bytes, filename: str) -> list[int]:
    """Unzip, validate EVERY row's structure, and return sorted distinct
    trade times (ms).

    Header handling is strictly positional: only row 0, and only if it is
    exactly the known Binance header, is treated as a header. Every other
    row -- first or not -- must be a structurally valid trade row or parsing
    fails closed with ``ValueError``. No row is silently discarded.
    """
    try:
        archive = zipfile.ZipFile(BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"unreadable ZIP: {filename}") from exc
    with archive:
        names = archive.namelist()
        if len(names) != 1:
            raise ValueError(f"unexpected archive members in {filename}: {names}")
        member = names[0]
        if not member.lower().endswith(".csv"):
            raise ValueError(f"unexpected archive member (not CSV) in {filename}: {member}")
        with archive.open(member) as raw:
            rows = list(csv.reader(TextIOWrapper(raw, encoding="utf-8")))

    if not rows:
        raise ValueError(f"no usable trade rows in {filename}")

    start = 1 if rows[0] == _EXPECTED_HEADER else 0

    times_ms: list[int] = []
    for row in rows[start:]:
        if len(row) != _EXPECTED_COLUMNS:
            raise ValueError(f"malformed trade row (expected {_EXPECTED_COLUMNS} columns) in {filename}: {row}")
        trade_id, raw_time = row[0], row[_TIME_COLUMN]
        if not trade_id.isdigit():
            raise ValueError(f"malformed trade id field in {filename}: {row}")
        if not raw_time.isdigit():
            raise ValueError(f"malformed trade timestamp field in {filename}: {row}")
        times_ms.append(int(raw_time))

    if not times_ms:
        raise ValueError(f"no usable trade rows in {filename}")
    return sorted(times_ms)


def capture_from_bytes(
    symbol: str, date: str, zip_bytes: bytes, checksum_text: str, identity: InstrumentIdentity,
) -> Capture:
    """Pure construction: verified archive bytes + published checksum + a
    caller-supplied stable ``InstrumentIdentity`` -> Capture.

    The adapter never derives instrument-instance identity from this
    capture's own contents (no capture-local "first observed" boundary);
    ``identity`` must be supplied by the caller and is checked for
    coherence with ``symbol``/the frozen usd-m/perpetual vocabulary before
    use. Raises ``ValueError`` (fail-closed, no partial capture) on
    checksum/filename mismatch, unreadable ZIP, malformed CSV, malformed
    timestamps, invalid symbol, or an identity that disagrees with the
    requested symbol/market/contract_type. Never returns an
    invalid/placeholder Capture for a missing archive -- that case is the
    caller's responsibility (``fetch_capture`` returns ``None``).
    """
    paths = archive_paths(symbol, date)
    _validate_identity(symbol, identity)
    source_key = paths["source_key"]
    digest = _verify_checksum(zip_bytes, checksum_text, paths["filename"], source_key)

    times_ms = _parse_trade_rows(zip_bytes, paths["filename"])
    timestamps = sorted({_canonical_timestamp(ms) for ms in times_ms})

    observations = tuple(
        MarketObservation(identity=identity, timestamp=ts, source_key=source_key, local_content_sha256=digest)
        for ts in timestamps
    )
    return Capture(identity=identity, observations=observations, source_key=source_key, local_content_sha256=digest)


def fetch_capture(
    symbol: str, date: str, identity: InstrumentIdentity, session: requests.Session | None = None,
) -> Capture | None:
    """Download the official archive + published checksum and build a Capture
    for the caller-supplied stable ``identity``.

    Bounded network use: at most one archive GET and one checksum GET. If the
    archive artifact is absent (404), returns ``None`` -- missing evidence,
    never a synthesized empty valid Capture and never a NOT_TRADABLE claim.
    Any other structural problem fails closed with ``ValueError``.
    """
    paths = archive_paths(symbol, date)
    _validate_identity(symbol, identity)
    session = session or requests.Session()

    response = session.get(paths["zip_url"], timeout=(10, 90))
    if response.status_code == 404:
        return None
    response.raise_for_status()
    zip_bytes = response.content

    checksum_response = session.get(paths["checksum_url"], timeout=30)
    if checksum_response.status_code == 404:
        # Archive present but its published checksum is not: cannot be admitted
        # as authoritative evidence. Fail closed rather than trust unverified bytes.
        raise ValueError(f"archive present but published checksum missing: {paths['checksum_url']}")
    checksum_response.raise_for_status()

    return capture_from_bytes(symbol, date, zip_bytes, checksum_response.text, identity)
