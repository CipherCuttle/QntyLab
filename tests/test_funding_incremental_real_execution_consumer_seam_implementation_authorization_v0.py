import ast
import hashlib
import json
from pathlib import Path

import pytest

from qntylab import jigsaw_funding_pressure_incremental_forecast_value_executor_v0 as executor


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/real_execution_consumer_seam_implementation_authorization_v0"
CLOSURE = json.loads((ARTIFACT_DIR / "closure.json").read_text(encoding="utf-8"))
ANALYSIS = json.loads((ARTIFACT_DIR / "static_consumer_path_analysis.json").read_text(encoding="utf-8"))


def test_closure_is_blocked_and_grants_no_authority():
    assert CLOSURE["state"] == "CLOSED_BLOCKED"
    assert CLOSURE["authorization_created"] is False
    assert CLOSURE["later_implementation_phases_authorized"] == 0
    assert CLOSURE["scientific_execution_authorized"] is False
    assert CLOSURE["evaluation_origins_consumed"] == 0
    assert CLOSURE["router_authority"] == "NONE"
    assert CLOSURE["qnty_authority"] == "NONE"
    assert CLOSURE["trading_authority"] == "NONE"
    assert CLOSURE["capital_authority"] == "NONE"


def test_frozen_bindings_and_source_bytes_are_unchanged():
    assert ANALYSIS["canonical_master"] == "60cec2646d4d6602e0ad33d0d4fc84edc2f272b9"
    assert ANALYSIS["frozen_bindings"]["preregistration_status"] == "PREREGISTERED_NOT_EXECUTED"
    paths = {
        "executor_source_sha256": "qntylab/jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py",
        "v2_source_sha256": "qntylab/jigsaw_funding_pressure_execution_v2.py",
        "foundation_source_sha256": "qntylab/jigsaw_funding_pressure_execution_foundation_v0.py",
        "preregistration_file_sha256": "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/preregistration.json",
    }
    for field, relative_path in paths.items():
        digest = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        assert digest == ANALYSIS["frozen_bindings"][field]


def test_frozen_executor_rejects_real_execution_label():
    rows = object()
    with pytest.raises(executor.UnauthorizedExecutionError):
        executor.run_incremental_forecast_evaluation(rows, execution_mode="REAL_SCIENTIFIC_EXECUTION")
    assert executor.AUTHORIZED_EXECUTION_MODES == (executor.EXECUTION_MODE_SYNTHETIC_VALIDATION,)


def test_static_analysis_identifies_the_only_truthful_blocker():
    assert ANALYSIS["static_consumer_path_analysis"]["frozen_computation_entry_point_is_single_entrypoint"] is True
    assert ANALYSIS["static_consumer_path_analysis"]["frozen_source_modification_required_for_truthful_real_mode"] is True
    assert ANALYSIS["static_consumer_path_analysis"]["algorithm_duplication_required_if_frozen_source_is_not_modified"] is True
    assert ANALYSIS["static_consumer_path_analysis"]["real_rows_can_remain_explicitly_real_under_current_executor"] is False
    assert ANALYSIS["static_consumer_path_analysis"]["disposition"] == "BLOCKED"


def test_future_contract_gates_are_fail_closed_and_outcome_blind():
    required = {
        "wrong prereg digest",
        "wrong frozen executor digest",
        "frozen executor source mutation",
        "copied/reimplemented algorithm proposal",
        "current-materializer laundering",
        "panel reorder",
        "panel substitution",
        "schedule count drift",
        "boundary-date inclusion",
        "runtime mismatch",
        "real rows labeled SYNTHETIC_VALIDATION",
        "adapter bypassing provenance verification",
        "adapter invoking computation before future claim",
        "adapter silently using V2 result semantics",
        "unauthorized data acquisition",
        "Router/Qnty/trading authority leakage",
    }
    assert set(ANALYSIS["fail_closed_contract_gates"]) == required
    # This phase records static fail-closed gates only; it never executes or
    # materializes a real-evidence path.
    assert CLOSURE["real_outcome_access_performed"] is False
    assert CLOSURE["scientific_execution_performed"] is False
    assert CLOSURE["evaluation_origins_consumed"] == 0


def test_frozen_executor_has_no_real_loader_or_claim_call():
    tree = ast.parse((ROOT / executor.MODULE_RELATIVE_PATH).read_text(encoding="utf-8"))
    names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }
    attributes = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }
    forbidden = {
        "load_verified_frozen_evidence",
        "claim_authorization_once",
        "execute_authorized_frozen_experiment_v2",
        "compute_frozen_experiment",
    }
    assert not forbidden.intersection(names | attributes)
