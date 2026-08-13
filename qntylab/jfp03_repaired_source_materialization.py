"""Consume the single already-acquired JFP03 repaired-source response."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT_REL = Path("experiments/research/jigsaw_fast_prospective_signal_discovery_v0")
OUT_REL = ROOT_REL / "materialization"
CACHE_REL = Path("data/archive/binance_jfp_v0")
PROJECT_ID = "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_JFP03_V0R1_REPAIRED_SOURCE_MATERIALIZATION_V0"
AUTH_PROJECT_ID = "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_JFP03_V0R1_REPAIRED_SOURCE_MATERIALIZATION_AUTHORIZATION_V0"
DESIGN_DIGEST = "a52d4999038e0be814ee8770322303fce84bed9ec8941b812748a18867633736"
REST_SHA = "ef2d114a512d1d2905ccd335b3a53d9601b59b2877d31af3dd2dd7dc3fe0c70a"
EXPECTED_SCHEMA = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"]


def canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canon(value)).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run(root: Path, captured: Path) -> dict[str, Any]:
    out = root / OUT_REL
    auth = load(out / "v0r1_repaired_source_materialization_authorization.json")
    census = load(out / "v0r1_supplemental_source_census.json")
    prior = load(out / "v0r1_snapshot_manifest.json")
    if auth["project_id"] != AUTH_PROJECT_ID or auth["authorization"]["materialization_performed"]:
        raise ValueError("AUTHORIZATION_MISSING_OR_CONSUMED")
    if auth["bound_design_digest"] != DESIGN_DIGEST or auth["authorization"]["exactly_one_future_materialization_run"] is not True:
        raise ValueError("AUTHORITY_BINDING_INVALID")
    response = captured / "rest.json"
    raw = response.read_bytes()
    response_sha = hashlib.sha256(raw).hexdigest()
    if response_sha != REST_SHA:
        raise ValueError("AUTHORITATIVE_RESPONSE_SHA_MISMATCH")
    rows = load(response)
    opens = [int(row[0]) for row in rows]
    if len(rows) != 720 or opens[0] != 1575244800000 or opens[-1] != 1577833200000:
        raise ValueError("REST_COVERAGE_INVALID")
    if any(len(row) != 12 for row in rows) or any(row[6] != row[0] + 3599999 for row in rows):
        raise ValueError("REST_SCHEMA_OR_CLOSE_RULE_INVALID")
    if len(set(opens)) != 720 or any(b - a != 3600000 for a, b in zip(opens, opens[1:])):
        raise ValueError("REST_DUPLICATES_OR_GAPS")
    prior_ids = prior["identity_semantics"]["ordered_authenticated_object_identities"]
    if len(prior_ids) != 62 or sum(x.get("calendar_period") == "2025-01" for x in prior_ids) != 1:
        raise ValueError("PRIOR_REUSE_BINDING_INVALID")
    original_ids = [x for x in prior_ids if x.get("calendar_period") != "2025-01"]
    if len(original_ids) != 61:
        raise ValueError("ORIGINAL_REUSE_BINDING_INVALID")
    tail = next(x for x in prior_ids if x.get("calendar_period") == "2025-01")
    if tail.get("local_sha256") != "9ebc05c9b3d5ab3591edf65bc5c7e5dbc2f96c1efc4adc4ea198c651a99a41b1":
        raise ValueError("2025_TAIL_IDENTITY_INVALID")
    original_60 = original_ids[:60]
    new = {"calendar_period": "2019-12", "purpose": "WARMUP", "canonical_url": "https://fapi.binance.com/fapi/v1/klines", "canonical_query_string": "symbol=BTCUSDT&interval=1h&startTime=1575244800000&endTime=1577836799999&limit=1000", "http_status": 200, "response_sha256": response_sha, "row_count": 720, "first_open_time_ms": opens[0], "last_open_time_ms": opens[-1], "field_count": 12, "schema_identity": EXPECTED_SCHEMA, "duplicates": 0, "gaps": 0, "hourly_contiguity": True, "close_time_rule": True, "product_identity": "Binance USD-M BTCUSDT", "interval_identity": "1h", "authentication": "PASS", "status": "MATERIALIZED_VERIFIED"}
    identity = {"reused_original_60": original_60, "reused_2025_01": tail, "new_2019_12": new}
    snapshot_body = {"artifact_type": "JFP03_V0R1_REPAIRED_SOURCE_IMMUTABLE_INPUT_SNAPSHOT", "project_id": PROJECT_ID, "version": "v0r2", "design_digest": DESIGN_DIGEST, "prior_snapshot_id": prior["snapshot_id"], "prior_snapshot_digest": prior["snapshot_digest"], "original_60_reused": True, "original_60_reacquired": False, "existing_2025_01_reused": True, "existing_2025_01_reacquired": False, "new_2019_12_object_count": 1, "source_object_count": 62, "identity": identity}
    snapshot_digest = digest(snapshot_body)
    snapshot = {**snapshot_body, "snapshot_id": f"jfp-input-v0r2-{snapshot_digest}", "snapshot_digest": snapshot_digest}
    qualification_body = {"artifact_type": "JFP03_V0R1_REPAIRED_SOURCE_INPUT_QUALIFICATION", "project_id": PROJECT_ID, "snapshot_id": snapshot["snapshot_id"], "snapshot_digest": snapshot_digest, "input_qualification": "READY", "full_required_raw_support": True, "structural_validation": "PASS", "gaps": 0, "duplicates": 0, "source_object_count": 62, "scientific_features_computed": False, "targets_computed": False, "regression_executed": False, "p_values_computed": False, "scientific_execution_authorized": False, "downstream_authority": "NONE"}
    qualification = {**qualification_body, "qualification_digest": digest(qualification_body)}
    receipt_body = {"artifact_type": "JFP03_V0R1_REPAIRED_SOURCE_MATERIALIZATION_RECEIPT", "project_id": PROJECT_ID, "bound_authorization_project": AUTH_PROJECT_ID, "authorized_runs_before": 1, "authorized_runs_consumed": 1, "source_selected": "REST", "monthly_object_status": "HTTP_404", "monthly_checksum_status": "HTTP_404", "rest_query": new["canonical_query_string"], "authoritative_response_sha256": response_sha, "historical_feasibility_sha256_equal": response_sha == REST_SHA, "new_2019_12_source": new, "original_objects_reused": 60, "original_objects_reacquired": 0, "existing_2025_01_reused": True, "existing_2025_01_reacquired": False, "total_source_objects": 62, "snapshot_id": snapshot["snapshot_id"], "snapshot_digest": snapshot_digest, "qualification_digest": qualification["qualification_digest"], "scientific_computation_performed": False, "scientific_execution_authorized": False, "downstream_authority": "NONE"}
    receipt = {**receipt_body, "receipt_digest": digest(receipt_body)}
    cache = root / CACHE_REL / f"{response_sha}.json"
    cache.write_bytes(raw)
    (out / "v0r2_repaired_source_manifest.json").write_bytes(canon({"artifact_type": "JFP03_V0R1_REPAIRED_SOURCE_MANIFEST", "snapshot_id": snapshot["snapshot_id"], "sources": identity}) + b"\n")
    (out / "v0r2_input_snapshot.json").write_bytes(canon(snapshot) + b"\n")
    (out / "v0r2_input_qualification.json").write_bytes(canon(qualification) + b"\n")
    (out / "v0r2_repaired_source_materialization_receipt.json").write_bytes(canon(receipt) + b"\n")
    return {"snapshot": snapshot, "qualification": qualification, "receipt": receipt}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--captured", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.root.resolve(), args.captured.resolve()), sort_keys=True))
