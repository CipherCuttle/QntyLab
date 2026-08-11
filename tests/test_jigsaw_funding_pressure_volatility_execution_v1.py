from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest

from qntylab import jigsaw_funding_pressure_volatility_execution_v1 as ex

T = datetime(2024, 1, 2, tzinfo=UTC)


def event(symbol, iso, rate):
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return ex.FundingEvent(symbol, int(dt.timestamp() * 1000), iso, rate)


def test_funding_pit_panel_median_and_f4_fail_closed():
    panel = {s: event(s, "2024-01-01T12:00:00Z", str(i + 1)) for i, s in enumerate(ex.PANEL)}
    assert ex.compute_funding_pressure(panel) == Decimal("10.5")
    assert ex.select_latest_funding_event([event(ex.PANEL[0], "2024-01-01T00:00:00Z", "1"), event(ex.PANEL[0], "2024-01-01T00:00:00Z", "2")], T) is None
    with pytest.raises(ex.DuplicateFundingTimestampError):
        ex.select_latest_funding_event([event(ex.PANEL[0], "2024-01-01T12:00:00Z", "1"), event(ex.PANEL[0], "2024-01-01T12:00:00Z", "2")], T)


def test_ecdf_365_current_and_exact_tertile_boundaries():
    prior = [Decimal(i) for i in range(1, 366)]
    assert ex.compute_pit_ecdf(prior, Decimal(121)) == Fraction(1, 3)
    assert ex.classify_funding_state(Fraction(1, 3)) == "LOW"
    assert ex.compute_pit_ecdf(prior, Decimal(243)) == Fraction(2, 3)
    assert ex.classify_funding_state(Fraction(2, 3)) == "HIGH"
    with pytest.raises(ValueError): ex.compute_pit_ecdf(prior[:-1], Decimal(1))


def bars(decision=T):
    return {s: [ex.BarOpenClose(decision + timedelta(hours=i), 101.0 + i) for i in range(-1, 24)] for s in ex.PANEL}


def test_v1_bar_open_mapping_is_hand_checkable_and_old_v0_mapping_fails():
    # Source open t-1 has close endpoint t; endpoint closes are 100..124.
    got = ex.compute_forward_rv24_from_bar_open_closes(T, bars())
    expected = ((sum((((101 + i) / (100 + i)) - 1) ** 2 for i in range(24)) / 24) ** 0.5)
    assert got == pytest.approx(expected)
    # The old V0 interpretation would consume source opens t..t+24,
    # hence would produce a different answer and is not a V1 input.
    old_rows = {s: [ex.BarOpenClose(T + timedelta(hours=i), 100.0 + i) for i in range(25)] for s in ex.PANEL}
    with pytest.raises(ValueError): ex.compute_forward_rv24_from_bar_open_closes(T, old_rows)


@pytest.mark.parametrize("mutation", ["start", "end", "forward", "backward", "missing", "interior", "duplicate", "reordered", "nonhourly", "decision", "panel", "endpoint_semantic", "mixed_semantic"])
def test_v1_source_window_mutations_fail_closed(mutation):
    data = bars()
    rows = list(data[ex.PANEL[0]])
    if mutation == "start": rows[0] = ex.BarOpenClose(T, 100)
    elif mutation == "end": rows[-1] = ex.BarOpenClose(T + timedelta(hours=24), 124)
    elif mutation == "forward": rows[1] = ex.BarOpenClose(T + timedelta(hours=1), 101)
    elif mutation == "backward": rows[1] = ex.BarOpenClose(T - timedelta(hours=1), 101)
    elif mutation == "missing": rows.pop(4)
    elif mutation == "interior": rows[4] = ex.BarOpenClose(T + timedelta(hours=5), 104)
    elif mutation == "duplicate": rows[4] = rows[3]
    elif mutation == "reordered": rows[4], rows[5] = rows[5], rows[4]
    elif mutation == "nonhourly": rows[4] = ex.BarOpenClose(T + timedelta(hours=3, minutes=1), 104)
    elif mutation == "endpoint_semantic": rows[0] = ex.BarOpenClose(rows[0].timestamp, 99, "LOGICAL_CLOSE_ENDPOINT", ex.REQUIRED_CLOSE_SEMANTIC)
    elif mutation == "mixed_semantic": rows[1] = ex.BarOpenClose(rows[1].timestamp, 101, ex.REQUIRED_SOURCE_TIMESTAMP_SEMANTIC, "CLOSE_ENDPOINT")
    if mutation not in {"decision", "panel"}: data[ex.PANEL[0]] = rows
    if mutation == "decision":
        with pytest.raises(ValueError): ex.compute_forward_rv24_from_bar_open_closes(T + timedelta(hours=1), data)
    elif mutation == "panel":
        data["FAKEUSDT"] = data.pop(ex.PANEL[0])
        with pytest.raises(ex.InputBindingError): ex.compute_forward_rv24_from_bar_open_closes(T, data)
    else:
        with pytest.raises((ValueError, ex.InputBindingError, TypeError)): ex.compute_forward_rv24_from_bar_open_closes(T, data)


def test_rv_market_primary_and_empty_robustness():
    assert ex.compute_rv24([0.01] * 24) == pytest.approx(0.01)
    assert ex.compute_rv24([0.01] * 23) is None
    returns = {s: 0.01 for s in ex.PANEL}
    assert ex.compute_equal_weight_market_return(returns) == pytest.approx(0.01)
    primary = ex.compute_primary_contrast([("HIGH", .04), ("LOW", .01), ("MID", 99)])
    assert primary["value"] == pytest.approx(.03)
    assert ex.compute_preregistered_robustness(primary)["checks"] == {}


def valid_binding():
    return {"preregistration_merge_sha": ex.PREREGISTRATION_MERGE_SHA, "contract_digest": ex.CONTRACT_DIGEST, "pit_v1_merge_sha": ex.PIT_V1_MERGE_SHA, "pit_v1_certificate_digest": ex.PIT_V1_CERTIFICATE_DIGEST, "funding_evidence_set_digest": ex.FUNDING_EVIDENCE_SET_DIGEST, "ohlcv_v1_evidence_set_digest": ex.OHLCV_V1_EVIDENCE_SET_DIGEST, "panel": list(ex.PANEL), "decision_window": {"first_decision": ex.FIRST_DECISION, "last_decision": ex.LAST_DECISION, "decision_count": 610}, "source_timestamp_semantic": ex.REQUIRED_SOURCE_TIMESTAMP_SEMANTIC, "close_semantic": ex.REQUIRED_CLOSE_SEMANTIC, "logical_endpoint_mapping": ex.REQUIRED_ENDPOINT_MAPPING}


def test_input_binding_authorization_and_receipt():
    ex.validate_input_binding(valid_binding())
    bad = valid_binding(); bad["pit_v1_certificate_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ex.InputBindingError): ex.validate_input_binding(bad)
    ex.authorize_execution("SYNTHETIC_FIXTURE", None)
    with pytest.raises(ex.ExecutionNotAuthorizedError): ex.authorize_execution("REAL_HISTORICAL", None)
    kwargs = dict(decision_window={"first_decision": ex.FIRST_DECISION}, census={"eligible": 0}, state_counts={}, primary={"value": None}, robustness={}, adjudication="NONE", execution_implementation_identity="runtime-supplied", artifact_hashes={})
    assert ex.build_execution_receipt(**kwargs)["receipt_digest"] == ex.build_execution_receipt(**kwargs)["receipt_digest"]
    assert ex.receipt_json(ex.build_execution_receipt(**kwargs))
    assert "EXECUTION_IMPLEMENTATION_SHA" not in vars(ex)
