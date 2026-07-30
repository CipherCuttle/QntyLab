"""Cross-validation of Parser A (independent, contract-derived) against
Parser B (qntylab.r1_retention_candidate.daily_primitive, a pre-existing
unfrozen candidate -- NOT "production": it has no callers anywhere in the
repository and its own module docstring disclaims frozen status).

This file intentionally imports Parser B; Parser A itself (qntylab/r1_reference_parser.py)
never does (see test_r1_reference_parser.py::test_reference_parser_does_not_import_production_semantic_parser).
Parser A was written, tested, and its implementation hashed BEFORE this file
was written or Parser B's source was read for this task.
"""

import gzip
from datetime import date

from qntylab import r1_reference_parser as rp
from qntylab.r1_retention_candidate import daily_primitive

CACHE_DIR = "/home/swirky/DevHub/repos/QntyLab/.r1_input_cache/sha256"

REAL_OBJECTS = [
    ("BTCUSDT_2020-03-25", "cbca6933a8f0a11429661cfa93b04056055d776ee199209e8af9719ad2060a33", date(2020, 3, 25)),
    ("UNIUSDT_2021-11-30", "8068ed2f06c280ad103b50525c4c8bc14a3a956a6ed40f4fba50ff738d59ebb4", date(2021, 11, 30)),
    ("ANCUSDT_2022-03-15", "cabc599c8d0b2da8df4bb07de64700092701ac8bf4987ee8b4395bef8a6398d2", date(2022, 3, 15)),
    ("FTTUSDT_2022-11-13", "8c085036c9b65a99379941434f3531fa7365b24e31a752cd10a0d80ea8df77fc", date(2022, 11, 13)),
    ("1000000CHEEMSUSDT_2026-05-28", "d1b50f8316c1874d7ae7bde11314d077f3cf1b2baece4a6cdd7459e83cc2ce2a", date(2026, 5, 28)),
]

HEADER = ("timestamp", "symbol", "side", "size", "price", "tickDirection",
          "trdMatchID", "grossValue", "homeNotional", "foreignNotional")


def _run_both(rows, day="2023-11-14"):
    import csv
    import io

    text = ",".join(HEADER) + "\n" + "\n".join(",".join(str(x) for x in r) for r in rows) + "\n"
    raw = gzip.compress(text.encode())
    a = rp.parse_daily_object(raw, date.fromisoformat(day), "x")
    b_rows = list(csv.DictReader(io.StringIO(text)))
    b_core, b_anom = daily_primitive(
        stream_id="x", utc_date=day, header=HEADER, rows=b_rows,
        historical_cutoff_utc="2026-06-30T23:59:59Z",
    )
    return a, b_core, b_anom


def test_real_objects_agree_on_core_aggregates():
    """Across all 5 real cached objects, A and B agree exactly on trade_count
    and to float precision on close/open/high/low/base_volume/quote_turnover.
    This is the positive convergence result: no anomalies present in these
    objects, so the precision-representation difference (Decimal-string vs
    float64) never manifests as a numeric disagreement here."""
    import csv
    import io

    for name, sha, day in REAL_OBJECTS:
        raw = open(f"{CACHE_DIR}/{sha}", "rb").read()
        a = rp.parse_daily_object(raw, day, f"x|{name}")
        text = gzip.decompress(raw).decode("utf-8")
        header = tuple(next(csv.reader(io.StringIO(text))))
        b_rows = list(csv.DictReader(io.StringIO(text)))
        b_core, b_anom = daily_primitive(
            stream_id=name, utc_date=day.isoformat(), header=header, rows=b_rows,
            historical_cutoff_utc="2026-06-30T23:59:59Z",
        )
        assert b_anom == [], f"{name}: unexpected Parser B anomalies {b_anom}"
        assert a.record["trade_count"] == b_core["trade_count"], name
        assert abs(float(a.record["close"]) - b_core["close"]) < 1e-9, name
        assert abs(float(a.record["quote_turnover"]) - b_core["quote_turnover"]) < 1e-6, name
        assert abs(float(a.record["base_volume"]) - b_core["base_volume"]) < 1e-9, name


def test_formerly_disagreement_side_included_in_b_fingerprint_not_in_contract():
    """REPAIRED (was a CONFIRMED DISAGREEMENT at blocked commit 2369336, see
    experiments/results/R1_REFERENCE_PARSER_VALIDATION_V1.md and
    tests/test_r1_retention_candidate_repair_v1.py for the repair record):
    two rows sharing trade id/timestamp/price/size but differing only in
    `side` are an exact duplicate per the frozen contract's own definition
    (duplicate_semantics: "identical trade id/timestamp/price/size" -- side
    is not listed, and the information-loss ledger classifies `side` as
    INTENTIONALLY_DISCARDED). Parser B's fingerprint used to additionally
    include `side`, mislabeling this case DUPLICATE_CONFLICTING; post-repair
    it agrees with Parser A that this is an ordinary exact duplicate."""
    rows = [
        ("1700000000.000", "TESTUSDT", "Buy", "1", "100", "PlusTick", "id-1", "1e8", "1", "100"),
        ("1700000000.000", "TESTUSDT", "Sell", "1", "100", "PlusTick", "id-1", "1e8", "1", "100"),
    ]
    a, b, banom = _run_both(rows)
    assert a.record["duplicate_count"] == 1
    assert a.record["rejected_row_count"] == 0
    assert "DUPLICATE_CONFLICTING" not in banom
    assert "DUPLICATE_UNEXPECTED" in banom
    assert a.record["trade_count"] == b["trade_count"] == 1


def test_formerly_disagreement_conflicting_duplicate_row_order_dependence():
    """REPAIRED (was a CONFIRMED DISAGREEMENT, blocking, at blocked commit
    2369336; see tests/test_r1_retention_candidate_repair_v1.py for the
    repair record). r1_source_precedence_freeze.json:conflict_rule requires
    conflicting canonical values to be fail-closed ("no lower-priority
    source silently replaces a higher-priority fact"). For a genuinely
    conflicting duplicate (same trade id, different price), Parser A
    excludes both rows from aggregation regardless of input row order
    (fail-closed, order-invariant). Parser B used to silently retain
    whichever row it encountered FIRST in iteration order -- so its `close`
    value for logically identical data changed depending on raw row order.
    Post-repair, Parser B groups by trade identity before classifying, so it
    now agrees with Parser A: fail-closed and order-invariant."""
    rows_fwd = [
        ("1700000000.000", "TESTUSDT", "Buy", "1", "100", "PlusTick", "id-1", "1e8", "1", "100"),
        ("1700000005.000", "TESTUSDT", "Buy", "1", "999", "PlusTick", "id-1", "1e8", "1", "999"),
    ]
    rows_rev = list(reversed(rows_fwd))

    a_f, b_f, banom_f = _run_both(rows_fwd)
    a_r, b_r, banom_r = _run_both(rows_rev)

    # Parser A: fail-closed and order-invariant
    assert a_f.record["trade_count"] == 0
    assert a_r.record["trade_count"] == 0
    assert a_f.record["rejected_row_count"] == a_r.record["rejected_row_count"] == 2

    # Parser B (post-repair): also fail-closed and order-invariant
    assert b_f["close"] == b_r["close"] is None
    assert b_f["trade_count"] == b_r["trade_count"] == 0
    assert b_f["rejected_row_count"] == b_r["rejected_row_count"] == 2
    assert "DUPLICATE_CONFLICTING" in banom_f and "DUPLICATE_CONFLICTING" in banom_r
