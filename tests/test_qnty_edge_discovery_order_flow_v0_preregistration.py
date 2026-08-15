import hashlib
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/specs/qnty_edge_discovery_order_flow_v0_preregistration.json"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _load():
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_preregistration_digest_and_fixed_denominator_are_self_consistent():
    value = _load()
    body = {key: item for key, item in value.items() if key != "preregistration_digest"}
    assert value["preregistration_digest"] == hashlib.sha256(_canonical(body)).hexdigest()

    denominator = value["search_denominator"]
    assert denominator["eligible_strategy_variants"] == 1
    assert denominator["eligible_asset_rows"] == 20
    assert denominator["eligible_asset_cost_cells"] == 40
    assert denominator["cost_modes"] == 2
    assert denominator["diagnostic_only_controls"] == 2
    assert value["universe"]["count"] == len(value["universe"]["ordered_symbols"]) == 20
    assert len(set(value["universe"]["ordered_symbols"])) == 20


def test_feature_is_lagged_distinct_and_timing_is_strict():
    value = _load()
    feature = value["feature_formula"]
    assert "taker_buy_quote_volume" in feature["taker_sell_quote_notional"]
    assert "total_quote_volume" in feature["taker_sell_quote_notional"]
    assert "normalized OFI" not in feature["primary_feature"]
    assert feature["source_bar"] == "[t-2h, t-1h)"
    assert feature["normalization_window_bars"] == 24

    timing = value["safe_known_timing"]
    assert timing["feature_source_end"] == "t-1h source-bar close"
    assert timing["decision_time"] == "t at the target bar open, after the fixed one-bar embargo"
    assert timing["execution_eligible_time"] == "t at target-bar open"
    assert timing["outcome_start"] == "t at target-bar open"
    assert "FEATURE_SOURCE_END < DECISION_TIME" in timing["ordering_contract"]
    assert "EXECUTION_ELIGIBLE_TIME < OUTCOME_END" in timing["ordering_contract"]


def test_no_new_v0_outcome_or_rescue_authority_is_declared():
    value = _load()
    assert value["status"] == "PREREGISTRATION_ONLY_OUTCOME_UNSEEN"
    assert value["evidence_scope"]["new_feature_outcomes_unseen"] is True
    assert value["temporal_design"]["sealed_holdout"] == "NONE_IN_THIS_PHASE"
    assert value["primary_direction"] == "CONTINUATION"
    assert value["prediction_horizon"]["alternatives"] == []
    assert value["ledger_action"]["trial_completed_event"] is False
    assert value["ledger_action"]["h010_reopened"] is False
    assert value["qntyagenteval_applicability"]["applicability"] == "NO_MATCH"


def test_fixed_temporal_blocks_are_chronological_and_non_overlapping():
    blocks = _load()["temporal_design"]["fixed_chronological_blocks"]
    intervals = [(datetime.fromisoformat(row["start"].replace("Z", "+00:00")), datetime.fromisoformat(row["end"].replace("Z", "+00:00"))) for row in blocks]
    assert all(start <= end for start, end in intervals)
    assert all(intervals[index][1] < intervals[index + 1][0] for index in range(len(intervals) - 1))
