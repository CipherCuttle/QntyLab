"""Outcome-blind validator for Jigsaw Fast V1 preregistration artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments/research/jigsaw_fast_prospective_signal_discovery_v1"

def load(name: str) -> dict:
    return json.loads((EXPERIMENT / name).read_text())

def canonical_digest(value: dict, field: str) -> str:
    body = dict(value); body.pop(field, None)
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def validate() -> None:
    census = load("candidate_census.json"); prereg = load("preregistration.json")
    candidates = census["candidates"]
    assert census["candidate_count"] == len(candidates) == 10
    assert len({c["candidate_id"] for c in candidates}) == 10
    assert any(c["candidate_id"] == "JFPV1_01" and c["selection_status"] == "REJECTED_PREMERGE_NONIDENTIFIABLE_CONTRACT" for c in candidates)
    assert any(c["candidate_id"] == "JFPV1_10" and c.get("repair_selection_status") == "FINALIST_REPLACEMENT" for c in candidates)
    assert prereg["exploratory_candidate_count"] == 10
    assert prereg["final_confirmatory_candidate_count"] == 5
    assert prereg["finalist_ids"] == ["JFPV1_02", "JFPV1_03", "JFPV1_04", "JFPV1_05", "JFPV1_10"]
    assert {c["candidate_id"] for c in prereg["finalist_contracts"]} == set(prereg["finalist_ids"])
    assert all(c["input_class"] == "DATA_SPINE_REUSE" for c in prereg["finalist_contracts"])
    assert all(c["expected_implementation_complexity"] == "SMALL" for c in prereg["finalist_contracts"])
    for contract in prereg["finalist_contracts"]:
        assert contract["feature"] not in contract["baseline"]
        assert contract["feature"] and contract["outcome"] and contract["horizon"]
    repair = prereg["repair_provenance"]
    assert repair["pre_outcome_repair"] is True
    assert repair["demoted_candidate"] == "JFPV1_01"
    assert repair["replacement_candidate"] == "JFPV1_10"
    assert repair["replacement_selection_used_only_frozen_census"] is True
    assert repair["no_new_candidate_created"] is True
    assert repair["no_rescoring_performed"] is True
    assert prereg["multiplicity"]["confirmatory_family_size"] == 5
    assert "null p-values" in prereg["multiplicity"]["blocked_candidate_denominator_policy"]
    assert all(v is False for k, v in prereg["authority"].items() if k != "capital_authority")
    assert prereg["authority"]["capital_authority"] == "NONE"
    assert all(v is False for v in prereg["outcome_blindness"].values())
    assert canonical_digest(census, "candidate_census_digest") == census["candidate_census_digest"]
    assert canonical_digest(prereg, "preregistration_digest") == prereg["preregistration_digest"]

if __name__ == "__main__":
    validate(); print("jigsaw_fast_prospective_signal_discovery_prereg_v1: PASS")
