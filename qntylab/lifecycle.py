"""Outcome-blind lifecycle reconstruction primitives for qualification samples.

This module intentionally has no price, return, ranking, or portfolio concepts.
It turns timestamped evidence into conservative instrument instances and
point-in-time tradability states only.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Iterable


STATE_ORDER = {
    "UNKNOWN": 0,
    "PRELAUNCH": 1,
    "OBSERVED_NOT_ELIGIBLE": 2,
    "TRADABLE": 3,
    "TEMPORARILY_UNOBSERVABLE": 4,
    "TERMINATED_AMBIGUOUS": 5,
    "TERMINATED_VERIFIED": 6,
}


@dataclass(frozen=True)
class EvidenceEvent:
    event_time: str
    claim: str
    grade: str
    source: str
    raw_identity: str


def instrument_instance_id(*, venue: str, symbol: str, contract_type: str,
                           first_observed: str, symbol_id: str | int | None = None) -> str:
    """Stable identity: a missing exchange id never creates presumed continuity."""
    parts = [venue.lower(), str(symbol).upper(), contract_type.lower(), first_observed]
    if symbol_id is not None:
        parts.append(f"symbol-id={symbol_id}")
    return "|".join(parts)


def state_at(events: Iterable[EvidenceEvent], at: str) -> str:
    """Return the latest causally known state; event input need not be ordered."""
    known = [event for event in events if event.event_time <= at]
    if not known:
        return "UNKNOWN"
    latest = max(known, key=lambda event: (event.event_time, STATE_ORDER.get(event.claim, -1)))
    if latest.claim not in STATE_ORDER:
        raise ValueError(f"unknown lifecycle claim: {latest.claim}")
    return latest.claim


def eligible_at(events: Iterable[EvidenceEvent], at: str) -> bool:
    """Eligibility is strictly point-in-time and never treats an outage as tradable."""
    return state_at(events, at) == "TRADABLE"


def terminal_policy(*, state: str, exposed: bool, settlement_available: bool) -> str:
    """Frozen fail-closed terminal rule; callers must supply exposure, not a price."""
    if state == "TERMINATED_VERIFIED" and settlement_available:
        return "PROCESS_FROZEN_SETTLEMENT_RULE"
    if state == "TERMINATED_AMBIGUOUS" and exposed:
        return "BLOCKED_BY_DATA_INTEGRITY"
    if state == "TERMINATED_AMBIGUOUS":
        return "REMOVE_AFTER_LAST_VERIFIED_TRADABLE_STATE"
    return "NO_TERMINAL_ACTION"


def receipt_root(receipts: Iterable[dict]) -> str:
    """Deterministic root for source receipts without examining market outcomes."""
    canonical = json.dumps(sorted(receipts, key=lambda row: json.dumps(row, sort_keys=True)),
                           sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(canonical.encode()).hexdigest()
