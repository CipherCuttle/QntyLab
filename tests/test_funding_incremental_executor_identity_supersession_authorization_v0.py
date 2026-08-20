"""Governance contract tests for the funding executor successor authorization."""

import ast
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/executor_identity_supersession_core_extraction_authorization_v0"
AUTH = json.loads((ARTIFACT_DIR / "authorization.json").read_text(encoding="utf-8"))
IDENTITY = json.loads((ARTIFACT_DIR / "identity_model.json").read_text(encoding="utf-8"))
CLOSURE = json.loads((ARTIFACT_DIR / "closure.json").read_text(encoding="utf-8"))


def test_historical_identity_is_exact_and_successor_identity_is_new():
    historical = IDENTITY["historical_v0"]
    assert historical["commit"] == "f6f12994d65c3dfeaf7839de560e58ad99547c62"
    historical_bytes = subprocess.run(
        ["git", "show", f"{historical['commit']}:{historical['source_path']}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    assert hashlib.sha256(historical_bytes).hexdigest() == historical["source_sha256"]
    assert historical["immutable"] is True
    assert AUTH["source_supersession_policy"]["successor_requires_new_identity"] is True
    assert AUTH["source_supersession_policy"]["successor_sha_must_differ_from_historical_sha"] is True


def test_source_evolution_is_not_history_mutation():
    model = IDENTITY["corrected_distinction"]
    assert model["historical_git_identity_immutable"] is True
    assert model["current_source_path_permanently_frozen"] is False
    assert model["current_source_may_evolve_after_canonical_merge"] is True
    assert model["successor_identity"] == "NEW_COMMIT_BLOB_SOURCE_DIGEST_MANIFEST_AND_BINDING"
    assert CLOSURE["historical_v0_git_identity_mutated"] is False


def test_one_later_phase_is_authorized_only_after_canonical_merge():
    frozen_baseline = AUTH["canonical_reconciliation"]["git_verification"]["origin_master_must_equal"]
    assert frozen_baseline == "502a4e02993f1d23f3cb91bc0d70044ebccaa79c"
    assert AUTH["authorization_effective"] == "AFTER_CANONICAL_MERGE_ONLY"
    assert AUTH["later_implementation_phases_authorized"] == 1
    assert CLOSURE["later_implementation_phase_count"] == 1
    assert CLOSURE["later_implementation_phase"] == "FUNDING_INCREMENTAL_EXECUTOR_CORE_EXTRACTION_AND_SUCCESSOR_IMPLEMENTATION_V1"
    assert subprocess.run(["git", "cat-file", "-e", f"{frozen_baseline}^{{commit}}"], cwd=ROOT).returncode == 0
    git_master = subprocess.run(["git", "rev-parse", "origin/master"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    assert subprocess.run(["git", "merge-base", "--is-ancestor", frozen_baseline, "HEAD"], cwd=ROOT).returncode == 0
    assert subprocess.run(["git", "merge-base", "--is-ancestor", frozen_baseline, git_master], cwd=ROOT).returncode == 0
    assert subprocess.run(["git", "merge-base", "--is-ancestor", "HEAD", frozen_baseline], cwd=ROOT).returncode != 0


def test_pr151_is_diagnostic_only_and_science_is_not_authorized():
    reconciliation = AUTH["canonical_reconciliation"]
    assert reconciliation["pr151_state"] == "CLOSED_UNMERGED"
    assert reconciliation["pr151_merged"] is False
    assert reconciliation["pr151_canonical_authority"] == "NONE"
    firewall = CLOSURE["outcome_firewall"]
    assert CLOSURE["scientific_execution_authority"] == "NONE"
    assert firewall["real_outcome_access"] is False
    assert firewall["scientific_execution"] is False
    assert firewall["evaluation_origins_consumed"] == 0
    assert firewall["new_data_acquisition"] is False
    assert firewall["scientific_result_created"] is False
    assert firewall["trial_completion_recorded"] is False


def test_future_equivalence_gate_and_single_core_rule_are_mandatory():
    gate = AUTH["equivalence_closure_gate"]
    assert gate["required_at_implementation_close"] is True
    assert gate["oracle_must_be_actual_historical_v0_bytes"] is True
    assert len(gate["corpus"]) >= 14
    assert gate["frozen_synthetic_result_digest"] == "sha256:1fca55ebdbe5c4d5b835cb65f87930755d231449c924eae912b522bd04b53ea2"
    assert AUTH["source_supersession_policy"]["active_successor_tree_one_shared_scientific_core"] is True
    manifest = gate["closure_manifest"]
    assert manifest["required_existing_fixture_path"] == "tests/test_jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py"
    assert manifest["required_frozen_fixture_path"].endswith("implementation_v0/synthetic_validation.json")
    assert manifest["generator_seeds"] == {"valid_forecast_rows": 20260820, "malformed_forecast_rows": 20260821}
    assert manifest["hostile_decimal_contexts"] == 24
    assert len(manifest["invalid_input_failure_classes"]) == 6
    assert manifest["required_differential_runner_path"] == "tests/test_funding_incremental_executor_core_extraction_differential_v1.py"
    assert manifest["canonical_result_schema"] == "IncrementalForecastEvaluation canonical serialization"
    assert manifest["canonical_result_schema_sha256"] == "0eb5029002fe472035023b9d73b4d852cf1a3f18a2693ed3454e5167cca2871f"


def test_provenance_v2_foundation_and_successor_manifest_bindings_are_explicit():
    bindings = AUTH["provenance_and_contract_bindings"]
    assert bindings["historical_provenance_baseline"] == "sha256:902be2246b64d133e0f22dd71c04eba344d12ead659e5f57c69183ab92f878d9"
    for relative_path, expected in {
        "qntylab/jigsaw_funding_pressure_execution_v2.py": bindings["v2_source_sha256"],
        "qntylab/jigsaw_funding_pressure_execution_foundation_v0.py": bindings["foundation_source_sha256"],
    }.items():
        assert hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest() == expected
    assert bindings["v2_result_contract"]["substitution_allowed"] is False
    assert bindings["v2_result_contract"]["entrypoint"] == "execute_authorized_frozen_experiment_v2"
    assert bindings["v2_result_contract"]["result_type"] == "FrozenExperimentResult"
    assert bindings["v2_result_contract"]["schema_sha256"] == "ea88d58dbb8f390fa4549539bdeb19c93e3e3f6a9a45f220a315c815ae4b4805"
    assert bindings["successor_result_contract"]["result_type"] == "IncrementalForecastEvaluation"
    assert bindings["successor_result_contract"]["schema_sha256"] == "0eb5029002fe472035023b9d73b4d852cf1a3f18a2693ed3454e5167cca2871f"
    incremental_tree = ast.parse((ROOT / "qntylab/jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py").read_text(encoding="utf-8"))
    incremental_fields = {
        node.name: [item.target.id for item in node.body if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)]
        for node in incremental_tree.body
        if isinstance(node, ast.ClassDef) and node.name in {"IncrementalForecastEvaluation", "OriginForecast"}
    }
    incremental_schema = {"result_type": "IncrementalForecastEvaluation", "fields": incremental_fields["IncrementalForecastEvaluation"], "origin_forecast_fields": incremental_fields["OriginForecast"]}
    incremental_digest = hashlib.sha256(json.dumps(incremental_schema, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert incremental_digest == bindings["successor_result_contract"]["schema_sha256"]
    v2_tree = ast.parse((ROOT / "qntylab/jigsaw_funding_pressure_execution_v2.py").read_text(encoding="utf-8"))
    v2_fields = {
        node.name: [item.target.id for item in node.body if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)]
        for node in v2_tree.body
        if isinstance(node, ast.ClassDef) and node.name in {"FrozenExperimentResult", "FrozenDecision"}
    }
    v2_schema = {"result_type": "FrozenExperimentResult", "fields": v2_fields["FrozenExperimentResult"], "decision_fields": v2_fields["FrozenDecision"]}
    v2_digest = hashlib.sha256(json.dumps(v2_schema, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert v2_digest == bindings["v2_result_contract"]["schema_sha256"]
    assert bindings["successor_manifest_binding"]["must_bind_new_source_digest"] is True
    assert bindings["successor_manifest_binding"]["must_bind_new_result_contract"] is True


def test_preregistration_and_historical_bindings_are_unchanged():
    contract = AUTH["frozen_scientific_contract"]
    prereg = ROOT / "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/preregistration.json"
    assert contract["status"] == "PREREGISTERED_NOT_EXECUTED"
    assert hashlib.sha256(prereg.read_bytes()).hexdigest() == contract["file_sha256"]
    assert contract["digest"] == "d7ec718ab14e73d2aea24749a22caa2921fd81b8a336e2f2eaffb30ae1e992ef"
    assert contract["evaluation_origins"] == 244
    assert contract["forecast_rows"] == 609
    assert len(contract["ordered_panel"]) == 20
