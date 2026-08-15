from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from qntylab.jfp_v3_shadow import (
    ActivationManager,
    BinanceUmTransport,
    Collector,
    ContractError,
    ReceiptLedger,
    bind_pr_a,
    collect_due,
    digest,
    activate_shadow,
    due_origin_ids,
    future_value,
    implementation_identity,
    resolve_universe,
    resolve_runtime_canonical_state,
    schedule,
    stamp,
    status,
    validate_activation,
)


ORIGIN = datetime(2026, 1, 1, tzinfo=UTC)
SYMBOLS = tuple(f"S{index:02d}USDT" for index in range(15))


def metadata(statuses: dict[str, str] | None = None, onboard: int | None = None) -> dict:
    statuses = statuses or {}
    onboard = onboard if onboard is not None else int((ORIGIN - timedelta(days=31)).timestamp() * 1000)
    return {"symbols": [{"symbol": symbol, "status": statuses.get(symbol, "TRADING"), "contractType": "PERPETUAL", "quoteAsset": "USDT", "onboardDate": onboard, "venue": "Binance", "market_type": "USD-M perpetual"} for symbol in SYMBOLS]}


def bars(symbols=SYMBOLS, start=ORIGIN - timedelta(hours=24), count=25, *, future=False):
    result = []
    for symbol_index, symbol in enumerate(symbols):
        previous = 100.0 + symbol_index
        for index in range(count):
            when = start + timedelta(hours=index)
            close = previous + (1.0 if (index + symbol_index) % 2 else -0.5)
            if future and index == 0:
                close = previous
            result.append({"symbol": symbol, "close_time": when.isoformat().replace("+00:00", "Z"), "close": str(close), "interval": "1h", "source_id": "fixture-binance", "raw_digest": digest([symbol, when.isoformat(), close])})
            previous = close
    return result


def one_origin_collector(tmp_path):
    ledger = ReceiptLedger(tmp_path / "events.jsonl")
    record = {
        "activation_master_sha": "f" * 40,
        "collector_implementation_sha": "a" * 64,
        "preregistration_digest": "b" * 64,
        "universe_contract_digest": "c" * 64,
        "source_contract_digest": "d" * 64,
        "scientific_contract_digest": "e" * 64,
        "schedule_contract_digest": "f" * 64,
        "activation_timestamp": (ORIGIN - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "shadow_run_id": "run-fixture",
    }
    activate_shadow(ledger, record, schedule(ORIGIN - timedelta(days=1)))
    return Collector(ledger), ledger


def test_pr_a_binding_uses_manifest_and_canonical_commit():
    state = resolve_runtime_canonical_state(refresh=False)
    binding = bind_pr_a(current_sha=state["head_sha"])
    assert binding["generation_id"] == "JFPV3_01"
    assert binding["artifact_digests"]["source_contract.json"]


def test_pr_a_binding_rejects_wrong_commit():
    with pytest.raises(ContractError):
        bind_pr_a(current_sha="f" * 40)


def test_universe_is_structural_deterministic_and_pit_safe():
    result = resolve_universe(metadata(), origin=ORIGIN, observed_at=ORIGIN - timedelta(minutes=1), source_id="fixture", transport_id="exchangeInfo-v0")
    assert result["ordered_U_t"] == list(SYMBOLS)
    assert result["N_t"] == 15
    assert result["universe_digest"] == digest(list(SYMBOLS))
    with pytest.raises(ContractError, match="PIT_VIOLATION"):
        resolve_universe(metadata(), origin=ORIGIN, observed_at=ORIGIN + timedelta(seconds=1), source_id="fixture", transport_id="exchangeInfo-v0")


def test_universe_excludes_status_and_young_listing():
    statuses = {SYMBOLS[0]: "SETTLING"}
    result = resolve_universe(metadata(statuses, onboard=int((ORIGIN - timedelta(days=29)).timestamp() * 1000)), origin=ORIGIN, observed_at=ORIGIN, source_id="fixture", transport_id="exchangeInfo-v0")
    assert result["N_t"] == 0
    assert {row["reason"] for row in result["excluded_symbol_records"]} == {"LISTING_AGE_BELOW_30_DAYS", "STATUS_NOT_TRADING"}


def test_schedule_is_exact_and_activation_offset_is_not_early():
    origins = schedule(datetime(2026, 2, 3, 12, tzinfo=UTC))
    assert len(origins) == 365
    assert origins[0] == datetime(2026, 2, 5, tzinfo=UTC)
    assert all(current - prior == timedelta(days=1) for prior, current in zip(origins, origins[1:]))


def test_schedule_rejects_noncanonical_count():
    with pytest.raises(ContractError): schedule(ORIGIN, 364)


def test_activation_guard_rejects_noncanonical_or_duplicate_shape():
    runtime_head = "f" * 40
    record = {"activation_master_sha": runtime_head, "collector_implementation_sha": "a" * 64, "preregistration_digest": "b" * 64, "universe_contract_digest": "c" * 64, "source_contract_digest": "d" * 64, "scientific_contract_digest": "e" * 64, "schedule_contract_digest": "f" * 64, "activation_timestamp": "2026-01-01T00:00:00Z", "shadow_run_id": "run-1"}
    validate_activation(record, current_sha=runtime_head, origin_master_sha=runtime_head, lineage={"all": True})
    with pytest.raises(ContractError): validate_activation(record, current_sha=runtime_head, origin_master_sha=runtime_head, dirty=True)
    with pytest.raises(ContractError, match="implementation"):
        validate_activation(record, current_sha=runtime_head, origin_master_sha=runtime_head, expected_implementation_sha="0" * 64)


def test_runtime_canonicality_survives_a_future_merge_sha():
    future_merge = "1" * 40
    record = {"activation_master_sha": future_merge, "collector_implementation_sha": "a" * 64, "preregistration_digest": "b" * 64, "universe_contract_digest": "c" * 64, "source_contract_digest": "d" * 64, "scientific_contract_digest": "e" * 64, "schedule_contract_digest": "f" * 64, "activation_timestamp": "2026-01-01T00:00:00Z", "shadow_run_id": "run-future"}
    validate_activation(record, current_sha=future_merge, origin_master_sha=future_merge, lineage={"pr_a": True, "pr_a_merge": True, "v0_closure": True, "v0_merge": True}, expected_implementation_sha="a" * 64)


def test_repaired_implementation_manifest_binds_exact_content():
    identity = implementation_identity()
    assert len(identity["implementation_digest"]) == 64
    assert identity["candidate_commit_sha"]


@pytest.mark.parametrize("case", [
    {"current_sha": "a" * 40, "origin_master_sha": "b" * 40},
    {"current_sha": "a" * 40, "origin_master_sha": "a" * 40, "dirty": True},
    {"current_sha": "a" * 40, "origin_master_sha": "a" * 40, "lineage": {"missing_anchor": False}},
])
def test_runtime_canonicality_negative_cases(case):
    sha = case["current_sha"]
    record = {"activation_master_sha": sha, "collector_implementation_sha": "a" * 64, "preregistration_digest": "b" * 64, "universe_contract_digest": "c" * 64, "source_contract_digest": "d" * 64, "scientific_contract_digest": "e" * 64, "schedule_contract_digest": "f" * 64, "activation_timestamp": "2026-01-01T00:00:00Z", "shadow_run_id": "run-negative"}
    with pytest.raises(ContractError): validate_activation(record, **case)


def test_transport_is_fixture_injectable_and_does_not_need_network():
    calls = []
    raw = json_bytes = b'{"symbols": []}'

    def requester(method, endpoint, params):
        calls.append((method, endpoint, params))
        return raw

    transport = BinanceUmTransport(requester)
    metadata_raw, source_id, transport_id = transport.metadata()
    assert metadata_raw == raw and source_id.startswith("binance-") and transport_id == "binance-rest-v0"
    assert calls[0][1].endswith("/exchangeInfo")


def test_collector_seals_same_universe_and_matures_synthetic_outcome(tmp_path):
    c, ledger = one_origin_collector(tmp_path)
    c.seal_metadata("origin-000", ORIGIN, metadata(), raw_metadata=b"fixture-metadata", observed_at=ORIGIN, source_id="fixture", transport_id="exchangeInfo-v0")
    prior = bars()
    c.seal_feature_inputs("origin-000", prior, source_capability_id="fixture-bars-v0", source_id="fixture", acquired_at=ORIGIN)
    sealed = c.seal_feature("origin-000", prior)
    assert sealed["payload"]["N_t"] == 15
    future = bars(start=ORIGIN, count=25, future=True)
    result = c.mature_outcome("origin-000", future, source_capability_id="fixture-bars-v0", source_id="fixture")
    assert result["event_type"] == "ORIGIN_ELIGIBLE"
    assert result["payload"]["universe_digest"] == sealed["payload"]["universe_digest"]
    assert status(ledger)["scientific_statistics"] == "NOT_EXPOSED"


def test_n_minimum_blocks_without_deleting_scheduled_origin(tmp_path):
    c, ledger = one_origin_collector(tmp_path)
    small = {"symbols": metadata()["symbols"][:14]}
    blocked = c.seal_metadata("origin-000", ORIGIN, small, raw_metadata=b"small", observed_at=ORIGIN, source_id="fixture", transport_id="exchangeInfo-v0")
    assert blocked["payload"]["block_reason"] == "UNIVERSE_TOO_SMALL"
    assert status(ledger)["scheduled_count"] == 365
    assert status(ledger)["blocked_count"] == 1


def test_missing_outcome_member_blocks_without_shrink(tmp_path):
    c, _ledger = one_origin_collector(tmp_path)
    c.seal_metadata("origin-000", ORIGIN, metadata(), raw_metadata=b"fixture", observed_at=ORIGIN, source_id="fixture", transport_id="exchangeInfo-v0")
    prior = bars(); c.seal_feature_inputs("origin-000", prior, source_capability_id="fixture", source_id="fixture", acquired_at=ORIGIN); c.seal_feature("origin-000", prior)
    incomplete = bars(start=ORIGIN, count=25, future=True)
    incomplete = [bar for bar in incomplete if bar["symbol"] != SYMBOLS[0] or bar["close_time"] == ORIGIN.strftime("%Y-%m-%dT%H:%M:%SZ")]
    blocked = c.mature_outcome("origin-000", incomplete, source_capability_id="fixture", source_id="fixture")
    assert blocked["event_type"] == "ORIGIN_BLOCKED"
    assert blocked["payload"]["block_reason"] == "OUTCOME_WINDOW_INCOMPLETE"


def test_receipt_chain_is_append_only_idempotent_and_detects_mutation(tmp_path):
    path = tmp_path / "events.jsonl"; ledger = ReceiptLedger(path)
    event = ledger.append("one", "ORIGIN_SCHEDULED", {"origin_id": "x"})
    assert ledger.append("one", "ORIGIN_SCHEDULED", {"origin_id": "x"}) == event
    assert ledger.verify()["integrity"] == "PASS"
    path.write_text(path.read_text().replace('"origin_id":"x"', '"origin_id":"y"'), encoding="utf-8")
    with pytest.raises(ContractError, match="mutation|chain"):
        ledger.verify()


def test_future_value_requires_sealed_universe_size_and_no_unknown_stats():
    with pytest.raises(ContractError, match="PIT_VIOLATION"):
        future_value([], SYMBOLS, ORIGIN, 14)
    assert not any(name in dir(Collector) for name in ("evaluate", "regress", "pvalue", "partial_r2"))


def test_status_does_not_expose_inference_fields(tmp_path):
    _c, ledger = one_origin_collector(tmp_path)
    payload = status(ledger)
    forbidden = {"beta", "p_value", "pvalue", "partial_r2", "z", "support", "performance"}
    assert forbidden.isdisjoint(payload)


def activation_record(run_id="run-test", activation_timestamp=None):
    return {
        "activation_master_sha": "f" * 40,
        "collector_implementation_sha": "a" * 64,
        "preregistration_digest": "b" * 64,
        "universe_contract_digest": "c" * 64,
        "source_contract_digest": "d" * 64,
        "scientific_contract_digest": "e" * 64,
        "schedule_contract_digest": "f" * 64,
        "activation_timestamp": (activation_timestamp or ORIGIN - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "shadow_run_id": run_id,
    }


def test_activation_status_lifecycle_and_partial_recovery(tmp_path):
    ledger = ReceiptLedger(tmp_path / "events.jsonl")
    assert status(ledger)["activation_state"] == "ARMED_BUT_INACTIVE"
    manager = ActivationManager(ledger)
    origins = schedule(ORIGIN - timedelta(days=1))
    manager.prepare(activation_record("run-crash"), origins)
    manager.persist_schedule(limit=147)
    assert status(ledger)["activation_state"] == "ACTIVATION_INCOMPLETE"
    manager.commit()
    assert status(ledger)["activation_state"] == "ACTIVATED_READY_FOR_FIRST_ORIGIN"
    assert status(ledger)["scheduled_count"] == 365
    assert status(ledger)["activation_count"] == 1


def test_activation_replay_conflict_and_second_activation_fail_closed(tmp_path):
    ledger = ReceiptLedger(tmp_path / "events.jsonl")
    manager = ActivationManager(ledger)
    origins = schedule(ORIGIN - timedelta(days=1))
    first = activation_record("run-one")
    manager.prepare(first, origins)
    with pytest.raises(ContractError, match="conflicting activation"):
        manager.prepare(activation_record("run-two"), origins)
    manager.commit()
    assert manager.commit()["event_type"] == "SHADOW_ACTIVATED"
    with pytest.raises(ContractError, match="conflicting activation"):
        manager.prepare(activation_record("run-two"), origins)


def test_activation_and_schedule_mutation_are_detected(tmp_path):
    path = tmp_path / "events.jsonl"
    ledger = ReceiptLedger(path)
    manager = ActivationManager(ledger)
    manager.prepare(activation_record(), schedule(ORIGIN - timedelta(days=1)))
    manager.persist_schedule(limit=1)
    original = path.read_text()
    path.write_text(original.replace('"shadow_run_id":"run-test"', '"shadow_run_id":"tampered"', 1))
    with pytest.raises(ContractError, match="mutation|chain"):
        manager.summary()


def test_orphan_schedule_and_collection_before_activation_are_rejected(tmp_path):
    ledger = ReceiptLedger(tmp_path / "events.jsonl")
    ledger.append("orphan", "ORIGIN_SCHEDULED", {"origin_id": "origin-000", "origin_index": 0, "origin_timestamp": stamp(ORIGIN), "shadow_run_id": "foreign", "activation_record_digest": "a" * 64, "schedule_digest": "b" * 64})
    with pytest.raises(ContractError, match="orphan"):
        status(ledger)
    with pytest.raises(ContractError, match="orphan|activation"):
        Collector(ledger).seal_metadata("origin-000", ORIGIN, metadata(), raw_metadata=b"x", observed_at=ORIGIN, source_id="fixture", transport_id="fixture")


def test_temporal_gates_reject_early_feature_and_outcome(tmp_path):
    collector, _ledger = one_origin_collector(tmp_path)
    with pytest.raises(ContractError, match="not due"):
        collector.seal_metadata("origin-000", ORIGIN, metadata(), raw_metadata=b"x", observed_at=ORIGIN, source_id="fixture", transport_id="fixture", now=ORIGIN - timedelta(seconds=1))
    collector.seal_metadata("origin-000", ORIGIN, metadata(), raw_metadata=b"x", observed_at=ORIGIN, source_id="fixture", transport_id="fixture", now=ORIGIN)
    prior = bars()
    collector.seal_feature_inputs("origin-000", prior, source_capability_id="fixture", source_id="fixture", acquired_at=ORIGIN, now=ORIGIN)
    collector.seal_feature("origin-000", prior, now=ORIGIN)
    with pytest.raises(ContractError, match="not mature"):
        collector.mature_outcome("origin-000", bars(start=ORIGIN, count=25, future=True), source_capability_id="fixture", source_id="fixture", now=ORIGIN + timedelta(hours=23, minutes=59))


def test_wrong_run_and_wrong_schedule_are_rejected(tmp_path):
    collector, ledger = one_origin_collector(tmp_path)
    committed = ActivationManager(ledger).summary()["committed"]
    foreign = dict(next(event["payload"] for event in ledger._events("ORIGIN_SCHEDULED") if event["payload"]["origin_id"] == "origin-000"), shadow_run_id="foreign")
    ledger.append("foreign-origin", "ORIGIN_SCHEDULED", foreign)
    with pytest.raises(ContractError, match="schedule|activation|mutation"):
        collector.seal_metadata("origin-000", ORIGIN, metadata(), raw_metadata=b"x", observed_at=ORIGIN, source_id="fixture", transport_id="fixture")
    assert committed["schedule_digest"]


class FixtureTransport:
    def metadata(self):
        return json.dumps(metadata(), sort_keys=True).encode(), "fixture-binance", "fixture-transport"

    def bars(self, symbol, start, end):
        return b"fixture-bars", "fixture-binance", bars((symbol,), start=start, count=25, future=start >= ORIGIN)


def test_due_runner_uses_only_mock_source_and_is_idempotent(tmp_path):
    collector, ledger = one_origin_collector(tmp_path)
    completed = collect_due(collector, FixtureTransport(), now=ORIGIN)
    assert completed == ["origin-000"]
    assert status(ledger)["feature_sealed_count"] == 1
    assert collect_due(collector, FixtureTransport(), now=ORIGIN) == []
