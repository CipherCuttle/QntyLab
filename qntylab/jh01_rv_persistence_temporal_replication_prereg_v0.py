"""Outcome-blind validator for the frozen JH01 temporal-replication contract.

This module deliberately has no market-data reader, network client,
materializer, feature builder, outcome builder, regression, or CLI.  It only
validates the static preregistration artifact before a separately authorized
future phase may consider any inputs.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping


EXPERIMENT_ID = "JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_PREREG_V0"
ARTIFACT_RELATIVE_PATH = Path("experiments/research/jh01_rv_persistence_temporal_replication_v0/preregistration.json")
SOURCE_PROJECT_ID = "JIGSAW_HARVEST_V0"
SOURCE_EXPERIMENT_ID = "JIGSAW_HARVEST_V0_PREREGISTRATION_V0"
SOURCE_PIECE_ID = "JH01_RV_PERSISTENCE"
SOURCE_PREREGISTRATION_DIGEST = "499b355ee2b308b4ae01e8c63b44a9a361d44d50fe381080131f41a4851849e3"
SOURCE_SNAPSHOT_ID = "rds-v0-c0fa7dc0e51c7680fccbd7e7cdd0945fcd63af3e8c75809a24aa3b216868b9ac"
SOURCE_SNAPSHOT_DIGEST = "c0fa7dc0e51c7680fccbd7e7cdd0945fcd63af3e8c75809a24aa3b216868b9ac"
UNIVERSE = (
    "ALICEUSDT", "APEUSDT", "API3USDT", "APTUSDT", "BCHUSDT", "CHRUSDT", "CHZUSDT", "ETCUSDT", "GMTUSDT", "INJUSDT",
    "LDOUSDT", "LINKUSDT", "LTCUSDT", "ONEUSDT", "OPUSDT", "REEFUSDT", "SANDUSDT", "TRXUSDT", "XLMUSDT", "XRPUSDT",
)
FIRST_DECISION = "2025-07-20T00:00:00Z"
LAST_DECISION = "2026-07-19T00:00:00Z"
REQUIRED_FIRST_BAR_OPEN = "2025-07-18T23:00:00Z"
REQUIRED_LAST_BAR_OPEN = "2026-07-19T23:00:00Z"
OBSERVATION_COUNT = 365
EXPECTED_HAC_LAG = 5
REQUIRED_KILL_CONDITIONS = frozenset(
    {
        "SOURCE_JH01_IDENTITY_MISMATCH", "SOURCE_PREREGISTRATION_DIGEST_MISMATCH", "SOURCE_SNAPSHOT_IDENTITY_MISMATCH", "REPLICATION_WINDOW_MISMATCH", "REPLICATION_OVERLAPS_DISCOVERY_HISTORY", "UNIVERSE_MISMATCH", "SYMBOL_SUBSTITUTION_ATTEMPT", "SURVIVOR_REWEIGHTING_ATTEMPT", "REQUIRED_COVERAGE_MISMATCH", "COVERAGE_GAP", "HOURLY_CONTINUITY_FAILURE", "BAR_TIME_SEMANTIC_MISMATCH", "SAFE_KNOWN_AFTER_VIOLATION", "OUTCOME_LEAKAGE", "DECISION_SCHEDULE_MISMATCH", "T_NOT_365", "RETURN_SEMANTIC_DRIFT", "FEATURE_RECIPE_DRIFT", "OUTCOME_RECIPE_DRIFT", "HAC_LAG_MISMATCH", "NONFINITE_PRICE_OR_DERIVED_VALUE", "OUTCOME_ACCESSED_BEFORE_FREEZE", "UNAUTHORIZED_MATERIALIZATION", "UNAUTHORIZED_EXECUTION", "POST_FREEZE_SCIENTIFIC_MUTATION",
    }
)


class ContractError(ValueError):
    """The frozen preregistration contract is incomplete or has drifted."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def contract_digest(value: Mapping[str, Any]) -> str:
    """Hash scientific content without its self-referential digest field."""
    body = {key: item for key, item in value.items() if key != "preregistration_digest"}
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def universe_digest(universe: tuple[str, ...] | list[str]) -> str:
    return hashlib.sha256(canonical_bytes(list(universe))).hexdigest()


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ContractError("timezone-aware UTC timestamp required")
    return parsed.astimezone(UTC)


def _stamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def derive_required_bar_coverage(first_decision: str, last_decision: str) -> tuple[str, str]:
    """Derive raw 1h bar-open coverage from the frozen return boundaries."""
    first, last = _utc(first_decision), _utc(last_decision)
    first_feature_return_close = first - timedelta(hours=23)
    first_required_bar_open = first_feature_return_close - timedelta(hours=2)
    final_outcome_return_close = last + timedelta(hours=24)
    last_required_bar_open = final_outcome_return_close - timedelta(hours=1)
    return _stamp(first_required_bar_open), _stamp(last_required_bar_open)


def hac_lag(observation_count: int) -> int:
    return math.floor(4 * (observation_count / 100) ** (2 / 9))


def load_preregistration(root: Path) -> dict[str, Any]:
    """Load only the static local contract artifact; no research inputs are read."""
    return json.loads((root / ARTIFACT_RELATIVE_PATH).read_text(encoding="utf-8"))


def validate(value: Mapping[str, Any]) -> None:
    if value.get("experiment_id") != EXPERIMENT_ID:
        raise ContractError("experiment identity mismatch")
    if value.get("preregistration_digest") != contract_digest(value):
        raise ContractError("preregistration digest mismatch")
    source = value.get("source_binding")
    expected_source = {
        "source_project_id": SOURCE_PROJECT_ID,
        "source_experiment_id": SOURCE_EXPERIMENT_ID,
        "source_piece_id": SOURCE_PIECE_ID,
        "source_preregistration_digest": SOURCE_PREREGISTRATION_DIGEST,
        "source_snapshot_id": SOURCE_SNAPSHOT_ID,
        "source_snapshot_digest": SOURCE_SNAPSHOT_DIGEST,
    }
    if not isinstance(source, Mapping) or any(source.get(key) != item for key, item in expected_source.items()):
        raise ContractError("source binding mismatch")
    if (tuple(value.get("ordered_universe", ())), value.get("universe_count"), value.get("universe_digest")) != (UNIVERSE, 20, universe_digest(UNIVERSE)):
        raise ContractError("ordered universe mismatch")
    schedule = value.get("decision_schedule")
    if not isinstance(schedule, Mapping):
        raise ContractError("decision schedule is required")
    if (schedule.get("first_decision"), schedule.get("last_decision"), schedule.get("decision_count")) != (
        FIRST_DECISION, LAST_DECISION, OBSERVATION_COUNT,
    ):
        raise ContractError("decision schedule mismatch")
    if schedule.get("frequency") != "P1D" or schedule.get("decision_time") != "00:00:00Z":
        raise ContractError("decision cadence mismatch")
    if _utc(LAST_DECISION) - _utc(FIRST_DECISION) != timedelta(days=OBSERVATION_COUNT - 1):
        raise ContractError("decision count is not calendar-consistent")
    coverage = value.get("required_raw_coverage")
    if not isinstance(coverage, Mapping):
        raise ContractError("raw coverage is required")
    if coverage.get("bar_interval") != "1h" or (coverage.get("first_bar_open"), coverage.get("last_bar_open")) != derive_required_bar_coverage(FIRST_DECISION, LAST_DECISION):
        raise ContractError("raw coverage does not follow the return algebra")
    measurement = value.get("measurement")
    if not isinstance(measurement, Mapping) or measurement.get("return_semantics") != "r_i,h = log(C_i,h / C_i,h-1), with finite strictly positive closes required for every exact panel member." or measurement.get("market_return") != "r_m,h = (1/20) * sum_i r_i,h over the exact ordered 20-symbol panel; no capitalization, volume, availability, or survivor weighting." or measurement.get("feature") != "RV24_prior,t = sqrt(sum_{h=t-23}^{t} r_m,h^2)." or measurement.get("outcome") != "RV24_future,t = sqrt(sum_{h=t+1}^{t+24} r_m,h^2).":
        raise ContractError("measurement recipe mismatch")
    inference = value.get("inference")
    if not isinstance(inference, Mapping) or hac_lag(OBSERVATION_COUNT) != EXPECTED_HAC_LAG or inference.get("hac_lag") != EXPECTED_HAC_LAG or inference.get("hypothesis_count") != 1 or inference.get("estimator") != "OLS_WITH_INTERCEPT" or inference.get("holm_adjustment") != "NOT_USED" or inference.get("effect_size_ratio_threshold") != "NOT_USED" or inference.get("pooling_or_meta_analysis") != "PROHIBITED":
        raise ContractError("HAC lag mismatch")
    independence = value.get("independence_contract")
    if not isinstance(independence, Mapping) or independence.get("replication_decision_dates_overlap_discovery") is not False or independence.get("replication_outcome_dates_overlap_discovery") is not False or independence.get("self_declaration_sufficient_for_independence") is not False or independence.get("same_history_reproduction_counts_as_replication") is not False:
        raise ContractError("independence contract mismatch")
    if not REQUIRED_KILL_CONDITIONS.issubset(set(value.get("kill_conditions", ()))):
        raise ContractError("kill conditions incomplete")
    if value.get("status") != "NOT_EXECUTED" or value.get("research_status") != "PREREGISTERED_MATERIALIZATION_NOT_AUTHORIZED":
        raise ContractError("outcome-blind status mismatch")
    if any(item is not False for item in value.get("outcome_blindness", {}).values()):
        raise ContractError("outcome-blindness breach declared")
    if not str(value.get("jigsaw_index_eligibility", "")).startswith("NOT_A_JIGSAW_EVIDENCE_PIECE"):
        raise ContractError("self-ingestion is not blocked")
    authority = value.get("authority")
    if not isinstance(authority, Mapping) or not authority or any(item != "NONE" for item in authority.values()):
        raise ContractError("unauthorized materialization or execution authority")
