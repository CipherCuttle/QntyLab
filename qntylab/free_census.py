"""Outcome-blind free-source census primitives for the R1 lifecycle survey.

These helpers turn raw public announcement/catalog records into structural
lifecycle and coverage facts only. There is no price, return, ranking,
portfolio, or PnL concept anywhere in this module.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable

ANNOUNCEMENT_CLASSES = (
    "PERP_LISTING",
    "PERP_DELISTING",
    "PERP_RELIST",
    "REBRAND",
    "CONTRACT_MIGRATION",
    "FUNDING_CHANGE",
    "OTHER",
    "AMBIGUOUS",
)


def symbol_mentioned(symbol: str, text: str) -> bool:
    """Word-boundary containment check.

    A naive substring check false-positives badly on this corpus: "LUNA"
    matches inside "LUNAI", "ANT" matches inside "MANTRA", and "BIT" matches
    inside "Bybit" itself. Require the candidate token to not be glued to
    surrounding alphanumerics on either side.
    """
    base = re.sub(r"USDT$", "", symbol, flags=re.IGNORECASE)
    for token in (symbol, base):
        if not token:
            continue
        pattern = rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])"
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def classify_announcement(title: str, *, queried_type: str | None = None) -> str:
    """Deterministic title-level classification; callers should still fetch
    and parse the body before treating a claim as confirmed, per the census
    contract. Title-only classification is a triage step, not final grading.
    """
    t = title.lower()
    if "relist" in t or "re-list" in t:
        return "PERP_RELIST"
    if "delist" in t:
        return "PERP_DELISTING"
    if queried_type == "new_crypto" and "perpetual" in t:
        return "PERP_LISTING"
    if "new listing" in t and "perpetual" in t:
        return "PERP_LISTING"
    if re.search(r"\brebrand", t) or re.search(r"\brenam", t):
        return "REBRAND"
    if ("migrat" in t or "token swap" in t) and "perpetual" not in t:
        return "CONTRACT_MIGRATION"
    if "migrat" in t and "perpetual" in t:
        return "CONTRACT_MIGRATION"
    if "funding" in t and ("interval" in t or "rate cap" in t or "methodolog" in t):
        return "FUNDING_CHANGE"
    if "swap" in t and "token" in t:
        return "REBRAND"
    return "OTHER"


def find_matching_delistings(symbol: str, announcements: Iterable[dict]) -> list[dict]:
    """Return announcements whose title precisely mentions this symbol."""
    return [a for a in announcements if symbol_mentioned(symbol, a.get("title", ""))]


def relist_gap_days(current_launch_iso: str, first_recorded_iso: str) -> int:
    """Days between a ticker's current official launch and the earliest
    independent recording of that same ticker. A large positive gap is a
    reuse/relist candidate: the exchange's current listing did not exist
    at the time the ticker was first observed, so an earlier, different
    instrument instance under the same ticker text is implied.
    """
    launch = datetime.fromisoformat(current_launch_iso.replace("Z", "+00:00"))
    first = datetime.fromisoformat(first_recorded_iso.replace("Z", "+00:00"))
    return (launch - first).days


def pit_eligible_count(markets: Iterable[dict], at: datetime) -> int:
    """Count markets structurally eligible at `at`: both a market-data
    observation window and a funding observation window cover `at`.

    `markets` rows are catalog-shaped: {"min_time", "max_time",
    "funding_rates": {"min_time", "max_time"}}, ISO-8601 strings. This is
    existence/coverage only -- no price, volume magnitude, or ranking.
    """
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)

    def parse(value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value.split(".")[0].replace("Z", "") + "+00:00")

    count = 0
    for row in markets:
        mn, mx = parse(row.get("min_time")), parse(row.get("max_time"))
        funding = row.get("funding_rates") or {}
        fmn, fmx = parse(funding.get("min_time")), parse(funding.get("max_time"))
        if mn and mx and mn <= at <= mx and fmn and fmx and fmn <= at <= fmx:
            count += 1
    return count
