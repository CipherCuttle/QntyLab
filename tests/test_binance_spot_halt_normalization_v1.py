import csv
import hashlib
import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "experiments/specs/binance_spot_halt_normalization_v1.json"
SOURCE_JSON_PATH = ROOT / "experiments/research/summaries/focused_trend_validation_v1_2023_source_resolution.json"
SOURCE_MD_PATH = ROOT / "experiments/research/summaries/focused_trend_validation_v1_2023_source_resolution.md"
LEDGER_PATHS = {
    "experiments/research/candidates.jsonl": "e4f1cfa931d0effe740d31d6d441a6479f5ebb0196f7241236622895d7c15006",
    "experiments/research/decisions.jsonl": "6b44b52333dc4ff6488948762294408523f161a5fabd146a6ed726a46ed3d6ff",
    "experiments/research/trials/2026.jsonl": "a9500c06f6eae8c991d5404603198ba3a65543df4e575814b59fcdb41bf7644b",
}
ASSETS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
NORMALIZED_TIMESTAMP = "2023-03-24T13:00:00Z"
SOURCE_COMMIT = "5a0fe6baae1d3ec9762384e192adb9b20e472263"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def _source() -> dict:
    return json.loads(SOURCE_JSON_PATH.read_text(encoding="utf-8"))


def _allowed_event(asset: dict, predicates: dict, bar: dict) -> bool:
    return (
        predicates["market"] == "Binance Spot"
        and predicates["interval"] == "1h"
        and predicates["timestamp"] == NORMALIZED_TIMESTAMP
        and predicates["official_trades_during_interval"] == 0
        and predicates["official_aggTrades_during_interval"] == 0
        and predicates["official_1m_klines_during_interval"] == 0
        and predicates["official_1h_kline_during_interval"] == "absent"
        and predicates["official_source_agreement"] == "REST and checksum-verified archives"
        and predicates["source_resolution_finding"] == "AUTHORITATIVE_NO_TRADE_INTERVAL_CONFIRMED"
        and bar["timestamp"] == NORMALIZED_TIMESTAMP
        and bar["volume"] == "0.00000000"
        and {bar["open"], bar["high"], bar["low"], bar["close"]} == {asset["halt_reference_price"]}
    )


def test_spec_freezes_three_assets_timestamp_commit_and_artifact_hashes():
    spec = _spec()
    assert spec["normalization_id"] == "PREREGISTER_BINANCE_SPOT_HALT_NORMALIZATION_V1"
    assert spec["normalization_version"] == "BINANCE_SPOT_HALT_NORMALIZATION_V1"
    assert spec["status"] == "REGISTERED_NOT_MATERIALIZED"
    assert spec["source_resolution_commit"] == SOURCE_COMMIT
    assert [asset["asset"] for asset in spec["assets"]] == list(ASSETS)
    assert {asset["derived_bar"]["timestamp"] for asset in spec["assets"]} == {NORMALIZED_TIMESTAMP}
    assert spec["source_resolution_artifacts"]["json"]["sha256"] == _sha256(SOURCE_JSON_PATH)
    assert spec["source_resolution_artifacts"]["markdown"]["sha256"] == _sha256(SOURCE_MD_PATH)


def test_committed_source_evidence_mandates_zero_trade_confirmation():
    source = _source()
    assert source["source_contract_finding"] == "AUTHORITATIVE_NO_TRADE_INTERVAL_CONFIRMED"
    for symbol, asset in source["assets"].items():
        assert symbol in ASSETS
        assert asset["classification"] == "AUTHORITATIVE_NO_TRADE_INTERVAL_CONFIRMED"
        comparison = asset["cross_source_comparison"]
        assert comparison == {
            "archive_1h_missing_in_gap": 1,
            "archive_1m_missing_in_gap": 60,
            "archive_agg_trade_gap_count": 0,
            "archive_trade_gap_count": 0,
            "rest_1h_missing_in_gap": 1,
            "rest_1m_missing_in_gap": 60,
            "rest_agg_trade_gap_count": 0,
            "rest_all_status_200": True,
            "rest_and_archives_agree": True,
        }
        assert asset["trades"]["hourly"][NORMALIZED_TIMESTAMP]["count"] == 0
        assert asset["aggTrades"]["hourly"][NORMALIZED_TIMESTAMP]["count"] == 0


def test_missing_kline_without_zero_trade_evidence_is_rejected():
    spec = _spec()
    predicates = deepcopy(spec["source_predicates"])
    predicates["official_trades_during_interval"] = None
    asset = spec["assets"][0]
    assert not _allowed_event(asset, predicates, asset["derived_bar"])


def test_authoritative_trade_inside_interval_rejects_normalization():
    spec = _spec()
    predicates = deepcopy(spec["source_predicates"])
    predicates["official_trades_during_interval"] = 1
    asset = spec["assets"][0]
    assert not _allowed_event(asset, predicates, asset["derived_bar"])


def test_ohlc_must_equal_reference_price_and_volume_zero():
    spec = _spec()
    predicates = spec["source_predicates"]
    for asset in spec["assets"]:
        assert _allowed_event(asset, predicates, asset["derived_bar"])
        bad_price = deepcopy(asset["derived_bar"])
        bad_price["high"] = "999.00000000"
        assert not _allowed_event(asset, predicates, bad_price)
        bad_volume = deepcopy(asset["derived_bar"])
        bad_volume["volume"] = "1.00000000"
        assert not _allowed_event(asset, predicates, bad_volume)


def test_raw_paths_and_derived_paths_are_distinct_and_raw_hashes_match():
    spec = _spec()
    for asset in spec["assets"]:
        raw = asset["authoritative_raw_path"]
        derived = asset["derived_path"]
        assert raw != derived
        assert raw.startswith("data/raw/")
        assert derived.startswith("data/derived/focused_trend_validation_v1/")
        assert _sha256(ROOT / raw) == asset["authoritative_raw_sha256"]
        assert not (ROOT / derived).exists()


def test_only_one_normalized_row_per_asset_and_all_other_gaps_reject():
    spec = _spec()
    assert spec["gap_policy"]["allowed_normalization_count"] == 3
    assert spec["gap_policy"]["allowed_policy"] == "NORMALIZE_ONLY_PREREGISTERED_AUTHORITATIVE_HALT"
    assert spec["gap_policy"]["global_policy_remains"] == "REJECT"
    assert spec["gap_policy"]["reject_policy"] == "REJECT_ALL_OTHER_GAPS"
    assert all("no other timestamp may be synthesized" != rule.lower() for rule in spec["explicit_forbidden_behavior"])
    assert "no other timestamp may be synthesized" in spec["gap_policy"]["rules"]


def test_normalization_version_affects_provenance_and_receipt_identity():
    spec = _spec()
    asset = spec["assets"][0]
    base_receipt = {
        "input_sha256": "derived-file-hash",
        "normalization_version": spec["normalization_version"],
        "source_resolution_commit": spec["source_resolution_commit"],
    }
    changed = dict(base_receipt, normalization_version="BINANCE_SPOT_HALT_NORMALIZATION_V2")
    base_hash = hashlib.sha256(json.dumps(base_receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    changed_hash = hashlib.sha256(json.dumps(changed, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert base_hash != changed_hash
    assert spec["trial_identity_requirements"]["derived_file_sha256_becomes_input_sha256"] is True
    assert spec["trial_identity_requirements"]["normalization_version_and_provenance_recorded_in_run_receipt"] is True
    assert asset["authoritative_raw_sha256"] != "derived-file-hash"


def test_no_raw_file_candidate_trial_or_decision_event_is_added():
    spec = _spec()
    for relative, expected in LEDGER_PATHS.items():
        assert _sha256(ROOT / relative) == expected
    for asset in spec["assets"]:
        rows = list(csv.DictReader((ROOT / asset["authoritative_raw_path"]).open(newline="", encoding="utf-8")))
        assert NORMALIZED_TIMESTAMP not in {row["timestamp"] for row in rows}
        assert _sha256(ROOT / asset["authoritative_raw_path"]) == asset["authoritative_raw_sha256"]


def test_spec_bytes_are_deterministic():
    raw = SPEC_PATH.read_bytes()
    parsed = json.loads(raw)
    assert raw == json.dumps(parsed, sort_keys=True, indent=2).encode("utf-8") + b"\n"
