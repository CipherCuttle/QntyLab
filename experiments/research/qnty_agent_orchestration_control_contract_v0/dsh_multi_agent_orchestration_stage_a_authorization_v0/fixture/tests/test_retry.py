"""Acceptance tests for the Stage-A bounded-retry fixture.

Do not modify this file as part of the fixture task.
"""

import pytest

from retry import retry_with_backoff


def test_succeeds_on_first_try_without_sleeping():
    calls = []

    def sleep(delay):
        calls.append(delay)

    result = retry_with_backoff(lambda: 42, max_attempts=3, base_delay=0.01, sleep=sleep)
    assert result == 42
    assert calls == []


def test_retries_then_succeeds_and_sleeps_between_attempts_only():
    attempts = {"n": 0}
    sleeps = []

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ValueError(f"fail {attempts['n']}")
        return "ok"

    result = retry_with_backoff(flaky, max_attempts=5, base_delay=0.01, sleep=sleeps.append)
    assert result == "ok"
    assert attempts["n"] == 3
    assert sleeps == [0.01, 0.02]


def test_exhausts_attempts_reraises_last_exception_and_does_not_sleep_after_final_attempt():
    attempts = {"n": 0}
    sleeps = []

    def always_fails():
        attempts["n"] += 1
        raise ValueError(f"failure {attempts['n']}")

    with pytest.raises(ValueError, match="failure 3"):
        retry_with_backoff(always_fails, max_attempts=3, base_delay=0.01, sleep=sleeps.append)

    assert attempts["n"] == 3
    assert sleeps == [0.01, 0.02]
