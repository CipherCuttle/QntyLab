from datetime import UTC, datetime
import hashlib
import json

import pytest

from qntylab.breadth_v2_input_bundle import (
    DECISION_CLOCK_ID, INSTRUMENT_CONTRACT_ID, InputBundleBlocked,
    build_input_bundle, funding_admission_boundary, price_admission_boundary,
    required_history_for_variant, validate_registered_candidate_history,
)
from qntylab.breadth_v2_execution import evaluation_input_bundle_sha256


def test_exact_clock_boundaries():
    assert price_admission_boundary("2024-01-01T07:00:00Z") == "2024-01-01T08:00:00Z"
    assert price_admission_boundary("2024-01-01T08:00:00Z") == "2024-01-01T09:00:00Z"
    assert funding_admission_boundary(1704095999998) == "2024-01-01T08:00:00Z"
    assert funding_admission_boundary(1704096000000) == "2024-01-01T08:00:00Z"
    assert funding_admission_boundary(1704096000003) == "2024-01-01T09:00:00Z"


def test_variant_history_and_catalog():
    assert required_history_for_variant("TIME_SERIES_MOMENTUM", {"lookback": 720}) == {"required_price_closes": 721, "required_funding_signal_events": 0}
    assert required_history_for_variant("MOVING_AVERAGE_TREND", {"slow": 720})["required_price_closes"] == 720
    assert required_history_for_variant("VOLATILITY_TARGETING", {"realized_volatility_window": 336, "volatility_baseline_window": 720})["required_price_closes"] == 337
    assert len(validate_registered_candidate_history()) == 28


def _source(symbol="BTCUSDT", price_change=0, funding_change="0"):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows = []
    for i in range(4):
        ts = (start + __import__("datetime").timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows.append({"timestamp": ts, "open": "1", "high": "2", "low": "0.5", "close": str(1 + i + price_change), "volume": "1"})
    csv = "timestamp,open,high,low,close,volume\n" + "".join(",".join(row.values()) + "\n" for row in rows)
    funding = {"symbol": symbol, "funding_time_ms": 1704067200000, "funding_time_utc": "2024-01-01T00:00:00.000Z", "funding_rate": funding_change}
    raw = json.dumps(funding, separators=(",", ":")) + "\n"
    return {"manifest": {"normalized_sha256": hashlib.sha256(csv.encode()).hexdigest(), "gap_count": 0, "materializer_contract_version": "p", "aggregate_source_receipt_digest": "a" * 64}}, {"normalized_jsonl": raw, "manifest": {"normalized_sha256": hashlib.sha256(raw.encode()).hexdigest(), "coverage_status": "COMPLETE", "materializer_contract_version": "f", "archive_aggregate_source_receipt_digest": "a" * 64, "rest_coverage_witness_digest": "b" * 64, "coverage_reconciliation_digest": "c" * 64}}


def test_bundle_requires_exact_clip_and_binds_identity():
    price, funding = _source()
    result = build_input_bundle(evaluation_start="2024-01-01T02:00:00Z", evaluation_end="2024-01-01T03:00:00Z", symbols=["BTCUSDT"], price_sources={"BTCUSDT": {**price, "normalized_csv": "timestamp,open,high,low,close,volume\n2024-01-01T00:00:00Z,1,2,0.5,1,1\n2024-01-01T01:00:00Z,1,2,0.5,2,1\n2024-01-01T02:00:00Z,1,2,0.5,3,1\n2024-01-01T03:00:00Z,1,2,0.5,4,1\n"}}, funding_sources={"BTCUSDT": funding})
    assert result["status"] == "READY"
    assert result["bundle_payload"]["decision_clock"] == DECISION_CLOCK_ID
    assert result["bundle_payload"]["instrument_contract_id"] == INSTRUMENT_CONTRACT_ID
    assert result["admitted_price"]["BTCUSDT"][0]["decision_time"] == "2024-01-01T02:00:00Z"


def test_coverage_and_instrument_fail_closed():
    price, funding = _source()
    price["normalized_csv"] = "bad\n"
    with pytest.raises(InputBundleBlocked, match="price parent SHA mismatch"):
        build_input_bundle(evaluation_start="2024-01-01T02:00:00Z", evaluation_end="2024-01-01T03:00:00Z", symbols=["BTCUSDT"], price_sources={"BTCUSDT": price}, funding_sources={"BTCUSDT": funding})
    with pytest.raises(InputBundleBlocked, match="wrong instrument"):
        build_input_bundle(evaluation_start="2024-01-01T02:00:00Z", evaluation_end="2024-01-01T03:00:00Z", symbols=["BTCUSDT"], price_sources={}, funding_sources={}, instrument_contract_id="WRONG")


def test_identity_mutations_and_provenance_are_causal():
    digest = "a" * 64
    assets = {"BTCUSDT": {"price_parent_content": digest, "price_content": digest, "price_provenance": digest, "funding_parent_content": digest, "funding_content": digest, "funding_provenance": digest, "coverage": "COMPLETE"}}
    base = dict(instrument_contract_id=INSTRUMENT_CONTRACT_ID, symbols=["BTCUSDT"], boundaries=["2024-01-01T00:00:00Z"], decision_clock=DECISION_CLOCK_ID, assets=assets)
    first = evaluation_input_bundle_sha256(**base)
    assert first == evaluation_input_bundle_sha256(**base)
    for field in ("price_parent_content", "price_content", "price_provenance", "funding_parent_content", "funding_content", "funding_provenance"):
        mutated = {"BTCUSDT": {**assets["BTCUSDT"], field: "b" * 64}}
        assert evaluation_input_bundle_sha256(**{**base, "assets": mutated}) != first
    assert evaluation_input_bundle_sha256(**{**base, "symbols": ["BTCUSDT"], "boundaries": ["2024-01-01T01:00:00Z"]}) != first
    with pytest.raises(ValueError, match="strict asset"):
        evaluation_input_bundle_sha256(**{**base, "assets": {"BTCUSDT": {**assets["BTCUSDT"], "extra": "x"}}})


def test_fixed_panel_and_funding_warmup_fail_closed():
    price, funding = _source()
    with pytest.raises(InputBundleBlocked, match="panel"):
        build_input_bundle(evaluation_start="2024-01-01T02:00:00Z", evaluation_end="2024-01-01T03:00:00Z", symbols=["BTCUSDT"], price_sources={"BTCUSDT": {**price, "normalized_csv": "timestamp,open,high,low,close,volume\n2024-01-01T00:00:00Z,1,2,0.5,1,1\n2024-01-01T01:00:00Z,1,2,0.5,2,1\n2024-01-01T02:00:00Z,1,2,0.5,3,1\n2024-01-01T03:00:00Z,1,2,0.5,4,1\n"}}, funding_sources={"BTCUSDT": funding}, family="FUNDING_CARRY", parameters={"funding_window_events": 168})
