"""Deterministic discovery index for canonical Jigsaw evidence pieces (F-02).

Jigsaw research produces immutable, frozen evidence artifacts under
``experiments/research/<experiment>/result.json``.  Those artifacts are
scientific records with no deterministic query surface: later synthesis code
has had to remember paths, grep, or read prose to find out what evidence
exists.  This module builds a small **derived, read-only discovery index**
over that evidence -- it does not reduce, score, vote on, weigh, or
reinterpret any of it.  See ``experiments/research/jigsaw_index.json`` for the
generated artifact and :mod:`qntylab.corpus_index` for the sibling index over
strategy-trial evidence (a different ontology; this module does not extend
it).

Eligibility contract
---------------------
Path location is used only as the repository scan boundary (everything under
``experiments/research/``).  Membership itself is decided purely by explicit
artifact self-declaration: a JSON object whose top-level ``schema_version``
string exists.  Two nested namespaces matter:

* ``RECOGNIZED_SCHEMA_FAMILY_PREFIX`` (``"jigsaw-evidence-piece-"``) marks a
  file as *claiming* to be a Jigsaw evidence-piece artifact.
* ``SUPPORTED_SCHEMA_VERSIONS`` is the subset of that family this module
  knows how to parse without inventing structure (today: exactly
  ``jigsaw-evidence-piece-v0``, the only schema version any canonical source
  currently uses).

A file that claims the family but is not in the supported set -- or claims
the family with a payload shape this module cannot parse without guessing --
fails the build closed (:class:`JigsawIndexError`) rather than being silently
dropped. A file that never claims the family at all is simply not in scope;
several other ``experiments/research/jigsaw_*`` artifacts exist (e.g.
in-flight or graveyarded condition-dependence and external-replication
experiments) that do not self-declare this schema and are not canonical
frozen Jigsaw *evidence pieces* under the current research ledger -- they are
correctly excluded, not silently dropped, because they were never eligible.

Two known native shapes exist for the supported schema and both are
represented without collapsing one into the other:

* ``MULTI_PIECE_ARRAY`` -- a ``pieces`` list of independently classified
  propositions (e.g. Jigsaw Harvest V0's four propositions).
* ``SINGLE_PIECE_OBJECT`` -- no ``pieces`` list; the whole document is one
  piece (e.g. the funding-pressure/volatility frozen negative result).

This module never manufactures independence, confidence, evidence weight, or
promotion authority, and it never rewrites a source artifact.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .research_ledger import RESEARCH_ROOT, canonical_bytes, sha256_bytes

JIGSAW_INDEX_SCHEMA_VERSION = "JIGSAW_INDEX_V0"
JIGSAW_INDEX_FILENAME = "jigsaw_index.json"

RECOGNIZED_SCHEMA_FAMILY_PREFIX = "jigsaw-evidence-piece-"
SUPPORTED_SCHEMA_VERSIONS = frozenset({"jigsaw-evidence-piece-v0"})

# Fields that, when present as a dict, carry the frozen data/history binding
# a piece was measured against. Different native shapes use different names
# for this; both are recognized without merging their semantics.
_BINDING_FIELD_CANDIDATES = ("snapshot_binding", "bound")

# Native scientific vocabulary preserved verbatim when explicitly present.
# Nothing here is invented when absent, and nothing is collapsed into a
# shared PASS/FAIL vocabulary.
_NATIVE_SCIENTIFIC_KEYS = ("piece_type", "classification", "decision", "adjudication", "evidence_class")
_PRIMARY_NATIVE_KEYS = ("proposition", "decision", "adjudication")

_EXPOSURE_CONTEXT_KEYS = ("prior_exposure_context", "prior_exposure_note")


class JigsawIndexError(RuntimeError):
    """The Jigsaw evidence census could not be built in a fail-closed way."""


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def scan_sources(
    root: Path = RESEARCH_ROOT,
) -> tuple[list[tuple[Path, dict[str, Any], str, str]], list[dict[str, Any]]]:
    """Read-only census of ``root`` for Jigsaw evidence-piece artifacts.

    Never raises and never writes anything. Returns ``(eligible,
    unsupported)`` where ``eligible`` is a list of
    ``(path, document, schema_version, content_sha256)`` tuples for sources
    using a schema this module knows how to parse, and ``unsupported`` lists
    sources that self-declare the recognized Jigsaw evidence-piece family
    but with a schema version this module does not support.
    """
    index_path = root / JIGSAW_INDEX_FILENAME
    eligible: list[tuple[Path, dict[str, Any], str, str]] = []
    unsupported: list[dict[str, Any]] = []
    if not root.exists():
        return eligible, unsupported
    for path in sorted(root.rglob("*.json")):
        if path == index_path:
            continue
        document = _read_json_object(path)
        if document is None:
            continue
        schema_version = document.get("schema_version")
        if not isinstance(schema_version, str) or not schema_version.startswith(RECOGNIZED_SCHEMA_FAMILY_PREFIX):
            continue
        content_sha256 = sha256_bytes(path.read_bytes())
        if schema_version in SUPPORTED_SCHEMA_VERSIONS:
            eligible.append((path, document, schema_version, content_sha256))
        else:
            unsupported.append(
                {
                    "relative_path": str(path),
                    "content_sha256": content_sha256,
                    "schema_version": schema_version,
                    "reason": "schema declares the recognized Jigsaw evidence-piece family "
                    f"but version {schema_version!r} is not in SUPPORTED_SCHEMA_VERSIONS",
                }
            )
    return eligible, unsupported


def _native_scientific_fields(piece: dict[str, Any]) -> dict[str, Any]:
    fields = {key: piece[key] for key in _NATIVE_SCIENTIFIC_KEYS if key in piece}
    primary = piece.get("primary")
    if isinstance(primary, dict):
        for key in _PRIMARY_NATIVE_KEYS:
            dotted = f"primary.{key}"
            if key in primary and dotted not in fields:
                fields[dotted] = primary[key]
    return fields


def _frozen_binding(piece: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    for key in _BINDING_FIELD_CANDIDATES:
        value = piece.get(key)
        if isinstance(value, dict):
            return value, key
    return None, None


def _prior_feature_exposure(piece: dict[str, Any]) -> str:
    raw = piece.get("prior_feature_exposure")
    if raw == "YES":
        return "YES"
    if raw == "NO":
        return "NO"
    return "UNKNOWN"


def _exposure_context(piece: dict[str, Any]) -> str | None:
    for key in _EXPOSURE_CONTEXT_KEYS:
        value = piece.get(key)
        if isinstance(value, str):
            return value
    return None


def _parse_source(
    relative_path: str,
    document: dict[str, Any],
    schema_version: str,
    content_sha256: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    experiment_id = document.get("experiment_id")
    if not isinstance(experiment_id, str) or not experiment_id:
        raise JigsawIndexError(f"malformed required source identity (missing experiment_id): {relative_path}")

    project_id = document.get("project_id") if isinstance(document.get("project_id"), str) else None
    preregistration_id = (
        document.get("preregistration_id") if isinstance(document.get("preregistration_id"), str) else None
    )
    directory_id = Path(relative_path).parent.name
    top_authority = document.get("authority") if isinstance(document.get("authority"), str) else None
    top_research_status = document.get("research_status") if isinstance(document.get("research_status"), str) else None
    top_promotion_eligible = (
        document.get("promotion_eligible") if isinstance(document.get("promotion_eligible"), bool) else None
    )

    raw_pieces = document.get("pieces")
    if raw_pieces is not None:
        if not isinstance(raw_pieces, list) or not raw_pieces:
            raise JigsawIndexError(
                f"unsupported eligible Jigsaw evidence payload shape (pieces is not a non-empty list): {relative_path}"
            )
        declared_count = document.get("piece_count")
        if declared_count is not None and declared_count != len(raw_pieces):
            raise JigsawIndexError(
                f"impossible provenance (declared piece_count {declared_count!r} != "
                f"len(pieces) {len(raw_pieces)}): {relative_path}"
            )
        proposition_ids: list[str] = []
        for piece in raw_pieces:
            if not isinstance(piece, dict):
                raise JigsawIndexError(
                    f"unsupported eligible Jigsaw evidence payload shape (piece is not an object): {relative_path}"
                )
            proposition_id = piece.get("proposition_id")
            if not isinstance(proposition_id, str) or not proposition_id:
                raise JigsawIndexError(
                    f"malformed required source identity (missing proposition_id): {relative_path}"
                )
            proposition_ids.append(proposition_id)
        if len(set(proposition_ids)) != len(proposition_ids):
            raise JigsawIndexError(f"duplicate piece identity within a single source: {relative_path}")
        declared_order = document.get("piece_order")
        if declared_order is not None and list(declared_order) != proposition_ids:
            raise JigsawIndexError(f"impossible provenance (piece_order does not match pieces[]): {relative_path}")
        shape = "MULTI_PIECE_ARRAY"
        piece_defs: list[tuple[int, dict[str, Any]]] = list(enumerate(raw_pieces))
    else:
        shape = "SINGLE_PIECE_OBJECT"
        piece_defs = [(0, document)]

    rows: list[dict[str, Any]] = []
    for index_in_source, piece in piece_defs:
        if shape == "MULTI_PIECE_ARRAY":
            piece_identity = piece["proposition_id"]
            piece_identity_kind = "SOURCE_NATIVE_PROPOSITION_ID"
        else:
            piece_identity = experiment_id
            piece_identity_kind = "SOURCE_NATIVE_EXPERIMENT_ID"

        piece_authority = piece.get("authority") if isinstance(piece.get("authority"), str) else None
        piece_research_status = piece.get("research_status") if isinstance(piece.get("research_status"), str) else None
        piece_promotion_eligible = (
            piece.get("promotion_eligible") if isinstance(piece.get("promotion_eligible"), bool) else None
        )
        authorities = piece.get("authorities") if isinstance(piece.get("authorities"), dict) else None
        binding, binding_field = _frozen_binding(piece)

        row_identity_payload = {
            "source_content_sha256": content_sha256,
            "piece_identity": piece_identity,
            "piece_identity_kind": piece_identity_kind,
            "piece_index_in_source": index_in_source,
        }
        row_id = "piece_" + sha256_bytes(canonical_bytes(row_identity_payload))[:24]

        rows.append(
            {
                "authority": {
                    "authorities": authorities,
                    "promotion_eligible": (
                        piece_promotion_eligible if piece_promotion_eligible is not None else top_promotion_eligible
                    ),
                    "top_level_authority": piece_authority or top_authority,
                },
                "frozen_binding": binding,
                "frozen_binding_source_field": binding_field,
                "identity": {
                    "directory_id": directory_id,
                    "experiment_id": experiment_id,
                    "preregistration_id": preregistration_id,
                    "project_id": project_id,
                },
                "native_payload": piece,
                "native_scientific_fields": _native_scientific_fields(piece),
                "piece_identity": piece_identity,
                "piece_identity_kind": piece_identity_kind,
                "prior_feature_exposure": _prior_feature_exposure(piece),
                "prior_feature_exposure_context": _exposure_context(piece),
                "provenance": {
                    "piece_index_in_source": index_in_source,
                    "source_artifact_relative_path": relative_path,
                    "source_content_digest": f"sha256:{content_sha256}",
                    "source_schema_version": schema_version,
                    "source_shape": shape,
                },
                "research_status": piece_research_status or top_research_status,
                "row_id": row_id,
            }
        )

    source_row = {
        "content_sha256": content_sha256,
        "piece_count": len(rows),
        "piece_identities": [row["piece_identity"] for row in rows],
        "relative_path": relative_path,
        "schema_version": schema_version,
        "shape": shape,
    }
    return rows, source_row


def build_index(root: Path = RESEARCH_ROOT) -> dict[str, Any]:
    """Deterministically rebuild the Jigsaw evidence index from canonical sources.

    Raises :class:`JigsawIndexError` (fail closed) rather than returning a
    partial index if any eligible source is unsupported, malformed, or in
    conflict with another source's identity.
    """
    eligible, unsupported = scan_sources(root)
    issues: list[str] = []
    for entry in unsupported:
        issues.append(f"unsupported eligible Jigsaw evidence schema: {entry['relative_path']} ({entry['reason']})")

    rows: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    seen_identity: dict[str, str] = {}
    source_digests: dict[str, str] = {}

    for path, document, schema_version, content_sha256 in eligible:
        relative_path = str(path)
        try:
            piece_rows, source_row = _parse_source(relative_path, document, schema_version, content_sha256)
        except JigsawIndexError as exc:
            issues.append(str(exc))
            continue
        sources.append(source_row)
        source_digests[relative_path] = content_sha256
        for row in piece_rows:
            identity = row["piece_identity"]
            if identity in seen_identity:
                issues.append(
                    f"duplicate piece identity {identity!r}: {seen_identity[identity]} and {relative_path}"
                )
                continue
            seen_identity[identity] = relative_path
            rows.append(row)

    if issues:
        raise JigsawIndexError("; ".join(sorted(issues)))

    rows.sort(key=lambda row: (row["provenance"]["source_artifact_relative_path"], row["provenance"]["piece_index_in_source"]))
    sources.sort(key=lambda source: source["relative_path"])

    return {
        "eligibility_rule": {
            "recognized_schema_family_prefix": RECOGNIZED_SCHEMA_FAMILY_PREFIX,
            "scan_root": str(root),
            "supported_schema_versions": sorted(SUPPORTED_SCHEMA_VERSIONS),
        },
        "generated_from": {"source_files_sha256": dict(sorted(source_digests.items()))},
        "pieces": rows,
        "schema_version": JIGSAW_INDEX_SCHEMA_VERSION,
        "sources": sources,
        "summary": _summarize(rows, sources),
    }


def _summarize(rows: list[dict[str, Any]], sources: list[dict[str, Any]]) -> dict[str, Any]:
    def _tally(values: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        return dict(sorted(counts.items()))

    return {
        "by_experiment_id": _tally([row["identity"]["experiment_id"] for row in rows]),
        "by_prior_feature_exposure": _tally([row["prior_feature_exposure"] for row in rows]),
        "by_research_status": _tally([str(row["research_status"]) for row in rows]),
        "by_source_shape": _tally([source["shape"] for source in sources]),
        "total_pieces": len(rows),
        "total_sources": len(sources),
    }


def index_digest(index: dict[str, Any]) -> str:
    return sha256_bytes(canonical_bytes(index))


def write_index(root: Path = RESEARCH_ROOT) -> dict[str, Any]:
    index = build_index(root)
    path = root / JIGSAW_INDEX_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(index) + b"\n")
    return index


def load_index(root: Path = RESEARCH_ROOT) -> dict[str, Any]:
    path = root / JIGSAW_INDEX_FILENAME
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise JigsawIndexError(f"index missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise JigsawIndexError(f"malformed JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise JigsawIndexError(f"JSON object required: {path}")
    return value


def doctor(root: Path = RESEARCH_ROOT) -> list[str]:
    """Fail-closed staleness/integrity check.

    Rebuilds the index in memory from current canonical source bytes and
    compares it against the on-disk artifact byte-for-byte; a derived index
    that no longer matches its sources is reported stale rather than trusted.
    """
    try:
        expected = build_index(root)
    except JigsawIndexError as exc:
        return [str(exc)]
    try:
        actual = load_index(root)
    except JigsawIndexError as exc:
        return [str(exc)]
    if actual != expected:
        return ["stale or divergent jigsaw_index.json"]
    return []


# ---------------------------------------------------------------------------
# Query surface
# ---------------------------------------------------------------------------


def list_pieces(
    index: dict[str, Any],
    *,
    project_id: str | None = None,
    experiment_id: str | None = None,
    directory_id: str | None = None,
    native_field: str | None = None,
    native_value: Any = None,
    prior_feature_exposure: str | None = None,
    promotion_eligible: bool | None = None,
) -> list[dict[str, Any]]:
    """Filter indexed pieces. Every filter is an exact match; none are fuzzy."""
    rows = list(index["pieces"])
    if project_id is not None:
        rows = [row for row in rows if row["identity"]["project_id"] == project_id]
    if experiment_id is not None:
        rows = [row for row in rows if row["identity"]["experiment_id"] == experiment_id]
    if directory_id is not None:
        rows = [row for row in rows if row["identity"]["directory_id"] == directory_id]
    if native_field is not None:
        rows = [row for row in rows if row["native_scientific_fields"].get(native_field) == native_value]
    if prior_feature_exposure is not None:
        rows = [row for row in rows if row["prior_feature_exposure"] == prior_feature_exposure]
    if promotion_eligible is not None:
        rows = [row for row in rows if row["authority"]["promotion_eligible"] == promotion_eligible]
    return rows


def get_piece(index: dict[str, Any], piece_identity: str) -> dict[str, Any] | None:
    """Exact stable-identity lookup. Unknown identity returns ``None``, never a guess."""
    matches = [row for row in index["pieces"] if row["piece_identity"] == piece_identity]
    if len(matches) > 1:  # pragma: no cover - build() already fails closed on duplicates
        raise JigsawIndexError(f"ambiguous piece identity in index: {piece_identity!r}")
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m qntylab.jigsaw_index")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build", help="rebuild experiments/research/jigsaw_index.json")
    subparsers.add_parser("doctor", help="check the index for staleness or integrity issues")
    subparsers.add_parser("summary", help="print the index summary without writing")
    list_parser = subparsers.add_parser("list", help="list indexed pieces")
    list_parser.add_argument("--project-id")
    list_parser.add_argument("--experiment-id")
    list_parser.add_argument("--directory-id")
    list_parser.add_argument("--prior-feature-exposure", choices=["YES", "NO", "UNKNOWN"])
    get_parser = subparsers.add_parser("get", help="get exactly one piece by stable identity")
    get_parser.add_argument("piece_identity")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            index = write_index()
            print(json.dumps({"digest": index_digest(index), "summary": index["summary"]}, indent=2, sort_keys=True))
        elif args.command == "doctor":
            issues = doctor()
            if issues:
                for issue in issues:
                    print(issue, file=sys.stderr)
                raise SystemExit(1)
            print("jigsaw_index: OK")
        elif args.command == "summary":
            index = build_index()
            print(json.dumps(index["summary"], indent=2, sort_keys=True))
        elif args.command == "list":
            index = load_index()
            rows = list_pieces(
                index,
                project_id=args.project_id,
                experiment_id=args.experiment_id,
                directory_id=args.directory_id,
                prior_feature_exposure=args.prior_feature_exposure,
            )
            print(json.dumps([row["piece_identity"] for row in rows], indent=2, sort_keys=True))
        else:
            index = load_index()
            piece = get_piece(index, args.piece_identity)
            if piece is None:
                print(f"no such piece: {args.piece_identity}", file=sys.stderr)
                raise SystemExit(1)
            print(json.dumps(piece, indent=2, sort_keys=True))
    except JigsawIndexError as exc:
        print(f"jigsaw index error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
