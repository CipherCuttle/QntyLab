from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from qntylab.breadth_v2_sealed import SEALED_T0
from qntylab.breadth_v2_sealed_observation_sync import (
    RUN_LOG_DIR,
    SEALED_OBSERVATION_UNIVERSE,
    _resume_start,
    safe_catch_up_end,
    sync_sealed_observation,
)


def _dt(*args, **kwargs) -> datetime:
    return datetime(*args, tzinfo=UTC, **kwargs)


# ---------------------------------------------------------------------------
# Pure boundary functions
# ---------------------------------------------------------------------------


def test_safe_catch_up_end_is_last_hour_of_previous_month():
    assert safe_catch_up_end(_dt(2026, 9, 3, 12)) == _dt(2026, 8, 31, 23)
    assert safe_catch_up_end(_dt(2026, 1, 1, 0)) == _dt(2025, 12, 31, 23)


def test_safe_catch_up_end_is_deterministic():
    as_of = _dt(2026, 11, 8, 19)
    assert safe_catch_up_end(as_of) == safe_catch_up_end(as_of)


def test_safe_catch_up_end_rejects_naive_datetime():
    with pytest.raises(ValueError):
        safe_catch_up_end(datetime(2026, 9, 1))


def test_universe_is_23_symbols_no_duplicates():
    assert len(SEALED_OBSERVATION_UNIVERSE) == 23
    assert len(set(SEALED_OBSERVATION_UNIVERSE)) == 23
    assert {"BTCUSDT", "ETHUSDT", "SOLUSDT"} <= set(SEALED_OBSERVATION_UNIVERSE)


def test_resume_start_defaults_to_sealed_t0_with_no_manifest(tmp_path):
    assert _resume_start(tmp_path / "missing.json", "normalized_last_timestamp") == SEALED_T0


def test_resume_start_never_precedes_sealed_t0_even_if_manifest_predates_it(tmp_path):
    # Nothing before SEALED_T0 may ever be treated as sealed-forward coverage,
    # even if some other (pre-existing, out-of-scope) manifest claims earlier data.
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({"normalized_last_timestamp": "2020-01-01T00:00:00Z"}))
    assert _resume_start(manifest, "normalized_last_timestamp") == SEALED_T0


def test_resume_start_falls_back_to_sealed_t0_on_corrupt_manifest_without_raising(tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_text("{not valid json")
    assert _resume_start(manifest, "normalized_last_timestamp") == SEALED_T0


def test_resume_start_continues_one_hour_after_last_materialized_timestamp(tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({"normalized_last_timestamp": "2026-08-31T23:00:00Z"}))
    assert _resume_start(manifest, "normalized_last_timestamp") == _dt(2026, 9, 1, 0)


# ---------------------------------------------------------------------------
# sync_sealed_observation, with fixture materializers standing in for the
# already-independently-tested real ones (same call signature/return shape).
# ---------------------------------------------------------------------------


class _RecordingMaterializer:
    """Fixture materializer that writes a manifest exactly like the real ones
    do, and records every call it received (for asserting determinism /
    idempotency / no-pre-T0 materialization)."""

    def __init__(self, *, manifest_suffix: str, last_key: str, available_through: datetime):
        self.manifest_suffix = manifest_suffix
        self.last_key = last_key
        self.available_through = available_through
        self.calls: list[tuple[str, datetime, datetime]] = []

    def __call__(self, symbol, start, end, root, session=None):
        self.calls.append((symbol, start, end))
        if self.available_through < start:
            return {"status": "SOURCE_OBJECT_ABSENT", "manifest": None}
        clipped_end = min(end, self.available_through)
        manifest = {
            "symbol": symbol,
            "requested_start": start.isoformat().replace("+00:00", "Z"),
            "requested_end": clipped_end.isoformat().replace("+00:00", "Z"),
            self.last_key: clipped_end.isoformat().replace("+00:00", "Z"),
            "materializer_contract_version": "FIXTURE_V0",
        }
        path = Path(root) / "data" / "manifests" / f"{symbol}{self.manifest_suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        return {"status": "MATERIALIZED_VERIFIED", "manifest": manifest}


def _fixtures(tmp_path, available_through=_dt(2026, 8, 31, 23)):
    price = _RecordingMaterializer(
        manifest_suffix="-perp-1h-hourly-input-v0.json",
        last_key="normalized_last_timestamp",
        available_through=available_through,
    )
    funding = _RecordingMaterializer(
        manifest_suffix="-perp-funding-events-v0.json",
        last_key="normalized_last_funding_time",
        available_through=available_through,
    )
    return price, funding


def test_first_run_starts_every_symbol_at_sealed_t0(tmp_path):
    price, funding = _fixtures(tmp_path)
    run = sync_sealed_observation(
        tmp_path,
        as_of=_dt(2026, 9, 3),
        symbols=("BTCUSDT",),
        materialize_price=price,
        materialize_funding=funding,
    )
    assert price.calls == [("BTCUSDT", SEALED_T0, _dt(2026, 8, 31, 23))]
    assert funding.calls == [("BTCUSDT", SEALED_T0, _dt(2026, 8, 31, 23))]
    assert run["symbols"][0]["price"]["status"] == "MATERIALIZED_VERIFIED"
    assert run["all_succeeded"] is True


def test_rerun_with_no_new_complete_month_is_idempotent_and_a_noop(tmp_path):
    price, funding = _fixtures(tmp_path)
    sync_sealed_observation(
        tmp_path, as_of=_dt(2026, 9, 3), symbols=("BTCUSDT",),
        materialize_price=price, materialize_funding=funding,
    )
    calls_after_first_run = len(price.calls)
    second = sync_sealed_observation(
        tmp_path, as_of=_dt(2026, 9, 5), symbols=("BTCUSDT",),
        materialize_price=price, materialize_funding=funding,
    )
    assert len(price.calls) == calls_after_first_run  # no new materializer call made
    assert second["symbols"][0]["price"]["status"] == "NOT_YET_DUE"
    assert second["all_succeeded"] is True


def test_downtime_is_caught_up_from_exact_last_materialized_hour(tmp_path):
    price, funding = _fixtures(tmp_path, available_through=_dt(2026, 8, 31, 23))
    sync_sealed_observation(
        tmp_path, as_of=_dt(2026, 9, 3), symbols=("BTCUSDT",),
        materialize_price=price, materialize_funding=funding,
    )
    # Two more months become available; the next run (simulating a long gap in
    # invocation) must resume exactly where the last run left off, not from
    # SEALED_T0 again and not from "now".
    price.available_through = funding.available_through = _dt(2026, 10, 31, 23)
    sync_sealed_observation(
        tmp_path, as_of=_dt(2026, 11, 5), symbols=("BTCUSDT",),
        materialize_price=price, materialize_funding=funding,
    )
    # The catch-up run must reach exactly the new safe boundary. It requests
    # from SEALED_T0 (not from where it left off) because the underlying
    # materializer overwrites, rather than appends, its on-disk artifact --
    # see `_invoke`'s docstring.
    assert price.calls[-1] == ("BTCUSDT", SEALED_T0, _dt(2026, 10, 31, 23))


def test_failed_acquisition_is_reported_blocked_not_silently_dropped(tmp_path):
    price, funding = _fixtures(tmp_path, available_through=SEALED_T0)  # nothing usable yet

    def always_blocked(symbol, start, end, root, session=None):
        return {"status": "BLOCKED", "manifest": None}

    run = sync_sealed_observation(
        tmp_path, as_of=_dt(2026, 9, 3), symbols=("BTCUSDT",),
        materialize_price=always_blocked, materialize_funding=funding,
    )
    assert run["symbols"][0]["price"]["status"] == "BLOCKED"
    assert run["all_succeeded"] is False


def test_transport_exception_is_reported_not_raised_and_does_not_abort_batch(tmp_path):
    # The real materializers do not catch requests.HTTPError/ConnectionError/
    # Timeout raised from their own network calls; the sync seam is the
    # fail-closed backstop that must catch those instead of letting one
    # symbol's transient failure crash the whole run.
    calls = []

    def raises_for_btc(symbol, start, end, root, session=None):
        calls.append(symbol)
        if symbol == "BTCUSDT":
            raise ConnectionError("simulated network failure")
        return {"status": "MATERIALIZED_VERIFIED", "manifest": {"normalized_last_timestamp": end.isoformat().replace("+00:00", "Z")}}

    run = sync_sealed_observation(
        tmp_path, as_of=_dt(2026, 9, 3), symbols=("BTCUSDT", "ETHUSDT"),
        materialize_price=raises_for_btc, materialize_funding=raises_for_btc,
    )
    assert calls == ["BTCUSDT", "BTCUSDT", "ETHUSDT", "ETHUSDT"]  # ETHUSDT still ran
    statuses = {row["symbol"]: row["price"]["status"] for row in run["symbols"]}
    assert statuses == {"BTCUSDT": "ACQUISITION_FAILED", "ETHUSDT": "MATERIALIZED_VERIFIED"}
    assert "simulated network failure" in run["symbols"][0]["price"]["error"]
    assert run["all_succeeded"] is False


def test_second_run_requests_full_cumulative_range_not_only_the_new_slice(tmp_path):
    # Both real materializers overwrite (not append) their on-disk raw/
    # manifest file on every call, so requesting only the incremental slice
    # on a catch-up run would make that run's file replace, not extend, the
    # previous run's -- silently losing earlier months from disk.
    price, funding = _fixtures(tmp_path, available_through=_dt(2026, 8, 31, 23))
    sync_sealed_observation(
        tmp_path, as_of=_dt(2026, 9, 3), symbols=("BTCUSDT",),
        materialize_price=price, materialize_funding=funding,
    )
    price.available_through = funding.available_through = _dt(2026, 9, 30, 23)
    sync_sealed_observation(
        tmp_path, as_of=_dt(2026, 10, 3), symbols=("BTCUSDT",),
        materialize_price=price, materialize_funding=funding,
    )
    assert all(call[1] == SEALED_T0 for call in price.calls)


def test_other_symbols_still_sync_when_one_symbol_is_blocked(tmp_path):
    calls = []

    def flaky(symbol, start, end, root, session=None):
        calls.append(symbol)
        if symbol == "ETHUSDT":
            return {"status": "SOURCE_AUTHENTICATION_UNAVAILABLE", "manifest": None}
        return {"status": "MATERIALIZED_VERIFIED", "manifest": {"normalized_last_timestamp": end.isoformat().replace("+00:00", "Z")}}

    run = sync_sealed_observation(
        tmp_path, as_of=_dt(2026, 9, 3), symbols=("BTCUSDT", "ETHUSDT"),
        materialize_price=flaky, materialize_funding=flaky,
    )
    assert calls.count("BTCUSDT") == 2  # price + funding both attempted
    assert calls.count("ETHUSDT") == 2
    statuses = {row["symbol"]: row["price"]["status"] for row in run["symbols"]}
    assert statuses == {"BTCUSDT": "MATERIALIZED_VERIFIED", "ETHUSDT": "SOURCE_AUTHENTICATION_UNAVAILABLE"}


def test_run_is_deterministic_given_same_inputs(tmp_path):
    price_a, funding_a = _fixtures(tmp_path / "a")
    (tmp_path / "a").mkdir()
    run_a = sync_sealed_observation(
        tmp_path / "a", as_of=_dt(2026, 9, 3), symbols=("BTCUSDT",),
        materialize_price=price_a, materialize_funding=funding_a,
    )
    price_b, funding_b = _fixtures(tmp_path / "b")
    (tmp_path / "b").mkdir()
    run_b = sync_sealed_observation(
        tmp_path / "b", as_of=_dt(2026, 9, 3), symbols=("BTCUSDT",),
        materialize_price=price_b, materialize_funding=funding_b,
    )
    identity_keys = {"sealed_t0", "as_of", "safe_catch_up_end", "symbols", "all_succeeded"}
    assert {k: run_a[k] for k in identity_keys} == {k: run_b[k] for k in identity_keys}


def test_run_writes_health_check_log(tmp_path):
    price, funding = _fixtures(tmp_path)
    sync_sealed_observation(
        tmp_path, as_of=_dt(2026, 9, 3), symbols=("BTCUSDT",),
        materialize_price=price, materialize_funding=funding,
    )
    logs = list((tmp_path / RUN_LOG_DIR).glob("*.json"))
    assert len(logs) == 1
    logged = json.loads(logs[0].read_text())
    assert logged["all_succeeded"] is True
    assert "return" not in json.dumps(logged).lower()
    assert "pnl" not in json.dumps(logged).lower()


def test_module_calls_no_strategy_or_ledger_economic_path():
    import qntylab.breadth_v2_sealed_observation_sync as mod

    source = Path(mod.__file__).read_text()
    for forbidden in ("record_breadth_v2_evaluation", "breadth_v2_strategies", "breadth_v2_runner", "prepare_breadth_v2_evaluation"):
        assert forbidden not in source
