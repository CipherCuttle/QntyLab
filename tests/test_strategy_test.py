import csv
import json
from pathlib import Path

import pytest

from qntylab.strategy_test import load_config, run_strategy, sha256_path


FIXTURE = Path(__file__).parent / "fixtures" / "daily_market_BTCUSDT_1h.csv"


def config(tmp_path, **overrides):
    value = {
        "schema_version": 1,
        "strategy_id": "H002_momentum",
        "strategy_version": "existing-qntylab-strategies-v1",
        "input_path": str(FIXTURE),
        "evaluation_start": "2021-01-01T00:00:00Z",
        "evaluation_end": "2021-01-02T05:00:00Z",
        "initial_capital": 10000,
        "fee_bps": 10,
        "slippage_bps": 0,
        "funding_boundary_mode": "STRICTLY_BEFORE_BAR_OPEN",
        "parameters": {"lookback": 3, "mode": "long_flat"},
    }
    value.update(overrides)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    return path


def run_once(tmp_path, cfg=None, name="run"):
    cfg = cfg or config(tmp_path)
    return run_strategy(
        strategy_id="H002_momentum",
        input_path=FIXTURE,
        config_path=cfg,
        output=tmp_path / name,
    )


def test_valid_config_parses(tmp_path):
    parsed = load_config(config(tmp_path))
    assert parsed["strategy_id"] == "H002_momentum"
    assert parsed["funding_boundary_mode"] == "STRICTLY_BEFORE_BAR_OPEN"


def test_unknown_and_malformed_config_fail(tmp_path):
    with pytest.raises(ValueError, match="unknown config keys"):
        load_config(config(tmp_path, extra=True))
    with pytest.raises(ValueError, match="unknown strategy"):
        load_config(config(tmp_path, strategy_id="NOPE"))
    malformed = tmp_path / "bad.json"
    malformed.write_text("{")
    with pytest.raises(ValueError, match="invalid config JSON"):
        load_config(malformed)


def test_selected_real_strategy_executes_on_fixture(tmp_path):
    result = run_once(tmp_path)
    assert result["receipt"]["status"] == "completed"
    assert result["metrics"]["observation_count"] == 29
    assert result["metrics"]["trade_count"] > 0


def test_future_data_cannot_influence_earlier_decision(tmp_path):
    changed = tmp_path / "changed.csv"
    rows = list(csv.DictReader(FIXTURE.open(newline="", encoding="utf-8")))
    rows[-1]["close"] = "999"
    rows[-1]["high"] = "1000"
    with changed.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    cfg = config(tmp_path, evaluation_end="2021-01-02T04:00:00Z")
    before = run_strategy(strategy_id="H002_momentum", input_path=FIXTURE, config_path=cfg, output=tmp_path / "before")
    after = run_strategy(strategy_id="H002_momentum", input_path=changed, config_path=cfg, output=tmp_path / "after")
    assert before["metrics"] == after["metrics"]


def test_same_inputs_produce_identical_normalized_outputs(tmp_path):
    first = run_once(tmp_path, name="first")
    second = run_once(tmp_path, name="second")
    assert first["metrics"] == second["metrics"]


def test_receipt_binds_input_config_code_and_results(tmp_path):
    cfg = config(tmp_path)
    result = run_once(tmp_path, cfg)
    receipt = result["receipt"]
    assert receipt["config_sha256"] == sha256_path(cfg)
    assert receipt["input_sha256"] == sha256_path(FIXTURE)
    assert receipt["repository_commit"]
    assert receipt["result_artifact_sha256"]["metrics"] == sha256_path(result["metrics_path"])


def test_costs_affect_net_return_correctly(tmp_path):
    zero = run_once(tmp_path, config(tmp_path, fee_bps=0, slippage_bps=0), name="zero")["metrics"]
    costly = run_once(tmp_path, config(tmp_path, fee_bps=10, slippage_bps=5), name="costly")["metrics"]
    assert zero["total_cost"] == 0
    assert costly["total_cost"] > 0
    assert costly["net_return"] < zero["net_return"]


def test_exploratory_label_is_always_true(tmp_path):
    assert run_once(tmp_path)["receipt"]["exploratory_only"] is True


def test_funding_boundary_mode_is_explicit(tmp_path):
    receipt = run_once(tmp_path)["receipt"]
    assert receipt["funding_boundary_mode"] == "STRICTLY_BEFORE_BAR_OPEN"


def test_unknown_boundary_mode_fails(tmp_path):
    with pytest.raises(ValueError, match="unknown funding_boundary_mode"):
        load_config(config(tmp_path, funding_boundary_mode="IMPLIED"))
