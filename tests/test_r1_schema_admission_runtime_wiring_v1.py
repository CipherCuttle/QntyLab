"""Runtime wiring: FROZEN R1 schema admission gating Parser-A materialization.

Covers the required test matrix (A-L) and the hostile red-team checklist
(R1-R10) for qntylab.r1_schema_admission + r1_daily_market_materializer.
materialize_admitted_parser_a, the first runtime integration of the frozen
schema-admission amendment (experiments/data/
r1_daily_market_evidence_schema_admission_amendment_v1.json).
"""
from __future__ import annotations

import gzip
import hashlib
import inspect
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from qntylab import r1_daily_market_materializer as materializer
from qntylab import r1_reference_parser as rp
from qntylab import r1_retention_candidate as rc
from qntylab import r1_schema_admission as admission
from qntylab import r1_schema_recognizer as recognizer

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "experiments/data"
REGISTRY = DATA / "r1_source_schema_registry_v1.json"
SCOPE = DATA / "r1_source_schema_registry_scope_amendment_v1.json"
ADMISSION_ARTIFACT = DATA / "r1_daily_market_evidence_schema_admission_amendment_v1.json"

INSTRUMENT = "BYBIT_PERP_TEST_INSTRUMENT_V1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _registry_fields(schema_id: str) -> list[str]:
    return json.loads(REGISTRY.read_bytes())["known_schema_variants"][schema_id]["field_set"]


def _raw_header_only(header: str) -> bytes:
    return gzip.compress((header + "\nrow\n").encode())


def _gzip(data: bytes, mtime: int) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=mtime, compresslevel=6) as f:
        f.write(data)
    return buf.getvalue()


BASE_HEADER = "timestamp,symbol,side,size,price,tickDirection,trdMatchID,grossValue,homeNotional,foreignNotional"
BASE_ROWS = (
    "1700000000.123,BTCUSDT,Buy,2,100.5,PlusTick,trade1,201.0,2,201.0\n"
    "1700000005.456,BTCUSDT,Sell,1,101.0,MinusTick,trade2,101.0,1,101.0\n"
)
BASE_CSV = (BASE_HEADER + "\n" + BASE_ROWS).encode()
BASE_UTC_DATE = date(2023, 11, 14)


def _raw_base_object() -> bytes:
    assert set(BASE_HEADER.split(",")) == set(_registry_fields("bybit_trade_v1"))
    return gzip.compress(BASE_CSV)


def _raw_rpi_object() -> bytes:
    fields = _registry_fields("bybit_trade_v1_rpi")
    return _raw_header_only(",".join(fields))


def _raw_unknown_object() -> bytes:
    return _raw_header_only("not,a,registered,header")


def _raw_malformed_object() -> bytes:
    # duplicate token name -> MALFORMED_HEADER
    return _raw_header_only("a,b,a")


def _raw_framing_failure_object() -> bytes:
    return b"this is not a valid gzip stream at all"


def _raw_empty_object() -> bytes:
    return gzip.compress(b"")


class _CallSpy:
    def __init__(self):
        self.calls: list[str] = []


@pytest.fixture()
def call_spy(monkeypatch):
    spy = _CallSpy()
    real_evaluate = admission.evaluate_schema_admission
    real_materialize_a = materializer.materialize_parser_a
    real_materialize_b = materializer.materialize_parser_b

    def spy_evaluate(*args, **kwargs):
        spy.calls.append("admission")
        return real_evaluate(*args, **kwargs)

    def spy_materialize_a(*args, **kwargs):
        spy.calls.append("parser_a")
        return real_materialize_a(*args, **kwargs)

    def spy_materialize_b(*args, **kwargs):
        spy.calls.append("parser_b")
        return real_materialize_b(*args, **kwargs)

    monkeypatch.setattr(materializer.admission, "evaluate_schema_admission", spy_evaluate)
    monkeypatch.setattr(materializer, "materialize_parser_a", spy_materialize_a)
    monkeypatch.setattr(materializer, "materialize_parser_b", spy_materialize_b)
    return spy


# --- A: authorized positive ------------------------------------------------

def test_a_authorized_base_object_admits_and_materializes(call_spy):
    raw = _raw_base_object()
    result = materializer.materialize_admitted_parser_a(raw, BASE_UTC_DATE, INSTRUMENT)
    assert result.is_valid
    assert result.parser == "A"
    assert result.record["schema_id"] == "bybit_trade_v1"
    assert result.record["trade_count"] == 2
    assert result.record["source_object_sha256"] == _sha256(raw)
    assert call_spy.calls == ["admission", "parser_a"]


# --- B: RPI recognized-but-unauthorized ------------------------------------

def test_b_rpi_recognized_but_not_authorized_blocks_materialization(call_spy):
    raw = _raw_rpi_object()

    # Prove RPI genuinely recognizes and that Parser A (run directly, bypassing
    # the gate) WOULD happily materialize it -- RPI is inside Parser A's own
    # row-semantics support scope. This is exactly why the gate, not Parser A
    # itself, must be the thing that stops it.
    direct = materializer.materialize_parser_a(raw, BASE_UTC_DATE, INSTRUMENT)
    assert direct.status == materializer.MATERIALIZED_VALID
    assert direct.record["schema_id"] == "bybit_trade_v1_rpi"
    call_spy.calls.clear()

    result = materializer.materialize_admitted_parser_a(raw, BASE_UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert result.record is None
    assert materializer.SCHEMA_INADMISSIBLE in result.anomalies
    assert "bybit_trade_v1_rpi" in result.reason
    assert call_spy.calls == ["admission"]  # parser_a never invoked


# --- C: NO_MATCH ------------------------------------------------------------

def test_c_no_match_blocks_materialization(call_spy):
    raw = _raw_unknown_object()
    result = materializer.materialize_admitted_parser_a(raw, BASE_UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert result.record is None
    assert materializer.SCHEMA_INADMISSIBLE in result.anomalies
    assert call_spy.calls == ["admission"]


# --- D: malformed header ----------------------------------------------------

def test_d_malformed_header_blocks_materialization(call_spy):
    raw = _raw_malformed_object()
    result = materializer.materialize_admitted_parser_a(raw, BASE_UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert result.record is None
    assert materializer.SCHEMA_INADMISSIBLE in result.anomalies
    assert call_spy.calls == ["admission"]


# --- E: framing failure ------------------------------------------------------

def test_e_framing_failure_blocks_materialization(call_spy):
    raw = _raw_framing_failure_object()
    result = materializer.materialize_admitted_parser_a(raw, BASE_UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert result.record is None
    assert materializer.SCHEMA_INADMISSIBLE in result.anomalies
    assert call_spy.calls == ["admission"]


# --- F: no interface/path exists to inject schema_id/disposition -----------

def test_f_no_recognition_shaped_admission_input_exists():
    params = set(inspect.signature(admission.evaluate_schema_admission).parameters)
    assert params == {
        "raw_bytes", "admission_bytes", "contract_bytes", "registry_bytes",
        "recognition_bytes", "scope_bytes",
    }
    for forbidden in ("disposition", "schema_id", "recognition_result", "receipt"):
        assert forbidden not in params

    params_gate = set(inspect.signature(materializer.materialize_admitted_parser_a).parameters)
    assert params_gate == {"raw_bytes", "expected_utc_date", "instrument_instance_id", "expected_raw_sha256"}
    for forbidden in ("disposition", "schema_id", "recognition_result", "receipt"):
        assert forbidden not in params_gate

    # Even an unregistered header cannot be admitted by any side channel.
    result = admission.evaluate_schema_admission(_raw_unknown_object())
    assert result.admission == admission.INADMISSIBLE
    assert result.schema_id is None


# --- G: exact registry mismatch fails closed --------------------------------

def test_g_wrong_registry_binding_fails_closed():
    mutated = json.loads(REGISTRY.read_bytes())
    mutated["known_schema_variants"]["bybit_trade_v1"]["field_set"].append("extra_field")
    mutated_bytes = json.dumps(mutated, sort_keys=True, separators=(",", ":")).encode()
    raw = _raw_base_object()
    with pytest.raises(ValueError, match="bound_authority.base_registry_sha256 mismatch"):
        admission.evaluate_schema_admission(raw, registry_bytes=mutated_bytes)


# --- H: frozen admission authority mismatch fails closed --------------------

def test_h_wrong_admission_artifact_bytes_fails_closed():
    raw = _raw_base_object()
    with pytest.raises((ValueError, json.JSONDecodeError)):
        admission.evaluate_schema_admission(raw, admission_bytes=b"not the frozen admission amendment bytes")


def test_h_tampered_but_valid_json_admission_artifact_fails_closed():
    tampered = json.loads(ADMISSION_ARTIFACT.read_bytes())
    tampered["semantic_body"]["schema_admission_rule"]["rule"] = "tampered"
    tampered_bytes = json.dumps(tampered).encode()
    raw = _raw_base_object()
    with pytest.raises(ValueError, match="schema admission semantic content mismatch"):
        admission.evaluate_schema_admission(raw, admission_bytes=tampered_bytes)


# --- I: scope mismatch fails closed -----------------------------------------

def test_i_wrong_scope_binding_fails_closed():
    mutated_scope = json.loads(SCOPE.read_bytes())
    mutated_scope["semantic_body"]["structural_authorization_matrix"]["bybit_trade_v1_rpi"]["daily_market_authorization"] = "AUTHORIZED_FOR_DAILYMARKET"
    mutated_bytes = json.dumps(mutated_scope).encode()
    raw = _raw_base_object()
    with pytest.raises(ValueError, match="mismatch"):
        admission.evaluate_schema_admission(raw, scope_bytes=mutated_bytes)


# --- J: deterministic replay -------------------------------------------------

def test_j_deterministic_replay_same_x_same_authorities():
    raw = _raw_base_object()
    first = admission.evaluate_schema_admission(raw)
    second = admission.evaluate_schema_admission(raw)
    assert first == second

    m1 = materializer.materialize_admitted_parser_a(raw, BASE_UTC_DATE, INSTRUMENT)
    m2 = materializer.materialize_admitted_parser_a(raw, BASE_UTC_DATE, INSTRUMENT)
    assert m1 == m2


# --- K: exact-X identity: logically-equivalent, byte-different X1/X2 --------

def test_k_byte_different_equivalent_content_objects_keep_separate_identity():
    x1 = _gzip(BASE_CSV, mtime=0)
    x2 = _gzip(BASE_CSV, mtime=1_600_000_000)
    assert x1 != x2
    assert _sha256(x1) != _sha256(x2)

    e1 = admission.evaluate_schema_admission(x1)
    e2 = admission.evaluate_schema_admission(x2)
    assert e1.source_object_sha256 == _sha256(x1)
    assert e2.source_object_sha256 == _sha256(x2)
    assert e1.source_object_sha256 != e2.source_object_sha256
    # Same logical content -> same disposition/schema_id/admission, distinct identity.
    assert e1.admission == e2.admission == admission.ADMISSIBLE
    assert e1.schema_id == e2.schema_id == "bybit_trade_v1"

    r1 = materializer.materialize_admitted_parser_a(x1, BASE_UTC_DATE, INSTRUMENT)
    r2 = materializer.materialize_admitted_parser_a(x2, BASE_UTC_DATE, INSTRUMENT)
    assert r1.record["source_object_sha256"] == _sha256(x1)
    assert r2.record["source_object_sha256"] == _sha256(x2)
    assert r1.record["source_object_sha256"] != r2.record["source_object_sha256"]


# --- L: downstream non-execution proof (all inadmissible cases) ------------

@pytest.mark.parametrize("build_raw", [
    _raw_rpi_object, _raw_unknown_object, _raw_malformed_object, _raw_framing_failure_object,
])
def test_l_inadmissible_cases_never_invoke_parser_a(build_raw, call_spy):
    raw = build_raw()
    result = materializer.materialize_admitted_parser_a(raw, BASE_UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert "parser_a" not in call_spy.calls
    assert "parser_b" not in call_spy.calls


# --- Hostile red-team R1-R10 -------------------------------------------------

def test_r1_admission_always_precedes_materialization(call_spy):
    materializer.materialize_admitted_parser_a(_raw_base_object(), BASE_UTC_DATE, INSTRUMENT)
    assert call_spy.calls.index("admission") < call_spy.calls.index("parser_a")


def test_r2_parser_a_success_cannot_override_admission_denial(call_spy):
    """RPI genuinely parses successfully under Parser A alone (test B), yet
    the admitted path must still deny it -- Parser A's own success is never
    consulted as an override for admission's decision."""
    raw = _raw_rpi_object()
    result = materializer.materialize_admitted_parser_a(raw, BASE_UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZATION_QUARANTINED
    assert "parser_a" not in call_spy.calls


def test_r3_rpi_cannot_reach_materialization():
    result = materializer.materialize_admitted_parser_a(_raw_rpi_object(), BASE_UTC_DATE, INSTRUMENT)
    assert result.record is None


def test_r4_caller_cannot_inject_schema_or_disposition():
    sig_admit = inspect.signature(admission.evaluate_schema_admission)
    sig_gate = inspect.signature(materializer.materialize_admitted_parser_a)
    for sig in (sig_admit, sig_gate):
        assert "schema_id" not in sig.parameters
        assert "disposition" not in sig.parameters
        assert "recognition_result" not in sig.parameters


def test_r5_x_admitted_is_exactly_x_parsed():
    raw = _raw_base_object()
    evaluation = admission.evaluate_schema_admission(raw)
    result = materializer.materialize_admitted_parser_a(raw, BASE_UTC_DATE, INSTRUMENT)
    assert evaluation.source_object_sha256 == result.record["source_object_sha256"] == _sha256(raw)


def test_r6_no_recency_or_latest_selector_only_exact_semantic_match():
    """The evaluator does not select 'whichever admission artifact is newest'
    or 'whatever is currently at this path' -- it verifies the exact semantic
    content hash of the one frozen value this module conforms to. A
    structurally valid, frozen-shaped candidate with different substantive
    content (e.g. a hypothetical later amendment) is rejected outright, never
    silently preferred as 'the current one'; the genuine frozen artifact
    (in whatever equivalent serialization) still works."""
    tampered = json.loads(ADMISSION_ARTIFACT.read_bytes())
    tampered["semantic_body"]["schema_admission_rule"]["rule"] += " AMENDED_LATER"
    tampered_bytes = json.dumps(tampered, sort_keys=True, separators=(",", ":")).encode()
    raw = _raw_base_object()
    with pytest.raises(ValueError, match="schema admission semantic content mismatch"):
        admission.evaluate_schema_admission(raw, admission_bytes=tampered_bytes)
    assert admission.evaluate_schema_admission(
        raw, admission_bytes=ADMISSION_ARTIFACT.read_bytes()
    ).admission == admission.ADMISSIBLE


def test_r7_wrong_r_or_scope_cannot_combine_with_valid_x():
    raw = _raw_base_object()
    with pytest.raises(ValueError):
        admission.evaluate_schema_admission(raw, registry_bytes=b"{}")
    with pytest.raises(ValueError):
        admission.evaluate_schema_admission(raw, scope_bytes=b"{}")


def test_r8_parser_b_never_acts_as_fallback(call_spy):
    for build_raw in (_raw_base_object, _raw_rpi_object, _raw_unknown_object, _raw_malformed_object):
        materializer.materialize_admitted_parser_a(build_raw(), BASE_UTC_DATE, INSTRUMENT)
    assert "parser_b" not in call_spy.calls
    assert "materialize_parser_b" not in inspect.getsource(materializer.materialize_admitted_parser_a)
    assert "daily_primitive" not in inspect.getsource(materializer.materialize_admitted_parser_a)


def test_r9_empty_object_gets_no_fabricated_schema_authorization():
    raw = _raw_empty_object()
    evaluation = admission.evaluate_schema_admission(raw)
    assert evaluation.recognition_disposition == recognizer.FRAMING_FAILURE
    assert "EMPTY_OBJECT" in evaluation.reasons
    assert evaluation.schema_id is None
    assert evaluation.admission == admission.INADMISSIBLE

    # The frozen carve-out lets Parser A's pre-existing zero-trade path run,
    # but it must never emit an authorized schema_id for it.
    result = materializer.materialize_admitted_parser_a(raw, BASE_UTC_DATE, INSTRUMENT)
    assert result.status == materializer.MATERIALIZED_VALID
    assert result.record["schema_id"] is None
    assert result.record["trade_count"] == 0


def test_r10_runtime_module_matches_frozen_artifact_bytes_exactly():
    """Guards against the runtime module silently drifting from, or
    redefining, the frozen authority it claims to implement."""
    def sha(b):
        return hashlib.sha256(b).hexdigest()

    def canon(v):
        return (json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()

    def semantic_sha(v):
        return sha(canon(v))

    candidate = json.loads(ADMISSION_ARTIFACT.read_bytes())
    assert semantic_sha(candidate["semantic_body"]) == admission._EXPECTED_ADMISSION_SEMANTIC_SHA256
    assert semantic_sha(candidate["effective_combined_contract_binding"]) == admission._EXPECTED_ADMISSION_EFFECTIVE_SHA256
    assert sha(REGISTRY.read_bytes()) == admission._EXPECTED_REGISTRY_SHA256
    assert candidate["status"] == "FROZEN"
    assert candidate["self_freeze_authorized"] is False


# --- Additional determinism / non-ambient sanity ----------------------------

def test_positive_replay_record_fields_are_fully_expected(call_spy):
    raw = _raw_base_object()
    result = materializer.materialize_admitted_parser_a(raw, BASE_UTC_DATE, INSTRUMENT)
    assert result.is_valid
    record = result.record
    assert record["instrument_instance_id"] == INSTRUMENT
    assert record["utc_date"] == BASE_UTC_DATE.isoformat()
    assert record["open"] == "100.5"
    assert record["close"] == "101.0"
    assert record["high"] == "101.0"
    assert record["low"] == "100.5"
    assert record["trade_count"] == 2
    assert record["duplicate_count"] == 0
    assert record["rejected_row_count"] == 0
    assert record["schema_id"] == "bybit_trade_v1"

    violations = materializer.validate_daily_market_evidence_v1(record)
    assert violations == []
