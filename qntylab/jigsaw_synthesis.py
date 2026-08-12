"""Deterministic cross-piece synthesis-eligibility derivation for canonical
Jigsaw evidence (F-03).

The F-02 discovery index (:mod:`qntylab.jigsaw_index`) answers "what canonical
Jigsaw evidence pieces exist?". It deliberately does not answer "how many
independent confirmations exist?", "which findings can be summarized
together?", or "does more evidence mean stronger evidence?". This module
answers a narrow, conservative version of those questions without ever
scoring, ranking, or aggregating evidence strength.

For every unordered pair of indexed pieces it records only mechanically or
source-supported facts -- shared source artifact, shared explicit snapshot
identity, decision-window relation, shared explicit feature/outcome fields --
and derives two small categorical classifications from those facts alone:

* ``claim_relation`` -- whether the two native propositions are the same,
  related, different, or too structurally incomparable to say.
* ``independence_status`` -- whether the two pieces share frozen history,
  merely overlap in time with no dataset identity established, or neither.

A small deterministic table then derives ``allowed_synthesis`` from those two
classifications. Nothing here infers dataset identity from matching
cardinality, matching symbol counts, or similarly-named fields (see
``qntylab.jigsaw_index``'s own doc for the same discipline on the discovery
side); every YES/NO is backed by an explicit, already-indexed field, and
anything else is UNKNOWN or NOT_ESTABLISHED. No function in this module
inspects a piece's identity string -- the same code runs unchanged for any
current or future canonical Jigsaw piece the F-02 index admits.

This module never assigns a confidence score, evidence weight, vote count, or
family verdict, never rewrites a native scientific classification, and never
grants State Snapshot, Router, Qnty, trading, or promotion authority. See
``experiments/research/jigsaw_synthesis_eligibility_v0/eligibility.json`` for
the generated artifact and its accompanying design note.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from . import jigsaw_index as _jigsaw_index
from .jigsaw_index import RESEARCH_ROOT
from .research_ledger import canonical_bytes, sha256_bytes

SYNTHESIS_SCHEMA_VERSION = "JIGSAW_SYNTHESIS_ELIGIBILITY_V0"
SYNTHESIS_DIRECTORY_NAME = "jigsaw_synthesis_eligibility_v0"
SYNTHESIS_FILENAME = "eligibility.json"

# The F-02 canonical merge commit this module's discovery-index consumption
# contract targets. This is a fixed provenance anchor, not a live
# `git rev-parse HEAD` read at generation time -- reading the live HEAD would
# make the artifact depend on wall-clock repository state (every later commit
# on this same phase branch would change it) and break byte-identical
# rebuild. It records which canonical upstream state F-02's discovery index
# was authoritative as of when this synthesis contract was written; it is not
# re-derived and carries no scientific content of its own.
CANONICAL_BASE_SHA = "ebdcc4e4bb3cc6015cad086a221597b6995f71ee"

AUTHORITY = "NON_AUTHORITATIVE_SYNTHESIS_METADATA_ONLY"

_CLAIM_RELATIONS = frozenset(
    {"IDENTICAL_CLAIM", "RELATED_DISTINCT_CLAIM", "DIFFERENT_CLAIM", "CLAIM_RELATION_NOT_ESTABLISHED"}
)
_INDEPENDENCE_STATUSES = frozenset(
    {
        "SHARED_FROZEN_HISTORY",
        "OVERLAPPING_HISTORY_INDEPENDENCE_NOT_ESTABLISHED",
        "INDEPENDENCE_NOT_ESTABLISHED",
        "INDEPENDENT_REPLICATION_EXPLICITLY_ESTABLISHED",
    }
)
_SYNTHESIS_ELIGIBILITIES = frozenset(
    {"SEPARATE_ONLY", "JOINT_CONTEXT_ONLY", "SAME_HISTORY_MULTI_PROPOSITION_CONTEXT", "INDEPENDENT_CONFIRMATION_ELIGIBLE"}
)

_PROHIBITED_INFERENCES = (
    "independent replication of these findings",
    "a combined or family-level verdict across the referenced pieces",
    "a confidence, evidence, or significance score",
    "State Snapshot feature eligibility",
    "causal, trading, or strategy interpretation",
    "an aggregate claim stronger than either native source result",
)


class JigsawSynthesisError(RuntimeError):
    """The synthesis eligibility artifact could not be built in a fail-closed way."""


# ---------------------------------------------------------------------------
# Mechanical pairwise fact derivation.
#
# Every helper below reads only fields already present on an indexed piece
# row (provenance, identity, frozen_binding, native_payload,
# prior_feature_exposure -- all produced by qntylab.jigsaw_index). None
# special-cases a piece by its piece_identity string.
# ---------------------------------------------------------------------------


def _same_source_artifact(a: dict, b: dict) -> str:
    return "YES" if a["provenance"]["source_artifact_relative_path"] == b["provenance"]["source_artifact_relative_path"] else "NO"


def _same_experiment(a: dict, b: dict) -> str:
    ea, eb = a["identity"]["experiment_id"], b["identity"]["experiment_id"]
    if not isinstance(ea, str) or not isinstance(eb, str):
        return "UNKNOWN"
    return "YES" if ea == eb else "NO"


def _binding_snapshot_id(row: dict) -> str | None:
    binding = row.get("frozen_binding")
    if not isinstance(binding, dict):
        return None
    value = binding.get("snapshot_id")
    return value if isinstance(value, str) else None


def _same_snapshot_identity(a: dict, b: dict) -> str:
    sa, sb = _binding_snapshot_id(a), _binding_snapshot_id(b)
    if sa is None or sb is None:
        return "UNKNOWN"
    return "YES" if sa == sb else "NO"


def _binding_window(row: dict) -> tuple[datetime, datetime] | None:
    binding = row.get("frozen_binding")
    if not isinstance(binding, dict):
        return None
    raw = binding.get("decision_window")
    if not isinstance(raw, str) or ".." not in raw:
        return None
    start_s, _, end_s = raw.partition("..")
    try:
        start = datetime.fromisoformat(start_s.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return start, end


def _decision_window_relation(a: dict, b: dict) -> str:
    wa, wb = _binding_window(a), _binding_window(b)
    if wa is None or wb is None:
        return "UNKNOWN"
    a_start, a_end = wa
    b_start, b_end = wb
    if a_start == b_start and a_end == b_end:
        return "EXACT"
    if a_start <= b_start and a_end >= b_end:
        return "A_CONTAINS_B"
    if b_start <= a_start and b_end >= a_end:
        return "B_CONTAINS_A"
    if a_start <= b_end and b_start <= a_end:
        return "PARTIAL_OVERLAP"
    return "DISJOINT"


def _same_data_history(same_snapshot_identity: str, same_source_artifact: str) -> str:
    if same_snapshot_identity == "YES" or same_source_artifact == "YES":
        return "YES"
    if same_snapshot_identity == "NO":
        return "NO"
    return "NOT_ESTABLISHED"


def _native_field(row: dict, field: str) -> Any:
    payload = row.get("native_payload")
    if not isinstance(payload, dict):
        return None
    return payload.get(field)


def _same_native_string_field(a: dict, b: dict, field: str) -> str:
    """YES/NO only when both pieces expose the same-named explicit field as
    a string; otherwise NOT_ESTABLISHED. Never infers equivalence from
    similarly-named or similarly-shaped fields it did not directly compare."""
    va, vb = _native_field(a, field), _native_field(b, field)
    if not isinstance(va, str) or not isinstance(vb, str):
        return "NOT_ESTABLISHED"
    return "YES" if va == vb else "NO"


def _independence_status(
    same_snapshot_identity: str,
    same_source_artifact: str,
    decision_window_relation: str,
) -> str:
    """Independence is established by provenance, not by assertion.

    Shared frozen history is a pure provenance fact -- identical explicit
    snapshot identity or literally the same source artifact -- and is
    checked first, unconditionally. It dominates everything else: a piece
    cannot declare its way out of demonstrably sharing the same frozen
    snapshot or source artifact it shares.

    INDEPENDENT_REPLICATION_EXPLICITLY_ESTABLISHED is intentionally
    unreachable from current indexed provenance. A piece could in principle
    self-declare an intended replication relationship (e.g. an
    `explicit_independent_replication_of` field naming another piece), but
    that states *intended target identity*, not *empirical data
    independence* -- and JIGSAW_INDEX_V0 currently exposes no field that
    positively establishes independent data/history (only presence/absence
    of a matching snapshot_id, which at best proves non-identity, never
    independence). Per the phase contract, this module does not invent a new
    provenance field merely to make that state reachable, and does not treat
    a bare declaration as sufficient on its own -- so this status stays
    unreachable in V0 rather than being derived from circumstantial or
    self-asserted facts. See design_note.md.
    """
    if same_snapshot_identity == "YES" or same_source_artifact == "YES":
        return "SHARED_FROZEN_HISTORY"
    if decision_window_relation in ("EXACT", "A_CONTAINS_B", "B_CONTAINS_A", "PARTIAL_OVERLAP"):
        return "OVERLAPPING_HISTORY_INDEPENDENCE_NOT_ESTABLISHED"
    return "INDEPENDENCE_NOT_ESTABLISHED"


def _claim_relation(same_feature: str, same_outcome: str) -> str:
    if same_feature == "NOT_ESTABLISHED" or same_outcome == "NOT_ESTABLISHED":
        return "CLAIM_RELATION_NOT_ESTABLISHED"
    if same_feature == "YES" and same_outcome == "YES":
        return "IDENTICAL_CLAIM"
    if same_feature == "YES" or same_outcome == "YES":
        return "RELATED_DISTINCT_CLAIM"
    return "DIFFERENT_CLAIM"


def _allowed_synthesis(independence_status: str, claim_relation: str) -> str:
    if independence_status == "INDEPENDENT_REPLICATION_EXPLICITLY_ESTABLISHED" and claim_relation in (
        "IDENTICAL_CLAIM",
        "RELATED_DISTINCT_CLAIM",
    ):
        return "INDEPENDENT_CONFIRMATION_ELIGIBLE"
    if independence_status == "SHARED_FROZEN_HISTORY":
        return "SAME_HISTORY_MULTI_PROPOSITION_CONTEXT"
    if independence_status == "OVERLAPPING_HISTORY_INDEPENDENCE_NOT_ESTABLISHED" and claim_relation in (
        "IDENTICAL_CLAIM",
        "RELATED_DISTINCT_CLAIM",
    ):
        return "JOINT_CONTEXT_ONLY"
    return "SEPARATE_ONLY"


def _build_pair(row_a: dict, row_b: dict) -> dict[str, Any]:
    same_source_artifact = _same_source_artifact(row_a, row_b)
    same_experiment = _same_experiment(row_a, row_b)
    same_snapshot_identity = _same_snapshot_identity(row_a, row_b)
    decision_window_relation = _decision_window_relation(row_a, row_b)
    same_data_history = _same_data_history(same_snapshot_identity, same_source_artifact)
    same_feature = _same_native_string_field(row_a, row_b, "feature")
    same_outcome = _same_native_string_field(row_a, row_b, "outcome")
    independence_status = _independence_status(same_snapshot_identity, same_source_artifact, decision_window_relation)
    claim_relation = _claim_relation(same_feature, same_outcome)
    allowed_synthesis = _allowed_synthesis(independence_status, claim_relation)
    return {
        "pair_id": f"{row_a['piece_identity']}::{row_b['piece_identity']}",
        "piece_a": row_a["piece_identity"],
        "piece_b": row_b["piece_identity"],
        "same_source_artifact": same_source_artifact,
        "same_experiment": same_experiment,
        "same_snapshot_identity": same_snapshot_identity,
        "decision_window_relation": decision_window_relation,
        "same_data_history": same_data_history,
        "same_feature": same_feature,
        "same_outcome": same_outcome,
        "prior_exposure_relation": {
            "piece_a_prior_feature_exposure": row_a["prior_feature_exposure"],
            "piece_b_prior_feature_exposure": row_b["prior_feature_exposure"],
        },
        "claim_relation": claim_relation,
        "independence_status": independence_status,
        "allowed_synthesis": allowed_synthesis,
    }


# ---------------------------------------------------------------------------
# Piece inventory (forensic pass, mechanically extracted).
# ---------------------------------------------------------------------------


def _piece_inventory_row(row: dict) -> dict[str, Any]:
    return {
        "piece_identity": row["piece_identity"],
        "row_id": row["row_id"],
        "experiment_id": row["identity"]["experiment_id"],
        "project_id": row["identity"]["project_id"],
        "preregistration_id": row["identity"]["preregistration_id"],
        "source_artifact_relative_path": row["provenance"]["source_artifact_relative_path"],
        "source_content_digest": row["provenance"]["source_content_digest"],
        "source_shape": row["provenance"]["source_shape"],
        "native_scientific_fields": row["native_scientific_fields"],
        "feature": _native_field(row, "feature"),
        "outcome": _native_field(row, "outcome"),
        "frozen_binding": row["frozen_binding"],
        "frozen_binding_source_field": row["frozen_binding_source_field"],
        "prior_feature_exposure": row["prior_feature_exposure"],
        "prior_feature_exposure_context": row["prior_feature_exposure_context"],
        "top_level_authority": row["authority"]["top_level_authority"],
        "promotion_eligible": row["authority"]["promotion_eligible"],
    }


# ---------------------------------------------------------------------------
# Bounded synthesis statements.
#
# A statement is generated deterministically for every pair whose
# allowed_synthesis is not SEPARATE_ONLY -- never hand-picked, so there is no
# narrative cherry-picking of which pairs get a combined sentence. Wording is
# templated from already-computed categorical facts only.
# ---------------------------------------------------------------------------


def _native_source_verdict(row: dict) -> dict[str, Any]:
    return {
        "piece_identity": row["piece_identity"],
        "native_scientific_fields": row["native_scientific_fields"],
        "prior_feature_exposure": row["prior_feature_exposure"],
        "prior_feature_exposure_context": row["prior_feature_exposure_context"],
        "top_level_authority": row["authority"]["top_level_authority"],
        "promotion_eligible": row["authority"]["promotion_eligible"],
    }


def _dedup(items: list[Any]) -> list[Any]:
    seen: list[Any] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _relationship_basis(pair: dict) -> str:
    parts = []
    if pair["same_source_artifact"] == "YES":
        parts.append("SAME_SOURCE_ARTIFACT")
    if pair["same_snapshot_identity"] == "YES":
        parts.append("SAME_SNAPSHOT_ID")
    if not parts:
        parts.append(f"DECISION_WINDOW_{pair['decision_window_relation']}")
    return "+".join(parts)


_WINDOW_PHRASE = {
    "EXACT": "cover the identical decision window",
    "PARTIAL_OVERLAP": "partially overlap",
}


def _statement_text(pair: dict, row_a: dict, row_b: dict) -> str:
    a_id, b_id = pair["piece_a"], pair["piece_b"]
    basis = pair["allowed_synthesis"]

    if basis == "SAME_HISTORY_MULTI_PROPOSITION_CONTEXT":
        exp_a = row_a["identity"]["experiment_id"]
        exp_b = row_b["identity"]["experiment_id"]
        context = f"experiment {exp_a}" if exp_a == exp_b else f"experiments {exp_a} and {exp_b}"
        basis_bits = []
        if pair["same_source_artifact"] == "YES":
            basis_bits.append(f"source artifact {row_a['provenance']['source_artifact_relative_path']!r}")
        snap_a = _binding_snapshot_id(row_a)
        if pair["same_snapshot_identity"] == "YES" and snap_a:
            basis_bits.append(f"snapshot {snap_a!r}")
        basis_clause = " and ".join(basis_bits) if basis_bits else "the same frozen decision window"
        # Branch on claim_relation itself (already correctly derived by
        # _claim_relation) rather than re-deriving from same_feature/
        # same_outcome here -- re-deriving invited two bugs a hostile review
        # caught: (a) an IDENTICAL_CLAIM pair (same_feature AND same_outcome
        # both YES) fell into the "different features" branch below just
        # because same_outcome was checked first, and (b)
        # CLAIM_RELATION_NOT_ESTABLISHED pairs fell into the same "different"
        # wording as a genuine DIFFERENT_CLAIM, laundering NOT_ESTABLISHED
        # into a confident negative in reader-facing prose even though the
        # structured claim_relation field stayed conservative.
        if pair["claim_relation"] == "IDENTICAL_CLAIM":
            outcome_clause = (
                "Both propositions test the same explicit feature against the same explicit "
                "outcome definition, so their native verdicts remain separately reported and are "
                "not combined into a shared effect size."
            )
        elif pair["claim_relation"] == "RELATED_DISTINCT_CLAIM":
            if pair["same_outcome"] == "YES":
                outcome_clause = (
                    "Both propositions use the same explicit outcome definition but test different "
                    "features, so their native verdicts remain separately reported and are not "
                    "combined into a shared effect size."
                )
            else:
                outcome_clause = (
                    "Both propositions test the same explicit feature against different outcome "
                    "definitions, so their native verdicts remain separately reported."
                )
        elif pair["claim_relation"] == "DIFFERENT_CLAIM":
            outcome_clause = (
                "The propositions concern different features and different outcome definitions "
                "within that shared frozen context, so no combined input-output relationship is "
                "licensed."
            )
        else:  # CLAIM_RELATION_NOT_ESTABLISHED
            outcome_clause = (
                "Whether the propositions concern the same or different features and outcome "
                "definitions is not established from the indexed fields alone, so no combined "
                "input-output relationship is licensed."
            )
        return (
            f"{a_id} and {b_id} are distinct preregistered propositions from {context}, evaluated "
            f"within the identical frozen sample ({basis_clause}). {outcome_clause} Each piece's "
            "native classification, direction, and limitations remain exactly as recorded in its "
            "source evidence; this pairing licenses only a same-history contextual grouping, not "
            "independent replication, mutual confirmation, or a combined family verdict."
        )

    if basis == "JOINT_CONTEXT_ONLY":
        window_relation = pair["decision_window_relation"]
        if window_relation == "A_CONTAINS_B":
            window_phrase = f"overlap, with {b_id}'s decision window fully contained in {a_id}'s"
        elif window_relation == "B_CONTAINS_A":
            window_phrase = f"overlap, with {a_id}'s decision window fully contained in {b_id}'s"
        else:
            window_phrase = _WINDOW_PHRASE.get(window_relation, "overlap")
        return (
            f"{a_id} (from {row_a['identity']['experiment_id']}) and {b_id} (from "
            f"{row_b['identity']['experiment_id']}) are separate Jigsaw evidence pieces whose "
            f"decision windows {window_phrase}, but neither identical data/snapshot identity nor "
            "independent replication is established between them. They may be discussed together "
            "only as contextually related observations over that overlapping period; this is not "
            "mutual confirmation and does not create an aggregate or stronger scientific claim than "
            "either native source result."
        )

    if basis == "INDEPENDENT_CONFIRMATION_ELIGIBLE":
        return (
            f"{a_id} and {b_id} carry an explicit source-declared independent-replication "
            "relationship and sufficiently compatible native claims. They are eligible to be read "
            "as independent confirmation of a compatible finding, strictly subject to each piece's "
            "own native scope, direction, and limitations."
        )

    raise JigsawSynthesisError(f"no synthesis statement is licensed for allowed_synthesis={basis!r}")


def _build_statement(pair: dict, row_a: dict, row_b: dict) -> dict[str, Any]:
    limitations = _dedup(list(_native_field(row_a, "limitations") or []) + list(_native_field(row_b, "limitations") or []))
    return {
        "synthesis_id": f"SYN__{pair['piece_a']}__{pair['piece_b']}",
        "statement": _statement_text(pair, row_a, row_b),
        "supporting_piece_ids": [pair["piece_a"], pair["piece_b"]],
        "relationship_basis": _relationship_basis(pair),
        "claim_relation": pair["claim_relation"],
        "independence_status": pair["independence_status"],
        "synthesis_eligibility": pair["allowed_synthesis"],
        "native_source_verdicts": {
            pair["piece_a"]: _native_source_verdict(row_a),
            pair["piece_b"]: _native_source_verdict(row_b),
        },
        "limitations": limitations,
        "prohibited_inferences": list(_PROHIBITED_INFERENCES),
        "authority": AUTHORITY,
    }


# ---------------------------------------------------------------------------
# Whole-artifact build.
# ---------------------------------------------------------------------------


def _summarize(pairs: list[dict], statements: list[dict]) -> dict[str, Any]:
    def _tally(values: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        return dict(sorted(counts.items()))

    return {
        "total_pairs": len(pairs),
        "pairs_by_independence_status": _tally([p["independence_status"] for p in pairs]),
        "pairs_by_claim_relation": _tally([p["claim_relation"] for p in pairs]),
        "pairs_by_allowed_synthesis": _tally([p["allowed_synthesis"] for p in pairs]),
        "total_synthesis_statements": len(statements),
    }


def build_synthesis(root: Path = RESEARCH_ROOT) -> dict[str, Any]:
    """Deterministically rebuild the synthesis-eligibility artifact from the
    current canonical Jigsaw index (rebuilt fresh in memory; never trusts a
    possibly-stale on-disk ``jigsaw_index.json``).

    Raises :class:`JigsawSynthesisError` (fail closed) if the underlying
    index itself cannot be built cleanly.
    """
    try:
        index = _jigsaw_index.build_index(root)
    except _jigsaw_index.JigsawIndexError as exc:
        raise JigsawSynthesisError(f"jigsaw_index could not be built: {exc}") from exc

    pieces = sorted(index["pieces"], key=lambda row: row["piece_identity"])
    piece_inventory = [_piece_inventory_row(row) for row in pieces]

    pairs: list[dict[str, Any]] = []
    statements: list[dict[str, Any]] = []
    for row_a, row_b in itertools.combinations(pieces, 2):
        pair = _build_pair(row_a, row_b)
        pairs.append(pair)
        if pair["allowed_synthesis"] != "SEPARATE_ONLY":
            statements.append(_build_statement(pair, row_a, row_b))

    independent_replication_established = any(
        pair["independence_status"] == "INDEPENDENT_REPLICATION_EXPLICITLY_ESTABLISHED" for pair in pairs
    )

    return {
        "authority": AUTHORITY,
        "generated_from": {
            "canonical_base_sha": CANONICAL_BASE_SHA,
            "jigsaw_index_schema": index["schema_version"],
            "jigsaw_index_digest": _jigsaw_index.index_digest(index),
            "source_files_sha256": index["generated_from"]["source_files_sha256"],
        },
        "piece_inventory": piece_inventory,
        "pair_relationships": pairs,
        "synthesis_statements": statements,
        "global_constraints": {
            "state_snapshot_authority": "NONE",
            "router_authority": "NONE",
            "qnty_authority": "NONE",
            "trading_authority": "NONE",
            "promotion_authority": "NONE",
            "independent_replication_established": "YES" if independent_replication_established else "NO",
        },
        "summary": _summarize(pairs, statements),
        "schema_version": SYNTHESIS_SCHEMA_VERSION,
    }


def synthesis_digest(synthesis: dict[str, Any]) -> str:
    return sha256_bytes(canonical_bytes(synthesis))


def write_synthesis(root: Path = RESEARCH_ROOT) -> dict[str, Any]:
    synthesis = build_synthesis(root)
    path = root / SYNTHESIS_DIRECTORY_NAME / SYNTHESIS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(synthesis) + b"\n")
    return synthesis


def load_synthesis(root: Path = RESEARCH_ROOT) -> dict[str, Any]:
    path = root / SYNTHESIS_DIRECTORY_NAME / SYNTHESIS_FILENAME
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise JigsawSynthesisError(f"synthesis artifact missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise JigsawSynthesisError(f"malformed JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise JigsawSynthesisError(f"JSON object required: {path}")
    return value


def doctor(root: Path = RESEARCH_ROOT) -> list[str]:
    """Fail-closed staleness/integrity check.

    First requires the upstream F-02 index itself to be current (a stale
    discovery index makes any synthesis over it untrustworthy); then rebuilds
    the synthesis artifact in memory and compares it byte-for-byte against
    the on-disk artifact.
    """
    index_issues = _jigsaw_index.doctor(root)
    if index_issues:
        return [f"jigsaw_index is not current (synthesis cannot be trusted): {issue}" for issue in index_issues]
    try:
        expected = build_synthesis(root)
    except JigsawSynthesisError as exc:
        return [str(exc)]
    try:
        actual = load_synthesis(root)
    except JigsawSynthesisError as exc:
        return [str(exc)]
    if actual != expected:
        return ["stale or divergent jigsaw_synthesis_eligibility.json"]
    return []


# ---------------------------------------------------------------------------
# Query surface
# ---------------------------------------------------------------------------


def get_pair(synthesis: dict[str, Any], piece_a: str, piece_b: str) -> dict[str, Any] | None:
    """Exact unordered-pair lookup. Unknown/misordered identities return
    ``None``, never a guess."""
    for pair in synthesis["pair_relationships"]:
        if {pair["piece_a"], pair["piece_b"]} == {piece_a, piece_b}:
            return pair
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m qntylab.jigsaw_synthesis")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build", help="rebuild experiments/research/jigsaw_synthesis_eligibility_v0/eligibility.json")
    subparsers.add_parser("doctor", help="check the synthesis artifact for staleness or integrity issues")
    subparsers.add_parser("summary", help="print the synthesis summary without writing")
    pair_parser = subparsers.add_parser("pair", help="get exactly one pair relationship by piece identities")
    pair_parser.add_argument("piece_a")
    pair_parser.add_argument("piece_b")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            synthesis = write_synthesis()
            print(json.dumps({"digest": synthesis_digest(synthesis), "summary": synthesis["summary"]}, indent=2, sort_keys=True))
        elif args.command == "doctor":
            issues = doctor()
            if issues:
                for issue in issues:
                    print(issue, file=sys.stderr)
                raise SystemExit(1)
            print("jigsaw_synthesis: OK")
        elif args.command == "summary":
            synthesis = build_synthesis()
            print(json.dumps(synthesis["summary"], indent=2, sort_keys=True))
        else:
            synthesis = load_synthesis()
            pair = get_pair(synthesis, args.piece_a, args.piece_b)
            if pair is None:
                print(f"no such pair: {args.piece_a} / {args.piece_b}", file=sys.stderr)
                raise SystemExit(1)
            print(json.dumps(pair, indent=2, sort_keys=True))
    except JigsawSynthesisError as exc:
        print(f"jigsaw synthesis error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
