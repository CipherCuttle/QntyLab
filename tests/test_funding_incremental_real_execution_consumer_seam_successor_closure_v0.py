import hashlib
import json
import subprocess
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
IMPL_DIR = (
    "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/"
    "real_execution_consumer_seam_successor_implementation_v0"
)
CLOSURE_PATH = ROOT / IMPL_DIR / "closure.json"
REVIEW_PATH = ROOT / IMPL_DIR / "hostile_review.md"
DECISION_PATH = ROOT / (
    "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/"
    "real_execution_consumer_seam_successor_decision_v0/decision.json"
)
PREDECESSOR_CLOSURE_PATH = ROOT / (
    "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/"
    "real_execution_consumer_seam_implementation_authorization_v0/closure.json"
)
PROJECTS_PATH = ROOT / "docs/state/projects.toml"
ROADMAP_PATH = ROOT / "docs/CURRENT_ROADMAP.md"
PROJECT_ID = "FUNDING_INCREMENTAL_REAL_EXECUTION_CONSUMER_SEAM_SUCCESSOR_IMPLEMENTATION_V0"
DECISION_PROJECT_ID = (
    "JIGSAW_FUNDING_PRESSURE_INCREMENTAL_FORECAST_VALUE_"
    "REAL_EXECUTION_CONSUMER_SEAM_SUCCESSOR_DECISION_V0"
)
REVIEWED_CANDIDATE_COMMIT = "d181d12096e19c1dbe2f89585e73b8f8f7b6b21f"
GOVERNING_DECISION_SHA256 = "dac2051e751953bf2958bf4a3fb9371a713fce75290291afc9b8f4f01a39a9dc"
PREDECESSOR_CLOSURE_SHA256 = "e4418ca21b74bec9199fd28d25219d3947f3298a21b5364f96d3d052409df2d6"


def _closure() -> dict[str, object]:
    return json.loads(CLOSURE_PATH.read_text(encoding="utf-8"))


def _record(project_id: str) -> dict[str, object]:
    registry = tomllib.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    return next(row for row in registry["project"] if row["project_id"] == project_id)


def test_closure_state_is_terminal_blocked() -> None:
    closure = _closure()

    assert closure["state"] == "CLOSED_BLOCKED"
    assert closure["terminal_reason"] == "hostile review failed required invariants"
    assert closure["next_action"] == "STOP"


def test_exactly_one_terminal_hostile_review_and_no_rereview() -> None:
    closure = _closure()
    review = REVIEW_PATH.read_text(encoding="utf-8")

    assert closure["terminal_review_count"] == 1
    assert closure["hostile_review"]["count"] == 1
    assert closure["hostile_review"]["review_type"] == "single terminal hostile review"
    assert closure["hostile_review"]["targeted_rereview_count"] == 0
    assert closure["hostile_review"]["targeted_rereview_used"] is False
    assert closure["hostile_review"]["repair_after_review_performed"] is False
    assert "Review count: 1" in review
    assert "No targeted rereview" in review


def test_reviewed_candidate_commit_is_bound_and_never_canonicalized() -> None:
    closure = _closure()
    record = _record(PROJECT_ID)
    reviewed = closure["reviewed_implementation"]
    assert isinstance(reviewed, dict)

    assert closure["reviewed_implementation"]["pull_request"] == 241
    assert closure["reviewed_implementation"]["candidate_commit"] == REVIEWED_CANDIDATE_COMMIT
    assert closure["reviewed_implementation"]["candidate_implementation_canonicalized"] is False
    assert closure["reviewed_implementation"]["candidate_implementation_merged"] is False
    assert closure["reviewed_implementation"]["candidate_source_on_canonical_master"] is False
    assert closure["reviewed_implementation"]["referenced_only_by_historical_commit_hash"] is True
    assert record["reviewed_candidate_commit"] == REVIEWED_CANDIDATE_COMMIT
    assert record["implementation_candidate_reviewed"] is True
    assert record["implementation_candidate_failed_review"] is True
    assert record["implementation_candidate_canonicalized"] is False
    assert record["implementation_candidate_merged"] is False
    assert record["implementation_completed"] is False
    assert record["pr241_merged"] is False


def test_both_terminal_findings_are_recorded_distinctly() -> None:
    closure = _closure()
    blocking = closure["hostile_review"]["blocking"]
    assert isinstance(blocking, list)

    assert closure["hostile_review"]["blocking_findings"] == 2
    assert len(blocking) == 2
    assert {finding["review_comment_id"] for finding in blocking} == {3925566255, 3925566262}
    assert {finding["finding_id"] for finding in blocking} == {
        "SYNTHETIC_PROVENANCE_LAUNDERING",
        "EXACTLY_ONCE_IS_PROCESS_LOCAL",
    }
    review = REVIEW_PATH.read_text(encoding="utf-8")
    assert "3925566255" in review
    assert "3925566262" in review


def test_failed_implementation_source_is_not_canonical_on_master() -> None:
    record = _record(PROJECT_ID)

    assert record["candidate_source_on_canonical_master"] is False
    for forbidden in (
        "qntylab/jigsaw_funding_pressure_incremental_forecast_value_consumer_seam_successor_v0.py",
        "qntylab/funding_incremental_consumer_seam_successor_v0.py",
    ):
        assert not (ROOT / forbidden).exists()
    # No implementation manifest from PR #241 was copied into the closure set.
    closure_manifest = _closure()
    assert closure_manifest["implementation_completed"] is False
    assert closure_manifest["later_implementation_phases_authorized"] == 0


def test_no_scientific_data_provider_claim_or_origin_authority() -> None:
    closure = _closure()
    record = _record(PROJECT_ID)

    assert closure["real_data_accessed"] is False
    assert closure["outcomes_accessed"] is False
    assert closure["providers_accessed"] is False
    assert closure["real_claims_accessed_or_consumed"] is False
    assert closure["evaluation_origins_consumed"] == 0
    assert closure["scientific_execution_performed"] is False
    assert closure["frozen_v0_bytes_changed"] is False
    for authority in ("router_authority", "qnty_authority", "trading_authority", "capital_authority"):
        assert closure[authority] == "NONE"
        assert record[authority] == "NONE"
    assert record["real_data_accessed"] is False
    assert record["outcomes_accessed"] is False
    assert record["providers_accessed"] is False
    assert record["real_claims_accessed_or_consumed"] is False
    assert record["evaluation_origins_consumed"] == 0
    assert record["scientific_execution_performed"] is False
    assert record["pr239_authorized"] is False
    assert record["later_implementation_phases_authorized"] == 0
    assert record["active_project_after_closure"] == "NONE"


def test_governing_decision_and_predecessor_closure_bytes_unchanged() -> None:
    assert hashlib.sha256(DECISION_PATH.read_bytes()).hexdigest() == GOVERNING_DECISION_SHA256
    assert hashlib.sha256(PREDECESSOR_CLOSURE_PATH.read_bytes()).hexdigest() == PREDECESSOR_CLOSURE_SHA256

    decision = json.loads(DECISION_PATH.read_text(encoding="utf-8"))
    assert decision["decision_state"] == "CLOSED_PASS"
    assert decision["authorized_successor_implementation"]["phase_id"] == PROJECT_ID

    predecessor = json.loads(PREDECESSOR_CLOSURE_PATH.read_text(encoding="utf-8"))
    assert predecessor["state"] == "CLOSED_BLOCKED"

    decision_record = _record(DECISION_PROJECT_ID)
    assert decision_record["decision_artifact_sha256"] == GOVERNING_DECISION_SHA256
    assert decision_record["predecessor_closure_sha256"] == PREDECESSOR_CLOSURE_SHA256
    assert decision_record["implementation_completed"] is False


def test_no_implementation_source_shipped_in_qntylab_for_this_phase() -> None:
    # The closure is bookkeeping-only: no repaired implementation code, durable
    # idempotency, provenance layer, or new synthetic batch type may ship here.
    closure = _closure()
    record = _record(PROJECT_ID)

    assert closure["state"] == "CLOSED_BLOCKED"
    assert record["state"] == "CLOSED_BLOCKED"
    assert record["governance_only"] is True


def test_roadmap_projection_matches_registry() -> None:
    record = _record(PROJECT_ID)
    roadmap = ROADMAP_PATH.read_text(encoding="utf-8")

    assert record["display_name"] in roadmap
    assert "`CLOSED_BLOCKED`" in roadmap
    summary = (
        "The successor implementation candidate was reviewed once and failed "
        "terminal review because the synthetic boundary could launder arbitrary "
        "ForecastRows as synthetic validation and process-local idempotency did "
        "not establish lifecycle-level exactly-once behavior. PR #241 remains "
        "unmerged. No repair, rereview, scientific authorization, or downstream "
        "authority is permitted under this phase."
    )
    assert summary in roadmap
    assert f"CLOSED_BLOCKED: {summary}" == record["next_action"]


def test_render_check_matches_generated_roadmap() -> None:
    result = subprocess.run(
        ["python", "-m", "qntylab.project_context", "render", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "roadmap current" in result.stdout


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
