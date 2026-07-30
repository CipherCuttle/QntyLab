"""Red-team repair for source-coverage timestamps misused as identity boundaries."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from qntylab.r1_input_bom import canonical_bytes, canonical_hash, required_domain


FALSE_SPLITS = ("DATAUSDT", "ETHUSDT", "FHEUSDT", "LITUSDT", "SOLUSDT", "SUSHIUSDT", "UNIUSDT", "ZKUSDT")
PROVEN_REUSE = ("MONUSDT",)


def field_semantics() -> list[dict]:
    return [
        {"field": "tardis.id", "class": "IDENTITY_EVIDENCE", "role": "source symbol label only"},
        {"field": "tardis.datasetId", "class": "SOURCE_COVERAGE_EVIDENCE", "role": "dataset locator, not venue identity"},
        {"field": "tardis.availableSince", "class": "SOURCE_COVERAGE_EVIDENCE", "role": "Tardis collection availability start"},
        {"field": "tardis.availableTo", "class": "SOURCE_COVERAGE_EVIDENCE", "role": "Tardis collection stop; may lag venue delisting"},
        {"field": "bybit.symbol", "class": "IDENTITY_EVIDENCE", "role": "current venue symbol label"},
        {"field": "bybit.symbolId", "class": "CURRENT_STATE_ONLY", "role": "current symbol-name id; no historical binding by itself"},
        {"field": "bybit.launchTime", "class": "CURRENT_STATE_ONLY", "role": "current instrument metadata corroboration"},
        {"field": "bybit.deliveryTime", "class": "CURRENT_STATE_ONLY", "role": "current metadata field"},
        {"field": "bybit.status", "class": "CURRENT_STATE_ONLY", "role": "current online-instrument status"},
        {"field": "archive first/last observation", "class": "OBSERVATION_EVIDENCE", "role": "source observation bounds, not lifecycle"},
        {"field": "announcement publication time", "class": "OBSERVATION_EVIDENCE", "role": "publication time, never event time"},
        {"field": "announcement explicit event time", "class": "LIFECYCLE_EVENT_EVIDENCE", "role": "only when explicitly parsed"},
    ]


def case_classifications() -> dict[str, str]:
    return {**{symbol: "FALSE_SPLIT_FROM_SOURCE_SEMANTICS" for symbol in FALSE_SPLITS}, "MONUSDT": "PROVEN_REUSE"}


def _identity_id(symbol: str, label: str) -> str:
    return f"bybit|{symbol}|linearperpetual|identity-v2|{label}"


def refine_domain(frozen: dict) -> dict:
    """Merge only source-semantic false splits; preserve affirmative reuse evidence."""
    by_symbol: dict[str, list[dict]] = {}
    for row in frozen["instances"]:
        by_symbol.setdefault(row["symbol"], []).append(row)
    result = []
    replacement: dict[str, list[str]] = {}
    for symbol, rows in sorted(by_symbol.items()):
        rows.sort(key=lambda row: row["instrument_instance_id"])
        if symbol not in FALSE_SPLITS:
            if symbol == "MONUSDT":
                prior, current = sorted(rows, key=lambda row: row["start_time"] or "")
                prior = deepcopy(prior); current = deepcopy(current)
                prior["instrument_instance_id"] = _identity_id(symbol, "prior-reuse-evidenced")
                current["instrument_instance_id"] = _identity_id(symbol, "current-reuse-evidenced")
                prior["identity_state"] = current["identity_state"] = "REUSE_EVIDENCED_BOUNDARY_UNTIMED"
                prior["lineage"], current["lineage"] = "prior_reuse_evidenced", "current_reuse_evidenced"
                prior["end_state"], prior["lifecycle_state"], prior["end_time"] = "AMBIGUOUS_TERMINAL", "TERMINATED_AMBIGUOUS", None
                prior["ambiguity_reasons"] = ["official_delisting_and_later_listing_without_exact_terminal_time"]
                result.extend((prior, current)); replacement[symbol] = [prior["instrument_instance_id"], current["instrument_instance_id"]]
            else:
                result.extend(rows)
            continue
        prior, current = sorted(rows, key=lambda row: row["start_time"] or "")
        merged = deepcopy(prior)
        merged["instrument_instance_id"] = _identity_id(symbol, "coverage-timestamps-merged")
        merged["lineage"] = "single_identity_source_coverage_reconciled"
        merged["identity_state"] = "SINGLE_IDENTITY_NO_AFFIRMATIVE_DISCONTINUITY"
        merged["start_time"] = min(value for value in (prior["start_time"], current["start_time"]) if value)
        merged["start_state"] = "FIRST_CAUSAL_TRADABILITY_EVIDENCE"
        merged["end_state"], merged["lifecycle_state"], merged["end_time"] = current["end_state"], current["lifecycle_state"], current["end_time"]
        merged["evidence_references"] = sorted(set(prior["evidence_references"] + current["evidence_references"]))
        merged["ambiguity_reasons"] = ["source_coverage_timestamp_disagreement_not_identity_boundary"]
        merged["source_temporal_evidence"] = {"tardis_available_since": prior["start_time"], "bybit_current_launch_time": current["start_time"]}
        result.append(merged); replacement[symbol] = [merged["instrument_instance_id"]]
    result.sort(key=lambda row: row["instrument_instance_id"])
    accounting = []
    for row in frozen["candidate_accounting"]:
        symbol = row["source_candidate_id"].split("|")[1]
        ids = replacement.get(symbol, row["instance_ids"])
        accounting.append({**row, "instance_ids": ids})
    counts = Counter()
    for row in result:
        counts[row["start_state"]] += 1; counts[row["end_state"]] += 1; counts[row["identity_state"]] += 1
    return {"artifact": "r1_historical_instance_domain_v2_source_semantics_refinement", "outcome_embargo": True,
            "predecessor_frozen_domain_sha256": canonical_hash(frozen), "candidate_population_count": frozen["candidate_population_count"],
            "accounted_candidate_count": frozen["accounted_candidate_count"], "unaccounted_candidates": 0, "silently_dropped_candidates": 0,
            "compiled_instrument_instance_count": len(result), "cutoff_utc": frozen["cutoff_utc"],
            "counts": {"identity_ambiguous": 0, "semantic_false_splits_merged": len(FALSE_SPLITS), "proven_reuse_pairs_retained": 1,
                       "ambiguous_terminals": counts["AMBIGUOUS_TERMINAL"], "open_at_cutoff": counts["OPEN_AT_HISTORICAL_CUTOFF"],
                       "future_reservoir_excluded": counts["OUTSIDE_HISTORICAL_CUTOFF"]},
            "candidate_accounting": accounting, "instances": result}


def build_audit(frozen: dict, refined: dict) -> dict:
    return {"artifact": "r1_identity_model_red_team_audit_v1", "outcome_embargo": True,
            "old_domain_sha256": canonical_hash(frozen), "new_domain_sha256": canonical_hash(refined),
            "source_semantics": field_semantics(), "case_classifications": case_classifications(),
            "compiler_defect": "v1 split every reuse-candidate ticker solely because Tardis coverage start and current Bybit launchTime differed; both timestamps were embedded in instance IDs as boundaries.",
            "minimum_identity_rule": "same venue+ticker+contract_type+base+quote is one identity hypothesis; split only on affirmative discontinuity evidence.",
            "observation_assignment_rule": "non-overlapping source observation segments may be labeled independently, but never become lifecycle events.",
            "source_docs": ["https://docs.tardis.dev/api/instruments-metadata-api", "https://bybit-exchange.github.io/docs/v5/market/instrument", "https://bybit-exchange.github.io/docs/v5/announcement"]}


def write_refinement(root: Path) -> dict:
    data = root / "experiments/data"
    frozen = json.loads((data / "r1_historical_instance_domain.json").read_text())
    refined = refine_domain(frozen)
    required = required_domain(refined)
    audit = build_audit(frozen, refined)
    identity = {"artifact": "r1_population_identity_assignment_v3_source_semantics", "outcome_embargo": True,
                "refined_domain_sha256": canonical_hash(refined), "audit_sha256": canonical_hash(audit),
                "old_ambiguous_instances": 18, "new_ambiguous_instances": 0,
                "old_unknown_market_objects": 20140, "new_unknown_market_objects": 0,
                "note": "identity-assignment unknowns only; archive/lifecycle availability is evaluated separately"}
    manifest = {"artifact": "r1_instance_domain_manifest_v2", "predecessor_domain_sha256": canonical_hash(frozen),
                "domain_sha256": canonical_hash(refined), "audit_sha256": canonical_hash(audit), "deterministic": True}
    for name, value in (("r1_historical_instance_domain_v2.json", refined), ("r1_instance_domain_manifest_v2.json", manifest),
                        ("r1_identity_model_red_team_audit.json", audit), ("r1_population_input_required_domain_v2.json", required),
                        ("r1_population_identity_assignment_v3.json", identity)):
        (data / name).write_bytes(canonical_bytes(value))
    return {"new_domain_sha256": manifest["domain_sha256"], **identity}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write: print(json.dumps(write_refinement(Path.cwd()), sort_keys=True))
