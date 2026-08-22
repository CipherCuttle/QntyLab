from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "DSH_STAGE_A_V1R3R2_PRELIVE_EXECUTION_ENFORCEMENT_GAP_CLOSURE_V0"
AUTHORIZATION_ID = (
    "DSH_STAGE_A_V1R3R2_PRELIVE_EXECUTION_ENFORCEMENT_GAP_CLOSURE_AUTHORIZATION_V0"
)
OLD_DIGEST = "57162eb65a4177ae58c6b503110dfe802ae345c3e6e9c3963acd207f693fbcc1"
NEW_DIGEST = "e3b623c58d0ce591baa9d0e07d9cf4dd802203d34a4a1b1521d29f75ca302ffa"
PHASE = (
    ROOT
    / "experiments/research/qnty_agent_orchestration_control_contract_v0"
    / "dsh_stage_a_v1r3r2_prelive_execution_enforcement_gap_closure_v0"
)


def load_json(relative: str) -> dict[str, object]:
    return json.loads((PHASE / relative).read_text(encoding="utf-8"))


def project_record() -> dict[str, object]:
    projects = tomllib.loads((ROOT / "docs/state/projects.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    return next(item for item in projects if item["project_id"] == PROJECT_ID)


def test_canonical_authorization_was_reconciled_before_implementation() -> None:
    diagnosis = load_json("diagnosis.json")
    authorization = diagnosis["canonical_authorization"]
    assert authorization == {
        "project_id": AUTHORIZATION_ID,
        "verified_on_origin_master": True,
        "origin_master_at_reconciliation": "3a51a044895bd974de14d611e5055dee478e905c",
        "source_conflicts": 0,
    }
    classifications = diagnosis["before_modification"]
    assert set(classifications.values()) <= {"HARD_ENFORCED", "DECLARATIVE_ONLY", "NOT_PRESENT", "UNKNOWN"}
    assert classifications["MAX_OUTPUT_TOKENS_4096"] == "NOT_PRESENT"
    assert classifications["SECRET_CHILD_FIREWALL"] == "NOT_PRESENT"


def test_single_full_profile_qualification_records_attempt_wire_child_and_secret_truth() -> None:
    qualification = load_json("qualification.json")
    assert qualification["qualification_run_count"] == 1
    cases = {item["id"]: item for item in qualification["cases"]}
    assert set(cases) == {
        "parent_success",
        "parent_429",
        "parent_500",
        "parent_timeout",
        "parent_connection",
        "claude_first",
        "codex_codex",
        "clean_then_codex",
        "double_repair",
        "double_rereview",
        "attempt_nine",
        "spend_exhaustion",
    }
    for name in ("parent_success", "parent_429", "parent_500", "parent_timeout", "parent_connection"):
        assert cases[name]["logical_parent_requests_reserved"] == 1
        assert cases[name]["actual_mock_provider_wire_attempts"] == 1
        assert cases[name]["adapter_max_output_tokens"] == 4096
    assert cases["attempt_nine"]["logical_parent_requests_reserved"] == 8
    assert cases["attempt_nine"]["actual_mock_provider_wire_attempts"] == 8
    assert cases["attempt_nine"]["denial"] == "ATTEMPT_CEILING"
    assert cases["spend_exhaustion"]["denial"] == "AUTHORIZED_SPEND_CAP"
    assert float(cases["spend_exhaustion"]["authorized_spend_usd"]) < 1.0
    assert cases["double_rereview"]["native_stub_invocation_counts"] == {
        "codex": 2,
        "claude": 2,
    }
    invariants = qualification["cross_case_invariants"]
    assert invariants["parent_environment_received_fake_sentinel"] is True
    assert invariants["native_child_sentinel_leaks"] == 0
    assert invariants["persisted_or_captured_sentinel_leaks"] == 0
    assert qualification["summary"]["real_secret_reads"] == 0
    assert qualification["summary"]["external_model_requests"] == 0
    assert qualification["summary"]["spend_usd"] == 0


def test_final_identity_is_reproducible_and_rejects_the_old_contract() -> None:
    recorded = load_json("evidence/digests.json")
    result = subprocess.run(
        ["node", str(PHASE / "evidence/compute-digests.mjs")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    computed = json.loads(result.stdout)
    for key in (
        "NEW_RUNTIME_MANIFEST_DIGEST",
        "NEW_EXECUTABLE_IDENTITY_DIGEST",
        "NEW_LAUNCH_POLICY_DIGEST",
        "NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST",
    ):
        assert recorded[key] == computed[key]
    assert recorded["production_file_digests"] == computed["components"]["launchPolicy"][
        "productionFileDigests"
    ]
    assert recorded["OLD_QUALIFIED_DIGEST"] == OLD_DIGEST
    assert recorded["OLD_QUALIFIED_DIGEST_STILL_VALID"] is False
    assert recorded["NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST"] == NEW_DIGEST
    assert OLD_DIGEST != NEW_DIGEST


def test_closure_records_hard_enforcement_review_repairs_and_zero_real_activity() -> None:
    closure = load_json("closure.json")
    assert closure["state"] == closure["verdict"] == "CLOSED_PASS"
    enforcement = closure["enforcement"]
    assert enforcement["CHILD_SEQUENCE_HARD_ENFORCED"] is True
    assert enforcement["CODEX_MAX_HARD_ENFORCED"] == 2
    assert enforcement["CLAUDE_MAX_HARD_ENFORCED"] == 2
    assert enforcement["PARENT_REQUEST_MAX_HARD_ENFORCED"] == 8
    assert enforcement["HIDDEN_RETRY_BYPASS"] is False
    assert enforcement["MAX_TOKENS_4096_HARD_ENFORCED"] is True
    assert enforcement["SPEND_CAP_HARD_ENFORCED"] is True
    assert enforcement["CLAIM_CONCURRENCY_PASS"] is True
    assert enforcement["CLAIM_PARTIAL_FAILURE_FAIL_CLOSED"] is True
    assert enforcement["QUALIFIED_CONTRACT_REQUIRED_BEFORE_SPAWN"] is True
    assert enforcement["QNTYLAB_ROOT_DERIVED_NOT_CALLER_CONTROLLED"] is True
    assert closure["identity"]["NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST"] == NEW_DIGEST
    assert closure["held_pr_189"]["PR189_STATUS"] == "SUPERSEDED_NOT_MERGEABLE"
    assert closure["review"]["open_critical"] == closure["review"]["open_high"] == 0
    assert closure["review"]["targeted_high_repaired"] == 1
    assert closure["safety"] == {
        "REAL_SECRET_READS": 0,
        "REAL_CLAIMS": 0,
        "EXTERNAL_MODEL_REQUESTS": 0,
        "SPEND": "$0",
        "real_stage_a_episodes": 0,
        "activation_artifacts_created": 0,
    }
    assert closure["next_phase_started"] is False


def test_registry_and_roadmap_close_without_live_authority() -> None:
    record = project_record()
    assert record["state"] == "CLOSED_PASS"
    assert record["authorization_project_id"] == AUTHORIZATION_ID
    assert record["new_qualified_launch_contract_digest"] == NEW_DIGEST
    assert record["old_qualified_digest_still_valid"] is False
    assert record["qualification_runs"] == 1
    assert record["pr189_status"] == "SUPERSEDED_NOT_MERGEABLE"
    assert record["open_critical"] == record["open_high"] == 0
    assert record["real_secret_reads"] == 0
    assert record["real_claims_created"] == 0
    assert record["provider_or_model_requests"] == 0
    assert record["construction_spend_usd"] == 0.0
    assert record["live_execution_authorized"] is False
    assert record["activation_authorized"] is False
    assert record["stage_b_authorized"] is False
    roadmap = (ROOT / "docs/CURRENT_ROADMAP.md").read_text(encoding="utf-8")
    assert "DSH Stage-A V1R3R2 prelive execution-enforcement gap closure V0` — `CLOSED_PASS" in roadmap
    assert NEW_DIGEST in roadmap
