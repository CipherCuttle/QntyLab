"""Synthetic-fixture-only tests for the JIGSAW_FUNDING_PRESSURE_VOLATILITY_V0
executor.

Hard invariant: nothing in this file reads or references the real certified
610-decision evidence set under
``experiments/research/jigsaw_funding_pressure_volatility_v0``. All numeric
fixtures below are artificial and hand-checkable.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest

from qntylab import jigsaw_funding_pressure_volatility_execution_v0 as ex


def _event(symbol: str, iso: str, rate: str) -> ex.FundingEvent:
    ms = int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)
    return ex.FundingEvent(symbol=symbol, funding_time_ms=ms, funding_time_utc=iso, funding_rate=rate)


DECISION = datetime(2024, 1, 2, 0, 0, 0, tzinfo=UTC)


# --------------------------------------------------------------------------
# select_latest_funding_event -- Funding PIT
# --------------------------------------------------------------------------


def test_event_exactly_at_decision_time_accepted():
    e = _event("BCHUSDT", "2024-01-02T00:00:00Z", "0.0001")
    assert ex.select_latest_funding_event([e], DECISION) == e


def test_event_before_decision_time_accepted():
    e = _event("BCHUSDT", "2024-01-01T12:00:00Z", "0.0001")
    assert ex.select_latest_funding_event([e], DECISION) == e


def test_future_event_rejected():
    e = _event("BCHUSDT", "2024-01-02T00:00:01Z", "0.0001")
    assert ex.select_latest_funding_event([e], DECISION) is None


def test_event_exactly_24h_old_rejected_per_strict_boundary():
    # decision_time - 24h < funding_time is required (strict); an event
    # exactly at decision_time-24h fails the strict lower bound.
    e = _event("BCHUSDT", "2024-01-01T00:00:00Z", "0.0001")
    assert ex.select_latest_funding_event([e], DECISION) is None


def test_event_one_second_within_24h_boundary_accepted():
    e = _event("BCHUSDT", "2024-01-01T00:00:01Z", "0.0001")
    got = ex.select_latest_funding_event([e], DECISION)
    assert got is not None and got == e


def test_stale_event_rejected():
    e = _event("BCHUSDT", "2023-12-30T00:00:00Z", "0.0001")
    assert ex.select_latest_funding_event([e], DECISION) is None


def test_missing_member_event_stream_yields_none():
    assert ex.select_latest_funding_event([], DECISION) is None


def test_latest_of_multiple_admissible_events_is_selected():
    older = _event("BCHUSDT", "2024-01-01T06:00:00Z", "0.0001")
    newer = _event("BCHUSDT", "2024-01-01T18:00:00Z", "0.0002")
    assert ex.select_latest_funding_event([older, newer], DECISION) == newer


def test_duplicate_timestamp_with_disagreeing_rate_fails_closed():
    a = _event("BCHUSDT", "2024-01-01T18:00:00Z", "0.0001")
    b = _event("BCHUSDT", "2024-01-01T18:00:00Z", "0.0002")
    with pytest.raises(ex.DuplicateFundingTimestampError):
        ex.select_latest_funding_event([a, b], DECISION)


def test_duplicate_timestamp_with_agreeing_rate_is_not_an_error():
    a = _event("BCHUSDT", "2024-01-01T18:00:00Z", "0.0001")
    b = _event("BCHUSDT", "2024-01-01T18:00:00Z", "0.0001")
    assert ex.select_latest_funding_event([a, b], DECISION) == a


def test_decision_time_must_be_exact_midnight():
    with pytest.raises(ValueError):
        ex.select_latest_funding_event([], datetime(2024, 1, 2, 1, 0, 0, tzinfo=UTC))


# --------------------------------------------------------------------------
# compute_funding_pressure -- panel median
# --------------------------------------------------------------------------


def _full_panel_events(rates: dict[str, str]) -> dict[str, ex.FundingEvent | None]:
    return {symbol: _event(symbol, "2024-01-01T12:00:00Z", rates[symbol]) for symbol in rates}


def test_median_even_n20_is_average_of_two_middle_order_statistics():
    rates = {symbol: str(i) for i, symbol in enumerate(ex.PANEL, start=1)}  # 1..20
    result = ex.compute_funding_pressure(_full_panel_events(rates))
    assert result == Decimal("10.5")


def test_median_is_independent_of_dict_insertion_order():
    rates = {symbol: str(i) for i, symbol in enumerate(ex.PANEL, start=1)}
    forward = _full_panel_events(rates)
    reversed_order = dict(reversed(list(forward.items())))
    assert ex.compute_funding_pressure(forward) == ex.compute_funding_pressure(reversed_order)


def test_missing_one_of_twenty_members_fails_closed():
    rates = {symbol: "0.0001" for symbol in ex.PANEL}
    panel = _full_panel_events(rates)
    del panel[ex.PANEL[0]]
    assert ex.compute_funding_pressure(panel) is None


def test_nonfinite_rate_fails_closed():
    rates = {symbol: "0.0001" for symbol in ex.PANEL}
    panel = _full_panel_events(rates)
    panel[ex.PANEL[0]] = _event(ex.PANEL[0], "2024-01-01T12:00:00Z", "NaN")
    assert ex.compute_funding_pressure(panel) is None


def test_absolute_value_transform_applied():
    rates = {symbol: "0.0001" for symbol in ex.PANEL}
    rates[ex.PANEL[0]] = "-0.0005"
    panel = _full_panel_events(rates)
    result = ex.compute_funding_pressure(panel)
    assert result is not None and result > 0


def test_none_event_for_a_member_fails_closed():
    rates = {symbol: "0.0001" for symbol in ex.PANEL}
    panel = _full_panel_events(rates)
    panel[ex.PANEL[0]] = None
    assert ex.compute_funding_pressure(panel) is None


# --------------------------------------------------------------------------
# compute_pit_ecdf / classify_funding_state -- ECDF and bins
# --------------------------------------------------------------------------


def test_ecdf_requires_exactly_365_prior_observations():
    with pytest.raises(ValueError):
        ex.compute_pit_ecdf([Decimal(1)] * 364, Decimal(1))


def test_exact_low_boundary_one_third_is_inclusive_and_reachable():
    prior = [Decimal(i) for i in range(1, 366)]
    current = Decimal(121)
    pct = ex.compute_pit_ecdf(prior, current)
    assert pct == Fraction(1, 3)
    assert ex.classify_funding_state(pct) == "LOW"


def test_exact_high_boundary_two_thirds_is_inclusive_and_reachable():
    prior = [Decimal(i) for i in range(1, 366)]
    current = Decimal(243)
    pct = ex.compute_pit_ecdf(prior, current)
    assert pct == Fraction(2, 3)
    assert ex.classify_funding_state(pct) == "HIGH"


def test_mid_is_reachable_strictly_between_thirds():
    prior = [Decimal(i) for i in range(1, 366)]
    current = Decimal(180)
    pct = ex.compute_pit_ecdf(prior, current)
    assert ex.LOW_THRESHOLD < pct < ex.HIGH_THRESHOLD
    assert ex.classify_funding_state(pct) == "MID"


def test_tie_semantics_are_inclusive_le():
    prior = [Decimal(5)] * 365
    current = Decimal(5)
    pct = ex.compute_pit_ecdf(prior, current)
    assert pct == Fraction(366, 366)
    assert ex.classify_funding_state(pct) == "HIGH"


def test_current_observation_is_included_in_the_population():
    # Every prior observation is strictly greater than current, so without
    # counting current itself the count would be 0/365 = 0. Including
    # current (which is trivially <= itself) makes it 1/366.
    prior = [Decimal(1000)] * 365
    current = Decimal(1)
    pct = ex.compute_pit_ecdf(prior, current)
    assert pct == Fraction(1, 366)


# --------------------------------------------------------------------------
# compute_hourly_asset_returns / compute_equal_weight_market_returns
# --------------------------------------------------------------------------


def test_simple_close_to_close_return_is_hand_computable():
    prior = {s: 100.0 for s in ex.PANEL}
    closes = {s: 101.0 for s in ex.PANEL}
    returns = ex.compute_hourly_asset_returns(closes, prior)
    assert returns[ex.PANEL[0]] == pytest.approx(0.01)
    assert len(returns) == 20


def test_market_return_requires_20_of_20():
    prior = {s: 100.0 for s in ex.PANEL}
    closes = {s: 101.0 for s in ex.PANEL}
    del closes[ex.PANEL[0]]
    returns = ex.compute_hourly_asset_returns(closes, prior)
    assert len(returns) == 19
    market = ex.compute_equal_weight_market_returns([returns])
    assert market == [None]


def test_missing_close_excludes_member_return():
    prior = {s: 100.0 for s in ex.PANEL}
    closes = {s: 101.0 for s in ex.PANEL}
    del closes[ex.PANEL[3]]
    returns = ex.compute_hourly_asset_returns(closes, prior)
    assert ex.PANEL[3] not in returns


def test_nonpositive_close_excludes_member_return():
    prior = {s: 100.0 for s in ex.PANEL}
    closes = {s: 101.0 for s in ex.PANEL}
    closes[ex.PANEL[3]] = 0.0
    returns = ex.compute_hourly_asset_returns(closes, prior)
    assert ex.PANEL[3] not in returns
    closes[ex.PANEL[3]] = -5.0
    returns = ex.compute_hourly_asset_returns(closes, prior)
    assert ex.PANEL[3] not in returns


def test_equal_weight_market_return_is_hand_computable():
    prior = {s: 100.0 for s in ex.PANEL}
    closes = dict(prior)
    for i, s in enumerate(ex.PANEL):
        closes[s] = 100.0 + i  # different returns per member
    returns = ex.compute_hourly_asset_returns(closes, prior)
    market = ex.compute_equal_weight_market_returns([returns])[0]
    expected = sum((100.0 + i) / 100.0 - 1.0 for i in range(20)) / 20
    assert market == pytest.approx(expected)


# --------------------------------------------------------------------------
# compute_rv24 -- zero-mean estimator, no annualization
# --------------------------------------------------------------------------


def test_rv24_requires_exactly_24_observations():
    assert ex.compute_rv24([0.01] * 23) is None
    assert ex.compute_rv24([0.01] * 25) is None


def test_rv24_fails_closed_on_any_missing_hour():
    window = [0.01] * 24
    window[10] = None
    assert ex.compute_rv24(window) is None


def test_rv24_is_hand_computable_constant_returns():
    window = [0.01] * 24
    assert ex.compute_rv24(window) == pytest.approx(0.01)


def test_rv24_uses_zero_mean_not_demeaned_variance():
    # One 0.04 return and 23 zero returns.
    window = [0.04] + [0.0] * 23
    raw_expected = (sum(r * r for r in window) / 24) ** 0.5
    demeaned_expected = (sum((r - sum(window) / 24) ** 2 for r in window) / 24) ** 0.5
    got = ex.compute_rv24(window)
    assert got == pytest.approx(raw_expected)
    assert got != pytest.approx(demeaned_expected)


def test_rv24_no_annualization_factor_applied():
    window = [0.01] * 24
    naive = (sum(r * r for r in window) / 24) ** 0.5
    assert ex.compute_rv24(window) == pytest.approx(naive)  # no sqrt(365) or similar scaling


# --------------------------------------------------------------------------
# compute_forward_rv24 -- canonical timestamp-aware outcome seam (F-01)
# --------------------------------------------------------------------------


def _timestamped_closes(decision: datetime = DECISION) -> dict[str, list[tuple[datetime, float]]]:
    return {
        symbol: [(decision + timedelta(hours=i), 100.0 + i) for i in range(25)]
        for symbol in ex.PANEL
    }


def test_forward_rv24_accepts_exact_t_through_t_plus_24_closes():
    result = ex.compute_forward_rv24(DECISION, _timestamped_closes())
    expected_hourly = [(101.0 + i) / (100.0 + i) - 1.0 for i in range(24)]
    assert result == pytest.approx((sum(r * r for r in expected_hourly) / 24) ** 0.5)


@pytest.mark.parametrize("mutation", ["missing", "before", "after", "shifted", "duplicate", "non_hourly", "reordered"])
def test_forward_rv24_rejects_noncanonical_timestamp_windows(mutation):
    closes = _timestamped_closes()
    rows = closes[ex.PANEL[0]]
    if mutation == "missing":
        rows.pop(10)
    elif mutation == "before":
        rows[0] = (DECISION - timedelta(hours=1), rows[0][1])
    elif mutation == "after":
        rows[-1] = (DECISION + timedelta(hours=25), rows[-1][1])
    elif mutation == "shifted":
        rows[1] = (DECISION + timedelta(hours=2), rows[1][1])
    elif mutation == "duplicate":
        rows[2] = (rows[1][0], rows[2][1])
    elif mutation == "non_hourly":
        rows[3] = (DECISION + timedelta(hours=3, minutes=1), rows[3][1])
    elif mutation == "reordered":
        rows[4], rows[5] = rows[5], rows[4]
    with pytest.raises(ValueError):
        ex.compute_forward_rv24(DECISION, closes)


def test_forward_rv24_rejects_wrong_decision_time_and_wrong_panel():
    with pytest.raises(ValueError):
        ex.compute_forward_rv24(DECISION + timedelta(hours=1), _timestamped_closes())
    wrong_panel = _timestamped_closes()
    wrong_panel["FAKEUSDT"] = wrong_panel.pop(ex.PANEL[0])
    with pytest.raises(ex.InputBindingError):
        ex.compute_forward_rv24(DECISION, wrong_panel)


def test_forward_rv24_price_shift_cannot_silently_generate_another_window():
    closes = _timestamped_closes()
    closes[ex.PANEL[0]] = [(timestamp + timedelta(hours=1), price) for timestamp, price in closes[ex.PANEL[0]]]
    with pytest.raises(ValueError):
        ex.compute_forward_rv24(DECISION, closes)


# --------------------------------------------------------------------------
# compute_primary_contrast -- single signed HIGH-minus-LOW contrast
# --------------------------------------------------------------------------


def test_primary_contrast_is_hand_computable_and_mid_is_excluded():
    rows = [("HIGH", 0.03), ("HIGH", 0.05), ("LOW", 0.01), ("LOW", 0.02), ("MID", 999.0)]
    result = ex.compute_primary_contrast(rows)
    assert result["value"] == pytest.approx(0.04 - 0.015)
    rows_mid_changed = [("HIGH", 0.03), ("HIGH", 0.05), ("LOW", 0.01), ("LOW", 0.02), ("MID", -999.0)]
    result2 = ex.compute_primary_contrast(rows_mid_changed)
    assert result["value"] == result2["value"]


def test_primary_contrast_empty_low_bin_fails_closed_not_invented():
    rows = [("HIGH", 0.03), ("MID", 0.02)]
    result = ex.compute_primary_contrast(rows)
    assert result["value"] is None
    assert result["blocked_reason"] == "EMPTY_REQUIRED_PRIMARY_BIN"


def test_primary_contrast_empty_high_bin_fails_closed_not_invented():
    rows = [("LOW", 0.03), ("MID", 0.02)]
    result = ex.compute_primary_contrast(rows)
    assert result["value"] is None
    assert result["blocked_reason"] == "EMPTY_REQUIRED_PRIMARY_BIN"


# --------------------------------------------------------------------------
# compute_preregistered_robustness -- proven empty / cannot mutate primary
# --------------------------------------------------------------------------


def test_robustness_defines_no_invented_checks_and_cannot_replace_primary():
    primary = {"value": 0.04}
    robustness = ex.compute_preregistered_robustness(primary)
    assert robustness["canonical_robustness_checks_defined_in_contract"] == ()
    assert robustness["checks"] == {}
    assert "value" not in robustness
    assert "primary" not in robustness
    assert robustness["primary_value_echo_readonly"] == 0.04


# --------------------------------------------------------------------------
# adjudicate_frozen_proposition
# --------------------------------------------------------------------------


def test_adjudicate_sealed_boundary_takes_precedence():
    result = ex.adjudicate_frozen_proposition(funding_state_clean=True, funding_coverage_ok=True, pit_alignment_ok=True, sealed_boundary_respected=False, primary={"value": 1.0})
    assert result == "BLOCKED_BY_SEALED_BREADTH_BOUNDARY"


def test_adjudicate_funding_coverage_blocked():
    result = ex.adjudicate_frozen_proposition(funding_state_clean=True, funding_coverage_ok=False, pit_alignment_ok=True, sealed_boundary_respected=True, primary={"value": 1.0})
    assert result == "BLOCKED_BY_FUNDING_COVERAGE"


def test_adjudicate_pit_alignment_blocked():
    result = ex.adjudicate_frozen_proposition(funding_state_clean=True, funding_coverage_ok=True, pit_alignment_ok=False, sealed_boundary_respected=True, primary={"value": 1.0})
    assert result == "BLOCKED_BY_PIT_ALIGNMENT"


def test_adjudicate_no_clean_funding_state():
    result = ex.adjudicate_frozen_proposition(funding_state_clean=False, funding_coverage_ok=True, pit_alignment_ok=True, sealed_boundary_respected=True, primary={"value": 1.0})
    assert result == "KILLED_NO_CLEAN_FUNDING_STATE"


def test_adjudicate_empty_bin_maps_to_no_clean_state():
    result = ex.adjudicate_frozen_proposition(funding_state_clean=True, funding_coverage_ok=True, pit_alignment_ok=True, sealed_boundary_respected=True, primary={"value": None})
    assert result == "KILLED_NO_CLEAN_FUNDING_STATE"


def test_adjudicate_nonpositive_contrast_killed():
    result = ex.adjudicate_frozen_proposition(funding_state_clean=True, funding_coverage_ok=True, pit_alignment_ok=True, sealed_boundary_respected=True, primary={"value": -0.01})
    assert result == "NO_POSITIVE_HIGH_MINUS_LOW_DIRECTIONAL_CONTRAST"
    result_zero = ex.adjudicate_frozen_proposition(funding_state_clean=True, funding_coverage_ok=True, pit_alignment_ok=True, sealed_boundary_respected=True, primary={"value": 0.0})
    assert result_zero == "NO_POSITIVE_HIGH_MINUS_LOW_DIRECTIONAL_CONTRAST"


def test_adjudicate_positive_contrast_supported():
    result = ex.adjudicate_frozen_proposition(funding_state_clean=True, funding_coverage_ok=True, pit_alignment_ok=True, sealed_boundary_respected=True, primary={"value": 0.01})
    assert result == ex.PRIMARY_PROPOSITION_SUPPORTED


# --------------------------------------------------------------------------
# validate_input_binding -- adversarial fixtures, fail closed
# --------------------------------------------------------------------------


def _valid_binding() -> dict:
    return {
        "preregistration_merge_sha": ex.PREREGISTRATION_MERGE_SHA,
        "contract_digest": ex.CONTRACT_DIGEST,
        "pit_certification_merge_sha": ex.PIT_CERTIFICATION_MERGE_SHA,
        "pit_certificate_digest": ex.PIT_CERTIFICATE_DIGEST,
        "funding_evidence_set_digest": ex.FUNDING_EVIDENCE_SET_DIGEST,
        "ohlcv_evidence_set_digest": ex.OHLCV_EVIDENCE_SET_DIGEST,
        "panel": list(ex.PANEL),
        "decision_window": {
            "first_combined_eligible_decision": ex.FIRST_COMBINED_ELIGIBLE_DECISION,
            "last_combined_eligible_decision": ex.LAST_COMBINED_ELIGIBLE_DECISION,
            "combined_pit_eligible_decisions_total": ex.COMBINED_PIT_ELIGIBLE_DECISIONS_TOTAL,
        },
    }


def test_valid_binding_passes():
    ex.validate_input_binding(_valid_binding())  # must not raise


def test_wrong_panel_symbol_rejected():
    binding = _valid_binding()
    binding["panel"] = list(ex.PANEL[:-1]) + ["FAKEUSDT"]
    with pytest.raises(ex.InputBindingError):
        ex.validate_input_binding(binding)


def test_wrong_panel_order_rejected_even_though_set_matches():
    binding = _valid_binding()
    reordered = list(ex.PANEL)
    reordered[0], reordered[1] = reordered[1], reordered[0]
    binding["panel"] = reordered
    assert set(reordered) == set(ex.PANEL)
    with pytest.raises(ex.InputBindingError):
        ex.validate_input_binding(binding)


def test_wrong_contract_digest_rejected():
    binding = _valid_binding()
    binding["contract_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ex.InputBindingError):
        ex.validate_input_binding(binding)


def test_wrong_pit_certificate_digest_rejected():
    binding = _valid_binding()
    binding["pit_certificate_digest"] = "sha256:" + "1" * 64
    with pytest.raises(ex.InputBindingError):
        ex.validate_input_binding(binding)


def test_wrong_funding_evidence_digest_rejected():
    binding = _valid_binding()
    binding["funding_evidence_set_digest"] = "sha256:" + "2" * 64
    with pytest.raises(ex.InputBindingError):
        ex.validate_input_binding(binding)


def test_wrong_ohlcv_evidence_digest_rejected():
    binding = _valid_binding()
    binding["ohlcv_evidence_set_digest"] = "sha256:" + "3" * 64
    with pytest.raises(ex.InputBindingError):
        ex.validate_input_binding(binding)


def test_wrong_decision_window_total_rejected():
    binding = _valid_binding()
    binding["decision_window"]["combined_pit_eligible_decisions_total"] = 609
    with pytest.raises(ex.InputBindingError):
        ex.validate_input_binding(binding)


def test_missing_binding_field_rejected():
    binding = _valid_binding()
    del binding["contract_digest"]
    with pytest.raises(ex.InputBindingError):
        ex.validate_input_binding(binding)


# --------------------------------------------------------------------------
# authorize_execution -- authority gate
# --------------------------------------------------------------------------


def test_synthetic_fixture_execution_is_permitted_without_authorization():
    ex.authorize_execution("SYNTHETIC_FIXTURE", None)  # must not raise


def test_real_execution_without_authorization_is_refused():
    with pytest.raises(ex.ExecutionNotAuthorizedError):
        ex.authorize_execution("REAL_HISTORICAL", None)


def test_real_execution_is_refused_even_with_a_plausible_looking_authorization():
    fake_authorization = {
        "authorization_id": "AUTH-0001",
        "experiment_id": ex.EXPERIMENT_ID,
        "preregistration_merge_sha": ex.PREREGISTRATION_MERGE_SHA,
        "contract_digest": ex.CONTRACT_DIGEST,
        "pit_certification_merge_sha": ex.PIT_CERTIFICATION_MERGE_SHA,
        "pit_certificate_digest": ex.PIT_CERTIFICATE_DIGEST,
        "execution_implementation_sha": "deadbeef" * 5,
        "funding_evidence_set_digest": ex.FUNDING_EVIDENCE_SET_DIGEST,
        "ohlcv_evidence_set_digest": ex.OHLCV_EVIDENCE_SET_DIGEST,
        "execution_scope": ex.REQUIRED_EXECUTION_SCOPE,
        "outcome_access_scope": ex.REQUIRED_OUTCOME_ACCESS_SCOPE,
    }
    with pytest.raises(ex.ExecutionNotAuthorizedError):
        ex.authorize_execution("REAL_HISTORICAL", fake_authorization, actual_execution_implementation_sha="cafebabe" * 5)


def test_unknown_execution_mode_rejected():
    with pytest.raises(ValueError):
        ex.authorize_execution("SOMETHING_ELSE", None)


def _valid_authorization(implementation_sha: str) -> dict:
    return {
        "authorization_id": "AUTH-0001",
        "experiment_id": ex.EXPERIMENT_ID,
        "preregistration_merge_sha": ex.PREREGISTRATION_MERGE_SHA,
        "contract_digest": ex.CONTRACT_DIGEST,
        "pit_certification_merge_sha": ex.PIT_CERTIFICATION_MERGE_SHA,
        "pit_certificate_digest": ex.PIT_CERTIFICATE_DIGEST,
        "execution_implementation_sha": implementation_sha,
        "funding_evidence_set_digest": ex.FUNDING_EVIDENCE_SET_DIGEST,
        "ohlcv_evidence_set_digest": ex.OHLCV_EVIDENCE_SET_DIGEST,
        "execution_scope": ex.REQUIRED_EXECUTION_SCOPE,
        "outcome_access_scope": ex.REQUIRED_OUTCOME_ACCESS_SCOPE,
    }


def test_real_authorization_requires_runtime_identity_to_match_artifact():
    sha = "a" * 40
    ex.authorize_execution("REAL_HISTORICAL", _valid_authorization(sha), actual_execution_implementation_sha=sha)


@pytest.mark.parametrize("bad_sha", ["b" * 40, "not-a-sha", "a" * 39])
def test_real_authorization_rejects_wrong_or_invalid_runtime_identity(bad_sha):
    with pytest.raises(ex.ExecutionNotAuthorizedError):
        ex.authorize_execution("REAL_HISTORICAL", _valid_authorization("a" * 40), actual_execution_implementation_sha=bad_sha)


def test_real_authorization_rejects_wrong_contract_pit_or_evidence_identity():
    sha = "a" * 40
    for field, value in (
        ("contract_digest", "sha256:" + "0" * 64),
        ("pit_certificate_digest", "sha256:" + "1" * 64),
        ("funding_evidence_set_digest", "sha256:" + "2" * 64),
        ("ohlcv_evidence_set_digest", "sha256:" + "3" * 64),
    ):
        authorization = _valid_authorization(sha)
        authorization[field] = value
        with pytest.raises(ex.ExecutionNotAuthorizedError):
            ex.authorize_execution("REAL_HISTORICAL", authorization, actual_execution_implementation_sha=sha)


def test_executor_has_no_self_referential_implementation_sha_constant():
    assert "EXECUTION_IMPLEMENTATION_SHA" not in vars(ex)


# --------------------------------------------------------------------------
# build_execution_receipt -- deterministic canonical-JSON receipt
# --------------------------------------------------------------------------


def _sample_receipt_kwargs() -> dict:
    return dict(
        panel=list(ex.PANEL),
        decision_window={"first_combined_eligible_decision": ex.FIRST_COMBINED_ELIGIBLE_DECISION, "last_combined_eligible_decision": ex.LAST_COMBINED_ELIGIBLE_DECISION, "combined_pit_eligible_decisions_total": ex.COMBINED_PIT_ELIGIBLE_DECISIONS_TOTAL},
        census={"eligible": 610, "excluded": 0},
        state_counts={"LOW": 200, "MID": 210, "HIGH": 200},
        primary={"value": 0.01, "high_count": 200, "low_count": 200},
        robustness={"checks": {}},
        adjudication=ex.PRIMARY_PROPOSITION_SUPPORTED,
        execution_implementation_identity="qntylab.jigsaw_funding_pressure_volatility_execution_v0",
        artifact_hashes={"synthetic_fixture": "0" * 64},
    )


def test_receipt_is_deterministic_for_identical_inputs():
    r1 = ex.build_execution_receipt(**_sample_receipt_kwargs())
    r2 = ex.build_execution_receipt(**_sample_receipt_kwargs())
    assert r1["receipt_digest"] == r2["receipt_digest"]
    assert ex.receipt_json(r1) == ex.receipt_json(r2)


def test_receipt_digest_changes_on_material_mutation():
    kwargs = _sample_receipt_kwargs()
    r1 = ex.build_execution_receipt(**kwargs)
    kwargs["primary"] = {**kwargs["primary"], "value": 0.02}
    r2 = ex.build_execution_receipt(**kwargs)
    assert r1["receipt_digest"] != r2["receipt_digest"]


def test_receipt_binds_frozen_parent_identity():
    receipt = ex.build_execution_receipt(**_sample_receipt_kwargs())
    assert receipt["preregistration_merge_sha"] == ex.PREREGISTRATION_MERGE_SHA
    assert receipt["contract_digest"] == ex.CONTRACT_DIGEST
    assert receipt["pit_certification_merge_sha"] == ex.PIT_CERTIFICATION_MERGE_SHA
    assert receipt["pit_certificate_digest"] == ex.PIT_CERTIFICATE_DIGEST
    assert receipt["funding_evidence_set_digest"] == ex.FUNDING_EVIDENCE_SET_DIGEST
    assert receipt["ohlcv_evidence_set_digest"] == ex.OHLCV_EVIDENCE_SET_DIGEST
    assert receipt["execution_authority"] == "NONE"
    assert receipt["outcome_access_authority"] == "NONE"
