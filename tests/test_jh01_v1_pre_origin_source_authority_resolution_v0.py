from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ARTIFACT_PATH = (
    ROOT
    / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1"
    / "jh01_v1_pre_origin_source_authority_resolution_v0.json"
)

QUALIFIED_RECORDER_IDENTITY = "4f5e1791be9f17c1871f9b510329a1632412e028d2a84223fa59e83bbe95ec1a"
WRAPPER_IMPLEMENTATION_IDENTITY = "1176037ff0d3102afc67670202154970e4af1491cff1cd19bc9526c9c9d67c41"
SOURCE_CONTRACT_IDENTITY = "BINANCE_USD_M_PERPETUAL_1H_LOGICAL_CLOSE"


def _artifact() -> dict:
    return json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))


def test_artifact_parses_and_carries_phase_identifiers() -> None:
    artifact = _artifact()
    assert artifact["artifact"] == "jh01_v1_pre_origin_source_authority_resolution_v0"
    assert artifact["artifact_version"] == "V0"
    assert artifact["phase"] == "JH01_V1_PRE_ORIGIN_SOURCE_AUTHORITY_RESOLUTION_V0"
    assert artifact["created_utc_date"] == "2026-08-27"
    assert artifact["resolution_verdict"] == "JH01_V1_EXISTING_CAMPAIGN_REPAIR_AUTHORIZED"


def test_preserved_identities_appear_exactly() -> None:
    raw = ARTIFACT_PATH.read_text(encoding="utf-8")
    assert QUALIFIED_RECORDER_IDENTITY in raw
    assert WRAPPER_IMPLEMENTATION_IDENTITY in raw
    assert SOURCE_CONTRACT_IDENTITY in raw
    preserved = _artifact()["preserved_identities"]
    assert preserved["qualified_recorder_identity"] == QUALIFIED_RECORDER_IDENTITY
    assert preserved["wrapper_implementation_identity"] == WRAPPER_IMPLEMENTATION_IDENTITY
    assert preserved["source_contract_identity"] == SOURCE_CONTRACT_IDENTITY


def test_target_commit_rule_pins_origin_master() -> None:
    rule = _artifact()["target_commit_rule"]
    assert isinstance(rule, str) and rule.strip()
    assert "origin/master" in rule
    assert "target_commit" in rule


def test_authorized_next_phase_and_bounded_scope_exist() -> None:
    artifact = _artifact()
    assert artifact["authorized_next_phase"] == "JH01_V1_PRE_ORIGIN_PRODUCTION_PATH_REPAIR_V0"
    bounded_scope = artifact["bounded_scope"]
    assert isinstance(bounded_scope, list) and bounded_scope
    assert all(isinstance(item, str) and item.strip() for item in bounded_scope)
    assert artifact["bounded_scope_constraint"] == "no real origin before 2026-09-15T00:00:00Z"


def test_evidence_references_exist_on_disk() -> None:
    for relative in _artifact()["evidence_references"]:
        assert (ROOT / relative).is_file(), relative


def test_recorder_and_wrapper_module_digests_still_match_pinned_identities() -> None:
    wrapper_before = hashlib.sha256(
        (ROOT / "qntylab/jh01_v1_prospective_operation_v0.py").read_bytes()
    ).hexdigest()
    recorder_before = hashlib.sha256(
        (ROOT / "qntylab/jh01_v1_prospective_recorder_implementation_v0.py").read_bytes()
    ).hexdigest()
    assert wrapper_before == WRAPPER_IMPLEMENTATION_IDENTITY
    assert recorder_before == QUALIFIED_RECORDER_IDENTITY
