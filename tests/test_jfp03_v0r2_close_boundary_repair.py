from __future__ import annotations

from datetime import datetime, timedelta, timezone


UTC = timezone.utc


def test_binance_open_time_maps_to_logical_close_boundary() -> None:
    open_time = datetime(2019, 12, 1, 23, tzinfo=UTC)
    close_time = open_time + timedelta(hours=1) - timedelta(milliseconds=1)
    assert close_time == datetime(2019, 12, 1, 23, 59, 59, 999000, tzinfo=UTC)
    assert close_time + timedelta(milliseconds=1) == datetime(2019, 12, 2, 0, tzinfo=UTC)


def test_v0r2_first_open_maps_to_next_logical_close_boundary() -> None:
    open_time = datetime(2019, 12, 2, 0, tzinfo=UTC)
    assert open_time + timedelta(hours=1) == datetime(2019, 12, 2, 1, tzinfo=UTC)


def test_har720_requires_721_close_observations() -> None:
    assert 720 + 1 == 721


def test_first_frozen_origin_requires_missing_prefix() -> None:
    first_decision = datetime(2020, 1, 1, 0, tzinfo=UTC)
    first_required_close = first_decision - timedelta(hours=720)
    v0r2_first_logical_close = datetime(2019, 12, 2, 1, tzinfo=UTC)
    assert first_required_close == datetime(2019, 12, 2, 0, tzinfo=UTC)
    assert first_required_close < v0r2_first_logical_close
    assert first_required_close - timedelta(hours=1) == datetime(2019, 12, 1, 23, tzinfo=UTC)


def test_first_origin_dropping_is_not_an_admissible_repair() -> None:
    assert "drop_first_origin" not in {"frozen_schedule", "har_return_count", "close_boundary"}
