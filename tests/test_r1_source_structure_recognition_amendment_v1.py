"""Hostile tests for
experiments/data/r1_source_structure_recognition_amendment_v1.json
(a PROTOCOL_AMENDMENT_CANDIDATE, not yet frozen -- see its own "status" field).

Closes the first missing normative boundary identified by the prior forensic/
adjudication audit: X -> H -> S, i.e. derive_header(X, G) -> H | FRAMING_FAILURE
composed with recognize(H, G, R) -> RECOGNIZED(S) | NO_MATCH | AMBIGUOUS |
MALFORMED_HEADER. No frozen artifact previously defined either function
mechanically; Parser A (order-insensitive) and Parser B (order-sensitive)
diverge, and neither reads the schema registry at runtime.

This file defines a standalone, explicitly non-authoritative, disposable
"candidate recognition evaluator" used only to exercise this candidate's own
fixtures during hostile review. It is not imported by, called by, or
presented as production code, and it does not import qntylab.r1_reference_parser
or qntylab.r1_retention_candidate: this candidate's semantics are derived from
the candidate text and the two base artifacts it amends, not from either
parser's implementation. Per the corrected Cybernetics ordering from the
preceding adjudication pass, this evaluator's job is to let hostile review
exercise an already-fully-determinate candidate, not to author the semantics
that review is deciding.

No production parser, materializer, or registry file is modified or imported
for its behavior by this test file.
"""
import gzip
import hashlib
import json
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_PATH = REPO_ROOT / "experiments/data/r1_source_structure_recognition_amendment_v1.json"
CONTRACT_PATH = REPO_ROOT / "experiments/data/r1_normalized_evidence_contract_v1.json"
REGISTRY_PATH = REPO_ROOT / "experiments/data/r1_source_schema_registry_v1.json"

REAL_OBJECT_SHA256 = "cbca6933a8f0a11429661cfa93b04056055d776ee199209e8af9719ad2060a33"
CACHE_DIR = REPO_ROOT / ".r1_input_cache/sha256"

BASE_HEADER = ("timestamp", "symbol", "side", "size", "price", "tickDirection",
               "trdMatchID", "grossValue", "homeNotional", "foreignNotional")
BASE_ROW = ("1700000000.000", "TESTUSDT", "Buy", "1", "100", "PlusTick",
            "t-1", "1e8", "1", "100")


def _canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def _canonical_hash(value):
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _candidate():
    return json.loads(CANDIDATE_PATH.read_bytes())


def _build_object(header_line: str, rows: list, line_ending: str = "\n",
                   trailing_newline: bool = True) -> bytes:
    body = line_ending.join([header_line] + [",".join(r) for r in rows])
    if trailing_newline:
        body += line_ending
    return gzip.compress(body.encode("utf-8"))


# ---------------------------------------------------------------------------
# 1. Candidate recognition evaluator (test-only, non-authoritative, disposable)
# ---------------------------------------------------------------------------

FRAMING_FAILURE = "FRAMING_FAILURE"
MALFORMED_HEADER = "MALFORMED_HEADER"
NO_MATCH = "NO_MATCH"
RECOGNIZED = "RECOGNIZED"
AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class Disposition:
    kind: str
    reason: tuple = ()
    schema_id: Optional[str] = None


def _derive_header(raw_bytes: bytes):
    """derive_header(X, G) -> (H_raw: tuple[str, ...], None) | (None, Disposition(FRAMING_FAILURE)).

    Per gzip_completion_policy in the candidate text: successful decompression
    requires reaching a validated gzip end-of-stream (d.eof is True), not
    merely producing some decompressed output without an exception. A
    truncated/incomplete member -- including any proper prefix of an
    otherwise-valid member -- must fail closed as INVALID_GZIP *before*
    header extraction, well-formedness checking, or recognition ever run.

    Zero-length raw X is not a distinguished pre-gzip sentinel: it is not a
    complete gzip member (no 10-byte header is present), so it falls through
    to the same d.eof-based completion check as any other incomplete member
    and is classified INVALID_GZIP, per step 1. EMPTY_OBJECT (step 4) applies
    only to a *successfully decompressed* member whose decoded text is empty
    -- see the d.eof / d.unused_data checks and the post-decode `text == ""`
    check below.
    """
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        decompressed = d.decompress(raw_bytes)
        decompressed += d.flush()
    except (zlib.error, OSError, EOFError):
        return None, Disposition(FRAMING_FAILURE, ("INVALID_GZIP",))
    if not d.eof:
        # Decompression consumed the supplied bytes without raising, but
        # never reached a validated end-of-stream -- a truncated/incomplete
        # member. This is INVALID_GZIP, identically to a member that raises.
        return None, Disposition(FRAMING_FAILURE, ("INVALID_GZIP",))
    if d.unused_data:
        return None, Disposition(FRAMING_FAILURE, ("MULTI_MEMBER_GZIP",))
    try:
        text = decompressed.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None, Disposition(FRAMING_FAILURE, ("INVALID_UTF8",))
    if text.startswith("﻿"):
        return None, Disposition(FRAMING_FAILURE, ("BOM_PRESENT",))
    if text == "":
        return None, Disposition(FRAMING_FAILURE, ("EMPTY_OBJECT",))
    header_line = text.split("\n", 1)[0] if "\n" in text else text
    if "\r" in header_line:
        return None, Disposition(FRAMING_FAILURE, ("NON_LF_LINE_TERMINATOR",))
    h_raw = tuple(header_line.split(","))
    if len(h_raw) < 2:
        return None, Disposition(FRAMING_FAILURE, ("FEWER_THAN_TWO_TOKENS",))
    return h_raw, None


def _well_formed(h_raw: tuple):
    """well_formed(H_raw) -> (H: frozenset, None) | (None, Disposition(MALFORMED_HEADER))."""
    reasons = set()
    if any(tok == "" for tok in h_raw):
        reasons.add("EMPTY_TOKEN_NAME")
    seen = set()
    for tok in h_raw:
        if tok in seen:
            reasons.add("DUPLICATE_TOKEN_NAME")
        seen.add(tok)
    if any('"' in tok for tok in h_raw):
        reasons.add("QUOTE_CHARACTER_IN_TOKEN")
    if reasons:
        return None, Disposition(MALFORMED_HEADER, tuple(sorted(reasons)))
    return frozenset(h_raw), None


def _recognize(H: frozenset, known_schema_variants: dict) -> Disposition:
    """recognize(H, G, R) match-set evaluation. Total set-membership scan; no
    first-match short-circuit and no dependence on dict iteration order."""
    matches = sorted(
        schema_id for schema_id, entry in known_schema_variants.items()
        if frozenset(entry["field_set"]) == H
    )
    if len(matches) == 0:
        return Disposition(NO_MATCH)
    if len(matches) == 1:
        return Disposition(RECOGNIZED, schema_id=matches[0])
    return Disposition(AMBIGUOUS, reason=tuple(matches))


def _full_pipeline(raw_bytes: bytes, registry_bytes: bytes) -> Disposition:
    h_raw, framing_failure = _derive_header(raw_bytes)
    if framing_failure is not None:
        return framing_failure
    H, malformed = _well_formed(h_raw)
    if malformed is not None:
        return malformed
    registry = json.loads(registry_bytes)
    return _recognize(H, registry["known_schema_variants"])


# --- receipt / replay -------------------------------------------------------

RECEIPT_KIND = "SOURCE_STRUCTURE_RECOGNITION_EVALUATION_RECEIPT_V1"


@dataclass(frozen=True)
class Receipt:
    source_object_sha256: str
    recognition_contract_sha256: str
    registry_snapshot_sha256: str
    disposition: str
    schema_id: Optional[str]

    def durable_value(self) -> dict:
        return {
            "disposition": self.disposition,
            "receipt_kind": RECEIPT_KIND,
            "recognition_contract_sha256": self.recognition_contract_sha256,
            "registry_snapshot_sha256": self.registry_snapshot_sha256,
            "schema_id": self.schema_id,
            "source_object_sha256": self.source_object_sha256,
        }

    def durable_bytes(self) -> bytes:
        return _canonical_bytes(self.durable_value())


def _make_receipt(raw_bytes: bytes, g_bytes: bytes, r_bytes: bytes) -> Receipt:
    disp = _full_pipeline(raw_bytes, r_bytes)
    return Receipt(
        source_object_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        recognition_contract_sha256=hashlib.sha256(g_bytes).hexdigest(),
        registry_snapshot_sha256=hashlib.sha256(r_bytes).hexdigest(),
        disposition=disp.kind,
        schema_id=disp.schema_id if disp.kind == RECOGNIZED else None,
    )


def _verify_receipt(receipt: Receipt, raw_bytes: bytes, g_bytes: bytes, r_bytes: bytes) -> Receipt:
    """Identity-only verification: recomputes X/G/R identity and the full
    recognition disposition (including schema_id, as an output assertion,
    never an input) from explicitly supplied bytes. Never resolves G/R
    ambiently -- the caller must supply the exact bytes to check against."""
    if hashlib.sha256(raw_bytes).hexdigest() != receipt.source_object_sha256:
        raise ValueError("supplied raw bytes do not match receipt's source_object_sha256")
    if hashlib.sha256(g_bytes).hexdigest() != receipt.recognition_contract_sha256:
        raise ValueError("supplied G bytes do not match receipt's recognition_contract_sha256")
    if hashlib.sha256(r_bytes).hexdigest() != receipt.registry_snapshot_sha256:
        raise ValueError("supplied R bytes do not match receipt's registry_snapshot_sha256")
    recomputed = _full_pipeline(raw_bytes, r_bytes)
    recomputed_schema_id = recomputed.schema_id if recomputed.kind == RECOGNIZED else None
    if recomputed.kind != receipt.disposition:
        raise ValueError(f"receipt disposition {receipt.disposition!r} != recomputed {recomputed.kind!r}")
    if recomputed_schema_id != receipt.schema_id:
        raise ValueError(f"receipt schema_id {receipt.schema_id!r} != recomputed {recomputed_schema_id!r}")
    return receipt


# --- authority selector simulation (identity vs authority, supersession) ---


@dataclass(frozen=True)
class AuthorityRecord:
    bound_registry_sha256: str
    supersedes: Optional[str] = None  # sha256 of the G this record supersedes, or None


def _is_legitimately_authorized(g_bytes: bytes, r_bytes: bytes, ledger: dict) -> bool:
    """Full authority check: G must be a ledger member AND R must be the
    exact registry bytes that ledger entry names -- never any self-consistent
    but non-designated pair."""
    g_hash = hashlib.sha256(g_bytes).hexdigest()
    r_hash = hashlib.sha256(r_bytes).hexdigest()
    record = ledger.get(g_hash)
    return record is not None and record.bound_registry_sha256 == r_hash


def _resolve_current_authority(ledger: dict) -> str:
    """Returns the sha256 of the unique non-superseded G in the ledger.
    Never uses recency/timestamp/insertion-order/lexicographic ordering --
    purely structural: an entry is current iff no other entry's `supersedes`
    names it."""
    superseded = {rec.supersedes for rec in ledger.values() if rec.supersedes}
    current = sorted(h for h in ledger if h not in superseded)
    if len(current) == 0:
        raise ValueError("AUTHORITY_UNRESOLVED: empty ledger")
    if len(current) > 1:
        raise ValueError("AUTHORITY_AMBIGUOUS: " + ",".join(current))
    return current[0]


def _verify_receipt_with_authority(receipt: Receipt, raw_bytes: bytes, g_bytes: bytes,
                                    r_bytes: bytes, ledger: dict) -> Receipt:
    """Full verification: identity (hash self-consistency) AND authority
    (legitimate designation), never identity alone."""
    if not _is_legitimately_authorized(g_bytes, r_bytes, ledger):
        raise ValueError("G/R pair is internally self-consistent but not a legitimately "
                          "authorized authority")
    return _verify_receipt(receipt, raw_bytes, g_bytes, r_bytes)


# ---------------------------------------------------------------------------
# 2. Candidate self-consistency / governance conventions
# ---------------------------------------------------------------------------


def test_candidate_is_not_yet_frozen():
    candidate = _candidate()
    assert candidate["status"] == "CANDIDATE_NOT_YET_FROZEN"
    assert candidate["self_freeze_authorized"] is False
    assert candidate["artifact_kind"] == "PROTOCOL_AMENDMENT_CANDIDATE"
    assert "freeze_provenance" not in candidate


def test_candidate_semantic_content_digest_is_self_consistent():
    candidate = _candidate()
    recomputed = _canonical_hash(candidate["semantic_body"])
    assert recomputed == candidate["amendment_semantic_content_sha256"]


def test_candidate_effective_binding_digest_is_self_consistent():
    candidate = _candidate()
    binding = candidate["effective_combined_contract_binding"]
    recomputed_semantic = _canonical_hash(candidate["semantic_body"])
    recomputed_binding = _canonical_hash({
        "amendment_semantic_content_sha256": recomputed_semantic,
        "base_contract_artifact": binding["base_contract_artifact"],
        "base_contract_sha256": binding["base_contract_sha256"],
        "base_registry_artifact": binding["base_registry_artifact"],
        "base_registry_sha256": binding["base_registry_sha256"],
    })
    assert recomputed_binding == candidate["effective_combined_contract_binding_sha256"]


def test_candidate_binds_current_bytes_of_base_contract_and_registry():
    candidate = _candidate()
    actual_contract_sha256 = hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()
    actual_registry_sha256 = hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest()
    assert actual_contract_sha256 == candidate["bound_authority"]["base_contract_sha256"]
    assert actual_registry_sha256 == candidate["bound_authority"]["base_registry_sha256"]
    amends = candidate["semantic_body"]["amends"]
    assert actual_contract_sha256 == amends["target_artifact_sha256_at_amendment_time"]
    assert actual_registry_sha256 == amends["target_registry_sha256_at_amendment_time"]
    assert amends["original_contract_bytes_unchanged_by_this_amendment"] is True
    assert amends["original_registry_bytes_unchanged_by_this_amendment"] is True


def test_candidate_does_not_authorize_raw_deletion():
    candidate = _candidate()
    assert candidate["raw_deletion_authorized"] is False


def test_candidate_declares_recognition_non_goals():
    non_goals = " ".join(_candidate()["semantic_body"]["non_goals"])
    for term in ("authorization", "admission", "materialization", "inference",
                  "Parser A, Parser B", "fuzzy"):
        assert term in non_goals, term


def test_candidate_e_g_is_unordered_exact_equality_not_subset_or_ordered():
    basis = _candidate()["semantic_body"]["equivalence_relation"]["adjudication_basis"]
    assert "Not ordered-tuple equality" in basis
    assert "Not subset matching" in basis
    assert "Not superset matching" in basis
    assert "Not fuzzy" in basis


def test_candidate_authority_selector_prohibits_recency():
    prohibited = _candidate()["semantic_body"]["authority_selector"]["prohibited_selectors"]
    joined = " ".join(prohibited).lower()
    for term in ("recency", "version", "mtime", "filename", "git"):
        assert term in joined, term


def test_candidate_receipt_has_no_header_digest():
    fields = _candidate()["semantic_body"]["receipt_and_replay"]["required_fields"]
    assert "observed_header_digest" not in fields
    assert set(fields) == {
        "receipt_kind", "source_object_sha256", "recognition_contract_sha256",
        "registry_snapshot_sha256", "disposition", "schema_id",
    }


# ---------------------------------------------------------------------------
# 3. T0-T13 hostile fixture matrix
# ---------------------------------------------------------------------------


def test_T0_valid_known_object_recognized():
    raw = (CACHE_DIR / REAL_OBJECT_SHA256).read_bytes()
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == RECOGNIZED
    assert disp.schema_id == "bybit_trade_v1"


def test_T1_header_and_row_permutation_together_same_schema():
    """Schema-equivalence question: permuting header AND rows together
    preserves logical content. recognize() consumes only H, never row
    content, so this necessarily yields the identical RECOGNIZED result as
    an unpermuted header -- this is the correct evidence for E_G's
    order-insensitivity, per the corrected Permutation-A/B split."""
    idx = [3, 0, 1, 2, 4, 5, 6, 7, 8, 9]
    permuted_header = ",".join(BASE_HEADER[i] for i in idx)
    permuted_row = tuple(BASE_ROW[i] for i in idx)
    raw = _build_object(permuted_header, [permuted_row])
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == RECOGNIZED
    assert disp.schema_id == "bybit_trade_v1"


def test_T2_header_only_permutation_is_not_an_order_sensitivity_signal():
    """Corruption-only question, per the corrected Permutation-A/B split:
    header reordered, row values left at their original (now mismatched)
    positions. recognize() still only consumes H (identical set of tokens as
    T1), so it still yields RECOGNIZED -- this equality with T1 is expected
    and is NOT evidence that E_G tolerates reordering "because rows still
    parse"; it is evidence that recognition is header-only by construction.
    Whether the resulting mislabeled row data is safe to consume is Parser
    A/B's row-processing concern, explicitly out of scope for this candidate
    (see non_goals)."""
    idx = [3, 0, 1, 2, 4, 5, 6, 7, 8, 9]
    permuted_header = ",".join(BASE_HEADER[i] for i in idx)
    unpermuted_row = BASE_ROW  # rows NOT permuted to match -- deliberately mislabeled
    raw = _build_object(permuted_header, [unpermuted_row])
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == RECOGNIZED
    assert disp.schema_id == "bybit_trade_v1"


def test_T3_duplicate_appended_field_name_is_malformed():
    header = ",".join(BASE_HEADER) + ",timestamp"  # 11 tokens, "timestamp" duplicated
    raw = _build_object(header, [BASE_ROW + ("extra",)])
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == MALFORMED_HEADER
    assert "DUPLICATE_TOKEN_NAME" in disp.reason


def test_T4_missing_field_is_no_match():
    header = ",".join(BASE_HEADER[:-1])  # drop foreignNotional
    raw = _build_object(header, [BASE_ROW[:-1]])
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == NO_MATCH


def test_T5_extra_unknown_field_is_no_match():
    header = ",".join(BASE_HEADER) + ",EXTRA_UNSEEN_COLUMN"
    raw = _build_object(header, [BASE_ROW + ("x",)])
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == NO_MATCH


def test_T6_case_mutation_is_no_match_no_casefold():
    header = "Timestamp," + ",".join(BASE_HEADER[1:])
    raw = _build_object(header, [BASE_ROW])
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == NO_MATCH


def test_T7_whitespace_mutation_is_no_match_no_trim():
    header = " timestamp," + ",".join(BASE_HEADER[1:])
    raw = _build_object(header, [BASE_ROW])
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == NO_MATCH


def test_T8_utf8_bom_is_framing_failure_not_stripped():
    body = "﻿" + ",".join(BASE_HEADER) + "\n" + ",".join(BASE_ROW) + "\n"
    raw = gzip.compress(body.encode("utf-8"))
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == FRAMING_FAILURE
    assert disp.reason == ("BOM_PRESENT",)


def test_T9_crlf_line_ending_is_framing_failure():
    raw = _build_object(",".join(BASE_HEADER), [BASE_ROW], line_ending="\r\n")
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == FRAMING_FAILURE
    assert disp.reason == ("NON_LF_LINE_TERMINATOR",)


def test_T10_quoted_header_token_is_malformed():
    header = '"timestamp",' + ",".join(BASE_HEADER[1:])
    raw = _build_object(header, [BASE_ROW])
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == MALFORMED_HEADER
    assert "QUOTE_CHARACTER_IN_TOKEN" in disp.reason


def test_T11_unterminated_quote_in_header_is_malformed_deterministically():
    """Header quoting is unsupported in v1 (no quote-aware interpretation is
    defined); a literal quote character -- terminated or not -- is fail-
    closed identically and deterministically, never left to whatever a CSV
    library's quote-escaping heuristics happen to do with an unterminated
    quote."""
    header = '"timestamp,' + ",".join(BASE_HEADER[1:])  # opening quote, never closed
    raw = _build_object(header, [BASE_ROW])
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == MALFORMED_HEADER
    assert "QUOTE_CHARACTER_IN_TOKEN" in disp.reason


def test_T12_concatenated_valid_second_gzip_member_is_framing_failure():
    """Must enforce the single-member policy, not Python gzip.decompress()'s
    implicit multi-member acceptance."""
    member1 = _build_object(",".join(BASE_HEADER), [BASE_ROW])
    member2 = gzip.compress(b"second,member\nx,y\n")
    raw = member1 + member2

    # Sanity: confirm this is exactly the hazard being closed -- Python's
    # gzip.decompress() silently concatenates both members by default.
    assert gzip.decompress(raw) == gzip.decompress(member1) + gzip.decompress(member2)

    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == FRAMING_FAILURE
    assert disp.reason == ("MULTI_MEMBER_GZIP",)


def test_T13_trailing_garbage_after_gzip_member_is_framing_failure():
    member1 = _build_object(",".join(BASE_HEADER), [BASE_ROW])
    raw = member1 + b"\x00\x01not-a-gzip-member\xff"
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == FRAMING_FAILURE
    assert disp.reason == ("MULTI_MEMBER_GZIP",)


def test_T14_truncated_real_object_prefixes_are_invalid_gzip_never_recognized():
    """Hostile-review-derived regression (gzip completion semantics):
    zlib.decompressobj can produce decompressed output, without raising,
    from a proper prefix of a valid gzip member. Checking only "did
    decompress() raise?" -- as the pre-repair evaluator did -- lets a
    truncated real object reach NO_MATCH or even RECOGNIZED instead of
    failing closed. Prefixes are generated mechanically from a genuine
    cached R1 object, not hand-built substitute streams, covering
    strategically different truncation points including the previously
    failing 1000-byte case from the hostile review."""
    raw = (CACHE_DIR / REAL_OBJECT_SHA256).read_bytes()
    n = len(raw)
    assert n == 121118, "cached fixture object size changed unexpectedly"

    truncation_points = {
        "very_short_prefix": 10,
        "short_prefix": 50,
        "about_200_bytes": 200,
        "about_1000_bytes": 1000,  # the hostile review's previously-failing case
        "about_half_object": n // 2,
        "trailer_truncated": n - 4,  # inside the 8-byte CRC32+ISIZE trailer
        "all_but_final_byte": n - 1,
    }

    for label, k in truncation_points.items():
        assert 0 < k < n, (label, k)
        prefix = raw[:k]
        disp = _full_pipeline(prefix, REGISTRY_PATH.read_bytes())
        assert disp.kind == FRAMING_FAILURE, (label, k, disp)
        assert disp.reason == ("INVALID_GZIP",), (label, k, disp)


def test_T14_full_object_still_recognized_positive_control():
    """Positive control for T14: the complete, untruncated object (k == n)
    must still reach RECOGNIZED -- proves the completion check rejects only
    genuinely incomplete streams, not the valid object itself."""
    raw = (CACHE_DIR / REAL_OBJECT_SHA256).read_bytes()
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == RECOGNIZED
    assert disp.schema_id == "bybit_trade_v1"


def test_T14_completeness_property_no_proper_prefix_reaches_recognition_layer():
    """Property: for a known-valid gzip X of length N, proper prefixes
    X[:k] for k < N that have not reached a complete member end must never
    produce a recognition-layer disposition (NO_MATCH/RECOGNIZED/AMBIGUOUS/
    MALFORMED_HEADER) -- only FRAMING_FAILURE(INVALID_GZIP). Representative
    hostile boundaries are used rather than an exhaustive byte-by-byte scan,
    which would be needlessly expensive for the same guarantee."""
    raw = (CACHE_DIR / REAL_OBJECT_SHA256).read_bytes()
    n = len(raw)
    registry_bytes = REGISTRY_PATH.read_bytes()
    recognition_layer_dispositions = {NO_MATCH, RECOGNIZED, AMBIGUOUS, MALFORMED_HEADER}

    for k in (1, 2, 10, 50, 200, 1000, n // 4, n // 2, (3 * n) // 4, n - 100, n - 8, n - 4, n - 1):
        assert 0 < k < n
        disp = _full_pipeline(raw[:k], registry_bytes)
        assert disp.kind not in recognition_layer_dispositions, (k, disp)
        assert disp.kind == FRAMING_FAILURE and disp.reason == ("INVALID_GZIP",), (k, disp)


def test_T12_multi_member_still_rejected_alongside_truncation_fix():
    """Regression guard, run together with T14: the gzip-completion repair
    must not weaken the pre-existing single-member policy. Both properties
    hold simultaneously: a complete first member followed by a second member
    is rejected under the existing multi-member policy, while an incomplete
    first member is rejected under the (repaired) completion policy -- these
    are two distinct, independently-triggered framing failures, not a single
    merged check."""
    member1 = _build_object(",".join(BASE_HEADER), [BASE_ROW])
    member2 = gzip.compress(b"second,member\nx,y\n")
    complete_plus_second_member = member1 + member2
    incomplete_first_member = member1[:-1]

    disp_complete_plus_second = _full_pipeline(complete_plus_second_member, REGISTRY_PATH.read_bytes())
    assert disp_complete_plus_second.kind == FRAMING_FAILURE
    assert disp_complete_plus_second.reason == ("MULTI_MEMBER_GZIP",)

    disp_incomplete = _full_pipeline(incomplete_first_member, REGISTRY_PATH.read_bytes())
    assert disp_incomplete.kind == FRAMING_FAILURE
    assert disp_incomplete.reason == ("INVALID_GZIP",)


def test_empty_token_name_is_malformed():
    header = ",".join(BASE_HEADER) + ","  # trailing comma -> empty final token
    raw = _build_object(header, [BASE_ROW + ("",)])
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == MALFORMED_HEADER
    assert "EMPTY_TOKEN_NAME" in disp.reason


def test_invalid_gzip_is_framing_failure():
    disp = _full_pipeline(b"not gzip at all", REGISTRY_PATH.read_bytes())
    assert disp.kind == FRAMING_FAILURE
    assert disp.reason == ("INVALID_GZIP",)


def test_empty_object_is_framing_failure():
    """EMPTY_OBJECT (step 4) applies to a *valid, complete* gzip member whose
    decompressed payload is empty -- not to raw X being empty (that is a
    distinct case, see test_raw_empty_bytes_is_invalid_gzip_not_empty_object
    below). gzip.compress(b"") is a genuine single gzip member that reaches
    a validated end-of-stream (d.eof is True) and decodes to "" -- the
    correct fixture for this disposition."""
    raw = gzip.compress(b"")
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == FRAMING_FAILURE
    assert disp.reason == ("EMPTY_OBJECT",)


def test_raw_empty_bytes_is_invalid_gzip_not_empty_object():
    """Hostile-review-derived regression: X = b"" is not a complete gzip
    member (no 10-byte header is even present), so it must fail the same
    d.eof-based completion check as any other truncated/incomplete member
    and be classified FRAMING_FAILURE(INVALID_GZIP) -- never treated as a
    distinguished pre-gzip EMPTY_OBJECT sentinel, and never reaching any
    recognition-layer disposition."""
    disp = _full_pipeline(b"", REGISTRY_PATH.read_bytes())
    assert disp.kind == FRAMING_FAILURE
    assert disp.reason == ("INVALID_GZIP",)
    assert (disp.kind, disp.reason) != (FRAMING_FAILURE, ("EMPTY_OBJECT",))
    assert disp.kind not in (MALFORMED_HEADER, NO_MATCH, AMBIGUOUS, RECOGNIZED)


def test_invalid_utf8_is_framing_failure():
    raw = gzip.compress(b"\xff\xfe,not,utf8\nrow,row\n")
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == FRAMING_FAILURE
    assert disp.reason == ("INVALID_UTF8",)


def test_fewer_than_two_tokens_is_framing_failure():
    raw = _build_object("onlyone", [("x",)])
    disp = _full_pipeline(raw, REGISTRY_PATH.read_bytes())
    assert disp.kind == FRAMING_FAILURE
    assert disp.reason == ("FEWER_THAN_TWO_TOKENS",)


# ---------------------------------------------------------------------------
# 4. Registry / ambiguity tests
# ---------------------------------------------------------------------------


def test_current_registry_signatures_are_pairwise_unique_under_e_g():
    registry = json.loads(REGISTRY_PATH.read_bytes())
    variants = registry["known_schema_variants"]
    signatures = {name: frozenset(entry["field_set"]) for name, entry in variants.items()}
    names = list(signatures)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            assert signatures[names[i]] != signatures[names[j]], (names[i], names[j])


def _synthetic_registry_bytes(variants: dict) -> bytes:
    return json.dumps({"known_schema_variants": variants}).encode()


def test_synthetic_signature_collision_yields_ambiguous_not_first_match():
    collision_field_set = list(BASE_HEADER)
    variants_order_a = {
        "schema_alpha": {"field_set": collision_field_set},
        "schema_beta": {"field_set": collision_field_set},
    }
    variants_order_b = {
        "schema_beta": {"field_set": collision_field_set},
        "schema_alpha": {"field_set": collision_field_set},
    }
    H = frozenset(BASE_HEADER)
    disp_a = _recognize(H, variants_order_a)
    disp_b = _recognize(H, variants_order_b)
    assert disp_a.kind == AMBIGUOUS
    assert disp_b.kind == AMBIGUOUS
    assert disp_a.reason == disp_b.reason == ("schema_alpha", "schema_beta")


def test_registry_key_ordering_does_not_affect_disposition():
    registry = json.loads(REGISTRY_PATH.read_bytes())
    variants = registry["known_schema_variants"]
    forward = dict(variants)
    reversed_order = dict(reversed(list(variants.items())))
    H = frozenset(BASE_HEADER)
    assert _recognize(H, forward) == _recognize(H, reversed_order)


def test_future_r2_addition_does_not_alter_historical_r1_receipt():
    r1_bytes = REGISTRY_PATH.read_bytes()
    raw = (CACHE_DIR / REAL_OBJECT_SHA256).read_bytes()
    g_bytes = CANDIDATE_PATH.read_bytes()

    receipt = _make_receipt(raw, g_bytes, r1_bytes)
    assert receipt.disposition == RECOGNIZED

    # A future registry R2 adds a new schema; this must never be consulted
    # to reinterpret the already-recorded R1 receipt.
    r2 = json.loads(r1_bytes)
    r2["known_schema_variants"]["future_variant"] = {"field_set": ["future"]}
    r2_bytes = json.dumps(r2).encode()
    assert hashlib.sha256(r2_bytes).hexdigest() != receipt.registry_snapshot_sha256

    # Replay against the exact R1 bytes still verifies.
    assert _verify_receipt(receipt, raw, g_bytes, r1_bytes) == receipt
    # Replay against R2 bytes fails identity (different registry_snapshot_sha256) --
    # never silently substituted for R1.
    with pytest.raises(ValueError, match="registry_snapshot_sha256"):
        _verify_receipt(receipt, raw, g_bytes, r2_bytes)


# ---------------------------------------------------------------------------
# 5. Authority / supersession hostile tests
# ---------------------------------------------------------------------------


def test_A1_A2_supersession_never_reinterprets_historical_evaluation():
    r1_bytes = REGISTRY_PATH.read_bytes()
    g1_bytes = b'{"artifact": "G1", "amends": "base"}'
    raw = (CACHE_DIR / REAL_OBJECT_SHA256).read_bytes()

    g1_hash = hashlib.sha256(g1_bytes).hexdigest()
    r1_hash = hashlib.sha256(r1_bytes).hexdigest()
    ledger = {g1_hash: AuthorityRecord(bound_registry_sha256=r1_hash)}

    # E1 produced and verified under A1 (G1/R1) while G1 is current.
    e1 = _make_receipt(raw, g1_bytes, r1_bytes)
    assert _resolve_current_authority(ledger) == g1_hash
    assert _verify_receipt_with_authority(e1, raw, g1_bytes, r1_bytes, ledger) == e1

    # A2 explicitly supersedes A1 with a new G2/R2.
    g2_bytes = b'{"artifact": "G2", "supersedes": "%s"}' % g1_hash.encode()
    g2_hash = hashlib.sha256(g2_bytes).hexdigest()
    r2 = json.loads(r1_bytes)
    r2["known_schema_variants"]["future_variant"] = {"field_set": ["future"]}
    r2_bytes = json.dumps(r2).encode()
    r2_hash = hashlib.sha256(r2_bytes).hexdigest()
    ledger[g2_hash] = AuthorityRecord(bound_registry_sha256=r2_hash, supersedes=g1_hash)

    # G2 is now current; G1 is no longer current for NEW evaluations.
    assert _resolve_current_authority(ledger) == g2_hash

    # E1 remains fully verifiable under its own historical authority (G1/R1),
    # unaffected by G2's existence -- verification never implicitly resolves
    # "current" authority, it requires explicit historical bytes.
    assert _verify_receipt_with_authority(e1, raw, g1_bytes, r1_bytes, ledger) == e1

    # G2 must never cause E1 to be silently reinterpreted under G2/R2: E1's
    # own claimed identity fields still name G1/R1, so attempting to verify
    # it against G2/R2 fails identity outright.
    with pytest.raises(ValueError, match="recognition_contract_sha256"):
        _verify_receipt_with_authority(e1, raw, g2_bytes, r2_bytes, ledger)


def test_self_consistent_fake_authority_is_rejected():
    """A self-consistent G'/R' pair (internal hashes match each other) that
    was never designated by the legitimate authority ledger must be rejected
    -- identity alone is never sufficient."""
    r1_bytes = REGISTRY_PATH.read_bytes()
    r1_hash = hashlib.sha256(r1_bytes).hexdigest()
    g1_bytes = b'{"artifact": "G1"}'
    g1_hash = hashlib.sha256(g1_bytes).hexdigest()
    ledger = {g1_hash: AuthorityRecord(bound_registry_sha256=r1_hash)}

    raw = (CACHE_DIR / REAL_OBJECT_SHA256).read_bytes()

    fake_g_bytes = b'{"artifact": "definitely-not-authorized-but-self-consistent"}'
    fake_e = _make_receipt(raw, fake_g_bytes, r1_bytes)

    # Identity-only verification (no authority check) trivially "passes" --
    # this is exactly the gap the authority check exists to close.
    assert _verify_receipt(fake_e, raw, fake_g_bytes, r1_bytes) == fake_e

    # Full authority-checked verification must reject it.
    with pytest.raises(ValueError, match="not a legitimately authorized authority"):
        _verify_receipt_with_authority(fake_e, raw, fake_g_bytes, r1_bytes, ledger)


def test_competing_non_superseded_authorities_fail_closed_as_ambiguous():
    r1_bytes = REGISTRY_PATH.read_bytes()
    r1_hash = hashlib.sha256(r1_bytes).hexdigest()
    g_a_bytes = b'{"artifact": "G_alpha"}'
    g_b_bytes = b'{"artifact": "G_beta_lexicographically_and_hash_wise_different"}'
    g_a_hash = hashlib.sha256(g_a_bytes).hexdigest()
    g_b_hash = hashlib.sha256(g_b_bytes).hexdigest()

    # Neither supersedes the other.
    ledger = {
        g_a_hash: AuthorityRecord(bound_registry_sha256=r1_hash),
        g_b_hash: AuthorityRecord(bound_registry_sha256=r1_hash),
    }
    with pytest.raises(ValueError, match="AUTHORITY_AMBIGUOUS"):
        _resolve_current_authority(ledger)

    # Confirm this is not resolved by any prohibited heuristic: neither
    # insertion order nor hash lexicographic order picks a winner -- both
    # orderings raise identically.
    ledger_reversed = {
        g_b_hash: ledger[g_b_hash],
        g_a_hash: ledger[g_a_hash],
    }
    with pytest.raises(ValueError, match="AUTHORITY_AMBIGUOUS"):
        _resolve_current_authority(ledger_reversed)


# ---------------------------------------------------------------------------
# 6. Receipt forgery tests
# ---------------------------------------------------------------------------


def _valid_receipt_and_bytes():
    r_bytes = REGISTRY_PATH.read_bytes()
    g_bytes = CANDIDATE_PATH.read_bytes()
    raw = (CACHE_DIR / REAL_OBJECT_SHA256).read_bytes()
    receipt = _make_receipt(raw, g_bytes, r_bytes)
    assert receipt.disposition == RECOGNIZED
    return receipt, raw, g_bytes, r_bytes


@pytest.mark.parametrize("field_name,replacement", [
    ("source_object_sha256", "0" * 64),
    ("recognition_contract_sha256", "1" * 64),
    ("registry_snapshot_sha256", "2" * 64),
    ("disposition", "AMBIGUOUS"),
    ("schema_id", "bybit_trade_v1_rpi"),
])
def test_forged_receipt_field_fails_verification(field_name, replacement):
    receipt, raw, g_bytes, r_bytes = _valid_receipt_and_bytes()
    forged = Receipt(**{**receipt.__dict__, field_name: replacement})
    with pytest.raises(ValueError):
        _verify_receipt(forged, raw, g_bytes, r_bytes)


def test_receipt_schema_id_is_output_assertion_never_input_authority():
    """Direct proof that receipt.schema_id is checked against independently
    recomputed recognition, never trusted as a caller-supplied input: a
    NO_MATCH object with a forged schema_id and forged RECOGNIZED disposition
    must fail verification even though every hash field is genuine."""
    r_bytes = REGISTRY_PATH.read_bytes()
    g_bytes = CANDIDATE_PATH.read_bytes()
    no_match_header = ",".join(BASE_HEADER) + ",EXTRA_UNSEEN_COLUMN"
    raw = _build_object(no_match_header, [BASE_ROW + ("x",)])

    genuine = _make_receipt(raw, g_bytes, r_bytes)
    assert genuine.disposition == NO_MATCH
    assert genuine.schema_id is None

    forged = Receipt(**{**genuine.__dict__, "disposition": RECOGNIZED, "schema_id": "bybit_trade_v1"})
    with pytest.raises(ValueError, match="disposition"):
        _verify_receipt(forged, raw, g_bytes, r_bytes)


def test_receipt_durable_bytes_round_trip_and_replay_after_object_loss():
    receipt, raw, g_bytes, r_bytes = _valid_receipt_and_bytes()
    durable = receipt.durable_bytes()
    value = json.loads(durable)
    replayed = Receipt(
        source_object_sha256=value["source_object_sha256"],
        recognition_contract_sha256=value["recognition_contract_sha256"],
        registry_snapshot_sha256=value["registry_snapshot_sha256"],
        disposition=value["disposition"],
        schema_id=value["schema_id"],
    )
    del receipt
    assert _verify_receipt(replayed, raw, g_bytes, r_bytes) == replayed
    assert replayed.durable_bytes() == durable
