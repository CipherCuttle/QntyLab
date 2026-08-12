from __future__ import annotations

import ast
import hashlib
import inspect
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from qntylab import jh01_rv_persistence_temporal_replication_execution_v0r1 as execution


ROOT = Path(__file__).resolve().parents[1]


def _window_fixture(*, unsafe_prior: bool = False):
    decision = datetime(2025, 7, 20, tzinfo=UTC)
    boundaries = [decision - timedelta(hours=index) for index in range(23, -1, -1)] + [decision + timedelta(hours=index) for index in range(1, 25)]
    returns = {boundary: 0.01 for boundary in boundaries}
    bars = {}
    for symbol in execution.UNIVERSE:
        bars[symbol] = {
            boundary - timedelta(hours=1): execution.BarClose(
                boundary - timedelta(hours=1),
                1.0,
                decision + timedelta(seconds=1) if unsafe_prior and boundary <= decision else boundary,
            )
            for boundary in boundaries
        }
    return decision, returns, bars


def _reference_hac(x: list[float], y: list[float]) -> tuple[float, float, float, tuple[float, float], float]:
    """Independent NumPy oracle: least-squares and outer-product algebra only."""
    X = np.column_stack((np.ones(len(x)), np.asarray(x)))
    beta = np.linalg.lstsq(X, np.asarray(y), rcond=None)[0]
    scores = X * (np.asarray(y) - X @ beta)[:, None]
    meat = scores.T @ scores
    for lag in range(1, 6):
        gamma = scores[lag:].T @ scores[:-lag]
        meat += (1.0 - lag / 6.0) * (gamma + gamma.T)
    covariance = np.linalg.inv(X.T @ X) @ meat @ np.linalg.inv(X.T @ X)
    standard_error = float(np.sqrt(covariance[1, 1]))
    interval = (float(beta[1] - execution.HAC_CRITICAL_VALUE_95 * standard_error), float(beta[1] + execution.HAC_CRITICAL_VALUE_95 * standard_error))
    return float(beta[0]), float(beta[1]), standard_error, interval, math.erfc(abs(float(beta[1]) / standard_error) / math.sqrt(2.0))


def test_log_returns_reject_simple_return_substitution_and_invalid_closes() -> None:
    assert execution.asset_log_return(100.0, 110.0) == pytest.approx(math.log(1.1))
    assert execution.asset_log_return(100.0, 110.0) != pytest.approx(0.1)
    for close in (0.0, -1.0, math.inf, math.nan):
        with pytest.raises(execution.ExecutionContractError):
            execution.asset_log_return(close, 1.0)


def test_market_return_requires_ordered_complete_equal_weight_panel() -> None:
    returns = {symbol: float(index) / 100.0 for index, symbol in enumerate(execution.UNIVERSE)}
    assert execution.market_hourly_return(returns) == pytest.approx(sum(returns.values()) / 20)
    with pytest.raises(execution.ExecutionContractError, match="exact ordered"):
        execution.market_hourly_return(dict(reversed(list(returns.items()))))
    with pytest.raises(execution.ExecutionContractError):
        execution.market_hourly_return(dict(list(returns.items())[:-1]))
    with pytest.raises(execution.ExecutionContractError):
        execution.market_hourly_return({**returns, "BTCUSDT": 0.1})


def test_rv24_requires_exact_nonoverlapping_return_windows() -> None:
    assert execution.market_rv24([0.01] * 24) == pytest.approx(math.sqrt(24 * 0.01**2))
    with pytest.raises(execution.ExecutionContractError):
        execution.market_rv24([0.01] * 23)
    with pytest.raises(execution.ExecutionContractError):
        execution.market_rv24([0.01] * 25)


def test_exact_prior_future_windows_and_safe_known_semantics() -> None:
    decision, returns, bars = _window_fixture()
    prior, future = execution.rv24_windows_at_decision(decision=decision, market_returns=returns, bars=bars)
    assert len(prior) == len(future) == 24
    assert prior[-1] == decision and future[0] == decision + timedelta(hours=1)
    assert prior[0] == decision - timedelta(hours=23) and future[-1] == decision + timedelta(hours=24)
    assert not set(prior) & set(future)
    _, _, unsafe_bars = _window_fixture(unsafe_prior=True)
    with pytest.raises(execution.ExecutionContractError, match="safely known"):
        execution.rv24_windows_at_decision(decision=decision, market_returns=returns, bars=unsafe_bars)


def test_panel_rejects_19_21_symbols_at_the_window_gate() -> None:
    decision, returns, bars = _window_fixture()
    with pytest.raises(execution.ExecutionContractError):
        execution.rv24_windows_at_decision(decision=decision, market_returns=returns, bars=dict(list(bars.items())[:-1]))
    with pytest.raises(execution.ExecutionContractError):
        execution.rv24_windows_at_decision(decision=decision, market_returns=returns, bars={**bars, "BTCUSDT": bars[execution.UNIVERSE[0]]})


def test_exact_365_intercept_hac5_matches_independent_numpy_oracle() -> None:
    x = [0.2 + index / 1000.0 + 0.03 * math.sin(index / 11.0) for index in range(365)]
    y = [0.05 + 0.7 * value + 0.02 * math.cos(index / 7.0) for index, value in enumerate(x)]
    actual = execution.ols_hac5(x, y)
    alpha, beta, standard_error, interval, p_value = _reference_hac(x, y)
    assert actual["alpha"] == pytest.approx(alpha, rel=0, abs=1e-13)
    assert actual["beta"] == pytest.approx(beta, rel=0, abs=1e-13)
    assert actual["hac_standard_error"] == pytest.approx(standard_error, rel=0, abs=1e-13)
    assert actual["confidence_interval_95"] == pytest.approx(interval, rel=0, abs=1e-13)
    assert actual["raw_p_value_two_sided"] == pytest.approx(p_value, rel=0, abs=1e-13)
    assert actual["hac_lag"] == 5
    assert actual["hac_covariance"] == "BARTLETT_NEWEY_WEST"


@pytest.mark.parametrize("size", [364, 366])
def test_ols_rejects_anything_but_365_rows(size: int) -> None:
    with pytest.raises(execution.ExecutionContractError, match="365"):
        execution.ols_hac5([float(index) for index in range(size)], [float(index) for index in range(size)])


def test_ols_requires_intercept_and_has_exact_bartlett_weights() -> None:
    x = [float(index) for index in range(365)]
    y = [3.0 + 2.0 * value + (0.1 if index % 2 else -0.1) for index, value in enumerate(x)]
    result = execution.ols_hac5(x, y)
    assert result["alpha"] == pytest.approx(3.0, abs=0.001)
    assert result["beta"] == pytest.approx(2.0, abs=0.0001)
    assert [1.0 - lag / (execution.HAC_LAG + 1) for lag in range(1, 6)] == pytest.approx([5 / 6, 4 / 6, 3 / 6, 2 / 6, 1 / 6])


@pytest.mark.parametrize(
    ("beta", "interval", "p_value", "expected"),
    [
        (0.2, (0.01, 0.4), 0.05, "REPLICATED_WITHIN_FROZEN_TEMPORAL_SCOPE"),
        (-0.2, (-0.4, -0.01), 0.05, "OPPOSITE_DIRECTION_WITHIN_FROZEN_TEMPORAL_SCOPE"),
        (0.2, (-0.01, 0.4), 0.001, "INCONCLUSIVE"),
        (0.2, (0.01, 0.4), 0.051, "INCONCLUSIVE"),
    ],
)
def test_classification_is_mechanical_raw_p_only(beta, interval, p_value, expected) -> None:
    assert execution.classify(beta=beta, confidence_interval_95=interval, raw_p_value_two_sided=p_value) == expected


def test_implementation_has_no_network_or_alternative_model_path() -> None:
    source = inspect.getsource(execution)
    tree = ast.parse(source)
    names = {node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not {"requests", "urllib", "urlopen", "wget", "curl", "statsmodels", "holm", "bonferroni"} & names
    assert "alternative" not in source.lower()
    assert "execution_count\": 1" in source


def test_result_digest_is_deterministic_and_classification_is_not_caller_supplied() -> None:
    payload = {"beta": 0.1, "classification": "INCONCLUSIVE", "execution_result_digest": "ignored"}
    assert execution.digest(payload, omitted_field="execution_result_digest") == execution.digest(dict(payload), omitted_field="execution_result_digest")
    assert "classification" not in inspect.signature(execution.execute_once).parameters


def test_v0r1_has_a_distinct_namespace_and_explicit_superseding_provenance() -> None:
    assert execution.ARTIFACT_RELATIVE == Path("experiments/research/jh01_rv_persistence_temporal_replication_v0/v0r1")
    assert execution.FROZEN_ARTIFACT_RELATIVE == Path("experiments/research/jh01_rv_persistence_temporal_replication_v0")
    assert execution.SUPERSEDES_EXECUTION == "JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_EXECUTION_V0"
    assert execution.PRIOR_EXECUTION_STATE == "EXECUTION_INTERRUPTED_AFTER_REAL_OUTCOME_ACCESS"
    assert execution.REPAIR_REASON == "STRICT_ZIP_ADJACENT_PAIR_CARDINALITY_DEFECT"
    assert execution.REPAIR_SCOPE == "ADJACENT_PAIR_ITERATION_ONLY"
    assert execution.PRISTINE_FIRST_EXECUTION is False
    assert execution.POST_START_REPAIR is True
    artifact_root = ROOT / execution.ARTIFACT_RELATIVE
    request = json.loads((artifact_root / "execution_request.json").read_text(encoding="utf-8"))
    started = json.loads((artifact_root / "execution_started.json").read_text(encoding="utf-8"))
    result = json.loads((artifact_root / "execution_result.json").read_text(encoding="utf-8"))
    for artifact, field in ((request, "execution_request_digest"), (started, "execution_started_digest"), (result, "execution_result_digest")):
        encoded = json.dumps({key: value for key, value in artifact.items() if key != field}, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
        assert artifact[field] == hashlib.sha256(encoded).hexdigest()
    assert started["execution_count"] == result["v0r1_execution_count"] == 1
    assert result["classification"] == "REPLICATED_WITHIN_FROZEN_TEMPORAL_SCOPE"
    assert result["post_start_repair"] is True
    assert result["pristine_first_execution"] is False


def _full_cardinality_synthetic_panel() -> dict[str, tuple[execution.BarClose, ...]]:
    opens = execution.expected_timestamps()
    return {
        symbol: tuple(
            execution.BarClose(
                datetime.fromisoformat(stamp.replace("Z", "+00:00")),
                100.0 + (symbol_index + 1) * 0.1 + hour_index * 0.001 + ((hour_index % 17) + 1) * 0.00001,
                datetime.fromisoformat(stamp.replace("Z", "+00:00")) + timedelta(hours=1),
            )
            for hour_index, stamp in enumerate(opens)
        )
        for symbol_index, symbol in enumerate(execution.UNIVERSE)
    }


def test_full_cardinality_synthetic_panel_executes_the_production_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    panel = _full_cardinality_synthetic_panel()
    calls = 0
    window_lengths: list[int] = []
    original_market_return = execution.market_hourly_return
    original_market_rv24 = execution.market_rv24

    def count_market_return(asset_returns: dict[str, float]) -> float:
        nonlocal calls
        calls += 1
        return original_market_return(asset_returns)

    def count_rv24(hourly_market_returns: list[float]) -> float:
        window_lengths.append(len(hourly_market_returns))
        return original_market_rv24(hourly_market_returns)

    monkeypatch.setattr(execution, "market_hourly_return", count_market_return)
    monkeypatch.setattr(execution, "market_rv24", count_rv24)
    rows = execution.build_design_rows(panel)
    opens = tuple(datetime.fromisoformat(stamp.replace("Z", "+00:00")) for stamp in execution.expected_timestamps())
    assert len(panel) == 20
    assert all(len(rows_for_symbol) == 8785 for rows_for_symbol in panel.values())
    assert sum(len(rows_for_symbol) for rows_for_symbol in panel.values()) == 175700
    assert calls == 8784
    assert len(rows) == 365
    assert len(window_lengths) == 730
    assert set(window_lengths) == {24}
    assert rows[0].decision_time == datetime(2025, 7, 20, tzinfo=UTC)
    assert rows[-1].decision_time == datetime(2026, 7, 19, tzinfo=UTC)
    assert (opens[0], opens[1]) == (datetime(2025, 7, 18, 23, tzinfo=UTC), datetime(2025, 7, 19, 0, tzinfo=UTC))
    assert (opens[8783], opens[8784]) == (datetime(2026, 7, 19, 22, tzinfo=UTC), datetime(2026, 7, 19, 23, tzinfo=UTC))


def test_exact_strict_zip_defect_and_repaired_pair_semantics() -> None:
    opens = tuple(datetime(2025, 7, 18, 23, tzinfo=UTC) + timedelta(hours=index) for index in range(8785))
    with pytest.raises(ValueError):
        tuple(zip(opens, opens[1:], strict=True))
    pairs = tuple(zip(opens[:-1], opens[1:], strict=True))
    assert len(pairs) == 8784
    assert pairs[0] == (opens[0], opens[1])
    assert pairs[-1] == (opens[8783], opens[8784])
    assert "zip(opens[:-1], opens[1:], strict=True)" in inspect.getsource(execution.build_design_rows)
