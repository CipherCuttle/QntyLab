"""Conformance tests for the unfrozen registry-scope amendment candidate.

The candidate does not redefine raw-header recognition.  It consumes a
structurally recognized schema_id from an exact registry snapshot and proves
that registration is distinct from DailyMarket authorization, admission, and
record validity.
"""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_PATH = REPO_ROOT / "experiments/data/r1_source_schema_registry_scope_amendment_v1.json"
REGISTRY_PATH = REPO_ROOT / "experiments/data/r1_source_schema_registry_v1.json"
CONTRACT_PATH = REPO_ROOT / "experiments/data/r1_normalized_evidence_contract_v1.json"
SOURCE_PRECEDENCE_FREEZE_PATH = REPO_ROOT / "experiments/data/r1_source_precedence_freeze.json"
INFORMATION_LOSS_LEDGER_PATH = REPO_ROOT / "experiments/data/r1_information_loss_ledger_v1.json"

STRUCTURAL_LAYOUT_UNKNOWN = "STRUCTURAL_LAYOUT_UNKNOWN"
STRUCTURAL_LAYOUT_KNOWN = "STRUCTURAL_LAYOUT_KNOWN"
AUTHORIZED = "AUTHORIZED_FOR_DAILYMARKET"
NOT_AUTHORIZED = "NOT_AUTHORIZED_FOR_DAILYMARKET"


def _canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def _canonical_hash(value):
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _candidate():
    return json.loads(CANDIDATE_PATH.read_bytes())


@dataclass(frozen=True)
class ScopeResult:
    structural_state: str
    daily_market_authorization: str
    registry_snapshot_sha256: str


def _scope(schema_id, exact_registry_bytes, candidate, requested_evidence_family="DailyMarketEvidenceV1"):
    """Scope table logic; successor authorities reuse its default-deny shape."""
    registry_hash = hashlib.sha256(exact_registry_bytes).hexdigest()
    registry = json.loads(exact_registry_bytes)
    known = registry["known_schema_variants"]
    if schema_id not in known:
        return ScopeResult(STRUCTURAL_LAYOUT_UNKNOWN, NOT_AUTHORIZED, registry_hash)
    if requested_evidence_family != "DailyMarketEvidenceV1":
        return ScopeResult(STRUCTURAL_LAYOUT_KNOWN, NOT_AUTHORIZED, registry_hash)
    entry = candidate["semantic_body"]["structural_authorization_matrix"].get(schema_id)
    authorization = entry["daily_market_authorization"] if entry else NOT_AUTHORIZED
    return ScopeResult(STRUCTURAL_LAYOUT_KNOWN, authorization, registry_hash)


def _evaluate_r1(schema_id, exact_registry_bytes, candidate, requested_evidence_family="DailyMarketEvidenceV1", authority_bytes=None):
    """R1 authorization requires all of its exact load-bearing authority bytes."""
    if authority_bytes is None:
        authority_bytes = {
            "base_registry": exact_registry_bytes,
            "base_contract": CONTRACT_PATH.read_bytes(),
            "source_precedence_freeze": SOURCE_PRECEDENCE_FREEZE_PATH.read_bytes(),
            "information_loss_ledger": INFORMATION_LOSS_LEDGER_PATH.read_bytes(),
        }
    _verify_r1_authority(candidate, authority_bytes)
    return _scope(schema_id, exact_registry_bytes, candidate, requested_evidence_family)


def _verify_r1_authority(candidate, authority_bytes):
    """Fail closed unless every authority that grants R1 scope is exact."""
    bound = candidate["bound_authority"]
    required = {
        "base_registry": bound["base_registry_sha256"],
        "base_contract": bound["base_contract_sha256"],
        "information_loss_ledger": bound["information_loss_ledger_sha256"],
        "source_precedence_freeze": bound["source_precedence_freeze_sha256"],
    }
    for authority, expected_sha256 in required.items():
        if hashlib.sha256(authority_bytes[authority]).hexdigest() != expected_sha256:
            raise ValueError(f"R1 scope evaluation requires its exact bound {authority} authority")
    if _canonical_hash(candidate["semantic_body"]) != candidate["amendment_semantic_content_sha256"]:
        raise ValueError("R1 scope evaluation requires its exact bound amendment semantics")
    binding = candidate["effective_combined_contract_binding"]
    if _canonical_hash(binding) != candidate["effective_combined_contract_binding_sha256"]:
        raise ValueError("R1 scope evaluation requires its exact complete authority binding")
    if binding != {
        "amendment_semantic_content_sha256": candidate["amendment_semantic_content_sha256"],
        "base_contract_artifact": bound["base_contract_artifact"],
        "base_contract_sha256": bound["base_contract_sha256"],
        "base_registry_artifact": bound["base_registry_artifact"],
        "base_registry_sha256": bound["base_registry_sha256"],
        "information_loss_ledger_artifact": bound["information_loss_ledger_artifact"],
        "information_loss_ledger_sha256": bound["information_loss_ledger_sha256"],
        "source_precedence_freeze_artifact": bound["source_precedence_freeze_artifact"],
        "source_precedence_freeze_sha256": bound["source_precedence_freeze_sha256"],
    }:
        raise ValueError("R1 scope evaluation requires its exact complete authority binding")


def _r1_registry_bytes():
    return REGISTRY_PATH.read_bytes()


def _r2_registry_bytes():
    registry = json.loads(_r1_registry_bytes())
    registry["known_schema_variants"]["future_structural_layout_v2"] = {
        "status": "KNOWN_VALID_SCHEMA_VARIANT", "field_set": ["future"]
    }
    return (json.dumps(registry, sort_keys=True, separators=(",", ":")) + "\n").encode()


def test_candidate_is_unfrozen_and_hashes_its_own_semantics():
    candidate = _candidate()
    assert candidate["artifact_kind"] == "PROTOCOL_AMENDMENT_CANDIDATE"
    assert candidate["status"] == "CANDIDATE_NOT_YET_FROZEN"
    assert candidate["self_freeze_authorized"] is False
    assert _canonical_hash(candidate["semantic_body"]) == candidate["amendment_semantic_content_sha256"]
    binding = candidate["effective_combined_contract_binding"]
    assert _canonical_hash(binding) == candidate["effective_combined_contract_binding_sha256"]


def test_candidate_binds_the_actual_unchanged_r1_authority_bytes():
    candidate = _candidate()
    bound = candidate["bound_authority"]
    assert hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest() == bound["base_registry_sha256"]
    assert hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest() == bound["base_contract_sha256"]
    assert hashlib.sha256(INFORMATION_LOSS_LEDGER_PATH.read_bytes()).hexdigest() == bound["information_loss_ledger_sha256"]
    assert hashlib.sha256(SOURCE_PRECEDENCE_FREEZE_PATH.read_bytes()).hexdigest() == bound["source_precedence_freeze_sha256"]
    assert candidate["semantic_body"]["amends"]["base_registry_bytes_unchanged"] is True
    assert candidate["semantic_body"]["amends"]["base_contract_bytes_unchanged"] is True


def test_base_trade_is_known_and_explicitly_authorized():
    result = _evaluate_r1("bybit_trade_v1", _r1_registry_bytes(), _candidate())
    assert result.structural_state == STRUCTURAL_LAYOUT_KNOWN
    assert result.daily_market_authorization == AUTHORIZED


@pytest.mark.parametrize("schema_id", [
    "bybit_trade_v1_rpi", "tardis_derivative_ticker_v1", "bybit_instruments_info_current_v1",
])
def test_registered_layouts_do_not_gain_authorization_from_membership(schema_id):
    result = _evaluate_r1(schema_id, _r1_registry_bytes(), _candidate())
    assert result.structural_state == STRUCTURAL_LAYOUT_KNOWN
    assert result.daily_market_authorization == NOT_AUTHORIZED


def test_rpi_is_structural_only_not_unknown_or_authorized():
    candidate = _candidate()
    entry = candidate["semantic_body"]["structural_authorization_matrix"]["bybit_trade_v1_rpi"]
    result = _evaluate_r1("bybit_trade_v1_rpi", _r1_registry_bytes(), candidate)
    assert entry["structural_state"] == STRUCTURAL_LAYOUT_KNOWN
    assert "unresolved" in entry["authorization_basis"].lower()
    assert result.daily_market_authorization == NOT_AUTHORIZED


def test_future_registered_layout_defaults_to_not_authorized():
    """A successor must explicitly promote a new layout; membership is never enough."""
    result = _scope("future_structural_layout_v2", _r2_registry_bytes(), _candidate())
    assert result.structural_state == STRUCTURAL_LAYOUT_KNOWN
    assert result.daily_market_authorization == NOT_AUTHORIZED


def test_r2_cannot_mutate_or_reinterpret_an_r1_evaluation():
    candidate = _candidate()
    r1 = _evaluate_r1("bybit_trade_v1_rpi", _r1_registry_bytes(), candidate)
    with pytest.raises(ValueError, match="exact bound base_registry authority"):
        _evaluate_r1("bybit_trade_v1_rpi", _r2_registry_bytes(), candidate)
    r2 = _scope("bybit_trade_v1_rpi", _r2_registry_bytes(), candidate)
    assert r1.registry_snapshot_sha256 == candidate["bound_authority"]["base_registry_sha256"]
    assert r2.registry_snapshot_sha256 != r1.registry_snapshot_sha256
    assert r1.daily_market_authorization == r2.daily_market_authorization == NOT_AUTHORIZED


def test_scope_is_not_schema_admission_or_record_validity():
    result = _evaluate_r1("bybit_trade_v1", _r1_registry_bytes(), _candidate())
    incomplete_record = {"schema_id": "bybit_trade_v1", "trade_count": 1}
    assert result.daily_market_authorization == AUTHORIZED
    assert set(incomplete_record) != {field["name"] for field in json.loads(CONTRACT_PATH.read_bytes())["layers"]["DailyMarketEvidenceV1"]["fields"]}
    assert "admission" not in ScopeResult.__dataclass_fields__
    assert "validity" not in ScopeResult.__dataclass_fields__


def test_requested_family_scope_fails_closed_for_mixed_family_membership():
    result = _evaluate_r1("tardis_derivative_ticker_v1", _r1_registry_bytes(), _candidate(), "FundingSettlementEvidenceV1")
    assert result.structural_state == STRUCTURAL_LAYOUT_KNOWN
    assert result.daily_market_authorization == NOT_AUTHORIZED


def test_candidate_defers_recognition_language_instead_of_overriding_field_set_authority():
    boundary = _candidate()["semantic_body"]["new_candidate_semantics"]["recognition_language_boundary"]
    assert "does not define raw-header recognition" in boundary
    assert "separate recognition-language amendment" in boundary


@pytest.mark.parametrize("authority", [
    "base_registry", "base_contract", "source_precedence_freeze",
    "information_loss_ledger",
])
def test_substitution_of_each_load_bearing_external_authority_fails_closed(authority):
    candidate = _candidate()
    authority_bytes = {
        "base_registry": _r1_registry_bytes(),
        "base_contract": CONTRACT_PATH.read_bytes(),
        "source_precedence_freeze": SOURCE_PRECEDENCE_FREEZE_PATH.read_bytes(),
        "information_loss_ledger": INFORMATION_LOSS_LEDGER_PATH.read_bytes(),
    }
    authority_bytes[authority] += b"substitution"
    with pytest.raises(ValueError, match=rf"exact bound {authority} authority"):
        _evaluate_r1("bybit_trade_v1", _r1_registry_bytes(), candidate, authority_bytes=authority_bytes)


def test_substitution_of_load_bearing_amendment_semantics_fails_closed():
    candidate = _candidate()
    candidate["semantic_body"]["structural_authorization_matrix"]["bybit_trade_v1"]["daily_market_authorization"] = NOT_AUTHORIZED
    with pytest.raises(ValueError, match="exact bound amendment semantics"):
        _evaluate_r1("bybit_trade_v1", _r1_registry_bytes(), candidate)


def test_effective_binding_cannot_omit_source_precedence_authority():
    candidate = _candidate()
    candidate["effective_combined_contract_binding"].pop("source_precedence_freeze_sha256")
    with pytest.raises(ValueError, match="exact complete authority binding"):
        _evaluate_r1("bybit_trade_v1", _r1_registry_bytes(), candidate)


def test_substitution_of_valid_alternate_ledger_fails_closed():
    candidate = _candidate()
    authority_bytes = {
        "base_registry": _r1_registry_bytes(),
        "base_contract": CONTRACT_PATH.read_bytes(),
        "source_precedence_freeze": SOURCE_PRECEDENCE_FREEZE_PATH.read_bytes(),
        "information_loss_ledger": _canonical_bytes({
            **json.loads(INFORMATION_LOSS_LEDGER_PATH.read_bytes()),
            "trade_stream_fields": [],
        }),
    }
    with pytest.raises(ValueError, match="exact bound information_loss_ledger authority"):
        _evaluate_r1("bybit_trade_v1", _r1_registry_bytes(), candidate, authority_bytes=authority_bytes)


def test_effective_binding_cannot_omit_information_loss_ledger_authority():
    candidate = _candidate()
    candidate["effective_combined_contract_binding"].pop("information_loss_ledger_sha256")
    with pytest.raises(ValueError, match="exact complete authority binding"):
        _evaluate_r1("bybit_trade_v1", _r1_registry_bytes(), candidate)


def test_changed_base_trade_mapping_cannot_retain_governing_identity():
    candidate = _candidate()
    changed_ledger = json.loads(INFORMATION_LOSS_LEDGER_PATH.read_bytes())
    changed_ledger["trade_stream_fields"][0]["target"] = "not DailyMarketEvidenceV1"
    assert _canonical_hash(changed_ledger) != candidate["bound_authority"]["information_loss_ledger_sha256"]
    authority_bytes = {
        "base_registry": _r1_registry_bytes(),
        "base_contract": CONTRACT_PATH.read_bytes(),
        "source_precedence_freeze": SOURCE_PRECEDENCE_FREEZE_PATH.read_bytes(),
        "information_loss_ledger": _canonical_bytes(changed_ledger),
    }
    with pytest.raises(ValueError, match="exact bound information_loss_ledger authority"):
        _evaluate_r1("bybit_trade_v1", _r1_registry_bytes(), candidate, authority_bytes=authority_bytes)


def test_unchanged_complete_authority_set_is_deterministic():
    candidate = _candidate()
    authority_bytes = {
        "base_registry": _r1_registry_bytes(),
        "base_contract": CONTRACT_PATH.read_bytes(),
        "source_precedence_freeze": SOURCE_PRECEDENCE_FREEZE_PATH.read_bytes(),
        "information_loss_ledger": INFORMATION_LOSS_LEDGER_PATH.read_bytes(),
    }
    assert _evaluate_r1("bybit_trade_v1", _r1_registry_bytes(), candidate, authority_bytes=authority_bytes) == _evaluate_r1("bybit_trade_v1", _r1_registry_bytes(), candidate, authority_bytes=authority_bytes)
