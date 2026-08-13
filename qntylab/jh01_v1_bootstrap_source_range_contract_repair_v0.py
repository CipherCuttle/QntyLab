"""Deterministic UTC dependency arithmetic for the JH01 V1 bootstrap repair.

This module deliberately consumes no source data.  Its timestamps are logical
hourly close boundaries, not provider-specific raw kline close timestamps.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


class SourceRangeContractError(ValueError):
    """Raised when the bounded frozen schedule is internally inconsistent."""


@dataclass(frozen=True)
class BootstrapSourceRange:
    first_live_origin: datetime
    forecast_horizon_hours: int
    strict_completion_operator: str
    required_initial_training_origins: int
    b3_longest_lag_days: int
    rv24_return_count: int
    latest_eligible_training_origin: datetime
    first_training_origin: datetime
    training_origins: tuple[datetime, ...]
    b3_rv24_origins: tuple[datetime, ...]
    rv24_return_closes: tuple[datetime, ...]
    earliest_b3_rv24_origin: datetime
    earliest_required_return_close: datetime
    earliest_required_source_close: datetime
    latest_required_completed_training_target_close: datetime


def derive_bootstrap_source_range(
    first_live_origin: datetime,
    *,
    forecast_horizon_hours: int = 24,
    required_initial_training_origins: int = 365,
    b3_longest_lag_days: int = 29,
    rv24_return_count: int = 24,
) -> BootstrapSourceRange:
    """Derive the exact logical-close dependency range for frozen JH01 V1.

    The completion condition is intentionally strict: ``o + horizon < T``.
    Daily origins are midnight UTC points, so an origin whose target completes
    at ``T`` is moved back one additional day.
    """
    if first_live_origin.tzinfo is None or first_live_origin.utcoffset() != timedelta(0):
        raise SourceRangeContractError("first_live_origin must be UTC-aware")
    if first_live_origin.time() != datetime.min.time():
        raise SourceRangeContractError("first_live_origin must be a midnight UTC daily origin")
    if min(forecast_horizon_hours, required_initial_training_origins, rv24_return_count) <= 0:
        raise SourceRangeContractError("horizon, training count, and RV return count must be positive")
    if b3_longest_lag_days < 0:
        raise SourceRangeContractError("B3 longest lag must be non-negative")

    horizon = timedelta(hours=forecast_horizon_hours)
    latest = first_live_origin - horizon
    # Equality is ineligible under o + horizon < T.
    if latest + horizon >= first_live_origin:
        latest -= timedelta(days=1)
    training_origins = tuple(latest - timedelta(days=index) for index in range(required_initial_training_origins))
    first_training = training_origins[-1]
    b3_rv24_origins = tuple(first_training - timedelta(days=index) for index in range(b3_longest_lag_days + 1))
    earliest_rv24 = b3_rv24_origins[-1]
    rv24_return_closes = tuple(earliest_rv24 - timedelta(hours=index) for index in range(rv24_return_count - 1, -1, -1))
    earliest_return = rv24_return_closes[0]
    earliest_source_close = earliest_return - timedelta(hours=1)
    latest_target_close = latest + horizon

    return BootstrapSourceRange(
        first_live_origin=first_live_origin,
        forecast_horizon_hours=forecast_horizon_hours,
        strict_completion_operator=f"o + {forecast_horizon_hours}h < T",
        required_initial_training_origins=required_initial_training_origins,
        b3_longest_lag_days=b3_longest_lag_days,
        rv24_return_count=rv24_return_count,
        latest_eligible_training_origin=latest,
        first_training_origin=first_training,
        training_origins=training_origins,
        b3_rv24_origins=b3_rv24_origins,
        rv24_return_closes=rv24_return_closes,
        earliest_b3_rv24_origin=earliest_rv24,
        earliest_required_return_close=earliest_return,
        earliest_required_source_close=earliest_source_close,
        latest_required_completed_training_target_close=latest_target_close,
    )
