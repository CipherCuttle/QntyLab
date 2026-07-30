"""Population-backed, outcome-blind R1 free-input bill of materials.

The required domain is derived only from the frozen instance-domain artifact.
Archive and API observations are deliberately a separate, replaceable layer.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Callable, Iterable
from urllib.request import urlopen


CUTOFF = "2026-06-30T23:59:59Z"
FIRST_EVALUATION_DATE = "2021-10-01"
MARKET_WARMUP_DAYS = 90
FUNDING_WARMUP_DAYS = 7
FUNDING_PAGE_CAP = 200
# The protocol requires realized settlements, but interval varies historically.
# Sixty calendar days is safely below 200 at the shortest commonly observed
# (8-hour) interval and therefore cannot silently cross the response cap.
FUNDING_SAFE_SEGMENT_DAYS = 60

VERDICT_SOURCE_ENUMERATION = "BLOCKED_BY_SOURCE_ENUMERATION"
VERDICT_MARKET = "R1_FREE_MARKET_DOMAIN_INSUFFICIENT"
VERDICT_FUNDING = "R1_FREE_FUNDING_DOMAIN_INSUFFICIENT"
VERDICT_LIFECYCLE = "R1_FREE_LIFECYCLE_DOMAIN_INSUFFICIENT"
VERDICT_IDENTITY = "R1_FREE_IDENTITY_DOMAIN_INSUFFICIENT"
READY = "R1_FREE_INPUT_BOM_READY"
VERDICT_PROTOCOL = "BLOCKED_BY_PROTOCOL_UNDERSPECIFICATION"


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def canonical_hash(value: object) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def _day(value: str | None) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


def _days_inclusive(start: str, end: str) -> int:
    return (_day(end) - _day(start)).days + 1  # type: ignore[operator]


def input_requirements() -> dict:
    first = _day(FIRST_EVALUATION_DATE)
    assert first is not None
    return {
        "first_candidate_evaluation_date": FIRST_EVALUATION_DATE,
        "historical_cutoff_utc": CUTOFF,
        "future_reservoir_start_utc": "2026-07-01T00:00:00Z",
        "pit_eligibility": {"finite_close_days": 90, "finite_quote_volume_days": 30,
                            "minimum_breadth": 10, "quote_volume": "trailing 30-day median through t"},
        "H012-30d": {"kind": "daily_close", "lookback_days": 30},
        "H012-90d": {"kind": "daily_close", "lookback_days": 90},
        "H014-24h": {"kind": "realized_funding", "lookback_days": 1},
        "H014-7d": {"kind": "realized_funding", "lookback_days": 7},
        "execution_boundary": "next close t+1 is structural input; no return is bridged across a gap",
        "required_market_input_start": str(first - timedelta(days=MARKET_WARMUP_DAYS)),
        "required_funding_input_start": str(first - timedelta(days=FUNDING_WARMUP_DAYS - 1)),
        "required_end": CUTOFF,
    }


def market_url(symbol: str, utc_date: str) -> str:
    return f"https://public.bybit.com/trading/{symbol}/{symbol}{utc_date}.csv.gz"


def archive_directory_url(symbol: str) -> str:
    return f"https://public.bybit.com/trading/{symbol}/"


def _segments(start: str, end: str, days: int = FUNDING_SAFE_SEGMENT_DAYS) -> list[dict]:
    cursor, last = _day(start), _day(end)
    assert cursor is not None and last is not None
    result = []
    while cursor <= last:
        segment_end = min(last, cursor + timedelta(days=days - 1))
        result.append({"start_utc": cursor.isoformat() + "T00:00:00Z",
                       "end_utc": segment_end.isoformat() + "T23:59:59Z"})
        cursor = segment_end + timedelta(days=1)
    return result


def _relevant(instance: dict) -> tuple[bool, str | None]:
    if instance["lifecycle_state"] == "FUTURE_RESERVOIR_EXCLUDED":
        return False, "FUTURE_RESERVOIR_STARTS_AFTER_2026_06_30_CUTOFF"
    return True, None


def required_domain(instances_document: dict) -> dict:
    """Create the immutable demand side; never inspect listings or API replies."""
    requirements = input_requirements()
    if instances_document.get("compiled_instrument_instance_count") != len(instances_document.get("instances", [])):
        raise ValueError("frozen instance count does not match instances array")
    records, exclusions = [], []
    for instance in sorted(instances_document["instances"], key=lambda row: row["instrument_instance_id"]):
        relevant, reason = _relevant(instance)
        base = {key: instance[key] for key in ("instrument_instance_id", "symbol", "lineage", "start_state", "end_state", "identity_state", "lifecycle_state")}
        if not relevant:
            exclusions.append({"instrument_instance_id": instance["instrument_instance_id"], "frozen_reason": reason})
            records.append({**base, "structurally_relevant_to_r1": False, "exclusion_reason": reason,
                            "market": None, "funding": None})
            continue
        start = _day(instance.get("start_time"))
        if start is None:
            market_start = funding_start = None
            state = "UNRESOLVED_START_BOUND"
        else:
            market_start = max(start, _day(requirements["required_market_input_start"]))
            funding_start = max(start, _day(requirements["required_funding_input_start"]))
            state = "DETERMINATE" if instance["end_state"] == "OPEN_AT_HISTORICAL_CUTOFF" else "UNRESOLVED_CAUSAL_CESSATION"
        if state == "DETERMINATE":
            market_end = funding_end = _day(CUTOFF)
        else:
            # Tardis recorder-stop evidence is not a verified terminal.  The
            # frozen artifact intentionally supplies no causal cessation date.
            market_end = funding_end = None
        market = {"required_start_utc": market_start.isoformat() if market_start else None,
                  "required_end_utc": market_end.isoformat() if market_end else None,
                  "interval_state": state,
                  "required_reasons": ["daily_causal_close", "daily_quote_turnover", "gap_state", "future_pit_universe_materialization"],
                  "expected_source_path_template": f"https://public.bybit.com/trading/{instance['symbol']}/{instance['symbol']}YYYY-MM-DD.csv.gz",
                  "required_object_count": _days_inclusive(market_start.isoformat(), market_end.isoformat()) if market_start and market_end else None}
        funding = {"required_start_utc": funding_start.isoformat() if funding_start else None,
                   "required_end_utc": funding_end.isoformat() if funding_end else None,
                   "interval_state": state,
                   "endpoint": "GET /v5/market/funding/history?category=linear&symbol=<symbol>",
                   "segments": _segments(funding_start.isoformat(), funding_end.isoformat()) if funding_start and funding_end else [],
                   "availability_state": "UNKNOWN"}
        records.append({**base, "structurally_relevant_to_r1": True, "exclusion_reason": None,
                        "ambiguity_reasons": instance.get("ambiguity_reasons", []), "market": market, "funding": funding})
    relevant_records = [row for row in records if row["structurally_relevant_to_r1"]]
    return {"artifact": "r1_population_input_required_domain_v1", "outcome_embargo": True,
            "frozen_instance_domain_sha256": canonical_hash(instances_document), "requirements": requirements,
            "instances_total": len(records), "instances_structurally_relevant_to_r1": len(relevant_records),
            "instances_excluded_by_frozen_rule": len(exclusions), "excluded_instances": exclusions,
            "determinate_market_object_count": sum(row["market"]["required_object_count"] or 0 for row in relevant_records),
            "unresolved_market_interval_count": sum(row["market"]["required_object_count"] is None for row in relevant_records),
            "records": records}


def parse_archive_listing(html: str, symbol: str) -> set[str]:
    """Extract only daily object names from Bybit's directory index."""
    pattern = re.compile(re.escape(symbol) + r"(\d{4}-\d{2}-\d{2})\.csv\.gz")
    return set(pattern.findall(html))


def fetch_archive_listings(symbols: Iterable[str], fetch: Callable[[str], str] | None = None) -> dict[str, set[str] | None]:
    """Enumerate directory metadata, never trade-file bodies. None is UNKNOWN."""
    def default_fetch(url: str) -> str:
        with urlopen(url, timeout=45) as response:
            return response.read().decode("utf-8", errors="replace")
    get = fetch or default_fetch
    unique = sorted(set(symbols))
    output: dict[str, set[str] | None] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        future_to_symbol = {pool.submit(get, archive_directory_url(symbol)): symbol for symbol in unique}
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                output[symbol] = parse_archive_listing(future.result(), symbol)
            except Exception:
                output[symbol] = None
    return output


def _date_range(start: str, end: str) -> Iterable[str]:
    cursor, last = _day(start), _day(end)
    assert cursor is not None and last is not None
    while cursor <= last:
        yield cursor.isoformat()
        cursor += timedelta(days=1)


def availability_observation(required: dict, listings: dict[str, set[str] | None] | None = None) -> dict:
    """Observe supply without changing any required record or membership."""
    listing_data = listings or {}
    records, counts, by_year, by_lifecycle, missingness = [], Counter(), defaultdict(Counter), defaultdict(Counter), Counter()
    for row in required["records"]:
        if not row["structurally_relevant_to_r1"]:
            continue
        market = row["market"]
        if market["required_object_count"] is None:
            records.append({"instrument_instance_id": row["instrument_instance_id"], "state": "UNKNOWN",
                            "reason": market["interval_state"]})
            continue
        if row["identity_state"] == "IDENTITY_AMBIGUOUS":
            state, why = "UNKNOWN", "identity_assignment_uncertainty"
            dates = list(_date_range(market["required_start_utc"], market["required_end_utc"]))
        elif row["symbol"] not in listing_data or listing_data[row["symbol"]] is None:
            state, why = "UNKNOWN", "source_enumeration_uncertainty"
            dates = list(_date_range(market["required_start_utc"], market["required_end_utc"]))
        else:
            available = listing_data[row["symbol"]] or set()
            dates = list(_date_range(market["required_start_utc"], market["required_end_utc"]))
            present_dates = [value for value in dates if value in available]
            absent_dates = [value for value in dates if value not in available]
            for value in present_dates:
                counts["present"] += 1; by_year[value[:4]]["present"] += 1; by_lifecycle[row["lifecycle_state"]]["present"] += 1
            for value in absent_dates:
                counts["absent"] += 1; by_year[value[:4]]["absent"] += 1; by_lifecycle[row["lifecycle_state"]]["absent"] += 1
            if absent_dates:
                missingness["unexpected_interior_absence"] += len(absent_dates)
            records.append({"instrument_instance_id": row["instrument_instance_id"], "state": "MIXED" if present_dates and absent_dates else ("PRESENT" if present_dates else "ABSENT"),
                            "present_object_count": len(present_dates), "absent_object_count": len(absent_dates),
                            "absent_dates": absent_dates, "unknown_object_count": 0})
            continue
        counts["unknown"] += len(dates); missingness[why] += len(dates)
        for value in dates:
            by_year[value[:4]]["unknown"] += 1; by_lifecycle[row["lifecycle_state"]]["unknown"] += 1
        records.append({"instrument_instance_id": row["instrument_instance_id"], "state": state, "reason": why,
                        "present_object_count": 0, "absent_object_count": 0, "unknown_object_count": len(dates)})
    return {"artifact": "r1_population_market_availability_v1", "outcome_embargo": True,
            "observation_state": "ENUMERATED" if listings is not None else "NOT_ENUMERATED",
            "counts": {key: counts[key] for key in ("present", "absent", "unknown")},
            "by_year": {key: dict(value) for key, value in sorted(by_year.items())},
            "by_lifecycle_state": {key: dict(value) for key, value in sorted(by_lifecycle.items())},
            "missingness": dict(missingness), "records": records}


def enumerate_archive_availability(required: dict, batch_size: int = 50) -> dict:
    """Bounded-memory archive enumeration; keeps only one index batch at a time."""
    relevant = [row for row in required["records"] if row["structurally_relevant_to_r1"]]
    grouped: dict[str, list[dict]] = defaultdict(list)
    unresolved = []
    for row in relevant:
        if row["market"]["required_object_count"] is None:
            unresolved.append(row)
        else:
            grouped[row["symbol"]].append(row)
    partials = [availability_observation({"records": unresolved}, {})]
    symbols = sorted(grouped)
    for offset in range(0, len(symbols), batch_size):
        batch = symbols[offset:offset + batch_size]
        listing_batch = fetch_archive_listings(batch)
        batch_records = [row for symbol in batch for row in grouped[symbol]]
        partials.append(availability_observation({"records": batch_records}, listing_batch))
    counts, missingness, years, lifecycles, records = Counter(), Counter(), defaultdict(Counter), defaultdict(Counter), []
    for partial in partials:
        counts.update(partial["counts"]); missingness.update(partial["missingness"]); records.extend(partial["records"])
        for year, values in partial["by_year"].items(): years[year].update(values)
        for lifecycle, values in partial["by_lifecycle_state"].items(): lifecycles[lifecycle].update(values)
    return {"artifact": "r1_population_market_availability_v1", "outcome_embargo": True,
            "observation_state": "ENUMERATED", "archive_directory_count": len(symbols),
            "counts": {key: counts[key] for key in ("present", "absent", "unknown")},
            "by_year": {key: dict(value) for key, value in sorted(years.items())},
            "by_lifecycle_state": {key: dict(value) for key, value in sorted(lifecycles.items())},
            "missingness": dict(missingness), "records": records}


def funding_request_rule() -> dict:
    return {"endpoint": "GET /v5/market/funding/history?category=linear&symbol=<symbol>", "limit": FUNDING_PAGE_CAP,
            "initial_segment_days": FUNDING_SAFE_SEGMENT_DAYS,
            "segmentation": "inclusive UTC ranges of at most 60 days; recursively bisect any 200-row response until each leaf has fewer than 200 rows; a minimum-range cap is NON_ENUMERABLE",
            "checks": ["200-record truncation", "range gaps", "duplicate timestamps", "non-monotonic timestamps", "boundary duplication", "boundary omission", "empty valid response", "HTTP/API failure"]}


def identity_assignment(required: dict) -> dict:
    affected = [row for row in required["records"] if row.get("identity_state") == "IDENTITY_AMBIGUOUS"]
    # The frozen artifact contains no verified causal terminal for either side
    # of each reuse split. Ticker-keyed raw observations therefore cannot be
    # assigned to one lineage without inventing a boundary.
    return {"affected_instance_count": len(affected), "deterministic": 0, "ambiguous": len(affected),
            "records": [{"instrument_instance_id": row["instrument_instance_id"], "symbol": row["symbol"],
                         "source_assignment": "SOURCE_ASSIGNMENT_AMBIGUOUS",
                         "reason": "ticker_keyed_source_and_no_verified_nonoverlap_boundary"} for row in affected]}


def funding_plan(required: dict) -> dict:
    rows = [row for row in required["records"] if row["structurally_relevant_to_r1"]]
    determinate = [row for row in rows if row["funding"]["interval_state"] == "DETERMINATE"]
    return {"funding_instances_required": len(rows), "enumerable": len(determinate),
            "non_enumerable": 0, "unknown": len(rows) - len(determinate),
            "estimated_request_count": sum(len(row["funding"]["segments"]) for row in determinate),
            "request_rule": funding_request_rule()}


def determine_verdict(required: dict, availability: dict, identity: dict, funding: dict) -> str:
    if identity["ambiguous"]:
        return VERDICT_IDENTITY
    if required["unresolved_market_interval_count"]:
        return VERDICT_LIFECYCLE
    if availability["observation_state"] != "ENUMERATED" or availability["counts"]["unknown"]:
        return VERDICT_SOURCE_ENUMERATION
    if availability["counts"]["absent"]:
        return VERDICT_MARKET
    if funding["non_enumerable"]:
        return VERDICT_FUNDING
    return READY


def write_population_bom(root: Path, *, enumerate_market: bool = False) -> dict:
    data = root / "experiments/data"
    instances = json.loads((data / "r1_historical_instance_domain.json").read_text())
    required = required_domain(instances)
    availability = enumerate_archive_availability(required) if enumerate_market else availability_observation(required)
    identity, funding = identity_assignment(required), funding_plan(required)
    verdict = determine_verdict(required, availability, identity, funding)
    manifest = {"artifact": "r1_population_input_bom_manifest_v1", "verdict": verdict, "outcome_embargo": True,
                "required_domain_sha256": canonical_hash(required), "availability_observation_sha256": canonical_hash(availability),
                "required_domain_is_independent_of_availability": True,
                "frozen_instance_domain_sha256": sha256((data / "r1_historical_instance_domain.json").read_bytes()).hexdigest()}
    plan = {"artifact": "r1_population_funding_acquisition_plan_v1", "outcome_embargo": True, **funding}
    for name, value in (("r1_population_input_required_domain.json", required), ("r1_population_market_availability.json", availability),
                        ("r1_population_funding_plan.json", plan), ("r1_population_identity_assignment.json", identity),
                        ("r1_population_input_bom_manifest.json", manifest)):
        (data / name).write_bytes(canonical_bytes(value))
    report = "\n".join(["# R1 population free-input BOM", "", "## VERDICT", "", verdict, "", "## COUNTS", "",
        f"- Instances total: {required['instances_total']}", f"- Structurally relevant: {required['instances_structurally_relevant_to_r1']}",
        f"- Frozen exclusions: {required['instances_excluded_by_frozen_rule']}", f"- Determinate required market objects: {required['determinate_market_object_count']}",
        f"- Market present / absent / unknown: {availability['counts']['present']} / {availability['counts']['absent']} / {availability['counts']['unknown']}",
        f"- Funding estimated request count: {funding['estimated_request_count']}", f"- Identity source-assignment ambiguous: {identity['ambiguous']}", "", "## OUTCOME EMBARGO", "",
        "No factor values, ranks, books, returns, PnL, IC, Sharpe, or null outcomes were computed."])
    (root / "experiments/results/R1_POPULATION_FREE_INPUT_BOM.md").write_text(report + "\n")
    return manifest


def lifecycle_acquisition_audit(required: dict) -> dict:
    """State the existing boundary without inventing an acquisition extension."""
    unresolved = [row for row in required["records"] if row["structurally_relevant_to_r1"] and row["market"]["interval_state"] != "DETERMINATE"]
    return {"ambiguous_terminal_instances": len(unresolved),
            "eligibility_rule": "frozen terminal policy removes an ambiguous-unexposed instance after its last verified tradable state",
            "acquisition_envelope_rule": "NOT_SPECIFIED_BY_FROZEN_PROTOCOL",
            "terminal_evidence_rule": "last observation, archive absence, and recorder availableTo never establish a verified terminal",
            "instances": [{"instrument_instance_id": row["instrument_instance_id"], "symbol": row["symbol"],
                           "eligibility_state": "TERMINATED_AMBIGUOUS_FAIL_CLOSED", "acquisition_envelope_state": "UNSPECIFIED",
                           "terminal_evidence_state": "NO_VERIFIED_TERMINAL"} for row in unresolved]}


def write_population_bom_v2(root: Path, *, enumerate_market: bool = False) -> dict:
    """Versioned BOM for the repaired identity domain; never rewrites v1."""
    data = root / "experiments/data"
    instance_path = data / "r1_historical_instance_domain_v2.json"
    instances = json.loads(instance_path.read_text())
    required = required_domain(instances)
    required["artifact"] = "r1_population_input_required_domain_v2"
    availability = enumerate_archive_availability(required, batch_size=200) if enumerate_market else availability_observation(required)
    availability["artifact"] = "r1_population_market_availability_v2"
    identity, funding = identity_assignment(required), funding_plan(required)
    lifecycle = lifecycle_acquisition_audit(required)
    verdict = VERDICT_PROTOCOL if lifecycle["ambiguous_terminal_instances"] else determine_verdict(required, availability, identity, funding)
    plan = {"artifact": "r1_population_funding_acquisition_plan_v2", "outcome_embargo": True, **funding,
            "acquisition_envelope_state": lifecycle["acquisition_envelope_rule"]}
    manifest = {"artifact": "r1_population_input_bom_manifest_v2", "verdict": verdict, "outcome_embargo": True,
                "v2_required_domain_sha256": canonical_hash(required), "v2_availability_sha256": canonical_hash(availability),
                "required_domain_is_independent_of_availability": True, "v2_instance_domain_sha256": sha256(instance_path.read_bytes()).hexdigest(),
                "lifecycle_acquisition_audit_sha256": canonical_hash(lifecycle)}
    for name, value in (("r1_population_input_required_domain_v2.json", required), ("r1_population_market_availability_v2.json", availability),
                        ("r1_population_funding_plan_v2.json", plan), ("r1_population_lifecycle_acquisition_v2.json", lifecycle),
                        ("r1_population_input_bom_manifest_v2.json", manifest)):
        (data / name).write_bytes(canonical_bytes(value))
    report = "\n".join(["# R1 population free-input BOM v2", "", "## VERDICT", "", verdict, "", "## COUNTS", "",
        f"- V2 instances: {required['instances_total']}", f"- Structurally relevant: {required['instances_structurally_relevant_to_r1']}",
        f"- Determinate market objects: {required['determinate_market_object_count']}",
        f"- Market present / absent / unknown: {availability['counts']['present']} / {availability['counts']['absent']} / {availability['counts']['unknown']}",
        f"- Ambiguous terminal acquisition envelopes: {lifecycle['ambiguous_terminal_instances']}",
        "", "## OUTCOME EMBARGO", "", "No factor values, ranks, books, returns, PnL, IC, Sharpe, or null outcomes were computed."])
    (root / "experiments/results/R1_FREE_INPUT_BOM_V2.md").write_text(report + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-population-bom", action="store_true")
    parser.add_argument("--write-population-bom-v2", action="store_true")
    parser.add_argument("--enumerate-market", action="store_true", help="directory metadata only; never downloads trade files")
    args = parser.parse_args()
    if args.write_population_bom:
        print(json.dumps(write_population_bom(Path.cwd(), enumerate_market=args.enumerate_market), sort_keys=True))
    if args.write_population_bom_v2:
        print(json.dumps(write_population_bom_v2(Path.cwd(), enumerate_market=args.enumerate_market), sort_keys=True))
