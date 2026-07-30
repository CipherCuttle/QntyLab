"""Regression / property tests for the Parser B (`daily_primitive`) repair
that resolves the two contract-conformance defects found by the independent
Parser A vs. Parser B cross-validation at blocked commit `2369336`
(see experiments/results/R1_REFERENCE_PARSER_VALIDATION_V1.md and
tests/test_r1_parser_a_vs_b_cross_validation.py):

  1. Conflicting-duplicate handling was row-order dependent (silently kept
     whichever row was seen first), contradicting the frozen fail-closed
     conflict_rule in r1_source_precedence_freeze.json.
  2. The dedup fingerprint included `side`, which r1_information_loss_ledger_v1.json
     classifies INTENTIONALLY_DISCARDED and which the frozen contract's own
     duplicate definition (r1_normalized_evidence_contract_v1.json:
     DailyMarketEvidenceV1.close.duplicate_semantics -- "identical trade
     id/timestamp/price/size") does not include.

Repair: qntylab/r1_retention_candidate.py now groups rows by trdMatchID
before classifying (rather than scanning sequentially and keeping the first
row seen), and the group-distinctness check omits `side`. See the repair
receipt for exact pre/post implementation SHA-256 values.
"""

import itertools

from qntylab.r1_retention_candidate import (
    ANOMALY_DUPLICATE_CONFLICTING,
    ANOMALY_DUPLICATE_UNEXPECTED,
    ANOMALY_TIMESTAMP_CONTAINMENT,
    BASE_SCHEMA,
    daily_primitive,
)

CUTOFF = "2026-06-30T23:59:59Z"


def row(ts, side="Buy", size="1.0", price="10.0", tickdir="PlusTick", trdid="a" * 32,
        home=None, foreign=None, gross=None):
    size_f, price_f = float(size), float(price)
    home = home if home is not None else str(size_f)
    foreign = foreign if foreign is not None else str(size_f * price_f)
    gross = gross if gross is not None else str(size_f * price_f * 1e8)
    return {"timestamp": str(ts), "symbol": "MONUSDT", "side": side, "size": size, "price": price,
            "tickDirection": tickdir, "trdMatchID": trdid, "grossValue": gross,
            "homeNotional": home, "foreignNotional": foreign}


def _primitive(rows, utc_date="2025-07-01"):
    return daily_primitive(stream_id="s", utc_date=utc_date, header=BASE_SCHEMA,
                            rows=rows, historical_cutoff_utc=CUTOFF)


# 1. identical duplicate rows -------------------------------------------------

def test_identical_duplicate_rows_collapse_to_one_observation():
    rows = [row("1751328000.0", trdid="c" * 32, price="10"),
            row("1751328000.0", trdid="c" * 32, price="10")]
    primitive, anomalies = _primitive(rows)
    assert primitive["trade_count"] == 1
    assert primitive["duplicate_count"] == 1
    assert primitive["close"] == "10"
    assert ANOMALY_DUPLICATE_UNEXPECTED in anomalies
    assert ANOMALY_DUPLICATE_CONFLICTING not in anomalies


# 2. conflicting duplicate rows fail closed -----------------------------------

def test_conflicting_duplicate_rows_fail_closed():
    rows = [row("1751328000.0", trdid="c" * 32, price="100"),
            row("1751328005.0", trdid="c" * 32, price="999")]
    primitive, anomalies = _primitive(rows)
    assert primitive["trade_count"] == 0
    assert primitive["close"] is None
    assert primitive["rejected_row_count"] == 2
    assert primitive["duplicate_count"] == 0
    assert ANOMALY_DUPLICATE_CONFLICTING in anomalies


# 3. conflicting duplicates in reversed order ---------------------------------

def test_conflicting_duplicate_reversed_order_yields_identical_result():
    rows = [row("1751328000.0", trdid="c" * 32, price="100"),
            row("1751328005.0", trdid="c" * 32, price="999")]
    forward, anomalies_f = _primitive(rows)
    reverse, anomalies_r = _primitive(list(reversed(rows)))
    assert forward == reverse
    assert anomalies_f == anomalies_r
    assert forward["trade_count"] == 0 and forward["close"] is None


# 4. 3+ permutations of the same conflicting set ------------------------------

def test_conflicting_duplicate_set_of_three_is_identical_under_every_permutation():
    conflicting = [
        row("1751328000.0", trdid="c" * 32, price="100"),
        row("1751328005.0", trdid="c" * 32, price="999"),
        row("1751328010.0", trdid="c" * 32, price="50"),
    ]
    results = {_json_key(_primitive(list(perm))) for perm in itertools.permutations(conflicting)}
    assert len(results) == 1, "conflicting-duplicate result must be identical under every permutation"
    primitive, anomalies = _primitive(conflicting)
    assert primitive["trade_count"] == 0
    assert primitive["rejected_row_count"] == 3
    assert ANOMALY_DUPLICATE_CONFLICTING in anomalies


def _json_key(result):
    primitive, anomalies = result
    return (tuple(sorted(primitive.items())), tuple(anomalies))


# 5. duplicate identity differing only in `side` -------------------------------

def test_duplicate_identity_excludes_side_per_frozen_contract():
    """r1_information_loss_ledger_v1.json classifies `side` INTENTIONALLY_DISCARDED
    and r1_normalized_evidence_contract_v1.json's own duplicate definition for
    `close` is "identical trade id/timestamp/price/size" -- side is not part
    of canonical trade identity, so two rows differing only in side must be
    treated as an ordinary exact duplicate, not a conflict."""
    rows = [row("1751328000.0", trdid="c" * 32, price="10", side="Buy"),
            row("1751328000.0", trdid="c" * 32, price="10", side="Sell")]
    primitive, anomalies = _primitive(rows)
    assert primitive["trade_count"] == 1
    assert primitive["duplicate_count"] == 1
    assert ANOMALY_DUPLICATE_UNEXPECTED in anomalies
    assert ANOMALY_DUPLICATE_CONFLICTING not in anomalies


# 6/7/8. reorder invariance for ordinary valid trades; close/quote_turnover unchanged

def test_ordinary_valid_trades_are_reorder_invariant_including_close_and_turnover():
    trades = [
        row("1751328000.0", trdid="1" * 32, price="5", size="1.0"),
        row("1751328100.0", trdid="2" * 32, price="8", size="2.0"),
        row("1751328200.0", trdid="3" * 32, price="3", size="1.5"),
    ]
    results = {_json_key(_primitive(list(perm))) for perm in itertools.permutations(trades)}
    assert len(results) == 1, "ordinary valid-trade aggregation must be identical under every permutation"
    primitive, anomalies = _primitive(trades)
    assert primitive["trade_count"] == 3
    assert primitive["open"] == "5"
    assert primitive["close"] == "3"
    assert primitive["high"] == "8"
    assert primitive["low"] == "3"
    assert primitive["base_volume"] == "4.5"
    assert primitive["quote_turnover"] == "25.5"
    assert anomalies == []


# 9. deterministic conflict diagnostics ----------------------------------------

def test_conflict_diagnostics_are_deterministic_across_permutations():
    conflicting = [
        row("1751328000.0", trdid="c" * 32, price="100"),
        row("1751328005.0", trdid="c" * 32, price="999"),
    ]
    ordinary = [row("1751328050.0", trdid="d" * 32, price="42")]
    mixed = conflicting + ordinary
    anomaly_sets = {tuple(_primitive(list(perm))[1]) for perm in itertools.permutations(mixed)}
    assert len(anomaly_sets) == 1
    primitive, anomalies = _primitive(mixed)
    assert anomalies == sorted(set(anomalies))
    assert ANOMALY_DUPLICATE_CONFLICTING in anomalies
    assert primitive["trade_count"] == 1
    assert primitive["close"] == "42"
    assert primitive["rejected_row_count"] == 2


# 10. UTC-day semantics unchanged ------------------------------------------------

def test_utc_day_boundary_semantics_unaffected_by_dedup_repair():
    late = row("1751414399.999", price="9", trdid="1" * 32)   # 2025-07-01T23:59:59.999Z
    early = row("1751414400.0", price="12", trdid="2" * 32)   # 2025-07-02T00:00:00Z
    day1, anomalies1 = _primitive([late, early], utc_date="2025-07-01")
    assert day1["trade_count"] == 1 and day1["close"] == "9"
    assert ANOMALY_TIMESTAMP_CONTAINMENT in anomalies1
    day2, anomalies2 = _primitive([late, early], utc_date="2025-07-02")
    assert day2["trade_count"] == 1 and day2["close"] == "12"
    assert ANOMALY_TIMESTAMP_CONTAINMENT in anomalies2


# --- property test: bounded fixture, exhaustive permutations -----------------

def test_property_mixed_fixture_invariant_under_all_permutations():
    """Bounded N=4 fixture (small enough to enumerate all 24 permutations):
    two ordinary valid trades plus one genuinely conflicting duplicate pair
    sharing a third trade id. For every permutation: the two valid records
    aggregate identically, and the conflicting pair produces the same
    deterministic fail-closed state -- never a physical-row-order effect."""
    ordinary_x = row("1751328100.0", trdid="1" * 32, price="5", size="1.0")
    ordinary_y = row("1751328200.0", trdid="2" * 32, price="8", size="1.0")
    conflict_1 = row("1751328300.0", trdid="3" * 32, price="50", size="1.0")
    conflict_2 = row("1751328400.0", trdid="3" * 32, price="77", size="1.0")
    fixture = [ordinary_x, ordinary_y, conflict_1, conflict_2]

    seen = set()
    for perm in itertools.permutations(fixture):
        primitive, anomalies = _primitive(list(perm))
        seen.add(_json_key((primitive, anomalies)))

    assert len(seen) == 1, f"expected exactly one canonical result across all permutations, got {len(seen)}"

    primitive, anomalies = _primitive(fixture)
    # valid records (x, y) aggregate deterministically
    assert primitive["trade_count"] == 2
    assert primitive["open"] == "5"
    assert primitive["close"] == "8"
    assert primitive["base_volume"] == "2.0"
    assert primitive["quote_turnover"] == "13.0"
    # conflicting identity fails closed, deterministically, every time
    assert primitive["rejected_row_count"] == 2
    assert primitive["duplicate_count"] == 0
    assert ANOMALY_DUPLICATE_CONFLICTING in anomalies
