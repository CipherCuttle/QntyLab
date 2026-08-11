from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from qntylab import jigsaw_funding_pressure_volatility_execution_v1 as ex


def binding():
    return {
        "preregistration_merge_sha": ex.PREREGISTRATION_MERGE_SHA,
        "contract_digest": ex.CONTRACT_DIGEST,
        "pit_v1_merge_sha": ex.PIT_V1_MERGE_SHA,
        "pit_v1_certificate_digest": ex.PIT_V1_CERTIFICATE_DIGEST,
        "funding_evidence_set_digest": ex.FUNDING_EVIDENCE_SET_DIGEST,
        "ohlcv_v1_evidence_set_digest": ex.OHLCV_V1_EVIDENCE_SET_DIGEST,
        "panel": list(ex.PANEL),
        "decision_window": {"first_decision": ex.FIRST_DECISION, "last_decision": ex.LAST_DECISION, "decision_count": ex.DECISION_COUNT},
        "source_timestamp_semantic": ex.REQUIRED_SOURCE_TIMESTAMP_SEMANTIC,
        "close_semantic": ex.REQUIRED_CLOSE_SEMANTIC,
        "logical_endpoint_mapping": ex.REQUIRED_ENDPOINT_MAPPING,
    }


def event(at, rate):
    return ex.FundingEvent("placeholder", int(at.timestamp() * 1000), at.isoformat().replace("+00:00", "Z"), str(rate))


def funding(at, rate):
    return {symbol: ex.FundingEvent(symbol, int(at.timestamp() * 1000), at.isoformat().replace("+00:00", "Z"), str(rate)) for symbol in ex.PANEL}


def bars(decision, rv):
    rows = {}
    step = 1 + rv
    for symbol in ex.PANEL:
        rows[symbol] = [ex.BarOpenClose(decision + timedelta(hours=i), 100 * step ** (i + 1)) for i in range(-1, 24)]
    return rows


def synthetic_inputs(schedule):
    funding_data = {}
    bars_data = {}
    first_required = schedule[0] - timedelta(days=365)
    for offset in range((schedule[-1] - first_required).days + 1):
        timestamp = first_required + timedelta(days=offset)
        rate = 0.1 if timestamp in schedule and (timestamp - schedule[0]).days % 2 == 0 else 1.0
        if timestamp in schedule and (timestamp - schedule[0]).days % 2 == 1:
            rate = 2.0
        funding_data[timestamp] = funding(timestamp, rate)
    for decision in schedule:
        bars_data[decision] = bars(decision, 0.01 if (decision - schedule[0]).days % 2 == 0 else 0.02)
    return funding_data, bars_data


def test_canonical_schedule_is_exact_and_daily():
    schedule = ex.canonical_decision_schedule()
    assert len(schedule) == 610
    assert schedule[0] == datetime(2023, 10, 19, tzinfo=UTC)
    assert schedule[-1] == datetime(2025, 6, 19, tzinfo=UTC)
    assert all(b - a == timedelta(days=1) for a, b in zip(schedule, schedule[1:]))


def test_canonical_executor_owns_full_synthetic_pipeline_and_receipt():
    schedule = tuple(datetime(2024, 1, 2, tzinfo=UTC) + timedelta(days=i) for i in range(4))
    funding_data, bars_data = synthetic_inputs(schedule)
    result = ex.execute_frozen_experiment_v1(mode="SYNTHETIC_FIXTURE", binding=binding(), funding_events_by_decision=funding_data, bars_by_decision=bars_data, synthetic_schedule=schedule)
    assert result["census"] == {"eligible_decisions": 4, "feature_states": 4, "outcome_labels": 4, "joined_primary_rows": 4, "excluded": 0}
    assert result["state_counts"] == {"LOW": 2, "MID": 0, "HIGH": 2}
    assert result["primary"]["value"] > 0
    assert result["adjudication"] == "PRIMARY_HYPOTHESIS_SUPPORTED"
    assert result["receipt"]["adjudication"] == result["adjudication"]
    assert "decision_window" in result["receipt"]


def test_real_historical_cannot_use_reduced_schedule_or_skip_authorization():
    with pytest.raises(ex.ExecutionNotAuthorizedError):
        ex.execute_frozen_experiment_v1(mode="REAL_HISTORICAL", binding=binding(), funding_events_by_decision={}, bars_by_decision={}, synthetic_schedule=(datetime(2024, 1, 1, tzinfo=UTC),))


def test_binding_and_authorization_mutations_fail_closed():
    bad = binding()
    bad["ohlcv_v1_evidence_set_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ex.InputBindingError):
        ex.execute_frozen_experiment_v1(mode="SYNTHETIC_FIXTURE", binding=bad, funding_events_by_decision={}, bars_by_decision={})
    with pytest.raises(ex.ExecutionNotAuthorizedError):
        ex.authorize_execution("REAL_HISTORICAL", {"authorization_id": "x"}, actual_execution_implementation_sha="f" * 40)


def authorization(sha="f" * 40):
    return {"authorization_id": "synthetic-controlled", "experiment_id": ex.EXPERIMENT_ID, "preregistration_merge_sha": ex.PREREGISTRATION_MERGE_SHA, "contract_digest": ex.CONTRACT_DIGEST, "pit_v1_merge_sha": ex.PIT_V1_MERGE_SHA, "pit_v1_certificate_digest": ex.PIT_V1_CERTIFICATE_DIGEST, "execution_implementation_sha": sha, "funding_evidence_set_digest": ex.FUNDING_EVIDENCE_SET_DIGEST, "ohlcv_v1_evidence_set_digest": ex.OHLCV_V1_EVIDENCE_SET_DIGEST, "execution_scope": "ONE_FROZEN_HISTORICAL_RUN", "outcome_access_scope": "EXACT_PREREGISTERED_OUTCOMES_ONLY"}


@pytest.mark.parametrize("mutation", ["runtime_sha", "implementation_sha", "pit_digest", "ohlcv_digest"])
def test_authorization_binding_mutations_refuse(mutation):
    auth = authorization()
    runtime_sha = "f" * 40
    if mutation == "runtime_sha": runtime_sha = "e" * 40
    elif mutation == "implementation_sha": auth["execution_implementation_sha"] = "e" * 40
    elif mutation == "pit_digest": auth["pit_v1_certificate_digest"] = "sha256:" + "0" * 64
    elif mutation == "ohlcv_digest": auth["ohlcv_v1_evidence_set_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ex.ExecutionNotAuthorizedError):
        ex.authorize_execution("REAL_HISTORICAL", auth, actual_execution_implementation_sha=runtime_sha)


def test_history_is_exactly_365_prior_plus_current_and_missing_day_blocks():
    with pytest.raises(ValueError):
        ex.compute_pit_ecdf([Decimal("1")] * 364, Decimal("1"))
    schedule = (datetime(2024, 1, 2, tzinfo=UTC),)
    funding_data, bars_data = synthetic_inputs(schedule)
    del funding_data[schedule[0] - timedelta(days=17)]
    with pytest.raises(ex.FrozenExecutionError, match="KILLED_NO_CLEAN_FUNDING_STATE"):
        ex.execute_frozen_experiment_v1(mode="SYNTHETIC_FIXTURE", binding=binding(), funding_events_by_decision=funding_data, bars_by_decision=bars_data, synthetic_schedule=schedule)


def test_pit_source_and_join_mutations_block_and_adjudication_is_not_caller_supplied():
    schedule = (datetime(2024, 1, 2, tzinfo=UTC), datetime(2024, 1, 3, tzinfo=UTC))
    funding_data, bars_data = synthetic_inputs(schedule)
    bars_data[schedule[0]][ex.PANEL[0]] = bars_data[schedule[0]][ex.PANEL[0]][1:]
    with pytest.raises((ValueError, ex.FrozenExecutionError)):
        ex.execute_frozen_experiment_v1(mode="SYNTHETIC_FIXTURE", binding=binding(), funding_events_by_decision=funding_data, bars_by_decision=bars_data, synthetic_schedule=schedule)
    with pytest.raises(TypeError):
        ex.build_execution_receipt(execution_result={}, execution_implementation_identity="x", artifact_hashes={}, adjudication="PRIMARY_HYPOTHESIS_SUPPORTED")


@pytest.mark.parametrize("mutation", ["missing_decision", "duplicate_decision", "shifted_decision", "missing_rv"])
def test_census_and_exact_join_mutations_fail_closed(mutation):
    schedule = (datetime(2024, 1, 2, tzinfo=UTC), datetime(2024, 1, 3, tzinfo=UTC))
    funding_data, bars_data = synthetic_inputs(schedule)
    if mutation == "missing_decision":
        del funding_data[schedule[1]]
    elif mutation == "duplicate_decision":
        schedule = schedule + (schedule[1],)
    elif mutation == "shifted_decision":
        bars_data[schedule[1] + timedelta(days=1)] = bars_data.pop(schedule[1])
    else:
        del bars_data[schedule[1]]
    with pytest.raises((ex.FrozenExecutionError, ValueError)):
        ex.execute_frozen_experiment_v1(mode="SYNTHETIC_FIXTURE", binding=binding(), funding_events_by_decision=funding_data, bars_by_decision=bars_data, synthetic_schedule=schedule)


def test_adjudication_is_mechanical_and_empty_bins_are_ambiguous():
    assert ex.derive_adjudication({"value": 1.0}) == "PRIMARY_HYPOTHESIS_SUPPORTED"
    assert ex.derive_adjudication({"value": 0.0}) == "NO_POSITIVE_HIGH_MINUS_LOW_DIRECTIONAL_CONTRAST"
    assert ex.derive_adjudication({"value": None}) == "BLOCKED_BY_FROZEN_CONTRACT_AMBIGUITY"
    assert ex.derive_adjudication({"value": -1.0}) != "PRIMARY_HYPOTHESIS_SUPPORTED"
    assert ex.derive_adjudication({"value": 1.0}) != "NO_POSITIVE_HIGH_MINUS_LOW_DIRECTIONAL_CONTRAST"
