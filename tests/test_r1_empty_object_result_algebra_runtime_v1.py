"""Runtime conformance tests for the FROZEN EMPTY_OBJECT result algebra
(experiments/data/r1_empty_object_result_algebra_amendment_v1.json), as
implemented in qntylab.r1_daily_market_materializer.materialize_parser_a
(lane R1_EMPTY_OBJECT_RESULT_ALGEBRA_RUNTIME_IMPLEMENTATION).

This file tests RUNTIME BEHAVIOR of the canonical public, admission-gated
Parser-A materialization boundary -- not the frozen amendment artifact's own
text/hash bindings, which remain covered, unmodified except for one narrowly
authorized exception, by tests/test_r1_empty_object_result_algebra_amendment_v1.py.

Covers: the public valid-record path, the exact EMPTY_OBJECT observation
path, the near-empty non-widening matrix, unauthorized/unknown inputs,
schema-substitution attacks, the private-capability/public-authority
separation, result-envelope tagged-union invariants, exact-X identity and
replay, authority-binding-mismatch fail-closed behavior, batch isolation,
the compatibility alias, the pre-repair/post-repair countermodel, and the
R1-R12 hostile mutation checklist.
"""
from __future__ import annotations

import gzip
import hashlib
import inspect
import io
import json
from dataclasses import fields
from datetime import date

import pytest

from qntylab import r1_daily_market_materializer as materializer
from qntylab import r1_schema_admission as admission
from qntylab import r1_schema_recognizer as recognizer

INSTRUMENT = "BYBIT_PERP_RUNTIME_TEST_V1"
UTC_DATE = date(2023, 11, 14)

REGISTRY_PATH = materializer._DATA / "r1_source_schema_registry_v1.json"
RESULT_ALGEBRA_PATH = materializer._RESULT_ALGEBRA_ARTIFACT_PATH


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _registry_fields(schema_id: str) -> list[str]:
    return json.loads(REGISTRY_PATH.read_bytes())["known_schema_variants"][schema_id]["field_set"]


BASE_HEADER = "timestamp,symbol,side,size,price,tickDirection,trdMatchID,grossValue,homeNotional,foreignNotional"
BASE_ROWS = (
    "1700000000.123,BTCUSDT,Buy,2,100.5,PlusTick,trade1,201.0,2,201.0\n"
    "1700000005.456,BTCUSDT,Sell,1,101.0,MinusTick,trade2,101.0,1,101.0\n"
)


def _valid_object() -> bytes:
    assert set(BASE_HEADER.split(",")) == set(_registry_fields("bybit_trade_v1"))
    return gzip.compress((BASE_HEADER + "\n" + BASE_ROWS).encode())


def _raw_header_only(header: str) -> bytes:
    return gzip.compress((header + "\nrow\n").encode())


def _rpi_object() -> bytes:
    return _raw_header_only(",".join(_registry_fields("bybit_trade_v1_rpi")))


def _unknown_object() -> bytes:
    return _raw_header_only("not,a,registered,header")


def _malformed_header_object() -> bytes:
    return _raw_header_only("a,b,a")  # duplicate token name


def _framing_failure_object() -> bytes:
    return b"this is not a valid gzip stream at all"


def _invalid_utf8_object() -> bytes:
    return gzip.compress(b"\xff\xfe\x00invalid utf8 csv content\n")


def _empty_object(mtime: int = 0) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=mtime, compresslevel=6) as f:
        f.write(b"")
    return buf.getvalue()


ALL_QUARANTINE_FIXTURES = [
    _rpi_object, _unknown_object, _malformed_header_object,
    _framing_failure_object, _invalid_utf8_object,
]

NEAR_EMPTY_BODIES = [b"\n", b" ", b",", b"\xef\xbb\xbf"]


# ---------------------------------------------------------------------------
# Public valid outcome
# ---------------------------------------------------------------------------

def test_public_valid_outcome_authorized_bybit_trade_v1():
    raw = _valid_object()
    evaluation = admission.evaluate_schema_admission(raw)
    result = materializer.materialize_parser_a(raw, UTC_DATE, INSTRUMENT)

    assert result.status == materializer.MATERIALIZED_VALID
    assert result.is_valid is True
    assert result.record is not None
    assert result.observation is None
    assert result.record["schema_id"] == evaluation.schema_id == "bybit_trade_v1"
    assert result.record["source_object_sha256"] == _sha256(raw) == result.raw_object_sha256


# ---------------------------------------------------------------------------
# Exact EMPTY_OBJECT outcome
# ---------------------------------------------------------------------------

def test_exact_empty_object_outcome(monkeypatch):
    raw = gzip.compress(b"")
    calls = []
    real_unadmitted = materializer._materialize_parser_a_unadmitted

    def spy(*a, **k):
        calls.append(1)
        return real_unadmitted(*a, **k)

    monkeypatch.setattr(materializer, "_materialize_parser_a_unadmitted", spy)

    evaluation = admission.evaluate_schema_admission(raw)
    result = materializer.materialize_parser_a(raw, UTC_DATE, INSTRUMENT)

    assert result.status == materializer.EMPTY_OBJECT_OBSERVATION
    assert result.is_valid is False
    assert result.record is None
    assert result.observation is not None
    assert result.observation["trade_count"] == 0
    assert "schema_id" not in result.observation
    assert result.observation["instrument_instance_id"] == INSTRUMENT
    assert result.observation["utc_date"] == UTC_DATE.isoformat()
    assert result.observation["source_object_sha256"] == _sha256(raw)
    assert result.observation["recognition_disposition"] == evaluation.recognition_disposition == recognizer.FRAMING_FAILURE
    assert result.observation["recognition_reasons"] == evaluation.reasons == ("EMPTY_OBJECT",)
    assert result.observation["schema_admission"] == evaluation.admission == admission.INADMISSIBLE
    assert calls == [], "private Parser-A primitive must not be called to manufacture the EMPTY_OBJECT observation"


# ---------------------------------------------------------------------------
# Near-empty matrix -- none may reach the EMPTY_OBJECT observation status
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body", NEAR_EMPTY_BODIES, ids=lambda b: repr(b))
def test_near_empty_gzip_bodies_never_reach_observation(body):
    raw = gzip.compress(body)
    result = materializer.materialize_parser_a(raw, UTC_DATE, INSTRUMENT)
    assert result.status != materializer.EMPTY_OBJECT_OBSERVATION
    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert result.observation is None
    assert result.record is None


def test_raw_empty_bytes_never_reach_observation():
    result = materializer.materialize_parser_a(b"", UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert result.observation is None


def test_invalid_gzip_never_reaches_observation():
    result = materializer.materialize_parser_a(_framing_failure_object(), UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert result.observation is None


def test_invalid_utf8_gzip_payload_never_reaches_observation():
    result = materializer.materialize_parser_a(_invalid_utf8_object(), UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert result.observation is None


# ---------------------------------------------------------------------------
# Unauthorized and unknown inputs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("build_raw", ALL_QUARANTINE_FIXTURES)
def test_unauthorized_and_unknown_inputs_quarantine(build_raw):
    result = materializer.materialize_parser_a(build_raw(), UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert result.is_valid is False
    assert result.record is None
    assert result.observation is None


def test_ambiguous_disposition_quarantines(monkeypatch):
    """No two registered schemas currently collide (pairwise-unique field
    sets), so AMBIGUOUS is not constructible against the real, frozen
    registry without breaking authority verification. Exercised here via a
    narrowly scoped monkeypatch of evaluate_schema_admission's return value
    only -- the real recognizer/registry/admission modules are untouched."""
    raw = _valid_object()
    fabricated = admission.SchemaAdmissionEvaluation(
        source_object_sha256=_sha256(raw),
        recognition_disposition=recognizer.AMBIGUOUS,
        schema_id=None,
        admission=admission.INADMISSIBLE,
        reasons=(),
    )
    monkeypatch.setattr(materializer.admission, "evaluate_schema_admission", lambda *a, **k: fabricated)
    result = materializer.materialize_parser_a(raw, UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert result.record is None
    assert result.observation is None


# ---------------------------------------------------------------------------
# Schema substitution attacks
# ---------------------------------------------------------------------------

def _admissible_evaluation(schema_id="bybit_trade_v1"):
    return admission.SchemaAdmissionEvaluation(
        source_object_sha256="a" * 64,
        recognition_disposition=recognizer.RECOGNIZED,
        schema_id=schema_id,
        admission=admission.ADMISSIBLE,
        reasons=(),
    )


@pytest.mark.parametrize("bad_schema_id", [None, "", "UNKNOWN_SCHEMA", "future_unlisted_schema_v999", 123])
def test_validate_admitted_record_rejects_bad_schema_ids(bad_schema_id):
    evaluation = _admissible_evaluation("bybit_trade_v1")
    record = {"schema_id": bad_schema_id}
    violations = materializer._validate_admitted_record(record, evaluation)
    assert violations


def test_validate_admitted_record_rejects_registered_but_unauthorized_mismatch():
    evaluation = _admissible_evaluation("bybit_trade_v1")
    record = {"schema_id": "bybit_trade_v1_rpi"}
    violations = materializer._validate_admitted_record(record, evaluation)
    assert violations


def test_validate_admitted_record_rejects_schema_id_differing_from_evaluation():
    evaluation = _admissible_evaluation("bybit_trade_v1")
    record = {"schema_id": "bybit_trade_v1_but_typo"}
    violations = materializer._validate_admitted_record(record, evaluation)
    assert violations


def test_validate_admitted_record_accepts_matching_schema_id():
    evaluation = _admissible_evaluation("bybit_trade_v1")
    record = {"schema_id": "bybit_trade_v1"}
    assert materializer._validate_admitted_record(record, evaluation) == []


def test_public_path_rejects_candidate_with_substituted_schema_id(monkeypatch):
    """End-to-end: even if the private primitive's candidate record carried a
    forged/mismatched schema_id, the public boundary's own
    _validate_admitted_record check must still block it -- there is no
    caller-facing parameter to inject this."""
    raw = _valid_object()
    real_unadmitted = materializer._materialize_parser_a_unadmitted

    def forged(*a, **k):
        result = real_unadmitted(*a, **k)
        forged_record = dict(result.record)
        forged_record["schema_id"] = "future_unlisted_schema_v999"
        return materializer.MaterializationResult(
            status=result.status, parser=result.parser, raw_object_sha256=result.raw_object_sha256,
            record=forged_record, anomalies=result.anomalies,
        )

    monkeypatch.setattr(materializer, "_materialize_parser_a_unadmitted", forged)
    result = materializer.materialize_parser_a(raw, UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert result.record is None
    assert result.is_valid is False


def test_public_path_rejects_candidate_with_substituted_source_object_sha256(monkeypatch):
    """End-to-end reproduction of the hostile-review blocker
    PUBLIC_VALID_WITH_WRONG_SOURCE_OBJECT_HASH: even if the private
    primitive's candidate record carried a forged record.source_object_sha256
    (e.g. because the private primitive's own check were mutated away), the
    public boundary must independently reverify record.source_object_sha256
    against sha256(raw_bytes) itself and quarantine on mismatch -- there is
    no caller-facing parameter to inject this."""
    raw = _valid_object()
    raw_sha = _sha256(raw)
    real_unadmitted = materializer._materialize_parser_a_unadmitted

    def forged(*a, **k):
        result = real_unadmitted(*a, **k)
        forged_record = dict(result.record)
        forged_record["source_object_sha256"] = "b" * 64
        return materializer.MaterializationResult(
            status=result.status, parser=result.parser, raw_object_sha256=result.raw_object_sha256,
            record=forged_record, anomalies=result.anomalies,
        )

    monkeypatch.setattr(materializer, "_materialize_parser_a_unadmitted", forged)
    result = materializer.materialize_parser_a(raw, UTC_DATE, INSTRUMENT)

    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert result.is_valid is False
    assert result.record is None
    assert result.observation is None
    assert result.raw_object_sha256 == raw_sha
    assert materializer.rc.ANOMALY_SOURCE_MUTATION in result.anomalies


def test_public_path_rejects_candidate_with_substituted_raw_object_sha256(monkeypatch):
    """Second substitution channel: candidate.raw_object_sha256 itself forged
    to a wrong-but-syntactically-valid hash, even though the record's own
    embedded source_object_sha256 is correct. The public boundary must reject
    this channel too, independent of the record-embedded check above."""
    raw = _valid_object()
    raw_sha = _sha256(raw)
    real_unadmitted = materializer._materialize_parser_a_unadmitted

    def forged(*a, **k):
        result = real_unadmitted(*a, **k)
        return materializer.MaterializationResult(
            status=result.status, parser=result.parser, raw_object_sha256="b" * 64,
            record=dict(result.record), anomalies=result.anomalies,
        )

    monkeypatch.setattr(materializer, "_materialize_parser_a_unadmitted", forged)
    result = materializer.materialize_parser_a(raw, UTC_DATE, INSTRUMENT)

    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert result.is_valid is False
    assert result.record is None
    assert result.observation is None
    assert result.raw_object_sha256 == raw_sha
    assert materializer.rc.ANOMALY_SOURCE_MUTATION in result.anomalies


def test_public_path_rejects_admission_evaluation_with_substituted_source_object_sha256(monkeypatch):
    """Third substitution channel: evaluation.source_object_sha256 itself
    forged to a wrong-but-syntactically-valid hash, even though both the
    candidate's raw_object_sha256 and its record's embedded
    source_object_sha256 are correct. The public boundary must
    independently reject this channel too -- it must not rely solely on the
    candidate-side checks and skip re-verifying the admission evaluation's
    own source-identity binding."""
    raw = _valid_object()
    raw_sha = _sha256(raw)
    real_evaluation = admission.evaluate_schema_admission(raw)
    forged_evaluation = admission.SchemaAdmissionEvaluation(
        source_object_sha256="b" * 64,
        recognition_disposition=real_evaluation.recognition_disposition,
        schema_id=real_evaluation.schema_id,
        admission=real_evaluation.admission,
        reasons=real_evaluation.reasons,
    )
    monkeypatch.setattr(materializer.admission, "evaluate_schema_admission", lambda *a, **k: forged_evaluation)
    result = materializer.materialize_parser_a(raw, UTC_DATE, INSTRUMENT)

    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert result.is_valid is False
    assert result.record is None
    assert result.observation is None
    assert result.raw_object_sha256 == raw_sha
    assert materializer.rc.ANOMALY_SOURCE_MUTATION in result.anomalies


def test_no_caller_facing_parameter_can_inject_schema_id():
    params = set(inspect.signature(materializer.materialize_parser_a).parameters)
    assert params == {"raw_bytes", "expected_utc_date", "instrument_instance_id", "expected_raw_sha256"}
    for forbidden in ("schema_id", "admission", "disposition", "recognition_result", "is_valid"):
        assert forbidden not in params


# ---------------------------------------------------------------------------
# Private capability boundary
# ---------------------------------------------------------------------------

def test_private_primitive_materializes_rpi_but_is_not_public_valid():
    raw = _rpi_object()
    direct = materializer._materialize_parser_a_unadmitted(raw, UTC_DATE, INSTRUMENT)
    assert direct.status == materializer.INTERNAL_PARSER_A_CANDIDATE
    assert direct.status != materializer.MATERIALIZED_VALID
    assert direct.is_valid is False
    assert direct.record["schema_id"] == "bybit_trade_v1_rpi"

    public = materializer.materialize_parser_a(raw, UTC_DATE, INSTRUMENT)
    assert public.status == materializer.MATERIALIZATION_QUARANTINED
    assert public.record is None
    assert public.is_valid is False


# ---------------------------------------------------------------------------
# Result-envelope construction attacks
# ---------------------------------------------------------------------------

def test_is_valid_false_when_record_and_observation_both_present():
    result = materializer.MaterializationResult(
        status=materializer.MATERIALIZED_VALID, parser="A", raw_object_sha256="a" * 64,
        record={"schema_id": "bybit_trade_v1"}, observation={"trade_count": 0},
    )
    assert result.is_valid is False


def test_is_valid_false_for_valid_status_with_record_absent():
    result = materializer.MaterializationResult(
        status=materializer.MATERIALIZED_VALID, parser="A", raw_object_sha256="a" * 64, record=None,
    )
    assert result.is_valid is False


def test_is_valid_always_false_for_empty_object_status():
    always_false = materializer.MaterializationResult(
        status=materializer.EMPTY_OBJECT_OBSERVATION, parser="A", raw_object_sha256="a" * 64,
        observation=None,
    )
    assert always_false.is_valid is False
    forced = materializer.MaterializationResult(
        status=materializer.EMPTY_OBJECT_OBSERVATION, parser="A", raw_object_sha256="a" * 64,
        observation={"trade_count": 0}, record={"schema_id": "x"},
    )
    assert forced.is_valid is False


def test_is_valid_always_false_for_quarantine_status_even_with_record_present():
    result = materializer.MaterializationResult(
        status=materializer.MATERIALIZATION_QUARANTINED, parser="A", raw_object_sha256="a" * 64,
        record={"schema_id": "bybit_trade_v1"},
    )
    assert result.is_valid is False


def test_is_valid_is_a_derived_property_not_a_constructor_field():
    field_names = {f.name for f in fields(materializer.MaterializationResult)}
    assert "is_valid" not in field_names
    with pytest.raises(TypeError):
        materializer.MaterializationResult(
            status=materializer.MATERIALIZED_VALID, parser="A", raw_object_sha256="a" * 64,
            is_valid=True,
        )


@pytest.mark.parametrize("build_raw", [_valid_object, _rpi_object, _unknown_object,
                                        _malformed_header_object, _framing_failure_object,
                                        _invalid_utf8_object, lambda: gzip.compress(b"")])
def test_canonical_boundary_never_produces_forbidden_envelope_states(build_raw):
    result = materializer.materialize_parser_a(build_raw(), UTC_DATE, INSTRUMENT)
    assert not (result.record is not None and result.observation is not None)
    if result.status == materializer.MATERIALIZED_VALID:
        assert result.record is not None and result.observation is None
    elif result.status == materializer.EMPTY_OBJECT_OBSERVATION:
        assert result.record is None and result.observation is not None
        assert result.is_valid is False
    elif result.status == materializer.MATERIALIZATION_QUARANTINED:
        assert result.record is None and result.observation is None
        assert result.is_valid is False


def test_source_never_constructs_result_with_both_record_and_observation_kwargs():
    """Structural proof: no MaterializationResult(...) call site inside
    materialize_parser_a's own source ever supplies both `record=` and
    `observation=` in the same call."""
    source = inspect.getsource(materializer.materialize_parser_a)
    for chunk in source.split("MaterializationResult(")[1:]:
        call_body = chunk.split(")\n", 1)[0]
        assert not ("record=" in call_body and "observation=" in call_body), call_body


# ---------------------------------------------------------------------------
# Exact-X replay
# ---------------------------------------------------------------------------

def test_exact_x_replay_deterministic():
    raw = _valid_object()
    r1 = materializer.materialize_parser_a(raw, UTC_DATE, INSTRUMENT)
    r2 = materializer.materialize_parser_a(raw, UTC_DATE, INSTRUMENT)
    assert r1 == r2

    empty = gzip.compress(b"")
    e1 = materializer.materialize_parser_a(empty, UTC_DATE, INSTRUMENT)
    e2 = materializer.materialize_parser_a(empty, UTC_DATE, INSTRUMENT)
    assert e1 == e2


def test_byte_distinct_empty_objects_share_outcome_but_not_identity():
    x1 = _empty_object(mtime=0)
    x2 = _empty_object(mtime=1_600_000_000)
    assert x1 != x2
    assert _sha256(x1) != _sha256(x2)

    r1 = materializer.materialize_parser_a(x1, UTC_DATE, INSTRUMENT)
    r2 = materializer.materialize_parser_a(x2, UTC_DATE, INSTRUMENT)

    assert r1.status == r2.status == materializer.EMPTY_OBJECT_OBSERVATION
    assert r1.observation["trade_count"] == r2.observation["trade_count"] == 0
    assert r1.observation["recognition_disposition"] == r2.observation["recognition_disposition"]
    assert r1.observation["recognition_reasons"] == r2.observation["recognition_reasons"]
    assert r1.observation["schema_admission"] == r2.observation["schema_admission"]

    assert r1.raw_object_sha256 != r2.raw_object_sha256
    assert r1.observation["source_object_sha256"] != r2.observation["source_object_sha256"]
    assert r1.observation["source_object_sha256"] == _sha256(x1)
    assert r2.observation["source_object_sha256"] == _sha256(x2)


# ---------------------------------------------------------------------------
# Authority mismatch
# ---------------------------------------------------------------------------

def test_result_algebra_authority_mismatch_fails_closed(monkeypatch):
    tampered = json.loads(RESULT_ALGEBRA_PATH.read_bytes())
    tampered["semantic_body"]["result_algebra"]["outcome_enum"].append("EXTRA_FABRICATED_OUTCOME")
    tampered_bytes = json.dumps(tampered).encode()
    monkeypatch.setattr(materializer, "_load_default_result_algebra_bytes", lambda: tampered_bytes)

    result = materializer.materialize_parser_a(_valid_object(), UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert result.record is None
    assert result.observation is None
    assert result.is_valid is False
    assert "RESULT_ALGEBRA_AUTHORITY_MISMATCH" in result.anomalies


def test_result_algebra_authority_mismatch_never_raises_out_of_public_boundary(monkeypatch):
    monkeypatch.setattr(materializer, "_load_default_result_algebra_bytes", lambda: b"not even json")
    result = materializer.materialize_parser_a(gzip.compress(b""), UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZATION_QUARANTINED


def test_result_algebra_authority_verifier_raises_directly_on_tamper():
    tampered = json.loads(RESULT_ALGEBRA_PATH.read_bytes())
    tampered["status"] = "CANDIDATE_NOT_YET_FROZEN"
    with pytest.raises(ValueError):
        materializer._verify_result_algebra_authority(json.dumps(tampered).encode())


def test_result_algebra_authority_verifies_real_frozen_bytes():
    doc = materializer._verify_result_algebra_authority(RESULT_ALGEBRA_PATH.read_bytes())
    assert doc["status"] == "FROZEN"


# ---------------------------------------------------------------------------
# Batch matrix
# ---------------------------------------------------------------------------

def test_batch_matrix_valid_empty_corrupt_valid():
    items = [
        (_valid_object(), UTC_DATE, "x|A"),
        (gzip.compress(b""), UTC_DATE, "x|B"),
        (_framing_failure_object(), UTC_DATE, "x|C"),
        (_valid_object(), UTC_DATE, "x|D"),
    ]
    results = materializer.materialize_batch(items, materializer.materialize_parser_a)
    assert len(results) == 4
    assert [r.status for r in results] == [
        materializer.MATERIALIZED_VALID,
        materializer.EMPTY_OBJECT_OBSERVATION,
        materializer.MATERIALIZATION_QUARANTINED,
        materializer.MATERIALIZED_VALID,
    ]
    assert results[0].record is not None and results[0].observation is None
    assert results[1].observation is not None and results[1].record is None
    assert results[2].record is None and results[2].observation is None
    assert results[3].record is not None and results[3].observation is None


# ---------------------------------------------------------------------------
# Compatibility alias
# ---------------------------------------------------------------------------

def test_compatibility_alias_is_same_function_object():
    assert materializer.materialize_admitted_parser_a is materializer.materialize_parser_a


def test_compatibility_alias_behaves_identically_across_all_statuses():
    for build_raw in ALL_QUARANTINE_FIXTURES + [_valid_object, lambda: gzip.compress(b"")]:
        raw = build_raw()
        via_canonical = materializer.materialize_parser_a(raw, UTC_DATE, INSTRUMENT)
        via_alias = materializer.materialize_admitted_parser_a(raw, UTC_DATE, INSTRUMENT)
        assert via_canonical == via_alias


# ---------------------------------------------------------------------------
# Current-runtime countermodel: explicit before/after regression description
# ---------------------------------------------------------------------------

def test_before_after_empty_object_countermodel_regression():
    """Before repair (pre-existing behavior this lane replaces): exact
    EMPTY_OBJECT reached MATERIALIZED_VALID_RECORD, is_valid=True,
    record.schema_id=None -- a direct contradiction of the frozen schema
    admission rule (countermodel_a_current_contradiction,
    FORBIDDEN_BY_RESULT_ALGEBRA). After repair: that state is mechanically
    unreachable through materialize_parser_a."""
    result = materializer.materialize_parser_a(gzip.compress(b""), UTC_DATE, INSTRUMENT)

    before_repair_forbidden_state = (
        result.status == materializer.MATERIALIZED_VALID
        and result.is_valid is True
        and result.record is not None
        and result.record.get("schema_id") is None
    )
    assert before_repair_forbidden_state is False

    assert result.status == materializer.EMPTY_OBJECT_OBSERVATION
    assert result.is_valid is False
    assert result.record is None


# ---------------------------------------------------------------------------
# Mutation-oriented hostile tests R1-R12
# ---------------------------------------------------------------------------

def test_r1_generic_framing_failure_acceptance_is_not_the_actual_rule():
    """R1: a generic 'any FRAMING_FAILURE qualifies' rule would wrongly admit
    the FEWER_THAN_TWO_TOKENS near-empty case. The real implementation uses
    exact reason-tuple equality (_EMPTY_OBJECT_REASONS), which this proves by
    checking the newline body is excluded despite also being FRAMING_FAILURE."""
    raw = gzip.compress(b"\n")
    evaluation = admission.evaluate_schema_admission(raw)
    assert evaluation.recognition_disposition == recognizer.FRAMING_FAILURE
    assert evaluation.reasons != materializer._EMPTY_OBJECT_REASONS
    result = materializer.materialize_parser_a(raw, UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZATION_QUARANTINED


def test_r2_empty_observation_never_carries_schema_id_none():
    result = materializer.materialize_parser_a(gzip.compress(b""), UTC_DATE, INSTRUMENT)
    assert "schema_id" not in result.observation
    assert result.observation.get("schema_id", "ABSENT") == "ABSENT"


def test_r3_empty_observation_never_carries_unknown_schema_sentinel():
    result = materializer.materialize_parser_a(gzip.compress(b""), UTC_DATE, INSTRUMENT)
    assert "UNKNOWN_SCHEMA" not in result.observation.values()
    assert "schema_id" not in result.observation


def test_r4_record_and_observation_never_simultaneously_present():
    for build_raw in [_valid_object, lambda: gzip.compress(b""), _rpi_object]:
        result = materializer.materialize_parser_a(build_raw(), UTC_DATE, INSTRUMENT)
        assert not (result.record is not None and result.observation is not None)


def test_r5_is_valid_cannot_be_forced_by_a_caller_supplied_field():
    with pytest.raises(TypeError):
        materializer.MaterializationResult(
            status=materializer.EMPTY_OBJECT_OBSERVATION, parser="A", raw_object_sha256="a" * 64,
            is_valid=True,
        )


def test_r6_private_primitive_status_is_never_the_public_valid_wire_value():
    assert materializer.INTERNAL_PARSER_A_CANDIDATE != materializer.MATERIALIZED_VALID
    for build_raw in [_valid_object, _rpi_object]:
        direct = materializer._materialize_parser_a_unadmitted(build_raw(), UTC_DATE, INSTRUMENT)
        assert direct.status != materializer.MATERIALIZED_VALID
        assert direct.is_valid is False


def test_r7_schema_identity_mismatch_enforcement_is_present():
    evaluation = _admissible_evaluation("bybit_trade_v1")
    mismatched = {"schema_id": "bybit_trade_v1_rpi"}
    assert materializer._validate_admitted_record(mismatched, evaluation) != []


def test_r8_mechanical_completeness_alone_does_not_authorize_validity():
    raw = _rpi_object()
    candidate = materializer._materialize_parser_a_unadmitted(raw, UTC_DATE, INSTRUMENT)
    assert materializer.validate_daily_market_evidence_v1(candidate.record) == []  # mechanically complete
    result = materializer.materialize_parser_a(raw, UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZATION_QUARANTINED  # yet not authorized


def test_r9_admitted_validator_does_not_reopen_an_ambient_registry():
    source = inspect.getsource(materializer._validate_admitted_record)
    for forbidden in ("read_bytes", "REGISTRY", "json.loads", "Path("):
        assert forbidden not in source
    params = set(inspect.signature(materializer._validate_admitted_record).parameters)
    assert params == {"record", "evaluation"}


def test_r10_authority_mismatch_never_becomes_valid_or_escapes(monkeypatch):
    monkeypatch.setattr(materializer, "_load_default_result_algebra_bytes", lambda: b"{}")
    result = materializer.materialize_parser_a(_valid_object(), UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert result.is_valid is False

    items = [(_valid_object(), UTC_DATE, "x|A"), (_valid_object(), UTC_DATE, "x|B")]
    results = materializer.materialize_batch(items, materializer.materialize_parser_a)
    assert len(results) == 2, "authority mismatch must not batch-terminate"
    assert all(r.status == materializer.MATERIALIZATION_QUARANTINED for r in results)


def test_r11_byte_distinct_empty_objects_are_not_collapsed():
    x1, x2 = _empty_object(mtime=0), _empty_object(mtime=42)
    r1 = materializer.materialize_parser_a(x1, UTC_DATE, INSTRUMENT)
    r2 = materializer.materialize_parser_a(x2, UTC_DATE, INSTRUMENT)
    assert r1.observation["source_object_sha256"] != r2.observation["source_object_sha256"]


def test_r12_near_empty_newline_body_cannot_enter_observation_branch():
    result = materializer.materialize_parser_a(gzip.compress(b"\n"), UTC_DATE, INSTRUMENT)
    assert result.status != materializer.EMPTY_OBJECT_OBSERVATION
