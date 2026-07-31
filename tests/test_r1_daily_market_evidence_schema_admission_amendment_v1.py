"""Conformance model for the unfrozen R1 schema-admission candidate.

Admission is deliberately tested as a semantic contract, not wired runtime:
schema admission derives recognition_result := recognize_G,R(X) directly from
the exact source-object bytes X being admitted, by applying frozen G to X and
exact R at evaluation time. No disposition, schema_id, or recognition-result/
receipt-shaped value is ever accepted as an admission input from outside that
derivation -- not even one whose X/G/R identity hashes are individually
correct. This closes BLOCK_FORGED_RECOGNITION_RESULT (repair_history
repair_index 5): a source object whose genuine recognition is NO_MATCH can no
longer be admitted by asserting disposition=RECOGNIZED with an otherwise
well-bound claim, because there is no admission input through which such a
claim could be asserted in the first place.
"""
import gzip
import hashlib
import inspect
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
class Admission:
    source_object_sha256: str
    recognition_disposition: str
    schema_id: str | None
    disposition: str


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


def admit(raw_bytes, registry_bytes=None, recognition_bytes=None):
    """Schema admission: recognition_result := recognize_G,R(X), derived here.

    The only source-identity input is the exact raw bytes X being admitted.
    registry_bytes/recognition_bytes are accepted only to exercise fail-closed
    G/R binding mismatches (Section 13/20 R4) -- callers cannot use them to
    supply a disposition or schema_id, because none exists as a parameter.
    """
    candidate = _verify_candidate_authorities()
    registry_bytes = registry_bytes if registry_bytes is not None else REGISTRY.read_bytes()
    recognition_bytes = recognition_bytes if recognition_bytes is not None else RECOGNITION.read_bytes()
    if _hash(registry_bytes) != candidate["bound_authority"]["base_registry_sha256"]:
        raise ValueError("candidate registry binding mismatch")
    if _hash(recognition_bytes) != candidate["bound_authority"]["frozen_source_structure_recognition_amendment_sha256"]:
        raise ValueError("recognition G binding mismatch")

    snapshot = recognizer.VerifiedRegistrySnapshot.from_exact_artifact_bytes(registry_bytes, _hash(registry_bytes))
    result = recognizer.recognize_source_object(raw_bytes, snapshot)
    source_object_sha256 = _hash(raw_bytes)

    if result.disposition != recognizer.RECOGNIZED or result.schema_id is None:
        return Admission(source_object_sha256, result.disposition, result.schema_id, INADMISSIBLE)
    known = json.loads(registry_bytes)["known_schema_variants"]
    if result.schema_id not in known:
        return Admission(source_object_sha256, result.disposition, result.schema_id, INADMISSIBLE)
    if _scope_authorization(result.schema_id, registry_bytes) != AUTHORIZED:
        return Admission(source_object_sha256, result.disposition, result.schema_id, INADMISSIBLE)
    return Admission(source_object_sha256, result.disposition, result.schema_id, ADMISSIBLE)


def test_candidate_is_frozen_and_binds_exact_frozen_authorities():
    candidate = _verify_candidate_authorities()
    assert candidate["status"] == "FROZEN"
    assert candidate["self_freeze_authorized"] is False
    assert candidate["artifact_kind"] == "PROTOCOL_AMENDMENT_CANDIDATE"
    assert candidate["bound_authority"]["base_registry_sha256"] == _hash(REGISTRY.read_bytes())


def test_freeze_is_governance_only_and_binds_the_reviewed_commit():
    """Mirrors test_freeze_is_governance_only_and_binds_the_reviewed_commit in
    tests/test_r1_source_structure_recognition_amendment_v1.py: the freeze commit
    must change only status/freeze_provenance, and freeze_provenance must bind the
    exact reviewed commit and review receipt, never imply self-freeze."""
    import subprocess

    reviewed_sha = "9df8a724e526559f742b5f9e3a95f99017c8d3ec"
    candidate = _candidate()
    review = json.loads(
        (DATA / "r1_daily_market_evidence_schema_admission_amendment_review_v1.json").read_bytes()
    )
    original = json.loads(subprocess.check_output(
        ["git", "show", f"{reviewed_sha}:experiments/data/r1_daily_market_evidence_schema_admission_amendment_v1.json"],
        cwd=ROOT,
        text=True,
    ))
    frozen_semantics = dict(candidate)
    original_semantics = dict(original)
    for payload in (frozen_semantics, original_semantics):
        payload.pop("status", None)
        payload.pop("freeze_provenance", None)
    assert frozen_semantics == original_semantics

    assert candidate["freeze_provenance"] == {
        "candidate_commit_reviewed_sha": reviewed_sha,
        "frozen_amendment_semantic_content_sha256": candidate["amendment_semantic_content_sha256"],
        "frozen_effective_combined_contract_binding_sha256": candidate["effective_combined_contract_binding_sha256"],
        "operator_authorization": "explicit operator authorization supplied for this governance-only freeze of the exact independently hostile-reviewed candidate; no semantic changes authorized",
        "review_receipt": "r1_daily_market_evidence_schema_admission_amendment_review_v1.json",
        "review_receipt_payload_sha256": review["review_payload_sha256"],
        "review_receipt_repository_native_at_review_time": False,
    }
    review_payload = dict(review)
    review_payload.pop("review_payload_sha256")
    assert review["review_payload_sha256"] == _semantic_hash(review_payload)
    assert review["reviewed_candidate_sha"] == candidate["freeze_provenance"]["candidate_commit_reviewed_sha"]
    assert review["reviewed_candidate_semantic_content_sha256"] == candidate["amendment_semantic_content_sha256"]
    assert review["reviewed_effective_combined_contract_binding_sha256"] == candidate["effective_combined_contract_binding_sha256"]
    assert review["verdict"] == "PASS_SAFE_TO_FREEZE"
    assert candidate["self_freeze_authorized"] is False


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


def test_interface_takes_only_x_no_recognition_shaped_input():
    """R1/R2/R3 (Section 20): the admission interface has no field a caller
    could use to assert a disposition, schema_id, or independent X hash."""
    params = set(inspect.signature(admit).parameters)
    assert params == {"raw_bytes", "registry_bytes", "recognition_bytes"}
    for forbidden in ("disposition", "schema_id", "recognition_result", "receipt", "source_object_sha256"):
        assert forbidden not in params


def test_experiment_a_no_match_forgery_is_now_inadmissible_by_construction():
    """Mandatory Experiment A: genuine recognition of X_bad is NO_MATCH; there
    is no way to assert RECOGNIZED(bybit_trade_v1) for it through admit()."""
    raw_bad = _raw("not,a,registered,header")
    genuine = recognizer.recognize_source_object(raw_bad, _registry_snapshot())
    assert genuine.disposition == recognizer.NO_MATCH and genuine.schema_id is None

    result = admit(raw_bad)
    assert result.recognition_disposition == recognizer.NO_MATCH
    assert result.schema_id is None
    assert result.disposition == INADMISSIBLE
    assert result.source_object_sha256 == _hash(raw_bad)


def test_experiment_b_rpi_object_cannot_be_relabeled_authorized():
    """Mandatory Experiment B: a genuine RPI object recognizes as
    bybit_trade_v1_rpi, which is registered-but-NOT_AUTHORIZED; nothing in the
    admission interface can relabel it as bybit_trade_v1."""
    fields = json.loads(REGISTRY.read_bytes())["known_schema_variants"]["bybit_trade_v1_rpi"]["field_set"]
    raw_rpi = _raw(",".join(fields))
    genuine = recognizer.recognize_source_object(raw_rpi, _registry_snapshot())
    assert genuine.disposition == recognizer.RECOGNIZED and genuine.schema_id == "bybit_trade_v1_rpi"

    result = admit(raw_rpi)
    assert result.recognition_disposition == recognizer.RECOGNIZED
    assert result.schema_id == "bybit_trade_v1_rpi"
    assert result.schema_id != "bybit_trade_v1"
    assert _scope_authorization("bybit_trade_v1_rpi", REGISTRY.read_bytes()) == NOT_AUTHORIZED
    assert result.disposition == INADMISSIBLE


def test_experiment_c_ambiguity_cannot_be_resolved_by_scope():
    """Mandatory Experiment C: a scratch-only synthetic registry with a
    field_set collision makes recognition AMBIGUOUS. Even though one of the
    matching schemas (bybit_trade_v1) would otherwise be AUTHORIZED, AMBIGUOUS
    is not RECOGNIZED, so admission is impossible -- scope cannot pick a
    winner among ambiguous matches."""
    variants = json.loads(REGISTRY.read_bytes())["known_schema_variants"]
    custom = dict(variants)
    custom["collision"] = dict(custom["bybit_trade_v1"])
    payload = _canonical({"known_schema_variants": custom})
    snapshot = _registry_snapshot(payload)
    raw = _raw(",".join(custom["bybit_trade_v1"]["field_set"]))

    result = recognizer.recognize_source_object(raw, snapshot)
    assert result.disposition == recognizer.AMBIGUOUS
    assert "bybit_trade_v1" in result.matching_schema_ids
    assert _scope_authorization("bybit_trade_v1", REGISTRY.read_bytes()) == AUTHORIZED
    assert result.disposition != recognizer.RECOGNIZED

    # The frozen candidate is bound to the exact frozen R; a synthetic,
    # differently-byte'd registry (even a self-consistent one) fails closed
    # at the admission boundary before scope is ever consulted.
    with pytest.raises(ValueError, match="candidate registry binding mismatch"):
        admit(raw, registry_bytes=payload)


def test_experiment_d_positive_control():
    """Mandatory Experiment D: a genuine, authorized, recognized object is
    admissible. The repair must not simply deny everything."""
    fields = json.loads(REGISTRY.read_bytes())["known_schema_variants"]["bybit_trade_v1"]["field_set"]
    raw_base = _raw(",".join(fields))
    genuine = recognizer.recognize_source_object(raw_base, _registry_snapshot())
    assert genuine.disposition == recognizer.RECOGNIZED and genuine.schema_id == "bybit_trade_v1"
    assert _scope_authorization("bybit_trade_v1", REGISTRY.read_bytes()) == AUTHORIZED

    result = admit(raw_base)
    assert result.recognition_disposition == recognizer.RECOGNIZED
    assert result.schema_id == "bybit_trade_v1"
    assert result.disposition == ADMISSIBLE


@pytest.mark.parametrize("schema_id", ["bybit_trade_v1_rpi", "tardis_derivative_ticker_v1", "bybit_instruments_info_current_v1"])
def test_registered_but_scope_unauthorized_is_inadmissible(schema_id):
    fields = json.loads(REGISTRY.read_bytes())["known_schema_variants"][schema_id]["field_set"]
    raw = _raw(",".join(fields))
    genuine = recognizer.recognize_source_object(raw, _registry_snapshot())
    assert genuine.disposition == recognizer.RECOGNIZED and genuine.schema_id == schema_id
    assert _scope_authorization(schema_id, REGISTRY.read_bytes()) == NOT_AUTHORIZED
    assert admit(raw).disposition == INADMISSIBLE


def test_unlisted_or_future_schema_defaults_deny():
    result = admit(_raw("not,a,registered,header"))
    assert result.disposition == INADMISSIBLE
    assert result.schema_id is None
    # No such thing as a "future_schema" registered anywhere on disk; the
    # registry itself is the only source of matchable schema_ids, so an
    # unlisted/future layout can only ever surface as NO_MATCH here.
    assert "future_schema" not in json.loads(REGISTRY.read_bytes())["known_schema_variants"]


@pytest.mark.parametrize("header", ["a", "a,,b", "a,b,a", '"a",b', "not,a,registered,header"])
def test_failure_results_are_never_admissible(header):
    raw = _raw(header)
    result = admit(raw)
    assert result.recognition_disposition in {recognizer.FRAMING_FAILURE, recognizer.MALFORMED_HEADER, recognizer.NO_MATCH}
    assert result.disposition == INADMISSIBLE


def test_empty_object_has_no_fabricated_schema_authorization():
    raw = gzip.compress(b"")
    result = admit(raw)
    assert result.recognition_disposition == recognizer.FRAMING_FAILURE
    assert result.schema_id is None
    assert result.disposition == INADMISSIBLE


def test_wrong_registry_binding_fails_closed():
    """Section 13/20 R4: a wrong R (even self-consistent bytes) is rejected
    before recognition or scope is ever consulted."""
    mutated_registry = json.loads(REGISTRY.read_bytes())
    mutated_registry["known_schema_variants"]["bybit_trade_v1"]["field_set"].append("extra_field")
    payload = _canonical(mutated_registry)
    raw = _raw(",".join(json.loads(REGISTRY.read_bytes())["known_schema_variants"]["bybit_trade_v1"]["field_set"]))
    with pytest.raises(ValueError, match="candidate registry binding mismatch"):
        admit(raw, registry_bytes=payload)


def test_wrong_recognition_binding_fails_closed():
    """Section 13/20 R4: a wrong G is rejected before recognition is derived."""
    raw = _raw(",".join(json.loads(REGISTRY.read_bytes())["known_schema_variants"]["bybit_trade_v1"]["field_set"]))
    with pytest.raises(ValueError, match="recognition G binding mismatch"):
        admit(raw, recognition_bytes=b"not the frozen recognition amendment bytes")


def test_wrong_scope_binding_fails_closed(monkeypatch):
    raw = _raw(",".join(json.loads(REGISTRY.read_bytes())["known_schema_variants"]["bybit_trade_v1"]["field_set"]))
    assert admit(raw).disposition == ADMISSIBLE
    mutated = _scope()
    mutated["semantic_body"]["structural_authorization_matrix"]["bybit_trade_v1"]["daily_market_authorization"] = NOT_AUTHORIZED
    monkeypatch.setattr(sys.modules[__name__], "_scope", lambda: mutated)
    with pytest.raises(ValueError, match="frozen scope semantic binding mismatch"):
        admit(raw)


def test_explicit_scope_authority_not_ambient_state(monkeypatch):
    raw = _raw(",".join(json.loads(REGISTRY.read_bytes())["known_schema_variants"]["bybit_trade_v1"]["field_set"]))
    assert admit(raw).disposition == ADMISSIBLE
    altered = _scope()
    altered["semantic_body"]["structural_authorization_matrix"]["bybit_trade_v1"]["daily_market_authorization"] = NOT_AUTHORIZED
    monkeypatch.setattr(sys.modules[__name__], "_scope", lambda: altered)
    with pytest.raises(ValueError, match="frozen scope semantic binding mismatch"):
        admit(raw)


def test_ordering_changes_recognition_neither_semantics_nor_first_match():
    registry = json.loads(REGISTRY.read_bytes())
    reversed_variants = dict(reversed(list(registry["known_schema_variants"].items())))
    reordered = _canonical({**registry, "known_schema_variants": reversed_variants})
    fields = registry["known_schema_variants"]["bybit_trade_v1"]["field_set"]
    assert recognizer.recognize_source_object(_raw(",".join(fields)), _registry_snapshot()).schema_id == "bybit_trade_v1"
    assert recognizer.recognize_source_object(_raw(",".join(fields)), _registry_snapshot(reordered)).schema_id == "bybit_trade_v1"
    assert _hash(reordered) != _hash(REGISTRY.read_bytes())  # it cannot masquerade as frozen R1


def test_historical_replay_is_deterministic_and_not_ambient():
    """Section 17/20 R8: same X, G, R, Scope -> same admission result, and the
    evaluator reads no ambient/wall-clock state -- only re-running the exact
    same X through the same derivation twice."""
    fields = json.loads(REGISTRY.read_bytes())["known_schema_variants"]["bybit_trade_v1"]["field_set"]
    raw = _raw(",".join(fields))
    first = admit(raw)
    second = admit(raw)
    assert first == second


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


def test_repair_history_records_forged_recognition_result_fix():
    repairs = _candidate()["repair_history"]
    entry = next(item for item in repairs if item["addressed_review_verdict"] == "BLOCK_FORGED_RECOGNITION_RESULT")
    assert entry["still_not_frozen"] is True
    assert entry["repair_index"] == 5
