"""Outcome-free Breadth V2 development-input census coordinator.

This module is deliberately an orchestration boundary.  It enumerates the
frozen registered plan, collapses the two cost modes onto one market-input
unit, derives the exact profile-specific history, and delegates READY bundle
construction to :func:`build_breadth_v2_input_bundle`.  It never calls the
runner, portfolio kernel, strategy functions, or ledger writers.
"""
from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import requests

from .breadth_v2_input_bundle import InputBundleBlocked, build_breadth_v2_input_bundle, required_history_for_variant
from .binance_um_funding_settlement import (
    REST_ENDPOINT,
    _parse_rest_page,
    materialize_from_objects as materialize_funding_from_objects,
    months as funding_months,
    rest_query,
)
from .binance_um_kline_1h import materialize_from_objects as materialize_price_from_objects, months as price_months
from .binance_um_funding_settlement import archive_paths as funding_archive_paths
from .binance_um_kline_1h import archive_paths as price_archive_paths
from .breadth_v2_runner import (
    COST_MODES,
    FROZEN_PANEL_ORDER,
    PANEL_EXECUTION_UNIT_ID,
    REGISTERED_PERIODS,
    REGISTERED_SCREEN_ID,
    SINGLE_ASSET,
    SYNCHRONIZED_PANEL,
    enumerate_registered_execution_plan,
    resolve_candidate,
    scientific_cell_count,
)

CONTRACT = "BREADTH_V2_DEV_INPUT_MATERIALIZATION_V0"
FREEZE_T0 = "2026-08-10T19:00:00Z"
TRANSPORT_RETRY_POLICY = "TRANSPORT_RETRY_POLICY_V0"
MAX_TRANSIENT_ATTEMPTS = 3
TRANSIENT_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
BLOCKED_SOURCE_STATUSES = frozenset({"SOURCE_OBJECT_ABSENT", "BLOCKED_PRICE_COVERAGE", "BLOCKED_FUNDING_COVERAGE", "BLOCKED_FUNDING_WARMUP", "BLOCKED_PROVENANCE", "BLOCKED_FIXED_PANEL_INPUT", "BLOCKED_PANEL_COVERAGE"})


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def price_clip_range(period_id: str, required_price_closes: int) -> tuple[str, str]:
    """Return the frozen source-open clip ``[T0-Nh, T1-1h]`` inclusive."""
    start, end = REGISTERED_PERIODS[period_id]
    t0 = datetime.fromisoformat(start.replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(end.replace("Z", "+00:00"))
    return (
        (t0 - timedelta(hours=int(required_price_closes))).isoformat().replace("+00:00", "Z"),
        (t1 - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
    )


def funding_parent_start(period_id: str) -> str:
    """Minimum ordinary-funding source start, one hour before evaluation T0."""
    start, _ = REGISTERED_PERIODS[period_id]
    t0 = datetime.fromisoformat(start.replace("Z", "+00:00"))
    return (t0 - timedelta(hours=1)).isoformat().replace("+00:00", "Z")


def classify_transport(*, status_code: int | None = None, error: BaseException | None = None) -> str:
    """Classify an unresolved request without turning transport into absence."""
    if status_code in TRANSIENT_HTTP_STATUSES or error is not None:
        return "ACQUISITION_UNRESOLVED"
    if status_code == 404:
        return "SOURCE_OBJECT_ABSENT"
    return "ACQUISITION_UNRESOLVED"


@dataclass(frozen=True)
class MarketInputKey:
    variant_id: str
    candidate_id: str
    family_id: str
    execution_unit_type: str
    execution_unit_id: str
    period_id: str


def enumerate_market_input_plan(candidates_path: str = "experiments/research/candidates.jsonl") -> list[MarketInputKey]:
    """Collapse BASELINE/STRESS descriptors into unique market-input units."""
    descriptors = enumerate_registered_execution_plan(candidates_path)
    grouped: dict[MarketInputKey, set[str]] = {}
    for descriptor in descriptors:
        key = MarketInputKey(
            descriptor.variant_id,
            resolve_candidate(descriptor.variant_id, candidates_path)["candidate_id"],
            descriptor.family_id,
            descriptor.execution_unit_type,
            descriptor.execution_unit_id,
            descriptor.period_id,
        )
        grouped.setdefault(key, set()).add(descriptor.cost_mode)
    if len(grouped) != 996 or any(modes != set(COST_MODES) for modes in grouped.values()):
        raise ValueError("registered plan did not collapse to 996 complete two-cost-mode input units")
    return sorted(grouped, key=lambda key: (key.family_id, key.variant_id, key.execution_unit_type, key.execution_unit_id, key.period_id))


def _symbol_evidence(bundle: Mapping[str, Any], symbol: str, price_sources: Mapping[str, Mapping[str, Any]], funding_sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    asset = bundle["bundle_payload"]["assets"][symbol]
    funding_manifest = funding_sources[symbol].get("manifest", {})
    return {
        "price_parent_normalized_sha256": asset["price_parent_content"],
        "price_provenance_digest": asset["price_provenance"],
        "funding_parent_normalized_sha256": asset["funding_parent_content"],
        "funding_archive_provenance_digest": asset["funding_provenance"],
        "funding_rest_witness_digest": funding_manifest.get("rest_coverage_witness_digest"),
        "funding_reconciliation_digest": funding_manifest.get("coverage_reconciliation_digest"),
        "coverage_status": asset["coverage"],
    }


def materialize_market_input(key: MarketInputKey, *, price_sources: Mapping[str, Mapping[str, Any]], funding_sources: Mapping[str, Mapping[str, Any]], candidates_path: str = "experiments/research/candidates.jsonl") -> dict[str, Any]:
    """Build one census row, with no strategy execution or outcome fields."""
    candidate = resolve_candidate(key.variant_id, candidates_path)
    history = required_history_for_variant(key.family_id, candidate["parameters"])
    start, end = REGISTERED_PERIODS[key.period_id]
    symbols = [key.execution_unit_id] if key.execution_unit_type == SINGLE_ASSET else list(FROZEN_PANEL_ORDER)
    base = {**asdict(key), "mapped_cost_modes": sorted(COST_MODES), "required_price_closes": history["required_price_closes"], "required_funding_signal_events": history["required_funding_signal_events"], "price_source_range": list(price_clip_range(key.period_id, history["required_price_closes"])), "funding_source_range": [funding_parent_start(key.period_id), end], "status": "BLOCKED", "evaluation_input_bundle_sha256": None, "blocking_reason": None, "blocking_details": None, "per_symbol_evidence_summary": {}}
    try:
        bundle = build_breadth_v2_input_bundle(evaluation_start=start, evaluation_end=end, symbols=symbols, price_sources=price_sources, funding_sources=funding_sources, family=key.family_id, parameters=candidate["parameters"])
    except InputBundleBlocked as exc:
        base["blocking_reason"], base["blocking_details"] = exc.status, str(exc)
        return base
    base.update({"status": "READY", "evaluation_input_bundle_sha256": bundle["evaluation_input_bundle_sha256"], "per_symbol_evidence_summary": {symbol: _symbol_evidence(bundle, symbol, price_sources, funding_sources) for symbol in symbols}})
    return base


def build_census(rows: Sequence[Mapping[str, Any]], *, freeze_commit: str, candidates_path: str = "experiments/research/candidates.jsonl") -> dict[str, Any]:
    """Build deterministic global counts and the content-addressed census."""
    ordered = sorted((dict(row) for row in rows), key=lambda row: tuple(row[name] for name in ("family_id", "variant_id", "execution_unit_type", "execution_unit_id", "period_id")))
    if len(ordered) != 996 or len({(row["variant_id"], row["execution_unit_type"], row["execution_unit_id"], row["period_id"]) for row in ordered}) != 996:
        raise ValueError("census must contain exactly 996 unique input records")
    if any(row["status"] == "READY" and not row.get("evaluation_input_bundle_sha256") for row in ordered):
        raise ValueError("READY census row lacks bundle identity")
    if any(row["status"] == "BLOCKED" and row.get("evaluation_input_bundle_sha256") is not None for row in ordered):
        raise ValueError("BLOCKED census row has fabricated bundle identity")
    ready = sum(row["status"] == "READY" for row in ordered)
    mapped_exec = ready * 2
    blocked_exec = (996 - ready) * 2
    ready_cells = sum(1 if row["execution_unit_type"] == SINGLE_ASSET else len(FROZEN_PANEL_ORDER) for row in ordered if row["status"] == "READY")
    blocked_cells = scientific_cell_count() - ready_cells
    reason_counts = {}
    for row in ordered:
        if row["status"] == "BLOCKED":
            reason = row.get("blocking_reason") or "BLOCKED_UNCLASSIFIED"
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    manifest = {"contract": CONTRACT, "registered_screen_id": REGISTERED_SCREEN_ID, "instrument_contract_id": "BINANCE_USDM_PERPETUAL_USDT_V1", "pre_acquisition_freeze_commit": freeze_commit, "sealed_t0": FREEZE_T0, "registered_input_records": 996, "registered_execution_units": 1992, "registered_scientific_cells": 3360, "ready_input_records": ready, "blocked_input_records": 996 - ready, "ready_mapped_execution_units": mapped_exec, "blocked_mapped_execution_units": blocked_exec, "ready_mapped_scientific_cells": ready_cells, "blocked_mapped_scientific_cells": blocked_cells, "blocking_reason_counts": dict(sorted(reason_counts.items())), "acquisition_unresolved_count": sum(row.get("blocking_reason") == "ACQUISITION_UNRESOLVED" for row in ordered), "input_records": ordered}
    manifest["campaign_input_universe_sha256"] = _sha({key: value for key, value in manifest.items() if key != "campaign_input_universe_sha256"})
    return manifest


class AcquisitionUnresolved(RuntimeError):
    """A transport failure after the bounded request retry policy."""


class EvidenceCache:
    """Content-addressed, append-only cache for authenticated source bytes."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.objects = self.root / "objects"
        self.requests = self.root / "requests"
        self.objects.mkdir(parents=True, exist_ok=True)
        self.requests.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(value: Any) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _request_path(self, request: Any) -> Path:
        return self.requests / f"{self._key(request)}.json"

    def _put(self, data: bytes, suffix: str) -> str:
        digest = hashlib.sha256(data).hexdigest()
        path = self.objects / f"{digest}{suffix}"
        if not path.exists():
            path.write_bytes(data)
        return digest

    def get(self, request: Any) -> dict[str, Any] | None:
        path = self._request_path(request)
        return json.loads(path.read_text()) if path.exists() else None

    def put(self, request: Any, *, status: str, data: bytes | None = None, suffix: str = ".bin", metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        result = {"request": request, "status": status, **(dict(metadata or {}))}
        if data is not None:
            result.update({"sha256": self._put(data, suffix), "byte_count": len(data)})
        path = self._request_path(request)
        if not path.exists() or (json.loads(path.read_text()).get("status") == "ACQUISITION_UNRESOLVED" and status != "ACQUISITION_UNRESOLVED"):
            path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        return json.loads(path.read_text())

    def bytes_for(self, record: Mapping[str, Any]) -> bytes | None:
        digest = record.get("sha256")
        if not digest:
            return None
        suffix = record.get("suffix", ".bin")
        path = self.objects / f"{digest}{suffix}"
        return path.read_bytes() if path.exists() else None


def _request_bytes(session: requests.Session, url: str, *, params: Mapping[str, Any] | None = None, attempts: int = MAX_TRANSIENT_ATTEMPTS) -> tuple[str, bytes | None, int | None]:
    last_error: BaseException | None = None
    for attempt in range(attempts):
        try:
            response = session.get(url, params=params, timeout=(10, 90))
            if response.status_code == 404:
                return "SOURCE_OBJECT_ABSENT", None, 404
            if response.status_code in TRANSIENT_HTTP_STATUSES:
                last_error = requests.HTTPError(f"transient HTTP {response.status_code}")
            elif response.status_code >= 400:
                return "ACQUISITION_UNRESOLVED", None, response.status_code
            else:
                return "AVAILABLE", bytes(response.content), response.status_code
        except requests.RequestException as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(min(2 ** attempt, 4))
    raise AcquisitionUnresolved(str(last_error or "request failed"))


def _cached_request(cache: EvidenceCache, session: requests.Session, request: Mapping[str, Any], *, suffix: str, attempts: int = MAX_TRANSIENT_ATTEMPTS, retry_unresolved: bool = False) -> tuple[dict[str, Any], bytes | None]:
    prior = cache.get(request)
    if prior and prior.get("status") in {"AVAILABLE", "SOURCE_OBJECT_ABSENT"}:
        return prior, cache.bytes_for(prior)
    if prior and prior.get("status") == "ACQUISITION_UNRESOLVED" and not retry_unresolved:
        return prior, None
    try:
        status, data, code = _request_bytes(session, request["url"], params=request.get("params"), attempts=attempts)
    except AcquisitionUnresolved as exc:
        return cache.put(request, status="ACQUISITION_UNRESOLVED", metadata={"error": str(exc)}), None
    return cache.put(request, status=status, data=data, suffix=suffix, metadata={"http_status": code, "suffix": suffix}), data


def _source_envelope(keys: Sequence[MarketInputKey], candidates_path: str) -> tuple[dict[str, tuple[str, str]], dict[str, tuple[str, str]]]:
    price: dict[str, list[datetime]] = {}
    funding: dict[str, list[datetime]] = {}
    max_funding_days = 180
    for key in keys:
        candidate = resolve_candidate(key.variant_id, candidates_path)
        history = required_history_for_variant(key.family_id, candidate["parameters"])
        period_start, period_end = REGISTERED_PERIODS[key.period_id]
        start = datetime.fromisoformat(period_start.replace("Z", "+00:00"))
        end = datetime.fromisoformat(period_end.replace("Z", "+00:00"))
        symbols = [key.execution_unit_id] if key.execution_unit_type == SINGLE_ASSET else list(FROZEN_PANEL_ORDER)
        for symbol in symbols:
            price.setdefault(symbol, []).extend([start - timedelta(hours=history["required_price_closes"]), end - timedelta(hours=1)])
            funding.setdefault(symbol, []).extend([start - timedelta(days=max_funding_days), end])
    to_range = lambda values: (min(values).isoformat().replace("+00:00", "Z"), max(values).isoformat().replace("+00:00", "Z"))
    return {symbol: to_range(values) for symbol, values in price.items()}, {symbol: to_range(values) for symbol, values in funding.items()}


def _acquire_monthly(cache: EvidenceCache, session: requests.Session, symbol: str, start: str, end: str, *, funding: bool, retry_unresolved: bool) -> tuple[dict[tuple[int, int], tuple[bytes | None, bytes | None]], list[dict[str, Any]]]:
    month_fn = funding_months if funding else price_months
    path_fn = funding_archive_paths if funding else price_archive_paths
    objects: dict[tuple[int, int], tuple[bytes | None, bytes | None]] = {}
    unresolved: list[dict[str, Any]] = []
    for year, month in month_fn(start, end):
        paths = path_fn(symbol, year, month)
        zip_request = {"kind": "funding_zip" if funding else "price_zip", "url": paths["zip_url"], "source_key": paths["source_key"]}
        zip_record, zip_bytes = _cached_request(cache, session, zip_request, suffix=".zip", retry_unresolved=retry_unresolved)
        if zip_record["status"] == "ACQUISITION_UNRESOLVED":
            unresolved.append(zip_record)
        checksum_bytes = None
        if zip_bytes is not None:
            checksum_request = {"kind": "funding_checksum" if funding else "price_checksum", "url": paths["checksum_url"], "source_key": paths["source_key"] + ".CHECKSUM"}
            checksum_record, checksum_bytes = _cached_request(cache, session, checksum_request, suffix=".CHECKSUM", retry_unresolved=retry_unresolved)
            if checksum_record["status"] == "ACQUISITION_UNRESOLVED":
                unresolved.append(checksum_record)
        objects[(year, month)] = (zip_bytes, checksum_bytes if funding or checksum_bytes is None else checksum_bytes.decode("utf-8"))
    return objects, unresolved


def _acquire_funding_witness(cache: EvidenceCache, session: requests.Session, symbol: str, start: str, end: str, *, retry_unresolved: bool) -> tuple[list[bytes] | None, list[dict[str, Any]]]:
    query = rest_query(symbol, start, end)
    pages: list[bytes] = []
    unresolved: list[dict[str, Any]] = []
    next_start = int(query["startTime"])
    while True:
        params = {**query, "startTime": next_start}
        request = {"kind": "funding_rest", "url": REST_ENDPOINT, "params": params}
        record, raw = _cached_request(cache, session, request, suffix=".json", retry_unresolved=retry_unresolved)
        if record["status"] != "AVAILABLE" or raw is None:
            if record["status"] == "ACQUISITION_UNRESOLVED": unresolved.append(record)
            return None, unresolved
        pages.append(raw)
        _, rows = _parse_rest_page(raw, symbol)
        if not rows or rows[-1][0] >= int(query["endTime"]) or len(rows) < 1000:
            break
        next_start = rows[-1][0]
    return pages, unresolved


def _acquire_symbol(cache: EvidenceCache, symbol: str, price_range: tuple[str, str], funding_range: tuple[str, str], *, retry_unresolved: bool, session: requests.Session | None = None) -> tuple[str, dict[tuple[int, int], tuple[bytes | None, bytes | str | None]], dict[tuple[int, int], tuple[bytes | None, bytes | str | None]], list[bytes] | None, list[dict[str, Any]]]:
    client = session or requests.Session()
    price_objects, price_errors = _acquire_monthly(cache, client, symbol, *price_range, funding=False, retry_unresolved=retry_unresolved)
    funding_objects, funding_errors = _acquire_monthly(cache, client, symbol, *funding_range, funding=True, retry_unresolved=retry_unresolved)
    witness, witness_errors = _acquire_funding_witness(cache, client, symbol, *funding_range, retry_unresolved=retry_unresolved)
    return symbol, price_objects, funding_objects, witness, price_errors + funding_errors + witness_errors


def _clip_witness_pages(pages: list[bytes] | None, symbol: str, start: str, end: str) -> list[bytes] | None:
    if pages is None:
        return None
    start_ms = int(datetime.fromisoformat(start.replace("Z", "+00:00")).timestamp() * 1000)
    end_ms = int(datetime.fromisoformat(end.replace("Z", "+00:00")).timestamp() * 1000)
    rows_by_time: dict[int, dict[str, Any]] = {}
    for page in pages:
        payload = json.loads(page)
        for row in payload:
            if start_ms <= row.get("fundingTime", -1) <= end_ms:
                rows_by_time[row["fundingTime"]] = row
    rows = [rows_by_time[key] for key in sorted(rows_by_time)]
    return [json.dumps(rows, ensure_ascii=True, separators=(",", ":")).encode("utf-8")]


def run_dev_input_acquisition(*, evidence_root: str | Path = "/home/swirky/DevHub/qntylab-evidence/breadth_v2_dev_inputs_v0", candidates_path: str = "experiments/research/candidates.jsonl", freeze_commit: str = "2608676b1d353446b00409c63a32b4b6a362c38e", input_keys: Sequence[MarketInputKey] | None = None, session: requests.Session | None = None) -> dict[str, Any]:
    """Acquire, cache, materialize, and census frozen development inputs only."""
    keys = list(input_keys) if input_keys is not None else enumerate_market_input_plan(candidates_path)
    cache = EvidenceCache(Path(evidence_root))
    client = session or requests.Session()
    price_ranges, funding_ranges = _source_envelope(keys, candidates_path)
    price_sources: dict[str, dict[str, Any]] = {}
    funding_sources: dict[str, dict[str, Any]] = {}
    source_objects: dict[str, tuple[dict[tuple[int, int], tuple[bytes | None, bytes | str | None]], dict[tuple[int, int], tuple[bytes | None, bytes | str | None]], list[bytes] | None]] = {}
    unresolved: list[dict[str, Any]] = []
    for retry_pass in (False, True):
        unresolved = []
        with ThreadPoolExecutor(max_workers=min(8, len(price_ranges))) as pool:
            futures = [pool.submit(_acquire_symbol, cache, symbol, price_ranges[symbol], funding_ranges[symbol], retry_unresolved=retry_pass, session=client if len(price_ranges) == 1 else None) for symbol in sorted(price_ranges)]
            for future in as_completed(futures):
                symbol, price_objects, funding_objects, witness, errors = future.result()
                source_objects[symbol] = (price_objects, funding_objects, witness)
                unresolved.extend(errors)
        if not unresolved:
            break
    if unresolved:
        raise AcquisitionUnresolved(f"{len(unresolved)} source requests remain unresolved after one targeted retry pass")
    price_materializations: dict[tuple[str, str, str], dict[str, Any]] = {}
    funding_materializations: dict[tuple[str, str, str], dict[str, Any]] = {}
    rows = []
    for key in keys:
        candidate = resolve_candidate(key.variant_id, candidates_path)
        history = required_history_for_variant(key.family_id, candidate["parameters"])
        period_start, period_end = REGISTERED_PERIODS[key.period_id]
        symbols = [key.execution_unit_id] if key.execution_unit_type == SINGLE_ASSET else list(FROZEN_PANEL_ORDER)
        for symbol in symbols:
            price_start, price_end = price_clip_range(key.period_id, history["required_price_closes"])
            price_key = (symbol, price_start, price_end)
            if price_key not in price_materializations:
                objects = source_objects[symbol][0]
                price_materializations[price_key] = materialize_price_from_objects(symbol, price_start, price_end, objects, retrieval_generation_identity=CONTRACT)
            funding_start = (datetime.fromisoformat(period_start.replace("Z", "+00:00")) - timedelta(days=180)).isoformat().replace("+00:00", "Z")
            funding_key = (symbol, funding_start, period_end)
            if funding_key not in funding_materializations:
                objects, witness = source_objects[symbol][1], source_objects[symbol][2]
                funding_materializations[funding_key] = materialize_funding_from_objects(symbol, funding_start, period_end, objects, retrieval_generation_identity=CONTRACT, rest_witness_pages=_clip_witness_pages(witness, symbol, funding_start, period_end))
        rows.append(materialize_market_input(key, price_sources={symbol: price_materializations[(symbol, *price_clip_range(key.period_id, history["required_price_closes"]))] for symbol in symbols}, funding_sources={symbol: funding_materializations[(symbol, (datetime.fromisoformat(period_start.replace("Z", "+00:00")) - timedelta(days=180)).isoformat().replace("+00:00", "Z"), period_end)] for symbol in symbols}, candidates_path=candidates_path))
    result: dict[str, Any] = {"contract": CONTRACT, "evidence_root": str(Path(evidence_root)), "source_request_counts": {"price": len(price_ranges), "funding": len(funding_ranges)}, "input_records": rows}
    if len(rows) == 996:
        result["census"] = build_census(rows, freeze_commit=freeze_commit, candidates_path=candidates_path)
        output = Path(evidence_root) / "manifests"
        output.mkdir(parents=True, exist_ok=True)
        (output / "BREADTH_V2_DEV_INPUT_UNIVERSE_V0.json").write_text(json.dumps(result["census"], sort_keys=True, indent=2) + "\n")
    return result
