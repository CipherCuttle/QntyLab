"""Parser A conformance regression suite for the frozen-G recognition repair.

Verifies that qntylab.r1_reference_parser.parse_daily_object now delegates
X->H->S recognition entirely to qntylab.r1_schema_recognizer (frozen G, bound
to experiments/data/r1_source_structure_recognition_amendment_v1.json) rather
than independently deciding gzip framing, header well-formedness, or schema
matching. Each fixture below is triangulated against frozen G's own
disposition (as pinned in tests/test_r1_schema_recognizer.py) and Parser A's
mapped legacy outcome.

This file is additive: it does not modify tests/test_r1_reference_parser.py's
existing coverage, qntylab/r1_schema_recognizer.py, or
qntylab/r1_retention_candidate.py (Parser B, deliberately left unrepaired and
out of scope for this task).
"""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from qntylab import r1_reference_parser as rp
from qntylab import r1_schema_recognizer as recognizer

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "experiments/data/r1_source_schema_registry_v1.json"
REGISTRY_BYTES = REGISTRY_PATH.read_bytes()
REGISTRY_HASH = hashlib.sha256(REGISTRY_BYTES).hexdigest()

BASE_HEADER = "timestamp,symbol,side,size,price,tickDirection,trdMatchID,grossValue,homeNotional,foreignNotional"


def _gz(text: str | bytes) -> bytes:
    data = text if isinstance(text, bytes) else text.encode("utf-8")
    return gzip.compress(data)


def _row(ts="1700000000.000", size="1", price="100", trdid="id-1", side="Buy", tick="PlusTick"):
    gross = float(size) * float(price) * 1e8
    return f"{ts},TESTUSDT,{side},{size},{price},{tick},{trdid},{gross},{size},{float(size) * float(price)}"


def _custom_snapshot(known_schema_variants: dict) -> "recognizer.VerifiedRegistrySnapshot":
    payload = json.dumps({"known_schema_variants": known_schema_variants}).encode("utf-8")
    return recognizer.VerifiedRegistrySnapshot.from_exact_artifact_bytes(
        payload, hashlib.sha256(payload).hexdigest()
    )


# --- registry binding identity ------------------------------------------

def test_recognition_binding_mode_is_explicitly_r1_bound_not_general():
    """S5 red-team: Parser A must not claim general historical-snapshot
    replay capability it doesn't possess."""
    assert rp.RECOGNITION_BINDING_MODE == "EXPLICITLY_R1_BOUND"


def test_default_registry_matches_frozen_amendment_binding():
    assert REGISTRY_HASH == rp._R1_REGISTRY_EXPECTED_SHA256


# --- positive fixtures ---------------------------------------------------

def test_reordered_rpi_header_still_recognized():
    header = "symbol,timestamp,price,size,side,tickDirection,trdMatchID,grossValue,homeNotional,foreignNotional,RPI"
    row = "TESTUSDT,1700000000.000,100,1,Buy,PlusTick,id-1,1e8,1,100,42"
    result = rp.parse_daily_object(_gz(header + "\n" + row + "\n"), date(2023, 11, 14), "x")
    assert result.status == rp.STATUS_OK
    assert result.schema_id == "bybit_trade_v1_rpi"


# --- framing red team (section 14) ---------------------------------------

def test_truncated_gzip_member_raises_gzip_corruption():
    complete = _gz(BASE_HEADER + "\n" + _row() + "\n")
    with pytest.raises(rp.GzipCorruptionError):
        rp.parse_daily_object(complete[:-1], date(2023, 11, 14), "x")


def test_bad_trailer_raises_gzip_corruption():
    complete = _gz(BASE_HEADER + "\n" + _row() + "\n")
    corrupted = complete[:-1] + bytes([complete[-1] ^ 0xFF])
    with pytest.raises(rp.GzipCorruptionError):
        rp.parse_daily_object(corrupted, date(2023, 11, 14), "x")


def test_concatenated_gzip_members_raises_gzip_corruption():
    raw = _gz(BASE_HEADER + "\n" + _row() + "\n") + _gz("x,y\n")
    with pytest.raises(rp.GzipCorruptionError):
        rp.parse_daily_object(raw, date(2023, 11, 14), "x")


def test_trailing_garbage_after_gzip_member_raises_gzip_corruption():
    raw = _gz(BASE_HEADER + "\n" + _row() + "\n") + b"trailing-garbage"
    with pytest.raises(rp.GzipCorruptionError):
        rp.parse_daily_object(raw, date(2023, 11, 14), "x")


def test_invalid_utf8_body_raises_unicode_decode_error():
    raw = _gz(b"\xff,field\nrow\n")
    with pytest.raises(UnicodeDecodeError):
        rp.parse_daily_object(raw, date(2023, 11, 14), "x")


def test_bom_prefix_raises_gzip_corruption():
    raw = _gz(b"\xef\xbb\xbf" + BASE_HEADER.encode() + b"\n" + _row().encode() + b"\n")
    with pytest.raises(rp.GzipCorruptionError):
        rp.parse_daily_object(raw, date(2023, 11, 14), "x")


def test_crlf_header_line_raises_gzip_corruption():
    raw = _gz((BASE_HEADER + "\r\n" + _row() + "\n"))
    with pytest.raises(rp.GzipCorruptionError):
        rp.parse_daily_object(raw, date(2023, 11, 14), "x")


def test_one_token_header_raises_truncated_csv():
    with pytest.raises(rp.TruncatedCSVError):
        rp.parse_daily_object(_gz("single\n"), date(2023, 11, 14), "x")


# --- header well-formedness -----------------------------------------------

def test_quoted_header_token_is_malformed_header():
    raw = _gz('"timestamp",symbol\n')
    result = rp.parse_daily_object(raw, date(2023, 11, 14), "x")
    assert result.status == rp.STATUS_MALFORMED_HEADER_QUARANTINE
    assert result.record is None
    assert result.schema_id is None
    assert "QUOTE_CHARACTER_IN_TOKEN" in result.diagnostics["malformed_header_reasons"]


def test_empty_header_token_is_malformed_header():
    raw = _gz("a,,b\n")
    result = rp.parse_daily_object(raw, date(2023, 11, 14), "x")
    assert result.status == rp.STATUS_MALFORMED_HEADER_QUARANTINE
    assert "EMPTY_TOKEN_NAME" in result.diagnostics["malformed_header_reasons"]


def test_duplicate_header_token_is_malformed_header():
    """The concrete, reachable countermodel: a valid, complete 10-column
    bybit_trade_v1 header with one existing field name appended a second
    time still equals the registered 10-element set under naive frozenset
    equality -- this is exactly the reachable gap A2 (identify_schema's
    frozenset-based collapse) that this repair closes by delegating
    well-formedness to frozen G, which checks DUPLICATE_TOKEN_NAME before
    any set-equality matching occurs."""
    header = BASE_HEADER + ",timestamp"  # 11 physical tokens, duplicate "timestamp"
    raw = _gz(header + "\n" + _row() + ",extra\n")
    result = rp.parse_daily_object(raw, date(2023, 11, 14), "x")
    assert result.status == rp.STATUS_MALFORMED_HEADER_QUARANTINE
    assert result.record is None
    assert "DUPLICATE_TOKEN_NAME" in result.diagnostics["malformed_header_reasons"]


def test_case_mutated_header_is_no_match_not_malformed():
    header = BASE_HEADER.replace("timestamp", "Timestamp")
    raw = _gz(header + "\n" + _row() + "\n")
    result = rp.parse_daily_object(raw, date(2023, 11, 14), "x")
    assert result.status == rp.STATUS_UNKNOWN_SCHEMA_QUARANTINE


def test_whitespace_padded_header_token_is_no_match_not_malformed():
    header = BASE_HEADER.replace("timestamp", " timestamp")
    raw = _gz(header + "\n" + _row() + "\n")
    result = rp.parse_daily_object(raw, date(2023, 11, 14), "x")
    assert result.status == rp.STATUS_UNKNOWN_SCHEMA_QUARANTINE


def test_extra_unknown_field_is_no_match():
    header = BASE_HEADER + ",extraField"
    raw = _gz(header + "\n" + _row() + ",zzz\n")
    result = rp.parse_daily_object(raw, date(2023, 11, 14), "x")
    assert result.status == rp.STATUS_UNKNOWN_SCHEMA_QUARANTINE


def test_missing_field_is_no_match():
    header = ",".join(BASE_HEADER.split(",")[:-1])  # drop foreignNotional
    raw = _gz(header + "\nrow\n")
    result = rp.parse_daily_object(raw, date(2023, 11, 14), "x")
    assert result.status == rp.STATUS_UNKNOWN_SCHEMA_QUARANTINE


# --- component-scope handling (recognized but Parser-A-unsupported) ------

def test_structurally_recognized_but_unsupported_schema_tardis():
    registry = json.loads(REGISTRY_BYTES)
    field_set = registry["known_schema_variants"]["tardis_derivative_ticker_v1"]["field_set"]
    raw = _gz(",".join(field_set) + "\n" + ",".join("v" for _ in field_set) + "\n")
    result = rp.parse_daily_object(raw, date(2023, 11, 14), "x")
    assert result.status == rp.STATUS_RECOGNIZED_UNSUPPORTED_SCHEMA_QUARANTINE
    assert result.schema_id == "tardis_derivative_ticker_v1"
    assert result.record is None


def test_structurally_recognized_but_unsupported_schema_instruments_info():
    registry = json.loads(REGISTRY_BYTES)
    field_set = registry["known_schema_variants"]["bybit_instruments_info_current_v1"]["field_set"]
    raw = _gz(",".join(field_set) + "\n" + ",".join("v" for _ in field_set) + "\n")
    result = rp.parse_daily_object(raw, date(2023, 11, 14), "x")
    assert result.status == rp.STATUS_RECOGNIZED_UNSUPPORTED_SCHEMA_QUARANTINE
    assert result.schema_id == "bybit_instruments_info_current_v1"
    assert result.record is None


# --- snapshot model / red team (section 13) -------------------------------

def test_s1_local_hardcoded_table_cannot_determine_recognition(monkeypatch):
    """S1: even if the frozen recognizer is forced to always say NO_MATCH,
    Parser A must not fall back to its own KNOWN_SCHEMA_COLUMNS/identify_schema
    to still produce a schema_id. Proves the live path holds no independent
    recognition authority."""
    def _always_no_match(raw_bytes, snapshot):
        return recognizer.RecognitionResult(recognizer.NO_MATCH)

    monkeypatch.setattr(rp.recognizer, "recognize_source_object", _always_no_match)
    raw = _gz(BASE_HEADER + "\n" + _row() + "\n")  # a header KNOWN_SCHEMA_COLUMNS would match
    result = rp.parse_daily_object(raw, date(2023, 11, 14), "x")
    assert result.status == rp.STATUS_UNKNOWN_SCHEMA_QUARANTINE
    assert result.schema_id is None


def test_s2_s6_tampered_registry_bytes_fail_closed_even_when_omitted(monkeypatch, tmp_path):
    """S2/S6: if the on-disk registry bytes do not match the pinned expected
    sha256, the default loader must fail closed -- never silently use
    whatever bytes are present, and never silently fall back to unverified
    ambient state merely because the caller omitted registry_snapshot."""
    tampered = tmp_path / "tampered_registry.json"
    tampered.write_bytes(REGISTRY_BYTES + b" ")  # any byte change invalidates the pin
    monkeypatch.setattr(rp, "_R1_REGISTRY_ARTIFACT_PATH", tampered)
    monkeypatch.setattr(rp, "_r1_default_registry_snapshot", None)
    with pytest.raises(ValueError):
        rp.parse_daily_object(_gz(BASE_HEADER + "\n" + _row() + "\n"), date(2023, 11, 14), "x")


def test_s3_registry_key_ordering_does_not_change_recognition():
    variants = json.loads(REGISTRY_BYTES)["known_schema_variants"]
    forward = _custom_snapshot(variants)
    reordered = _custom_snapshot(dict(reversed(list(variants.items()))))

    raw = _gz(BASE_HEADER + "\n" + _row() + "\n")
    r_forward = rp.parse_daily_object(raw, date(2023, 11, 14), "x", registry_snapshot=forward)
    r_reordered = rp.parse_daily_object(raw, date(2023, 11, 14), "x", registry_snapshot=reordered)
    assert r_forward.schema_id == r_reordered.schema_id == "bybit_trade_v1"


def test_s4_synthetic_signature_collision_is_ambiguous_not_first_match():
    """S4: a synthetic registry where two schema_ids share an identical
    field_set must yield AMBIGUOUS naming both ids, never a first-match
    RECOGNIZED that depends on dict iteration order."""
    variants = json.loads(REGISTRY_BYTES)["known_schema_variants"]
    collided = dict(variants)
    collided["bybit_trade_v1_collision_twin"] = {
        "field_set": list(variants["bybit_trade_v1"]["field_set"])
    }
    snapshot = _custom_snapshot(collided)
    raw = _gz(BASE_HEADER + "\n" + _row() + "\n")
    result = rp.parse_daily_object(raw, date(2023, 11, 14), "x", registry_snapshot=snapshot)
    assert result.status == rp.STATUS_AMBIGUOUS_SCHEMA_QUARANTINE
    assert result.record is None
    assert set(result.diagnostics["matching_schema_ids"]) == {"bybit_trade_v1", "bybit_trade_v1_collision_twin"}


def test_registry_identity_mismatch_in_explicit_injection_fails_closed():
    with pytest.raises(ValueError):
        recognizer.VerifiedRegistrySnapshot.from_exact_artifact_bytes(REGISTRY_BYTES, "0" * 64)
