"""Terminal-closure bookkeeping for the failed hardening implementation V0.

Governed phase ``FUNDING_INCREMENTAL_CONTRACT_INTEGRITY_HARDENING_IMPLEMENTATION_V0``
terminal closure (bookkeeping only).  The implementation PR #245 failed its one
independent hostile review (four High), received the one permitted bounded
repair, and the one permitted targeted Critical/High re-review returned one
remaining High finding; the lifecycle budget is exhausted and the phase is
CLOSED_BLOCKED.  No implementation source from PR #245 is canonical; the failed
implementation stays non-canonical source evidence reachable through Git/PR
history only.  This suite asserts the closure bookkeeping truthfully records
that terminal state.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DECISION_DIR = (
    "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/"
    "contract_integrity_hardening_decision_v0"
)
CLOSURE_PATH = ROOT / DECISION_DIR / "implementation_closure.json"
RECEIPTS_PATH = ROOT / DECISION_DIR / "implementation_review_receipts.md"
DECISION_PATH = ROOT / DECISION_DIR / "decision.json"
PROJECTS_PATH = ROOT / "docs/state/projects.toml"
PROJECT_ID = "JIGSAW_FUNDING_PRESSURE_INCREMENTAL_CONTRACT_INTEGRITY_HARDENING_IMPLEMENTATION_V0"
DECISION_PROJECT_ID = "JIGSAW_FUNDING_PRESSURE_INCREMENTAL_CONTRACT_INTEGRITY_HARDENING_DECISION_V0"
GOVERNING_DECISION_SHA256 = "712cda5d4e82414ab095deecabaa7d2af054bc7b97ab5cbd394c9fdbeda32a23"
CANONICAL_MASTER = "12202259845ada4f9876288426fed91aba5b6861"
REVIEWED_CANDIDATE_COMMIT = "a6200d3e3d1ae2cffc44cca1d1db5d626239452c"
REPAIRED_CANDIDATE_COMMIT = "db6a6c6ed5102019300066edfdf4d4d9402f111a"
INITIAL_REVIEW_ID = "PRR_kwDOTo27Xs8AAAABMQI3yw"
TARGETED_REREVIEW_ID = "PRR_kwDOTo27Xs8AAAABMQ8rww"
INITIAL_THREADS = (
    "PRRT_kwDOTo27Xs6fbIjW",
    "PRRT_kwDOTo27Xs6fbIjc",
    "PRRT_kwDOTo27Xs6fbIjd",
    "PRRT_kwDOTo27Xs6fbIjh",
)
REMAINING_THREAD = "PRRT_kwDOTo27Xs6fcsAd"
EXECUTOR_V0_RELATIVE_PATH = "qntylab/jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py"
REAL_CAPABLE_WRAPPER_V1_RELATIVE_PATH = (
    "qntylab/jigsaw_funding_pressure_incremental_forecast_value_real_capable_wrapper_v1.py"
)
EXECUTOR_V0_SHA256 = "1ffcfeb959cfc547fcda96384c1c8f58b3f5cbc174c5d535324480ede312e8c6"
REAL_CAPABLE_WRAPPER_V1_SHA256 = "b0d30af9f6def297c23981c554d6c2224ff1736a491db009a9d8ce7fcc9a9b2e"
NON_CANONICAL_IMPLEMENTATION_SOURCE = (
    "qntylab/jigsaw_funding_pressure_incremental_forecast_value_hardened_evaluation_boundary_v1.py"
)


def _closure() -> dict[str, object]:
    return json.loads(CLOSURE_PATH.read_text(encoding="utf-8"))


def _record(project_id: str) -> dict[str, object]:
    registry = tomllib.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    return next(row for row in registry["project"] if row["project_id"] == project_id)


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def test_closure_state_is_terminal_blocked() -> None:
    closure = _closure()
    assert closure["state"] == "CLOSED_BLOCKED"
    assert closure["final_disposition"] == "CLOSED_BLOCKED"
    assert closure["next_action"] == "STOP"
    record = _record(PROJECT_ID)
    assert record["state"] == "CLOSED_BLOCKED"
    assert record["canonicalization_status"] == "NOT_CANONICALIZED"


def test_governing_decision_binding_is_unchanged() -> None:
    closure = _closure()
    assert closure["governing_decision"]["sha256"] == GOVERNING_DECISION_SHA256
    assert closure["canonical_master"] == CANONICAL_MASTER
    assert hashlib.sha256(DECISION_PATH.read_bytes()).hexdigest() == GOVERNING_DECISION_SHA256
    record = _record(PROJECT_ID)
    assert record["governing_decision_project_id"] == DECISION_PROJECT_ID
    assert record["governing_decision_artifact_sha256"] == GOVERNING_DECISION_SHA256
    assert record["governing_decision_unchanged"] is True


def test_review_budget_is_exhausted_exactly_as_lived() -> None:
    closure = _closure()
    budget = closure["review_budget"]
    assert budget["initial_hostile_review_count"] == 1
    assert budget["initial_high_count"] == 4
    assert budget["bounded_repair_used"] is True
    assert budget["targeted_critical_high_rereview_used"] is True
    assert budget["targeted_rereview_high_count"] == 1
    assert budget["repair_budget_exhausted"] is True
    assert budget["further_repair_authorized"] is False
    assert budget["further_rereview_authorized"] is False
    initial = closure["initial_hostile_review"]
    assert initial["github_review_id"] == INITIAL_REVIEW_ID
    assert initial["reviewed_candidate_commit"] == REVIEWED_CANDIDATE_COMMIT
    assert initial["high"] == 4 and initial["critical"] == 0
    assert tuple(finding["thread"] for finding in initial["findings"]) == INITIAL_THREADS
    rereview = closure["targeted_critical_high_rereview"]
    assert rereview["github_review_id"] == TARGETED_REREVIEW_ID
    assert rereview["reviewed_candidate_commit"] == REPAIRED_CANDIDATE_COMMIT
    assert rereview["high"] == 1 and rereview["critical"] == 0
    remaining = rereview["remaining_findings"][0]
    assert remaining["thread"] == REMAINING_THREAD
    assert remaining["severity"] == "HIGH"
    assert "implementation-only governance decision" in remaining["summary"]
    assert closure["bounded_repair"]["used"] is True
    assert closure["bounded_repair"]["repaired_candidate_commit"] == REPAIRED_CANDIDATE_COMMIT


def test_review_receipts_are_durable_and_faithful() -> None:
    receipts = RECEIPTS_PATH.read_text(encoding="utf-8")
    assert INITIAL_REVIEW_ID in receipts
    assert TARGETED_REREVIEW_ID in receipts
    for thread in (*INITIAL_THREADS, REMAINING_THREAD):
        assert thread in receipts
    assert REVIEWED_CANDIDATE_COMMIT in receipts
    assert REPAIRED_CANDIDATE_COMMIT in receipts
    assert "FINAL_DISPOSITION = CLOSED_BLOCKED" in receipts
    assert "FURTHER_REPAIR_AUTHORIZED = NO" in receipts
    assert "FURTHER_REREVIEW_AUTHORIZED = NO" in receipts
    assert "PR245_MERGE_AUTHORIZED = NO" in receipts


def test_failed_implementation_is_never_canonical_and_pr245_stays_unmerged() -> None:
    closure = _closure()
    record = _record(PROJECT_ID)
    # No implementation source from PR #245 exists on canonical master.
    assert not (ROOT / NON_CANONICAL_IMPLEMENTATION_SOURCE).exists()
    assert not (ROOT / "tests/test_funding_incremental_contract_integrity_hardening_invariants_v0.py").exists()
    assert closure["pull_request"]["number"] == 245
    assert closure["pull_request"]["merge_authorized"] is False
    assert closure["pull_request"]["merged"] is False
    assert closure["pull_request"]["stays_as_non_canonical_source_evidence"] is True
    assert record["reviewed_pr"] == 245
    assert record["pr245_merge_authorized"] is False
    assert record["pr245_merged"] is False
    assert record["candidate_source_on_canonical_master"] is False
    # The reviewed/repaired candidates are not ancestors of canonical master.
    for commit in (REVIEWED_CANDIDATE_COMMIT, REPAIRED_CANDIDATE_COMMIT):
        probe = subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "origin/master"],
            check=False,
            capture_output=True,
        )
        assert probe.returncode != 0, f"{commit} unexpectedly became an ancestor of master"


def test_frozen_v0_bytes_are_unchanged() -> None:
    assert (
        hashlib.sha256((ROOT / EXECUTOR_V0_RELATIVE_PATH).read_bytes()).hexdigest()
        == EXECUTOR_V0_SHA256
    )
    assert (
        hashlib.sha256((ROOT / REAL_CAPABLE_WRAPPER_V1_RELATIVE_PATH).read_bytes()).hexdigest()
        == REAL_CAPABLE_WRAPPER_V1_SHA256
    )
    closure = _closure()
    assert closure["frozen_v0"]["bytes_changed"] is False


def test_no_authority_is_created_by_the_closure() -> None:
    closure = _closure()
    authority = closure["authority"]
    for flag in (
        "scientific_execution_authorized",
        "scientific_evaluation_authorized",
        "real_data_access_authorized",
        "outcome_access_authorized",
        "provider_access_authorized",
        "claim_access_authorized",
        "claim_consumption_authorized",
        "real_capable_path_activation_authorized",
        "further_implementation_phase_authorized",
    ):
        assert authority[flag] is False
    for domain in ("router_authority", "qnty_authority", "qntyspot_authority", "trading_authority",
                   "capital_authority", "downstream_authority"):
        assert authority[domain] == "NONE"
    record = _record(PROJECT_ID)
    for flag in (
        "scientific_execution_authorized",
        "scientific_evaluation_authorized",
        "real_data_access_authorized",
        "outcome_access_authorized",
        "provider_access_authorized",
        "claim_consumption_authorized",
        "scientific_execution_performed",
        "real_data_accessed",
        "outcomes_accessed",
        "providers_accessed",
        "real_claims_accessed_or_consumed",
    ):
        assert record[flag] is False
    for domain in ("router_authority", "qnty_authority", "qntyspot_authority", "trading_authority",
                   "capital_authority", "downstream_authority"):
        assert record[domain] == "NONE"
    assert record["active_project_after_closure"] == "NONE"
