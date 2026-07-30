"""Protocol tests for experiments/data/r1_normalized_evidence_duplicate_semantics_amendment_v1.json
(a PROTOCOL_AMENDMENT_CANDIDATE, not yet frozen -- see its own "status" field).

This amendment closes exactly two gaps identified by an independent review of
repair commit e466401 (BLOCKED_BY_CANONICAL_TIEBREAK_UNDERSPECIFICATION):
  (a) which textual spelling of a numerically-equal duplicate price/size
      survives collapse ("duplicate representative selection"), and
  (b) that raw row arrival order must not affect canonical
      DailyMarketEvidenceV1 bytes/hash ("row-order non-interference").

These tests do not modify, and do not require modifying, either parser. They:
  1. verify the amendment artifact's self-consistent digests and its binding
     to the actual current bytes of the base contract it amends;
  2. reimplement the amendment's stated representative-selection rule
     standalone (not by importing either parser) and cross-check it against
     Parser B (qntylab.r1_retention_candidate, e466401) to substantiate the
     amendment's CONFORMS claim empirically;
  3. cross-check Parser A (qntylab.r1_reference_parser) to substantiate the
     amendment's NONCONFORMING claim empirically (still order-dependent);
  4. run an adversarial battery (3+ spellings, mixed price+size spelling,
     ordinary rows mixed with a duplicate group, side/tickDirection-only
     variation, genuine numeric conflict, permuted arrival order) against
     the standalone rule and against Parser B;
  5. regression-check the amendment's empirical grammar-scope claim against
     the same bounded 5-object real pilot cache already used elsewhere in
     this suite (no new acquisition; no corpus materialization).
"""
import gzip
import hashlib
import io
import itertools
import json
import re
import subprocess
from datetime import date
from pathlib import Path

from qntylab import r1_reference_parser as rp
from qntylab.r1_input_bom import canonical_hash
from qntylab.r1_retention_candidate import (
    ANOMALY_DUPLICATE_CONFLICTING,
    ANOMALY_DUPLICATE_UNEXPECTED,
    BASE_SCHEMA,
    daily_primitive,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
AMENDMENT_PATH = REPO_ROOT / "experiments/data/r1_normalized_evidence_duplicate_semantics_amendment_v1.json"
BASE_CONTRACT_PATH = REPO_ROOT / "experiments/data/r1_normalized_evidence_contract_v1.json"
CACHE_DIR = REPO_ROOT / ".r1_input_cache/sha256"

REAL_OBJECTS = [
    ("BTCUSDT_2020-03-25", "cbca6933a8f0a11429661cfa93b04056055d776ee199209e8af9719ad2060a33"),
    ("UNIUSDT_2021-11-30", "8068ed2f06c280ad103b50525c4c8bc14a3a956a6ed40f4fba50ff738d59ebb4"),
    ("ANCUSDT_2022-03-15", "cabc599c8d0b2da8df4bb07de64700092701ac8bf4987ee8b4395bef8a6398d2"),
    ("FTTUSDT_2022-11-13", "8c085036c9b65a99379941434f3531fa7365b24e31a752cd10a0d80ea8df77fc"),
    ("1000000CHEEMSUSDT_2026-05-28", "d1b50f8316c1874d7ae7bde11314d077f3cf1b2baece4a6cdd7459e83cc2ce2a"),
]

CUTOFF = "2026-06-30T23:59:59Z"


def _canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def _canonical_hash(value):
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load_amendment():
    return json.loads(AMENDMENT_PATH.read_bytes())


# --- 1. amendment self-consistency and provenance binding -------------------

def test_amendment_is_frozen_with_recorded_operator_authorization():
    """Governance-status expectation updated to reflect the explicit
    protocol-owner freeze authorization recorded in freeze_provenance; the
    reviewed semantic content itself (amendment_semantic_content_sha256) is
    unchanged -- see test_amendment_semantic_content_digest_is_self_consistent
    and test_amendment_base_contract_binding_matches_actual_current_file."""
    amendment = _load_amendment()
    assert amendment["status"] == "FROZEN"
    assert amendment["freeze_authorized_by_this_task"] is True
    assert amendment["freeze_provenance"]["candidate_commit_reviewed_sha"] == "92c1759d7153d37d52edc57d37c4febb5cc3e067"
    assert amendment["freeze_provenance"]["frozen_amendment_semantic_content_sha256"] == amendment["amendment_semantic_content_sha256"]
    assert amendment["freeze_provenance"]["frozen_effective_combined_contract_binding_sha256"] == amendment["effective_combined_contract_binding_sha256"]


def test_amendment_semantic_content_digest_is_self_consistent():
    amendment = _load_amendment()
    recomputed = _canonical_hash(amendment["semantic_body"])
    assert recomputed == amendment["amendment_semantic_content_sha256"]


def test_amendment_effective_combined_binding_digest_is_self_consistent():
    amendment = _load_amendment()
    binding = amendment["effective_combined_contract_binding"]
    recomputed_semantic = _canonical_hash(amendment["semantic_body"])
    recomputed_binding = _canonical_hash({
        "base_contract_artifact": binding["base_contract_artifact"],
        "base_contract_sha256": binding["base_contract_sha256"],
        "amendment_semantic_content_sha256": recomputed_semantic,
    })
    assert recomputed_binding == amendment["effective_combined_contract_binding_sha256"]


def test_amendment_base_contract_binding_matches_actual_current_file():
    """The amendment must be bound to the CURRENT bytes of the contract it
    amends -- if the base contract ever changes without a new amendment
    revision, this must fail rather than silently amend stale text."""
    amendment = _load_amendment()
    actual_sha256 = hashlib.sha256(BASE_CONTRACT_PATH.read_bytes()).hexdigest()
    assert actual_sha256 == amendment["semantic_body"]["amends"]["target_artifact_sha256_at_amendment_time"]
    assert actual_sha256 == amendment["effective_combined_contract_binding"]["base_contract_sha256"]


def test_amendment_freeze_does_not_authorize_raw_deletion():
    """raw_deletion_authorized is a permanent semantic-body invariant, unaffected
    by the governance freeze; freeze_authorized_by_this_task now reflects the
    explicit operator authorization recorded in freeze_provenance (see
    test_amendment_is_frozen_with_recorded_operator_authorization)."""
    amendment = _load_amendment()
    assert amendment["semantic_body"]["raw_deletion_authorized"] is False
    assert amendment["freeze_authorized_by_this_task"] is True


# --- standalone reimplementation of the amendment's stated rule -------------
# Deliberately NOT importing either parser's internal helper: this is an
# independent re-derivation of duplicate_representative_selection_rule from
# the amendment text, used to empirically prove Parser B's conformance and
# Parser A's nonconformance rather than merely asserting them in prose.

def amendment_rule_representative(group_price_size_pairs):
    """group_price_size_pairs: list of (price_str, size_str). Returns the
    lexicographically-smallest (price_str, size_str) pair, per
    duplicate_representative_selection_rule.rule."""
    return min(group_price_size_pairs, key=lambda ps: (ps[0], ps[1]))


def _row(ts, size, price, trdid, side="Buy", tickdir="PlusTick"):
    size_f, price_f = float(size), float(price)
    return {"timestamp": str(ts), "symbol": "MONUSDT", "side": side, "size": size, "price": price,
            "tickDirection": tickdir, "trdMatchID": trdid, "grossValue": str(size_f * price_f * 1e8),
            "homeNotional": str(size_f), "foreignNotional": str(size_f * price_f)}


def _b_primitive(rows, utc_date="2025-07-01"):
    return daily_primitive(stream_id="s", utc_date=utc_date, header=BASE_SCHEMA, rows=rows,
                            historical_cutoff_utc=CUTOFF)


def _a_record(rows, header, day="2025-07-01"):
    text = ",".join(header) + "\n" + "\n".join(",".join(str(x) for x in r.values()) for r in rows) + "\n"
    raw = gzip.compress(text.encode())
    return rp.parse_daily_object(raw, date.fromisoformat(day), "x").record


# --- 2. Parser B conformance, proven against the standalone rule -----------

def test_parser_b_conforms_to_amendment_rule_price_scale():
    a = _row("1751328000.0", size="2", price="1.1", trdid="c" * 32)
    b = _row("1751328000.0", size="2.00", price="1.10", trdid="c" * 32)
    expected_price, expected_size = amendment_rule_representative([("1.1", "2"), ("1.10", "2.00")])
    for perm in itertools.permutations([a, b]):
        core, _ = _b_primitive(list(perm))
        assert core["close"] == expected_price
        assert core["base_volume"] == expected_size


def test_parser_b_conforms_to_amendment_rule_size_scale():
    a = _row("1751328000.0", size="2", price="1.1", trdid="d" * 32)
    b = _row("1751328000.0", size="2.00", price="1.1", trdid="d" * 32)
    expected_price, expected_size = amendment_rule_representative([("1.1", "2"), ("1.1", "2.00")])
    for perm in itertools.permutations([a, b]):
        core, _ = _b_primitive(list(perm))
        assert core["close"] == expected_price
        assert core["base_volume"] == expected_size


def test_parser_b_conforms_to_amendment_rule_three_plus_spellings():
    spellings = ["1.1", "1.10", "1.100", "1.1000"]
    rows = [_row("1751328000.0", size="2", price=p, trdid="e" * 32) for p in spellings]
    expected_price, _ = amendment_rule_representative([(p, "2") for p in spellings])
    hashes = set()
    for perm in itertools.permutations(rows):
        core, _ = _b_primitive(list(perm))
        assert core["close"] == expected_price
        hashes.add(canonical_hash(core))
    assert len(hashes) == 1


def test_parser_b_conforms_amendment_rule_mixed_price_and_size_spelling():
    pairs = [("1.1", "2"), ("1.10", "2.00"), ("1.1", "2.00"), ("1.10", "2")]
    rows = [_row("1751328000.0", size=s, price=p, trdid="f" * 32) for p, s in pairs]
    expected_price, expected_size = amendment_rule_representative(pairs)
    for perm in itertools.permutations(rows):
        core, _ = _b_primitive(list(perm))
        assert core["close"] == expected_price
        assert core["base_volume"] == expected_size


def test_parser_b_conforms_amendment_rule_ordinary_rows_mixed_with_duplicate_group():
    dup_a = _row("1751328000.0", size="2", price="1.1", trdid="g" * 32)
    dup_b = _row("1751328000.0", size="2.00", price="1.10", trdid="g" * 32)
    ordinary = _row("1751328100.0", size="5", price="4.35", trdid="h" * 32)
    trades = [dup_a, dup_b, ordinary]
    hashes = set()
    for perm in itertools.permutations(trades):
        core, _ = _b_primitive(list(perm))
        hashes.add(canonical_hash(core))
    assert len(hashes) == 1


def test_parser_b_conforms_amendment_residual_tie_proof_side_and_tickdirection_irrelevant():
    """residual_tie_proof: rows tied on (price_string, size_string) that
    differ only in side/tickDirection must not affect canonical output."""
    a = _row("1751328000.0", size="2", price="1.1", trdid="i" * 32, side="Buy", tickdir="PlusTick")
    b = _row("1751328000.0", size="2", price="1.1", trdid="i" * 32, side="Sell", tickdir="ZeroMinusTick")
    core_ab, _ = _b_primitive([a, b])
    core_ba, _ = _b_primitive([b, a])
    assert core_ab == core_ba


def test_parser_b_conforms_amendment_rule_genuine_conflict_unaffected():
    """conflict_semantics_unchanged: a genuine numeric conflict must never
    have the representative-selection rule pick a winner."""
    a = _row("1751328000.0", size="2", price="1.1", trdid="j" * 32)
    b = _row("1751328000.0", size="2", price="1.2", trdid="j" * 32)
    for perm in itertools.permutations([a, b]):
        core, anom = _b_primitive(list(perm))
        assert core["trade_count"] == 0
        assert ANOMALY_DUPLICATE_CONFLICTING in anom


def test_parser_b_conforms_amendment_rule_row_order_non_interference_hash():
    a = _row("1751328000.0", size="2", price="1.1", trdid="k" * 32)
    b = _row("1751328000.0", size="2.00", price="1.10", trdid="k" * 32)
    core_ab, _ = _b_primitive([a, b])
    core_ba, _ = _b_primitive([b, a])
    assert canonical_hash(core_ab) == canonical_hash(core_ba)


# --- 3. Parser A: formerly nonconforming, since repaired -------------------
# Parser A's group[0]-before-sort nonconformance, documented here at
# amendment-freeze time (parser_status.parser_a.conformance = NONCONFORMING),
# was repaired in a separate, subsequent, authorized task per
# parser_status.parser_a.disposition's own required-next-step -- see
# tests/test_r1_reference_parser_duplicate_semantics_repair_v1.py for the
# full repair regression/conformance suite. These two tests are updated to
# reflect that repair (governance/status expectations only; the frozen
# amendment's semantic_body, recording the pre-repair historical state, is
# untouched -- see test_amendment_semantic_content_digest_is_self_consistent).

def test_parser_a_formerly_nonconforming_now_order_independent_for_mixed_scale_duplicate():
    """Previously (at freeze time) proved rec_fwd != rec_rev, documenting
    NONCONFORMING. Parser A has since been repaired to implement
    duplicate_representative_selection_rule independently, so this now
    proves the opposite: order-independence and agreement with the
    standalone amendment-rule oracle, in both raw orders."""
    header = ("timestamp", "symbol", "side", "size", "price", "tickDirection",
              "trdMatchID", "grossValue", "homeNotional", "foreignNotional")
    a = _row("1751328000.0", size="2", price="1.1", trdid="l" * 32)
    b = _row("1751328000.0", size="2.00", price="1.10", trdid="l" * 32)
    rec_fwd = _a_record([a, b], header)
    rec_rev = _a_record([b, a], header)
    expected_price, expected_size = amendment_rule_representative([("1.1", "2"), ("1.10", "2.00")])

    # source_object_sha256 is a fingerprint of the literal raw archive bytes
    # (different forward vs. reversed CSV text by construction) and is
    # excluded from the row-order-invariance comparison for the same reason
    # test_r1_reference_parser.py::test_deterministic_regardless_of_row_order
    # excludes it -- it is not a row-content derivation.
    rec_fwd_content = {k: v for k, v in rec_fwd.items() if k != "source_object_sha256"}
    rec_rev_content = {k: v for k, v in rec_rev.items() if k != "source_object_sha256"}
    assert rec_fwd_content == rec_rev_content, "Parser A must now be order-independent (repaired)"
    assert rec_fwd["close"] == rec_rev["close"] == expected_price
    assert rec_fwd["base_volume"] == rec_rev["base_volume"] == expected_size


def test_parser_a_sha_recorded_at_amendment_freeze_time_is_historically_accurate():
    """No longer asserts Parser A is byte-identical *today* -- Parser A has
    since been legitimately repaired. Instead verifies the amendment's
    recorded snapshot (parser_status.parser_a.current_sha256) was accurate
    *at governance-freeze commit 2da988c7cfa6defe90991f823e988d97fc0952d1*,
    which remains true and immutable regardless of later repair."""
    amendment = _load_amendment()
    result = subprocess.run(
        ["git", "show", "2da988c7cfa6defe90991f823e988d97fc0952d1:qntylab/r1_reference_parser.py"],
        cwd=REPO_ROOT, capture_output=True, check=True,
    )
    historical_sha = hashlib.sha256(result.stdout).hexdigest()
    assert historical_sha == amendment["semantic_body"]["parser_status"]["parser_a"]["current_sha256"]


def test_parser_b_unmodified_by_this_amendment_sha256():
    import qntylab.r1_retention_candidate as rc
    amendment = _load_amendment()
    actual = hashlib.sha256(Path(rc.__file__).read_bytes()).hexdigest()
    assert actual == amendment["semantic_body"]["parser_status"]["parser_b_e466401"]["current_sha256"]


# --- 4. adversarial battery: one logical input -> one canonical output -----

def test_adversarial_three_plus_spellings_price_and_size_independently():
    price_spellings = ["1.1", "1.10", "1.100", "1.1000"]
    size_spellings = ["2", "2.0", "2.00", "2.000"]
    rows = [_row("1751328000.0", size=s, price=p, trdid="m" * 32)
            for p, s in zip(price_spellings, size_spellings)]
    hashes = set()
    for perm in itertools.permutations(rows):
        core, _ = _b_primitive(list(perm))
        hashes.add(canonical_hash(core))
    assert len(hashes) == 1


def test_adversarial_five_row_group_mixed_spelling_and_noise():
    group = [
        _row("1751328000.0", size="2.000", price="1.10", trdid="n" * 32, side="Buy", tickdir="PlusTick"),
        _row("1751328000.0", size="2.00", price="1.1000", trdid="n" * 32, side="Sell", tickdir="MinusTick"),
        _row("1751328000.0", size="2.0", price="1.1", trdid="n" * 32, side="Buy", tickdir="ZeroPlusTick"),
        _row("1751328000.0", size="2", price="1.10000", trdid="n" * 32, side="Sell", tickdir="ZeroMinusTick"),
        _row("1751328000.0", size="2.00000", price="1.100", trdid="n" * 32, side="Buy", tickdir="PlusTick"),
    ]
    hashes = set()
    for perm in itertools.permutations(group):
        core, _ = _b_primitive(list(perm))
        hashes.add(canonical_hash(core))
    assert len(hashes) == 1


def test_adversarial_permuted_arrival_same_timestamp_same_trade_id_no_duplicates():
    """Row-order non-interference must also hold trivially when there is no
    duplicate group at all (ordinary distinct trades reordered)."""
    rows = [
        _row("1751328000.0", size="1", price="10", trdid="o" * 32),
        _row("1751328100.0", size="2", price="20", trdid="p" * 32),
        _row("1751328200.0", size="3", price="30", trdid="q" * 32),
    ]
    hashes = set()
    for perm in itertools.permutations(rows):
        core, _ = _b_primitive(list(perm))
        hashes.add(canonical_hash(core))
    assert len(hashes) == 1


# --- 5. grammar-scope regression against the existing bounded real cache --

def test_grammar_scope_claim_holds_on_currently_cached_real_objects():
    """Regression check for duplicate_representative_selection_rule.grammar_scope:
    every price/size token in the currently cached 5-object real pilot must
    match the plain fixed-point decimal grammar the amendment's well-
    definedness claim is scoped to. Reads only the same bounded cache other
    tests in this suite already depend on; performs no new acquisition."""
    plain_decimal = re.compile(r"^[0-9]+(\.[0-9]+)?$")
    offenders = []
    for name, sha in REAL_OBJECTS:
        path = CACHE_DIR / sha
        if not path.exists():
            continue
        text = gzip.decompress(path.read_bytes()).decode("utf-8")
        reader = __import__("csv").DictReader(io.StringIO(text))
        for row in reader:
            for field in ("price", "size"):
                token = row.get(field)
                if token is not None and not plain_decimal.match(token):
                    offenders.append((name, field, token))
    assert offenders == [], f"tokens outside the amendment's declared grammar scope: {offenders[:5]}"
