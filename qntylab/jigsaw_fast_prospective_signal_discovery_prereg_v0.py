"""Static validator for the outcome-blind Jigsaw Fast V0 preregistration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments/research/jigsaw_fast_prospective_signal_discovery_v0"


def load_json(name: str) -> dict:
    return json.loads((EXPERIMENT / name).read_text())


def canonical_digest(value: dict, field: str) -> str:
    body = dict(value)
    body.pop(field, None)
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate() -> None:
    census = load_json("candidate_census.json")
    prereg = load_json("preregistration.json")
    ids = [candidate["candidate_id"] for candidate in census["candidates"]]
    assert ids == ["JFP01", "JFP02", "JFP03"]
    assert census["candidate_count"] == 3 == len(ids)
    assert prereg["candidate_ids"] == ids
    assert prereg["candidate_count"] == 3
    assert len(set(ids)) == 3
    assert canonical_digest(census, "candidate_census_digest") == census["candidate_census_digest"]
    assert canonical_digest(prereg, "preregistration_digest") == prereg["preregistration_digest"]
    required = {
        "origin_type", "exact_proposition", "feature", "safe_known_after", "outcome",
        "primary_horizon", "universe", "benchmark", "primary_metric_statistic",
        "multiplicity_treatment", "materiality_rule", "historical_source_contract",
        "historical_discovery_window", "prospective_maturity_condition",
        "integrity_kill_conditions", "scientific_kill_conditions", "no_rescue_rule",
    }
    for candidate in census["candidates"]:
        assert required <= candidate.keys(), candidate["candidate_id"]
        assert candidate["safe_known_after"].startswith("SAFE-KNOWN-AFTER")
        assert candidate["no_rescue_rule"]
    jfp01 = census["candidates"][0]
    assert "[t,t+10s)" in jfp01["feature"]
    assert "generic_flow_control" in jfp01
    assert "[t-10s,t)" in jfp01["generic_flow_control"]
    assert "beta_boundary" in jfp01["primary_metric_statistic"]
    assert "2024-11-01T00:00:00Z" in jfp01["historical_discovery_window"]
    assert "2026-07-31T23:45:00Z" in jfp01["historical_discovery_window"]
    jfp03 = census["candidates"][2]
    assert "AFI_t" in jfp03["feature"]
    assert "BUY_SHARE_t" in jfp03["feature"]
    assert "* log" not in jfp03["feature"]
    assert "forecast" not in jfp03["materiality_rule"]
    assert "open interest" in census["prohibited_candidate_classes"]
    assert "ML" in census["prohibited_candidate_classes"]
    assert "volume-surprise multiplication" in census["prohibited_candidate_classes"]
    assert prereg["outcome_blindness"] == {
        "market_data_accessed": False,
        "candidate_outcomes_opened": False,
        "features_computed": False,
        "outcomes_computed": False,
        "historical_execution_performed": False,
        "scientific_result_exists": False,
    }
    authority = prereg["authority"]
    assert all(value is False for key, value in authority.items() if key != "capital_authority")
    assert authority["capital_authority"] == "NONE"
    assert prereg["prospective_observation_contract_v0"]["authority"]["scientific_status"] == "DISCOVERY_ONLY"
    assert prereg["prospective_observation_contract_v0"]["authority"]["capital_authority"] == "NONE"
    assert prereg["historical_contract"]["terminal_classifications"][-1] == "BLOCKED_CANDIDATE"
    assert "candidate-local" in prereg["historical_contract"]["common_sample_rule"]
    assert "exactly three ordered candidate results" in prereg["historical_contract"]["result_semantics"]


if __name__ == "__main__":
    validate()
    print("jigsaw_fast_prospective_signal_discovery_prereg_v0: PASS")
