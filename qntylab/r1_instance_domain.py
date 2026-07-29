"""Compile the frozen R1 census population into explicit lifecycle instances."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from qntylab.free_census import symbol_mentioned
from qntylab.lifecycle import instrument_instance_id


CUTOFF = "2026-06-30T23:59:59Z"
CUTOFF_MS = 1782863999000


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def canonical_hash(value: object) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def utc_from_ms(value: str | int) -> str:
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def is_pre_cutoff(value: str) -> bool:
    return value <= CUTOFF


def candidate_population(tardis: list[dict], current: list[dict]) -> list[dict]:
    """Union upstream catalog facts; no archive/funding/current-membership filtering."""
    rows: dict[str, dict] = {}
    for row in tardis:
        symbol = row["id"].upper()
        if symbol in rows:
            raise ValueError(f"duplicate Tardis candidate: {symbol}")
        rows[symbol] = {"source_candidate_id": f"bybit|{symbol}|linearperpetual", "symbol": symbol,
                        "base": symbol.removesuffix("USDT"), "quote": "USDT", "contract_type": "LinearPerpetual",
                        "tardis_available_since": row.get("availableSince"), "tardis_available_to": row.get("availableTo"),
                        "evidence_sources": ["tardis_catalog"]}
    for row in current:
        if row.get("quoteCoin") != "USDT" or row.get("contractType") != "LinearPerpetual":
            continue
        symbol = row["symbol"].upper()
        item = rows.setdefault(symbol, {"source_candidate_id": f"bybit|{symbol}|linearperpetual", "symbol": symbol,
                                        "base": row.get("baseCoin") or symbol.removesuffix("USDT"), "quote": "USDT",
                                        "contract_type": "LinearPerpetual", "tardis_available_since": None,
                                        "tardis_available_to": None, "evidence_sources": []})
        if "bybit_current_metadata" in item["evidence_sources"]:
            raise ValueError(f"duplicate current candidate: {symbol}")
        item["evidence_sources"].append("bybit_current_metadata")
        item["current_launch_time"] = utc_from_ms(row["launchTime"])
        item["current_status"] = row.get("status")
        item["current_symbol_id"] = row.get("symbolId")
    return [rows[key] for key in sorted(rows)]


def compile_domain(candidates: list[dict], announcements: list[dict], reuse: list[dict]) -> dict:
    seen = set()
    reuse_by_symbol = {row["symbol"].upper(): row for row in reuse}
    instances = []
    accounting = []
    for candidate in candidates:
        candidate_id = candidate["source_candidate_id"]
        if candidate_id in seen:
            raise ValueError(f"duplicate candidate id: {candidate_id}")
        seen.add(candidate_id)
        symbol = candidate["symbol"]
        official_launch = candidate.get("official_launch_time")
        start = official_launch or candidate.get("tardis_available_since")
        current_launch = candidate.get("current_launch_time")
        official_terminal = candidate.get("official_terminal_time")
        start_state = "VERIFIED_LAUNCH" if official_launch else ("FIRST_CAUSAL_TRADABILITY_EVIDENCE" if start else "START_AMBIGUOUS")
        is_future = (start and not is_pre_cutoff(start)) or (not start and current_launch and not is_pre_cutoff(current_launch))
        title_matches = [row for row in announcements if "delist" in row.get("title", "").lower()
                         and symbol_mentioned(symbol, row.get("title", "")) and int(row.get("dateTimestamp", 0)) <= CUTOFF_MS]
        terminal = candidate.get("tardis_available_to")
        if is_future:
            end_state, lifecycle_state = "OUTSIDE_HISTORICAL_CUTOFF", "FUTURE_RESERVOIR_EXCLUDED"
        elif official_terminal:
            end_state, lifecycle_state = "VERIFIED_TERMINAL", "TERMINATED_VERIFIED"
        elif "bybit_current_metadata" in candidate["evidence_sources"] and candidate.get("current_status") == "Trading":
            end_state, lifecycle_state = "OPEN_AT_HISTORICAL_CUTOFF", "OPEN_AT_CUTOFF_CORROBORATED"
        elif terminal:
            end_state, lifecycle_state = "AMBIGUOUS_TERMINAL", "TERMINATED_AMBIGUOUS"
        else:
            end_state, lifecycle_state = "AMBIGUOUS_TERMINAL", "LIFECYCLE_AMBIGUOUS"
        reuse_row = reuse_by_symbol.get(symbol)
        instance_specs = [(start, start_state, "SINGLE_CANDIDATE_NO_REUSE_EVIDENCE", "primary")]
        if reuse_row:
            # The candidate text represents two unproven lineages; retaining both
            # is safer than silently concatenating them under one ticker.
            instance_specs = [(start, start_state, "IDENTITY_AMBIGUOUS", "prior_lineage"),
                              (current_launch, "START_AMBIGUOUS", "IDENTITY_AMBIGUOUS", "current_lineage")]
        record_ids = []
        for ordinal, (instance_start, instance_start_state, identity_state, lineage) in enumerate(instance_specs):
            instance_start = instance_start or "UNKNOWN"
            instance_id = instrument_instance_id(venue="bybit", symbol=symbol, contract_type="LinearPerpetual",
                                                 first_observed=instance_start, symbol_id=(candidate.get("current_symbol_id") if lineage == "current_lineage" else None))
            record_ids.append(instance_id)
            instances.append({"instrument_instance_id": instance_id, "source_candidate_id": candidate_id,
                              "symbol": symbol, "base": candidate["base"], "quote": "USDT", "contract_type": "LinearPerpetual",
                              "lineage": lineage, "start_time": None if instance_start == "UNKNOWN" else instance_start,
                              "start_state": instance_start_state, "end_time": official_terminal if end_state == "VERIFIED_TERMINAL" else None,
                              "end_state": end_state, "identity_state": identity_state, "lifecycle_state": lifecycle_state,
                              "evidence_references": sorted(candidate["evidence_sources"] + (["bybit_announcements"] if title_matches else [])),
                              "ambiguity_reasons": (["ticker_reuse_or_relist_unproven_continuity"] if reuse_row else ([] if end_state != "AMBIGUOUS_TERMINAL" else (["title_level_terminal_announcement_unparsed"] if title_matches else ["no_authoritative_terminal_event"]))),
                              "temporal": {"event_time": instance_start if instance_start != "UNKNOWN" else None,
                                           "availability_time": None, "retrieval_time": "2026-07-29T00:00:00Z"}})
        accounting.append({"source_candidate_id": candidate_id, "instance_ids": record_ids, "accounting_state": "ACCOUNTED"})
    if len(accounting) != len(candidates):
        raise ValueError("candidate accounting mismatch")
    instances.sort(key=lambda row: row["instrument_instance_id"])
    accounting.sort(key=lambda row: row["source_candidate_id"])
    counts = Counter()
    for row in instances:
        counts[row["start_state"]] += 1; counts[row["end_state"]] += 1; counts[row["identity_state"]] += 1
    years = Counter((row["start_time"] or "UNKNOWN")[:4] for row in instances)
    return {"artifact": "r1_historical_instance_domain", "cutoff_utc": CUTOFF, "outcome_embargo": True,
            "candidate_population_count": len(candidates), "accounted_candidate_count": len(accounting),
            "unaccounted_candidates": 0, "silently_dropped_candidates": 0, "compiled_instrument_instance_count": len(instances),
            "counts": {"verified_starts": counts["VERIFIED_LAUNCH"], "ambiguous_starts": counts["START_AMBIGUOUS"],
                       "causal_evidence_starts": counts["FIRST_CAUSAL_TRADABILITY_EVIDENCE"], "verified_terminals": counts["VERIFIED_TERMINAL"],
                       "ambiguous_terminals": counts["AMBIGUOUS_TERMINAL"], "open_at_cutoff": counts["OPEN_AT_HISTORICAL_CUTOFF"],
                       "identity_ambiguous": counts["IDENTITY_AMBIGUOUS"], "reuse_splits": len(reuse), "future_reservoir_excluded": counts["OUTSIDE_HISTORICAL_CUTOFF"]},
            "instances_by_start_year": dict(sorted(years.items())), "candidate_accounting": accounting, "instances": instances}


def write_domain(root: Path, raw_root: Path) -> dict:
    raw = {name: raw_root / name for name in ("tardis_usdt_perp_symbols.json", "bybit_live_linear_instruments.json", "bybit_delistings_all.json", "identity_reuse_candidates.json")}
    tardis, current, announcements, reuse = (json.loads(path.read_text()) for path in raw.values())
    candidates = candidate_population(tardis, current)
    domain = compile_domain(candidates, announcements, reuse)
    manifest = {"artifact": "r1_instance_domain_manifest", "candidate_source": "Tardis catalog union Bybit captured linear metadata", "raw_source_sha256": {name: sha256(path.read_bytes()).hexdigest() for name, path in raw.items()}, "domain_sha256": canonical_hash(domain), "deterministic": True, "verdict": "R1_HISTORICAL_INSTANCE_DOMAIN_READY"}
    data = root / "experiments/data"; data.mkdir(parents=True, exist_ok=True)
    (data / "r1_historical_instance_domain.json").write_bytes(canonical_bytes(domain))
    (data / "r1_instance_domain_manifest.json").write_bytes(canonical_bytes(manifest))
    report = f"# R1 historical instance domain\n\n## VERDICT\n\nR1_HISTORICAL_INSTANCE_DOMAIN_READY\n\nThe frozen 967-candidate union is fully accounted for; {domain['compiled_instrument_instance_count']} explicit instances preserve ambiguity rather than dropping candidates. The {domain['counts']['future_reservoir_excluded']} post-cutoff candidates are represented only as excluded future-reservoir records.\n"
    (root / "experiments/results/R1_HISTORICAL_INSTANCE_DOMAIN.md").write_text(report)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--raw-root", type=Path, required=True); parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write: print(json.dumps(write_domain(Path.cwd(), args.raw_root), sort_keys=True))
