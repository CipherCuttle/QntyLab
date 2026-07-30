"""Regression / property tests for the Parser B (`daily_primitive`) canonical-
serialization and diagnostic-guard repair that resolves the two independent-
review counterexamples reported against commit 220d59b:

  CX-1 (BLOCKED_BY_CANONICAL_SERIALIZATION): for a duplicate group whose
  members are numerically equal but textually spelled at different decimal
  scales (e.g. price "1.1" vs "1.10", size "2" vs "2.00"), Parser B kept
  `group[0]` -- whichever row the raw feed happened to list first -- as the
  surviving representative. Numeric value was unaffected, but the *spelling*
  of open/high/low/close/base_volume/quote_turnover (and therefore the
  canonical bytes and canonical hash) depended on raw row order.

  CX-2 (uncaught diagnostic float conversion): the redundant-field diagnostic
  cast `float(size)`/`float(price)` outside the row's protected parse. A
  price token that `Decimal()` accepts without error but `float()` rejects
  (e.g. "sNaN", a signaling NaN) escaped as an uncaught ValueError instead of
  the intended PARSE_REJECTION.

Repair (qntylab/r1_retention_candidate.py):
  - `_canonical_duplicate_representative` selects the duplicate-group
    survivor by `min(group, key=lambda g: (str(price), str(size)))` -- a
    pure function of the group's own content, not of arrival order.
  - The diagnostic float() conversion is now inside the same try/except as
    the rest of the row's parse; on failure the row is rejected via the
    existing ANOMALY_PARSE_REJECTION path (the row is excluded from
    aggregation entirely -- letting an sNaN Decimal through would only move
    the uncaught crash to the later Decimal sum()/max() aggregation).

Neither fix touches Parser A (qntylab/r1_reference_parser.py), the frozen
contract artifacts, or any other duplicate/conflict/numeric behavior.
"""

import itertools

from qntylab.r1_input_bom import canonical_hash
from qntylab.r1_retention_candidate import (
    ANOMALY_DUPLICATE_CONFLICTING,
    ANOMALY_DUPLICATE_UNEXPECTED,
    ANOMALY_PARSE_REJECTION,
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


def _primitive(rows, utc_date="2025-07-01", header=BASE_SCHEMA):
    return daily_primitive(stream_id="s", utc_date=utc_date, header=header,
                            rows=rows, historical_cutoff_utc=CUTOFF)


def _canonical(result):
    primitive, anomalies = result
    return canonical_hash(primitive), tuple(sorted(anomalies))


# --- CX-1: mixed-scale duplicate order invariance ---------------------------

def test_cx1_mixed_scale_price_duplicate_is_order_invariant():
    """price '1.1' vs '1.10', same trdMatchID/timestamp/size. Post-repair,
    forward and reversed row order must yield byte-identical canonical
    output (this is the exact reported counterexample shape)."""
    a = row("1751328000.0", size="2", price="1.1", trdid="c" * 32)
    b = row("1751328000.0", size="2", price="1.10", trdid="c" * 32)
    forward, anom_f = _primitive([a, b])
    reverse, anom_r = _primitive([b, a])
    assert forward == reverse
    assert anom_f == anom_r
    assert forward["duplicate_count"] == 1
    assert ANOMALY_DUPLICATE_UNEXPECTED in anom_f


def test_cx1_mixed_scale_size_duplicate_is_order_invariant():
    """size '2' vs '2.00', same trdMatchID/timestamp/price."""
    a = row("1751328000.0", size="2", price="1.1", trdid="c" * 32)
    b = row("1751328000.0", size="2.00", price="1.1", trdid="c" * 32)
    forward, anom_f = _primitive([a, b])
    reverse, anom_r = _primitive([b, a])
    assert forward == reverse
    assert anom_f == anom_r


def test_cx1_reported_example_price_and_size_both_mixed_scale():
    """The exact reported minimal shape: price "1.1"/"1.10" AND size implicitly
    consistent, with quote_turnover "2.2"/"2.2000" differing pre-repair."""
    a = row("1751328000.0", size="2", price="1.1", trdid="c" * 32)
    b = row("1751328000.0", size="2.00", price="1.10", trdid="c" * 32)
    forward, _ = _primitive([a, b])
    reverse, _ = _primitive([b, a])
    assert forward == reverse
    assert forward["close"] == "1.1"
    assert forward["quote_turnover"] == "2.2"
    assert forward["base_volume"] == "2"


def test_cx1_mixed_scale_duplicate_plus_ordinary_trade_all_permutations():
    """The defect must not only be tested in an isolated one-observation day:
    add one ordinary distinct trade alongside the mixed-scale duplicate pair
    and require all 3! row-order permutations to agree byte-for-byte."""
    dup_a = row("1751328000.0", size="2", price="1.1", trdid="c" * 32)
    dup_b = row("1751328000.0", size="2.00", price="1.10", trdid="c" * 32)
    ordinary = row("1751328100.0", size="5", price="4.35", trdid="d" * 32)
    trades = [dup_a, dup_b, ordinary]
    results = {_canonical(_primitive(list(perm))) for perm in itertools.permutations(trades)}
    assert len(results) == 1, f"expected one canonical result across permutations, got {len(results)}"
    primitive, anomalies = _primitive(trades)
    assert primitive["trade_count"] == 2
    assert primitive["duplicate_count"] == 1
    assert ANOMALY_DUPLICATE_UNEXPECTED in anomalies


def test_cx1_canonical_hash_invariant_not_only_numeric_value():
    """The bug was byte/hash nondeterminism, not numeric wrongness -- assert
    canonical_hash equality explicitly, not just numeric equality."""
    a = row("1751328000.0", size="2", price="1.1", trdid="c" * 32)
    b = row("1751328000.0", size="2.00", price="1.10", trdid="c" * 32)
    forward, _ = _primitive([a, b])
    reverse, _ = _primitive([b, a])
    assert canonical_hash(forward) == canonical_hash(reverse)


# --- unaffected duplicate/conflict behaviors --------------------------------

def test_exact_textual_duplicate_behavior_unchanged():
    a = row("1751328000.0", trdid="c" * 32, price="4.35", size="100")
    b = row("1751328000.0", trdid="c" * 32, price="4.35", size="100")
    primitive, anomalies = _primitive([a, b])
    assert primitive["trade_count"] == 1
    assert primitive["duplicate_count"] == 1
    assert primitive["quote_turnover"] == "435.00"
    assert ANOMALY_DUPLICATE_UNEXPECTED in anomalies
    assert ANOMALY_DUPLICATE_CONFLICTING not in anomalies


def test_conflicting_duplicate_still_fails_closed_and_order_invariant():
    """Genuine numeric conflict (same identity, price 1.1 vs 1.2) must still
    fail closed -- the representative-selection repair must never pick a
    winner for a truly conflicting group."""
    a = row("1751328000.0", trdid="c" * 32, price="1.1", size="2")
    b = row("1751328000.0", trdid="c" * 32, price="1.2", size="2")
    forward, anom_f = _primitive([a, b])
    reverse, anom_r = _primitive([b, a])
    assert forward == reverse
    assert forward["trade_count"] == 0
    assert forward["close"] is None
    assert forward["rejected_row_count"] == 2
    assert ANOMALY_DUPLICATE_CONFLICTING in anom_f
    assert ANOMALY_DUPLICATE_CONFLICTING in anom_r


def test_side_only_and_tickdirection_only_duplicate_behavior_unaffected():
    """side/tickDirection differences alone (numeric price/size/timestamp
    identical) never reach a canonical output field and must still collapse
    as an ordinary duplicate, unaffected by the representative-selection
    change (which only tie-breaks on price/size spelling)."""
    a = row("1751328000.0", trdid="c" * 32, price="4.35", size="100", side="Buy", tickdir="PlusTick")
    b = row("1751328000.0", trdid="c" * 32, price="4.35", size="100", side="Sell", tickdir="ZeroPlusTick")
    forward, anom_f = _primitive([a, b])
    reverse, anom_r = _primitive([b, a])
    assert forward == reverse
    assert forward["trade_count"] == 1
    assert forward["duplicate_count"] == 1
    assert ANOMALY_DUPLICATE_UNEXPECTED in anom_f
    assert ANOMALY_DUPLICATE_CONFLICTING not in anom_f


# --- CX-2: guarded diagnostic conversion ------------------------------------

def _snan_row(ts, *, trdid, price="10.0", size="1.0"):
    """`row()` unconditionally computes float(size)/float(price) to derive
    home/foreign/gross defaults, which itself raises on "sNaN" independent
    of the parser under test. Build the raw row dict directly so the fixture
    isolates the parser's own handling of a malformed price/size."""
    return {"timestamp": str(ts), "symbol": "MONUSDT", "side": "Buy", "size": size, "price": price,
            "tickDirection": "PlusTick", "trdMatchID": trdid, "grossValue": "1",
            "homeNotional": "1", "foreignNotional": "1"}


def test_cx2_snan_price_no_longer_raises_uncaught_exception():
    """Reproduction: before the repair this call raised an uncaught
    ValueError ('cannot convert signaling NaN to float') from the diagnostic
    float(price) cast. It must not raise at all now."""
    r = _snan_row("1751328000.0", price="sNaN", trdid="c" * 32)
    primitive, anomalies = _primitive([r])  # must not raise
    assert primitive is not None


def test_cx2_snan_price_produces_controlled_rejection():
    """Acceptable post-repair semantic result: the same controlled
    PARSE_REJECTION path as any other malformed row -- trade_count=0,
    close=None, matching the pre-Decimal-migration behavior for this input."""
    r = _snan_row("1751328000.0", price="sNaN", trdid="c" * 32)
    primitive, anomalies = _primitive([r])
    assert primitive["trade_count"] == 0
    assert primitive["close"] is None
    assert primitive["rejected_row_count"] == 1
    assert ANOMALY_PARSE_REJECTION in anomalies


def test_cx2_snan_size_also_produces_controlled_rejection():
    r = _snan_row("1751328000.0", size="sNaN", trdid="c" * 32)
    primitive, anomalies = _primitive([r])
    assert primitive["trade_count"] == 0
    assert ANOMALY_PARSE_REJECTION in anomalies


def test_cx2_snan_row_does_not_prevent_other_rows_in_same_object_from_parsing():
    """The diagnostic guard must reject only the malformed row, not the
    whole object -- an ordinary sibling trade on the same day still parses."""
    bad = _snan_row("1751328000.0", price="sNaN", trdid="c" * 32)
    ok = row("1751328100.0", price="4.35", size="100", trdid="d" * 32)
    primitive, anomalies = _primitive([bad, ok])
    assert primitive["trade_count"] == 1
    assert primitive["quote_turnover"] == "435.00"
    assert primitive["rejected_row_count"] == 1
    assert ANOMALY_PARSE_REJECTION in anomalies


def test_cx2_diagnostic_remains_noncanonical_and_nonbinding_on_ordinary_rows():
    """An ordinary, fully valid row is completely unaffected by the guard:
    same canonical output as before this repair."""
    r = row("1751328000.0", price="4.35", size="100", trdid="1" * 32)
    primitive, anomalies = _primitive([r])
    assert primitive["quote_turnover"] == "435.00"
    assert anomalies == []


# --- property test: permutations including mixed-scale duplicates ----------

def test_property_permutation_invariance_with_mixed_scale_duplicates_and_ordinary_trades():
    """Targets the exact hole the pre-existing property test
    (test_r1_retention_candidate_numeric_repair_v1.py::
    test_property_precision_sensitive_fixture_invariant_under_all_permutations)
    could not expose: that test only permuted rows with *distinct* trade IDs,
    so it could never generate a duplicate group. This fixture explicitly
    includes a duplicate group whose members share a Decimal value but differ
    in textual scale, alongside ordinary distinct trades, and requires exactly
    one canonical byte result (and one canonical hash) across every
    permutation of the raw rows."""
    dup_a = row("1751328000.0", size="2", price="1.1", trdid="c" * 32)
    dup_b = row("1751328000.0", size="2.00", price="1.10", trdid="c" * 32)
    ordinary_1 = row("1751328100.0", size="1", price="0.1", trdid="e" * 32)
    ordinary_2 = row("1751328200.0", size="1", price="0.2", trdid="f" * 32)
    trades = [dup_a, dup_b, ordinary_1, ordinary_2]

    results = {_canonical(_primitive(list(perm))) for perm in itertools.permutations(trades)}
    assert len(results) == 1, f"expected one canonical result across all permutations, got {len(results)}"

    primitive, anomalies = _primitive(trades)
    assert primitive["trade_count"] == 3
    assert primitive["duplicate_count"] == 1
    assert anomalies == [ANOMALY_DUPLICATE_UNEXPECTED]
