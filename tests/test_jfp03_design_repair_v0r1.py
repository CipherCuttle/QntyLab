from __future__ import annotations

import hashlib
import json
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "experiments/research/jigsaw_fast_prospective_signal_discovery_v0/jfp03_design_repair_v0r1.json"
PREREG = ROOT / "experiments/research/jigsaw_fast_prospective_signal_discovery_v0/preregistration.json"
CENSUS = ROOT / "experiments/research/jigsaw_fast_prospective_signal_discovery_v0/candidate_census.json"


def _digest_without_design_digest(value: dict) -> str:
    body = {key: item for key, item in value.items() if key != "design_digest"}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def test_design_repair_is_deterministic_and_outcome_blind() -> None:
    design = json.loads(DESIGN.read_text())
    assert design["design_digest"] == _digest_without_design_digest(design)
    assert design["prior_real_execution_count"] == 0
    assert design["prior_execution_started"] is False
    assert design["scientific_features_computed"] is False
    assert design["scientific_outcomes_computed"] is False
    assert design["selected_har_construction"] == "CONTIGUOUS_HORIZON_RV"
    assert design["execution_authorization"]["v0r1_project_created"] is False


def test_har_contract_has_exact_boundaries_and_cardinalities() -> None:
    components = json.loads(DESIGN.read_text())["har_components"]
    assert [components[key]["return_count"] for key in ("HAR_1H_t", "HAR_24H_t", "HAR_168H_t", "HAR_720H_t")] == [1, 24, 168, 720]
    assert all(component["last_included_close"] == "C_t" for component in components.values())
    assert all(component["maximum_timestamp"] == "t" for component in components.values() if "maximum_timestamp" in component)
    target = json.loads(DESIGN.read_text())["future_target"]
    assert target["return_indices"] == "r_(t+1h)..r_(t+24h)"
    assert target["return_count"] == 24


def test_existing_snapshot_is_rejected_structurally_without_opening_values() -> None:
    design = json.loads(DESIGN.read_text())
    compatibility = design["materialization_compatibility"]
    assert compatibility["existing_snapshot_compatible"] is False
    assert compatibility["input_reacquisition_authorized"] is False
    assert compatibility["authenticated_jfp03_object_count"] == 60
    assert "2019-12-02T00:00:00Z" in compatibility["structural_reason"]


def test_original_scientific_artifacts_are_unchanged_and_v0_is_closed() -> None:
    assert json.loads(PREREG.read_text())["preregistration_digest"] == "9e9236b34b131c13cebfb0b8043ef59043b2928fa6fcd88dd7b10909d9e8ccfe"
    assert json.loads(CENSUS.read_text())["candidate_ids"] == ["JFP01", "JFP02", "JFP03"]
    _, _, registry = project_context.load_context_sources(ROOT)
    v0 = next(item for item in registry["project"] if item["project_id"] == "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_HISTORICAL_EXECUTION_V0")
    assert v0["state"] == "CLOSED_BLOCKED"
    assert v0["terminal_reason"] == "FROZEN_DESIGN_UNDERSPECIFIED_BEFORE_REAL_ACCESS"
    assert v0["real_execution_count"] == 0
    assert v0["execution_started"] is False
    assert v0["jfp03_execution_authorized"] is False
    assert not list((DESIGN.parent / "execution").glob("execution_started.json")) if (DESIGN.parent / "execution").exists() else True
