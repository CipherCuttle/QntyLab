"""Black-box conformance tests derived from frozen G and exact R only."""

from __future__ import annotations

import gzip
import hashlib
import json
from itertools import permutations
from pathlib import Path

import pytest

from qntylab.r1_schema_recognizer import (
    AMBIGUOUS,
    FRAMING_FAILURE,
    MALFORMED_HEADER,
    NO_MATCH,
    RECOGNIZED,
    VerifiedRegistrySnapshot,
    recognize_source_object,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_BYTES = (REPO_ROOT / "experiments/data/r1_source_schema_registry_v1.json").read_bytes()
REGISTRY_HASH = hashlib.sha256(REGISTRY_BYTES).hexdigest()


def snapshot(registry_bytes: bytes = REGISTRY_BYTES) -> VerifiedRegistrySnapshot:
    return VerifiedRegistrySnapshot.from_exact_artifact_bytes(
        registry_bytes, hashlib.sha256(registry_bytes).hexdigest()
    )


def object_for(header: str | bytes) -> bytes:
    return gzip.compress(header if isinstance(header, bytes) else header.encode())


def header_for(schema_id: str) -> list[str]:
    return json.loads(REGISTRY_BYTES)["known_schema_variants"][schema_id]["field_set"]


@pytest.mark.parametrize(
    ("fixture_id", "raw", "disposition", "reason", "schema_id"),
    [
        ("empty_raw_object", b"", FRAMING_FAILURE, "INVALID_GZIP", None),
        ("empty_gzip_payload", object_for(b""), FRAMING_FAILURE, "EMPTY_OBJECT", None),
        ("truncated_member", object_for("timestamp,symbol\n")[:-1], FRAMING_FAILURE, "INVALID_GZIP", None),
        ("bad_trailer", object_for("timestamp,symbol\n")[:-1] + b"x", FRAMING_FAILURE, "INVALID_GZIP", None),
        ("concatenated_members", object_for("timestamp,symbol\n") + object_for("x,y\n"), FRAMING_FAILURE, "MULTI_MEMBER_GZIP", None),
        ("trailing_garbage", object_for("timestamp,symbol\n") + b"trailing", FRAMING_FAILURE, "MULTI_MEMBER_GZIP", None),
        ("invalid_utf8", object_for(b"\xff,field\n"), FRAMING_FAILURE, "INVALID_UTF8", None),
        ("bom", object_for(b"\xef\xbb\xbfa,b\n"), FRAMING_FAILURE, "BOM_PRESENT", None),
        ("cr_header", object_for("a,b\r\n"), FRAMING_FAILURE, "NON_LF_LINE_TERMINATOR", None),
        ("quoted_header", object_for('"a",b\n'), MALFORMED_HEADER, "QUOTE_CHARACTER_IN_TOKEN", None),
        ("one_token", object_for("single\n"), FRAMING_FAILURE, "FEWER_THAN_TWO_TOKENS", None),
        ("empty_token", object_for("a,,b\n"), MALFORMED_HEADER, "EMPTY_TOKEN_NAME", None),
        ("duplicate_token", object_for("a,a\n"), MALFORMED_HEADER, "DUPLICATE_TOKEN_NAME", None),
        ("multiple_malformed", object_for('a,,a,a"\n'), MALFORMED_HEADER, "EMPTY_TOKEN_NAME", None),
        ("unknown_well_formed", object_for("unknown,fields\n"), NO_MATCH, None, None),
        ("bybit_trade_v1", object_for(",".join(header_for("bybit_trade_v1")) + "\n"), RECOGNIZED, None, "bybit_trade_v1"),
        ("bybit_trade_v1_rpi", object_for(",".join(header_for("bybit_trade_v1_rpi")) + "\n"), RECOGNIZED, None, "bybit_trade_v1_rpi"),
        ("tardis_derivative_ticker_v1", object_for(",".join(header_for("tardis_derivative_ticker_v1")) + "\n"), RECOGNIZED, None, "tardis_derivative_ticker_v1"),
        ("bybit_instruments_info_current_v1", object_for(",".join(header_for("bybit_instruments_info_current_v1")) + "\n"), RECOGNIZED, None, "bybit_instruments_info_current_v1"),
    ],
)
def test_frozen_g_conformance_vectors(fixture_id, raw, disposition, reason, schema_id):
    result = recognize_source_object(raw, snapshot())
    assert result.disposition == disposition, fixture_id
    if reason:
        assert reason in result.reasons, fixture_id
    assert result.schema_id == schema_id, fixture_id


def test_all_malformed_reasons_are_reported_deterministically():
    first = recognize_source_object(object_for('a,,a,a"\n'), snapshot())
    second = recognize_source_object(object_for('a,,a,a"\n'), snapshot())
    assert set(first.reasons) == {
        "EMPTY_TOKEN_NAME",
        "DUPLICATE_TOKEN_NAME",
        "QUOTE_CHARACTER_IN_TOKEN",
    }
    assert first.reasons == second.reasons


@pytest.mark.parametrize("mutation", [lambda h: h.replace(",foreignNotional", ""), lambda h: h.replace("timestamp", "Timestamp"), lambda h: h.replace("timestamp", " timestamp")])
def test_exact_tokens_reject_missing_case_and_whitespace_mutations(mutation):
    header = ",".join(header_for("bybit_trade_v1")) + "\n"
    assert recognize_source_object(object_for(mutation(header)), snapshot()).disposition == NO_MATCH


def test_selected_header_permutations_are_recognition_invariant():
    header = header_for("bybit_trade_v1")
    expected = recognize_source_object(object_for(",".join(header) + "\n"), snapshot())
    for ordering in (header[::-1], header[1:] + header[:1], list(permutations(header[:3]))[4] + tuple(header[3:])):
        raw_header = ",".join(ordering) + "\n"
        assert recognize_source_object(object_for(raw_header), snapshot()) == expected


def test_registry_key_order_has_no_semantic_effect():
    registry = json.loads(REGISTRY_BYTES)
    items = list(registry["known_schema_variants"].items())
    registry["known_schema_variants"] = dict(reversed(items))
    reordered = (json.dumps(registry, sort_keys=False, separators=(",", ":")) + "\n").encode()
    raw = object_for(",".join(header_for("bybit_trade_v1")) + "\n")
    assert recognize_source_object(raw, snapshot(reordered)) == recognize_source_object(raw, snapshot())


def test_duplicate_registry_signature_is_ambiguous_not_first_match():
    registry = json.loads(REGISTRY_BYTES)
    registry["known_schema_variants"]["synthetic_duplicate"] = {
        "field_set": header_for("bybit_trade_v1")
    }
    duplicate_bytes = (json.dumps(registry, separators=(",", ":")) + "\n").encode()
    result = recognize_source_object(object_for(",".join(header_for("bybit_trade_v1")) + "\n"), snapshot(duplicate_bytes))
    assert result.disposition == AMBIGUOUS
    assert result.matching_schema_ids == ("bybit_trade_v1", "synthetic_duplicate")


def test_unrelated_future_schema_cannot_change_existing_unique_match():
    registry = json.loads(REGISTRY_BYTES)
    registry["known_schema_variants"]["future_unrelated"] = {"field_set": ["future", "only"]}
    changed = (json.dumps(registry, separators=(",", ":")) + "\n").encode()
    raw = object_for(",".join(header_for("bybit_trade_v1")) + "\n")
    assert recognize_source_object(raw, snapshot(changed)) == recognize_source_object(raw, snapshot())


def test_every_selected_proper_gzip_prefix_stops_before_recognition():
    complete = object_for(",".join(header_for("bybit_trade_v1")) + "\n")
    for index in (0, 1, 7, len(complete) // 2, len(complete) - 1):
        result = recognize_source_object(complete[:index], snapshot())
        assert result == type(result)(FRAMING_FAILURE, ("INVALID_GZIP",))


def test_snapshot_identity_is_exact_bytes_not_an_ambient_path_or_canonical_json():
    with pytest.raises(ValueError, match="selected registry snapshot"):
        VerifiedRegistrySnapshot.from_exact_artifact_bytes(REGISTRY_BYTES, "0" * 64)
