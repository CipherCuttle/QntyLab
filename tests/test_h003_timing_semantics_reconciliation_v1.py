from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from qntylab.h003_edge_falsification_v0 import net_return_path, reconstruct_h003


ROOT = Path(__file__).resolve().parents[1]
RECONCILIATION_PATH = ROOT / "experiments/research/h003_defensive_followup_v1/timing_semantics_reconciliation_v1.json"
STATE_PATH = ROOT / "experiments/research/state.json"
VARIANT_ID = "variant_00eb140f03a5f6ab40600160"
DECISION_EVENT_ID = "event_decision_232206a8b9e45a253b952b3e"


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_legacy_h003_path_has_one_extra_bar_delay() -> None:
    # 192 completed one-hour bars at 1.0 leave MA48 == MA192. At row 192,
    # the close jumps to 2.0, making the completed-bar raw MA relation LONG.
    # The frozen prose says that decision should own 2.0 -> 4.0 immediately.
    close = np.ones(195, dtype=float)
    close[192] = 2.0
    close[193] = 4.0
    close[194] = 8.0

    position = reconstruct_h003(close)
    net = net_return_path(close, position, total_cost_bps=0.0)

    # strategies._causal moves raw[192] to position[193].
    assert position[192] == 0.0
    assert position[193] == 1.0

    # net_return_path then uses position[:-1] for close[i] -> close[i+1].
    # Therefore the immediately following 2 -> 4 return is not owned, while
    # the later 4 -> 8 return is. This pins the historical double-alignment.
    assert net[192] == 0.0
    assert net[193] == 1.0


def test_reconciliation_preserves_history_and_forbids_pr266_backfill() -> None:
    record = _load(RECONCILIATION_PATH)

    assert record["finding"]["status"] == "CONFIRMED_IMPLEMENTATION_PREREG_DIVERGENCE"
    assert record["finding"]["classification"] == "LEGACY_H003_ONE_EXTRA_BAR_DELAY"
    assert record["historical_evidence_treatment"]["rewrite_forbidden"] is True
    assert record["historical_evidence_treatment"]["rerun_to_replace_existing_results_forbidden"] is True
    assert record["historical_evidence_treatment"]["existing_v0_results_preserved"] is True
    assert record["historical_evidence_treatment"]["original_2023_failure_preserved"] is True

    origin = record["origin_reconciliation"]
    assert origin["pr266_origin_elapsed_before_origin_artifact_was_canonical"] is True
    assert origin["preauthorized_sealed_backfill_rule_present"] is False
    assert origin["research_ledger_activation_transition_present_in_pr266"] is False
    assert origin["pr266_codex_p1_left_unresolved"] is True
    assert origin["owned_prospective_observations_under_pr266_origin"] == "NONE_AUTHORIZED"
    assert origin["backfill_from_2026_09_11T18_00_00Z"] == "FORBIDDEN"


def test_reconciliation_selects_preregistered_intended_semantics_result_blind() -> None:
    record = _load(RECONCILIATION_PATH)
    prospective = record["prospective_semantics"]

    assert prospective["selected_semantics"] == "ORIGINALLY_PREREGISTERED_INTENDED_SEMANTICS"
    assert "without comparing economic results" in prospective["selection_basis"]
    assert "t->t+1 exactly once" in prospective["rule"]
    assert "second evaluator shift" in prospective["implementation_guard"]


def test_research_ledger_is_fail_closed_after_reconciliation() -> None:
    state = _load(STATE_PATH)
    variant = state["variants"][VARIANT_ID]

    assert variant["status"] == "BLOCKED"
    assert variant["latest_decision_event_id"] == DECISION_EVENT_ID
    assert "active_reopen_event_id" not in variant
    assert "reopen_authorization_contract_path" not in variant
    assert "new prospective origin strictly in the future" in variant["revisit_condition"]

    authority = _load(RECONCILIATION_PATH)["authority"]
    assert authority["status"] == "BLOCKED_PENDING_REOPEN_AND_NEW_FUTURE_ORIGIN"
    assert authority["market_data_recording_authorized"] is False
    assert authority["signal_recording_authorized"] is False
    assert authority["integrity_receipt_recording_authorized"] is False
    assert authority["economic_verdict_authorized"] is False
    assert authority["live_execution"] == "FORBIDDEN"
