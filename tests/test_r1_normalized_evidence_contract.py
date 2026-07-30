"""Operational-sufficiency fixtures for r1_normalized_evidence_contract_v1.json.

Synthetic-fixture proof only: demonstrates each frozen pre-outcome operation
can be computed from the normalized evidence contract fields alone, with no
discarded raw field. Uses fabricated prices/rates, never real R1 data, and
never computes an R1 hypothesis outcome (no ranking, no return, no PnL).
"""
from __future__ import annotations

from datetime import date, timedelta


def synthetic_daily_row(utc_date: str, close, quote_turnover, trade_count=1):
    return {
        "utc_date": utc_date,
        "close": close,
        "quote_turnover": quote_turnover,
        "trade_count": trade_count,
    }


def pit_eligible(rows: list[dict], t_index: int, *, finite_close_days=90, finite_volume_days=30, min_breadth=1) -> bool:
    """Uses ONLY DailyMarketEvidenceV1.close / .quote_turnover / .trade_count."""
    window = rows[max(0, t_index - finite_close_days + 1): t_index + 1]
    if len(window) < finite_close_days:
        return False
    if any(row["close"] is None for row in window):
        return False
    vol_window = rows[max(0, t_index - finite_volume_days + 1): t_index + 1]
    if len(vol_window) < finite_volume_days or any(row["quote_turnover"] is None for row in vol_window):
        return False
    return True


def h012_momentum_score(rows: list[dict], t_index: int, lookback_days: int):
    """Uses ONLY DailyMarketEvidenceV1.close."""
    if t_index - lookback_days < 0:
        return None
    a, b = rows[t_index]["close"], rows[t_index - lookback_days]["close"]
    if a is None or b is None:
        return None
    return a / b - 1


def h014_funding_score(funding_rows: list[dict], t_utc_date: str, lookback_days: int):
    """Uses ONLY FundingSettlementEvidenceV1.settlement_timestamp_utc / .realized_funding_rate / .assignment_state."""
    t = date.fromisoformat(t_utc_date)
    window_start = t - timedelta(days=lookback_days)
    total, any_missing = 0.0, False
    for row in funding_rows:
        ts = date.fromisoformat(row["settlement_timestamp_utc"][:10])
        if window_start < ts <= t:
            if row["assignment_state"] != "ASSIGNED" or row["realized_funding_rate"] is None:
                any_missing = True
            else:
                total += row["realized_funding_rate"]
    return None if any_missing else total


def _make_90d_close_series(closes: list[float]) -> list[dict]:
    start = date(2024, 1, 1)
    return [synthetic_daily_row((start + timedelta(days=i)).isoformat(), c, 1000.0) for i, c in enumerate(closes)]


def test_pit_eligibility_uses_only_contract_fields_and_needs_full_windows():
    rows = _make_90d_close_series([100.0] * 90)
    assert pit_eligible(rows, 89, finite_close_days=90, finite_volume_days=30) is True
    assert pit_eligible(rows, 88, finite_close_days=90, finite_volume_days=30) is False


def test_pit_eligibility_excludes_on_missing_close_never_imputes():
    rows = _make_90d_close_series([100.0] * 90)
    rows[45]["close"] = None
    assert pit_eligible(rows, 89, finite_close_days=90, finite_volume_days=30) is False


def test_h012_momentum_score_uses_only_close_field_both_lookbacks():
    rows = _make_90d_close_series([100.0 + i for i in range(120)])
    assert h012_momentum_score(rows, 100, 30) == rows[100]["close"] / rows[70]["close"] - 1
    assert h012_momentum_score(rows, 100, 90) == rows[100]["close"] / rows[10]["close"] - 1


def test_h012_momentum_score_none_before_complete_lookback():
    rows = _make_90d_close_series([100.0] * 10)
    assert h012_momentum_score(rows, 5, 30) is None


def test_h014_funding_score_sums_only_settled_events_in_window():
    funding = [
        {"settlement_timestamp_utc": "2024-06-01T08:00:00Z", "realized_funding_rate": 0.0001, "assignment_state": "ASSIGNED"},
        {"settlement_timestamp_utc": "2024-06-01T16:00:00Z", "realized_funding_rate": 0.0002, "assignment_state": "ASSIGNED"},
        {"settlement_timestamp_utc": "2024-05-20T00:00:00Z", "realized_funding_rate": 0.9, "assignment_state": "ASSIGNED"},
    ]
    assert abs(h014_funding_score(funding, "2024-06-01", 1) - 0.0003) < 1e-12


def test_h014_funding_score_missing_or_unassigned_event_in_window_is_none_not_imputed():
    funding = [
        {"settlement_timestamp_utc": "2024-06-01T08:00:00Z", "realized_funding_rate": 0.0001, "assignment_state": "ASSIGNED"},
        {"settlement_timestamp_utc": "2024-06-01T16:00:00Z", "realized_funding_rate": None, "assignment_state": "UNASSIGNED_AMBIGUOUS"},
    ]
    assert h014_funding_score(funding, "2024-06-01", 1) is None


def test_breadth_gate_needs_only_pit_eligibility_no_additional_field():
    rows_a = _make_90d_close_series([100.0] * 90)
    rows_b = _make_90d_close_series([50.0] * 90)
    eligible_count = sum(1 for rows in (rows_a, rows_b) if pit_eligible(rows, 89, finite_close_days=90, finite_volume_days=30))
    assert eligible_count == 2
