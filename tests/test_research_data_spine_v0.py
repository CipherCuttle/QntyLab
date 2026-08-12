from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import polars as pl
import pytest

from qntylab import research_data_spine as spine


def _rows(start: str, close: str = "11") -> list[dict[str, str]]:
    hours = ("00", "01", "02")
    return [
        {"timestamp": f"2024-01-01T{hour}:00:00Z", "open": "10", "high": "30", "low": "9", "close": close, "volume": "100"}
        for hour in hours
    ]


def _sources() -> dict[str, list[dict[str, str]]]:
    return {"AAAUSDT": _rows("2024-01-01T00:00:00Z"), "BBBUSDT": _rows("2024-01-01T00:00:00Z", close="21")}


def _build(tmp_path: Path, rows: dict[str, list[dict[str, str]]] | None = None) -> dict:
    return spine.materialize_snapshot(
        source_rows_by_symbol=rows or _sources(),
        expected_symbols=["AAAUSDT", "BBBUSDT"],
        source_certificate_identity="sha256:" + "a" * 64,
        source_evidence_digest="sha256:" + "b" * 64,
        evidence_root=tmp_path,
    )


def _reader_args(result: dict) -> dict:
    return {
        "snapshot_path": result["snapshot_path"],
        "expected_snapshot_digest": result["snapshot_digest"],
        "requested_symbols": ["AAAUSDT", "BBBUSDT"],
        "start": "2024-01-01T00:00:00Z",
        "end": "2024-01-01T02:00:00Z",
    }


def _manifest(path: Path) -> dict:
    return json.loads((path / "manifest.json").read_text())


def _write_manifest(path: Path, value: dict) -> None:
    (path / "manifest.json").write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def test_same_approved_logical_inputs_have_canonical_identity_and_idempotent_reuse(tmp_path: Path):
    first = _build(tmp_path)
    second = _build(tmp_path, {"BBBUSDT": _sources()["BBBUSDT"], "AAAUSDT": _sources()["AAAUSDT"]})
    assert first["snapshot_id"] == second["snapshot_id"]
    assert first["snapshot_digest"] == second["snapshot_digest"]
    assert second["reused"] is True
    assert [part["instrument_identity"]["symbol"] for part in first["manifest"]["ordered_partitions"]] == ["AAAUSDT", "BBBUSDT"]


def test_reader_verifies_and_two_non_scientific_consumers_reuse_the_same_snapshot(tmp_path: Path):
    result = _build(tmp_path)
    args = _reader_args(result)
    frame = spine.read_window(**args)
    a = spine.funding_pressure_ohlcv_window_adapter(**args)
    b = spine.generic_panel_window_consumer(**args)
    assert frame.height == 6
    assert a["snapshot_id"] == b["snapshot_id"] == result["snapshot_id"]
    assert a["snapshot_digest"] == b["snapshot_digest"] == result["snapshot_digest"]
    assert b["row_count"] == 6
    assert b["symbols"] == ["AAAUSDT", "BBBUSDT"]


def test_partition_byte_mutation_and_existing_same_id_different_content_fail_closed(tmp_path: Path):
    result = _build(tmp_path)
    target = result["snapshot_path"] / "partitions/AAAUSDT.parquet"
    target.write_bytes(target.read_bytes() + b"tamper")
    with pytest.raises(spine.ResearchDataSpineError, match="byte integrity"):
        spine.verify_snapshot(result["snapshot_path"], result["snapshot_digest"])
    with pytest.raises(spine.ResearchDataSpineError, match="byte integrity"):
        _build(tmp_path)


def test_logical_row_mutation_fails_even_if_manifest_byte_hash_is_replaced(tmp_path: Path):
    result = _build(tmp_path)
    target = result["snapshot_path"] / "partitions/AAAUSDT.parquet"
    pl.read_parquet(target).with_columns(pl.lit("999").alias("close")).write_parquet(target, use_pyarrow=False)
    manifest = _manifest(result["snapshot_path"])
    manifest["ordered_partitions"][0]["parquet_byte_sha256"] = spine._sha_file(target)
    _write_manifest(result["snapshot_path"], manifest)
    with pytest.raises(spine.ResearchDataSpineError, match="OHLC ordering is invalid|logical partition integrity"):
        spine.verify_snapshot(result["snapshot_path"], result["snapshot_digest"])


def test_manifest_schema_and_identity_mutations_fail(tmp_path: Path):
    result = _build(tmp_path)
    manifest = _manifest(result["snapshot_path"])
    manifest["source_evidence_digest"] = "sha256:" + "c" * 64
    _write_manifest(result["snapshot_path"], manifest)
    with pytest.raises(spine.ResearchDataSpineError, match="snapshot digest mismatch"):
        spine.verify_snapshot(result["snapshot_path"], result["snapshot_digest"])

    result = _build(tmp_path / "schema")
    target = result["snapshot_path"] / "partitions/AAAUSDT.parquet"
    pl.read_parquet(target).select([field for field in spine.LOGICAL_FIELDS if field != "volume"]).write_parquet(target, use_pyarrow=False)
    manifest = _manifest(result["snapshot_path"])
    manifest["ordered_partitions"][0]["parquet_byte_sha256"] = spine._sha_file(target)
    _write_manifest(result["snapshot_path"], manifest)
    with pytest.raises(spine.ResearchDataSpineError, match="Parquet read/schema failed"):
        spine.verify_snapshot(result["snapshot_path"], result["snapshot_digest"])

    result = _build(tmp_path / "identity")
    target = result["snapshot_path"] / "partitions/AAAUSDT.parquet"
    pl.read_parquet(target).with_columns(pl.lit("wrong-instance").alias("instrument_instance_id")).write_parquet(target, use_pyarrow=False)
    manifest = _manifest(result["snapshot_path"])
    manifest["ordered_partitions"][0]["parquet_byte_sha256"] = spine._sha_file(target)
    _write_manifest(result["snapshot_path"], manifest)
    with pytest.raises(spine.ResearchDataSpineError, match="stored partition identity failed"):
        spine.verify_snapshot(result["snapshot_path"], result["snapshot_digest"])


def test_source_certificate_mutation_and_source_substitution_are_rejected(tmp_path: Path, monkeypatch):
    certificate_path = Path("experiments/research/jigsaw_funding_pressure_volatility_v0/pit_coverage_certificate_v1.json")
    certificate = json.loads(certificate_path.read_text())
    assert spine._certificate_identity(certificate) == certificate["pit_coverage_certificate_v1_digest"]
    certificate["status"] = "MUTATED"
    with pytest.raises(spine.ResearchDataSpineError, match="source certificate digest mismatch"):
        spine._certificate_identity(certificate)

    original = spine._sha_file
    monkeypatch.setattr(spine, "_sha_file", lambda path: "0" * 64 if path.name == "BCHUSDT-perp-1h.csv" else original(path))
    with pytest.raises(spine.ResearchDataSpineError, match="source substitution or mutation"):
        spine.materialize_certified_funding_pressure_v1(repository_root=Path("."), evidence_root=tmp_path)


def test_duplicate_and_gap_policy_violations_fail(tmp_path: Path):
    duplicate = _sources()
    duplicate["AAAUSDT"] = [*duplicate["AAAUSDT"], duplicate["AAAUSDT"][1]]
    with pytest.raises(spine.ResearchDataSpineError, match="duplicate"):
        _build(tmp_path, duplicate)
    gap = _sources()
    gap["AAAUSDT"] = [gap["AAAUSDT"][0], gap["AAAUSDT"][2]]
    with pytest.raises(spine.ResearchDataSpineError, match="coverage gap"):
        _build(tmp_path, gap)
    unordered = _sources()
    unordered["AAAUSDT"] = list(reversed(unordered["AAAUSDT"]))
    with pytest.raises(spine.ResearchDataSpineError, match="strict timestamp order"):
        _build(tmp_path, unordered)


def test_reader_rejects_out_of_contract_symbol_or_window(tmp_path: Path):
    result = _build(tmp_path)
    args = _reader_args(result)
    with pytest.raises(spine.ResearchDataSpineError, match="outside snapshot composition"):
        spine.read_window(**(args | {"requested_symbols": ["MISSINGUSDT"]}))
    with pytest.raises(spine.ResearchDataSpineError, match="outside certified coverage"):
        spine.read_window(**(args | {"end": "2024-01-01T03:00:00Z"}))
