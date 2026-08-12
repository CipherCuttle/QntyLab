from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil

import polars as pl
import pytest

from qntylab import jigsaw_harvest_execution_v0 as bridge
from qntylab import jigsaw_harvest_v0 as harvest
from qntylab import research_data_spine as spine


BRIDGE_SHA = "b" * 40
SYNTHETIC_FIRST_BAR_OPEN = "2024-01-01T00:00:00Z"
SYNTHETIC_LAST_BAR_OPEN = "2024-01-01T02:00:00Z"


def _source_rows(symbol_index: int) -> list[dict[str, str]]:
    opened = datetime.fromisoformat(SYNTHETIC_FIRST_BAR_OPEN.replace("Z", "+00:00")).astimezone(UTC)
    final = datetime.fromisoformat(SYNTHETIC_LAST_BAR_OPEN.replace("Z", "+00:00")).astimezone(UTC)
    rows = []
    while opened <= final:
        close = 100 + symbol_index + (opened.hour / 100)
        rows.append(
            {
                "timestamp": opened.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": f"{close - 0.1:.2f}",
                "high": f"{close + 0.2:.2f}",
                "low": f"{close - 0.2:.2f}",
                "close": f"{close:.2f}",
                "volume": "100",
            }
        )
        opened += timedelta(hours=1)
    return rows


@pytest.fixture(scope="session")
def synthetic_snapshot(tmp_path_factory: pytest.TempPathFactory) -> dict:
    sources = {symbol: _source_rows(index) for index, symbol in enumerate(harvest.UNIVERSE)}
    return spine.materialize_snapshot(
        source_rows_by_symbol=sources,
        expected_symbols=list(harvest.UNIVERSE),
        source_certificate_identity="sha256:" + "a" * 64,
        source_evidence_digest="sha256:" + "b" * 64,
        evidence_root=tmp_path_factory.mktemp("synthetic-jigsaw-harvest-snapshot"),
    )


@pytest.fixture
def bound_snapshot(monkeypatch: pytest.MonkeyPatch, synthetic_snapshot: dict) -> dict:
    monkeypatch.setattr(harvest, "EXPECTED_SNAPSHOT_ID", synthetic_snapshot["snapshot_id"])
    monkeypatch.setattr(harvest, "EXPECTED_SNAPSHOT_DIGEST", synthetic_snapshot["snapshot_digest"])
    monkeypatch.setattr(harvest, "FIRST_BAR_OPEN", SYNTHETIC_FIRST_BAR_OPEN)
    monkeypatch.setattr(harvest, "LAST_BAR_OPEN", SYNTHETIC_LAST_BAR_OPEN)
    return synthetic_snapshot


def _copy_snapshot(tmp_path: Path, snapshot: dict) -> Path:
    target = tmp_path / "snapshot"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(snapshot["snapshot_path"], target)
    return target


def _rows() -> tuple[harvest.DesignRow, ...]:
    return tuple(
        harvest.DesignRow(
            decision_time=decision,
            rv24_prior=(index + 1) / 100,
            dispersion24=(index + 2) / 90,
            breadth7d=(index % 20) / 20,
            drawdown_depth30d=(index % 30) / 100,
            rv24_future=(index + 3) / 80,
            market_return_future=(index + 4) / 70,
        )
        for index, decision in enumerate(harvest.canonical_schedule())
    )


def _patch_design_rows(monkeypatch: pytest.MonkeyPatch, seen: dict) -> None:
    fixture_rows = _rows()

    def fake_build(*, bars_by_symbol: dict[str, tuple[harvest.BarClose, ...]]) -> tuple[harvest.DesignRow, ...]:
        seen["bars"] = bars_by_symbol
        return fixture_rows

    monkeypatch.setattr(harvest, "_build_design_rows", fake_build)


def test_bridge_delegates_verified_transport_and_frozen_statistics(bound_snapshot: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}
    _patch_design_rows(monkeypatch, seen)
    ols_calls: list[str] = []
    holm_input: dict[str, float] = {}
    classify_calls: list[tuple[float, tuple[float, float], float]] = []

    def fake_ols(*, proposition_id: str, x: list[float], y: list[float]):
        ols_calls.append(proposition_id)
        assert len(x) == len(y) == harvest.OBSERVATION_COUNT
        index = harvest.PROPOSITION_IDS.index(proposition_id) + 1
        return float(index), 0.1, (0.8, 1.2), index / 100

    def fake_holm(values: dict[str, float]) -> dict[str, float]:
        holm_input.update(values)
        return {identifier: values[identifier] for identifier in harvest.PROPOSITION_IDS}

    def fake_classify(*, beta: float, interval: tuple[float, float], holm_p: float) -> str:
        classify_calls.append((beta, interval, holm_p))
        return "INCONCLUSIVE"

    monkeypatch.setattr(harvest, "_ols_hac", fake_ols)
    monkeypatch.setattr(harvest, "holm_adjust", fake_holm)
    monkeypatch.setattr(harvest, "classify", fake_classify)
    receipt = bridge.execute_verified_snapshot(snapshot_path=bound_snapshot["snapshot_path"], execution_bridge_sha=BRIDGE_SHA)

    assert list(seen["bars"]) == list(harvest.UNIVERSE)
    first = seen["bars"][harvest.UNIVERSE[0]][0]
    assert first.bar_open_time.isoformat().replace("+00:00", "Z") == harvest.FIRST_BAR_OPEN
    assert first.safe_known_after == first.bar_open_time + timedelta(hours=1)
    assert first.close == pytest.approx(100.0)
    assert ols_calls == list(harvest.PROPOSITION_IDS)
    assert holm_input == {identifier: (index + 1) / 100 for index, identifier in enumerate(harvest.PROPOSITION_IDS)}
    assert len(classify_calls) == 4
    assert receipt["ordered_proposition_ids"] == list(harvest.PROPOSITION_IDS)
    assert [result["proposition_id"] for result in receipt["results"]] == list(harvest.PROPOSITION_IDS)
    assert len(receipt["results"]) == 4
    assert receipt["hac_lag"] == 5
    assert receipt["canonical_execution_base"] == bridge.CANONICAL_EXECUTION_BASE
    assert receipt["reviewed_harvest_implementation_sha"] == bridge.REVIEWED_HARVEST_IMPLEMENTATION_SHA
    assert receipt["execution_bridge_sha"] == BRIDGE_SHA
    assert receipt["implementation_identity"] == BRIDGE_SHA
    assert receipt["execution_mode"] == "REAL_FROZEN_SNAPSHOT"
    assert receipt["result_order"] == list(harvest.PROPOSITION_IDS)
    assert receipt["result_order"] == receipt["ordered_proposition_ids"]
    assert receipt["snapshot_id"] == bound_snapshot["snapshot_id"]
    assert receipt["snapshot_digest"] == bound_snapshot["snapshot_digest"]
    assert receipt["throughput"] == {"snapshot_reused": True, "new_data_acquisitions": 0, "new_data_qualification_phases": 0, "data_infrastructure_changes": 0}
    assert receipt["authority"] == "NON_AUTHORITATIVE_EXPLORATORY_ONLY"
    assert receipt["explicit"] == {"scientific_authority": "EXPLORATORY_ASSOCIATION_ONLY", "router_authority": "NONE", "qnty_authority": "NONE", "trading_authority": "NONE"}
    assert receipt["result_digest"] == harvest.result_digest(receipt)

    preregistration = json.loads(
        (Path(__file__).parents[1] / "experiments" / "research" / "jigsaw_harvest_v0" / "preregistration.json").read_text()
    )
    for field in preregistration["result_schema"]["required_global_fields"]:
        assert field in receipt


def test_receipt_is_deterministic_and_bridge_requires_final_sha(bound_snapshot: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_design_rows(monkeypatch, {})
    first = bridge.execute_verified_snapshot(snapshot_path=bound_snapshot["snapshot_path"], execution_bridge_sha=BRIDGE_SHA)
    second = bridge.execute_verified_snapshot(snapshot_path=bound_snapshot["snapshot_path"], execution_bridge_sha=BRIDGE_SHA)
    assert first == second
    for field, replacement in {
        "implementation_identity": "c" * 40,
        "execution_mode": "SYNTHETIC",
        "result_order": list(reversed(harvest.PROPOSITION_IDS)),
    }.items():
        mutated = deepcopy(first)
        mutated[field] = replacement
        assert harvest.result_digest(mutated) != first["result_digest"]
    with pytest.raises(bridge.ExecutionBridgeError, match="commit SHA"):
        bridge.execute_verified_snapshot(snapshot_path=bound_snapshot["snapshot_path"], execution_bridge_sha="pending")


def test_wrong_snapshot_digest_id_and_universe_rejected(bound_snapshot: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(harvest, "EXPECTED_SNAPSHOT_DIGEST", "0" * 64)
    with pytest.raises(spine.ResearchDataSpineError, match="digest mismatch"):
        bridge.execute_verified_snapshot(snapshot_path=bound_snapshot["snapshot_path"], execution_bridge_sha=BRIDGE_SHA)

    monkeypatch.setattr(harvest, "EXPECTED_SNAPSHOT_DIGEST", bound_snapshot["snapshot_digest"])
    monkeypatch.setattr(harvest, "EXPECTED_SNAPSHOT_ID", "rds-v0-" + "1" * 64)
    with pytest.raises(harvest.FrozenInputError, match="substitution"):
        bridge.execute_verified_snapshot(snapshot_path=bound_snapshot["snapshot_path"], execution_bridge_sha=BRIDGE_SHA)

    monkeypatch.setattr(harvest, "EXPECTED_SNAPSHOT_ID", bound_snapshot["snapshot_id"])
    monkeypatch.setattr(harvest, "UNIVERSE", ("MISSINGUSDT", *harvest.UNIVERSE[1:]))
    with pytest.raises(harvest.FrozenInputError, match="universe"):
        bridge.execute_verified_snapshot(snapshot_path=bound_snapshot["snapshot_path"], execution_bridge_sha=BRIDGE_SHA)


def test_corrupted_and_logically_mutated_parquet_are_rejected(bound_snapshot: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_design_rows(monkeypatch, {})
    corrupted = _copy_snapshot(tmp_path / "corrupted", bound_snapshot)
    target = corrupted / "partitions" / f"{harvest.UNIVERSE[0]}.parquet"
    target.write_bytes(target.read_bytes() + b"tamper")
    with pytest.raises(spine.ResearchDataSpineError, match="byte integrity"):
        bridge.execute_verified_snapshot(snapshot_path=corrupted, execution_bridge_sha=BRIDGE_SHA)

    logical = _copy_snapshot(tmp_path / "logical", bound_snapshot)
    target = logical / "partitions" / f"{harvest.UNIVERSE[0]}.parquet"
    pl.read_parquet(target).with_columns(pl.lit("999").alias("close")).write_parquet(target, use_pyarrow=False)
    manifest_path = logical / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["ordered_partitions"][0]["parquet_byte_sha256"] = spine._sha_file(target)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(spine.ResearchDataSpineError, match="OHLC ordering is invalid|logical partition integrity"):
        bridge.execute_verified_snapshot(snapshot_path=logical, execution_bridge_sha=BRIDGE_SHA)


def test_schema_mutation_and_no_network_or_acquisition_fallback(bound_snapshot: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_design_rows(monkeypatch, {})
    mutated = _copy_snapshot(tmp_path / "schema", bound_snapshot)
    target = mutated / "partitions" / f"{harvest.UNIVERSE[0]}.parquet"
    pl.read_parquet(target).select([field for field in spine.LOGICAL_FIELDS if field != "volume"]).write_parquet(target, use_pyarrow=False)
    manifest_path = mutated / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["ordered_partitions"][0]["parquet_byte_sha256"] = spine._sha_file(target)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(spine.ResearchDataSpineError, match="Parquet read/schema failed"):
        bridge.execute_verified_snapshot(snapshot_path=mutated, execution_bridge_sha=BRIDGE_SHA)
    monkeypatch.setattr(spine, "materialize_snapshot", lambda **_kwargs: pytest.fail("bridge attempted data acquisition/materialization"))
    bridge.execute_verified_snapshot(snapshot_path=bound_snapshot["snapshot_path"], execution_bridge_sha=BRIDGE_SHA)
    source = Path(bridge.__file__).read_text()
    assert "requests" not in source and "urllib" not in source
