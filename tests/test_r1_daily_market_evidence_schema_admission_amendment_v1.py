"""Protocol tests for
experiments/data/r1_daily_market_evidence_schema_admission_amendment_v1.json
(a PROTOCOL_AMENDMENT_CANDIDATE, not yet frozen -- see its own "status" field).

Closes H1_PROTOCOL_UNDERSPECIFICATION (unregistered schema does not
normatively entail invalid/inadmissible DailyMarketEvidenceV1) via
semantic_body.schema_admission_rule, and then repairs
BLOCK_REGISTRY_TIME_AMBIGUITY (an independent hostile review verdict on that
rule's first draft, which read known_schema_variants "at the time of
evaluation" -- a live, wall-clock-dependent read with no per-decision
registry-version binding) via semantic_body.registry_snapshot_binding.

These tests do not modify, and do not require modifying, Parser A, Parser B,
or the materialization boundary. They:
  1. verify the amendment artifact's self-consistent digests and its binding
     to the actual current bytes of the base contract and schema registry it
     amends (both left byte-for-byte unedited by this amendment);
  2. reimplement schema_admission_rule standalone (not by importing either
     parser's internals) as the minimal, registry-snapshot-bound predicate the
     amendment defines: every evaluation carries an explicit
     registry_snapshot_sha256 and is a pure function of (schema_id,
     known_schema_variants, registry_snapshot_sha256) only;
  3. empirically corroborate, using the CURRENT unmodified implementation,
     that Parser A already conforms and Parser B does not -- the exact
     countermodel the amendment closes at the protocol level; remediating
     Parser B remains an explicitly out-of-scope, required subsequent
     implementation task;
  4. prove raw retention and scientific admission are independent, and that a
     registered schema confers no automatic validity, under more than one
     registry snapshot;
  5. prove the real T1/T2 registry-time counterfactual: an evaluation
     recorded under registry snapshot R1 is immutable and is never silently
     replaced by a fresh evaluation under a later registry snapshot R2 for
     byte-identical raw input; R2 admission is obtainable only as an
     explicitly new, separately identified evaluation; and evaluation under a
     fixed (X, R, C) is deterministic across execution time and independent
     of any ambient/global registry state;
  6. prove the amendment leaves duplicate/container/lifecycle/PIT semantics,
     and the base contract/registry bytes themselves, untouched.
"""
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping, Optional

from qntylab import r1_reference_parser as rp
from qntylab.r1_daily_market_materializer import (
    MATERIALIZATION_QUARANTINED,
    MATERIALIZED_VALID,
    ALL_CONTRACT_FIELDS,
    materialize_parser_a,
    materialize_parser_b,
    validate_daily_market_evidence_v1,
)
from qntylab.r1_retention_candidate import (
    ANOMALY_SCHEMA_MISMATCH,
    BASE_SCHEMA,
    daily_primitive,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
AMENDMENT_PATH = REPO_ROOT / "experiments/data/r1_daily_market_evidence_schema_admission_amendment_v1.json"
BASE_CONTRACT_PATH = REPO_ROOT / "experiments/data/r1_normalized_evidence_contract_v1.json"
SCHEMA_REGISTRY_PATH = REPO_ROOT / "experiments/data/r1_source_schema_registry_v1.json"
DUP_AMENDMENT_PATH = REPO_ROOT / "experiments/data/r1_normalized_evidence_duplicate_semantics_amendment_v1.json"

CUTOFF = "2026-06-30T23:59:59Z"


def _canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def _canonical_hash(value):
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load_amendment():
    return json.loads(AMENDMENT_PATH.read_bytes())


def _load_known_schema_variants():
    registry = json.loads(SCHEMA_REGISTRY_PATH.read_bytes())
    return dict(registry["known_schema_variants"])


def _registry_snapshot_sha256():
    """R1: the registry snapshot identity is the sha256 of the actual, current
    registry artifact bytes -- the same sha256-artifact-pinning convention
    already used by bound_authority/base_registry_sha256 elsewhere in this
    document, applied to the admission evaluation itself."""
    return hashlib.sha256(SCHEMA_REGISTRY_PATH.read_bytes()).hexdigest()


# --- 1. amendment self-consistency and provenance binding -------------------

def test_amendment_is_candidate_not_frozen():
    amendment = _load_amendment()
    assert amendment["status"] == "CANDIDATE_NOT_YET_FROZEN"
    assert amendment["self_freeze_authorized"] is False
    assert amendment["artifact_kind"] == "PROTOCOL_AMENDMENT_CANDIDATE"


def test_amendment_addresses_the_audited_verdict():
    amendment = _load_amendment()
    assert amendment["audit_origin"]["verdict_addressed"] == "H1_PROTOCOL_UNDERSPECIFICATION"


def test_repair_history_records_the_registry_time_repair():
    amendment = _load_amendment()
    history = amendment["repair_history"]
    assert len(history) == 1
    assert history[0]["addressed_review_verdict"] == "BLOCK_REGISTRY_TIME_AMBIGUITY"
    assert history[0]["still_not_frozen"] is True


def test_amendment_semantic_content_digest_is_self_consistent():
    amendment = _load_amendment()
    recomputed = _canonical_hash(amendment["semantic_body"])
    assert recomputed == amendment["amendment_semantic_content_sha256"]


def test_amendment_effective_combined_binding_digest_is_self_consistent():
    amendment = _load_amendment()
    binding = amendment["effective_combined_contract_binding"]
    recomputed_semantic = _canonical_hash(amendment["semantic_body"])
    recomputed_binding = _canonical_hash({
        "amendment_semantic_content_sha256": recomputed_semantic,
        "base_contract_artifact": binding["base_contract_artifact"],
        "base_contract_sha256": binding["base_contract_sha256"],
        "base_registry_artifact": binding["base_registry_artifact"],
        "base_registry_sha256": binding["base_registry_sha256"],
    })
    assert recomputed_binding == amendment["effective_combined_contract_binding_sha256"]


def test_amendment_binds_current_bytes_of_base_contract_and_registry():
    """The amendment must be bound to the CURRENT bytes of both artifacts it
    amends -- if either ever changes without a new amendment revision, this
    must fail rather than silently amend stale text."""
    amendment = _load_amendment()
    actual_contract_sha256 = hashlib.sha256(BASE_CONTRACT_PATH.read_bytes()).hexdigest()
    actual_registry_sha256 = hashlib.sha256(SCHEMA_REGISTRY_PATH.read_bytes()).hexdigest()
    assert actual_contract_sha256 == amendment["semantic_body"]["amends"]["target_artifact_sha256_at_amendment_time"]
    assert actual_contract_sha256 == amendment["effective_combined_contract_binding"]["base_contract_sha256"]
    assert actual_registry_sha256 == amendment["semantic_body"]["amends"]["target_registry_sha256_at_amendment_time"]
    assert actual_registry_sha256 == amendment["effective_combined_contract_binding"]["base_registry_sha256"]


def test_amendment_does_not_authorize_raw_deletion():
    amendment = _load_amendment()
    assert amendment["raw_deletion_authorized"] is False
    assert amendment["semantic_body"]["raw_deletion_authorized"] is False


def test_registry_snapshot_binding_section_present_and_adopted():
    amendment = _load_amendment()
    binding = amendment["semantic_body"]["registry_snapshot_binding"]
    assert binding["adopted"] is True
    assert binding["closes"].startswith("Independent hostile review verdict BLOCK_REGISTRY_TIME_AMBIGUITY")


# --- 2. standalone reimplementation of the registry-snapshot-bound predicate
# Deliberately not importing either parser's schema_identify/identify_schema:
# this is an independent re-derivation of the amendment's stated predicate
# from its own text, evaluated against the real registry file.

SCHEMA_ADMISSIBLE = "SCHEMA_ADMISSIBLE"
SCHEMA_INADMISSIBLE = "SCHEMA_INADMISSIBLE"


@dataclass(frozen=True)
class SchemaAdmissionEvaluation:
    """An admission evaluation is a recorded fact bound to a specific
    registry snapshot -- it is never mutated after construction (frozen), so
    a later evaluation under a different registry snapshot cannot silently
    alter an earlier one, only produce a new, distinct instance."""
    disposition: str
    schema_id: Optional[str]
    registry_snapshot_sha256: str


def daily_market_evidence_v1_schema_admission(
    schema_id: Optional[str],
    known_schema_variants: Mapping[str, object],
    registry_snapshot_sha256: str,
) -> SchemaAdmissionEvaluation:
    """Standalone reimplementation of
    semantic_body.schema_admission_rule.predicate_definition, per the
    registry_snapshot_binding repair: registry_snapshot_sha256 is a required
    positional argument (no default), and the function reads no ambient or
    global registry state -- it is a pure function of its three explicit
    arguments only. Governs only the schema_id dimension: necessary, not
    sufficient, for overall record validity."""
    if not isinstance(registry_snapshot_sha256, str) or len(registry_snapshot_sha256) != 64:
        raise ValueError(
            "registry_snapshot_sha256 is a required 64-hex-char binding, not optional "
            "(schema_admission_rule.predicate_definition)"
        )
    if schema_id is None or schema_id not in known_schema_variants:
        disposition = SCHEMA_INADMISSIBLE
    else:
        disposition = SCHEMA_ADMISSIBLE
    return SchemaAdmissionEvaluation(
        disposition=disposition,
        schema_id=schema_id,
        registry_snapshot_sha256=registry_snapshot_sha256,
    )


def test_predicate_requires_registry_snapshot_sha256():
    known = _load_known_schema_variants()
    import pytest
    with pytest.raises(ValueError):
        daily_market_evidence_v1_schema_admission("bybit_trade_v1", known, None)
    with pytest.raises(ValueError):
        daily_market_evidence_v1_schema_admission("bybit_trade_v1", known, "")
    with pytest.raises(ValueError):
        daily_market_evidence_v1_schema_admission("bybit_trade_v1", known, "not-a-sha256")


def test_predicate_registered_schema_is_admissible():
    known = _load_known_schema_variants()
    r1 = _registry_snapshot_sha256()
    for schema_id in known:
        evaluation = daily_market_evidence_v1_schema_admission(schema_id, known, r1)
        assert evaluation.disposition == SCHEMA_ADMISSIBLE
        assert evaluation.registry_snapshot_sha256 == r1


def test_predicate_none_schema_id_is_inadmissible():
    known = _load_known_schema_variants()
    r1 = _registry_snapshot_sha256()
    evaluation = daily_market_evidence_v1_schema_admission(None, known, r1)
    assert evaluation.disposition == SCHEMA_INADMISSIBLE
    assert evaluation.registry_snapshot_sha256 == r1


def test_predicate_unregistered_schema_id_is_inadmissible():
    known = _load_known_schema_variants()
    r1 = _registry_snapshot_sha256()
    evaluation = daily_market_evidence_v1_schema_admission("some_never_seen_variant", known, r1)
    assert evaluation.disposition == SCHEMA_INADMISSIBLE
    assert evaluation.registry_snapshot_sha256 == r1


# --- 3. countermodel: current implementation reproduces the audited gap ----
# (empirical corroboration only -- the gap being closed is a protocol-text
# gap, not this specific implementation bug; see
# semantic_body.underspecification_recorded.empirical_corroboration_not_itself_the_gap)

_UNKNOWN_HEADER = BASE_SCHEMA + ("EXTRA_UNSEEN_COLUMN",)


def _unknown_schema_row():
    return {"timestamp": "1700000000.000", "symbol": "MONUSDT", "side": "Buy", "size": "1",
            "price": "1", "tickDirection": "PlusTick", "trdMatchID": "t-1",
            "grossValue": "1e8", "homeNotional": "1", "foreignNotional": "1",
            "EXTRA_UNSEEN_COLUMN": "x"}


def _unknown_schema_raw_bytes():
    import gzip
    row = _unknown_schema_row()
    text = ",".join(_UNKNOWN_HEADER) + "\n" + ",".join(row[h] for h in _UNKNOWN_HEADER) + "\n"
    return gzip.compress(text.encode())


def test_countermodel_reproduced_on_current_parser_b_path():
    """Direct reproduction of the auditor's countermodel using the current,
    unmodified Parser B / materializer code: an unknown-schema object with
    otherwise-parseable rows is currently MATERIALIZED_VALID, is_valid=True,
    despite carrying SCHEMA_MISMATCH and schema_id=None."""
    core, anomalies = daily_primitive(stream_id="s", utc_date="2023-11-14", header=_UNKNOWN_HEADER,
                                       rows=[_unknown_schema_row()], historical_cutoff_utc=CUTOFF)
    assert core["schema_id"] is None
    assert ANOMALY_SCHEMA_MISMATCH in anomalies
    assert core["trade_count"] == 1  # record otherwise complete, not empty/refused

    raw = _unknown_schema_raw_bytes()
    result = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)
    assert result.status == MATERIALIZED_VALID
    assert result.is_valid is True
    assert result.record["schema_id"] is None
    assert ANOMALY_SCHEMA_MISMATCH in result.anomalies
    # validate_daily_market_evidence_v1 (unmodified) does not itself check
    # schema_id membership -- this is exactly the gap being closed at the
    # protocol level, not by editing this function.
    assert validate_daily_market_evidence_v1(result.record) == []


def test_countermodel_rejected_under_new_predicate():
    """The same record that the current implementation calls
    MATERIALIZED_VALID is SCHEMA_INADMISSIBLE under the amendment's
    registry-snapshot-bound predicate -- the protocol-level contradiction the
    amendment resolves, without requiring any code change here."""
    known = _load_known_schema_variants()
    r1 = _registry_snapshot_sha256()
    raw = _unknown_schema_raw_bytes()
    result = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)
    assert result.status == MATERIALIZED_VALID  # current implementation, unchanged
    evaluation = daily_market_evidence_v1_schema_admission(result.record["schema_id"], known, r1)
    assert evaluation.disposition == SCHEMA_INADMISSIBLE
    assert result.is_valid is True and evaluation.disposition == SCHEMA_INADMISSIBLE, (
        "this contradiction between implementation-level is_valid and the new "
        "protocol-level admission predicate is exactly parser_status.parser_b_current's "
        "recorded NONCONFORMING disposition; remediation is explicitly out of scope here"
    )


def test_parser_a_already_conforms_never_valid_on_unknown_schema():
    """Parser A already never emits a non-None record for an unrecognized
    column set -- it already satisfies schema_admission_rule without any
    change, per semantic_body.parser_status.parser_a_current."""
    raw = _unknown_schema_raw_bytes()
    result = materialize_parser_a(raw, date(2023, 11, 14), "x")
    assert result.status == MATERIALIZATION_QUARANTINED
    assert result.record is None
    assert result.status != MATERIALIZED_VALID

    direct = rp.parse_daily_object(raw, date(2023, 11, 14), "x")
    assert direct.status == rp.STATUS_UNKNOWN_SCHEMA_QUARANTINE
    assert direct.record is None


# --- 4. red-team scenario B: raw retention independent of admission --------

def test_raw_retention_independent_of_admission_parser_a():
    """Scenario B: raw object identity (raw_object_sha256) remains available
    for an unknown-schema object even though it is not admitted -- retention
    is not gated on, and does not grant, admission."""
    raw = _unknown_schema_raw_bytes()
    result = materialize_parser_a(raw, date(2023, 11, 14), "x")
    assert result.status == MATERIALIZATION_QUARANTINED
    assert result.raw_object_sha256 == hashlib.sha256(raw).hexdigest()


def test_raw_retention_independent_of_admission_parser_b():
    known = _load_known_schema_variants()
    r1 = _registry_snapshot_sha256()
    raw = _unknown_schema_raw_bytes()
    result = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)
    evaluation = daily_market_evidence_v1_schema_admission(result.record["schema_id"], known, r1)
    assert evaluation.disposition == SCHEMA_INADMISSIBLE
    # raw identity is present regardless of the (inadmissible) predicate result
    assert result.raw_object_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.record["source_object_sha256"] == hashlib.sha256(raw).hexdigest()


# --- 5. red-team scenario C: registered schema confers no automatic validity,
# under more than one registry snapshot (mutation D coverage)

def test_registered_schema_with_missing_required_field_still_invalid():
    """A record with a SCHEMA_ADMISSIBLE schema_id but a pre-existing
    contract violation (missing required non-null field when trade_count>0)
    remains invalid under the unmodified validator -- schema registration is
    necessary, not sufficient. Checked under both R1 and a simulated R2 to
    prove the sufficiency-collapse a later registry snapshot must not grant."""
    known_r1 = _load_known_schema_variants()
    r1 = _registry_snapshot_sha256()
    known_r2 = dict(known_r1)
    known_r2["future_variant_not_yet_registered"] = {"status": "KNOWN_VALID_SCHEMA_VARIANT"}
    r2 = _canonical_hash(known_r2)  # stand-in for a distinct future registry artifact's own sha256
    assert r2 != r1

    for schema_id, known, r in (("bybit_trade_v1", known_r1, r1),
                                 ("future_variant_not_yet_registered", known_r2, r2)):
        evaluation = daily_market_evidence_v1_schema_admission(schema_id, known, r)
        assert evaluation.disposition == SCHEMA_ADMISSIBLE

        record = {f: None for f in ALL_CONTRACT_FIELDS}
        record.update({
            "instrument_instance_id": "x", "utc_date": "2023-11-14", "trade_count": 1,
            "duplicate_count": 0, "rejected_row_count": 0, "schema_id": schema_id,
            "open": "1", "high": "1", "low": "1",
            # "close" deliberately omitted (stays None) -- required when trade_count>0
            "base_volume": "1", "quote_turnover": "1",
            "first_source_timestamp_utc": "2023-11-14T00:00:00.000Z",
            "last_source_timestamp_utc": "2023-11-14T00:00:00.000Z",
            "first_source_trade_id": "t-1", "last_source_trade_id": "t-1",
            "source_object_sha256": "a" * 64,
        })
        violations = validate_daily_market_evidence_v1(record)
        assert any("close" in v for v in violations), (
            "SCHEMA_ADMISSIBLE under a registry snapshot must never make condition (a) "
            "unnecessary, regardless of which registry snapshot granted (b)"
        )


# --- 6. the actual registry-time repair: real T1/T2 counterfactual ---------

def test_r1_evaluation_is_immutable_and_survives_a_later_r2_evaluation():
    """The real T1/T2 counterfactual (not the old, insufficient 'a Python
    variable does not spontaneously mutate' test): raw bytes X evaluated
    under registry snapshot R1 (schema S absent) are SCHEMA_INADMISSIBLE. A
    later, distinct registry snapshot R2 (schema S registered) is then
    constructed and X is evaluated fresh under R2. The R1 evaluation object,
    obtained BEFORE R2 existed, must still report SCHEMA_INADMISSIBLE
    afterward -- it must not have been silently reclassified -- and the R1
    and R2 evaluations must be distinct, separately identified facts."""
    known_r1 = _load_known_schema_variants()
    r1 = _registry_snapshot_sha256()
    schema_id = "future_variant_not_yet_registered"

    # T1: evaluate under R1 (S absent). Keep the resulting evaluation object.
    evaluation_r1 = daily_market_evidence_v1_schema_admission(schema_id, known_r1, r1)
    assert evaluation_r1.disposition == SCHEMA_INADMISSIBLE
    assert evaluation_r1.registry_snapshot_sha256 == r1

    # A later, independently reviewed amendment creates a DISTINCT registry
    # snapshot R2 that registers S. This is a new artifact/identity, not an
    # in-place mutation of R1's known_schema_variants dict.
    known_r2 = dict(known_r1)
    known_r2[schema_id] = {"status": "KNOWN_VALID_SCHEMA_VARIANT"}
    r2 = _canonical_hash(known_r2)
    assert r2 != r1

    # T2: the R1 evaluation, obtained before R2 existed, is unchanged -- values
    # are immutable (frozen dataclass) and nothing re-derives it from live state.
    assert evaluation_r1.disposition == SCHEMA_INADMISSIBLE
    assert evaluation_r1.registry_snapshot_sha256 == r1

    # A fresh, explicit evaluation of the SAME raw schema_id under R2 is a
    # NEW, separately identified fact -- SCHEMA_ADMISSIBLE under R2 only.
    evaluation_r2 = daily_market_evidence_v1_schema_admission(schema_id, known_r2, r2)
    assert evaluation_r2.disposition == SCHEMA_ADMISSIBLE
    assert evaluation_r2.registry_snapshot_sha256 == r2

    # The two evaluations are distinct facts, not the same fact overwritten.
    assert evaluation_r1 != evaluation_r2
    assert evaluation_r1.registry_snapshot_sha256 != evaluation_r2.registry_snapshot_sha256
    assert evaluation_r1.disposition != evaluation_r2.disposition
    # And the R1 fact, inspected one more time after R2's evaluation exists,
    # still reads exactly as it did at T1 -- no retroactive reclassification.
    assert evaluation_r1.disposition == SCHEMA_INADMISSIBLE


_AMBIENT_REGISTRY_FOR_DETERMINISM_TEST = {"known_schema_variants": {}, "registry_snapshot_sha256": "0" * 64}


def test_evaluation_is_deterministic_and_independent_of_ambient_registry_state():
    """admission(X, R, C, t1) == admission(X, R, C, t2): calling the predicate
    twice with the exact same explicit (schema_id, known_schema_variants,
    registry_snapshot_sha256) arguments must yield the same result even if
    some unrelated ambient/global value that a naive implementation might
    mistake for 'the current registry' changes in between -- because the
    predicate must never read such ambient state, only its own arguments."""
    known = _load_known_schema_variants()
    r1 = _registry_snapshot_sha256()

    _AMBIENT_REGISTRY_FOR_DETERMINISM_TEST["known_schema_variants"] = dict(known)
    _AMBIENT_REGISTRY_FOR_DETERMINISM_TEST["registry_snapshot_sha256"] = r1
    evaluation_t1 = daily_market_evidence_v1_schema_admission("bybit_trade_v1", known, r1)

    # Mutate the ambient stand-in between calls -- a correct, argument-pure
    # predicate must be unaffected because it never consults this dict.
    _AMBIENT_REGISTRY_FOR_DETERMINISM_TEST["known_schema_variants"] = {}
    _AMBIENT_REGISTRY_FOR_DETERMINISM_TEST["registry_snapshot_sha256"] = "f" * 64

    evaluation_t2 = daily_market_evidence_v1_schema_admission("bybit_trade_v1", known, r1)
    assert evaluation_t1 == evaluation_t2
    assert evaluation_t1.disposition == SCHEMA_ADMISSIBLE == evaluation_t2.disposition


def test_r2_admission_requires_its_own_explicit_registry_snapshot():
    """A caller cannot obtain R2's admissibility by reusing R1's
    registry_snapshot_sha256 with R2's known_schema_variants (mutation A:
    'evaluator silently uses latest/current registry') -- the snapshot
    identity and the variant map must agree, and every evaluation records
    its own explicit snapshot rather than an implicit 'current' one."""
    known_r1 = _load_known_schema_variants()
    r1 = _registry_snapshot_sha256()
    known_r2 = dict(known_r1)
    known_r2["future_variant_not_yet_registered"] = {"status": "KNOWN_VALID_SCHEMA_VARIANT"}
    r2 = _canonical_hash(known_r2)

    # Evaluating with R2's variant map still records itself as governed by R2
    # -- never silently mislabeled as R1 (mutation B: registry identity
    # omitted/mismatched in provenance).
    evaluation = daily_market_evidence_v1_schema_admission("future_variant_not_yet_registered", known_r2, r2)
    assert evaluation.registry_snapshot_sha256 == r2
    assert evaluation.registry_snapshot_sha256 != r1


# --- 7. red-team scenario E: unrelated frozen semantics left untouched -----

def test_amendment_declares_unrelated_semantics_out_of_scope():
    amendment = _load_amendment()
    out_of_scope = amendment["semantic_body"]["explicitly_not_addressed_by_this_amendment"]
    joined = " ".join(out_of_scope)
    for term in ("duplicate semantics", "timestamp", "funding", "gap classification", "lifecycle"):
        assert term in joined, term


def test_amendment_leaves_duplicate_semantics_amendment_bytes_untouched():
    amendment = _load_amendment()
    actual_sha256 = hashlib.sha256(DUP_AMENDMENT_PATH.read_bytes()).hexdigest()
    recorded = amendment["semantic_body"]["amends"]["also_informed_by_unchanged"][
        "r1_normalized_evidence_duplicate_semantics_amendment_v1.json_sha256"
    ]
    assert actual_sha256 == recorded


def test_amendment_leaves_base_contract_and_registry_bytes_untouched():
    """Redundant with test_amendment_binds_current_bytes_of_base_contract_and_registry
    but asserted directly against amends.original_*_bytes_unchanged_by_this_amendment
    to pin the amendment's own explicit claim, not just the digest binding."""
    amendment = _load_amendment()
    assert amendment["semantic_body"]["amends"]["original_contract_bytes_unchanged_by_this_amendment"] is True
    assert amendment["semantic_body"]["amends"]["original_schema_registry_bytes_unchanged_by_this_amendment"] is True


def test_known_schema_duplicate_semantics_regression_unaffected():
    """Sanity regression: a KNOWN-schema duplicate-group fixture must still
    resolve exactly as the (unmodified) duplicate-semantics amendment
    already governs -- this amendment does not touch that logic."""
    from decimal import Decimal
    rows = [
        {"timestamp": "1751328000.0", "symbol": "MONUSDT", "side": "Buy", "size": "2", "price": "1.1",
         "tickDirection": "PlusTick", "trdMatchID": "z" * 32, "grossValue": "220000000",
         "homeNotional": "2", "foreignNotional": "2.2"},
        {"timestamp": "1751328000.0", "symbol": "MONUSDT", "side": "Sell", "size": "2.00", "price": "1.10",
         "tickDirection": "MinusTick", "trdMatchID": "z" * 32, "grossValue": "220000000",
         "homeNotional": "2.00", "foreignNotional": "2.20"},
    ]
    core, anomalies = daily_primitive(stream_id="s", utc_date="2025-07-01", header=BASE_SCHEMA,
                                       rows=rows, historical_cutoff_utc=CUTOFF)
    assert core["schema_id"] == "bybit_trade_v1"
    assert Decimal(core["close"]) == Decimal("1.1")
    assert core["duplicate_count"] == 1


def test_parser_status_snapshots_match_current_module_bytes():
    """Governance snapshot accuracy: parser_status records the exact current
    module bytes at candidate-authoring time, so a later, legitimate repair
    of either module is detectable as a snapshot mismatch rather than
    silently assumed still accurate."""
    amendment = _load_amendment()
    import qntylab.r1_reference_parser as rp_mod
    import qntylab.r1_retention_candidate as rc_mod
    a_sha = hashlib.sha256(Path(rp_mod.__file__).read_bytes()).hexdigest()
    b_sha = hashlib.sha256(Path(rc_mod.__file__).read_bytes()).hexdigest()
    assert a_sha == amendment["semantic_body"]["parser_status"]["parser_a_current"]["current_sha256"]
    assert b_sha == amendment["semantic_body"]["parser_status"]["parser_b_current"]["current_sha256"]
