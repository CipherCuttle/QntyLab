"""First-party Binance USD-M source seam for Order Flow Prospective V1.

Qualification-only. Importing this module performs no network, scheduling,
market-data collection, or persistence action. Pull-request tests inject a
transport and never contact the provider. A manual qualification workflow may
perform one non-scientific connectivity/shape probe on canonical master.

Real prospective collection remains unauthorized until a separate activation
phase binds this source implementation and the already-qualified recorder.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import order_flow_prospective_v1_recorder as recorder


ROOT = Path(__file__).resolve().parents[1]
RECORDER_QUALIFICATION_MERGE_SHA = "5043c4e311980ec7b655be8f93f97b91b845c2ff"
RECORDER_SOURCE_PATH = "qntylab/order_flow_prospective_v1_recorder.py"
RECORDER_RESULT_PATH = (
    "experiments/research/qnty_edge_discovery_order_flow_v1/"
    "recorder_qualification_result.json"
)
EXPECTED_QUALIFICATION_RUN_ID = 34730310188
EXPECTED_RELEASE_ID = 387757083
EXPECTED_ASSET_ID = 560308361
EXPECTED_ASSET_SHA256 = "61878def8d673e38f0417062a43d328c79805cd4883bc9b40875e1b6a41fc8bc"

ENDPOINT_BASE = recorder.ENDPOINT_BASE
ENDPOINT_PATH = recorder.ENDPOINT_PATH
INTERVAL = recorder.INTERVAL
PANEL = recorder.PANEL
RECORDING_WINDOW = recorder.RECORDING_WINDOW


class SourceBlocked(ValueError):
    """The first-party source seam failed closed."""


Fetcher = Callable[..., Sequence[Sequence[Any]]]


def _instant(value: str | datetime) -> datetime:
    try:
        return recorder.parse_utc(value)
    except (ValueError, recorder.RecorderBlocked) as exc:
        raise SourceBlocked(str(exc)) from exc


def _hour(value: str | datetime) -> datetime:
    try:
        return recorder.hour(value)
    except recorder.RecorderBlocked as exc:
        raise SourceBlocked(str(exc)) from exc


def _stamp(value: str | datetime) -> str:
    return _instant(value).isoformat().replace("+00:00", "Z")


def validate_recorder_qualification(root: Path = ROOT) -> dict[str, Any]:
    """Bind this seam to the exact qualified recorder and PASS receipt."""
    recorder_path = root / RECORDER_SOURCE_PATH
    result_path = root / RECORDER_RESULT_PATH
    if not recorder_path.is_file() or not result_path.is_file():
        raise SourceBlocked("qualified recorder source/result is missing")
    try:
        committed_recorder = subprocess.check_output(
            ["git", "show", f"{RECORDER_QUALIFICATION_MERGE_SHA}:{RECORDER_SOURCE_PATH}"],
            cwd=root,
        )
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", RECORDER_QUALIFICATION_MERGE_SHA, "HEAD"],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SourceBlocked("qualified recorder Git lineage unavailable") from exc
    if committed_recorder != recorder_path.read_bytes():
        raise SourceBlocked("recorder source differs from canonical qualification merge")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceBlocked("recorder qualification result is malformed") from exc
    expected = {
        "state": "PASS",
        "scientific_evidence": False,
        "authority": "NONE",
        "recorder_qualification_merge_sha": RECORDER_QUALIFICATION_MERGE_SHA,
    }
    for key, value in expected.items():
        if result.get(key) != value:
            raise SourceBlocked(f"recorder qualification result mismatch: {key}")
    run = result.get("workflow_run") or {}
    release = result.get("immutable_release") or {}
    acceptance = result.get("acceptance") or {}
    if run.get("id") != EXPECTED_QUALIFICATION_RUN_ID or run.get("conclusion") != "success":
        raise SourceBlocked("recorder qualification workflow result mismatch")
    if run.get("head_sha") != RECORDER_QUALIFICATION_MERGE_SHA:
        raise SourceBlocked("recorder qualification head SHA mismatch")
    if release.get("id") != EXPECTED_RELEASE_ID or release.get("asset_id") != EXPECTED_ASSET_ID:
        raise SourceBlocked("recorder qualification release identity mismatch")
    if release.get("asset_sha256") != EXPECTED_ASSET_SHA256:
        raise SourceBlocked("recorder qualification asset digest mismatch")
    if release.get("immutable") is not True or release.get("draft") is not False:
        raise SourceBlocked("recorder qualification release is not immutable")
    required_acceptance = {
        "immutable_true": "PASS",
        "asset_digest_matches_staged_ledger": "PASS",
        "immutable_delete_denied_for_policy_reason": "PASS",
        "independent_read_only_restore": "PASS",
        "restored_bytes_equal_staged_bytes": "PASS",
    }
    for key, value in required_acceptance.items():
        if acceptance.get(key) != value:
            raise SourceBlocked(f"recorder qualification acceptance mismatch: {key}")
    return {
        "recorder_merge_sha": RECORDER_QUALIFICATION_MERGE_SHA,
        "recorder_sha256": sha256(committed_recorder).hexdigest(),
        "qualification_run_id": EXPECTED_QUALIFICATION_RUN_ID,
        "qualification_asset_sha256": EXPECTED_ASSET_SHA256,
    }


def request_spec(logical_close: str | datetime, *, symbol: str) -> dict[str, Any]:
    """Build the exact first-party one-hour request without scientific admission."""
    close = _hour(logical_close)
    if symbol not in PANEL:
        raise SourceBlocked(f"non-panel symbol rejected: {symbol}")
    provider_open = close - timedelta(hours=1)
    return {
        "endpoint_base": ENDPOINT_BASE,
        "endpoint_path": ENDPOINT_PATH,
        "params": {
            "symbol": symbol,
            "interval": INTERVAL,
            "startTime": int(provider_open.timestamp() * 1000),
            "endTime": int(close.timestamp() * 1000) - 1,
            "limit": 1,
        },
    }


def default_fetch_one(
    *,
    symbol: str,
    logical_close: str | datetime,
    timeout: float = 30.0,
    opener=urlopen,
) -> list[list[Any]]:
    """Fetch exactly one requested first-party USD-M kline response page."""
    spec = request_spec(logical_close, symbol=symbol)
    query = urlencode(spec["params"])
    request = Request(
        f"{spec['endpoint_base']}{spec['endpoint_path']}?{query}",
        headers={"User-Agent": "QntyLab-OrderFlow-Prospective-V1-SourceQualification/1"},
    )
    try:
        with opener(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            if status != 200:
                raise SourceBlocked(f"Binance USD-M REST rejected request: HTTP {status}")
            payload = json.loads(response.read())
    except SourceBlocked:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise SourceBlocked(f"Binance USD-M REST transport failure: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SourceBlocked("Binance USD-M REST returned malformed JSON") from exc
    if not isinstance(payload, list):
        raise SourceBlocked("Binance USD-M REST returned non-array payload")
    if len(payload) != 1:
        raise SourceBlocked("exact-hour source must return exactly one kline row")
    row = payload[0]
    if not isinstance(row, list) or len(row) != 12:
        raise SourceBlocked("provider kline row must contain exactly 12 fields")
    return payload


def validate_probe_row(
    *, symbol: str, logical_close: str | datetime, raw_row: Sequence[Any]
) -> dict[str, str]:
    """Validate only transport shape/timestamps; never expose price/volume values."""
    close = _hour(logical_close)
    if symbol not in PANEL:
        raise SourceBlocked(f"non-panel symbol rejected: {symbol}")
    if len(raw_row) != 12:
        raise SourceBlocked("provider kline row must contain exactly 12 fields")
    expected_open = int((close - timedelta(hours=1)).timestamp() * 1000)
    expected_close = int(close.timestamp() * 1000) - 1
    try:
        provider_open = int(raw_row[0])
        provider_close = int(raw_row[6])
    except (TypeError, ValueError, IndexError) as exc:
        raise SourceBlocked("provider timestamps are malformed") from exc
    if provider_open != expected_open or provider_close != expected_close:
        raise SourceBlocked("provider row timestamp identity mismatch")
    return {"symbol": symbol, "logical_close_utc": _stamp(close), "status": "SHAPE_TIMESTAMP_PASS"}


def fetch_scientific_batch(
    *,
    logical_close: str | datetime,
    observed_at: str | datetime,
    fetcher: Fetcher | None = None,
) -> dict[str, list[Any]]:
    """Fetch one frozen five-symbol scientific batch inside its one-hour window."""
    validate_recorder_qualification()
    close = _hour(logical_close)
    try:
        recorder.classify_logical_close(close)
    except recorder.RecorderBlocked as exc:
        raise SourceBlocked(str(exc)) from exc
    observed = _instant(observed_at)
    if observed < close:
        raise SourceBlocked("scientific source fetch attempted before logical close")
    if observed >= close + RECORDING_WINDOW:
        raise SourceBlocked("scientific recording window missed; provider fetch forbidden")
    fetcher = fetcher or default_fetch_one
    rows: dict[str, list[Any]] = {}
    for symbol in PANEL:
        payload = list(fetcher(symbol=symbol, logical_close=close))
        if len(payload) != 1:
            raise SourceBlocked(f"exact-hour source must return exactly one row for {symbol}")
        row = list(payload[0])
        validate_probe_row(symbol=symbol, logical_close=close, raw_row=row)
        rows[symbol] = row
    try:
        recorder.normalize_batch(logical_close=close, rows=rows, observed_at=observed)
    except recorder.RecorderBlocked as exc:
        raise SourceBlocked(f"scientific source batch rejected: {exc}") from exc
    return rows


def stage_due_hour(
    ledger: recorder.EvidenceLedger,
    *,
    logical_close: str | datetime,
    observed_at: str | datetime,
    fetcher: Fetcher | None = None,
) -> dict[str, Any]:
    """Stage the exact hour or mark it missed; late hours never contact provider."""
    close = _hour(logical_close)
    observed = _instant(observed_at)
    try:
        recorder.classify_logical_close(close)
    except recorder.RecorderBlocked as exc:
        raise SourceBlocked(str(exc)) from exc
    if observed < close:
        raise SourceBlocked("scientific hour is not complete")
    if observed >= close + RECORDING_WINDOW:
        try:
            return ledger.mark_missed(logical_close=close, detected_at=observed)
        except recorder.RecorderBlocked as exc:
            raise SourceBlocked(str(exc)) from exc
    rows = fetch_scientific_batch(
        logical_close=close,
        observed_at=observed,
        fetcher=fetcher,
    )
    try:
        return ledger.record_batch(logical_close=close, rows=rows, observed_at=observed)
    except recorder.RecorderBlocked as exc:
        raise SourceBlocked(str(exc)) from exc


def latest_completed_logical_close(as_of: str | datetime) -> datetime:
    now = _instant(as_of)
    return now.replace(minute=0, second=0, microsecond=0)


def run_non_scientific_live_probe(
    *, as_of: str | datetime | None = None, fetcher: Fetcher | None = None
) -> dict[str, Any]:
    """Probe current provider connectivity/shape without retaining scientific values."""
    validate_recorder_qualification()
    now = datetime.now(UTC) if as_of is None else _instant(as_of)
    close = latest_completed_logical_close(now)
    fetcher = fetcher or default_fetch_one
    results: list[dict[str, str]] = []
    for symbol in PANEL:
        payload = list(fetcher(symbol=symbol, logical_close=close))
        if len(payload) != 1:
            raise SourceBlocked(f"live probe expected exactly one row for {symbol}")
        results.append(validate_probe_row(symbol=symbol, logical_close=close, raw_row=payload[0]))
    return {
        "mode": "NON_SCIENTIFIC_SOURCE_QUALIFICATION",
        "scientific_evidence": False,
        "logical_close_utc": _stamp(close),
        "symbol_count": len(results),
        "symbols": [result["symbol"] for result in results],
        "status": "PASS",
    }
