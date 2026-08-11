"""Synthetic-only execution candidate for the PIT V1 Jigsaw experiment.

The canonical outcome seam accepts authenticated hourly bars whose timestamps
are bar-open times.  It deliberately does not accept anonymous timestamp/price
tuples or logical close endpoints.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any, Mapping, Sequence

from .research_ledger import canonical_bytes, sha256_bytes

EXPERIMENT_ID = "JIGSAW_FUNDING_PRESSURE_VOLATILITY_PREREGISTRATION_V0"
EXECUTION_PHASE_ID = "JIGSAW_FUNDING_PRESSURE_VOLATILITY_EXECUTION_ENABLEMENT_V1"
PREREGISTRATION_MERGE_SHA = "98e9dbcbec5dab18f7498cf4c5df77e14a8d5569"
CONTRACT_DIGEST = "sha256:749641cbee99bc769a6095e2a5877e4ccf1c46db0a82860885eedc06734cd2d6"
PIT_V1_MERGE_SHA = "3e54cb86cdc43c76c1cbf72acc4dfebecb6b10fa"
PIT_V1_CERTIFICATE_DIGEST = "sha256:eee5ce2769e49970a7a4e8d4851d7da569abc156d4f183959b416bfb8dbf188b"
FUNDING_EVIDENCE_SET_DIGEST = "sha256:3677e5aeafd17c47e4951b2095d6247c8fb7cd3fb603cc70d5ea5658fd768faa"
OHLCV_V1_EVIDENCE_SET_DIGEST = "sha256:97760d127e33c51f2ac687f5f8edb92ffa3ac01b1c7c963951872a87ab3b5ae9"
PANEL = ("BCHUSDT", "XRPUSDT", "LTCUSDT", "TRXUSDT", "ETCUSDT", "LINKUSDT", "XLMUSDT", "CHZUSDT", "SANDUSDT", "REEFUSDT", "CHRUSDT", "ALICEUSDT", "ONEUSDT", "API3USDT", "GMTUSDT", "APEUSDT", "OPUSDT", "INJUSDT", "LDOUSDT", "APTUSDT")
FIRST_DECISION = "2023-10-19T00:00:00Z"
LAST_DECISION = "2025-06-19T00:00:00Z"
DECISION_COUNT = 610
LOW_THRESHOLD, HIGH_THRESHOLD = Fraction(1, 3), Fraction(2, 3)
REQUIRED_SOURCE_TIMESTAMP_SEMANTIC = "BAR_OPEN_TIME"
REQUIRED_CLOSE_SEMANTIC = "CLOSE_PRICE_OF_BAR_OPENED_AT_TIMESTAMP"
REQUIRED_ENDPOINT_MAPPING = "BAR_OPEN_TIME_PLUS_1_HOUR"


class InputBindingError(ValueError): pass
class ExecutionNotAuthorizedError(RuntimeError): pass
class DuplicateFundingTimestampError(ValueError): pass


@dataclass(frozen=True)
class FundingEvent:
    symbol: str
    funding_time_ms: int
    funding_time_utc: str
    funding_rate: str


@dataclass(frozen=True)
class BarOpenClose:
    """An authenticated source row: timestamp is the bar open, not its close endpoint."""
    timestamp: datetime
    close: float
    timestamp_semantic: str = REQUIRED_SOURCE_TIMESTAMP_SEMANTIC
    close_semantic: str = REQUIRED_CLOSE_SEMANTIC


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def validate_decision_time(value: datetime) -> datetime:
    value = _utc(value)
    if (value.hour, value.minute, value.second, value.microsecond) != (0, 0, 0, 0):
        raise ValueError("decision_time must be exactly midnight UTC")
    return value


def select_latest_funding_event(events: Sequence[FundingEvent], decision_time: datetime) -> FundingEvent | None:
    t = validate_decision_time(decision_time)
    eligible = [e for e in events if t - timedelta(hours=24) < _utc(datetime.fromisoformat(e.funding_time_utc.replace("Z", "+00:00"))) <= t]
    if not eligible: return None
    latest = max(e.funding_time_ms for e in eligible)
    ties = [e for e in eligible if e.funding_time_ms == latest]
    if len({e.funding_rate for e in ties}) > 1: raise DuplicateFundingTimestampError("disagreeing funding-rate tie")
    return ties[0]


def compute_funding_pressure(panel_events: Mapping[str, FundingEvent | None]) -> Decimal | None:
    if tuple(panel_events) != PANEL: return None
    values = []
    for symbol in PANEL:
        event = panel_events[symbol]
        if event is None or event.symbol != symbol: return None
        try: value = Decimal(event.funding_rate)
        except (InvalidOperation, ValueError): return None
        if not value.is_finite(): return None
        values.append(abs(value))
    values.sort()
    return (values[9] + values[10]) / 2


def compute_pit_ecdf(prior_365: Sequence[Decimal], current: Decimal) -> Fraction:
    if len(prior_365) != 365: raise ValueError("exactly 365 prior observations required")
    values = [*prior_365, current]
    return Fraction(sum(v <= current for v in values), 366)


def classify_funding_state(percentile: Fraction) -> str:
    if percentile <= LOW_THRESHOLD: return "LOW"
    if percentile >= HIGH_THRESHOLD: return "HIGH"
    return "MID"


def compute_hourly_asset_returns(closes: Mapping[str, float], prior_closes: Mapping[str, float]) -> dict[str, float]:
    result = {}
    for symbol, current in closes.items():
        prior = prior_closes.get(symbol)
        if prior is None or not all(isinstance(x, (int, float)) and math.isfinite(x) and x > 0 for x in (prior, current)): continue
        result[symbol] = current / prior - 1.0
    return result


def compute_equal_weight_market_return(asset_returns: Mapping[str, float]) -> float | None:
    if tuple(asset_returns) != PANEL: return None
    return sum(asset_returns[s] for s in PANEL) / 20


def compute_rv24(returns: Sequence[float | None]) -> float | None:
    if len(returns) != 24 or any(r is None or not math.isfinite(r) for r in returns): return None
    return math.sqrt(sum(r * r for r in returns) / 24)


def compute_forward_rv24_from_bar_open_closes(decision_time: datetime, bars_by_symbol: Mapping[str, Sequence[BarOpenClose]]) -> float | None:
    """Map source opens t-1h..t+23h to logical closes t..t+24h, then compute 24 returns."""
    t = validate_decision_time(decision_time)
    if tuple(bars_by_symbol) != PANEL: raise InputBindingError("panel must be the exact ordered 20-member panel")
    required_opens = tuple(t + timedelta(hours=i) for i in range(-1, 24))
    closes_by_symbol: dict[str, tuple[float, ...]] = {}
    for symbol in PANEL:
        rows = bars_by_symbol[symbol]
        if len(rows) != 25: raise ValueError("exactly 25 source bars required")
        seen = set()
        closes = []
        for index, row in enumerate(rows):
            if not isinstance(row, BarOpenClose): raise TypeError("canonical inputs must be BarOpenClose records")
            ts = _utc(row.timestamp)
            if row.timestamp_semantic != REQUIRED_SOURCE_TIMESTAMP_SEMANTIC or row.close_semantic != REQUIRED_CLOSE_SEMANTIC:
                raise InputBindingError("source semantic identity mismatch")
            if ts in seen or ts != required_opens[index]: raise ValueError("source opens must be exactly t-1h..t+23h in order")
            seen.add(ts)
            if not isinstance(row.close, (int, float)) or not math.isfinite(row.close) or row.close <= 0: raise ValueError("invalid close")
            closes.append(float(row.close))
        closes_by_symbol[symbol] = tuple(closes)
    returns = []
    for i in range(24):
        interval = {s: closes_by_symbol[s][i + 1] / closes_by_symbol[s][i] - 1.0 for s in PANEL}
        market = compute_equal_weight_market_return(interval)
        if market is None: return None
        returns.append(market)
    return compute_rv24(returns)


def compute_primary_contrast(rows: Sequence[tuple[str, float]]) -> dict[str, Any]:
    high = [v for state, v in rows if state == "HIGH"]
    low = [v for state, v in rows if state == "LOW"]
    mid = sum(state == "MID" for state, _ in rows)
    if not high or not low: return {"value": None, "high_count": len(high), "low_count": len(low), "mid_count": mid, "blocked_reason": "EMPTY_REQUIRED_PRIMARY_BIN"}
    mh, ml = sum(high) / len(high), sum(low) / len(low)
    return {"value": mh - ml, "mean_high": mh, "mean_low": ml, "high_count": len(high), "low_count": len(low), "mid_count": mid, "blocked_reason": None}


def compute_preregistered_robustness(primary: Mapping[str, Any]) -> dict[str, Any]:
    return {"canonical_robustness_checks_defined_in_contract": (), "checks": {}, "primary_value_echo_readonly": primary.get("value")}


def validate_input_binding(binding: Mapping[str, Any]) -> None:
    expected = {"preregistration_merge_sha": PREREGISTRATION_MERGE_SHA, "contract_digest": CONTRACT_DIGEST, "pit_v1_merge_sha": PIT_V1_MERGE_SHA, "pit_v1_certificate_digest": PIT_V1_CERTIFICATE_DIGEST, "funding_evidence_set_digest": FUNDING_EVIDENCE_SET_DIGEST, "ohlcv_v1_evidence_set_digest": OHLCV_V1_EVIDENCE_SET_DIGEST}
    for key, value in expected.items():
        if binding.get(key) != value: raise InputBindingError(f"{key} mismatch")
    if tuple(binding.get("panel", ())) != PANEL: raise InputBindingError("panel mismatch")
    window = binding.get("decision_window", {})
    if (window.get("first_decision"), window.get("last_decision"), window.get("decision_count")) != (FIRST_DECISION, LAST_DECISION, DECISION_COUNT): raise InputBindingError("decision window mismatch")
    if (binding.get("source_timestamp_semantic"), binding.get("close_semantic"), binding.get("logical_endpoint_mapping")) != (REQUIRED_SOURCE_TIMESTAMP_SEMANTIC, REQUIRED_CLOSE_SEMANTIC, REQUIRED_ENDPOINT_MAPPING): raise InputBindingError("source semantic binding mismatch")


REQUIRED_EXECUTION_SCOPE = "ONE_FROZEN_HISTORICAL_RUN"
REQUIRED_OUTCOME_ACCESS_SCOPE = "EXACT_PREREGISTERED_OUTCOMES_ONLY"


def authorize_execution(mode: str, authorization: Mapping[str, Any] | None, *, actual_execution_implementation_sha: str | None = None) -> None:
    if mode == "SYNTHETIC_FIXTURE": return
    if mode != "REAL_HISTORICAL": raise ValueError("unknown execution mode")
    if authorization is None or not isinstance(actual_execution_implementation_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", actual_execution_implementation_sha): raise ExecutionNotAuthorizedError("real execution requires external authorization and runtime SHA")
    required = {"experiment_id": EXPERIMENT_ID, "preregistration_merge_sha": PREREGISTRATION_MERGE_SHA, "contract_digest": CONTRACT_DIGEST, "pit_v1_merge_sha": PIT_V1_MERGE_SHA, "pit_v1_certificate_digest": PIT_V1_CERTIFICATE_DIGEST, "execution_implementation_sha": actual_execution_implementation_sha, "funding_evidence_set_digest": FUNDING_EVIDENCE_SET_DIGEST, "ohlcv_v1_evidence_set_digest": OHLCV_V1_EVIDENCE_SET_DIGEST, "execution_scope": REQUIRED_EXECUTION_SCOPE, "outcome_access_scope": REQUIRED_OUTCOME_ACCESS_SCOPE}
    if any(authorization.get(k) != v for k, v in required.items()) or "authorization_id" not in authorization: raise ExecutionNotAuthorizedError("authorization binding mismatch")


def build_execution_receipt(*, decision_window: Mapping[str, Any], census: Mapping[str, int], state_counts: Mapping[str, int], primary: Mapping[str, Any], robustness: Mapping[str, Any], adjudication: str, execution_implementation_identity: str, artifact_hashes: Mapping[str, str]) -> dict[str, Any]:
    body = {"experiment_id": EXPERIMENT_ID, "execution_phase_id": EXECUTION_PHASE_ID, "preregistration_merge_sha": PREREGISTRATION_MERGE_SHA, "contract_digest": CONTRACT_DIGEST, "pit_v1_merge_sha": PIT_V1_MERGE_SHA, "pit_v1_certificate_digest": PIT_V1_CERTIFICATE_DIGEST, "funding_evidence_set_digest": FUNDING_EVIDENCE_SET_DIGEST, "ohlcv_v1_evidence_set_digest": OHLCV_V1_EVIDENCE_SET_DIGEST, "panel": list(PANEL), "decision_window": dict(decision_window), "census": dict(census), "state_counts": dict(state_counts), "primary_statistic_identity": "mean(RV24|HIGH) - mean(RV24|LOW)", "primary_statistic": dict(primary), "robustness": dict(robustness), "adjudication": adjudication, "execution_implementation_identity": execution_implementation_identity, "artifact_hashes": dict(artifact_hashes), "execution_authority": "NONE", "outcome_access_authority": "NONE"}
    body["receipt_digest"] = sha256_bytes(canonical_bytes(body))
    return body


def receipt_json(receipt: Mapping[str, Any]) -> str:
    return json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
