import hashlib
import json
from pathlib import Path

import pytest

from qntylab import holdout_data_audit as audit


ROOT = Path(__file__).resolve().parents[1]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build():
    return audit.build_audit(ROOT)


def test_audit_covers_exactly_three_assets_and_2023_count():
    result = _build()
    assert result["spec"]["assets"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert set(result["timestamp_coverage"]) == {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
    assert result["spec"]["expected_2023_count"] == 8760


def test_exact_missing_timestamps_are_deterministic():
    result = _build()
    assert result["exact_gaps"] == {
        "BTCUSDT": ["2023-03-24T13:00:00Z"],
        "ETHUSDT": ["2023-03-24T13:00:00Z"],
        "SOLUSDT": ["2023-03-24T13:00:00Z"],
    }
    for coverage in result["timestamp_coverage"].values():
        assert coverage["row_count_2023"] == 8759
        assert coverage["unique_timestamp_count_2023"] == 8759


def test_duplicates_and_non_hour_aligned_rows_fail():
    row = {"timestamp": "2023-01-01T00:00:00Z"}
    with pytest.raises(ValueError, match="duplicate"):
        audit.assert_unique_hourly_open_timestamps([row, row])
    with pytest.raises(ValueError, match="non-hour-aligned"):
        audit.assert_unique_hourly_open_timestamps([{"timestamp": "2023-01-01T00:30:00Z"}])


def test_warmup_requirements_are_derived_from_registered_variants():
    result = _build()
    btc = {row["variant_id"]: row for row in result["warmup_coverage"]["BTCUSDT"]}
    assert btc["variant_f201cbb38819b1e09e763ac7"]["required_warmup_start"] == "2022-12-02T00:00:00Z"
    assert btc["variant_00eb140f03a5f6ab40600160"]["required_warmup_start"] == "2022-12-24T00:00:00Z"
    assert btc["variant_296a2973dfde57cec911715b"]["required_warmup_start"] == "2022-12-02T00:00:00Z"
    assert btc["variant_f201cbb38819b1e09e763ac7"]["evaluation_gaps"] == ["2023-03-24T13:00:00Z"]


def test_no_strategy_calculation_occurs():
    source = (ROOT / "qntylab/holdout_data_audit.py").read_text(encoding="utf-8")
    assert "from .backtest" not in source
    assert "from .strategies" not in source
    assert ".strategy_test" not in source
    result = _build()
    assert result["strategy_execution"] == "NOT_RUN"


def test_no_raw_or_manifest_file_changes_when_building_audit():
    paths = [ROOT / path for path in audit.RAW_AND_MANIFEST_PATHS]
    before = {path: _sha(path) for path in paths}
    _build()
    after = {path: _sha(path) for path in paths}
    assert after == before


def test_no_trial_or_decision_event_is_added_when_building_audit():
    paths = [
        ROOT / "experiments/research/candidates.jsonl",
        ROOT / "experiments/research/decisions.jsonl",
        ROOT / "experiments/research/trials/2026.jsonl",
    ]
    before = {path: _sha(path) for path in paths}
    _build()
    after = {path: _sha(path) for path in paths}
    assert after == before


def test_audit_output_is_byte_deterministic(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    first = audit.build_audit(ROOT)
    second = audit.build_audit(ROOT)
    first_bytes = json.dumps(first, sort_keys=True, indent=2).encode()
    second_bytes = json.dumps(second, sort_keys=True, indent=2).encode()
    assert first_bytes == second_bytes
    (tmp_path / "audit.json").write_bytes(first_bytes)
    assert _sha(tmp_path / "audit.json") == hashlib.sha256(second_bytes).hexdigest()


def test_contamination_search_records_evidence_paths():
    result = _build()
    contamination = result["holdout_contamination"]
    assert contamination["classification"] == "NO_EVIDENCE_OF_PRIOR_2023_INSPECTION"
    assert "generic_2023_evidence_paths" in contamination
    assert any("first_batch" in row["path"] for row in contamination["generic_2023_evidence_paths"])


def test_unrelated_wip_is_untouched_when_building_audit():
    tracked = ROOT / "data/manifests/BTCUSDT-perp-1h.json"
    before = _sha(tracked)
    _build()
    assert _sha(tracked) == before
