from qntylab.lifecycle import EvidenceEvent, eligible_at, instrument_instance_id, receipt_root, state_at, terminal_policy


def test_lifecycle_state_is_causal_and_gap_is_not_tradable():
    events = [
        EvidenceEvent("2024-01-01T00:00:00Z", "PRELAUNCH", "A", "bybit", "a"),
        EvidenceEvent("2024-01-02T00:00:00Z", "TRADABLE", "B", "tardis", "b"),
        EvidenceEvent("2024-01-03T00:00:00Z", "TEMPORARILY_UNOBSERVABLE", "B", "tardis", "c"),
    ]
    assert state_at(events, "2024-01-01T12:00:00Z") == "PRELAUNCH"
    assert eligible_at(events, "2024-01-02T12:00:00Z")
    assert not eligible_at(events, "2024-01-03T12:00:00Z")


def test_identity_and_terminal_policy_fail_closed():
    assert instrument_instance_id(venue="bybit", symbol="abcusdt", contract_type="LinearPerpetual", first_observed="2024-01-01T00:00:00Z") != instrument_instance_id(venue="bybit", symbol="abcusdt", contract_type="LinearPerpetual", first_observed="2025-01-01T00:00:00Z")
    assert terminal_policy(state="TERMINATED_AMBIGUOUS", exposed=True, settlement_available=False) == "BLOCKED_BY_DATA_INTEGRITY"
    assert terminal_policy(state="TERMINATED_AMBIGUOUS", exposed=False, settlement_available=False) == "REMOVE_AFTER_LAST_VERIFIED_TRADABLE_STATE"


def test_receipt_root_is_deterministic():
    rows = [{"source": "a", "sha256": "1"}, {"source": "b", "sha256": "2"}]
    assert receipt_root(rows) == receipt_root(reversed(rows))
