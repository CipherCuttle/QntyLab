"""Regression / conformance tests for the Parser A (`qntylab.r1_reference_parser`)
duplicate-representative-selection repair.

Context: experiments/data/r1_normalized_evidence_duplicate_semantics_amendment_v1.json
is FROZEN (governance commit 2da988c7cfa6defe90991f823e988d97fc0952d1). Its own
parser_status.parser_a recorded Parser A as NONCONFORMING:

  qntylab/r1_reference_parser.py:299 used `canonical.append(group[0])` for an
  already-classified equivalent (non-conflicting) duplicate group -- selecting
  whichever row the raw source happened to list first, a function of raw
  arrival order rather than of the group's own content.

Repair: `canonical.append(group[0])` is replaced with
`canonical.append(_canonical_duplicate_representative(group))`, a new,
independently-implemented helper that selects the group member whose
(price_source_string, size_source_string) pair is lexicographically smallest
-- matching duplicate_representative_selection_rule.rule verbatim, but
computed over Parser A's own `(ts, trade_id, price, size)` tuple layout
without importing or calling Parser B's `_canonical_duplicate_representative`
in qntylab/r1_retention_candidate.py (see
test_r1_reference_parser.py::test_reference_parser_does_not_import_production_semantic_parser,
which this repair does not touch and which continues to pass).

This file does not modify Parser B and does not import Parser B's
representative-selection helper: the `frozen_rule_representative` oracle
below is a fresh reimplementation of the frozen rule text used only to check
both parsers against a common independent reference, not to define either
parser's behavior.
"""
import gzip
import hashlib
import itertools
import json
import subprocess
from datetime import date
from pathlib import Path

from qntylab import r1_reference_parser as rp
from qntylab.r1_retention_candidate import (
    ANOMALY_DUPLICATE_CONFLICTING,
    BASE_SCHEMA,
    daily_primitive,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / ".r1_input_cache/sha256"
CUTOFF = "2026-06-30T23:59:59Z"

# Frozen artifacts this repair must not touch (independently re-verified here,
# not merely asserted in prose).
EXPECTED_BASE_CONTRACT_SHA256 = "c199b9481285d80b34183b8a7681f75ef7e60e5aadad6e4e0ece3ef8f33d6c92"
EXPECTED_AMENDMENT_SEMANTIC_SHA256 = "aa732948b19957a2e3fb7cd2ae1905a3b94a902a0200e24e25874f036894adf9"
EXPECTED_EFFECTIVE_COMBINED_BINDING_SHA256 = "0d0dc12c16535f4ecb06ccfd9b87543862caf7d261cbe8a459d152dee4f493ab"
EXPECTED_PARSER_B_SHA256 = "cfa829c7e28a658258cf31d768c7685c5a6e0cad0c04c75a1fb3faaba0e685c6"

REAL_OBJECTS = [
    ("BTCUSDT_2020-03-25", "cbca6933a8f0a11429661cfa93b04056055d776ee199209e8af9719ad2060a33", date(2020, 3, 25)),
    ("UNIUSDT_2021-11-30", "8068ed2f06c280ad103b50525c4c8bc14a3a956a6ed40f4fba50ff738d59ebb4", date(2021, 11, 30)),
    ("ANCUSDT_2022-03-15", "cabc599c8d0b2da8df4bb07de64700092701ac8bf4987ee8b4395bef8a6398d2", date(2022, 3, 15)),
    ("FTTUSDT_2022-11-13", "8c085036c9b65a99379941434f3531fa7365b24e31a752cd10a0d80ea8df77fc", date(2022, 11, 13)),
    ("1000000CHEEMSUSDT_2026-05-28", "d1b50f8316c1874d7ae7bde11314d077f3cf1b2baece4a6cdd7459e83cc2ce2a", date(2026, 5, 28)),
]

HEADER = ("timestamp", "symbol", "side", "size", "price", "tickDirection",
          "trdMatchID", "grossValue", "homeNotional", "foreignNotional")

# Fields both parsers derive from row content in a directly comparable form.
# Excludes instrument_instance_id/stream_id (identity-key naming differs by
# parser input contract) and source_object_sha256 (Parser A only; it is a
# fingerprint of the literal raw archive bytes, not a row-content derivation
# -- see the pre-existing test_deterministic_regardless_of_row_order in
# test_r1_reference_parser.py, which excludes it for the same reason).
CORE_FIELDS = (
    "schema_id", "trade_count", "duplicate_count", "rejected_row_count",
    "open", "high", "low", "close", "base_volume", "quote_turnover",
    "first_source_timestamp_utc", "last_source_timestamp_utc",
    "first_source_trade_id", "last_source_trade_id",
)

# Fields safe to compare *across* Parser A and Parser B. Excludes
# first_source_timestamp_utc/last_source_timestamp_utc: Parser A renders
# these as ISO-8601 strings (_epoch_to_iso) while Parser B keeps the raw
# epoch float -- a pre-existing, unrelated representational difference
# between the two independent implementations (already absent from
# tests/test_r1_parser_a_vs_b_cross_validation.py's field-by-field
# comparison), not something this duplicate-semantics repair touches or is
# required to reconcile.
AB_SHARED_FIELDS = tuple(f for f in CORE_FIELDS if f not in
                         ("first_source_timestamp_utc", "last_source_timestamp_utc"))


def _project(record: dict) -> dict:
    return {k: record[k] for k in CORE_FIELDS}


def _project_ab(record: dict) -> dict:
    return {k: record[k] for k in AB_SHARED_FIELDS}


def _canonical_hash(value) -> str:
    return hashlib.sha256(
        (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()
    ).hexdigest()


def frozen_rule_representative(candidates):
    """Independent reimplementation of
    duplicate_representative_selection_rule.rule: candidates is a list of
    (price_str, size_str); returns the lexicographically smallest pair.
    Not imported from either parser."""
    return min(candidates, key=lambda ps: (ps[0], ps[1]))


def _row(ts, size, price, trdid, side="Buy", tickdir="PlusTick"):
    size_f, price_f = float(size), float(price)
    return {"timestamp": str(ts), "symbol": "MONUSDT", "side": side, "size": size, "price": price,
            "tickDirection": tickdir, "trdMatchID": trdid, "grossValue": str(size_f * price_f * 1e8),
            "homeNotional": str(size_f), "foreignNotional": str(size_f * price_f)}


def _a_record(rows, day="2025-07-01"):
    text = ",".join(HEADER) + "\n" + "\n".join(",".join(str(row[h]) for h in HEADER) for row in rows) + "\n"
    raw = gzip.compress(text.encode())
    return rp.parse_daily_object(raw, date.fromisoformat(day), "x").record


def _b_primitive(rows, utc_date="2025-07-01"):
    return daily_primitive(stream_id="s", utc_date=utc_date, header=BASE_SCHEMA, rows=rows,
                            historical_cutoff_utc=CUTOFF)


# --- 0. frozen protocol / Parser B immutability (re-verified, not assumed) --

def test_frozen_protocol_hashes_unchanged():
    base_sha = hashlib.sha256(
        (REPO_ROOT / "experiments/data/r1_normalized_evidence_contract_v1.json").read_bytes()
    ).hexdigest()
    assert base_sha == EXPECTED_BASE_CONTRACT_SHA256

    amendment = json.loads(
        (REPO_ROOT / "experiments/data/r1_normalized_evidence_duplicate_semantics_amendment_v1.json").read_bytes()
    )
    sem_sha = _canonical_hash(amendment["semantic_body"])
    assert sem_sha == EXPECTED_AMENDMENT_SEMANTIC_SHA256
    binding = amendment["effective_combined_contract_binding"]
    combined_sha = _canonical_hash({
        "base_contract_artifact": binding["base_contract_artifact"],
        "base_contract_sha256": binding["base_contract_sha256"],
        "amendment_semantic_content_sha256": sem_sha,
    })
    assert combined_sha == EXPECTED_EFFECTIVE_COMBINED_BINDING_SHA256
    assert amendment["status"] == "FROZEN"


def test_parser_b_sha_recorded_at_this_repair_commit_is_historically_accurate():
    """No longer asserts Parser B is byte-identical *today* -- Parser B has
    since been legitimately repaired by the subsequent, separately-reviewed
    timestamp-canonicalization repair (see
    tests/test_r1_timestamp_canonicalization_repair_v1.py), which this
    duplicate-semantics repair's own scope never touched. Instead verifies
    Parser B's hash *at commit e56b201* (this repair's own commit, at which
    Parser B was untouched) matches the historically recorded snapshot,
    which remains true and immutable regardless of the later, unrelated
    timestamp repair."""
    result = subprocess.run(
        ["git", "show", "e56b201:qntylab/r1_retention_candidate.py"],
        cwd=REPO_ROOT, capture_output=True, check=True,
    )
    historical_sha = hashlib.sha256(result.stdout).hexdigest()
    assert historical_sha == EXPECTED_PARSER_B_SHA256


# --- 1. CX reproduction (documents the pre-repair defect, now fixed) --------

def test_cx_reproduction_price_scale_now_row_order_invariant():
    """Pre-repair, forward/reversed raw order for {price='1.1'} vs
    {price='1.10'} (same trdMatchID/timestamp/size) produced different
    canonical `close`/`base_volume` and different canonical hash, because
    `canonical.append(group[0])` picked whichever row appeared first. Fixed
    by _canonical_duplicate_representative."""
    a = _row("1751328000.0", size="2", price="1.1", trdid="c" * 32)
    b = _row("1751328000.0", size="2.00", price="1.10", trdid="c" * 32)
    rec_fwd = _a_record([a, b])
    rec_rev = _a_record([b, a])
    assert rec_fwd["close"] == rec_rev["close"] == "1.1"
    assert rec_fwd["base_volume"] == rec_rev["base_volume"] == "2"
    assert _project(rec_fwd) == _project(rec_rev)


def test_cx_reproduction_size_scale_now_row_order_invariant():
    a = _row("1751328000.0", size="2", price="1.1", trdid="d" * 32)
    b = _row("1751328000.0", size="2.00", price="1.1", trdid="d" * 32)
    rec_fwd = _a_record([a, b])
    rec_rev = _a_record([b, a])
    assert rec_fwd["base_volume"] == rec_rev["base_volume"] == "2"
    assert _project(rec_fwd) == _project(rec_rev)


def test_cx_reproduction_combined_scale_now_row_order_invariant():
    a = _row("1751328000.0", size="2", price="1.1", trdid="e" * 32)
    b = _row("1751328000.0", size="2.00", price="1.10", trdid="e" * 32)
    rec_fwd = _a_record([a, b])
    rec_rev = _a_record([b, a])
    assert rec_fwd["close"] == rec_rev["close"] == "1.1"
    assert rec_fwd["base_volume"] == rec_rev["base_volume"] == "2"
    assert _project(rec_fwd) == _project(rec_rev)
    assert _canonical_hash(_project(rec_fwd)) == _canonical_hash(_project(rec_rev))


# --- 2. classification-before-tiebreak: 3+ spellings, mixed price+size -----

def test_three_plus_equivalent_spellings_single_representative():
    spellings = ["1.1", "1.10", "1.100", "1.1000"]
    rows = [_row("1751328000.0", size="2", price=p, trdid="f" * 32) for p in spellings]
    expected_price, _ = frozen_rule_representative([(p, "2") for p in spellings])
    hashes = set()
    for perm in itertools.permutations(rows):
        rec = _a_record(list(perm))
        assert rec["close"] == expected_price
        hashes.add(_canonical_hash(_project(rec)))
    assert len(hashes) == 1


def test_mixed_price_and_size_spelling_single_representative():
    pairs = [("1.1", "2"), ("1.10", "2.00"), ("1.1", "2.00"), ("1.10", "2")]
    rows = [_row("1751328000.0", size=s, price=p, trdid="g" * 32) for p, s in pairs]
    expected_price, expected_size = frozen_rule_representative(pairs)
    for perm in itertools.permutations(rows):
        rec = _a_record(list(perm))
        assert rec["close"] == expected_price
        assert rec["base_volume"] == expected_size


def test_ordinary_rows_mixed_with_duplicate_group_single_hash():
    dup_a = _row("1751328000.0", size="2", price="1.1", trdid="h" * 32)
    dup_b = _row("1751328000.0", size="2.00", price="1.10", trdid="h" * 32)
    ordinary = _row("1751328100.0", size="5", price="4.35", trdid="i" * 32)
    trades = [dup_a, dup_b, ordinary]
    hashes = set()
    for perm in itertools.permutations(trades):
        rec = _a_record(list(perm))
        hashes.add(_canonical_hash(_project(rec)))
    assert len(hashes) == 1


def test_never_synthesizes_an_absent_spelling():
    """1.1 / 1.10 / 1.100 present -> representative must be one of those
    three, never a synthesized '1.1000'."""
    spellings = ["1.1", "1.10", "1.100"]
    rows = [_row("1751328000.0", size="2", price=p, trdid="j" * 32) for p in spellings]
    rec = _a_record(rows)
    assert rec["close"] in spellings


# --- 3. genuine numeric conflict remains fail-closed ------------------------

def test_genuine_price_conflict_fails_closed_both_orders_agree_with_b():
    a = _row("1751328000.0", size="2", price="1.1", trdid="k" * 32)
    b = _row("1751328000.0", size="2", price="1.2", trdid="k" * 32)
    for perm in itertools.permutations([a, b]):
        rec = _a_record(list(perm))
        assert rec["trade_count"] == 0
        core, anom = _b_primitive(list(perm))
        assert core["trade_count"] == 0
        assert ANOMALY_DUPLICATE_CONFLICTING in anom


def test_genuine_size_conflict_fails_closed_both_orders_agree_with_b():
    a = _row("1751328000.0", size="2", price="1.1", trdid="l" * 32)
    b = _row("1751328000.0", size="3", price="1.1", trdid="l" * 32)
    for perm in itertools.permutations([a, b]):
        rec = _a_record(list(perm))
        assert rec["trade_count"] == 0
        core, anom = _b_primitive(list(perm))
        assert core["trade_count"] == 0
        assert ANOMALY_DUPLICATE_CONFLICTING in anom


# --- 4. exact-duplicate / discarded-field regressions unchanged ------------

def test_exact_textual_duplicate_unchanged_by_this_repair():
    a = _row("1751328000.0", size="2", price="1.1", trdid="m" * 32)
    b = _row("1751328000.0", size="2", price="1.1", trdid="m" * 32)
    rec = _a_record([a, b])
    assert rec["trade_count"] == 1
    assert rec["duplicate_count"] == 1
    assert rec["close"] == "1.1"


def test_side_and_tickdirection_only_variation_irrelevant():
    a = _row("1751328000.0", size="2", price="1.1", trdid="n" * 32, side="Buy", tickdir="PlusTick")
    b = _row("1751328000.0", size="2", price="1.1", trdid="n" * 32, side="Sell", tickdir="ZeroMinusTick")
    rec_ab = _a_record([a, b])
    rec_ba = _a_record([b, a])
    assert _project(rec_ab) == _project(rec_ba)


# --- 5. event-time semantics unchanged (raw order != event order) ----------

def test_event_time_ordering_unaffected_by_representative_selection():
    """Raw listing order differs from event-timestamp order; open/close and
    first/last trade id must still follow parsed event time, not raw
    position, and must be unaffected by the duplicate-representative fix."""
    later = _row("1751328100.0", size="1", price="103", trdid="o" * 32)
    earlier = _row("1751328000.0", size="1", price="100", trdid="p" * 32)
    middle = _row("1751328050.0", size="1", price="101", trdid="q" * 32)
    rec = _a_record([later, earlier, middle])  # raw order deliberately not event order
    assert rec["open"] == "100"
    assert rec["close"] == "103"
    assert rec["first_source_trade_id"] == "p" * 32
    assert rec["last_source_trade_id"] == "o" * 32


def test_event_time_ordering_unaffected_with_a_duplicate_group_present():
    dup_a = _row("1751328000.0", size="2", price="1.1", trdid="r" * 32)
    dup_b = _row("1751328000.0", size="2.00", price="1.10", trdid="r" * 32)
    later = _row("1751328100.0", size="5", price="4.35", trdid="s" * 32)
    rec = _a_record([later, dup_b, dup_a])
    assert rec["open"] == "1.1"
    assert rec["close"] == "4.35"
    assert rec["first_source_trade_id"] == "r" * 32
    assert rec["last_source_trade_id"] == "s" * 32


# --- 6. A/B agreement on the amended (blocking) duplicate class ------------

def test_a_b_agree_price_scale_duplicate():
    a = _row("1751328000.0", size="2", price="1.1", trdid="t" * 32)
    b = _row("1751328000.0", size="2.00", price="1.10", trdid="t" * 32)
    for perm in itertools.permutations([a, b]):
        rec = _a_record(list(perm))
        core, _ = _b_primitive(list(perm))
        assert _canonical_hash(_project_ab(rec)) == _canonical_hash(_project_ab(core))


def test_a_b_agree_size_scale_duplicate():
    a = _row("1751328000.0", size="2", price="1.1", trdid="u" * 32)
    b = _row("1751328000.0", size="2.00", price="1.1", trdid="u" * 32)
    for perm in itertools.permutations([a, b]):
        rec = _a_record(list(perm))
        core, _ = _b_primitive(list(perm))
        assert _canonical_hash(_project_ab(rec)) == _canonical_hash(_project_ab(core))


def test_a_b_agree_combined_scale_duplicate():
    a = _row("1751328000.0", size="2", price="1.1", trdid="v" * 32)
    b = _row("1751328000.0", size="2.00", price="1.10", trdid="v" * 32)
    for perm in itertools.permutations([a, b]):
        rec = _a_record(list(perm))
        core, _ = _b_primitive(list(perm))
        assert _canonical_hash(_project_ab(rec)) == _canonical_hash(_project_ab(core))


def test_a_b_agree_three_plus_spellings():
    spellings = ["1.1", "1.10", "1.100", "1.1000"]
    rows = [_row("1751328000.0", size="2", price=p, trdid="w" * 32) for p in spellings]
    for perm in itertools.permutations(rows):
        rec = _a_record(list(perm))
        core, _ = _b_primitive(list(perm))
        assert _canonical_hash(_project_ab(rec)) == _canonical_hash(_project_ab(core))


def test_a_b_agree_discarded_field_variation():
    a = _row("1751328000.0", size="2", price="1.1", trdid="x" * 32, side="Buy", tickdir="PlusTick")
    b = _row("1751328000.0", size="2", price="1.1", trdid="x" * 32, side="Sell", tickdir="ZeroMinusTick")
    for perm in itertools.permutations([a, b]):
        rec = _a_record(list(perm))
        core, _ = _b_primitive(list(perm))
        assert _canonical_hash(_project_ab(rec)) == _canonical_hash(_project_ab(core))


def test_a_b_agree_duplicate_group_plus_ordinary_rows():
    dup_a = _row("1751328000.0", size="2", price="1.1", trdid="y" * 32)
    dup_b = _row("1751328000.0", size="2.00", price="1.10", trdid="y" * 32)
    ordinary = _row("1751328100.0", size="5", price="4.35", trdid="z" * 32)
    for perm in itertools.permutations([dup_a, dup_b, ordinary]):
        rec = _a_record(list(perm))
        core, _ = _b_primitive(list(perm))
        assert _canonical_hash(_project_ab(rec)) == _canonical_hash(_project_ab(core))


# --- 7. bounded property test: independent oracle + A == B ------------------

def test_property_bounded_permutations_independent_oracle_and_a_equals_b():
    price_spellings = ["1.1", "1.10", "1.100", "1.1000"]
    size_spellings = ["2", "2.0", "2.00", "2.000"]
    rows = [_row("1751328000.0", size=s, price=p, trdid="aa" * 16)
            for p, s in zip(price_spellings, size_spellings)]
    expected_price, expected_size = frozen_rule_representative(list(zip(price_spellings, size_spellings)))
    a_hashes, b_hashes = set(), set()
    for perm in itertools.permutations(rows):
        rec = _a_record(list(perm))
        core, _ = _b_primitive(list(perm))
        assert rec["close"] == core["close"] == expected_price
        assert rec["base_volume"] == core["base_volume"] == expected_size
        a_hashes.add(_canonical_hash(_project_ab(rec)))
        b_hashes.add(_canonical_hash(_project_ab(core)))
    assert len(a_hashes) == 1
    assert len(b_hashes) == 1
    assert a_hashes == b_hashes


# --- 8. real-corpus (5 cached objects) A/B agreement preserved -------------

def test_real_corpus_five_objects_a_b_agreement_preserved():
    import csv
    import io

    checked = 0
    for name, sha, day in REAL_OBJECTS:
        path = CACHE_DIR / sha
        if not path.exists():
            continue
        raw = path.read_bytes()
        a = rp.parse_daily_object(raw, day, f"x|{name}")
        text = gzip.decompress(raw).decode("utf-8")
        header = tuple(next(csv.reader(io.StringIO(text))))
        b_rows = list(csv.DictReader(io.StringIO(text)))
        b_core, b_anom = daily_primitive(
            stream_id=name, utc_date=day.isoformat(), header=header, rows=b_rows,
            historical_cutoff_utc=CUTOFF,
        )
        assert b_anom == [], f"{name}: unexpected Parser B anomalies {b_anom}"
        assert _project_ab(a.record) == _project_ab(b_core), name
        checked += 1
    assert checked == 5, "expected all 5 cached real pilot objects to be present"
