"""Artificial fixture: market observation (Model B) stays orthogonal to lifecycle.

Proves that an authenticated point observation never becomes, bridges, erases,
or retroactively affects a lifecycle transition computed via
``qntylab.lifecycle.state_at`` / ``eligible_at``. Fully offline/synthetic: no
Binance acquisition, no CMS, no network.
"""
from qntylab.lifecycle import EvidenceEvent, eligible_at, state_at
from qntylab.market_observation import (
    INVALID,
    NOT_OBSERVED_IN_CAPTURE,
    OBSERVED,
    UNKNOWN,
    Capture,
    InstrumentIdentity,
    MarketObservation,
    observed_at,
)


# --- Fixture identities -----------------------------------------------------

S1 = InstrumentIdentity(symbol="BTCUSDT", market="usd-m", contract_type="perpetual",
                         instrument_instance_id="binance|BTCUSDT|perpetual|usd-m|2024-01-01T00:00:00Z")
S2 = InstrumentIdentity(symbol="BTCUSDT", market="usd-m", contract_type="perpetual",
                         instrument_instance_id="binance|BTCUSDT|perpetual|usd-m|2025-01-01T00:00:00Z")
WRONG_MARKET = InstrumentIdentity(symbol="BTCUSDT", market="spot", contract_type="spot",
                                   instrument_instance_id="binance|BTCUSDT|spot|spot|2024-01-01T00:00:00Z")

CAPTURE_S1_SOURCE_KEY = "binance-usdm-agg-trades-2024-06-01"
CAPTURE_S1_HASH = "a" * 64
CAPTURE_S2_SOURCE_KEY = "binance-usdm-agg-trades-2025-06-01"
CAPTURE_S2_HASH = "c" * 64
CAPTURE_WRONG_MARKET_SOURCE_KEY = "binance-spot-agg-trades-2024-06-01"
CAPTURE_WRONG_MARKET_HASH = "d" * 64

OBS_S1_0900 = MarketObservation(identity=S1, timestamp="2024-06-01T09:00:00Z",
                                 source_key=CAPTURE_S1_SOURCE_KEY,
                                 local_content_sha256=CAPTURE_S1_HASH)
OBS_S1_1600 = MarketObservation(identity=S1, timestamp="2024-06-01T16:00:00Z",
                                 source_key=CAPTURE_S1_SOURCE_KEY,
                                 local_content_sha256=CAPTURE_S1_HASH)
OBS_S2_LATER = MarketObservation(identity=S2, timestamp="2025-06-01T09:00:00Z",
                                  source_key=CAPTURE_S2_SOURCE_KEY,
                                  local_content_sha256=CAPTURE_S2_HASH)
OBS_WRONG_MARKET = MarketObservation(identity=WRONG_MARKET, timestamp="2024-06-01T09:00:00Z",
                                      source_key=CAPTURE_WRONG_MARKET_SOURCE_KEY,
                                      local_content_sha256=CAPTURE_WRONG_MARKET_HASH)

CAPTURE_S1 = Capture(identity=S1, observations=(OBS_S1_0900, OBS_S1_1600),
                      source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256=CAPTURE_S1_HASH)
CAPTURE_S2 = Capture(identity=S2, observations=(OBS_S2_LATER,),
                      source_key=CAPTURE_S2_SOURCE_KEY, local_content_sha256=CAPTURE_S2_HASH)
CAPTURE_WRONG_MARKET = Capture(identity=WRONG_MARKET, observations=(OBS_WRONG_MARKET,),
                                source_key=CAPTURE_WRONG_MARKET_SOURCE_KEY,
                                local_content_sha256=CAPTURE_WRONG_MARKET_HASH)

# S1's lifecycle stream: suspended at 10:00, terminated at 17:00. Never touched
# by any observed_at() call in this file.
S1_EVENTS = [
    EvidenceEvent("2024-06-01T00:00:00Z", "TRADABLE", "A", "binance", S1.instrument_instance_id),
    EvidenceEvent("2024-06-01T10:00:00Z", "TEMPORARILY_UNOBSERVABLE", "A", "binance", S1.instrument_instance_id),
    EvidenceEvent("2024-06-01T17:00:00Z", "TERMINATED_VERIFIED", "A", "binance", S1.instrument_instance_id),
]


def _frozen_snapshot(events):
    return [(event.event_time, event.claim, event.grade, event.source, event.raw_identity) for event in events]


# --- Observation isolation --------------------------------------------------

def test_exact_observation_returns_observed():
    assert observed_at(CAPTURE_S1, S1, "2024-06-01T09:00:00Z") == OBSERVED


def test_observation_creates_no_evidence_event():
    before = _frozen_snapshot(S1_EVENTS)
    observed_at(CAPTURE_S1, S1, "2024-06-01T09:00:00Z")
    assert _frozen_snapshot(S1_EVENTS) == before
    assert all(not isinstance(row, MarketObservation) for row in S1_EVENTS)


# --- Suspension: no bridging -------------------------------------------------

def test_0900_observation_does_not_bridge_1000_suspension_to_1200():
    observed_at(CAPTURE_S1, S1, "2024-06-01T09:00:00Z")  # evaluate observation first
    assert state_at(S1_EVENTS, "2024-06-01T12:00:00Z") == "TEMPORARILY_UNOBSERVABLE"
    assert eligible_at(S1_EVENTS, "2024-06-01T12:00:00Z") is False


# --- No retrocausality -------------------------------------------------------

def test_1600_observation_does_not_retroactively_affect_1200():
    at_1200_before = eligible_at(S1_EVENTS, "2024-06-01T12:00:00Z")
    observed_at(CAPTURE_S1, S1, "2024-06-01T16:00:00Z")
    assert observed_at(CAPTURE_S1, S1, "2024-06-01T16:00:00Z") == OBSERVED
    assert eligible_at(S1_EVENTS, "2024-06-01T12:00:00Z") == at_1200_before is False


# --- Termination remains terminal -------------------------------------------

def test_termination_remains_terminal_despite_later_observation():
    assert state_at(S1_EVENTS, "2024-06-01T18:00:00Z") == "TERMINATED_VERIFIED"
    observed_at(CAPTURE_S1, S1, "2024-06-01T16:00:00Z")
    assert state_at(S1_EVENTS, "2024-06-01T18:00:00Z") == "TERMINATED_VERIFIED"
    assert eligible_at(S1_EVENTS, "2024-06-01T18:00:00Z") is False


# --- Reuse / relisting: S2 must not touch S1 --------------------------------

def test_s2_same_symbol_observation_does_not_affect_s1():
    assert observed_at(CAPTURE_S2, S2, "2025-06-01T09:00:00Z") == OBSERVED
    # S1 lifecycle state is unaffected by any S2 observation.
    assert state_at(S1_EVENTS, "2025-06-01T12:00:00Z") == "TERMINATED_VERIFIED"
    # S2's capture must not satisfy an S1 identity query, even same ticker string.
    assert observed_at(CAPTURE_S2, S1, "2025-06-01T09:00:00Z") == INVALID
    assert S1.instrument_instance_id != S2.instrument_instance_id
    assert S1.symbol == S2.symbol


# --- Wrong-market adversary --------------------------------------------------

def test_wrong_market_does_not_match():
    assert observed_at(CAPTURE_WRONG_MARKET, S1, "2024-06-01T09:00:00Z") == INVALID


# --- Missing-evidence adversary ----------------------------------------------

def test_missing_capture_returns_unknown_never_not_tradable():
    result = observed_at(None, S1, "2024-06-01T09:00:00Z")
    assert result == UNKNOWN
    assert result != "NOT_TRADABLE"


# --- Capture-without-match adversary -----------------------------------------

def test_valid_capture_no_exact_timestamp_returns_not_observed_in_capture():
    result = observed_at(CAPTURE_S1, S1, "2024-06-01T09:00:01Z")  # one second off; no tolerance
    assert result == NOT_OBSERVED_IN_CAPTURE
    # NOT_OBSERVED_IN_CAPTURE must never be interpreted as NOT_TRADABLE.
    assert result != "NOT_TRADABLE"


# --- No observation result mutates lifecycle state --------------------------

def test_no_observation_result_mutates_lifecycle_state():
    before = _frozen_snapshot(S1_EVENTS)
    for capture, identity, at in (
        (CAPTURE_S1, S1, "2024-06-01T09:00:00Z"),
        (CAPTURE_S1, S1, "2024-06-01T09:00:01Z"),
        (None, S1, "2024-06-01T09:00:00Z"),
        (CAPTURE_WRONG_MARKET, S1, "2024-06-01T09:00:00Z"),
        (CAPTURE_S2, S2, "2025-06-01T09:00:00Z"),
    ):
        observed_at(capture, identity, at)
    assert _frozen_snapshot(S1_EVENTS) == before


# --- H01: capture provenance binding -----------------------------------------

def test_cross_capture_injected_observation_returns_invalid():
    # O_A genuinely belongs to CAPTURE_S1 (its provenance matches). An
    # attacker constructs a "Capture B" with different provenance but
    # smuggles O_A's exact observation object into it.
    forged_capture = Capture(
        identity=S1,
        observations=(OBS_S1_0900,),
        source_key="attacker-controlled-source",
        local_content_sha256="9" * 64,
    )
    assert observed_at(forged_capture, S1, "2024-06-01T09:00:00Z") == INVALID


def test_same_source_key_wrong_hash_returns_invalid():
    forged_capture = Capture(
        identity=S1,
        observations=(OBS_S1_0900,),
        source_key=CAPTURE_S1_SOURCE_KEY,  # matches
        local_content_sha256="f" * 64,     # does not match
    )
    assert observed_at(forged_capture, S1, "2024-06-01T09:00:00Z") == INVALID


def test_wrong_source_key_same_hash_returns_invalid():
    forged_capture = Capture(
        identity=S1,
        observations=(OBS_S1_0900,),
        source_key="different-source",   # does not match
        local_content_sha256=CAPTURE_S1_HASH,  # matches
    )
    assert observed_at(forged_capture, S1, "2024-06-01T09:00:00Z") == INVALID


def test_genuine_observation_still_returns_observed_after_binding_repair():
    # Reject-all guard: the binding check must not degenerate into rejecting
    # legitimate, correctly-bound evidence.
    assert observed_at(CAPTURE_S1, S1, "2024-06-01T09:00:00Z") == OBSERVED


# --- H02: structural / malformed-evidence validation -------------------------

def test_empty_local_content_sha256_returns_invalid():
    bad_obs = MarketObservation(identity=S1, timestamp="2024-06-01T09:00:00Z",
                                 source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256="")
    bad_capture = Capture(identity=S1, observations=(bad_obs,),
                           source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256="")
    assert observed_at(bad_capture, S1, "2024-06-01T09:00:00Z") == INVALID


def test_malformed_local_content_sha256_returns_invalid():
    bad_obs = MarketObservation(identity=S1, timestamp="2024-06-01T09:00:00Z",
                                 source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256="not-a-hash")
    bad_capture = Capture(identity=S1, observations=(bad_obs,),
                           source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256="not-a-hash")
    assert observed_at(bad_capture, S1, "2024-06-01T09:00:00Z") == INVALID


def test_short_hash_returns_invalid():
    bad_obs = MarketObservation(identity=S1, timestamp="2024-06-01T09:00:00Z",
                                 source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256="a" * 10)
    bad_capture = Capture(identity=S1, observations=(bad_obs,),
                           source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256="a" * 10)
    assert observed_at(bad_capture, S1, "2024-06-01T09:00:00Z") == INVALID


def test_whitespace_only_hash_returns_invalid():
    bad_capture = Capture(identity=S1, observations=(OBS_S1_0900,),
                           source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256=" " * 64)
    assert observed_at(bad_capture, S1, "2024-06-01T09:00:00Z") == INVALID


def test_empty_timestamp_query_returns_invalid():
    assert observed_at(CAPTURE_S1, S1, "") == INVALID


def test_malformed_timestamp_query_returns_invalid():
    assert observed_at(CAPTURE_S1, S1, "not-a-timestamp") == INVALID


def test_empty_timestamp_observation_returns_invalid():
    bad_obs = MarketObservation(identity=S1, timestamp="",
                                 source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256=CAPTURE_S1_HASH)
    bad_capture = Capture(identity=S1, observations=(bad_obs,),
                           source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256=CAPTURE_S1_HASH)
    # Query the capture's identity with an empty timestamp: query-side
    # validation must reject before ever reaching the malformed observation.
    assert observed_at(bad_capture, S1, "") == INVALID


def test_empty_symbol_returns_invalid():
    bad_identity = InstrumentIdentity(symbol="", market="usd-m", contract_type="perpetual",
                                       instrument_instance_id=S1.instrument_instance_id)
    assert observed_at(CAPTURE_S1, bad_identity, "2024-06-01T09:00:00Z") == INVALID


def test_empty_market_returns_invalid():
    bad_identity = InstrumentIdentity(symbol="BTCUSDT", market="", contract_type="perpetual",
                                       instrument_instance_id=S1.instrument_instance_id)
    assert observed_at(CAPTURE_S1, bad_identity, "2024-06-01T09:00:00Z") == INVALID


def test_empty_contract_type_returns_invalid():
    bad_identity = InstrumentIdentity(symbol="BTCUSDT", market="usd-m", contract_type="",
                                       instrument_instance_id=S1.instrument_instance_id)
    assert observed_at(CAPTURE_S1, bad_identity, "2024-06-01T09:00:00Z") == INVALID


def test_empty_instrument_instance_id_returns_invalid():
    bad_identity = InstrumentIdentity(symbol="BTCUSDT", market="usd-m", contract_type="perpetual",
                                       instrument_instance_id="")
    assert observed_at(CAPTURE_S1, bad_identity, "2024-06-01T09:00:00Z") == INVALID


def test_whitespace_only_identity_field_returns_invalid():
    bad_identity = InstrumentIdentity(symbol="   ", market="usd-m", contract_type="perpetual",
                                       instrument_instance_id=S1.instrument_instance_id)
    assert observed_at(CAPTURE_S1, bad_identity, "2024-06-01T09:00:00Z") == INVALID


def test_empty_source_key_on_capture_returns_invalid():
    bad_capture = Capture(identity=S1, observations=(OBS_S1_0900,),
                           source_key="", local_content_sha256=CAPTURE_S1_HASH)
    assert observed_at(bad_capture, S1, "2024-06-01T09:00:00Z") == INVALID


def test_empty_source_key_on_observation_returns_invalid():
    bad_obs = MarketObservation(identity=S1, timestamp="2024-06-01T09:00:00Z",
                                 source_key="", local_content_sha256=CAPTURE_S1_HASH)
    bad_capture = Capture(identity=S1, observations=(bad_obs,),
                           source_key="", local_content_sha256=CAPTURE_S1_HASH)
    assert observed_at(bad_capture, S1, "2024-06-01T09:00:00Z") == INVALID


def test_whitespace_only_source_key_returns_invalid():
    bad_capture = Capture(identity=S1, observations=(OBS_S1_0900,),
                           source_key="   ", local_content_sha256=CAPTURE_S1_HASH)
    assert observed_at(bad_capture, S1, "2024-06-01T09:00:00Z") == INVALID


# --- Reject-all adversary guard ------------------------------------------------

def test_valid_capture_no_exact_observation_still_not_observed_in_capture_after_repair():
    # Must not have degenerated into INVALID-for-everything: a structurally
    # sound capture with no exact match is still NOT_OBSERVED_IN_CAPTURE.
    assert observed_at(CAPTURE_S1, S1, "2024-06-01T09:00:01Z") == NOT_OBSERVED_IN_CAPTURE


# --- H02: regex-shaped but calendar/clock-impossible timestamps -------------
# The regex alone accepts strings that no UTC calendar date/time can
# represent (e.g. February 31st) or that no clock can display (e.g. 24:00:00,
# a 60th minute, a 60th second). These must be rejected as INVALID, on both
# the query side and the stored-observation side, without loosening the
# frozen YYYY-MM-DDTHH:MM:SSZ format.

def test_impossible_calendar_date_query_returns_invalid():
    assert observed_at(CAPTURE_S1, S1, "2026-02-31T12:00:00Z") == INVALID


def test_month_13_query_returns_invalid():
    assert observed_at(CAPTURE_S1, S1, "2026-13-01T12:00:00Z") == INVALID


def test_month_00_query_returns_invalid():
    assert observed_at(CAPTURE_S1, S1, "2026-00-01T12:00:00Z") == INVALID


def test_day_00_query_returns_invalid():
    assert observed_at(CAPTURE_S1, S1, "2026-01-00T12:00:00Z") == INVALID


def test_day_32_query_returns_invalid():
    assert observed_at(CAPTURE_S1, S1, "2026-01-32T12:00:00Z") == INVALID


def test_hour_24_query_returns_invalid():
    assert observed_at(CAPTURE_S1, S1, "2026-01-01T24:00:00Z") == INVALID


def test_minute_60_query_returns_invalid():
    assert observed_at(CAPTURE_S1, S1, "2026-01-01T23:60:00Z") == INVALID


def test_second_60_query_returns_invalid():
    assert observed_at(CAPTURE_S1, S1, "2026-01-01T23:59:60Z") == INVALID


def test_non_leap_year_feb_29_query_returns_invalid():
    # 2025 is not a leap year: Feb 29 does not exist.
    assert observed_at(CAPTURE_S1, S1, "2025-02-29T12:00:00Z") == INVALID


def test_leap_year_feb_29_is_valid_calendar_date():
    # 2024 is a leap year: Feb 29 is a genuine calendar date. No capture
    # covers this identity/timestamp, so the correct result is
    # NOT_OBSERVED_IN_CAPTURE, not INVALID -- proving the date itself passed
    # validation.
    assert observed_at(CAPTURE_S1, S1, "2024-02-29T12:00:00Z") == NOT_OBSERVED_IN_CAPTURE


def test_impossible_observation_timestamp_returns_invalid():
    # The stored MarketObservation itself carries a calendar-impossible
    # timestamp; the query timestamp is well-formed syntax but happens to
    # equal the same impossible string, and the capture is otherwise valid.
    bad_obs = MarketObservation(identity=S1, timestamp="2026-02-31T12:00:00Z",
                                 source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256=CAPTURE_S1_HASH)
    bad_capture = Capture(identity=S1, observations=(OBS_S1_0900, bad_obs),
                           source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256=CAPTURE_S1_HASH)
    assert observed_at(bad_capture, S1, "2026-02-31T12:00:00Z") == INVALID


def test_non_canonical_single_digit_month_day_rejected():
    # The frozen representation requires two-digit month/day; a parser must
    # not silently normalize "2026-1-1..." into a canonical timestamp.
    assert observed_at(CAPTURE_S1, S1, "2026-1-1T12:00:00Z") == INVALID


def test_valid_ordinary_timestamp_still_returns_observed():
    # Reject-all guard: an exact, calendar-valid timestamp on a genuine
    # observation must still resolve to OBSERVED after the repair.
    assert observed_at(CAPTURE_S1, S1, "2024-06-01T09:00:00Z") == OBSERVED


# --- H02 final repair: capture-wide validation before lookup -----------------
# Four-case truth table (section 10 of the fixture spec).

def test_case_a_valid_capture_matching_valid_row_returns_observed():
    assert observed_at(CAPTURE_S1, S1, "2024-06-01T09:00:00Z") == OBSERVED


def test_case_b_valid_capture_no_matching_valid_row_returns_not_observed_in_capture():
    assert observed_at(CAPTURE_S1, S1, "2024-06-01T16:00:00Z" ) == OBSERVED  # sanity: this row exists
    assert observed_at(CAPTURE_S1, S1, "2024-06-01T23:00:00Z") == NOT_OBSERVED_IN_CAPTURE


def test_case_c_invalid_capture_matching_malformed_row_returns_invalid():
    bad_obs = MarketObservation(identity=S1, timestamp="2026-02-31T12:00:00Z",
                                 source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256=CAPTURE_S1_HASH)
    bad_capture = Capture(identity=S1, observations=(OBS_S1_0900, bad_obs),
                           source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256=CAPTURE_S1_HASH)
    assert observed_at(bad_capture, S1, "2026-02-31T12:00:00Z") == INVALID


def test_case_d_invalid_capture_nonmatching_malformed_row_returns_invalid():
    # Load-bearing regression: a malformed stored observation that does NOT
    # match the query must still invalidate the whole capture, not be
    # silently skipped by the lookup loop.
    bad_obs = MarketObservation(identity=S1, timestamp="2026-02-31T12:00:00Z",
                                 source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256=CAPTURE_S1_HASH)
    bad_capture = Capture(identity=S1, observations=(OBS_S1_0900, bad_obs),
                           source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256=CAPTURE_S1_HASH)
    assert observed_at(bad_capture, S1, "2024-06-01T09:00:00Z") == INVALID


def test_case_d_provenance_nonmatching_foreign_row_returns_invalid():
    # A row with foreign provenance (wrong source_key/hash) that does not
    # match the query timestamp must still invalidate the capture.
    foreign_obs = MarketObservation(identity=S1, timestamp="2099-01-01T00:00:00Z",
                                     source_key="source_B", local_content_sha256="b" * 64)
    bad_capture = Capture(identity=S1, observations=(OBS_S1_0900, foreign_obs),
                           source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256=CAPTURE_S1_HASH)
    assert observed_at(bad_capture, S1, "2024-06-01T09:00:00Z") == INVALID


def test_case_d_identity_nonmatching_malformed_row_returns_invalid():
    # A row with an invalid identity field that does not match the query
    # timestamp must still invalidate the capture.
    bad_identity = InstrumentIdentity(symbol="", market="usd-m", contract_type="perpetual",
                                       instrument_instance_id=S1.instrument_instance_id)
    bad_obs = MarketObservation(identity=bad_identity, timestamp="2099-01-01T00:00:00Z",
                                 source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256=CAPTURE_S1_HASH)
    bad_capture = Capture(identity=S1, observations=(OBS_S1_0900, bad_obs),
                           source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256=CAPTURE_S1_HASH)
    assert observed_at(bad_capture, S1, "2024-06-01T09:00:00Z") == INVALID


def test_malformed_capture_validity_independent_of_queried_timestamp():
    # Whether a capture is structurally valid must not depend on which
    # timestamp the caller happens to query.
    bad_obs = MarketObservation(identity=S1, timestamp="2026-02-31T12:00:00Z",
                                 source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256=CAPTURE_S1_HASH)
    bad_capture = Capture(identity=S1, observations=(OBS_S1_0900, bad_obs),
                           source_key=CAPTURE_S1_SOURCE_KEY, local_content_sha256=CAPTURE_S1_HASH)
    for at in ("2024-06-01T09:00:00Z", "2024-06-01T16:00:00Z", "2099-01-01T00:00:00Z"):
        assert observed_at(bad_capture, S1, at) == INVALID
