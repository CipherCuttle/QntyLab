from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from qntylab import jfp_v2_pr_b as prb


def panel(value: float = 0.01) -> dict[str, float]:
    return {symbol: value + index / 1000 for index, symbol in enumerate(prb.PANEL)}


def hourly_rows() -> list[dict[str, float]]:
    return [{symbol: ((-1 if (hour + index) % 3 == 0 else 1) * (0.001 + index / 100000)) for index, symbol in enumerate(prb.PANEL)} for hour in range(24)]


def test_frozen_source_binding_and_schedule_are_structural_only(tmp_path):
    receipts = prb.materialize_structural_receipts(tmp_path)
    assert receipts["binding"]["source_identity"] == prb.SOURCE_ID
    assert receipts["binding"]["exact_panel"] == list(prb.PANEL)
    assert receipts["integrity"]["source_integrity_pass"] is True
    assert len(receipts["schedule"]["origins"]) == 608
    assert receipts["schedule"]["origins"][0]["origin_timestamp"] == prb.ANALYSIS_START
    assert receipts["schedule"]["schedule_digest"] == prb.digest(prb.origin_schedule())


def test_jfpv2_04_features_and_sample_sd():
    returns = panel()
    assert prb.hourly_log_return(100.0, 101.0) == pytest.approx(0.009950330853168092)
    assert prb.concentration(returns) == pytest.approx(max(map(abs, returns.values())) / sum(map(abs, returns.values())))
    assert prb.sample_sd((1.0, 2.0, 4.0)) == pytest.approx(1.5275252316519468)
    assert prb.sample_sd(tuple(returns.values())) > 0


def test_jfpv2_06_windows():
    rows = hourly_rows()
    assert 0 < prb.downside_share(rows) < 1
    assert prb.panel_rv24(rows) == pytest.approx((sum(x * x for row in rows for x in row.values())) ** 0.5)


@pytest.mark.parametrize("fn", [lambda: prb.concentration({symbol: 0.0 for symbol in prb.PANEL}), lambda: prb.downside_share([{symbol: 0.0 for symbol in prb.PANEL} for _ in range(24)])])
def test_zero_feature_domains_block(fn):
    with pytest.raises(prb.PRBBlocked, match="BLOCKED_INVALID_FEATURE_DOMAIN"):
        fn()


def test_ols_hac_matches_independent_direct_oracle_and_hac_l0_larger():
    design = [[1.0, float(i), float(i % 4)] for i in range(12)]
    outcome = [2.0 + 0.5 * i + 0.25 * (i % 4) + (0.01 if i % 2 else -0.01) for i in range(12)]
    result = prb.ols_hac(design, outcome, 0)
    # Independent normal-equation oracle; it does not call any production
    # OLS/HAC/Holm/classification helper.
    normal = [[sum(row[i] * row[j] for row in design) for j in range(3)] for i in range(3)]
    rhs = [sum(row[i] * y for row, y in zip(design, outcome)) for i in range(3)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda row: abs(normal[row][col]))
        normal[col], normal[pivot] = normal[pivot], normal[col]
        rhs[col], rhs[pivot] = rhs[pivot], rhs[col]
        scale = normal[col][col]
        normal[col] = [value / scale for value in normal[col]]
        rhs[col] /= scale
        for row in range(3):
            if row != col:
                scale = normal[row][col]
                normal[row] = [a - scale * b for a, b in zip(normal[row], normal[col])]
                rhs[row] -= scale * rhs[col]
    oracle_beta_x = rhs[-1]
    assert result["beta"] == pytest.approx(oracle_beta_x, abs=1e-12)
    assert result["hac_standard_error"] > 0
    assert prb.ols_hac(design, outcome, 3)["hac_standard_error"] != result["hac_standard_error"]


def test_rank_deficiency_is_blocked():
    with pytest.raises(prb.PRBBlocked, match="MODEL_IDENTIFIABLE=false"):
        prb.ols_hac([[1.0, 2.0, 2.0] for _ in range(5)], [1, 2, 3, 4, 5], 0)


def test_holm_keeps_blocked_member_and_classification():
    adjusted = prb.holm_two({"JFPV2_04": 0.01, "JFPV2_06": None})
    assert adjusted == {"JFPV2_04": pytest.approx(0.02), "JFPV2_06": None}
    assert prb.classify(beta=1.0, raw_p=0.001, holm_p=0.002, materiality_pass=True) == "HISTORICAL_SCREEN_SUPPORT"
    assert prb.classify(beta=-1.0, raw_p=0.001, holm_p=0.002, materiality_pass=True) == "HISTORICAL_SCREEN_NO_SUPPORT"
    assert prb.classify(beta=None, raw_p=None, holm_p=None, materiality_pass=False, blocked="domain") == "BLOCKED_CANDIDATE"


def test_real_rds_scientific_execution_is_fail_closed():
    with pytest.raises(prb.PRBBlocked, match="REFUSED"):
        prb.real_execution_is_disabled(mode="PR_B_PHASE", source_id=prb.SOURCE_ID)


def test_deterministic_synthetic_serialization_and_result_schema():
    design = [[1.0, float(i)] for i in range(10)]
    outcome = [1.0 + 0.2 * i + (0.01 if i % 2 else -0.01) for i in range(10)]
    fit = prb.ols_hac(design, outcome, 0)
    result = {field: None for field in prb.RESULT_FIELDS}
    result.update({"candidate_id": "JFPV2_04", "beta_candidate": fit["beta"], "hac_standard_error": fit["hac_standard_error"], "raw_p_two_sided": fit["raw_p"], "holm_adjusted_p": fit["raw_p"], "classification": "HISTORICAL_SCREEN_NO_SUPPORT"})
    first = prb.digest(result)
    second = prb.digest(json.loads(json.dumps(result, sort_keys=True)))
    assert first == second
    assert tuple(result) == prb.RESULT_FIELDS
