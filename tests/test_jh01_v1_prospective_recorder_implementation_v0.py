from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import json
import hashlib
import pytest

from qntylab import jh01_v1_prospective_recorder_implementation_v0 as recorder


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/prospective_recorder_and_input_materialization_implementation_v0.json"
PANEL = json.loads((ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/preregistration.json").read_text())["frozen_target"]["ordered_20_symbol_panel"]


def fixture_bars() -> tuple[recorder.Bar, ...]:
    start, end = datetime(2025, 8, 15, tzinfo=UTC), datetime(2026, 9, 15, tzinfo=UTC)
    values = []
    hours = int((end - start).total_seconds() // 3600)
    for offset in range(hours + 1):
        close = start + timedelta(hours=offset)
        for index, symbol in enumerate(PANEL):
            price = 100 + index + 0.01 * offset + 0.1 * ((offset + index) % 7)
            values.append(recorder.Bar(symbol, close, price, (int((close - timedelta(hours=1)).timestamp() * 1000), str(price), str(price), str(price), str(price), "1", int((close - timedelta(milliseconds=1)).timestamp() * 1000), "1", 1, "1", "1", "0")))
    return tuple(values)


@pytest.fixture(scope="module")
def bars() -> tuple[recorder.Bar, ...]: return fixture_bars()


def test_frozen_fixture_recorder_implements_source_range_models_and_artifact(bars):
    artifact = recorder.build_forecast_artifact(ROOT, bars, origin=recorder.FIRST_LIVE_ORIGIN, qualification_mode=True)
    assert artifact["first_required_source_close"] == "2025-08-15T00:00:00Z"
    assert artifact["training_origin_count"] == 365
    assert artifact["training_first_origin"] == "2025-09-14T00:00:00Z"
    assert artifact["training_last_origin"] == "2026-09-13T00:00:00Z"
    assert set(("C_JH01", "B0", "B1", "B3")) <= artifact.keys()
    assert artifact["B3"]["monthly_coefficient"] == artifact["B3"]["monthly_coefficient"]
    assert artifact["forecast_artifact_canonical_digest"] == recorder.digest({key: value for key, value in artifact.items() if key != "forecast_artifact_canonical_digest"})
    assert "p_value" not in artifact and "realized_target" not in artifact


def test_determinism_activation_and_origin_recovery(bars):
    first = recorder.build_forecast_artifact(ROOT, bars, origin=recorder.FIRST_LIVE_ORIGIN, qualification_mode=True)
    second = recorder.build_forecast_artifact(ROOT, bars, origin=recorder.FIRST_LIVE_ORIGIN, qualification_mode=True)
    assert recorder.canonical_bytes(first) == recorder.canonical_bytes(second)
    with pytest.raises(recorder.RecorderBlocked, match="REAL_V1_ACTIVATION_REQUIRED"):
        recorder.build_forecast_artifact(ROOT, bars, origin=recorder.FIRST_LIVE_ORIGIN, qualification_mode=False)
    existing = {"origin_identity": recorder.origin_identity(recorder.FIRST_LIVE_ORIGIN), "artifact_digest": first["forecast_artifact_canonical_digest"]}
    assert recorder.recover_publication(existing, first) == "IDEMPOTENT_AUTHORITATIVE_RECOVERY"
    with pytest.raises(recorder.RecorderBlocked, match="different digest"):
        recorder.recover_publication({**existing, "artifact_digest": "0" * 64}, first)


@pytest.mark.parametrize("mutation", ["future", "duplicate", "missing", "open", "wrong_symbol", "wrong_raw_close"])
def test_source_negative_matrix_fails_closed(bars, mutation):
    changed = list(bars)
    if mutation == "future": changed.append(recorder.Bar(PANEL[0], recorder.FIRST_LIVE_ORIGIN + timedelta(hours=1), 123.0, (0,) * 12))
    elif mutation == "duplicate": changed.append(changed[0])
    elif mutation == "missing": changed = [bar for bar in changed if not (bar.symbol == PANEL[0] and bar.logical_close == datetime(2025, 8, 20, tzinfo=UTC))]
    elif mutation == "open": changed[0] = recorder.Bar(changed[0].symbol, changed[0].logical_close, changed[0].close, changed[0].raw_row, False)
    elif mutation == "wrong_symbol": changed[0] = recorder.Bar("WRONG", changed[0].logical_close, changed[0].close, changed[0].raw_row)
    else: changed[0] = recorder.Bar(changed[0].symbol, changed[0].logical_close, changed[0].close, (0, *changed[0].raw_row[1:]))
    with pytest.raises(recorder.RecorderBlocked): recorder.build_forecast_artifact(ROOT, changed, origin=recorder.FIRST_LIVE_ORIGIN, qualification_mode=True)


def test_retention_package_is_complete_and_tamper_fails(bars, tmp_path):
    forecast = recorder.build_forecast_artifact(ROOT, bars, origin=recorder.FIRST_LIVE_ORIGIN, qualification_mode=True)
    manifest = recorder.retention_package(tmp_path, forecast=forecast, release_metadata={"informational": True}, bundle=b"fixture-bundle", trusted_root=b"fixture-root\n")
    assert set(manifest["files"]) == {"forecast.json", "release_metadata.json", "release_attestation.sigstore.json", "trusted_root.jsonl"}
    recorder.verify_retention_package(tmp_path)
    (tmp_path / "forecast.json").write_bytes(b"{}")
    with pytest.raises(recorder.RecorderBlocked): recorder.verify_retention_package(tmp_path)


def test_qualification_receipt_preserves_frozen_inputs_and_blocks_real_v1():
    result = json.loads(RESULT.read_text())
    prereg = ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/preregistration.json"
    assert result["state"] == "CLOSED_PASS"
    assert hashlib.sha256(prereg.read_bytes()).hexdigest() == result["frozen_inputs"]["v1_preregistration_bytes_sha256"]
    assert result["frozen_inputs"]["first_required_source_close"] == "2025-08-15T00:00:00Z"
    assert result["frozen_inputs"]["obsolete_historical_boundary_consumed"] is False
    assert result["qualification"]["synthetic_live_canary_used"] is False
    assert result["authority"]["v0r3_implementation_authorization_consumed"] is True
    assert not any(value for key, value in result["authority"].items() if key not in {"recorder_implementation_qualified", "v0r3_implementation_authorization_consumed"})
