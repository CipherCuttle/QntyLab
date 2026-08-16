"""Bounded, outcome-free materialization for Order Flow V0.

This phase binds only the frozen Binance USD-M source inputs.  It deliberately
does not calculate the feature, positions, returns, funding PnL, or any
scientific result.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from . import binance_um_funding_settlement as funding
from . import binance_um_kline_1h as kline
from .market_observation import InstrumentIdentity

PROJECT_ID = "QNTY_EDGE_DISCOVERY_ORDER_FLOW_V0_INPUT_MATERIALIZATION_V0"
AUTH_PROJECT_ID = "QNTY_EDGE_DISCOVERY_ORDER_FLOW_V0_INPUT_MATERIALIZATION_AUTHORIZATION_V0"
ROOT_REL = Path("experiments/research/qnty_edge_discovery_order_flow_v0/materialization/v0")
AUTH_REL = ROOT_REL / "input_materialization_authorization.json"
PREREG_REL = Path("experiments/specs/qnty_edge_discovery_order_flow_v0_preregistration.json")
UNIVERSE = (
    "BCHUSDT", "XRPUSDT", "LTCUSDT", "TRXUSDT", "ETCUSDT", "LINKUSDT",
    "XLMUSDT", "CHZUSDT", "SANDUSDT", "REEFUSDT", "CHRUSDT", "ALICEUSDT",
    "ONEUSDT", "API3USDT", "GMTUSDT", "APEUSDT", "OPUSDT", "INJUSDT",
    "LDOUSDT", "APTUSDT",
)
PERIODS = ("DEV_2022", "DEV_2024", "DEV_2025")
REQUIRED_FIELDS = set(kline.FIELDS)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def stamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_stamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def identity(symbol: str) -> InstrumentIdentity:
    return InstrumentIdentity(symbol, "usd-m", "perpetual", f"binance|{symbol}|perpetual|usd-m|order-flow-v0")


def git_rev(root: Path, ref: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", ref], text=True).strip()


def derive_windows(prereg: dict[str, Any]) -> dict[str, dict[str, str]]:
    blocks = prereg["temporal_design"]["fixed_chronological_blocks"]
    result: dict[str, dict[str, str]] = {}
    for block in blocks:
        start = parse_stamp(block["start"])
        end = parse_stamp(block["end"])
        result[block["id"]] = {
            "period_start": stamp(start),
            "period_end": stamp(end),
            "price_start": stamp(start - timedelta(hours=26)),
            "price_end": stamp(end + timedelta(hours=1)),
            "funding_start": stamp(start),
            "funding_end": stamp(end + timedelta(hours=1)),
            "price_derivation": "period start - 26h through period end + 1h: 24-bar median history, lagged source bar, target open, and terminal next-open tail",
            "funding_derivation": "period start through period end + 1h, inclusive event-time settlement obligation",
        }
    if tuple(result) != PERIODS:
        raise ValueError("frozen temporal block order changed")
    return result


def verify_authority(root: Path, auth: dict[str, Any], prereg: dict[str, Any]) -> None:
    if auth["project_id"] != AUTH_PROJECT_ID or auth["state"] != "CLOSED_PASS":
        raise ValueError("AUTHORIZATION_STATE_INVALID")
    later = auth["later_phase"]
    if later["project_id"] != PROJECT_ID or later["later_materialization_phase_authorized"] is not True:
        raise ValueError("LATER_PHASE_AUTHORIZATION_INVALID")
    if any(later[key] for key in ("implementation_authorized", "scientific_execution_authorized", "historical_outcome_access_authorized")):
        raise ValueError("AUTHORITY_ESCALATION_IN_AUTHORIZATION")
    if auth["candidate_identity"]["candidate_id"] != prereg["ledger_action"]["candidate_id"]:
        raise ValueError("CANDIDATE_BINDING_INVALID")
    if tuple(auth["frozen_universe"]["ordered_symbols"]) != UNIVERSE:
        raise ValueError("UNIVERSE_BINDING_INVALID")
    if auth["coverage_denominator"]["required_asset_period_windows"] != 60:
        raise ValueError("WINDOW_DENOMINATOR_INVALID")
    canonical_master = auth["canonicalization"]["canonical_master_sha"]
    if git_rev(root, "HEAD") != canonical_master and subprocess.call(["git", "-C", str(root), "merge-base", "--is-ancestor", canonical_master, "HEAD"]) != 0:
        raise ValueError("AUTHORIZATION_NOT_CANONICALIZED")
    if auth["frozen_contract_identity"]["preregistration_digest"] != prereg["preregistration_digest"]:
        raise ValueError("PREREGISTRATION_DIGEST_INVALID")


def _index_path(root: Path, kind: str) -> Path:
    path = root / "data" / "archive" / f"qnty_edge_order_flow_v0_{kind}_object_index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_index(path: Path, value: dict[str, Any]) -> None:
    path.write_bytes(canonical(value) + b"\n")


def _fetch_one(kind: str, symbol: str, year: int, month: int, cache_root: Path, index: dict[str, Any]) -> tuple[str, tuple[int, int], dict[str, Any]]:
    if kind == "price":
        paths = kline.archive_paths(symbol, year, month)
        cache_dir = cache_root / "binance_um_kline_1h"
    else:
        paths = funding.archive_paths(symbol, year, month)
        cache_dir = cache_root / "binance_um_funding_settlement"
    key = f"{symbol}:{year:04d}-{month:02d}"
    prior = index.get(key)
    if prior and prior.get("status") == "HTTP_404":
        return kind, (year, month), prior
    if prior and prior.get("status") == "MATERIALIZED_FETCHED" and Path(prior["zip_path"]).exists() and Path(prior["checksum_path"]).exists():
        return kind, (year, month), prior
    try:
        archive = requests.get(paths["zip_url"], timeout=(10, 90))
        if archive.status_code == 404:
            return kind, (year, month), {"key": key, "status": "HTTP_404", "zip_url": paths["zip_url"], "checksum_url": paths["checksum_url"], "http_status": 404}
        archive.raise_for_status()
        check = requests.get(paths["checksum_url"], timeout=(10, 30))
        if check.status_code != 200:
            return kind, (year, month), {"key": key, "status": "CHECKSUM_UNAVAILABLE", "zip_url": paths["zip_url"], "checksum_url": paths["checksum_url"], "http_status": check.status_code, "zip_sha256": sha256_bytes(archive.content)}
        zip_sha = sha256_bytes(archive.content)
        checksum_bytes = bytes(check.content)
        checksum_sha = sha256_bytes(checksum_bytes)
        zip_path = cache_dir / f"{zip_sha}.zip"
        checksum_path = cache_dir / f"{checksum_sha}.CHECKSUM"
        cache_dir.mkdir(parents=True, exist_ok=True)
        if not zip_path.exists(): zip_path.write_bytes(archive.content)
        if not checksum_path.exists(): checksum_path.write_bytes(checksum_bytes)
        return kind, (year, month), {"key": key, "status": "MATERIALIZED_FETCHED", "zip_url": paths["zip_url"], "checksum_url": paths["checksum_url"], "http_status": 200, "zip_path": str(zip_path), "checksum_path": str(checksum_path), "zip_sha256": zip_sha, "checksum_sha256": checksum_sha, "checksum_text": check.text}
    except (requests.RequestException, OSError) as exc:
        return kind, (year, month), {"key": key, "status": "SOURCE_AUTHENTICATION_UNAVAILABLE", "zip_url": paths["zip_url"], "checksum_url": paths["checksum_url"], "error_type": type(exc).__name__}


def fetch_objects(root: Path, kind: str, requests_for: list[tuple[str, int, int]], workers: int = 8) -> dict[tuple[str, int, int], dict[str, Any]]:
    index_path = _index_path(root, kind)
    index = _load_index(index_path)
    pending = [(symbol, year, month) for symbol, year, month in requests_for if f"{symbol}:{year:04d}-{month:02d}" not in index or index[f"{symbol}:{year:04d}-{month:02d}"].get("status") not in {"HTTP_404", "MATERIALIZED_FETCHED"}]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_fetch_one, kind, symbol, year, month, root / "data" / "archive", index) for symbol, year, month in pending]
        for future in as_completed(futures):
            _, _, record = future.result()
            index[record["key"]] = record
    _save_index(index_path, index)
    return {(symbol, year, month): index[f"{symbol}:{year:04d}-{month:02d}"] for symbol, year, month in requests_for}


def _objects(records: dict[tuple[str, int, int], dict[str, Any]], symbol: str) -> dict[tuple[int, int], tuple[bytes | None, str | None]]:
    result = {}
    for (record_symbol, year, month), record in records.items():
        if record_symbol != symbol: continue
        if record.get("status") != "MATERIALIZED_FETCHED":
            result[(year, month)] = (None, None)
        else:
            result[(year, month)] = (Path(record["zip_path"]).read_bytes(), Path(record["checksum_path"]).read_text(encoding="utf-8"))
    return result


def _source_rows_for_price(csv_text: str) -> tuple[int, str | None, str | None, int, list[str]]:
    reader = csv.DictReader(csv_text.splitlines())
    if set(reader.fieldnames or ()) != REQUIRED_FIELDS:
        return 0, None, None, 0, ["REQUIRED_FIELD_SET_INVALID"]
    rows = list(reader)
    gaps: list[str] = []
    opens = [int(row["open_time"]) for row in rows]
    for previous, current in zip(opens, opens[1:]):
        if current - previous != 3_600_000:
            gaps.append(f"{previous}->{current}")
    close_rule = [int(row["close_time"]) == int(row["open_time"]) + 3_599_999 for row in rows]
    if not all(close_rule): gaps.append("CLOSE_TIME_RULE_INVALID")
    return len(rows), rows[0]["timestamp"] if rows else None, rows[-1]["timestamp"] if rows else None, len(gaps), gaps[:20]


def _funding_pages(symbol: str, start: str, end: str) -> list[bytes] | None:
    query = funding.rest_query(symbol, start, end)
    pages: list[bytes] = []
    next_start = int(query["startTime"])
    try:
        while True:
            params = {**query, "startTime": next_start}
            response = requests.get(funding.REST_ENDPOINT, params=params, timeout=(10, 30))
            if response.status_code != 200: return None
            raw = bytes(response.content)
            pages.append(raw)
            _, rows = funding._parse_rest_page(raw, symbol)
            if not rows or rows[-1][0] >= int(query["endTime"]) or len(rows) < funding.REST_LIMIT: break
            if rows[-1][0] < next_start: return None
            next_start = rows[-1][0]
    except (requests.RequestException, funding.MaterializationError, ValueError, TypeError):
        return None
    return pages


def _write_ignored(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return sha256_bytes(content.encode())


def run(root: Path, workers: int = 8) -> dict[str, Any]:
    auth = json.loads((root / AUTH_REL).read_text(encoding="utf-8"))
    prereg = json.loads((root / PREREG_REL).read_text(encoding="utf-8"))
    verify_authority(root, auth, prereg)
    windows = derive_windows(prereg)
    request_rows = []
    price_requests: list[tuple[str, int, int]] = []
    funding_requests: list[tuple[str, int, int]] = []
    for symbol in UNIVERSE:
        for period in PERIODS:
            window = windows[period]
            for year, month in kline.months(window["price_start"], window["price_end"]): price_requests.append((symbol, year, month))
            for year, month in funding.months(window["funding_start"], window["funding_end"]): funding_requests.append((symbol, year, month))
            request_rows.append({"symbol": symbol, "period_id": period, **window})
    price_records = fetch_objects(root, "price", sorted(set(price_requests)), workers)
    funding_records = fetch_objects(root, "funding", sorted(set(funding_requests)), workers)
    def source_identity(kind: str, records: dict[tuple[str, int, int], dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for (symbol, year, month), record in sorted(records.items()):
            item = {key: value for key, value in record.items() if key not in {"checksum_text", "zip_path", "checksum_path", "error_type"}}
            item["symbol"] = symbol
            item["year"] = year
            item["month"] = month
            item["source_key"] = record.get("zip_url", "").replace("https://data.binance.vision/", "")
            item["downloaded_byte_sha256"] = record.get("zip_sha256")
            checksum_text = record.get("checksum_text")
            item["provider_published_sha256"] = checksum_text.split()[0].lower() if checksum_text and len(checksum_text.split()) >= 2 else None
            item["checksum_text_sha256"] = record.get("checksum_sha256")
            result.append(item)
        return result
    source_body = {"artifact_type": "QNTY_EDGE_ORDER_FLOW_V0_AUTHENTICATED_SOURCE_MANIFEST", "schema_version": "qnty-edge-order-flow-v0-source-manifest-v1", "project_id": PROJECT_ID, "source_contract_identity": auth["source_scope"]["source_contract_identity"], "price_objects": source_identity("price", price_records), "funding_objects": source_identity("funding", funding_records), "provider_checksum_required": True, "local_downloaded_byte_sha256_required": True}
    source_manifest = {**source_body, "source_manifest_digest": digest(source_body)}
    rows: list[dict[str, Any]] = []
    materialized_files: list[dict[str, Any]] = []
    raw_root = root / "data" / "raw" / "qnty_edge_order_flow_v0"
    for request in request_rows:
        symbol, period = request["symbol"], request["period_id"]
        ident = identity(symbol)
        price_objects = _objects(price_records, symbol)
        price = kline.materialize_from_objects(symbol, request["price_start"], request["price_end"], price_objects, ident, "qnty-edge-order-flow-v0")
        price_statuses = [r["status"] for r in price["receipts"]]
        price_row: dict[str, Any] = {"status": price["status"], "source_object_receipts": price["receipts"], "manifest": price.get("manifest")}
        if price["status"] == "MATERIALIZED_VERIFIED":
            count, first, last, gap_count, gap_details = _source_rows_for_price(price["normalized_csv"])
            expected = int((parse_stamp(request["price_end"]) - parse_stamp(request["price_start"])) .total_seconds() // 3600) + 1
            if count != expected or gap_count:
                price_row["status"] = "BLOCKED_PRICE_CONTINUITY"
            price_row.update({"normalized_row_count": count, "normalized_first_timestamp": first, "normalized_last_timestamp": last, "expected_row_count": expected, "gap_count": gap_count, "gap_details": gap_details})
            if price_row["status"] == "MATERIALIZED_VERIFIED":
                path = raw_root / "price" / symbol / f"{period}.csv"
                file_sha = _write_ignored(path, price["normalized_csv"])
                materialized_files.append({"kind": "price", "symbol": symbol, "period_id": period, "path": str(path.relative_to(root)), "sha256": file_sha, "row_count": count})
        else:
            price_row.update({"normalized_row_count": 0, "expected_row_count": None, "gap_count": None, "gap_details": []})
        funding_objects = _objects(funding_records, symbol)
        pages = _funding_pages(symbol, request["funding_start"], request["funding_end"])
        fund = funding.materialize_from_objects(symbol, request["funding_start"], request["funding_end"], funding_objects, ident, "qnty-edge-order-flow-v0", pages)
        fund_status = fund["status"]
        fund_row: dict[str, Any] = {"status": fund_status, "source_object_receipts": fund["receipts"], "manifest": fund.get("manifest"), "rest_witness_available": pages is not None}
        if fund_status == "MATERIALIZED_VERIFIED":
            path = raw_root / "funding" / symbol / f"{period}.jsonl"
            file_sha = _write_ignored(path, fund["normalized_jsonl"])
            materialized_files.append({"kind": "funding", "symbol": symbol, "period_id": period, "path": str(path.relative_to(root)), "sha256": file_sha, "row_count": fund["manifest"]["normalized_event_count"]})
        blockers = []
        if price_row["status"] != "MATERIALIZED_VERIFIED": blockers.append("PRICE_INPUT_MISSING_OR_INVALID")
        if fund_status != "MATERIALIZED_VERIFIED": blockers.append("FUNDING_INPUT_MISSING_OR_INVALID")
        rows.append({"symbol": symbol, "period_id": period, "price": price_row, "funding": fund_row, "status": "INPUT_READY" if not blockers else "BLOCKED", "blockers": blockers})
    rows.sort(key=lambda row: (UNIVERSE.index(row["symbol"]), PERIODS.index(row["period_id"])))
    census_body = {"artifact_type": "QNTY_EDGE_ORDER_FLOW_V0_INPUT_MATERIALIZATION_COVERAGE_CENSUS", "schema_version": "qnty-edge-order-flow-v0-input-materialization-census-v1", "project_id": PROJECT_ID, "candidate_id": auth["candidate_identity"]["candidate_id"], "variant_id": auth["candidate_identity"]["variant_id"], "ordered_symbols": list(UNIVERSE), "periods": list(PERIODS), "required_asset_period_windows": 60, "rows": rows, "input_ready_windows": sum(row["status"] == "INPUT_READY" for row in rows), "blocked_windows": sum(row["status"] == "BLOCKED" for row in rows), "scientific_features_computed": False, "future_returns_accessed": False, "pnl_computed": False, "scientific_execution_performed": False}
    census = {**census_body, "coverage_census_digest": digest(census_body)}
    snapshot_body = {"artifact_type": "QNTY_EDGE_ORDER_FLOW_V0_IMMUTABLE_INPUT_SNAPSHOT", "schema_version": "qnty-edge-order-flow-v0-input-snapshot-v1", "project_id": PROJECT_ID, "candidate_id": auth["candidate_identity"]["candidate_id"], "variant_id": auth["candidate_identity"]["variant_id"], "source_contract_identity": auth["source_scope"]["source_contract_identity"], "preregistration_digest": auth["frozen_contract_identity"]["preregistration_digest"], "universe_digest": auth["frozen_contract_identity"]["universe_digest"], "feature_digest": auth["frozen_contract_identity"]["feature_digest"], "cost_digest": auth["frozen_contract_identity"]["cost_digest"], "coverage_census_digest": census["coverage_census_digest"], "source_manifest_digest": source_manifest["source_manifest_digest"], "materialized_files": materialized_files, "windows": request_rows, "source_bytes_are_content_addressed": True, "scientific_features_computed": False, "future_returns_accessed": False, "pnl_computed": False, "scientific_execution_authorized": False}
    snapshot = {**snapshot_body, "snapshot_digest": digest(snapshot_body), "snapshot_id": f"qnty-edge-order-flow-v0-input-{digest(snapshot_body)}"}
    terminal = "INPUT_READY" if census["blocked_windows"] == 0 else "BLOCKED"
    qualification_body = {"artifact_type": "QNTY_EDGE_ORDER_FLOW_V0_INPUT_QUALIFICATION", "schema_version": "qnty-edge-order-flow-v0-input-qualification-v1", "project_id": PROJECT_ID, "snapshot_id": snapshot["snapshot_id"], "snapshot_digest": snapshot["snapshot_digest"], "coverage_census_digest": census["coverage_census_digest"], "terminal_state": terminal, "required_asset_period_windows": 60, "input_ready_windows": census["input_ready_windows"], "blocked_windows": census["blocked_windows"], "all_required_inputs_ready": terminal == "INPUT_READY", "scientific_features_computed": False, "future_returns_accessed": False, "pnl_computed": False, "scientific_execution_performed": False, "scientific_execution_authorized": False, "downstream_authority": "NONE"}
    qualification = {**qualification_body, "qualification_digest": digest(qualification_body)}
    receipt_body = {"artifact_type": "QNTY_EDGE_ORDER_FLOW_V0_INPUT_MATERIALIZATION_RECEIPT", "schema_version": "qnty-edge-order-flow-v0-input-materialization-receipt-v1", "project_id": PROJECT_ID, "authorization_project_id": AUTH_PROJECT_ID, "authorized_runs_before": 1, "authorized_runs_consumed": 1, "terminal_state": terminal, "source_contract_identity": auth["source_scope"]["source_contract_identity"], "required_asset_period_windows": 60, "input_ready_windows": census["input_ready_windows"], "blocked_windows": census["blocked_windows"], "source_manifest_digest": source_manifest["source_manifest_digest"], "coverage_census_digest": census["coverage_census_digest"], "snapshot_digest": snapshot["snapshot_digest"], "qualification_digest": qualification["qualification_digest"], "scientific_computation_performed": False, "scientific_execution_authorized": False, "downstream_authority": "NONE", "origin_master": git_rev(root, "origin/master"), "implementation_head": git_rev(root, "HEAD")}
    receipt = {**receipt_body, "receipt_digest": digest(receipt_body)}
    out = root / ROOT_REL
    out.mkdir(parents=True, exist_ok=True)
    for name, value in (("input_materialization_request.json", {"artifact_type": "QNTY_EDGE_ORDER_FLOW_V0_INPUT_MATERIALIZATION_REQUEST", "project_id": PROJECT_ID, "authorization_project_id": AUTH_PROJECT_ID, "candidate_identity": auth["candidate_identity"], "frozen_contract_identity": auth["frozen_contract_identity"], "ordered_symbols": list(UNIVERSE), "windows": request_rows, "request_digest": digest({"project_id": PROJECT_ID, "authorization_project_id": AUTH_PROJECT_ID, "candidate_identity": auth["candidate_identity"], "frozen_contract_identity": auth["frozen_contract_identity"], "ordered_symbols": list(UNIVERSE), "windows": request_rows})}), ("source_manifest.json", source_manifest), ("coverage_census.json", census), ("input_snapshot.json", snapshot), ("input_qualification.json", qualification), ("materialization_receipt.json", receipt)):
        (out / name).write_bytes(canonical(value) + b"\n")
    implementation = {"artifact_type": "QNTY_EDGE_ORDER_FLOW_V0_INPUT_MATERIALIZATION_IMPLEMENTATION_MANIFEST", "schema_version": "qnty-edge-order-flow-v0-input-materialization-implementation-v1", "project_id": PROJECT_ID, "implementation_module": "qntylab.qnty_edge_order_flow_v0_input_materialization", "implementation_sha256": sha256_bytes((root / "qntylab/qnty_edge_order_flow_v0_input_materialization.py").read_bytes()), "materializer_kline_contract": kline.CONTRACT_VERSION, "materializer_funding_contract": funding.CONTRACT_VERSION, "source_contract_identity": auth["source_scope"]["source_contract_identity"], "origin_master": git_rev(root, "origin/master"), "terminal_state": terminal, "scientific_execution_authorized": False, "outcome_firewall": {"feature_values": False, "future_returns": False, "pnl": False, "correlations": False, "rankings": False}}
    (out / "implementation_manifest.json").write_bytes(canonical(implementation) + b"\n")
    return {"terminal_state": terminal, "coverage_census_digest": census["coverage_census_digest"], "snapshot_digest": snapshot["snapshot_digest"], "qualification_digest": qualification["qualification_digest"], "receipt_digest": receipt["receipt_digest"], "input_ready_windows": census["input_ready_windows"], "blocked_windows": census["blocked_windows"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    print(json.dumps(run(args.root.resolve(), max(1, args.workers)), sort_keys=True))
