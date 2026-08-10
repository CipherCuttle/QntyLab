"""Derived corpus index (Research Factory V2, Seam 6).

One row per completed strategy trial, generated deterministically from evidence
that already exists: the canonical candidate/decision/trial streams, the frozen
family ontology, and the frozen instrument contracts.  This is a generated
artifact on the existing rebuild path, exactly like ``state.json`` and
``trial_index.json`` -- not a database, not an experiment store.

Two rules keep V1 and V2 evidence from being laundered into each other:

* ``evidence_capability`` distinguishes ``SUMMARY_ONLY`` from ``BAR_PATH``.  A
  query that requires per-bar paths cannot silently consume V1 rows.
* ``instrument_contract_id`` is required on every row, and pooling across
  contracts fails closed unless the caller explicitly declares a
  cross-instrument comparison.

Historical rows carry values the receipt never stored natively.  Every such
field is tagged ``HISTORICAL_RECONSTRUCTION`` against ``NATIVE_RECEIPT`` so a
reconstructed label can never be mistaken for a recorded one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import family_ontology, instrument_contract
from .research_ledger import (
    CORPUS_GENERATION_V1,
    CORPUS_GENERATION_V2,
    RESEARCH_ROOT,
    LedgerError,
    canonical_bytes,
    load_canonical_history,
    replay,
    sha256_bytes,
)

CORPUS_INDEX_SCHEMA_VERSION = "CORPUS_INDEX_V1"
CORPUS_INDEX_PATH = RESEARCH_ROOT / "corpus_index.json"

SUMMARY_ONLY = "SUMMARY_ONLY"
BAR_PATH = "BAR_PATH"

NATIVE_RECEIPT = "NATIVE_RECEIPT"
HISTORICAL_RECONSTRUCTION = "HISTORICAL_RECONSTRUCTION"

# Generation-level historical classification.  Every committed V1 trial reads a
# Binance Spot 1h CSV (`data/raw/*-1h.csv`, manifest source_kind "Binance Spot
# public market-data REST"), including the halt-normalized 2023 derivations,
# which are spot bars repaired from spot archives.  This is a derived
# classification of already-committed input provenance, not a rewrite: no
# historical event or hash is modified.
HISTORICAL_INSTRUMENT_CONTRACT_ID = instrument_contract.BINANCE_SPOT_USDT_V1
HISTORICAL_INSTRUMENT_PROVENANCE = (
    "Generation-level historical classification derived from the committed input/source contract "
    "of every V1 trial (Binance Spot public market-data 1h klines). No historical event, trial_id "
    "or hash was rewritten."
)

# Explicitly registered screens whose variant denominator is frozen in a
# committed specification.  Denominators are never invented retroactively for
# informal generation-1 exploration: an unlisted campaign yields null with a
# reason code rather than a guessed number.
REGISTERED_SCREENS: dict[str, dict[str, Any]] = {
    "curated_breadth_screen_v1": {
        "registered_screen_id": "CURATED_BREADTH_SCREEN_V1",
        "registered_variant_denominator": 15,
        "source": "experiments/specs/curated_breadth_screen_v1.json",
    },
    "focused_trend_validation_v1": {
        "registered_screen_id": "FOCUSED_TREND_VALIDATION_V1",
        "registered_variant_denominator": None,
        "source": "experiments/specs/focused_trend_validation_v1.json",
        "denominator_reason": "NOT_RETROACTIVELY_ASSIGNED",
    },
}


class CorpusIndexError(RuntimeError):
    pass


def _run_id_from_receipt_path(receipt_path: str) -> str:
    return Path(receipt_path).parent.name


def _campaign_from_receipt_path(receipt_path: str) -> str | None:
    parts = Path(receipt_path).parts
    if "runs" not in parts:
        return None
    index = parts.index("runs")
    return parts[index + 1] if len(parts) > index + 1 else None


def _reconstruct_period_and_cost(run_id: str) -> tuple[str | None, str | None]:
    """Recover period and cost mode from a V1 run directory name.

    V1 receipts wrote ``period`` and ``cost_mode`` as empty strings, so the only
    committed carrier of those labels is the run ID.  Shape:
    ``NNN__CANDIDATE_X__SYMBOL__PERIOD__COSTMODE__trial_xxx``.
    """
    parts = run_id.split("__")
    if len(parts) == 6 and parts[0].isdigit() and parts[5].startswith("trial_"):
        return parts[3], parts[4]
    if len(parts) == 4:
        return parts[2], parts[3]
    return None, None


def build_corpus(root: Path = RESEARCH_ROOT) -> dict[str, Any]:
    """Build the deterministic corpus index from canonical history."""
    history = load_canonical_history(root)
    state, _trial_index, issues = replay(history, verify_evidence=False, root=root)
    if issues:
        raise CorpusIndexError("; ".join(issues))

    family_ontology.verify_alias_coverage(
        [event["family_id"] for event in history.candidates if event["event_type"] == "CANDIDATE_PROPOSED"]
    )
    proposals = {
        event["variant_id"]: event for event in history.candidates if event["event_type"] == "CANDIDATE_PROPOSED"
    }

    rows: list[dict[str, Any]] = []
    for event in history.trials:
        proposal = proposals.get(event["variant_id"])
        if proposal is None:
            raise CorpusIndexError(f"trial without proposal: {event['event_id']}")
        native = "instrument_contract_id" in event
        run_id = _run_id_from_receipt_path(event["receipt_path"])
        campaign = _campaign_from_receipt_path(event["receipt_path"])
        screen = REGISTERED_SCREENS.get(campaign or "", {})

        if native:
            instrument_contract_id = event["instrument_contract_id"]
            period_id = event.get("period_id")
            cost_mode = event.get("cost_mode")
            value_origin = NATIVE_RECEIPT
            research_generation = event["research_generation"]
            funding_treatment = event["funding_treatment"]
            bar_path_sha256 = event.get("bar_path_sha256")
            screen_id = event.get("registered_screen_id") or screen.get("registered_screen_id")
            denominator = event.get("registered_variant_denominator")
            if denominator is None:
                denominator = screen.get("registered_variant_denominator")
        else:
            instrument_contract_id = HISTORICAL_INSTRUMENT_CONTRACT_ID
            period_id, cost_mode = _reconstruct_period_and_cost(run_id)
            value_origin = HISTORICAL_RECONSTRUCTION
            research_generation = CORPUS_GENERATION_V1
            funding_treatment = None
            bar_path_sha256 = None
            screen_id = screen.get("registered_screen_id")
            denominator = screen.get("registered_variant_denominator")

        canonical_family_id = family_ontology.resolve_family(event["family_id"])
        variant_state = state["variants"].get(event["variant_id"], {})
        rows.append(
            {
                "bar_path_sha256": bar_path_sha256,
                "canonical_family_id": canonical_family_id,
                "candidate_id": event["candidate_id"],
                "cost_mode": cost_mode,
                "evaluation_end": event["evaluation_end"],
                "evaluation_start": event["evaluation_start"],
                "evidence_capability": BAR_PATH if bar_path_sha256 else SUMMARY_ONLY,
                "fee_bps": float(event["fee_bps"]),
                "funding_treatment": funding_treatment,
                "input_sha256": event["input_sha256"],
                "instrument_contract_digest": instrument_contract.contract_digest(instrument_contract_id),
                "instrument_contract_id": instrument_contract_id,
                "instrument_contract_value_origin": value_origin,
                "metrics": dict(sorted(event["compact_metrics"].items())),
                "metrics_schema_version": _metrics_schema_version(event["compact_metrics"]),
                "mode": proposal["mode"],
                "parameters": proposal["parameters"],
                "period_id": period_id,
                "raw_family_id": event["family_id"],
                "registered_screen_id": screen_id,
                "registered_variant_denominator": denominator,
                "repository_commit": event["repository_commit"],
                "research_generation": research_generation,
                "research_intent": event["research_intent"],
                "run_id": run_id,
                "semantic_value_origin": value_origin,
                "slippage_bps": float(event["slippage_bps"]),
                "strategy_id": proposal["strategy_id"],
                "strategy_version": proposal["strategy_version"],
                "symbol": event["symbol"],
                "trial_id": event["trial_id"],
                "variant_current_status": variant_state.get("status"),
                "variant_id": event["variant_id"],
            }
        )

    rows.sort(key=lambda row: (row["trial_id"], row["run_id"]))
    unresolved = [row["run_id"] for row in rows if row["period_id"] is None or row["cost_mode"] is None]
    if unresolved:
        raise CorpusIndexError(f"unresolved period/cost semantics for runs: {sorted(unresolved)[:5]}")

    return {
        "family_ontology_digest": family_ontology.ontology_digest(),
        "family_ontology_version": family_ontology.FAMILY_ONTOLOGY_VERSION,
        "generated_from": history.generated_from,
        "historical_instrument_provenance": HISTORICAL_INSTRUMENT_PROVENANCE,
        "instrument_contract_schema_version": instrument_contract.INSTRUMENT_CONTRACT_SCHEMA_VERSION,
        "rows": rows,
        "schema_version": CORPUS_INDEX_SCHEMA_VERSION,
        "summary": _summarize(rows),
    }


def _metrics_schema_version(metrics: dict[str, Any]) -> str:
    """Tag metric-field coverage so incomparable generations cannot be pooled."""
    return "METRICS_V2_NINE_FIELD" if len(metrics) == 9 else f"METRICS_PARTIAL_{len(metrics)}_FIELD"


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def _tally(key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            value = row.get(key)
            counts[str(value)] = counts.get(str(value), 0) + 1
        return dict(sorted(counts.items()))

    return {
        "by_canonical_family": _tally("canonical_family_id"),
        "by_cost_mode": _tally("cost_mode"),
        "by_evidence_capability": _tally("evidence_capability"),
        "by_instrument_contract": _tally("instrument_contract_id"),
        "by_period": _tally("period_id"),
        "by_research_generation": _tally("research_generation"),
        "by_symbol": _tally("symbol"),
        "distinct_variants": len({row["variant_id"] for row in rows}),
        "total_rows": len(rows),
    }


def select(
    corpus: dict[str, Any],
    *,
    canonical_family_id: str | None = None,
    instrument_contract_id: str | None = None,
    require_bar_path: bool = False,
    allow_cross_instrument: bool = False,
) -> dict[str, Any]:
    """Query the corpus with fail-closed instrument and evidence rules.

    Returns the selected rows plus telemetry naming exactly what was excluded
    and why, so an analysis can never quietly run on fewer rows than it thinks.
    """
    rows = list(corpus["rows"])
    telemetry: dict[str, Any] = {"input_rows": len(rows), "excluded": {}}

    if canonical_family_id is not None:
        family_ontology.family_record(canonical_family_id)
        kept = [row for row in rows if row["canonical_family_id"] == canonical_family_id]
        telemetry["excluded"]["family_mismatch"] = len(rows) - len(kept)
        rows = kept

    if instrument_contract_id is not None:
        instrument_contract.contract_payload(instrument_contract_id)
        kept = [row for row in rows if row["instrument_contract_id"] == instrument_contract_id]
        telemetry["excluded"]["instrument_contract_mismatch"] = len(rows) - len(kept)
        rows = kept

    if require_bar_path:
        kept = [row for row in rows if row["evidence_capability"] == BAR_PATH]
        excluded = len(rows) - len(kept)
        telemetry["excluded"]["summary_only_rows"] = excluded
        if excluded:
            telemetry["summary_only_excluded_generations"] = sorted(
                {row["research_generation"] for row in rows if row["evidence_capability"] == SUMMARY_ONLY}
            )
        rows = kept
        if not rows:
            raise CorpusIndexError(
                "bar-path query matched no rows: every candidate row is SUMMARY_ONLY "
                f"(excluded {excluded}); V1 evidence cannot satisfy a per-bar requirement"
            )

    # Default corpus rule: FAIL_CLOSED_ON_MIXED_INSTRUMENT_CORPUS.
    instrument_contract.assert_single_instrument_contract(
        [row["instrument_contract_id"] for row in rows],
        allow_cross_instrument=allow_cross_instrument,
    )
    telemetry["selected_rows"] = len(rows)
    telemetry["instrument_contracts"] = sorted({row["instrument_contract_id"] for row in rows})
    telemetry["cross_instrument_declared"] = bool(allow_cross_instrument)
    return {"rows": rows, "telemetry": telemetry}


def corpus_digest(corpus: dict[str, Any]) -> str:
    return sha256_bytes(canonical_bytes(corpus))


def write_corpus(root: Path = RESEARCH_ROOT) -> dict[str, Any]:
    corpus = build_corpus(root)
    path = root / "corpus_index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(corpus) + b"\n")
    return corpus


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m qntylab.corpus_index")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build", help="rebuild experiments/research/corpus_index.json")
    subparsers.add_parser("summary", help="print the corpus summary without writing")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            corpus = write_corpus()
            print(json.dumps({"digest": corpus_digest(corpus), "summary": corpus["summary"]}, indent=2, sort_keys=True))
        else:
            corpus = build_corpus()
            print(json.dumps(corpus["summary"], indent=2, sort_keys=True))
    except (CorpusIndexError, LedgerError, family_ontology.FamilyOntologyError, instrument_contract.InstrumentContractError) as exc:
        print(f"corpus index error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
