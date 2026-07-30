"""Regression / conformance tests for the DailyMarketEvidenceV1 timestamp
canonicalization repair (first_source_timestamp_utc / last_source_timestamp_utc).

Context: an independent NEW CHAT review of Parser A candidate commit e56b201
(verdict BLOCKED_BY_CANONICAL_FIELD_SCOPE) established that these two fields
are typed by the frozen contract
(experiments/data/r1_normalized_evidence_contract_v1.json:DailyMarketEvidenceV1)
as "timestamp (ISO 8601, millisecond or finer)", required: true -- and that:

  - Parser B (qntylab.r1_retention_candidate.daily_primitive) returned a bare
    Python float (the raw epoch value), not an ISO-8601 string at all. This
    was already logged as open, unresolved debt in an earlier repair receipt
    (experiments/data/r1_parser_b_numeric_conformance_repair_v1.json:
    known_out_of_scope_findings_still_open), not a sanctioned permitted
    provenance difference.
  - Parser A (qntylab.r1_reference_parser._epoch_to_iso) emitted ISO-8601
    strings but did not zero-pad the fractional-second component to a
    millisecond minimum: a whole-second source timestamp (no explicit
    fractional digits, e.g. token "1647328776") produced only one fractional
    digit ("...:36.0Z") instead of "...:36.000Z". Reproduced live on the real
    cached ANCUSDT_2022-03-15 and FTTUSDT_2022-11-13 objects.

This repair touches ONLY canonical timestamp-string formatting for these two
fields in each parser. It does not touch duplicate semantics, numeric OHLC
aggregation, event ordering/selection, or identity.
"""
import csv
import gzip
import hashlib
import io
import itertools
import json
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

EXPECTED_BASE_CONTRACT_SHA256 = "c199b9481285d80b34183b8a7681f75ef7e60e5aadad6e4e0ece3ef8f33d6c92"
EXPECTED_AMENDMENT_SEMANTIC_SHA256 = "aa732948b19957a2e3fb7cd2ae1905a3b94a902a0200e24e25874f036894adf9"
EXPECTED_EFFECTIVE_COMBINED_BINDING_SHA256 = "0d0dc12c16535f4ecb06ccfd9b87543862caf7d261cbe8a459d152dee4f493ab"
PRE_REPAIR_PARSER_A_SHA256 = "0d019ec2ba7969bfe6f07d6e3da0ea302968ae4a0969a4661b852bb59baba07d"
PRE_REPAIR_PARSER_B_SHA256 = "cfa829c7e28a658258cf31d768c7685c5a6e0cad0c04c75a1fb3faaba0e685c6"

HEADER = ("timestamp", "symbol", "side", "size", "price", "tickDirection",
          "trdMatchID", "grossValue", "homeNotional", "foreignNotional")

REAL_OBJECTS = [
    ("BTCUSDT_2020-03-25", "cbca6933a8f0a11429661cfa93b04056055d776ee199209e8af9719ad2060a33", date(2020, 3, 25)),
    ("UNIUSDT_2021-11-30", "8068ed2f06c280ad103b50525c4c8bc14a3a956a6ed40f4fba50ff738d59ebb4", date(2021, 11, 30)),
    ("ANCUSDT_2022-03-15", "cabc599c8d0b2da8df4bb07de64700092701ac8bf4987ee8b4395bef8a6398d2", date(2022, 3, 15)),
    ("FTTUSDT_2022-11-13", "8c085036c9b65a99379941434f3531fa7365b24e31a752cd10a0d80ea8df77fc", date(2022, 11, 13)),
    ("1000000CHEEMSUSDT_2026-05-28", "d1b50f8316c1874d7ae7bde11314d077f3cf1b2baece4a6cdd7459e83cc2ce2a", date(2026, 5, 28)),
]

ISO_PATTERN = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3,}Z$")


def _row(ts, size, price, trdid, side="Buy", tickdir="PlusTick"):
    size_f, price_f = float(size), float(price)
    return {"timestamp": str(ts), "symbol": "MONUSDT", "side": side, "size": size, "price": price,
            "tickDirection": tickdir, "trdMatchID": trdid, "grossValue": str(size_f * price_f * 1e8),
            "homeNotional": str(size_f), "foreignNotional": str(size_f * price_f)}


def _a_record(rows, day="2023-11-14"):
    text = ",".join(HEADER) + "\n" + "\n".join(",".join(str(row[h]) for h in HEADER) for row in rows) + "\n"
    raw = gzip.compress(text.encode())
    return rp.parse_daily_object(raw, date.fromisoformat(day), "x").record


def _b_core(rows, utc_date="2023-11-14"):
    core, anom = daily_primitive(stream_id="s", utc_date=utc_date, header=BASE_SCHEMA, rows=rows,
                                  historical_cutoff_utc=CUTOFF)
    return core, anom


def _canonical_hash(value) -> str:
    return hashlib.sha256(
        (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()
    ).hexdigest()


# --- 0. frozen protocol immutability (re-verified, not assumed) -------------

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


def test_parser_a_at_prior_repair_commit_was_the_expected_snapshot():
    """Historical snapshot check: Parser A immediately after the duplicate-
    semantics repair (commit e56b201, prior to this timestamp repair) was
    exactly this hash. Immutable regardless of this later, legitimate repair."""
    import subprocess
    result = subprocess.run(
        ["git", "show", "e56b201:qntylab/r1_reference_parser.py"],
        cwd=REPO_ROOT, capture_output=True, check=True,
    )
    assert hashlib.sha256(result.stdout).hexdigest() == PRE_REPAIR_PARSER_A_SHA256


def test_parser_b_at_prior_repair_commit_was_the_expected_snapshot():
    """Same historical-snapshot check for Parser B, which this timestamp
    repair legitimately modifies (unlike the duplicate-semantics repair,
    which left Parser B untouched)."""
    import subprocess
    result = subprocess.run(
        ["git", "show", "e56b201:qntylab/r1_retention_candidate.py"],
        cwd=REPO_ROOT, capture_output=True, check=True,
    )
    assert hashlib.sha256(result.stdout).hexdigest() == PRE_REPAIR_PARSER_B_SHA256


# --- 1. counterexample closure: Parser B bare-float violation ---------------

def test_cx_parser_b_now_emits_iso8601_string_not_float():
    rows = [_row("1585132572.9822", size="1", price="6500", trdid="cx-b-1")]
    core, _ = _b_core(rows, utc_date="2020-03-25")
    assert isinstance(core["first_source_timestamp_utc"], str), (
        "Parser B must emit an ISO-8601 string, not a bare float/number "
        f"(got {core['first_source_timestamp_utc']!r} of type "
        f"{type(core['first_source_timestamp_utc'])})"
    )
    assert ISO_PATTERN.match(core["first_source_timestamp_utc"])
    assert core["first_source_timestamp_utc"] == "2020-03-25T10:36:12.9822Z"
    assert core["last_source_timestamp_utc"] == core["first_source_timestamp_utc"]


def test_cx_parser_b_whole_second_now_millisecond_padded():
    rows = [_row("1647328776", size="1", price="2.7", trdid="cx-b-2")]
    core, _ = _b_core(rows, utc_date="2022-03-15")
    assert core["first_source_timestamp_utc"] == "2022-03-15T07:19:36.000Z"


# --- 2. counterexample closure: Parser A whole-second under-padding --------

def test_cx_parser_a_whole_second_now_millisecond_padded():
    """Pre-repair, Decimal('1647328776') - int(...) == Decimal('0') whose
    str() has no '.', so _epoch_to_iso emitted a single '0' fractional digit
    ('...:36.0Z') instead of the contract-required millisecond-or-finer
    ('...:36.000Z'). Reproduces the real ANCUSDT_2022-03-15 case."""
    a = _a_record([_row("1647328776", size="1", price="2.7", trdid="cx-a-1")], day="2022-03-15")
    assert a["first_source_timestamp_utc"].endswith(".000Z")
    assert a["first_source_timestamp_utc"] == "2022-03-15T07:19:36.000Z"


def test_cx_parser_a_fractional_precision_preserved_not_truncated():
    """Existing >=3-digit fractional precision (e.g. the real BTCUSDT
    4-digit '.9822' token) must be preserved verbatim, never truncated to
    exactly 3 digits."""
    a = _a_record([_row("1585132572.9822", size="1", price="6500", trdid="cx-a-2")], day="2020-03-25")
    assert a["first_source_timestamp_utc"] == "2020-03-25T10:36:12.9822Z"


# --- 3. A/B byte-identical timestamp cross-validation -----------------------

def test_ab_timestamps_byte_identical_across_fractional_digit_counts():
    cases = [
        ("1700000000", "2023-11-14T22:13:20.000Z"),        # whole second
        ("1700000000.1", "2023-11-14T22:13:20.100Z"),       # 1 fractional digit
        ("1700000000.01", "2023-11-14T22:13:20.010Z"),      # 2 fractional digits
        ("1700000000.001", "2023-11-14T22:13:20.001Z"),     # 3 fractional digits
        ("1700000000.1234", "2023-11-14T22:13:20.1234Z"),   # 4 fractional digits
        ("1700000000.123456", "2023-11-14T22:13:20.123456Z"),  # 6 fractional digits
    ]
    for token, expected in cases:
        a = _a_record([_row(token, size="1", price="1", trdid=f"cx-{token}")])
        core, _ = _b_core([_row(token, size="1", price="1", trdid=f"cx-{token}")])
        assert a["first_source_timestamp_utc"] == expected, token
        assert core["first_source_timestamp_utc"] == expected, token
        assert a["first_source_timestamp_utc"] == core["first_source_timestamp_utc"]
        assert type(a["first_source_timestamp_utc"]) is type(core["first_source_timestamp_utc"]) is str


def test_ab_timestamps_byte_identical_across_calendar_boundaries():
    cases = [
        ("1700006399.5", "2023-11-14T23:59:59.500Z", "2023-11-14"),   # before midnight UTC
        ("1700006400.5", "2023-11-15T00:00:00.500Z", "2023-11-15"),   # after midnight UTC
        ("1706745599.25", "2024-01-31T23:59:59.250Z", "2024-01-31"),  # month boundary
        ("1704067199.75", "2023-12-31T23:59:59.750Z", "2023-12-31"),  # year boundary
        ("1709164800.001", "2024-02-29T00:00:00.001Z", "2024-02-29"), # leap day
    ]
    for token, expected, day in cases:
        a = _a_record([_row(token, size="1", price="1", trdid=f"cx-{token}")], day=day)
        core, _ = _b_core([_row(token, size="1", price="1", trdid=f"cx-{token}")], utc_date=day)
        assert a["first_source_timestamp_utc"] == expected, (token, day)
        assert core["first_source_timestamp_utc"] == expected, (token, day)


# --- 4. event-order non-regression: canonical formatting must not reselect --

def test_event_order_unchanged_first_last_trade_identity():
    later = _row("1700000100.000", size="1", price="103", trdid="evt-later")
    earlier = _row("1700000000.000", size="1", price="100", trdid="evt-earlier")
    middle = _row("1700000050.000", size="1", price="101", trdid="evt-middle")
    a = _a_record([later, earlier, middle])
    core, _ = _b_core([later, earlier, middle])
    assert a["first_source_trade_id"] == "evt-earlier"
    assert a["last_source_trade_id"] == "evt-later"
    assert core["first_source_trade_id"] == "evt-earlier"
    assert core["last_source_trade_id"] == "evt-later"
    assert a["open"] == "100" and a["close"] == "103"
    assert core["open"] == "100" and core["close"] == "103"
    # canonical timestamps must correspond to the same (earliest/latest) trades
    assert a["first_source_timestamp_utc"] == core["first_source_timestamp_utc"] == "2023-11-14T22:13:20.000Z"
    assert a["last_source_timestamp_utc"] == core["last_source_timestamp_utc"] == "2023-11-14T22:15:00.000Z"


def test_event_order_unchanged_with_duplicate_group_present():
    dup_a = _row("1700000000.000", size="2", price="1.1", trdid="dup-1")
    dup_b = _row("1700000000.000", size="2.00", price="1.10", trdid="dup-1")
    later = _row("1700000100.000", size="5", price="4.35", trdid="dup-later")
    a = _a_record([later, dup_b, dup_a])
    core, _ = _b_core([later, dup_b, dup_a])
    assert a["first_source_trade_id"] == core["first_source_trade_id"] == "dup-1"
    assert a["last_source_trade_id"] == core["last_source_trade_id"] == "dup-later"
    assert a["open"] == core["open"] == "1.1"
    assert a["close"] == core["close"] == "4.35"


# --- 5. duplicate-semantics non-regression ----------------------------------

def test_duplicate_semantics_still_agree_price_scale():
    a_row = _row("1700000000.000", size="2", price="1.1", trdid="d-1")
    b_row = _row("1700000000.000", size="2.00", price="1.10", trdid="d-1")
    for perm in itertools.permutations([a_row, b_row]):
        a = _a_record(list(perm))
        core, _ = _b_core(list(perm))
        assert a["close"] == core["close"] == "1.1"
        assert a["base_volume"] == core["base_volume"] == "2"


def test_duplicate_semantics_still_agree_three_plus_spellings():
    spellings = ["1.1", "1.10", "1.100", "1.1000"]
    rows = [_row("1700000000.000", size="2", price=p, trdid="d-2") for p in spellings]
    for perm in itertools.permutations(rows):
        a = _a_record(list(perm))
        core, _ = _b_core(list(perm))
        assert a["close"] == core["close"] == "1.1"


def test_duplicate_semantics_genuine_conflict_still_fails_closed():
    a_row = _row("1700000000.000", size="2", price="1.1", trdid="d-3")
    b_row = _row("1700000000.000", size="2", price="1.2", trdid="d-3")
    for perm in itertools.permutations([a_row, b_row]):
        a = _a_record(list(perm))
        core, anom = _b_core(list(perm))
        assert a["trade_count"] == 0
        assert core["trade_count"] == 0
        assert ANOMALY_DUPLICATE_CONFLICTING in anom


# --- 6. numeric non-regression ----------------------------------------------

def test_numeric_fields_unaffected_by_timestamp_repair():
    from decimal import Decimal
    row_435 = _row("1700000000.000", size="100", price="4.35", trdid="n-1")
    a = _a_record([row_435])
    core, _ = _b_core([row_435])
    assert a["quote_turnover"] == core["quote_turnover"] == "435.00"

    rows_sum = [_row("1700000000.001", size="0.1", price="1", trdid="n-2"),
                _row("1700000000.002", size="0.2", price="1", trdid="n-3"),
                _row("1700000000.003", size="0.3", price="1", trdid="n-4")]
    a = _a_record(rows_sum)
    core, _ = _b_core(rows_sum)
    oracle = Decimal("0.1") + Decimal("0.2") + Decimal("0.3")
    assert Decimal(a["base_volume"]) == Decimal(core["base_volume"]) == oracle

    big_row = _row("1700000000.000", size="12345678901234567890.1",
                    price="1.00000000000000000001", trdid="n-5")
    a = _a_record([big_row])
    core, _ = _b_core([big_row])
    assert a["quote_turnover"] == core["quote_turnover"]


# --- 7. property / metamorphic: permutation + duplicate-spelling invariance -

def test_property_row_permutation_same_canonical_timestamps():
    rows = [
        _row("1700000000.500", size="1", price="10", trdid="p-1"),
        _row("1700000100.250", size="2", price="20", trdid="p-2"),
        _row("1700000200.125", size="3", price="30", trdid="p-3"),
    ]
    first_ts, last_ts = set(), set()
    for perm in itertools.permutations(rows):
        a = _a_record(list(perm))
        core, _ = _b_core(list(perm))
        assert a["first_source_timestamp_utc"] == core["first_source_timestamp_utc"]
        assert a["last_source_timestamp_utc"] == core["last_source_timestamp_utc"]
        first_ts.add(a["first_source_timestamp_utc"])
        last_ts.add(a["last_source_timestamp_utc"])
    assert len(first_ts) == 1 and len(last_ts) == 1


def test_property_equivalent_duplicate_spelling_permutation_same_canonical_timestamps():
    rows = [
        _row("1700000000.000", size="2", price="1.1", trdid="q-1"),
        _row("1700000000.000", size="2.00", price="1.10", trdid="q-1"),
        _row("1700000000.000", size="2.000", price="1.100", trdid="q-1"),
    ]
    hashes = set()
    for perm in itertools.permutations(rows):
        a = _a_record(list(perm))
        core, _ = _b_core(list(perm))
        assert a["first_source_timestamp_utc"] == core["first_source_timestamp_utc"] == "2023-11-14T22:13:20.000Z"
        hashes.add((a["first_source_timestamp_utc"], a["last_source_timestamp_utc"]))
    assert len(hashes) == 1


# --- 8. real-corpus cross-validation: BTC / ANC / FTT counterexamples ------

def test_real_corpus_timestamp_agreement_and_counterexample_closure():
    checked = 0
    closures = {"BTCUSDT_2020-03-25": False, "ANCUSDT_2022-03-15": False, "FTTUSDT_2022-11-13": False}
    for name, sha, day in REAL_OBJECTS:
        path = CACHE_DIR / sha
        if not path.exists():
            continue
        raw = path.read_bytes()
        a = rp.parse_daily_object(raw, day, f"x|{name}")
        text = gzip.decompress(raw).decode("utf-8")
        header = tuple(next(csv.reader(io.StringIO(text))))
        b_rows = list(csv.DictReader(io.StringIO(text)))
        b_core, b_anom = daily_primitive(stream_id=name, utc_date=day.isoformat(), header=header,
                                          rows=b_rows, historical_cutoff_utc=CUTOFF)
        assert b_anom == [], f"{name}: unexpected Parser B anomalies {b_anom}"

        for field in ("first_source_timestamp_utc", "last_source_timestamp_utc"):
            assert isinstance(a.record[field], str), f"{name}: A.{field} not a string"
            assert isinstance(b_core[field], str), f"{name}: B.{field} not a string"
            assert ISO_PATTERN.match(a.record[field]), f"{name}: A.{field}={a.record[field]!r}"
            assert ISO_PATTERN.match(b_core[field]), f"{name}: B.{field}={b_core[field]!r}"
            assert a.record[field] == b_core[field], f"{name}: A/B disagree on {field}"

        if name in closures:
            closures[name] = True
        checked += 1
    assert checked == 5, "expected all 5 cached real pilot objects to be present"
    assert all(closures.values()), f"missing real-corpus counterexample objects: {closures}"

    # explicit named closure assertions
    btc = next(o for o in REAL_OBJECTS if o[0] == "BTCUSDT_2020-03-25")
    anc = next(o for o in REAL_OBJECTS if o[0] == "ANCUSDT_2022-03-15")
    ftt = next(o for o in REAL_OBJECTS if o[0] == "FTTUSDT_2022-11-13")
    for name, sha, day in (btc, anc, ftt):
        raw = (CACHE_DIR / sha).read_bytes()
        a = rp.parse_daily_object(raw, day, f"x|{name}")
        assert ISO_PATTERN.match(a.record["first_source_timestamp_utc"])
        assert a.record["first_source_timestamp_utc"].split(".")[1].rstrip("Z").__len__() >= 3


# --- 9. contract-projection: source_object_sha256 handling documented ------

def test_source_object_sha256_still_parser_a_only_by_design():
    """source_object_sha256 fingerprints the literal raw archive bytes (per
    r1_ingest_contract.json:pipeline), not row content. Parser A computes and
    returns it inside parse_daily_object; Parser B's daily_primitive does not
    compute it at all (it is a receipt-layer concern for Parser B, built
    separately in build_receipt). This repair does not change that division
    of responsibility -- it is out of scope for a timestamp-field repair."""
    row = _row("1700000000.000", size="1", price="1", trdid="src-1")
    a = _a_record([row])
    core, _ = _b_core([row])
    assert "source_object_sha256" in a
    assert "source_object_sha256" not in core
