"""Outcome-blind prospective-timing gate for the frozen JH01 V0 protocol.

This module is deliberately calendar/provenance-only.  It neither reads nor
acquires market data, and it cannot fit, create, or evaluate a forecast.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Iterable, Mapping


PROJECT_ID = "JH01_RV_PERSISTENCE_INCREMENTAL_FORECAST_VALUE_INPUT_MATERIALIZATION_AUTHORIZATION_V0"
CANDIDATE_ID = "CANDIDATE_JH01_RV_PERSISTENCE_INCREMENTAL_FORECAST_VALUE_V0"
FIRST_DECISION = "2026-07-20T00:00:00Z"
LAST_DECISION = "2027-07-19T00:00:00Z"
REQUIRED_ORIGINS = 365
FORECAST_HORIZON = timedelta(hours=24)
IMMUTABLE_MECHANISMS = frozenset({"GIT_COMMIT", "GIT_REF", "CANONICAL_APPEND_ONLY_RECEIPT", "IMMUTABLE_CLAIM"})


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def format_time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def origins() -> tuple[datetime, ...]:
    first, last = parse_time(FIRST_DECISION), parse_time(LAST_DECISION)
    values = tuple(first + timedelta(days=index) for index in range(REQUIRED_ORIGINS))
    if values[-1] != last:
        raise ValueError("FROZEN_ORIGIN_SCHEDULE_INVALID")
    return values


def pre_freeze_origins(freeze_time: str) -> tuple[datetime, ...]:
    freeze = parse_time(freeze_time)
    return tuple(origin for origin in origins() if origin + FORECAST_HORIZON <= freeze)


def receipt_is_valid(receipt: Mapping[str, Any], origin: datetime) -> bool:
    """Accept only identity-bound immutable evidence strictly before target time."""
    if receipt.get("candidate_id") != CANDIDATE_ID:
        return False
    if receipt.get("forecast_origin") != format_time(origin):
        return False
    if not isinstance(receipt.get("forecast_artifact_digest"), str) or not receipt["forecast_artifact_digest"]:
        return False
    if receipt.get("persistence_mechanism") not in IMMUTABLE_MECHANISMS:
        return False
    if receipt.get("immutable") is not True or receipt.get("committed") is not True:
        return False
    try:
        persisted = parse_time(str(receipt["persistence_time"]))
    except (KeyError, TypeError, ValueError):
        return False
    return origin <= persisted < origin + FORECAST_HORIZON


def assess(freeze_time: str, receipts: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Return the fail-closed disposition without inspecting any target value."""
    elapsed = pre_freeze_origins(freeze_time)
    receipt_rows = tuple(receipts)
    missing = tuple(origin for origin in elapsed if not any(receipt_is_valid(row, origin) for row in receipt_rows))
    integrity = (
        "ESTABLISHED"
        if not missing
        else "FAILED_FROZEN_START_ALREADY_ELAPSED_WITHOUT_PERSISTED_FORECAST"
    )
    return {
        "pre_freeze_origins": tuple(format_time(origin) for origin in elapsed),
        "missing_pre_target_forecast_origins": tuple(format_time(origin) for origin in missing),
        "prospective_integrity": integrity,
        "materialization_authorized": integrity == "ESTABLISHED",
        "scientific_execution_authorized": False,
    }
