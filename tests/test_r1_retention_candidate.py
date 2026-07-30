from hashlib import sha256
import json
from pathlib import Path

import pytest

from qntylab.r1_input_bom import canonical_bytes, canonical_hash
from qntylab.r1_retention_candidate import (ANOMALY_DUPLICATE_CONFLICTING, ANOMALY_DUPLICATE_UNEXPECTED,
                                             ANOMALY_FUTURE_CUTOFF, ANOMALY_REDUNDANT_FIELD_MISMATCH,
                                             ANOMALY_SCHEMA_MISMATCH, ANOMALY_TIMESTAMP_CONTAINMENT,
                                             BASE_SCHEMA, RAW_DELETED_AFTER_VERIFIED_DERIVATION,
                                             RAW_QUARANTINED_ANOMALY, RAW_RETAINED, RAW_UNAVAILABLE_SOURCE_ABSENT,
                                             REHYDRATION_REPRODUCIBLE, DERIVATION_AUDITABLE,
                                             PRESERVATION_REPRODUCIBLE,
                                             assert_uniform_parser_version, audit_reservoir_dimension_key,
                                             build_receipt, daily_primitive, raw_deletion_permitted,
                                             record_rehydration_attempt, reproducibility_claim_level,
                                             retention_state, select_audit_reservoir, write_candidate)

CUTOFF = "2026-06-30T23:59:59Z"


def row(ts, side="Buy", size="1.0", price="10.0", tickdir="PlusTick", trdid="a" * 32,
        home=None, foreign=None, gross=None):
    size_f, price_f = float(size), float(price)
    home = home if home is not None else str(size_f)
    foreign = foreign if foreign is not None else str(size_f * price_f)
    gross = gross if gross is not None else str(size_f * price_f * 1e8)
    return {"timestamp": str(ts), "symbol": "MONUSDT", "side": side, "size": size, "price": price,
            "tickDirection": tickdir, "trdMatchID": trdid, "grossValue": gross,
            "homeNotional": home, "foreignNotional": foreign}


# --- pilot reproduction / input-order invariance / UTC boundary ----------

def test_pilot_reproduction_is_deterministic_and_order_invariant():
    rows = [row("1751328000.5", price="11", trdid="b" * 32), row("1751328000.1", price="10", trdid="a" * 32)]
    forward, anomalies_f = daily_primitive(stream_id="s", utc_date="2025-07-01", header=BASE_SCHEMA,
                                            rows=rows, historical_cutoff_utc=CUTOFF)
    reversed_, anomalies_r = daily_primitive(stream_id="s", utc_date="2025-07-01", header=BASE_SCHEMA,
                                              rows=list(reversed(rows)), historical_cutoff_utc=CUTOFF)
    assert forward == reversed_
    assert anomalies_f == anomalies_r == []
    assert forward["open"] == 10.0 and forward["close"] == 11.0


def test_utc_day_boundary_23_59_59_and_00_00_00_are_assigned_to_correct_day():
    late = row("1751414399.999", price="9")   # 2025-07-01T23:59:59.999Z
    early = row("1751414400.0", price="12")   # 2025-07-02T00:00:00Z
    day1, anomalies1 = daily_primitive(stream_id="s", utc_date="2025-07-01", header=BASE_SCHEMA,
                                        rows=[late, early], historical_cutoff_utc=CUTOFF)
    assert day1["trade_count"] == 1 and day1["close"] == 9.0
    assert ANOMALY_TIMESTAMP_CONTAINMENT in anomalies1
    day2, anomalies2 = daily_primitive(stream_id="s", utc_date="2025-07-02", header=BASE_SCHEMA,
                                        rows=[late, early], historical_cutoff_utc=CUTOFF)
    assert day2["trade_count"] == 1 and day2["close"] == 12.0
    assert ANOMALY_TIMESTAMP_CONTAINMENT in anomalies2


def test_future_cutoff_rejection():
    beyond = row("1751500000.0")  # after 2026-06-30T23:59:59Z cutoff
    primitive, anomalies = daily_primitive(stream_id="s", utc_date="2025-07-01", header=BASE_SCHEMA,
                                            rows=[beyond], historical_cutoff_utc="2025-07-01T23:59:59Z")
    assert primitive["trade_count"] == 0
    assert ANOMALY_FUTURE_CUTOFF in anomalies


def test_identical_timestamps_break_ties_by_trade_id_deterministically():
    r1 = row("1751328000.0", price="5", trdid="a" * 32)
    r2 = row("1751328000.0", price="7", trdid="b" * 32)
    primitive, _ = daily_primitive(stream_id="s", utc_date="2025-07-01", header=BASE_SCHEMA,
                                    rows=[r2, r1], historical_cutoff_utc=CUTOFF)
    assert primitive["open"] == 5.0 and primitive["close"] == 7.0


# --- duplicate handling ---------------------------------------------------

def test_duplicate_handling_identical_vs_conflicting():
    original = row("1751328000.0", trdid="c" * 32, price="10")
    exact_dup = row("1751328000.0", trdid="c" * 32, price="10")
    conflicting_dup = row("1751328000.0", trdid="c" * 32, price="99")
    primitive, anomalies = daily_primitive(stream_id="s", utc_date="2025-07-01", header=BASE_SCHEMA,
                                            rows=[original, exact_dup], historical_cutoff_utc=CUTOFF)
    assert primitive["duplicate_count"] == 1 and primitive["trade_count"] == 1
    assert ANOMALY_DUPLICATE_UNEXPECTED in anomalies and ANOMALY_DUPLICATE_CONFLICTING not in anomalies

    _, anomalies2 = daily_primitive(stream_id="s", utc_date="2025-07-01", header=BASE_SCHEMA,
                                     rows=[original, conflicting_dup], historical_cutoff_utc=CUTOFF)
    assert ANOMALY_DUPLICATE_CONFLICTING in anomalies2


# --- schema drift / redundant-field independent validation ---------------

def test_unknown_schema_variant_forces_schema_mismatch_anomaly():
    weird_header = BASE_SCHEMA + ("EXTRA_UNSEEN_COLUMN",)
    _, anomalies = daily_primitive(stream_id="s", utc_date="2025-07-01", header=weird_header,
                                    rows=[row("1751328000.0")], historical_cutoff_utc=CUTOFF)
    assert ANOMALY_SCHEMA_MISMATCH in anomalies


def test_redundant_field_mismatch_is_a_free_independent_validation_signal():
    bad = row("1751328000.0", size="1.0", price="10.0", home="999")  # homeNotional should equal size
    _, anomalies = daily_primitive(stream_id="s", utc_date="2025-07-01", header=BASE_SCHEMA,
                                    rows=[bad], historical_cutoff_utc=CUTOFF)
    assert ANOMALY_REDUNDANT_FIELD_MISMATCH in anomalies


# --- crash consistency ----------------------------------------------------

def test_raw_deletion_not_permitted_before_receipt_written():
    for stage in ("RETRIEVED_UNHASHED", "HASHED", "PARSED", "NORMALIZED_WRITTEN"):
        assert not raw_deletion_permitted(stage)
    for stage in ("RECEIPT_WRITTEN", "RAW_ELIGIBLE_FOR_DELETION", "RAW_DELETED"):
        assert raw_deletion_permitted(stage)


@pytest.mark.parametrize("stage", ["RETRIEVED_UNHASHED", "HASHED", "PARSED", "NORMALIZED_WRITTEN"])
def test_crash_before_receipt_written_keeps_raw_retained_regardless_of_reservoir_or_anomaly(stage):
    state, reason = retention_state(http_or_result_state="SOURCE_PRESENT", anomalies=[],
                                     audit_reservoir_member=False, commit_stage=stage)
    assert state == RAW_RETAINED and "COMMIT_INCOMPLETE" in reason


# --- retention independent of outcomes ------------------------------------

def test_retention_state_accepts_no_outcome_shaped_input():
    import inspect
    params = set(inspect.signature(retention_state).parameters)
    outcome_terms = {"pnl", "sharpe", "ic", "return", "weight", "rank", "factor_value", "outcome"}
    assert not (params & outcome_terms)


def test_ordinary_object_is_deleted_only_after_receipt_committed_no_anomaly_no_reservoir():
    state, reason = retention_state(http_or_result_state="SOURCE_PRESENT", anomalies=[],
                                     audit_reservoir_member=False, commit_stage="RECEIPT_WRITTEN")
    assert state == RAW_DELETED_AFTER_VERIFIED_DERIVATION


def test_anomaly_forces_raw_retention_even_if_committed_and_not_reservoir_member():
    state, reason = retention_state(http_or_result_state="SOURCE_PRESENT", anomalies=[ANOMALY_SCHEMA_MISMATCH],
                                     audit_reservoir_member=False, commit_stage="RAW_ELIGIBLE_FOR_DELETION")
    assert state == RAW_QUARANTINED_ANOMALY


def test_audit_reservoir_member_is_retained_even_without_anomaly():
    state, reason = retention_state(http_or_result_state="SOURCE_PRESENT", anomalies=[],
                                     audit_reservoir_member=True, commit_stage="RECEIPT_WRITTEN")
    assert state == RAW_RETAINED and reason == "PREDECLARED_AUDIT_RESERVOIR_MEMBER"


def test_source_absent_never_had_raw_bytes():
    state, _ = retention_state(http_or_result_state="SOURCE_ABSENT", anomalies=[],
                                audit_reservoir_member=False, commit_stage="RECEIPT_WRITTEN")
    assert state == RAW_UNAVAILABLE_SOURCE_ABSENT


# --- audit reservoir: deterministic, strategy-blind, budget-bounded ------

def _candidates():
    return [
        {"object_key": "a", "stream_id": "s1", "utc_date": "2021-01-01", "byte_size": 200_000, "schema_id": "bybit_trade_v1"},
        {"object_key": "b", "stream_id": "s1", "utc_date": "2021-06-01", "byte_size": 250_000, "schema_id": "bybit_trade_v1"},
        {"object_key": "c", "stream_id": "s2", "utc_date": "2024-01-01", "byte_size": 5_000_000, "schema_id": "bybit_trade_v1"},
        {"object_key": "d", "stream_id": "s2", "utc_date": "2026-06-30", "byte_size": 90_000, "schema_id": "bybit_trade_v1_rpi"},
    ]


def test_audit_reservoir_selection_is_deterministic_regardless_of_input_order():
    forward, total_f = select_audit_reservoir(_candidates(), budget_bytes=10_000_000)
    shuffled, total_s = select_audit_reservoir(list(reversed(_candidates())), budget_bytes=10_000_000)
    assert forward == shuffled and total_f == total_s


def test_audit_reservoir_respects_fixed_byte_budget():
    selected, total = select_audit_reservoir(_candidates(), budget_bytes=100_000)
    assert total <= 100_000
    assert selected  # smallest object still fits


def test_audit_reservoir_dimension_key_has_no_outcome_shaped_fields():
    key = audit_reservoir_dimension_key(stream_id="s1", utc_date="2024-01-01", byte_size=123, schema_id="bybit_trade_v1")
    assert key == ("s1", "2024", "lt_100kb", "bybit_trade_v1")
    import inspect
    params = set(inspect.signature(audit_reservoir_dimension_key).parameters)
    assert not (params & {"pnl", "sharpe", "ic", "return_", "weight", "outcome"})


# --- provenance receipt: raw SHA / parser SHA / normalization SHA bound --

def test_receipt_binds_raw_sha_parser_sha_and_normalization_sha():
    primitive, anomalies = daily_primitive(stream_id="bybit|MONUSDT|LinearPerpetual", utc_date="2025-07-01",
                                            header=BASE_SCHEMA, rows=[row("1751328000.0")],
                                            historical_cutoff_utc=CUTOFF)
    raw_bytes = b"raw-object-bytes"
    receipt = build_receipt(stream_id="bybit|MONUSDT|LinearPerpetual", cache_key="k1",
                             source_url="https://public.bybit.com/trading/MONUSDT/MONUSDT2025-07-01.csv.gz",
                             retrieval_timestamp_utc="2026-07-30T00:00:00Z", http_or_result_state="SOURCE_PRESENT",
                             raw_bytes=raw_bytes, gzip_valid=True, header=BASE_SCHEMA, primitive=primitive,
                             anomalies=anomalies, audit_reservoir_member=False, commit_stage="RECEIPT_WRITTEN")
    assert receipt["sha256"] == sha256(raw_bytes).hexdigest()
    assert receipt["parser_implementation_sha256"] == receipt["normalization_contract_sha256"]
    assert receipt["normalized_primitive_sha256"] == canonical_hash(primitive)
    assert receipt["raw_retention_state"] == RAW_DELETED_AFTER_VERIFIED_DERIVATION


# --- source mutation / rehydration ----------------------------------------

def test_rehydration_sha_match_is_verified_and_does_not_touch_original_sha():
    receipt = {"sha256": "aaaa", "raw_retention_state": RAW_DELETED_AFTER_VERIFIED_DERIVATION, "anomalies": []}
    updated = record_rehydration_attempt(receipt, attempt_timestamp_utc="2026-08-01T00:00:00Z", rehydrated_sha256="aaaa")
    assert updated["sha256"] == "aaaa"
    assert updated["rehydration_attempts"][-1]["state"] == "REHYDRATION_VERIFIED"
    assert updated["raw_retention_state"] == RAW_DELETED_AFTER_VERIFIED_DERIVATION


def test_rehydration_sha_mismatch_is_rejected_and_forces_quarantine_not_overwrite():
    receipt = {"sha256": "aaaa", "raw_retention_state": RAW_DELETED_AFTER_VERIFIED_DERIVATION, "anomalies": []}
    updated = record_rehydration_attempt(receipt, attempt_timestamp_utc="2026-08-01T00:00:00Z", rehydrated_sha256="bbbb")
    assert updated["sha256"] == "aaaa"  # original never overwritten
    assert updated["rehydration_attempts"][-1]["state"] == "SOURCE_MUTATION_DETECTED"
    assert updated["raw_retention_state"] == RAW_QUARANTINED_ANOMALY
    assert "SOURCE_MUTATION" in updated["raw_retention_reason"]


# --- reproducibility claim levels -----------------------------------------

def test_reproducibility_claim_levels_match_retention_state():
    assert reproducibility_claim_level(RAW_RETAINED, currently_rehydratable=True) == PRESERVATION_REPRODUCIBLE
    assert reproducibility_claim_level(RAW_QUARANTINED_ANOMALY, currently_rehydratable=False) == PRESERVATION_REPRODUCIBLE
    assert reproducibility_claim_level(RAW_DELETED_AFTER_VERIFIED_DERIVATION, currently_rehydratable=True) == REHYDRATION_REPRODUCIBLE
    assert reproducibility_claim_level(RAW_DELETED_AFTER_VERIFIED_DERIVATION, currently_rehydratable=False) == DERIVATION_AUDITABLE


# --- no silent mixed parser versions --------------------------------------

def test_mixed_parser_implementation_versions_fail_closed():
    receipts = [{"parser_implementation_sha256": "v1"}, {"parser_implementation_sha256": "v2"}]
    with pytest.raises(ValueError):
        assert_uniform_parser_version(receipts)
    assert_uniform_parser_version([{"parser_implementation_sha256": "v1"}, {"parser_implementation_sha256": "v1"}])


# --- candidate artifact binds itself to this test module ------------------

def test_candidate_is_canonical_and_binds_current_module_and_test_receipts():
    root = Path(__file__).parents[1]
    candidate = write_candidate(root)
    assert candidate["verdict"] == "R1_BOUNDED_EVIDENCE_RETENTION_CANDIDATE_READY_FOR_REVIEW"
    assert candidate["implementation_sha256"] == sha256((root / "qntylab/r1_retention_candidate.py").read_bytes()).hexdigest()
    assert candidate["test_module_sha256"] == sha256(Path(__file__).read_bytes()).hexdigest()
    written_path = root / "experiments/data/r1_bounded_evidence_retention_candidate_v1.json"
    if written_path.exists():
        on_disk = json.loads(written_path.read_bytes())
        assert on_disk["verdict"] == candidate["verdict"]
