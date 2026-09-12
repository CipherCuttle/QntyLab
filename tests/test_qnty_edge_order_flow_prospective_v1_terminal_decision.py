from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREREG = (
    ROOT
    / "experiments"
    / "research"
    / "qnty_edge_discovery_order_flow_v1"
    / "preregistration.json"
)


def test_terminal_integrity_failure_precedes_scientific_non_support() -> None:
    doc = json.loads(PREREG.read_text(encoding="utf-8"))
    decision = doc["terminal_decision_contract"]
    gate = doc["terminal_support_gate"]

    assert "integrity" in decision["decision_order"].lower()
    assert "precedence" in decision["decision_order"].lower()
    assert gate["integrity_failure_label"] == "INCONCLUSIVE_PROSPECTIVE_INTEGRITY_FAILURE"
    assert "failed_label" in decision["integrity_failure_action"]
    assert "do not emit" in decision["integrity_failure_action"]
    assert "evidence against" in decision["integrity_failure_action"]

    preconditions = decision["integrity_preconditions"]
    assert any("2592 valid origins" in item for item in preconditions)
    assert any("no backfill" in item for item in preconditions)
    assert any("full column rank" in item for item in preconditions)
    assert any("terminal outcome tail" in item for item in preconditions)


def test_scientific_failure_is_only_reachable_after_integrity_pass() -> None:
    doc = json.loads(PREREG.read_text(encoding="utf-8"))
    decision = doc["terminal_decision_contract"]

    support = decision["scientific_support_conditions_after_integrity_pass"]
    assert len(support) == 4
    assert any("pooled beta" in item for item in support)
    assert any("p-value <= 0.01" in item for item in support)
    assert any("4 of 5" in item for item in support)
    assert any("concentration share" in item for item in support)
    assert "Only after all integrity preconditions pass" in decision["scientific_failure_action"]


def test_row_validity_rules_must_freeze_before_first_real_warmup_close() -> None:
    doc = json.loads(PREREG.read_text(encoding="utf-8"))
    deadline = doc["terminal_decision_contract"]["recorder_validity_freeze_deadline"]

    assert "2026-09-15T00:00:00Z" in deadline
    assert "machine-checkable row-validity rules" in deadline
    assert "may not change" in deadline
    assert "may not add discretionary magnitude-based filtering" in deadline
