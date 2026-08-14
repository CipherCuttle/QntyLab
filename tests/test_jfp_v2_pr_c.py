from __future__ import annotations

import json

import pytest

from qntylab import jfp_v2_pr_b as prb
from qntylab import jfp_v2_pr_c as prc


ARTIFACTS = prc.ARTIFACT_ROOT


def test_preexecution_authority_binds_frozen_lineage_without_prb_changes():
    authority = json.loads((ARTIFACTS / "execution_authority.json").read_text())
    assert authority["execution_start_master"] == prc.EXPECTED_MASTER
    assert authority["implementation_commit"] == prc.IMPLEMENTATION_COMMIT
    assert authority["implementation_source_digest"] == prc.IMPLEMENTATION_SOURCE_DIGEST
    assert authority["origin_schedule_digest"] == prc.SCHEDULE_DIGEST
    assert authority["real_execution_count_authorized"] == 1
    assert authority["alternate_specification"] is False


def test_result_schema_and_family_preserve_both_finalists():
    results = json.loads((ARTIFACTS / "candidate_results.json").read_text())
    family = json.loads((ARTIFACTS / "family_result.json").read_text())
    assert {result["candidate_id"] for result in results} == set(prb.FINALISTS)
    assert all(set(prb.RESULT_FIELDS) == set(result) for result in results)
    assert all(result["eligible_origin_count"] == 608 and result["blocked_origin_count"] == 0 for result in results)
    assert family["family_size"] == 2
    assert family["support_candidates"] == ["JFPV2_06"]
    assert family["no_support_candidates"] == ["JFPV2_04"]
    assert family["blocked_candidates"] == []
    assert family["family_verdict"] == "FAST_LANE_HISTORICAL_SURVIVOR"


def test_execution_integrity_is_frozen_and_non_escalating():
    manifest = json.loads((ARTIFACTS / "execution_manifest.json").read_text())
    receipt = json.loads((ARTIFACTS / "execution_receipt.json").read_text())
    assert manifest["source_snapshot_digest"] == prb.SOURCE_DIGEST
    assert manifest["network_market_data_used"] is False
    assert manifest["source_substitution"] is False
    assert receipt["real_historical_execution_lineages"] == 1
    assert "trading" not in receipt


def test_frozen_prb_implementation_identity_is_verified():
    prc.verify_implementation_identity()


def test_execute_requires_committed_authority(monkeypatch, tmp_path):
    monkeypatch.setattr(prc, "ARTIFACT_ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="pre-execution authority"):
        prc.execute()
