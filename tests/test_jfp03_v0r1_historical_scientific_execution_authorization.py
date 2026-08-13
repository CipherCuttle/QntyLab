from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pytest

from qntylab import jfp03_v0r1_historical_scientific_execution as execution


ROOT = Path(__file__).resolve().parents[1]


def _bound_workspace_identity() -> dict[str, object]:
    return {
        "workspace_root": str(execution.EXECUTION_WORKSPACE_ROOT),
        "git_common_dir": str(execution.EXECUTION_GIT_COMMON_DIR),
        "git_common_dir_device": execution.EXECUTION_GIT_COMMON_DIR_DEVICE,
        "git_common_dir_inode": execution.EXECUTION_GIT_COMMON_DIR_INODE,
    }


def _verify_fixture(root: Path) -> dict[str, object]:
    return execution.verify_frozen_bindings(
        root,
        _workspace_identity_for_test=_bound_workspace_identity(),
    )


def _rewrite_with_digest(path: Path, field: str, mutate) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    value[field] = execution.object_digest(value, omitted_field=field)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


@pytest.fixture()
def frozen_root(tmp_path: Path) -> Path:
    for relative in (
        execution.MODULE_RELATIVE,
        execution.AUTHORIZATION_RELATIVE,
        execution.SNAPSHOT_RELATIVE,
        execution.QUALIFICATION_RELATIVE,
        execution.SOURCE_MANIFEST_RELATIVE,
        Path("docs/state/projects.toml"),
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    return tmp_path


def _synthetic_rows(count: int = 160) -> tuple[execution.DesignRow, ...]:
    rows = []
    for index in range(count):
        h1 = 1.0 + 0.003 * index + 0.07 * math.sin(index * 0.31)
        h24 = 2.0 + math.sqrt(index + 1) / 20.0
        h168 = 3.0 + 0.2 * math.sin(index * 0.13)
        h720 = 4.0 + 0.3 * math.cos(index * 0.07)
        afi = (index % 17) / 16.0
        noise = 0.02 * math.sin(index * 0.91) + 0.01 * math.cos(index * 0.43)
        target = 0.4 + 0.2 * h1 - 0.03 * h24 + 0.05 * h168 + 0.04 * h720 + 0.08 * afi + noise
        rows.append(
            execution.DesignRow(
                decision_time_ms=execution.FIRST_DECISION_MS + index * execution.HOUR_MS,
                har_1h=h1,
                har_24h=h24,
                har_168h=h168,
                har_720h=h720,
                afi=afi,
                rv24_future=target,
            )
        )
    return tuple(rows)


def test_exact_snapshot_design_executor_and_authorization_bindings() -> None:
    verified = execution.verify_frozen_bindings(ROOT)
    assert verified["snapshot"]["snapshot_id"] == execution.SNAPSHOT_ID
    assert verified["snapshot"]["snapshot_digest"] == execution.SNAPSHOT_DIGEST
    assert verified["qualification"]["qualification_digest"] == execution.QUALIFICATION_DIGEST
    assert verified["qualification"]["input_qualification"] == "READY"
    assert verified["authorization"]["design_digest"] == execution.DESIGN_DIGEST
    assert verified["authorization"]["historical_scientific_execution_runs_allowed"] == 1
    assert verified["authorization"]["historical_scientific_execution_runs_consumed"] == 0
    assert verified["executor_implementation_sha256"] == execution.file_sha256(ROOT / execution.MODULE_RELATIVE)
    assert verified["executor_contract_digest"] == execution.executor_contract_digest()


def test_wrong_snapshot_is_rejected_even_if_tampered_artifact_is_self_consistent(frozen_root: Path) -> None:
    path = frozen_root / execution.SNAPSHOT_RELATIVE
    value = json.loads(path.read_text(encoding="utf-8"))
    value["snapshot_id"] = "wrong-snapshot"
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(execution.ExecutionContractError, match="snapshot identity"):
        _verify_fixture(frozen_root)


def test_wrong_design_digest_is_rejected(frozen_root: Path) -> None:
    path = frozen_root / execution.AUTHORIZATION_RELATIVE
    _rewrite_with_digest(path, "authorization_digest", lambda value: value.update(design_digest="0" * 64))
    with pytest.raises(execution.ExecutionContractError, match="design digest"):
        _verify_fixture(frozen_root)


def test_wrong_executor_identity_is_rejected(frozen_root: Path) -> None:
    path = frozen_root / execution.AUTHORIZATION_RELATIVE
    _rewrite_with_digest(
        path,
        "authorization_digest",
        lambda value: value.update(executor_implementation_sha256="0" * 64),
    )
    with pytest.raises(execution.ExecutionContractError, match="executor implementation identity"):
        _verify_fixture(frozen_root)


@pytest.mark.parametrize(
    "field",
    [
        "numpy_version",
        "platform_release",
        "libc_version",
        "python_compiler",
        "python_build_date",
        "python_cache_tag",
        "python_soabi",
    ],
)
def test_wrong_runtime_identity_is_rejected_before_claim(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    drifted = {**execution.FROZEN_RUNTIME_IDENTITY, field: "different"}
    monkeypatch.setattr(execution, "runtime_identity", lambda: drifted)
    with pytest.raises(execution.ExecutionContractError, match="runtime identity"):
        execution.verify_frozen_bindings(ROOT)


def test_wrong_execution_workspace_is_rejected(frozen_root: Path) -> None:
    drifted = {**_bound_workspace_identity(), "git_common_dir_inode": 1}
    with pytest.raises(execution.ExecutionContractError, match="workspace identity"):
        execution.verify_frozen_bindings(
            frozen_root,
            _workspace_identity_for_test=drifted,
        )


def test_exact_afi_formula_and_quote_volume_denominator() -> None:
    assert execution.afi(100.0, 65.0) == pytest.approx(abs(2.0 * 0.65 - 1.0))
    assert execution.afi(100.0, 35.0) == pytest.approx(execution.afi(100.0, 65.0))
    parsed = execution._parse_source_row(
        [0, "1", "2", "0.5", "1.5", "999", execution.HOUR_MS - 1, "200", 8, "888", "125", "0"]
    )
    assert parsed.total_quote_volume == 200
    assert parsed.taker_buy_quote_volume == 125
    assert execution.afi(parsed.total_quote_volume, parsed.taker_buy_quote_volume) == pytest.approx(0.25)


@pytest.mark.parametrize("denominator", [0.0, -1.0, math.nan, math.inf])
def test_zero_or_invalid_afi_denominator_fails_closed(denominator: float) -> None:
    with pytest.raises(execution.ExecutionContractError):
        execution.afi(denominator, 1.0)


def test_return_uses_hourly_close_boundaries_and_positive_finite_prices() -> None:
    row = execution.Kline(
        open_time_ms=1_600_000 * execution.HOUR_MS,
        close_time_ms=1_600_001 * execution.HOUR_MS - 1,
        close=102.0,
        total_quote_volume=10.0,
        taker_buy_quote_volume=6.0,
    )
    assert row.close_boundary_ms == row.open_time_ms + execution.HOUR_MS
    assert execution.log_return(100.0, row.close) == pytest.approx(math.log(1.02))
    for bad in (0.0, -1.0, math.nan, math.inf):
        with pytest.raises(execution.ExecutionContractError):
            execution.log_return(100.0, bad)


def test_har_windows_are_exact_sqrt_sums_without_normalization() -> None:
    decision = execution.FIRST_DECISION_MS
    returns = {
        decision - offset * execution.HOUR_MS: (offset + 1) / 1000.0
        for offset in range(720)
    }
    actual = execution.har_features(decision, returns)
    for value, hours in zip(actual, (1, 24, 168, 720), strict=True):
        boundaries = execution.baseline_return_boundaries_ms(decision, hours)
        expected = math.sqrt(sum(returns[item] ** 2 for item in boundaries))
        assert value == pytest.approx(expected)
    assert execution.baseline_return_boundaries_ms(decision, 1) == (decision,)


def test_first_har720_and_future_target_boundaries_are_exact_and_disjoint() -> None:
    baseline = execution.baseline_return_boundaries_ms(execution.FIRST_DECISION_MS, 720)
    target = execution.target_return_boundaries_ms(execution.FIRST_DECISION_MS)
    assert baseline[0] == execution.FIRST_DECISION_MS - 719 * execution.HOUR_MS
    assert baseline[-1] == execution.FIRST_DECISION_MS
    assert baseline[0] - execution.HOUR_MS == execution.FIRST_REQUIRED_CLOSE_MS
    assert target[0] == execution.FIRST_DECISION_MS + execution.HOUR_MS
    assert target[-1] == execution.FIRST_DECISION_MS + 24 * execution.HOUR_MS
    assert set(baseline).isdisjoint(target)
    returns = {boundary: 0.01 for boundary in target}
    assert execution.future_target(execution.FIRST_DECISION_MS, returns) == pytest.approx(math.sqrt(24) * 0.01)


def test_exact_inclusive_hourly_decision_schedule_and_no_row_dropping() -> None:
    schedule = execution.canonical_schedule_ms()
    assert schedule[0] == execution.FIRST_DECISION_MS
    assert schedule[-1] == execution.LAST_DECISION_MS
    assert len(schedule) == execution.OBSERVATION_COUNT == 43_848
    assert all(right - left == execution.HOUR_MS for left, right in zip(schedule, schedule[1:]))
    assert len(execution.expected_close_boundaries_ms()) == 44_592
    with pytest.raises(execution.ExecutionContractError, match="row dropping prohibited"):
        execution.build_design_rows(())
    rows = list(_synthetic_rows())
    rows[10] = execution.DesignRow(**{**rows[10].__dict__, "afi": math.nan})
    with pytest.raises(execution.ExecutionContractError, match="row dropping prohibited"):
        execution.fit_frozen_models(rows)


def test_frozen_source_range_selection_allows_only_trailing_out_of_scope_rows() -> None:
    expected = (execution.HOUR_MS, 2 * execution.HOUR_MS)
    rows = tuple(
        execution.Kline(
            open_time_ms=index * execution.HOUR_MS,
            close_time_ms=(index + 1) * execution.HOUR_MS - 1,
            close=100.0 + index,
            total_quote_volume=10.0,
            taker_buy_quote_volume=6.0,
        )
        for index in range(3)
    )
    assert tuple(row.close_boundary_ms for row in execution.select_frozen_coverage(rows, expected)) == expected
    with pytest.raises(execution.ExecutionContractError, match="leading row"):
        execution.select_frozen_coverage(rows, expected[1:])
    with pytest.raises(execution.ExecutionContractError, match="complete coverage"):
        execution.select_frozen_coverage((rows[0], rows[2]), expected)


def test_baseline_and_full_models_use_one_identical_complete_sample() -> None:
    rows = _synthetic_rows()
    result = execution.fit_frozen_models(rows)
    assert result["observation_count"] == len(rows)
    assert result["common_sample_pass"] is True
    assert result["hac_lag"] == 24
    assert result["hac_kernel"] == "BARTLETT_NEWEY_WEST"
    assert result["hac_lag_selection"] == "NONE"
    assert result["inference_reference"] == "ASYMPTOTIC_NORMAL_Z_TWO_SIDED"


def test_newey_west_uses_every_bartlett_lag_through_24() -> None:
    rows = _synthetic_rows(80)
    values = np.asarray(
        [[row.har_1h, row.har_24h, row.har_168h, row.har_720h, row.afi, row.rv24_future] for row in rows],
        dtype=np.float64,
    )
    x = np.column_stack((np.ones(len(rows)), values[:, :5]))
    beta = np.linalg.lstsq(x, values[:, 5], rcond=None)[0]
    residuals = values[:, 5] - x @ beta
    actual = execution._newey_west_covariance(x, residuals)

    bread = np.linalg.inv(x.T @ x)
    scores = x * residuals[:, None]
    meat = np.zeros((6, 6), dtype=np.float64)
    for score in scores:
        meat += np.outer(score, score)
    for lag in range(1, 25):
        weight = 1.0 - lag / 25.0
        for current in range(lag, len(rows)):
            meat += weight * (
                np.outer(scores[current], scores[current - lag])
                + np.outer(scores[current - lag], scores[current])
            )
    expected = bread @ meat @ bread
    assert np.allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_partial_r2_formula_and_inclusive_materiality_gate_are_exact() -> None:
    assert execution.partial_r2(100.0, 99.9) == pytest.approx(0.001)
    assert execution.support_classification(
        gamma=1e-9,
        raw_p_value=execution.RAW_ALPHA_GATE,
        partial_r2_value=execution.PARTIAL_R2_GATE,
    ) == "DISCOVERY_SUPPORTED_WITHIN_FROZEN_SCOPE"
    assert execution.support_classification(
        gamma=1e-9,
        raw_p_value=execution.RAW_ALPHA_GATE,
        partial_r2_value=execution.PARTIAL_R2_GATE - 1e-12,
    ) == "NO_DISCOVERY_SUPPORT_FOUND"


def test_direction_raw_alpha_and_holm_gates_are_exact() -> None:
    assert execution.RAW_ALPHA_GATE == 0.05 / 3
    assert execution.support_classification(
        gamma=0.0,
        raw_p_value=execution.RAW_ALPHA_GATE,
        partial_r2_value=execution.PARTIAL_R2_GATE,
    ) == "NO_DISCOVERY_SUPPORT_FOUND"
    assert execution.support_classification(
        gamma=1.0,
        raw_p_value=execution.RAW_ALPHA_GATE + 1e-12,
        partial_r2_value=execution.PARTIAL_R2_GATE,
    ) == "NO_DISCOVERY_SUPPORT_FOUND"
    family = execution.multiplicity_family(0.4, "NO_DISCOVERY_SUPPORT_FOUND")
    assert family[2]["status"] == "NO_DISCOVERY_SUPPORT_FOUND"
    assert family[2]["holm_adjusted_p_value"] == 1.0
    assert execution.multiplicity_family(0.01, "DISCOVERY_SUPPORTED_WITHIN_FROZEN_SCOPE")[2]["holm_adjusted_p_value"] == pytest.approx(0.03)


def test_blocked_jfp01_jfp02_scientific_values_remain_null_not_p_one() -> None:
    family = execution.multiplicity_family(0.01, "DISCOVERY_SUPPORTED_WITHIN_FROZEN_SCOPE")
    assert [record["candidate_id"] for record in family] == ["JFP01", "JFP02", "JFP03"]
    for record in family[:2]:
        assert record["status"] == "BLOCKED_CANDIDATE"
        assert record["raw_p_value"] is None
        assert record["holm_adjusted_p_value"] is None
    blocked_jfp03 = execution.multiplicity_family(None, "BLOCKED_CANDIDATE")[2]
    assert blocked_jfp03["status"] == "BLOCKED_CANDIDATE"
    assert blocked_jfp03["raw_p_value"] is None
    assert blocked_jfp03["holm_adjusted_p_value"] is None


def test_execution_claim_is_durable_and_replay_fails_closed(frozen_root: Path) -> None:
    verified = _verify_fixture(frozen_root)
    shared_claim = frozen_root / "shared-git-common-dir" / execution.CLAIM_GIT_COMMON_RELATIVE
    verified["claim_path"] = shared_claim
    first_worktree = frozen_root / "worktree-one"
    second_worktree = frozen_root / "worktree-two"
    first_worktree.mkdir()
    second_worktree.mkdir()
    claim = execution.claim_execution(first_worktree, verified)
    assert claim["historical_scientific_execution_runs_consumed_after"] == 1
    on_disk = json.loads(shared_claim.read_text(encoding="utf-8"))
    assert on_disk["start_digest"] == execution.object_digest(on_disk, omitted_field="start_digest")
    with pytest.raises(execution.ExecutionAlreadyClaimed):
        execution.claim_execution(second_worktree, verified)


def test_source_loader_refuses_access_before_one_shot_claim() -> None:
    verified = execution.verify_frozen_bindings(ROOT)
    with pytest.raises(execution.ExecutionContractError, match="claim required"):
        execution.load_frozen_klines(ROOT, verified)


def test_scientific_result_envelope_cannot_authorize_downstream_systems() -> None:
    envelope = execution._result_envelope(
        {
            "executor_implementation_sha256": execution.file_sha256(ROOT / execution.MODULE_RELATIVE),
            "executor_contract_digest": execution.executor_contract_digest(),
            "runtime_identity": execution.FROZEN_RUNTIME_IDENTITY,
            "runtime_identity_digest": execution.runtime_identity_digest(execution.FROZEN_RUNTIME_IDENTITY),
        }
    )
    assert envelope["downstream_authority"] == "NONE"
    assert envelope["capital_authority"] == "NONE"
    for field in (
        "jigsaw_synthesis_authorized",
        "state_snapshot_authorized",
        "forecaster_authorized",
        "router_authorized",
        "qnty_authorized",
        "paper_trading_authorized",
        "trading_authorized",
    ):
        assert envelope[field] is False
    contract = execution.executor_contract()
    assert contract["downstream_authority"] == "NONE"
    assert contract["network_access"] == "PROHIBITED_NOT_IMPLEMENTED"
    assert tuple(contract["output_fields"]) == execution.OUTPUT_FIELDS
