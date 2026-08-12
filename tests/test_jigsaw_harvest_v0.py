from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from qntylab import jigsaw_harvest_v0 as harvest


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _returns(values: list[float]) -> dict[str, float]:
    return {symbol: values[index] for index, symbol in enumerate(harvest.UNIVERSE)}


def _rows(*, sign: float = 1.0) -> tuple[harvest.DesignRow, ...]:
    rows = []
    for index, decision in enumerate(harvest.canonical_schedule()):
        x = (index - 289.5) / 100.0
        noise = 0.03 * math.sin(index * 0.31) + 0.01 * math.cos(index * 0.17)
        rows.append(harvest.DesignRow(
            decision_time=decision,
            rv24_prior=x,
            dispersion24=x * 0.8 + 0.2 * math.cos(index * 0.13),
            breadth7d=(index % 21) / 20.0,
            drawdown_depth30d=(index % 29) / 100.0,
            rv24_future=sign * 1.4 * x + noise,
            market_return_future=sign * 0.8 * ((index % 21) / 20.0) + sign * 1.2 * ((index % 29) / 100.0) + noise,
        ))
    return tuple(rows)


def test_exact_return_rv_dispersion_and_breadth_recipes() -> None:
    returns = _returns([0.0] * 19 + [math.log(2.0)])
    assert harvest.asset_log_return(10.0, 20.0) == pytest.approx(math.log(2.0))
    assert harvest.market_hourly_return(returns) == pytest.approx(math.log(2.0) / 20)
    assert harvest.market_return_24([0.1] * 24) == pytest.approx(2.4)
    assert harvest.market_rv24([0.1] * 24) == pytest.approx(math.sqrt(0.24))
    assert harvest.dispersion24(_returns([0.0] * 19 + [20.0])) == pytest.approx(math.sqrt(20.0))
    assert harvest.breadth7d(_returns([0.0, *([1.0] * 19)])) == pytest.approx(19 / 20)


def test_breadth_treats_zero_as_not_positive() -> None:
    assert harvest.breadth7d(_returns([0.0] * 20)) == 0.0


def test_drawdown_is_positive_oriented_and_inclusive() -> None:
    assert harvest.drawdown_depth30d([1.0] * 721) == 0.0
    assert harvest.drawdown_depth30d([1.0] * 720 + [0.75]) == pytest.approx(0.25)


def test_outcome_starts_strictly_after_feature_boundary() -> None:
    decision = _utc(harvest.FIRST_DECISION)
    prior = tuple(decision - timedelta(hours=offset) for offset in range(23, -1, -1))
    future = tuple(decision + timedelta(hours=offset) for offset in range(1, 25))
    assert prior[-1] == decision
    assert future[0] == decision + timedelta(hours=1)
    assert set(prior).isdisjoint(future)


def test_schedule_is_mechanically_frozen_to_580_rows_and_final_outcome_fits() -> None:
    schedule = harvest.derive_common_schedule(first_bar_open=harvest.FIRST_BAR_OPEN, last_bar_open=harvest.LAST_BAR_OPEN)
    assert len(schedule) == 580
    assert schedule[0] == _utc(harvest.FIRST_DECISION)
    assert schedule[-1] == _utc(harvest.LAST_DECISION)
    assert schedule[-1] + timedelta(hours=24) == _utc("2025-06-20T00:00:00Z")
    assert schedule[-1] + timedelta(hours=24) == _utc(harvest.LAST_BAR_OPEN) + timedelta(hours=1)
    with pytest.raises(harvest.FrozenInputError, match="coverage"):
        harvest.derive_common_schedule(first_bar_open="2023-10-19T00:00:00Z", last_bar_open=harvest.LAST_BAR_OPEN)


def test_safe_known_after_and_gap_contracts_fail_closed() -> None:
    opened = _utc(harvest.FIRST_BAR_OPEN)
    valid = [harvest.BarClose(opened, 1.0, opened + timedelta(hours=1)), harvest.BarClose(opened + timedelta(hours=1), 1.1, opened + timedelta(hours=2))]
    with pytest.raises(harvest.FrozenInputError, match="coverage"):
        harvest._validate_hourly_partition(valid)
    invalid_known = [harvest.BarClose(opened, 1.0, opened)]
    with pytest.raises(harvest.FrozenInputError, match="safe-known-after"):
        harvest._validate_hourly_partition(invalid_known)


def test_snapshot_substitution_and_universe_mutation_rejected_before_real_execution() -> None:
    with pytest.raises(harvest.FrozenInputError, match="substitution"):
        harvest.validate_real_snapshot_identity(snapshot_id="wrong", snapshot_digest=harvest.EXPECTED_SNAPSHOT_DIGEST, universe=harvest.UNIVERSE)
    with pytest.raises(harvest.FrozenInputError, match="universe"):
        harvest.validate_real_snapshot_identity(snapshot_id=harvest.EXPECTED_SNAPSHOT_ID, snapshot_digest=harvest.EXPECTED_SNAPSHOT_DIGEST, universe=tuple(reversed(harvest.UNIVERSE)))
    with pytest.raises(harvest.RealExecutionDisabledError):
        harvest.real_execution_is_disabled(snapshot_id=harvest.EXPECTED_SNAPSHOT_ID, snapshot_digest=harvest.EXPECTED_SNAPSHOT_DIGEST, universe=harvest.UNIVERSE)


def test_hac_bandwidth_is_exactly_five_and_other_sample_sizes_block() -> None:
    assert harvest.primary_hac_bandwidth(580) == 5
    with pytest.raises(harvest.FrozenInputError):
        harvest.primary_hac_bandwidth(579)


def test_holm_is_deterministic_with_ties() -> None:
    adjusted = harvest.holm_adjust({identifier: 0.01 for identifier in harvest.PROPOSITION_IDS})
    assert list(adjusted) == list(harvest.PROPOSITION_IDS)
    assert list(adjusted.values()) == [0.04, 0.04, 0.04, 0.04]
    with pytest.raises(harvest.FrozenInputError):
        harvest.holm_adjust({"JH01_RV_PERSISTENCE": 0.01})


def test_classification_branches_are_frozen() -> None:
    assert harvest.classify(beta=0.2, interval=(0.01, 0.4), holm_p=0.01) == "SUPPORTED_WITHIN_FROZEN_SCOPE"
    assert harvest.classify(beta=-0.2, interval=(-0.4, -0.01), holm_p=0.9) == "NOT_SUPPORTED"
    assert harvest.classify(beta=0.2, interval=(-0.1, 0.4), holm_p=0.9) == "INCONCLUSIVE"


def test_synthetic_runner_emits_all_four_results_in_order_without_scientific_authority() -> None:
    result = harvest.analyze_synthetic_fixture(_rows())
    assert result["execution_mode"] == "SYNTHETIC_FIXTURE_ONLY"
    assert result["scientific_result"] == "NONE_SYNTHETIC_FIXTURE_ONLY"
    assert result["authority"] == harvest.AUTHORITY
    assert result["preregistration_digest"] == harvest.PREREGISTRATION_DIGEST
    assert result["snapshot_binding"] == "SYNTHETIC_FIXTURE_NO_REAL_SNAPSHOT"
    assert result["snapshot_id"] is None and result["snapshot_digest"] is None
    assert result["result_digest"] == harvest.result_digest(result)
    assert result["result_order"] == list(harvest.PROPOSITION_IDS)
    assert [item["proposition_id"] for item in result["results"]] == list(harvest.PROPOSITION_IDS)
    assert len(result["results"]) == 4


def test_opposite_synthetic_relation_is_retained_not_suppressed() -> None:
    result = harvest.analyze_synthetic_fixture(_rows(sign=-1.0))
    assert len(result["results"]) == 4
    assert any(item["classification"] == "NOT_SUPPORTED" for item in result["results"])


def test_wrong_schedule_blocks_the_whole_fixture() -> None:
    with pytest.raises(harvest.FrozenInputError, match="580"):
        harvest.analyze_synthetic_fixture(_rows()[:-1])


def test_preregistration_digest_is_deterministic_and_has_no_results() -> None:
    import json
    path = Path("experiments/research/jigsaw_harvest_v0/preregistration.json")
    value = json.loads(path.read_text())
    assert harvest.preregistration_digest(value) == value["preregistration_digest"]
    assert value["common_schedule"]["observation_count"] == 580
    assert value["estimator"]["hac"]["frozen_T"] == 580
    assert value["estimator"]["hac"]["derived_primary_hac_lag"] == 5
    correction = value["pre_execution_correction"]
    assert correction["previous_count"] == 579
    assert correction["corrected_count"] == 580
    assert correction["endpoints_changed"] is False
    assert correction["hypotheses_changed"] is False
    assert correction["scientific_results_seen"] is False
    assert value["status"] == "NOT_EXECUTED"
    assert "results" not in value


def test_runner_has_no_network_or_generic_recipe_surface() -> None:
    source = Path(harvest.__file__).read_text()
    assert "requests" not in source
    assert "urllib" not in source
    assert "recipe registry" not in source.lower()
    assert harvest.PROPOSITION_IDS == ("JH01_RV_PERSISTENCE", "JH02_DISPERSION_TO_RV", "JH03_BREADTH_TO_RETURN", "JH04_DRAWDOWN_TO_RETURN")
