import csv
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from qntylab.backtest import evaluate
from qntylab.strategy_test import (
    assert_relevant_source_clean,
    load_config,
    relevant_source_clean,
    relevant_source_sha256,
    run_strategy,
    sanity_warnings,
    sha256_path,
    summarize_runs,
)
from qntylab.research_ledger import canonical_bytes, compute_variant_id, event_id, rebuild
from qntylab.strategies import positions


FIXTURE = Path(__file__).parent / "fixtures" / "daily_market_BTCUSDT_1h.csv"


def _candidate_id(strategy_id, parameters):
    stem = "_".join(str(parameters[key]) for key in sorted(parameters))
    return f"TEST_{strategy_id}_{stem}".replace(".", "_")


def config(tmp_path, **overrides):
    strategy_id = overrides.get("strategy_id", "H002_momentum")
    parameters = overrides.get("parameters", {"lookback": 3, "mode": "long_flat"})
    value = {
        "schema_version": 1,
        "strategy_id": strategy_id,
        "strategy_version": "existing-qntylab-strategies-v1",
        "input_path": str(FIXTURE),
        "evaluation_start": "2021-01-01T00:00:00Z",
        "evaluation_end": "2021-01-02T05:00:00Z",
        "initial_capital": 10000,
        "fee_bps": 10,
        "slippage_bps": 0,
        "funding_boundary_mode": "NOT_APPLICABLE",
        "gap_policy": "REJECT",
        "expected_interval": "1h",
        "candidate_id": _candidate_id(strategy_id, parameters),
        "research_intent": "SCREEN",
        "parameters": parameters,
    }
    value.update(overrides)
    value["candidate_id"] = overrides.get("candidate_id", _candidate_id(value["strategy_id"], value["parameters"]))
    path = tmp_path / "config.json"
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    return path


def research_root(tmp_path, configs):
    root = tmp_path / "research"
    (root / "trials").mkdir(parents=True, exist_ok=True)
    candidates = []
    for cfg_path in configs:
        cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
        event = {
            "event_id": "",
            "event_type": "CANDIDATE_PROPOSED",
            "candidate_id": cfg["candidate_id"],
            "family_id": f"TEST_FAMILY_{cfg['strategy_id']}",
            "variant_id": compute_variant_id(cfg),
            "strategy_id": cfg["strategy_id"],
            "strategy_version": cfg["strategy_version"],
            "objective": "test fixture candidate",
            "origin": "unit test",
            "mechanism": "unit test",
            "prediction": "unit test",
            "required_data": "unit test fixture",
            "decision_time": "unit test",
            "execution_time": "unit test",
            "benchmark": "unit test",
            "parameters": cfg["parameters"],
            "mode": cfg["parameters"]["mode"],
            "bar_interval": cfg["expected_interval"],
            "required_input_kind": "OHLCV_1H_CSV",
            "funding_boundary_mode": cfg["funding_boundary_mode"],
            "failure_condition": "unit test",
            "recorded_at_utc": "2026-08-02T00:00:00Z",
        }
        event["event_id"] = event_id("event_proposal", event)
        candidates.append(event)
    (root / "candidates.jsonl").write_bytes(b"".join(canonical_bytes(event) + b"\n" for event in candidates))
    (root / "decisions.jsonl").write_text("", encoding="utf-8")
    (root / "trials" / "2026.jsonl").write_text("", encoding="utf-8")
    rebuild(root)
    return root


def run_once(tmp_path, cfg=None, name="run"):
    cfg = cfg or config(tmp_path)
    return run_strategy(
        strategy_id="H002_momentum",
        input_path=FIXTURE,
        config_path=cfg,
        output=tmp_path / name,
        research_root=research_root(tmp_path, [cfg]),
        require_clean_source=False,
    )


def write_fixture(path: Path, closes: list[float], *, skip_hour: int | None = None) -> None:
    rows = []
    for i, close in enumerate(closes):
        hour = i if skip_hour is None or i < skip_hour else i + 1
        rows.append(
            {
                "timestamp": f"2021-01-01T{hour:02d}:00:00Z",
                "open": str(close),
                "high": str(close),
                "low": str(close),
                "close": str(close),
                "volume": "1",
            }
        )
    with path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)


def test_relevant_clean_source_runs(tmp_path):
    assert run_once(tmp_path)["receipt"]["relevant_source_clean"] is True


def test_relevant_source_cleanliness_checks_only_bound_tracked_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    bound = repo / "qntylab/strategy_test.py"
    unrelated = repo / "data/manifests/dirty.json"
    bound.parent.mkdir(parents=True)
    unrelated.parent.mkdir(parents=True)
    bound.write_text("one\n", encoding="utf-8")
    unrelated.write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "qntylab/strategy_test.py", "data/manifests/dirty.json"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)

    unrelated.write_text("two\n", encoding="utf-8")
    assert relevant_source_clean(repo, ("qntylab/strategy_test.py",))
    assert_relevant_source_clean(repo, ("qntylab/strategy_test.py",))

    bound.write_text("two\n", encoding="utf-8")
    assert not relevant_source_clean(repo, ("qntylab/strategy_test.py",))
    with pytest.raises(RuntimeError, match="relevant tracked source"):
        assert_relevant_source_clean(repo, ("qntylab/strategy_test.py",))


def test_relevant_source_digest_changes_when_bound_bytes_change(tmp_path):
    repo = tmp_path / "repo"
    (repo / "qntylab").mkdir(parents=True)
    source = repo / "qntylab/data.py"
    source.write_text("one\n", encoding="utf-8")
    first = relevant_source_sha256(repo, ("qntylab/data.py",))
    source.write_text("one!\n", encoding="utf-8")
    assert relevant_source_sha256(repo, ("qntylab/data.py",)) != first


def test_valid_config_parses(tmp_path):
    parsed = load_config(config(tmp_path))
    assert parsed["strategy_id"] == "H002_momentum"
    assert parsed["funding_boundary_mode"] == "NOT_APPLICABLE"


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


def test_receipt_binds_actual_current_commit_and_source_digest(tmp_path):
    result = run_once(tmp_path)
    expected_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    assert result["receipt"]["repository_commit"] == expected_commit
    assert result["receipt"]["relevant_source_sha256"] == relevant_source_sha256()


def test_hand_computable_accounting_fixture():
    close = np.array([100.0, 110.0, 99.0, 99.0, 108.9])
    signal = np.array([0.0, 1.0, -1.0, 0.0, 1.0])
    shifted_position = np.array([0.0, 0.0, 1.0, -1.0, 0.0])
    returns = np.array([0.1, -0.1, 0.0, 0.1])
    gross = np.array([0.0, -0.0, 0.0, -0.1])
    turnover = np.array([0.0, 1.0, 2.0, 1.0])
    costs = np.array([0.0, 0.001, 0.002, 0.001])
    net = np.array([0.0, -0.001, -0.002, -0.101])
    equity = np.cumprod(1 + net)
    drawdown = equity / np.maximum.accumulate(np.r_[1.0, equity])[1:] - 1

    assert positions("H002_momentum", close, {"lookback": 1, "mode": "long_short"}).tolist() == shifted_position.tolist()
    result = evaluate(close, shifted_position, 10)
    assert signal.tolist() == [0.0, 1.0, -1.0, 0.0, 1.0]
    assert returns.tolist() == pytest.approx([0.1, -0.1, 0.0, 0.1])
    assert gross.tolist() == pytest.approx([0.0, 0.0, 0.0, -0.1])
    assert turnover.tolist() == pytest.approx([0.0, 1.0, 2.0, 1.0])
    assert costs.tolist() == pytest.approx([0.0, 0.001, 0.002, 0.001])
    assert net.tolist() == pytest.approx([0.0, -0.001, -0.002, -0.101])
    assert result["gross_cumulative_return"] == pytest.approx(float(np.prod(1 + gross) - 1))
    assert result["net_cumulative_return"] == pytest.approx(float(equity[-1] - 1))
    assert result["max_drawdown"] == pytest.approx(float(drawdown.min()))
    assert result["fee_cost"] == pytest.approx(0.004)
    assert result["trade_count"] == 3


def test_hand_computable_benchmark_excess_and_exposure_metrics(tmp_path):
    fixture = tmp_path / "fixture.csv"
    write_fixture(fixture, [100.0, 110.0, 121.0, 108.9, 119.79, 131.769])
    cfg = config(tmp_path, input_path=str(fixture), evaluation_end="2021-01-01T05:00:00Z", parameters={"lookback": 1, "mode": "long_flat"}, fee_bps=0)
    result = run_strategy(
        strategy_id="H002_momentum",
        input_path=fixture,
        config_path=cfg,
        output=tmp_path / "metrics",
        research_root=research_root(tmp_path, [cfg]),
        require_clean_source=False,
    )["metrics"]
    assert result["buy_and_hold_return"] == pytest.approx(0.31769)
    assert result["excess_return_vs_buy_and_hold"] == pytest.approx(result["net_return"] - result["buy_and_hold_return"])
    assert result["exposure_fraction"] == pytest.approx(3 / 6)


def test_cost_units_are_basis_points_per_abs_position_change():
    close = np.array([100.0, 101.0, 102.0, 103.0])
    position = np.array([0.0, 1.0, -1.0, 0.0])
    result = evaluate(close, position, 25)
    assert result["fee_cost"] == pytest.approx((1 + 2 + 1) * 25 / 10_000)


def test_no_implicit_leverage_in_supported_strategies():
    close = np.array([100.0, 101.0, 99.0, 102.0, 98.0, 103.0, 97.0, 104.0, 96.0, 105.0])
    configs = {
        "H002_momentum": {"lookback": 1, "mode": "long_short"},
        "H003_moving_average": {"fast": 2, "slow": 3, "mode": "long_short"},
        "H004_mean_reversion": {"lookback": 2, "threshold": 0.5, "mode": "long_short"},
        "H005_donchian": {"lookback": 2, "mode": "long_short"},
    }
    for strategy_id, params in configs.items():
        assert set(positions(strategy_id, close, params).tolist()) <= {-1.0, 0.0, 1.0}


@pytest.mark.parametrize(
    ("strategy_id", "params"),
    [
        ("H002_momentum", {"lookback": 3, "mode": "long_flat"}),
        ("H003_moving_average", {"fast": 2, "slow": 4, "mode": "long_flat"}),
        ("H004_mean_reversion", {"lookback": 3, "threshold": 1.5, "mode": "long_short"}),
        ("H005_donchian", {"lookback": 3, "mode": "long_flat"}),
    ],
)
def test_supported_existing_strategy_ids_dispatch(tmp_path, strategy_id, params):
    cfg = config(tmp_path, strategy_id=strategy_id, parameters=params)
    result = run_strategy(
        strategy_id=strategy_id,
        input_path=FIXTURE,
        config_path=cfg,
        output=tmp_path / strategy_id,
        research_root=research_root(tmp_path, [cfg]),
        require_clean_source=False,
    )
    assert result["receipt"]["strategy_id"] == strategy_id
    assert result["receipt"]["parameters"] == params


def test_fixed_h002_followup_dispatch(tmp_path):
    cfg = config(tmp_path, parameters={"lookback": 24, "mode": "long_flat"})
    parsed = load_config(cfg, strategy_id="H002_momentum")
    assert parsed["parameters"] == {"lookback": 24, "mode": "long_flat"}


def test_fixed_h003_followup_dispatch(tmp_path):
    cfg = config(tmp_path, strategy_id="H003_moving_average", parameters={"fast": 24, "slow": 96, "mode": "long_flat"})
    parsed = load_config(cfg, strategy_id="H003_moving_average")
    assert parsed["parameters"] == {"fast": 24, "slow": 96, "mode": "long_flat"}


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
    root = research_root(tmp_path, [cfg])
    before = run_strategy(
        strategy_id="H002_momentum",
        input_path=FIXTURE,
        config_path=cfg,
        output=tmp_path / "before",
        research_root=root,
        require_clean_source=False,
    )
    after = run_strategy(
        strategy_id="H002_momentum",
        input_path=changed,
        config_path=cfg,
        output=tmp_path / "after",
        research_root=root,
        require_clean_source=False,
    )
    assert before["metrics"] == after["metrics"]


def test_same_inputs_produce_identical_normalized_outputs(tmp_path):
    first = run_once(tmp_path, name="first")
    second = run_once(tmp_path, name="second")
    assert first["metrics"] == second["metrics"]


def test_output_collision_fails_without_overwrite(tmp_path):
    run_once(tmp_path, name="collision")
    with pytest.raises(FileExistsError):
        run_once(tmp_path, name="collision")


def test_gap_free_fixture_succeeds_and_missing_hour_fails(tmp_path):
    good = tmp_path / "good.csv"
    bad = tmp_path / "bad.csv"
    closes = [100.0, 101.0, 102.0, 103.0, 104.0]
    write_fixture(good, closes)
    write_fixture(bad, closes, skip_hour=3)
    cfg = config(tmp_path, input_path=str(good), evaluation_end="2021-01-01T04:00:00Z", parameters={"lookback": 1, "mode": "long_flat"})
    root = research_root(tmp_path, [cfg])
    assert run_strategy(
        strategy_id="H002_momentum",
        input_path=good,
        config_path=cfg,
        output=tmp_path / "good",
        research_root=root,
        require_clean_source=False,
    )["receipt"]["gap_policy"] == "REJECT"
    with pytest.raises(ValueError, match="timestamp gap rejected"):
        run_strategy(
            strategy_id="H002_momentum",
            input_path=bad,
            config_path=cfg,
            output=tmp_path / "bad",
            research_root=root,
            require_clean_source=False,
        )


def test_receipt_binds_input_config_code_and_results(tmp_path):
    cfg = config(tmp_path)
    result = run_once(tmp_path, cfg)
    receipt = result["receipt"]
    assert receipt["config_sha256"] == sha256_path(cfg)
    assert receipt["input_sha256"] == sha256_path(FIXTURE)
    assert receipt["repository_commit"]
    assert receipt["relevant_source_clean"] is True
    assert receipt["relevant_source_sha256"] == relevant_source_sha256()
    assert receipt["result_artifact_sha256"]["metrics"] == sha256_path(result["metrics_path"])
    assert receipt["parameters"] == {"lookback": 3, "mode": "long_flat"}


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
    assert receipt["funding_boundary_mode"] == "NOT_APPLICABLE"


def test_unknown_boundary_mode_fails(tmp_path):
    with pytest.raises(ValueError, match="unknown funding_boundary_mode"):
        load_config(config(tmp_path, funding_boundary_mode="IMPLIED"))


def test_funding_free_strategy_rejects_funding_boundary_mode(tmp_path):
    with pytest.raises(ValueError, match="does not use funding"):
        load_config(config(tmp_path, funding_boundary_mode="STRICTLY_BEFORE_BAR_OPEN"))


def test_unknown_strategy_still_fails(tmp_path):
    with pytest.raises(ValueError, match="unknown strategy"):
        cfg = config(tmp_path)
        run_strategy(
            strategy_id="UNKNOWN",
            input_path=FIXTURE,
            config_path=cfg,
            output=tmp_path / "bad",
            research_root=research_root(tmp_path, [cfg]),
            require_clean_source=False,
        )


def test_batch_summary_is_deterministic_and_reads_artifacts(tmp_path):
    h005_cfg = config(tmp_path, strategy_id="H005_donchian", parameters={"lookback": 3, "mode": "long_flat"})
    h005 = run_strategy(
        strategy_id="H005_donchian",
        input_path=FIXTURE,
        config_path=h005_cfg,
        output=tmp_path / "z_h005",
        research_root=research_root(tmp_path, [h005_cfg]),
        require_clean_source=False,
    )
    h002 = run_once(tmp_path, name="a_h002")
    first = summarize_runs([h005["receipt_path"].parent, h002["receipt_path"].parent], tmp_path / "first.csv")
    second = summarize_runs([h002["receipt_path"].parent, h005["receipt_path"].parent], tmp_path / "second.csv")
    assert [row["strategy_id"] for row in first["rows"]] == ["H002_momentum", "H005_donchian"]
    assert first["rows"] == second["rows"]
    assert first["rows"][0]["gross_return"] == h002["metrics"]["gross_return"]
    assert "repository_commit" in first["rows"][0]
    assert "buy_and_hold_return" in first["rows"][0]


def test_summary_flags_receipt_hash_mismatch(tmp_path):
    result = run_once(tmp_path)
    metrics = json.loads(result["metrics_path"].read_text(encoding="utf-8"))
    metrics["net_return"] = 123.0
    result["metrics_path"].write_text(json.dumps(metrics, sort_keys=True) + "\n", encoding="utf-8")
    summary = summarize_runs([result["receipt_path"].parent], tmp_path / "summary.csv")
    assert summary["rows"][0]["status"] == "receipt/hash mismatch"
    assert summary["warning_count"] > 0


def test_non_finite_metrics_are_flagged():
    assert "non-finite metric" in sanity_warnings(
        {
            "gross_return": 0.0,
            "net_return": float("nan"),
            "total_cost": 0.0,
            "maximum_drawdown": 0.0,
            "trade_count": 1,
        }
    )
