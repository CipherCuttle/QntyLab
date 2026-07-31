"""Conformance model for the unfrozen R1 schema-admission candidate.

Admission is deliberately tested as a semantic contract, not wired runtime:
frozen recognition produces schema identity; frozen scope authorizes it.
"""
import gzip
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from qntylab import r1_schema_recognizer as recognizer


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "experiments/data"
AMENDMENT = DATA / "r1_daily_market_evidence_schema_admission_amendment_v1.json"
CONTRACT = DATA / "r1_normalized_evidence_contract_v1.json"
REGISTRY = DATA / "r1_source_schema_registry_v1.json"
RECOGNITION = DATA / "r1_source_structure_recognition_amendment_v1.json"
SCOPE = DATA / "r1_source_schema_registry_scope_amendment_v1.json"
PARSER_A = ROOT / "qntylab/r1_reference_parser.py"
PARSER_B = ROOT / "qntylab/r1_retention_candidate.py"

ADMISSIBLE = "SCHEMA_ADMISSIBLE"
INADMISSIBLE = "SCHEMA_INADMISSIBLE"
AUTHORIZED = "AUTHORIZED_FOR_DAILYMARKET"
NOT_AUTHORIZED = "NOT_AUTHORIZED_FOR_DAILYMARKET"


def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _semantic_hash(value):
    return _hash(_canonical(value))


def _raw(header):
    return gzip.compress((header + "\nrow\n").encode())


def _registry_snapshot(registry_bytes=None):
    registry_bytes = registry_bytes or REGISTRY.read_bytes()
    return recognizer.VerifiedRegistrySnapshot.from_exact_artifact_bytes(registry_bytes, _hash(registry_bytes))


@dataclass(frozen=True)
class RecognitionReceipt:
    source_object_sha256: str
    recognition_contract_sha256: str
    registry_snapshot_sha256: str
    disposition: str
    schema_id: str | None


@dataclass(frozen=True)
class Admission:
    schema_id: str | None
    disposition: str


def _recognized(raw_bytes, snapshot=None):
    snapshot = snapshot or _registry_snapshot()
    result = recognizer.recognize_source_object(raw_bytes, snapshot)
    return RecognitionReceipt(
        _hash(raw_bytes), _hash(RECOGNITION.read_bytes()), snapshot.registry_snapshot_sha256,
        result.disposition, result.schema_id,
    )


def _candidate():
    return json.loads(AMENDMENT.read_bytes())


def _scope():
    return json.loads(SCOPE.read_bytes())


def _verify_candidate_authorities():
    candidate = _candidate()
    bound = candidate["bound_authority"]
    assert _semantic_hash(candidate["semantic_body"]) == candidate["amendment_semantic_content_sha256"]
    assert _semantic_hash(candidate["effective_combined_contract_binding"]) == candidate["effective_combined_contract_binding_sha256"]
    exact = {
        "base_contract_sha256": CONTRACT.read_bytes(),
        "base_registry_sha256": REGISTRY.read_bytes(),
        "frozen_source_structure_recognition_amendment_sha256": RECOGNITION.read_bytes(),
        "frozen_source_schema_registry_scope_amendment_sha256": SCOPE.read_bytes(),
    }
    for field, payload in exact.items():
        if _hash(payload) != bound[field]:
            raise ValueError(f"candidate {field} mismatch")
    recognition = json.loads(RECOGNITION.read_bytes())
    scope = _scope()
    assert recognition["amendment_semantic_content_sha256"] == bound["frozen_source_structure_recognition_semantic_sha256"]
    assert recognition["effective_combined_contract_binding_sha256"] == bound["frozen_source_structure_recognition_effective_binding_sha256"]
    assert scope["amendment_semantic_content_sha256"] == bound["frozen_source_schema_registry_scope_semantic_sha256"]
    assert scope["effective_combined_contract_binding_sha256"] == bound["frozen_source_schema_registry_scope_effective_binding_sha256"]
    return candidate


def _scope_authorization(schema_id, registry_bytes):
    """Frozen scope semantics: exact R plus explicit matrix, otherwise deny."""
    scope = _scope()
    if _hash(registry_bytes) != scope["bound_authority"]["base_registry_sha256"]:
        raise ValueError("frozen scope registry binding mismatch")
    if _semantic_hash(scope["semantic_body"]) != scope["amendment_semantic_content_sha256"]:
        raise ValueError("frozen scope semantic binding mismatch")
    if _semantic_hash(scope["effective_combined_contract_binding"]) != scope["effective_combined_contract_binding_sha256"]:
        raise ValueError("frozen scope effective binding mismatch")
    known = json.loads(registry_bytes)["known_schema_variants"]
    if schema_id not in known:
        return NOT_AUTHORIZED
    entry = scope["semantic_body"]["structural_authorization_matrix"].get(schema_id)
    return entry["daily_market_authorization"] if entry else NOT_AUTHORIZED


def admit(receipt, source_object_sha256, registry_bytes=None):
    """The candidate's only schema input is a frozen-G recognition output."""
    candidate = _verify_candidate_authorities()
    if receipt.source_object_sha256 != source_object_sha256:
        raise ValueError("recognition X binding mismatch")
    registry_bytes = registry_bytes or REGISTRY.read_bytes()
    if _hash(registry_bytes) != candidate["bound_authority"]["base_registry_sha256"]:
        raise ValueError("candidate registry binding mismatch")
    if receipt.recognition_contract_sha256 != candidate["bound_authority"]["frozen_source_structure_recognition_amendment_sha256"]:
        raise ValueError("recognition G binding mismatch")
    if receipt.registry_snapshot_sha256 != _hash(registry_bytes):
        raise ValueError("recognition R binding mismatch")
    if receipt.disposition != recognizer.RECOGNIZED or receipt.schema_id is None:
        return Admission(receipt.schema_id, INADMISSIBLE)
    known = json.loads(registry_bytes)["known_schema_variants"]
    if receipt.schema_id not in known:
        return Admission(receipt.schema_id, INADMISSIBLE)
    if _scope_authorization(receipt.schema_id, registry_bytes) != AUTHORIZED:
        return Admission(receipt.schema_id, INADMISSIBLE)
    return Admission(receipt.schema_id, ADMISSIBLE)


def test_candidate_is_unfrozen_and_binds_exact_frozen_authorities():
    candidate = _verify_candidate_authorities()
    assert candidate["status"] == "CANDIDATE_NOT_YET_FROZEN"
    assert candidate["self_freeze_authorized"] is False
    assert candidate["artifact_kind"] == "PROTOCOL_AMENDMENT_CANDIDATE"
    assert candidate["bound_authority"]["base_registry_sha256"] == _hash(REGISTRY.read_bytes())


def test_authority_hashes_and_scope_matrix_match_disk():
    recognition, scope = json.loads(RECOGNITION.read_bytes()), _scope()
    assert recognition["status"] == scope["status"] == "FROZEN"
    assert recognition["amendment_semantic_content_sha256"] == "9a919ec68af8cee6caf661286315b61dd104d61c070676a75bfe89448c7e9758"
    assert recognition["effective_combined_contract_binding_sha256"] == "222b5edcb7370accd73526a034bf129f537a9cb5aac4b8ad157399d32899662c"
    assert scope["amendment_semantic_content_sha256"] == "f1645ce186c73232bb5e4945f734f2ea1c94db856255da0332272bedacd87571"
    assert scope["effective_combined_contract_binding_sha256"] == "3291c33ff0d4d33a1b9f43938c832bc6d0ba32e0c45b3628a80dc55e1c155ac0"
    assert _hash(REGISTRY.read_bytes()) == "02d2a75cdaa3d53a2708d2d20d5bf19f934fc68e6ee1b942404994d80ab94c4d"
    matrix = scope["semantic_body"]["structural_authorization_matrix"]
    assert matrix["bybit_trade_v1"]["daily_market_authorization"] == AUTHORIZED
    for schema_id in ("bybit_trade_v1_rpi", "tardis_derivative_ticker_v1", "bybit_instruments_info_current_v1"):
        assert matrix[schema_id]["daily_market_authorization"] == NOT_AUTHORIZED


def test_a1_authorized_recognized_schema_passes():
    fields = json.loads(REGISTRY.read_bytes())["known_schema_variants"]["bybit_trade_v1"]["field_set"]
    receipt = _recognized(_raw(",".join(fields)))
    assert receipt.disposition == recognizer.RECOGNIZED and receipt.schema_id == "bybit_trade_v1"
    assert admit(receipt, receipt.source_object_sha256).disposition == ADMISSIBLE


@pytest.mark.parametrize("schema_id", ["bybit_trade_v1_rpi", "tardis_derivative_ticker_v1", "bybit_instruments_info_current_v1"])
def test_a2_to_a4_registered_but_scope_unauthorized_is_inadmissible(schema_id):
    fields = json.loads(REGISTRY.read_bytes())["known_schema_variants"][schema_id]["field_set"]
    receipt = _recognized(_raw(",".join(fields)))
    assert receipt.disposition == recognizer.RECOGNIZED and receipt.schema_id == schema_id
    assert _scope_authorization(schema_id, REGISTRY.read_bytes()) == NOT_AUTHORIZED
    assert admit(receipt, receipt.source_object_sha256).disposition == INADMISSIBLE


def test_a5_and_a6_unlisted_or_caller_substituted_schema_cannot_pass():
    receipt = _recognized(_raw("not,a,registered,header"))
    assert receipt.disposition == recognizer.NO_MATCH
    assert admit(receipt, receipt.source_object_sha256).disposition == INADMISSIBLE
    forged = RecognitionReceipt(receipt.source_object_sha256, receipt.recognition_contract_sha256,
                                receipt.registry_snapshot_sha256, recognizer.NO_MATCH, "bybit_trade_v1")
    assert admit(forged, forged.source_object_sha256).disposition == INADMISSIBLE
    future = RecognitionReceipt("a" * 64, _hash(RECOGNITION.read_bytes()), _hash(REGISTRY.read_bytes()),
                                recognizer.RECOGNIZED, "future_schema")
    assert admit(future, future.source_object_sha256).disposition == INADMISSIBLE
    with pytest.raises(ValueError, match="recognition X binding mismatch"):
        admit(forged, "b" * 64)


def test_a7_ambiguous_cannot_become_first_match():
    variants = json.loads(REGISTRY.read_bytes())["known_schema_variants"]
    custom = dict(variants)
    custom["collision"] = dict(custom["bybit_trade_v1"])
    payload = _canonical({"known_schema_variants": custom})
    snapshot = _registry_snapshot(payload)
    raw = _raw(",".join(custom["bybit_trade_v1"]["field_set"]))
    result = recognizer.recognize_source_object(raw, snapshot)
    assert result.disposition == recognizer.AMBIGUOUS
    receipt = RecognitionReceipt(_hash(raw), _hash(RECOGNITION.read_bytes()), snapshot.registry_snapshot_sha256,
                                 result.disposition, result.schema_id)
    with pytest.raises(ValueError, match="registry binding mismatch"):
        admit(receipt, receipt.source_object_sha256, payload)


def test_a8_a9_exact_r_or_frozen_scope_mismatch_fails_closed(monkeypatch):
    receipt = _recognized(_raw("not,a,registered,header"))
    bad_r = RecognitionReceipt(receipt.source_object_sha256, receipt.recognition_contract_sha256,
                               "0" * 64, receipt.disposition, receipt.schema_id)
    with pytest.raises(ValueError, match="recognition R binding mismatch"):
        admit(bad_r, bad_r.source_object_sha256)
    mutated = _scope()
    mutated["semantic_body"]["structural_authorization_matrix"]["bybit_trade_v1"]["daily_market_authorization"] = NOT_AUTHORIZED
    monkeypatch.setattr(sys.modules[__name__], "_scope", lambda: mutated)
    with pytest.raises(ValueError, match="frozen scope semantic binding mismatch"):
        _scope_authorization("bybit_trade_v1", REGISTRY.read_bytes())


def test_a10_ordering_changes_recognition_neither_semantics_nor_first_match():
    registry = json.loads(REGISTRY.read_bytes())
    reversed_variants = dict(reversed(list(registry["known_schema_variants"].items())))
    reordered = _canonical({**registry, "known_schema_variants": reversed_variants})
    fields = registry["known_schema_variants"]["bybit_trade_v1"]["field_set"]
    assert recognizer.recognize_source_object(_raw(",".join(fields)), _registry_snapshot()).schema_id == "bybit_trade_v1"
    assert recognizer.recognize_source_object(_raw(",".join(fields)), _registry_snapshot(reordered)).schema_id == "bybit_trade_v1"
    assert _hash(reordered) != _hash(REGISTRY.read_bytes())  # it cannot masquerade as frozen R1


def test_a11_explicit_scope_authority_not_ambient_state(monkeypatch):
    receipt = _recognized(_raw(",".join(json.loads(REGISTRY.read_bytes())["known_schema_variants"]["bybit_trade_v1"]["field_set"])))
    assert admit(receipt, receipt.source_object_sha256).disposition == ADMISSIBLE
    altered = _scope()
    altered["semantic_body"]["structural_authorization_matrix"]["bybit_trade_v1"]["daily_market_authorization"] = NOT_AUTHORIZED
    monkeypatch.setattr(sys.modules[__name__], "_scope", lambda: altered)
    with pytest.raises(ValueError, match="frozen scope semantic binding mismatch"):
        admit(receipt, receipt.source_object_sha256)


@pytest.mark.parametrize("header", ["a", "a,,b", "a,b,a", '"a",b', "not,a,registered,header"])
def test_failure_results_are_never_admissible(header):
    receipt = _recognized(_raw(header))
    assert receipt.disposition in {recognizer.FRAMING_FAILURE, recognizer.MALFORMED_HEADER, recognizer.NO_MATCH}
    assert admit(receipt, receipt.source_object_sha256).disposition == INADMISSIBLE


def test_empty_object_has_no_fabricated_schema_authorization():
    receipt = _recognized(gzip.compress(b""))
    assert receipt.disposition == recognizer.FRAMING_FAILURE
    assert receipt.schema_id is None
    assert admit(receipt, receipt.source_object_sha256).disposition == INADMISSIBLE


def test_parser_status_snapshots_match_current_module_bytes():
    parser = _candidate()["semantic_body"]["parser_status"]
    assert _hash(PARSER_A.read_bytes()) == parser["parser_a_current"]["current_sha256"]
    assert _hash(PARSER_B.read_bytes()) == parser["parser_b_current"]["current_sha256"]
    rebind = next(item["parser_a_rebind"] for item in _candidate()["repair_history"] if "parser_a_rebind" in item)
    assert rebind["old_sha256"] == "76bfd763afbce1167ff931b912c7bb12e6c90e4b07d9ef862f6400e14a63823e"
    assert rebind["new_sha256"] == parser["parser_a_current"]["current_sha256"]


def test_candidate_does_not_claim_runtime_wiring_or_h001_semantics():
    text = json.dumps(_candidate()["semantic_body"], sort_keys=True)
    assert "does not claim that runtime persisted recognition/admission receipt transport exists" in text
    assert "H001" not in text
    assert "first-match" in text
