from datetime import datetime, timezone

from qntylab.free_census import (
    classify_announcement,
    find_matching_delistings,
    pit_eligible_count,
    relist_gap_days,
    symbol_mentioned,
)


def test_symbol_mentioned_rejects_substring_false_positives():
    # These are real false positives observed against the live Bybit feed.
    assert not symbol_mentioned("LUNAUSDT", "Delisting of QORPO, OBOL, LUNAI, TUNA and WEETH")
    assert not symbol_mentioned("ANTUSDT", "Token swap and rebranding of MANTRA (OM) to MANTRA (MANTRA)")
    assert not symbol_mentioned("BITUSDT", "Bybit Alpha: Notice of removal of 2 tokens")


def test_symbol_mentioned_accepts_true_positives():
    assert symbol_mentioned("AGIXUSDT", "Delisting of FETUSDT, OCEANUSDT, and AGIXUSDT Perpetual Contracts")
    assert symbol_mentioned("FTTUSDT", "Updated Delisting Time of FTTUSDT Contract")
    assert symbol_mentioned("10000NFTUSDT", "Delisting of  10000NFTUSDT Perpetual Contract")


def test_classify_announcement_covers_required_classes():
    assert classify_announcement("New listing: TBTUSDT Perpetual Contract", queried_type="new_crypto") == "PERP_LISTING"
    assert classify_announcement("Delisting of AGIXUSDT Perpetual Contract") == "PERP_DELISTING"
    assert classify_announcement("Relisting of XUSDT Perpetual Contract") == "PERP_RELIST"
    assert classify_announcement("Rebranding of XToken to YToken") == "REBRAND"
    assert classify_announcement("Contract migration and token swap for ZUSDT") == "CONTRACT_MIGRATION"
    assert classify_announcement("Update to funding rate interval methodology") == "FUNDING_CHANGE"
    assert classify_announcement("Scheduled system maintenance notice") == "OTHER"


def test_find_matching_delistings_filters_precisely():
    announcements = [
        {"title": "Delisting of FETUSDT, OCEANUSDT, and AGIXUSDT Perpetual Contracts"},
        {"title": "Delisting of QORPO, OBOL, LUNAI, TUNA and WEETH"},
    ]
    hits = find_matching_delistings("AGIXUSDT", announcements)
    assert len(hits) == 1
    assert find_matching_delistings("LUNAUSDT", announcements) == []


def test_relist_gap_days_flags_reuse_candidates():
    # LITUSDT: current launch far after first independent recording -> reuse candidate.
    gap = relist_gap_days("2025-12-30T00:00:00.000Z", "2021-11-29T00:00:00.000Z")
    assert gap > 900
    # A launch that matches first observation within noise is not a reuse candidate.
    gap2 = relist_gap_days("2024-01-01T00:00:00Z", "2023-12-20T00:00:00.000Z")
    assert gap2 < 30


def test_pit_eligible_count_requires_both_market_and_funding_coverage():
    markets = [
        {"min_time": "2021-01-01T00:00:00Z", "max_time": "2026-01-01T00:00:00Z",
         "funding_rates": {"min_time": "2021-01-01T00:00:00Z", "max_time": "2026-01-01T00:00:00Z"}},
        # market data present but no funding coverage yet at `at` -> not eligible
        {"min_time": "2021-01-01T00:00:00Z", "max_time": "2026-01-01T00:00:00Z",
         "funding_rates": {"min_time": "2023-01-01T00:00:00Z", "max_time": "2026-01-01T00:00:00Z"}},
        # neither window covers `at`
        {"min_time": "2025-01-01T00:00:00Z", "max_time": "2026-01-01T00:00:00Z",
         "funding_rates": {"min_time": "2025-01-01T00:00:00Z", "max_time": "2026-01-01T00:00:00Z"}},
    ]
    at = datetime(2022, 6, 1, tzinfo=timezone.utc)
    assert pit_eligible_count(markets, at) == 1


def test_pit_eligible_count_handles_missing_funding_gracefully():
    markets = [{"min_time": "2021-01-01T00:00:00Z", "max_time": "2026-01-01T00:00:00Z"}]
    at = datetime(2022, 6, 1, tzinfo=timezone.utc)
    assert pit_eligible_count(markets, at) == 0
