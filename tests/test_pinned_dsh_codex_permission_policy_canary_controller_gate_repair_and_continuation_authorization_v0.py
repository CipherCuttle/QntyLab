"""Governance-only tests for the future pinned-DSH controller-gate repair."""

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_permission_policy_canary_controller_gate_repair_and_continuation_authorization_v0"
AUTH = json.loads((ARTIFACT / "authorization.json").read_text(encoding="utf-8"))
PREDECESSOR = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_terminal_error_permission_policy_forensics_v0"


def test_predecessor_and_first_exposure_binding_are_exact():
    predecessor = AUTH["predecessor"]
    assert predecessor["project_id"] == "PINNED_DSH_CODEX_TERMINAL_ERROR_PERMISSION_POLICY_FORENSICS_V0"
    assert predecessor["pr"] == 153
    assert predecessor["merge_sha"] == "2e0025b71a0212aed211b0f6a95d39093b7b1a48"
    assert predecessor["state"] == "CLOSED_BLOCKED"
    assert predecessor["live_product_invocations"] == 0
    assert predecessor["live_canaries_consumed"] == 0
    assert predecessor["treatment_exposures"] == 0
    assert predecessor["retry_count"] == 0
    assert AUTH["first_exposure"]["this_is_not_a_retry_of_an_exposed_canary"] is True
    assert AUTH["first_exposure"]["authorized_later_live_exposures"] == 1
    assert AUTH["first_exposure"]["authorized_later_retries_after_product_launch"] == 0
    assert not (ROOT / predecessor["consumed_marker"]["path"]).exists()


def test_defect_and_repair_surface_are_narrowly_bound():
    defect = AUTH["controller_defect"]
    assert defect["proven"] is True
    assert defect["path"] == "qntylab/pinned_dsh_codex_terminal_error_permission_policy_forensics_v0.py"
    assert defect["symbols"] == ["credential_presence", "run_live"]
    assert defect["old_predicate"] == "if credential_presence():"
    assert AUTH["allowed_later_repair"]["controller_repair_is_treatment_change"] is False
    assert AUTH["allowed_later_repair"]["surface"] == "pre-treatment credential gate only"
    assert "change DSH treatment" in AUTH["allowed_later_repair"]["prohibited_repairs"]


def test_credential_matrix_is_fail_closed_and_value_free():
    matrix = AUTH["credential_gate_test_matrix"]
    assert matrix["deny_set"] == ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY"]
    assert matrix["dummy_values_only"] is True
    assert {case["expected"] for case in matrix["cases"]} == {"PASS", "BLOCK", "BLOCK_MALFORMED"}
    assert any(case["id"] == "H" and case["expected"] == "BLOCK_MALFORMED" for case in matrix["cases"])
    assert any(case["id"] == "I" and case["expected"] == "BLOCK_MALFORMED" for case in matrix["cases"])
    serialized = (ARTIFACT / "authorization.json").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY_VALUE" not in serialized
    assert "Bearer ey" not in serialized
    assert "secret_value" not in serialized


def test_treatment_identity_and_product_pins_are_unchanged():
    delta = AUTH["frozen_treatment"]["request_delta"]
    assert AUTH["frozen_treatment"]["request_delta_count"] == 1
    assert delta == [{"method": "thread/start", "path": "params.approvalPolicy", "before": "<ABSENT>", "after": "never"}]
    identity = AUTH["product_identity"]
    assert identity["dsh_commit"] == "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
    assert identity["dsh_tree"] == "3bc8f89fe494a4755c188be354add4e8b1e7b188"
    assert identity["dsh_tag"] == "dsh-v0.1.0-rc.7"
    assert identity["codex_version"] == "codex-cli 0.147.0"
    assert PREDECESSOR.joinpath("fake_app_server_request_diff.json").is_file()


def test_consumption_boundary_and_authority_ceiling_are_frozen():
    boundary = AUTH["consumption_boundary"]
    assert "immediately before" in boundary["write_point"]
    assert "no second product attempt" in boundary["marker_written_means"]
    ceiling = AUTH["governance_ceiling"]
    assert ceiling["historical_a_rerun"] is False
    assert ceiling["pr137_rerun"] is False
    assert ceiling["pr141_rerun"] is False
    assert ceiling["sandbox_experiment"] is False
    assert ceiling["scientific"] == "NONE"
    assert ceiling["qnty_runtime"] == "NONE"
    assert ceiling["trading"] == "NONE"
    assert ceiling["capital"] == "NONE"
    assert ceiling["auto_merge"] is False


def test_authorization_is_canonicality_gated_and_no_product_runs_here():
    assert AUTH["phase_state"] == "CLOSED_PASS"
    assert AUTH["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert AUTH["authorization_effective"] == "AFTER_CANONICAL_MERGE_ONLY"
    assert AUTH["later_live_contract"]["max_product_invocations"] == 1
    assert AUTH["later_live_contract"]["max_retries"] == 0
    assert AUTH["qnty_agent_eval"] == "NO_MATCH"
    assert subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
