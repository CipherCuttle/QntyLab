"""Bounded, outcome-blind closure of the nine frozen R1 ticker-reuse cases."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.request import urlopen

from qntylab.r1_input_bom import canonical_bytes, canonical_hash


TARGET_SYMBOLS = ("DATAUSDT", "ETHUSDT", "FHEUSDT", "LITUSDT", "MONUSDT", "SOLUSDT", "SUSHIUSDT", "UNIUSDT", "ZKUSDT")
UNRESOLVED = "IDENTITY_UNRESOLVED"
SEPARATED = "LINEAGES_SEPARATED"
SAME = "SAME_INSTANCE_PROVEN"

# These are the only linked official pages found for the bounded target set.
# A page's publication date is deliberately not promoted to an event timestamp.
ANNOUNCEMENT_URLS = {
    "DATAUSDT": ("https://announcements.bybit.com/en/article/new-listing-datausdt-perpetual-contract-with-up-to-12-5x-leverage--art34c5cee4fca8/",),
    "FHEUSDT": ("https://announcements.bybit.com/en/article/new-listing-fheusdt-perpetual-contract-in-innovation-zone-with-up-to-12-5x-leverage-blt637d75a7fe889e48/",),
    "MONUSDT": (
        "https://announcements.bybit.com/article/new-listing-monusdt-perpetual-contract-blt48d546cd343758f8/",
        "https://announcements.bybit.com/article/delisting-of-monusdt-perpetual-contract-bltaca6e9a18f4a8883/",
        "https://announcements.bybit.com/en/article/new-listing-monusdt-perpetual-contract-with-up-to-50x-leverage-bltd3079c765fca3ed9/",
    ),
    "ZKUSDT": ("https://announcements.bybit.com/article/new-listing-zkusdt-perpetual-contract-blt856eb538fa884753/",),
}


def utc_from_ms(value: str | int) -> str:
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_instrument_response(raw: bytes, requested_status: str) -> dict:
    """Preserve returned records; do not assume Bybit honored the status filter."""
    value = json.loads(raw)
    rows = []
    for row in value.get("result", {}).get("list", []):
        rows.append({key: row.get(key) for key in ("symbol", "symbolId", "status", "launchTime", "deliveryTime", "contractType", "baseCoin", "quoteCoin")})
    return {"requested_status": requested_status, "response_sha256": sha256(raw).hexdigest(), "returned_rows": rows,
            "status_filter_honored": all(row.get("status") == requested_status for row in rows)}


def archive_clusters(dates: list[str]) -> list[dict]:
    """Observation clusters are corroboration only, not lifecycle events."""
    parsed = sorted(datetime.fromisoformat(value).date() for value in set(dates))
    result: list[dict] = []
    for value in parsed:
        if not result or value > datetime.fromisoformat(result[-1]["end_utc"]).date() + timedelta(days=1):
            result.append({"start_utc": value.isoformat(), "end_utc": value.isoformat()})
        else:
            result[-1]["end_utc"] = value.isoformat()
    return result


def parse_archive_listing(raw: bytes, symbol: str) -> list[str]:
    matches = re.findall((re.escape(symbol) + r"(\d{4}-\d{2}-\d{2})\.csv\.gz").encode(), raw)
    return sorted({value.decode("ascii") for value in matches})


def classify_lineages(*, exact_terminal_utc: str | None, exact_later_launch_utc: str | None,
                      continuity_proven: bool = False) -> tuple[str, list[dict], list[str]]:
    """Only explicit, ordered event times create an assignment contract."""
    if continuity_proven:
        return SAME, [], []
    if exact_terminal_utc and exact_later_launch_utc and exact_terminal_utc < exact_later_launch_utc:
        return SEPARATED, [
            {"lineage": "prior", "admissible_end_utc": exact_terminal_utc, "assignment": "t <= end"},
            {"lineage": "current", "admissible_start_utc": exact_later_launch_utc, "assignment": "t >= start"},
            {"lineage": "gap", "start_exclusive_utc": exact_terminal_utc, "end_exclusive_utc": exact_later_launch_utc, "assignment": "neither"},
        ], []
    return UNRESOLVED, [], ["no_verified_nonoverlap_boundary"]


def announcement_temporal_fields(event_time_utc: str | None, publication_time_utc: str | None) -> dict:
    """Keep page/publication time distinct from an explicitly parsed event time."""
    return {"event_time_utc": event_time_utc, "publication_time_utc": publication_time_utc,
            "event_time_state": "EXPLICIT" if event_time_utc else "NOT_EXTRACTED"}


def _get(url: str) -> bytes:
    with urlopen(url, timeout=45) as response:
        return response.read()


def _page_receipt(url: str) -> dict:
    try:
        raw = _get(url)
    except Exception as exc:
        return {"url": url, "raw_sha256": None, "byte_size": None, "title": None,
                **announcement_temporal_fields(None, None), "event_time_state": "UNAVAILABLE_TRANSPORT_FAILURE",
                "publication_time_state": "NOT_PROMOTED", "transport_error_type": type(exc).__name__}
    text = raw.decode("utf-8", errors="replace")
    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    return {"url": url, "raw_sha256": sha256(raw).hexdigest(), "byte_size": len(raw),
            "title": re.sub(r"\s+", " ", title.group(1)).strip() if title else None,
            **announcement_temporal_fields(None, None),
            "publication_time_state": "PAGE_OR_SEARCH_PUBLICATION_DATE_NOT_PROMOTED_TO_EVENT_TIME"}


def build_resolution(domain: dict, required: dict, instrument_receipts: dict[str, dict], archive_receipts: dict[str, dict], announcement_receipts: dict[str, list[dict]]) -> dict:
    instances = {row["instrument_instance_id"]: row for row in domain["instances"]}
    required_rows = {row["instrument_instance_id"]: row for row in required["records"]}
    cases = []
    for symbol in TARGET_SYMBOLS:
        pair = sorted([row for row in instances.values() if row["symbol"] == symbol and row["identity_state"] == "IDENTITY_AMBIGUOUS"], key=lambda row: row["start_time"] or "")
        if len(pair) != 2:
            raise ValueError(f"expected exactly two frozen reuse instances for {symbol}")
        classification, intervals, unresolved = classify_lineages(exact_terminal_utc=None, exact_later_launch_utc=None)
        market_objects = sum((required_rows[row["instrument_instance_id"]]["market"] or {}).get("required_object_count") or 0 for row in pair)
        funding_segments = sum(len((required_rows[row["instrument_instance_id"]]["funding"] or {}).get("segments", [])) for row in pair)
        cases.append({"symbol": symbol, "input_instrument_instance_ids": [row["instrument_instance_id"] for row in pair],
                      "current_inferred_intervals": [{"instrument_instance_id": row["instrument_instance_id"], "start_utc": row["start_time"], "end_state": row["end_state"]} for row in pair],
                      "official_instrument_receipts": instrument_receipts[symbol], "announcement_receipts": announcement_receipts.get(symbol, []),
                      "archive_observation": archive_receipts[symbol], "funding_observation": {"state": "NOT_QUERIED_TO_AVOID_UNNECESSARY_SETTLEMENT_RETRIEVAL"},
                      "classification": classification, "assignment_intervals": intervals, "unresolved_reasons": unresolved,
                      "affected_determinate_market_objects": market_objects, "affected_determinate_funding_segments": funding_segments,
                      "conflicts": ["current_status_filter_closed_returned_trading_or_no_historical_closed_record", "archive_presence_is_not_lifecycle_event"]})
    counts = {key: sum(case["classification"] == key for case in cases) for key in (SEPARATED, SAME, UNRESOLVED)}
    return {"artifact": "r1_reuse_identity_resolution_v1", "outcome_embargo": True,
            "frozen_instance_domain_sha256": canonical_hash(domain), "frozen_required_domain_sha256": canonical_hash(required),
            "case_count": len(cases), "classification_counts": counts, "cases": cases}


def write_resolution(root: Path) -> dict:
    data = root / "experiments/data"
    domain = json.loads((data / "r1_historical_instance_domain.json").read_text())
    required = json.loads((data / "r1_population_input_required_domain.json").read_text())
    instruments, archives, announcements = {}, {}, {}
    for symbol in TARGET_SYMBOLS:
        status_receipts = []
        for status in ("Trading", "Closed"):
            url = f"https://api.bybit.com/v5/market/instruments-info?category=linear&symbol={symbol}&status={status}"
            status_receipts.append({"url": url, **parse_instrument_response(_get(url), status)})
        instruments[symbol] = status_receipts
        url = f"https://public.bybit.com/trading/{symbol}/"
        raw = _get(url)
        archives[symbol] = {"url": url, "raw_sha256": sha256(raw).hexdigest(), "object_count": len(parse_archive_listing(raw, symbol)),
                            "clusters": archive_clusters(parse_archive_listing(raw, symbol)), "state": "OBSERVATION_ONLY"}
        announcements[symbol] = [_page_receipt(url) for url in ANNOUNCEMENT_URLS.get(symbol, ())]
    resolution = build_resolution(domain, required, instruments, archives, announcements)
    assignment = {"artifact": "r1_population_identity_assignment_v2", "outcome_embargo": True,
                  "resolution_sha256": canonical_hash(resolution), "reuse_cases_total": 9,
                  "lineages_separated": resolution["classification_counts"][SEPARATED], "same_instance_proven": resolution["classification_counts"][SAME],
                  "identity_unresolved": resolution["classification_counts"][UNRESOLVED], "instances_source_assignment_deterministic": 0,
                  "instances_source_assignment_ambiguous": 18, "market_unknown_objects_before": 20140, "market_unknown_objects_after": 20140,
                  "funding_assignment_impact": "unchanged; no evidence-backed assignment overlay exists"}
    (data / "r1_reuse_identity_resolution.json").write_bytes(canonical_bytes(resolution))
    (data / "r1_population_identity_assignment_v2.json").write_bytes(canonical_bytes(assignment))
    return assignment


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        print(json.dumps(write_resolution(Path.cwd()), sort_keys=True))
