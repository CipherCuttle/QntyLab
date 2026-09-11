from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from qntylab.h003_defensive_followup_v1_prospective_reopen import (
    prospective_h003_owned_return_path,
    prospective_h003_positions,
)
from qntylab.h003_edge_falsification_v0 import net_return_path, reconstruct_h003


ROOT = Path(__file__).resolve().parents[1]
RECONCILIATION_PATH = ROOT / "experiments/research/h003_defensive_followup_v1/timing_semantics_reconciliation_v1.json"
PROSPECTIVE_REOPEN_CONTRACT_PATH = ROOT / "experiments/specs/h003_defensive_followup_v1_prospective_reopen_v2.json"
STATE_PATH = ROOT / "experiments/research/state.json"
VARIANT_ID = "variant_00eb140f03a5f6ab40600160"
REOPEN_EVENT_ID = "event_reopen_h003_defensive_followup_v1_prospective_v2"


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_legacy_h003_path_has_one_extra_bar_delay() -> None:
    # A falling 192-bar history makes the completed-bar relation at row 191
    # unambiguously FLAT under long_flat. A large row-192 jump makes the raw
    # relation at row 192 unambiguously LONG, avoiding equality/roundoff edges.
    # The frozen prose says that row-192 decision should own 50 -> 100.
    close = np.empty(195, dtype=float)
    close[:192] = np.linspace(3.0, 1.0, 192)
    close[192] = 50.0
    close[193] = 100.0
    close[194] = 200.0

    position = reconstruct_h003(close)
    net = net_return_path(close, position, total_cost_bps=0.0)

    # strategies._causal moves raw[192] to position[193].
    assert position[192] == 0.0
    assert position[193] == 1.0

    # net_return_path then uses position[:-1] for close[i] -> close[i+1].
    # Therefore the immediately following 50 -> 100 return is not owned,
    # while the later 100 -> 200 return is. This pins the legacy extra delay.
    assert net[192] == 0.0
    assert net[193] == 1.0


def test_prospective_h003_completed_bar_owns_next_return_exactly_once() -> None:
    # Build a deterministic one-bar LONG pulse: the completed row-192 MA
    # relation is LONG, while row 193 is FLAT. This lets the fixture distinguish
    # ownership of 192->193 from the following 193->194 return.
    close = np.r_[np.full(144, 0.5), np.full(48, 0.4), 5.2, 0.01, 1.0]

    position = prospective_h003_positions(close)
    owned = prospective_h003_owned_return_path(close)

    assert position[191] == 0.0
    assert position[192] == 1.0
    assert position[193] == 0.0

    expected_192_to_193 = close[193] / close[192] - 1.0
    assert np.isclose(owned[192], expected_192_to_193)
    assert owned[193] == 0.0


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


def test_research_ledger_remains_fail_closed_under_explicit_prospective_reopen() -> None:
    state = _load(STATE_PATH)
    variant = state["variants"][VARIANT_ID]

    # Historical TRIAL_COMPLETED events are replayed after the explicit reopen,
    # so the display status is SCREENING. Authority remains fail-closed because
    # the exact active contract grants no historical trial execution and keeps
    # prospective recording inactive until a separately valid origin-v2.
    assert variant["status"] == "SCREENING"
    assert variant["latest_decision_event_id"] is None
    assert variant["active_reopen_event_id"] == REOPEN_EVENT_ID
    assert variant["reopen_authorization_contract_path"] == "experiments/specs/h003_defensive_followup_v1_prospective_reopen_v2.json"

    contract = _load(PROSPECTIVE_REOPEN_CONTRACT_PATH)
    assert contract["reopen_event_id"] == REOPEN_EVENT_ID
    assert contract["metadata"]["trial_execution_authority"] == "NONE"
    recorder = contract["metadata"]["prospective_recorder"]
    assert recorder["status"] == "ARMED_BUT_INACTIVE_PENDING_VALID_ORIGIN_V2_ARTIFACT"
    assert recorder["origin"] is None
    assert recorder["market_data_recording_authorized"] is False
    assert recorder["signal_recording_authorized"] is False
    assert recorder["integrity_receipt_recording_authorized"] is False
    assert recorder["economic_verdict_authorized"] is False

    authority = _load(RECONCILIATION_PATH)["authority"]
    assert authority["market_data_recording_authorized"] is False
    assert authority["signal_recording_authorized"] is False
    assert authority["integrity_receipt_recording_authorized"] is False
    assert authority["economic_verdict_authorized"] is False
    assert authority["live_execution"] == "FORBIDDEN"
