from __future__ import annotations

from qntylab.research_ledger import CanonicalHistory, replay


VARIANT_ID = "variant_reopen_chronology_test"
CANDIDATE_ID = "CANDIDATE_REOPEN_CHRONOLOGY_TEST"
FAMILY_ID = "REOPEN_CHRONOLOGY_TEST"
OLD_DECISION = "event_old_terminal"
REOPEN = "event_reopen_terminal"
NEW_DECISION = "event_new_terminal"


def _proposal() -> dict:
    return {
        "event_type": "CANDIDATE_PROPOSED",
        "event_id": "event_proposal_terminal",
        "candidate_id": CANDIDATE_ID,
        "family_id": FAMILY_ID,
        "variant_id": VARIANT_ID,
    }


def _decision(event_id: str, recorded_at: str, status: str = "GRAVEYARDED") -> dict:
    return {
        "event_type": "DECISION_RECORDED",
        "event_id": event_id,
        "candidate_id": CANDIDATE_ID,
        "family_id": FAMILY_ID,
        "variant_id": VARIANT_ID,
        "status": status,
        "scope": "EXACT_VARIANT",
        "revisit_condition": "explicit reopen required",
        "recorded_at_utc": recorded_at,
    }


def _reopen() -> dict:
    return {
        "event_type": "CANDIDATE_REOPENED",
        "event_id": REOPEN,
        "candidate_id": CANDIDATE_ID,
        "variant_id": VARIANT_ID,
        "previous_decision_event_id": OLD_DECISION,
        "recorded_at_utc": "2026-01-02T00:00:00Z",
    }


def test_consumed_reopen_does_not_clear_later_terminal_decision() -> None:
    history = CanonicalHistory(
        candidates=(_proposal(), _reopen()),
        decisions=(
            _decision(OLD_DECISION, "2026-01-01T00:00:00Z"),
            _decision(NEW_DECISION, "2026-01-03T00:00:00Z"),
        ),
        trials=(),
        generated_from={},
    )

    state, _trial_index, issues = replay(history)

    assert issues == []
    variant = state["variants"][VARIANT_ID]
    assert variant["status"] == "GRAVEYARDED"
    assert variant["latest_decision_event_id"] == NEW_DECISION
    assert variant["revisit_condition"] == "explicit reopen required"


def test_unconsumed_reopen_still_clears_targeted_terminal_decision() -> None:
    history = CanonicalHistory(
        candidates=(_proposal(), _reopen()),
        decisions=(_decision(OLD_DECISION, "2026-01-01T00:00:00Z"),),
        trials=(),
        generated_from={},
    )

    state, _trial_index, issues = replay(history)

    assert issues == []
    variant = state["variants"][VARIANT_ID]
    assert variant["status"] == "PROPOSED"
    assert variant["latest_decision_event_id"] is None
