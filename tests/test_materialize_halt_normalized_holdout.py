from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from qntylab import materialize_halt_normalized_holdout as m


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
RAW_PATHS = tuple(ROOT / f"data/raw/{asset}-1h.csv" for asset in ASSETS)
PERP_MANIFEST_PATHS = tuple(ROOT / f"data/manifests/{asset}-perp-1h.json" for asset in ASSETS)
CANONICAL_STREAMS = (
    ROOT / "experiments/research/candidates.jsonl",
    ROOT / "experiments/research/decisions.jsonl",
    ROOT / "experiments/research/trials/2026.jsonl",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as src:
        return list(csv.DictReader(src))


@pytest.fixture()
def rendered() -> dict:
    return m.render_materialization(ROOT)


@pytest.fixture()
def temp_root(tmp_path: Path) -> Path:
    for path in (
        "experiments/specs/binance_spot_halt_normalization_v1.json",
        "experiments/specs/focused_trend_validation_v1.json",
        "experiments/research/summaries/focused_trend_validation_v1_2023_source_resolution.json",
        "experiments/research/summaries/focused_trend_validation_v1_2023_source_resolution.md",
    ):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, target)
    for asset in ASSETS:
        target = tmp_path / f"data/raw/{asset}-1h.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f"data/raw/{asset}-1h.csv", target)
    return tmp_path


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def update_source_artifact_hash(temp_root: Path) -> None:
    spec_path = temp_root / m.SPEC_PATH
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    source_path = temp_root / spec["source_resolution_artifacts"]["json"]["path"]
    spec["source_resolution_artifacts"]["json"]["sha256"] = sha256(source_path)
    write_json(spec_path, spec)


def update_raw_hash(temp_root: Path, asset: str) -> None:
    spec_path = temp_root / m.SPEC_PATH
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    for item in spec["assets"]:
        if item["asset"] == asset:
            item["authoritative_raw_sha256"] = sha256(temp_root / item["authoritative_raw_path"])
    write_json(spec_path, spec)


def test_materializes_exactly_three_authorized_assets(rendered: dict):
    assert tuple(rendered["receipt"]["assets"]) == ASSETS
    assert len(rendered["derived_sha256"]) == 3


def test_exactly_one_halt_row_per_asset_with_frozen_ohlcv(rendered: dict):
    for asset, data in rendered["receipt"]["assets"].items():
        row = data["inserted_row"]
        assert data["authorized_derived_rows"] == 1
        assert row["timestamp"] == "2023-03-24T13:00:00Z"
        assert row["open"] == row["high"] == row["low"] == row["close"]
        assert row["volume"] == "0.00000000"
        if asset == "BTCUSDT":
            assert row["close"] == "28080.00000000"
        if asset == "ETHUSDT":
            assert row["close"] == "1789.52000000"
        if asset == "SOLUSDT":
            assert row["close"] == "21.73000000"


def test_all_non_normalized_rows_match_source_data(rendered: dict):
    halt_ts = "2023-03-24T13:00:00Z"
    for asset, data in rendered["receipt"]["assets"].items():
        source = {row["timestamp"]: row for row in read_rows(ROOT / data["authoritative_raw_path"])}
        derived_path = Path(data["derived_path"])
        derived_rows = list(csv.DictReader((ROOT / derived_path).open(newline="", encoding="utf-8")))
        derived = {row["timestamp"]: row for row in derived_rows if row["timestamp"] != halt_ts}
        assert source == derived
        assert data["source_rows_compared"] == len(source)
        assert data["source_mismatches"] == 0
        assert data["unexpected_derived_rows"] == 0


def test_2023_coverage_and_warmup_range_are_sufficient(rendered: dict):
    for data in rendered["receipt"]["assets"].values():
        cover = data["coverage_2023"]
        assert cover == {
            "first_timestamp": "2023-01-01T00:00:00Z",
            "last_timestamp": "2023-12-31T23:00:00Z",
            "missing_timestamps": 0,
            "row_count": 8760,
            "unique_timestamp_count": 8760,
        }
    assert rendered["receipt"]["warmup_start"] == "2022-12-02T00:00:00Z"


def test_repeated_generation_is_byte_identical_and_hashes_are_stable(rendered: dict):
    rerendered = m.render_materialization(ROOT)
    assert rendered["derived_sha256"] == rerendered["derived_sha256"]
    assert rendered["manifest_sha256"] == rerendered["manifest_sha256"]
    assert rendered["receipt_json_sha256"] == rerendered["receipt_json_sha256"]
    assert rendered["receipt_md_sha256"] == rerendered["receipt_md_sha256"]
    for path, content in rendered["files"].items():
        assert content == rerendered["files"][path]


def test_manifest_and_receipt_hashes_are_deterministic(rendered: dict):
    assert rendered["receipt_json_sha256"] == sha256(ROOT / m.RECEIPT_JSON_PATH)
    assert rendered["receipt_md_sha256"] == sha256(ROOT / m.RECEIPT_MD_PATH)
    for data in rendered["receipt"]["assets"].values():
        assert data["manifest_sha256"] == sha256(ROOT / data["manifest_path"])


def test_derived_sha256_differs_from_raw_and_assets_are_distinct(rendered: dict):
    hashes = set()
    for data in rendered["receipt"]["assets"].values():
        hashes.add(data["derived_sha256"])
        assert data["derived_sha256"] != data["authoritative_raw_sha256"]
    assert len(hashes) == 3


def test_manifest_schema_and_trial_identity_readiness(rendered: dict):
    spec = json.loads((ROOT / m.SPEC_PATH).read_text(encoding="utf-8"))
    required = set(spec["manifest_schema"])
    for data in rendered["receipt"]["assets"].values():
        manifest = json.loads((ROOT / data["manifest_path"]).read_text(encoding="utf-8"))
        assert set(manifest) == required
        assert manifest["derived_sha256"] == data["derived_sha256"]
        assert manifest["normalization_version"] == spec["normalization_version"]
    assert rendered["receipt"]["trial_identity_readiness"]["derived_file_sha256_becomes_input_sha256"] is True
    assert rendered["receipt"]["trial_identity_readiness"]["normalization_version_and_provenance_recorded_in_run_receipt"] is True


def test_no_strategy_backtest_or_ledger_module_is_invoked_by_materializer():
    source = (ROOT / "qntylab/materialize_halt_normalized_holdout.py").read_text(encoding="utf-8")
    assert "import qntylab.strategy_test" not in source
    assert "from . import strategy_test" not in source
    assert "from .backtest" not in source
    assert "import qntylab.backtest" not in source
    assert "research_ledger" not in source
    assert "qntylab.strategy_test" not in sys.modules


def test_no_candidate_trial_decision_raw_or_perp_manifest_mutation(rendered: dict):
    before = {path: sha256(path) for path in (*CANONICAL_STREAMS, *RAW_PATHS, *PERP_MANIFEST_PATHS)}
    m.render_materialization(ROOT)
    after = {path: sha256(path) for path in (*CANONICAL_STREAMS, *RAW_PATHS, *PERP_MANIFEST_PATHS)}
    assert before == after


def test_source_raw_hashes_are_enforced(temp_root: Path):
    raw_path = temp_root / "data/raw/BTCUSDT-1h.csv"
    raw_path.write_text(raw_path.read_text(encoding="utf-8").replace("28080.00000000", "28081.00000000", 1), encoding="utf-8")
    with pytest.raises(m.MaterializationError, match="raw hash mismatch"):
        m.render_materialization(temp_root)


def test_source_resolution_hashes_are_enforced(temp_root: Path):
    source_path = temp_root / "experiments/research/summaries/focused_trend_validation_v1_2023_source_resolution.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["source_contract_finding"] = "MUTATED"
    write_json(source_path, source)
    with pytest.raises(m.MaterializationError, match="JSON hash mismatch"):
        m.render_materialization(temp_root)


def test_additional_required_gap_fails_closed(temp_root: Path):
    raw_path = temp_root / "data/raw/BTCUSDT-1h.csv"
    rows = read_rows(raw_path)
    rows = [row for row in rows if row["timestamp"] != "2023-01-02T00:00:00Z"]
    raw_path.write_bytes(m.render_csv(rows))
    update_raw_hash(temp_root, "BTCUSDT")
    with pytest.raises(m.MaterializationError, match="unexpected required-range source gaps"):
        m.render_materialization(temp_root)


def test_duplicate_normalized_timestamp_fails(temp_root: Path):
    raw_path = temp_root / "data/raw/BTCUSDT-1h.csv"
    rows = read_rows(raw_path)
    rows.append(
        {
            "timestamp": "2023-03-24T13:00:00Z",
            "open": "28080.00000000",
            "high": "28080.00000000",
            "low": "28080.00000000",
            "close": "28080.00000000",
            "volume": "0.00000000",
        }
    )
    rows.sort(key=lambda row: row["timestamp"])
    raw_path.write_bytes(m.render_csv(rows))
    update_raw_hash(temp_root, "BTCUSDT")
    with pytest.raises(m.MaterializationError, match="already exists"):
        m.render_materialization(temp_root)


def test_unauthorized_asset_fails_closed(temp_root: Path):
    spec_path = temp_root / m.SPEC_PATH
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["assets"][2]["asset"] = "XRPUSDT"
    write_json(spec_path, spec)
    with pytest.raises(m.MaterializationError, match="three authorized assets"):
        m.render_materialization(temp_root)


def test_reference_price_mismatch_fails_closed(temp_root: Path):
    spec_path = temp_root / m.SPEC_PATH
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["assets"][0]["halt_reference_price"] = "28081.00000000"
    write_json(spec_path, spec)
    with pytest.raises(m.MaterializationError, match="OHLC must equal reference price"):
        m.render_materialization(temp_root)


def test_nonzero_volume_or_unequal_ohlc_fails_closed(temp_root: Path):
    spec_path = temp_root / m.SPEC_PATH
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["assets"][0]["derived_bar"]["volume"] = "1.00000000"
    write_json(spec_path, spec)
    with pytest.raises(m.MaterializationError, match="volume must be zero"):
        m.render_materialization(temp_root)
    spec["assets"][0]["derived_bar"]["volume"] = "0.00000000"
    spec["assets"][0]["derived_bar"]["high"] = "28081.00000000"
    write_json(spec_path, spec)
    with pytest.raises(m.MaterializationError, match="OHLC must equal reference price"):
        m.render_materialization(temp_root)


def test_more_than_one_inserted_row_fails_closed(temp_root: Path):
    spec_path = temp_root / m.SPEC_PATH
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["assets"].append(dict(spec["assets"][0]))
    write_json(spec_path, spec)
    with pytest.raises(m.MaterializationError, match="three authorized assets"):
        m.render_materialization(temp_root)


def test_interval_with_authoritative_trades_fails_closed(temp_root: Path):
    source_path = temp_root / "experiments/research/summaries/focused_trend_validation_v1_2023_source_resolution.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["assets"]["BTCUSDT"]["trades"]["hourly"]["2023-03-24T13:00:00Z"]["count"] = 1
    write_json(source_path, source)
    update_source_artifact_hash(temp_root)
    with pytest.raises(m.MaterializationError, match="authoritative trades present"):
        m.render_materialization(temp_root)


def test_normalization_version_mismatch_fails_closed(temp_root: Path):
    spec_path = temp_root / m.SPEC_PATH
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["normalization_version"] = "BINANCE_SPOT_HALT_NORMALIZATION_V2"
    write_json(spec_path, spec)
    with pytest.raises(m.MaterializationError, match="unsupported normalization version"):
        m.render_materialization(temp_root)
