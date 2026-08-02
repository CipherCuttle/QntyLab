import hashlib
import json
from collections import Counter
from pathlib import Path

from qntylab.research_ledger import compute_variant_id, context_text, doctor
from qntylab.curated_breadth_screen import expand_planned_runs


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "experiments/research"
SPEC_PATH = ROOT / "experiments/specs/curated_breadth_screen_v1.json"
NEW_CANDIDATE_IDS = {
    "CANDIDATE_H002_MOMENTUM_72_LONG_FLAT",
    "CANDIDATE_H002_MOMENTUM_168_LONG_FLAT",
    "CANDIDATE_H002_MOMENTUM_720_LONG_FLAT",
    "CANDIDATE_H003_MA_12_48_LONG_FLAT",
    "CANDIDATE_H003_MA_48_192_LONG_FLAT",
    "CANDIDATE_H003_MA_168_720_LONG_FLAT",
    "CANDIDATE_H005_DONCHIAN_168_LONG_FLAT",
    "CANDIDATE_H005_DONCHIAN_720_LONG_FLAT",
    "CANDIDATE_H006_REVERSAL_1_LONG_SHORT",
    "CANDIDATE_H006_REVERSAL_3_LONG_SHORT",
    "CANDIDATE_H006_REVERSAL_6_LONG_SHORT",
    "CANDIDATE_H006_REVERSAL_12_LONG_SHORT",
    "CANDIDATE_H007_VOL_SCALED_MA_24_96_RV24",
    "CANDIDATE_H007_VOL_SCALED_MA_24_96_RV72",
    "CANDIDATE_H007_VOL_SCALED_MA_24_96_RV168",
}


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_curated_breadth_screen_v1_registration_is_frozen():
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    candidates = _jsonl(RESEARCH / "candidates.jsonl")
    decisions = _jsonl(RESEARCH / "decisions.jsonl")
    trials = _jsonl(RESEARCH / "trials/2026.jsonl")
    state = json.loads((RESEARCH / "state.json").read_text(encoding="utf-8"))
    candidate_events = [event for event in candidates if event["event_type"] == "CANDIDATE_PROPOSED"]
    new_events = [event for event in candidate_events if event["candidate_id"] in NEW_CANDIDATE_IDS]

    assert spec["screen_id"] == "CURATED_BREADTH_SCREEN_V1"
    assert spec["status"] == "REGISTERED_NOT_EXECUTED"
    assert len(new_events) == 15
    assert len(candidate_events) == 19
    assert set(spec["new_candidate_ids"]) == NEW_CANDIDATE_IDS
    assert len(spec["new_variant_ids"]) == 15
    assert len(set(spec["new_variant_ids"])) == 15
    assert {event["variant_id"] for event in new_events} == set(spec["new_variant_ids"])
    assert len({event["candidate_id"] for event in new_events}) == 15
    assert len({event["variant_id"] for event in candidate_events}) == 19
    assert all(event["origin"] == "CURATED_MECHANISM_AND_LITERATURE_ANCHORED" for event in new_events)
    assert all(event["mechanism"] and event["prediction"] and event["benchmark"] and event["failure_condition"] for event in new_events)
    assert {event["variant_id"] for event in new_events}.isdisjoint(
        {
            "variant_966eea454bc9ac3d22603a7c",
            "variant_aa66ba0edf856ac06f055917",
            "variant_83e1fee345fb3915774652a5",
            "variant_282aa437c78189c7c8b2c124",
        }
    )
    for event in new_events:
        assert event["variant_id"] == compute_variant_id(event)

    assert Counter(event["family_id"] for event in new_events) == {
        "time_series_momentum": 3,
        "moving_average_trend": 3,
        "price_breakout": 2,
        "short_horizon_reversal": 4,
        "volatility_scaled_trend": 3,
    }
    assert {key: len(value["new_candidate_ids"]) for key, value in spec["families"].items()} == {
        "time_series_momentum": 3,
        "moving_average_trend": 3,
        "price_breakout": 2,
        "short_horizon_reversal": 4,
        "volatility_scaled_trend": 3,
    }

    assert state["variants"]["variant_aa66ba0edf856ac06f055917"]["status"] == "SURVIVOR"
    assert state["variants"]["variant_966eea454bc9ac3d22603a7c"]["status"] == "GRAVEYARDED"
    assert state["variants"]["variant_83e1fee345fb3915774652a5"]["status"] == "GRAVEYARDED"
    assert state["variants"]["variant_282aa437c78189c7c8b2c124"]["status"] == "GRAVEYARDED"
    assert all(event["scope"] == "EXACT_VARIANT" for event in decisions)
    assert {
        "variant_aa66ba0edf856ac06f055917",
        "variant_966eea454bc9ac3d22603a7c",
        "variant_83e1fee345fb3915774652a5",
        "variant_282aa437c78189c7c8b2c124",
    } <= {event["variant_id"] for event in decisions}
    planned = expand_planned_runs(SPEC_PATH, repo_root=ROOT)
    planned_ids = {row["trial_id"] for row in planned}
    assert len(planned_ids) == 360
    assert Counter(event["trial_id"] for event in trials if event["trial_id"] in planned_ids) == {trial_id: 1 for trial_id in planned_ids}
    assert Counter(event["variant_id"] for event in trials if event["trial_id"] in planned_ids) == {
        variant_id: 24 for variant_id in spec["new_variant_ids"]
    }

    assert "variant_282aa437c78189c7c8b2c124" in spec["historical_anchor_variant_ids"]
    assert "variant_282aa437c78189c7c8b2c124" not in spec["new_variant_ids"]
    assert "variant_aa66ba0edf856ac06f055917" in spec["historical_anchor_variant_ids"]
    assert "variant_aa66ba0edf856ac06f055917" not in spec["new_variant_ids"]
    assert spec["expected_new_run_count"] == 360
    assert spec["assets"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert set(spec["periods"]) == {"2022", "2024", "2025", "2026YTD"}
    assert "2023" not in spec["periods"]
    assert spec["excluded_periods"]["2023"]
    assert spec["cost_modes"] == {"baseline": {"fee_bps": 10, "slippage_bps": 0}, "stress": {"fee_bps": 10, "slippage_bps": 10}}
    assert spec["gap_policy"] == "REJECT"
    assert spec["expected_interval"] == "1h"

    reversal = spec["families"]["short_horizon_reversal"]["frozen_formula"]
    assert reversal["cumulative_return_h"] == "close[t] / close[t-h] - 1"
    assert reversal["desired_position_next_bar"] == "raw_signal[t]"
    assert [item["parameters"]["lookback"] for item in spec["candidate_details"] if item["family_id"] == "short_horizon_reversal"] == [1, 3, 6, 12]

    vol = spec["families"]["volatility_scaled_trend"]["frozen_formula"]
    assert vol["hourly_log_return"] == "r[t] = log(close[t] / close[t-1])"
    assert vol["risk_multiplier"] == "clip(volatility_baseline[t] / rv_w[t], 0.25, 1.0)"
    assert vol["desired_position_next_bar"] == "base_signal[t] * risk_multiplier[t]"
    assert [item["parameters"]["realized_volatility_window"] for item in spec["candidate_details"] if item["family_id"] == "volatility_scaled_trend"] == [24, 72, 168]
    assert set(spec["implementation_required_variant_ids"]) == {
        item["variant_id"] for item in spec["candidate_details"] if item["implementation_readiness"] == "IMPLEMENTATION_REQUIRED"
    }

    h002_h003 = ROOT / "experiments/research/summaries/h002_h003_followup_v1_summary_compact.csv"
    first_batch = ROOT / "experiments/research/summaries/first_batch_summary_compact.csv"
    assert spec["historical_anchors"]["variant_aa66ba0edf856ac06f055917"]["evidence_sha256"][str(h002_h003.relative_to(ROOT))] == _sha(h002_h003)
    assert spec["historical_anchors"]["variant_282aa437c78189c7c8b2c124"]["evidence_sha256"][str(first_batch.relative_to(ROOT))] == _sha(first_batch)

    for action in [
        "parameter optimization",
        "grid search beyond registered variants",
        "automatic survivor decisions",
        "automatic family graveyard decisions",
        "Formal QNTY promotion",
        "master-strategy construction",
        "paper trading",
        "live trading",
    ]:
        assert action in spec["prohibited_actions"]
    assert doctor(RESEARCH) == []
    context = context_text(RESEARCH)
    assert "total candidate variants: 19" in context
    assert "total completed trials: 378" in context
    assert len(context.splitlines()) < 80
