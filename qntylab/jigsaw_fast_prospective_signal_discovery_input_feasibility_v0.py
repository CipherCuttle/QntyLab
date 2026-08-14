"""Validator for the outcome-free V1 input-feasibility authority record."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/jigsaw_fast_prospective_signal_discovery_v1/input_feasibility_v0.json"

def load() -> dict:
    return json.loads(ARTIFACT.read_text())

def canonical_digest(value: dict) -> str:
    body = dict(value); body.pop("authorization_digest", None)
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def validate() -> None:
    x = load()
    assert x["project_state"] == "CLOSED_BLOCKED"
    assert x["canonical_finalist_ids"] == ["JFPV1_02", "JFPV1_03", "JFPV1_04", "JFPV1_05", "JFPV1_10"]
    assert x["exploratory_denominator"] == 10
    assert x["confirmatory_family_size"] == 5
    assert x["ready_finalist_count"] == 0
    assert x["blocked_input_contract_ids"] == x["canonical_finalist_ids"]
    assert len(x["finalist_feasibility"]) == 5
    assert all(row["input_status"] == "BLOCKED_INPUT_CONTRACT" for row in x["finalist_feasibility"])
    assert x["rds_forensics"]["panel_symbols"] and "BTCUSDT" not in x["rds_forensics"]["panel_symbols"]
    assert all(value is False for key, value in x["authority"].items() if isinstance(value, bool))
    assert x["authority"]["capital_authority"] == "NONE"
    assert x["hostile_review"] == {"count": 1, "critical": 0, "high": 0, "targeted_rereview_used": False, "result": "PASS"}
    assert canonical_digest(x) == x["authorization_digest"]

if __name__ == "__main__":
    validate(); print("jigsaw_fast_prospective_signal_discovery_input_feasibility_v0: PASS")
