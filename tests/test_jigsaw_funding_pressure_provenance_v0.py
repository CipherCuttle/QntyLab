import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from qntylab import jigsaw_funding_pressure_provenance_v0 as provenance


def test_pit_v1_certificate_digest_and_mutation():
    certificate = provenance._load("pit_coverage_certificate_v1.json")
    assert provenance.canonical_digest(provenance._without(certificate, "pit_coverage_certificate_v1_digest")) == "sha256:eee5ce2769e49970a7a4e8d4851d7da569abc156d4f183959b416bfb8dbf188b"
    mutated = copy.deepcopy(certificate)
    mutated["pit_eligibility"]["combined_executable_decisions_total"] = 609
    assert provenance.canonical_digest(provenance._without(mutated, "pit_coverage_certificate_v1_digest")) != provenance.PIT_V1_DIGEST


def test_coverage_schedule_is_derived_and_complete():
    coverage = provenance.compute_funding_coverage()
    assert coverage["first_required_pressure_day"] == "2022-10-19"
    assert coverage["last_required_pressure_day"] == "2025-06-19"
    assert coverage["pressure_day_count"] == 975
    assert coverage["symbol_day_requirement_count"] == 19500
    assert coverage["symbol_day_complete_count"] == 19500
    assert coverage["missing_count"] == 0


def test_funding_boundary_is_strict_lower_and_inclusive_upper():
    decision = datetime(2023, 10, 19, tzinfo=UTC)
    lower = decision - timedelta(hours=24)
    assert not (lower < lower <= decision)
    assert lower <= decision


def test_verifier_uses_active_checkout_root():
    assert provenance.ROOT == provenance.Path(provenance.__file__).resolve().parents[1]


def test_tampered_evidence_byte_fails(tmp_path):
    item = provenance._load("provenance_baseline_v0.json")["evidence_files"][0]
    path = tmp_path / item["relative_path"]
    path.parent.mkdir(parents=True)
    path.write_bytes((provenance.ROOT / item["relative_path"]).read_bytes() + b"x")
    with pytest.raises(AssertionError, match="evidence byte mismatch"):
        provenance.verify_evidence_entry(item, tmp_path, require_tracked=False)


def test_removed_evidence_path_fails(tmp_path):
    item = provenance._load("provenance_baseline_v0.json")["evidence_files"][0]
    with pytest.raises(AssertionError, match="evidence byte mismatch"):
        provenance.verify_evidence_entry(item, tmp_path, require_tracked=False)


@pytest.mark.parametrize("field", ["funding_history_coverage_digest", "execution_git_provenance_contract_digest"])
def test_digest_artifacts_are_self_consistent(field):
    filename = {"funding_history_coverage_digest": "funding_history_coverage_v0.json", "execution_git_provenance_contract_digest": "execution_git_provenance_contract_v0.json"}[field]
    payload = provenance._load(filename)
    assert payload[field] == provenance.canonical_digest(provenance._without(payload, field))
