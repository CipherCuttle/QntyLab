from __future__ import annotations

import ast
import copy
import hashlib
import inspect
from pathlib import Path

import pytest

from qntylab import jh01_rv_persistence_temporal_replication_input_materialization_v0 as materialization
from qntylab import jh01_rv_persistence_temporal_replication_prereg_v0 as prereg


ROOT = Path(__file__).resolve().parents[1]


def _row(timestamp: str, close: str = "1.5") -> dict[str, str]:
    return {"timestamp": timestamp, "open": "1", "high": "2", "low": "1", "close": close, "volume": "3"}


def _symbol(symbol: str, rows: list[dict[str, str]] | None = None, content: str = "fixture") -> dict:
    supplied = rows if rows is not None else [_row(stamp) for stamp in materialization.expected_timestamps()]
    return materialization.qualify_symbol(
        symbol,
        supplied,
        source_object_digests=[hashlib.sha256(symbol.encode()).hexdigest()],
        raw_content_digest=hashlib.sha256(content.encode()).hexdigest(),
    )


def _full_panel() -> dict[str, dict]:
    return {symbol: _symbol(symbol, content=symbol) for symbol in prereg.UNIVERSE}


def test_frozen_request_binds_exact_preregistration_panel_and_time_contract() -> None:
    request = materialization.materialization_request(ROOT)
    assert request["replication_preregistration_digest"] == "46f923023b4b696307da2b9d6fc4c8db9d04b40b012de35e0bf738cc03c4be57"
    assert request["ordered_universe"] == list(prereg.UNIVERSE)
    assert request["universe_digest"] == "e6d1447ff2be57f81eaf943b62218ce9a7b9a6f5bf2d25f9be255cb3f2040cd8"
    assert request["first_required_bar_open"] == "2025-07-18T23:00:00Z"
    assert request["last_required_bar_open"] == "2026-07-19T23:00:00Z"
    assert request["request_digest"] == materialization.digest({key: value for key, value in request.items() if key != "request_digest"})


def test_expected_hourly_timestamp_set_is_exact_and_mechanical() -> None:
    stamps = materialization.expected_timestamps()
    assert len(stamps) == 8785
    assert stamps[0] == prereg.REQUIRED_FIRST_BAR_OPEN
    assert stamps[-1] == prereg.REQUIRED_LAST_BAR_OPEN
    assert len(set(stamps)) == 8785


def test_short_missing_duplicate_unexpected_and_unordered_input_each_fails() -> None:
    expected = [_row(stamp) for stamp in materialization.expected_timestamps()]
    assert _symbol("ALICEUSDT", expected[:-1])["qualification"] == "BLOCKED"
    missing = [*expected[:100], *expected[101:]]
    assert "MISSING_REQUIRED_HOUR" in _symbol("ALICEUSDT", missing)["block_reasons"]
    duplicate = [*expected, copy.deepcopy(expected[100])]
    assert "DUPLICATE_REQUIRED_TIMESTAMP" in _symbol("ALICEUSDT", duplicate)["block_reasons"]
    unexpected = [*expected, _row("2026-07-20T00:00:00Z")]
    assert "UNEXPECTED_HOUR" in _symbol("ALICEUSDT", unexpected)["block_reasons"]
    unordered = [expected[1], expected[0], *expected[2:]]
    assert "TIMESTAMPS_NOT_MONOTONIC" in _symbol("ALICEUSDT", unordered)["block_reasons"]


@pytest.mark.parametrize("close", ["nan", "inf", "0", "-1"])
def test_nonfinite_or_nonpositive_raw_price_fails(close: str) -> None:
    rows = [_row(stamp) for stamp in materialization.expected_timestamps()]
    rows[10]["close"] = close
    assert "NONFINITE_OR_NONPOSITIVE_RAW_PRICE" in _symbol("ALICEUSDT", rows)["block_reasons"]


def test_exact_full_twenty_symbol_continuous_panel_passes_and_substitution_fails() -> None:
    panel = _full_panel()
    qualified = materialization.qualify_panel(panel)
    assert qualified["qualification_status"] == "INPUT_READY"
    assert qualified["pass_count"] == 20
    assert qualified["blocked_count"] == 0
    substituted = dict(panel)
    substituted.pop("XRPUSDT")
    substituted["BTCUSDT"] = _symbol("BTCUSDT")
    assert materialization.qualify_panel(substituted)["qualification_status"] == "BLOCKED_BY_INPUT_CONTRACT"
    nineteen = dict(panel)
    nineteen.pop("XRPUSDT")
    assert materialization.qualify_panel(nineteen)["qualification_status"] == "BLOCKED_BY_INPUT_CONTRACT"


def test_source_content_and_aggregate_snapshot_identity_are_load_bearing() -> None:
    panel = _full_panel()
    qualification = materialization.qualify_panel(panel)
    request = materialization.materialization_request(ROOT)
    original = materialization.snapshot_manifest(request, qualification)
    mutated = copy.deepcopy(qualification)
    mutated["per_symbol"][0]["accepted_raw_content_sha256"] = "0" * 64
    changed = materialization.snapshot_manifest(request, mutated)
    assert original["snapshot_digest"] != changed["snapshot_digest"]
    source_mutated = copy.deepcopy(qualification)
    source_mutated["per_symbol"][0]["ordered_source_object_digests"][0] = "f" * 64
    assert materialization.snapshot_manifest(request, source_mutated)["snapshot_digest"] != original["snapshot_digest"]
    assert original["snapshot_id"] != prereg.SOURCE_SNAPSHOT_ID
    assert original["discovery_snapshot_alias"] is False


def test_temporal_overlap_fails_and_qualification_never_claims_scientific_execution() -> None:
    with pytest.raises(materialization.QualificationError, match="REPLICATION_OVERLAPS_DISCOVERY_HISTORY"):
        materialization.prove_temporal_independence("2025-07-19T23:00:00Z", "2025-07-19T23:00:00Z")
    value = materialization.qualify_panel(_full_panel())
    assert value["scientific_replication_claim"] == "NOT_EXECUTED"
    assert value["jigsaw_evidence_created"] is False
    assert value["execution_authorized"] is False
    assert value["state_snapshot_authorized"] is False


def test_preregistration_bytes_unchanged_and_materializer_has_no_scientific_computation_path() -> None:
    before = hashlib.sha256((ROOT / prereg.ARTIFACT_RELATIVE_PATH).read_bytes()).hexdigest()
    materialization.materialization_request(ROOT)
    after = hashlib.sha256((ROOT / prereg.ARTIFACT_RELATIVE_PATH).read_bytes()).hexdigest()
    assert after == before
    tree = ast.parse(inspect.getsource(materialization))
    names = {node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {node.attr.lower() for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not ({"log", "ols", "hac", "regression", "pvalue", "p_value", "rv24"} & (names | attributes))
