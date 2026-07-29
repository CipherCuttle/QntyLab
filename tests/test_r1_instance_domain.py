import copy

from qntylab.r1_instance_domain import canonical_bytes, canonical_hash, candidate_population, compile_domain


def fixtures():
    tardis = [{"id": "OLDUSDT", "availableSince": "2021-01-01T00:00:00Z", "availableTo": "2022-01-01T00:00:00Z"}, {"id": "LIVEUSDT", "availableSince": "2022-01-01T00:00:00Z"}]
    current = [{"symbol": "LIVEUSDT", "baseCoin": "LIVE", "quoteCoin": "USDT", "contractType": "LinearPerpetual", "launchTime": "1640995200000", "status": "Trading", "symbolId": 1}, {"symbol": "REUSEUSDT", "baseCoin": "REUSE", "quoteCoin": "USDT", "contractType": "LinearPerpetual", "launchTime": "1640995200000", "status": "Trading", "symbolId": 2}]
    reuse = [{"symbol": "REUSEUSDT"}]
    announcements = [{"title": "Delisting of OLDUSDT Perpetual", "dateTimestamp": 1650000000000}]
    return tardis, current, announcements, reuse


def test_complete_accounting_and_repeatability():
    tardis, current, announcements, reuse = fixtures(); domain = compile_domain(candidate_population(tardis, current), announcements, reuse)
    assert domain["candidate_population_count"] == domain["accounted_candidate_count"] == 3
    assert domain["unaccounted_candidates"] == domain["silently_dropped_candidates"] == 0
    assert canonical_bytes(domain) == canonical_bytes(copy.deepcopy(domain)) == canonical_bytes(compile_domain(list(reversed(candidate_population(tardis, current))), announcements, reuse))


def test_duplicate_candidates_fail_and_current_membership_cannot_filter_domain():
    tardis, current, _, _ = fixtures()
    try: candidate_population(tardis + [tardis[0]], current)
    except ValueError: pass
    else: raise AssertionError("duplicate candidate accepted")
    assert {row["symbol"] for row in candidate_population(tardis, current)} == {"OLDUSDT", "LIVEUSDT", "REUSEUSDT"}


def test_reuse_terminal_open_and_future_states_are_explicit():
    tardis, current, announcements, reuse = fixtures(); domain = compile_domain(candidate_population(tardis, current), announcements, reuse)
    assert domain["counts"]["identity_ambiguous"] == 2 and domain["counts"]["ambiguous_terminals"] >= 1 and domain["counts"]["open_at_cutoff"] >= 1
    future = [{"id": "FUTUREUSDT", "availableSince": "2026-07-01T00:00:00Z"}]
    assert compile_domain(candidate_population(future, []), [], [])["counts"]["future_reservoir_excluded"] == 1


def test_hash_is_canonical():
    tardis, current, announcements, reuse = fixtures(); domain = compile_domain(candidate_population(tardis, current), announcements, reuse)
    assert canonical_hash(domain) == canonical_hash(copy.deepcopy(domain))


def test_verified_launch_ambiguous_start_and_duplicate_evidence_are_explicit():
    candidate = {"source_candidate_id": "bybit|VERIFIEDUSDT|linearperpetual", "symbol": "VERIFIEDUSDT", "base": "VERIFIED", "quote": "USDT", "contract_type": "LinearPerpetual", "official_launch_time": "2022-01-01T00:00:00Z", "official_terminal_time": "2022-02-01T00:00:00Z", "tardis_available_since": None, "tardis_available_to": None, "evidence_sources": ["official_listing"]}
    domain = compile_domain([candidate], [], [])
    assert domain["instances"][0]["start_state"] == "VERIFIED_LAUNCH" and domain["instances"][0]["end_state"] == "VERIFIED_TERMINAL"
    tardis, current, announcements, reuse = fixtures()
    assert canonical_hash(compile_domain(candidate_population(tardis, current), announcements, reuse)) == canonical_hash(compile_domain(candidate_population(tardis, current), announcements + announcements, reuse))


def test_future_event_cannot_create_pre_cutoff_terminal():
    tardis, current, _, reuse = fixtures()
    future_only = [{"title": "Delisting of OLDUSDT Perpetual", "dateTimestamp": 1782864000000}]
    domain = compile_domain(candidate_population(tardis, current), future_only, reuse)
    old = next(row for row in domain["instances"] if row["symbol"] == "OLDUSDT")
    assert old["end_state"] == "AMBIGUOUS_TERMINAL"
