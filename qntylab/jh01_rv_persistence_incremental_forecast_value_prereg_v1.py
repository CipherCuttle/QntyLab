"""Static, outcome-blind V1 prospective forecast-persistence contract."""
from __future__ import annotations

import hashlib
import json
import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

EXPERIMENT_ID = "JH01_RV_PERSISTENCE_INCREMENTAL_FORECAST_VALUE_PREREG_V1"
CANDIDATE_ID = "CANDIDATE_JH01_RV_PERSISTENCE_INCREMENTAL_FORECAST_VALUE_V1"
ARTIFACT = Path("experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/preregistration.json")
FIRST_DECISION = "2026-09-15T00:00:00Z"
LAST_DECISION = "2027-09-14T00:00:00Z"
REQUIRED_ORIGINS = 365


class ContractError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def contract_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes({key: item for key, item in value.items() if key != "preregistration_digest"})).hexdigest()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def origins() -> tuple[datetime, ...]:
    first, last = parse_time(FIRST_DECISION), parse_time(LAST_DECISION)
    values = tuple(first + timedelta(days=index) for index in range(REQUIRED_ORIGINS))
    if values[-1] != last:
        raise ContractError("frozen schedule is not exactly 365 inclusive daily origins")
    return values


def canonical_freeze_is_eligible(canonical_merge_time: str) -> bool:
    """Fail closed: a canonical merge after the frozen deadline blocks V1."""
    return parse_time(canonical_merge_time) <= parse_time("2026-09-01T00:00:00Z")


def validate_canonical_freeze(value: Mapping[str, Any], canonical_merge_time: str) -> None:
    """Mandatory canonical-merge gate; a late merge blocks the exact V1."""
    validate(value)
    if value["preregistration_lead_time"]["canonical_freeze_gate"] != "MANDATORY_BEFORE_CANONICAL_MERGE":
        raise ContractError("canonical freeze gate not mandatory")
    if not canonical_freeze_is_eligible(canonical_merge_time):
        raise ContractError("PREREG_CANONICAL_FREEZE_TOO_LATE")


def load_preregistration(root: Path) -> dict[str, Any]:
    return json.loads((root / ARTIFACT).read_text(encoding="utf-8"))


def validate(value: Mapping[str, Any]) -> None:
    if value.get("experiment_id") != EXPERIMENT_ID or value.get("candidate_id") != CANDIDATE_ID:
        raise ContractError("V1 identity mismatch")
    if value.get("preregistration_digest") != contract_digest(value):
        raise ContractError("preregistration digest mismatch")
    if value.get("scientific_diff_from_v0") != "TIMING_AND_PROSPECTIVE_GOVERNANCE_ONLY":
        raise ContractError("scientific-diff invariant broken")
    holdout = value["evaluation_design"]["prospective_holdout"]
    if (holdout["first_decision"], holdout["last_decision"], holdout["required_valid_origins"], holdout["maximum_valid_origins"]) != (FIRST_DECISION, LAST_DECISION, 365, 365):
        raise ContractError("holdout schedule mismatch")
    persistence = value["forecast_persistence_contract"]
    if persistence["feature_information_cutoff"] != "MAX_INPUT_BAR_CLOSE <= t" or persistence["open_or_partial_future_bars"] != "PROHIBITED" or persistence["persistence_window"] != "t <= persistence_time < t + 1 hour":
        raise ContractError("prospective persistence boundary mismatch")
    target = value["frozen_target"]
    panel = target.get("ordered_20_symbol_panel")
    if not isinstance(panel, list) or len(panel) != 20 or len(set(panel)) != 20:
        raise ContractError("exact ordered panel mismatch")
    if hashlib.sha256(canonical_bytes(panel)).hexdigest() != target.get("ordered_20_symbol_panel_sha256"):
        raise ContractError("ordered panel digest mismatch")
    if value.get("classification") is None or value.get("search_accounting") is None:
        raise ContractError("frozen classification or search accounting missing")
    lead = value["preregistration_lead_time"]
    if lead["minimum_canonical_prereg_lead_days"] != 14 or lead["canonical_freeze_deadline"] != "2026-09-01T00:00:00Z":
        raise ContractError("lead-time invariant mismatch")
    if lead["canonical_freeze_gate"] != "MANDATORY_BEFORE_CANONICAL_MERGE":
        raise ContractError("canonical freeze gate not mandatory")
    source = value["source_binding"]
    if source["mutable_global_synthesis_aggregate_byte_pinned"] is not False or source["jigsaw_pair_attestation_at_freeze"]["independent_replication_established"] is not False:
        raise ContractError("synthesis binding invalid")
    if value["sealed_evaluation"]["interim_scientific_evaluation"] != "PROHIBITED":
        raise ContractError("interim evaluation is not sealed")
    if any(item is not False for item in value["outcome_blindness"].values()) or any(item is not False for item in value["authority"].values()):
        raise ContractError("outcome-blindness or authority breach")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the mandatory V1 canonical-freeze lead-time gate")
    parser.add_argument("--canonical-merge-time", required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    validate_canonical_freeze(load_preregistration(args.root), args.canonical_merge_time)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
