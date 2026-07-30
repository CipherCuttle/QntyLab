"""Regression / property tests for the Parser B (`daily_primitive`) numeric-
precision repair: `open`/`high`/`low`/`close`/`base_volume`/`quote_turnover`
are now parsed and aggregated as `Decimal` end-to-end and serialized with
`str()`, never routed through Python `float`, per
`experiments/data/r1_normalized_evidence_contract_v1.json`
(`DailyMarketEvidenceV1.quote_turnover.precision_semantics`: "computed in
source-native decimal precision, not float64"; `.close.precision_semantics`:
"preserve source string precision; no float rounding on ingest").

This follows the row-order/duplicate-identity repair recorded in
tests/test_r1_retention_candidate_repair_v1.py (commit 0edadf3) and repairs
the numeric non-conformance that repair explicitly left open (see
experiments/data/r1_parser_b_conflict_repair_v1.json:known_out_of_scope_findings_still_open).

Canonical counterexample motivating this repair: price="4.35", size="100".
Exact (contract-required) quote_turnover is "435.00". Pre-repair Parser B
computed `float("4.35") * float("100")` = 434.99999999999994 (a wrong,
non-conformant canonical value for a completely ordinary trade -- no exotic
input needed). See experiments/data/r1_parser_b_numeric_conformance_repair_v1.json
for the full counterexample table.

No `math.isclose` / tolerance-based acceptance anywhere in this file: exact
Decimal-string comparison only.
"""

import itertools

from qntylab.r1_retention_candidate import (
    ANOMALY_DUPLICATE_CONFLICTING,
    ANOMALY_DUPLICATE_UNEXPECTED,
    BASE_SCHEMA,
    daily_primitive,
)

CUTOFF = "2026-06-30T23:59:59Z"
RPI_SCHEMA = BASE_SCHEMA + ("RPI",)


def row(ts, side="Buy", size="1.0", price="10.0", tickdir="PlusTick", trdid="a" * 32,
        home=None, foreign=None, gross=None, rpi=None):
    size_f, price_f = float(size), float(price)
    home = home if home is not None else str(size_f)
    foreign = foreign if foreign is not None else str(size_f * price_f)
    gross = gross if gross is not None else str(size_f * price_f * 1e8)
    r = {"timestamp": str(ts), "symbol": "MONUSDT", "side": side, "size": size, "price": price,
         "tickDirection": tickdir, "trdMatchID": trdid, "grossValue": gross,
         "homeNotional": home, "foreignNotional": foreign}
    if rpi is not None:
        r["RPI"] = rpi
    return r


def _primitive(rows, utc_date="2025-07-01", header=BASE_SCHEMA):
    return daily_primitive(stream_id="s", utc_date=utc_date, header=header,
                            rows=rows, historical_cutoff_utc=CUTOFF)


def _json_key(result):
    primitive, anomalies = result
    return (tuple(sorted(primitive.items())), tuple(anomalies))


# 1. exact decimal parsing: source string precision preserved verbatim -------

def test_exact_decimal_parsing_preserves_source_string_precision():
    """20-significant-digit price exceeds float64's ~15-17 digit mantissa;
    float(price_str) is already lossy before any arithmetic. Decimal(price_str)
    is exact."""
    price = "12345.678901234567891"
    primitive, _ = _primitive([row("1751328000.0", price=price, trdid="1" * 32)])
    assert primitive["close"] == price
    assert primitive["open"] == price
    assert primitive["high"] == price
    assert primitive["low"] == price


# 2. exact price * size: no float64 multiplication error --------------------

def test_exact_price_times_size_no_float64_error():
    """price=4.35, size=100: exact decimal product is 435.00. float(4.35) *
    float(100) == 434.99999999999994 (a genuine IEEE-754 binary rounding
    error on ordinary decimal inputs, not an edge case)."""
    primitive, _ = _primitive([row("1751328000.0", price="4.35", size="100", trdid="1" * 32)])
    assert primitive["quote_turnover"] == "435.00"


# 3. exact turnover accumulation across multiple trades ---------------------

def test_exact_turnover_accumulation_across_multiple_trades():
    """0.1 + 0.2 + 0.3 is the textbook non-associative float example:
    float(0.1) + float(0.2) + float(0.3) != 0.6 bit-for-bit (though it can
    happen to *repr* as "0.6"); Decimal("0.1")+Decimal("0.2")+Decimal("0.3")
    is exactly Decimal("0.6")."""
    trades = [
        row("1751328000.0", price="0.1", size="1", trdid="1" * 32),
        row("1751328001.0", price="0.2", size="1", trdid="2" * 32),
        row("1751328002.0", price="0.3", size="1", trdid="3" * 32),
    ]
    primitive, _ = _primitive(trades)
    assert primitive["quote_turnover"] == "0.6"


# 4. large row count accumulation --------------------------------------------

def test_high_row_count_accumulation_exact():
    """1000 rows of price=0.01, size=1: exact sum is 10.00. Bounded synthetic
    fixture (no network/population data)."""
    trades = [row(f"{1751328000 + i}.0", price="0.01", size="1", trdid=f"{i:032d}")
              for i in range(1000)]
    primitive, anomalies = _primitive(trades)
    assert primitive["trade_count"] == 1000
    assert primitive["quote_turnover"] == "10.00"
    assert anomalies == []


# 5. mixture of very large and very small values -----------------------------

def test_mixed_large_and_small_decimal_values_exact():
    big = row("1751328000.0", price="100000000.123456789", size="1", trdid="1" * 32)
    small = row("1751328001.0", price="0.000000001", size="1", trdid="2" * 32)
    primitive, _ = _primitive([big, small])
    assert primitive["quote_turnover"] == "100000000.123456790"


# 6. close serialization preserves trailing precision ------------------------

def test_close_serialization_preserves_trailing_zeros_no_ambiguity():
    """price="1.10" must serialize back as "1.10", never "1.1" or "1" or a
    float repr artifact like "1.1000000000000001" -- the frozen contract
    forbids silently re-encoding a semantically-equivalent-but-differently-
    spelled value unless it explicitly distinguishes them, which it does not
    here (this is a single source string, not two spellings to reconcile)."""
    primitive, _ = _primitive([row("1751328000.0", price="1.10", trdid="1" * 32)])
    assert primitive["close"] == "1.10"


# 7. row reorder invariance, exact ------------------------------------------

def test_row_reorder_invariance_is_exact_not_approximate():
    trades = [
        row("1751328000.0", price="0.1", size="1", trdid="1" * 32),
        row("1751328001.0", price="0.2", size="1", trdid="2" * 32),
        row("1751328002.0", price="4.35", size="100", trdid="3" * 32),
    ]
    forward, anomalies_f = _primitive(trades)
    reverse, anomalies_r = _primitive(list(reversed(trades)))
    assert forward == reverse
    assert anomalies_f == anomalies_r
    assert forward["quote_turnover"] == "435.30"


# 8. equivalent decimal spellings are numerically equal for dedup -----------

def test_equivalent_decimal_spellings_treated_as_same_value_for_duplicate_grouping():
    """Two rows sharing trdMatchID/timestamp/size with price spelled "10" vs
    "10.0" are numerically identical (Decimal("10") == Decimal("10.0")), so
    per the frozen contract's duplicate definition (identical trade
    id/timestamp/price/size) they are an ordinary exact duplicate, not a
    conflict -- string-spelling differences alone must not trigger
    DUPLICATE_CONFLICTING."""
    rows = [row("1751328000.0", trdid="c" * 32, price="10"),
            row("1751328000.0", trdid="c" * 32, price="10.0")]
    primitive, anomalies = _primitive(rows)
    assert primitive["trade_count"] == 1
    assert primitive["duplicate_count"] == 1
    assert ANOMALY_DUPLICATE_UNEXPECTED in anomalies
    assert ANOMALY_DUPLICATE_CONFLICTING not in anomalies


# 9. duplicate handling still correct after numeric repair ------------------

def test_duplicate_handling_still_correct_after_numeric_repair():
    original = row("1751328000.0", trdid="c" * 32, price="4.35", size="100")
    exact_dup = row("1751328000.0", trdid="c" * 32, price="4.35", size="100")
    primitive, anomalies = _primitive([original, exact_dup])
    assert primitive["trade_count"] == 1
    assert primitive["duplicate_count"] == 1
    assert primitive["quote_turnover"] == "435.00"
    assert ANOMALY_DUPLICATE_UNEXPECTED in anomalies
    assert ANOMALY_DUPLICATE_CONFLICTING not in anomalies


# 10. conflicting duplicates still fail closed after numeric repair ---------

def test_conflicting_duplicates_still_fail_closed_after_numeric_repair():
    conflict = [
        row("1751328000.0", trdid="c" * 32, price="4.35", size="100"),
        row("1751328005.0", trdid="c" * 32, price="9.99", size="100"),
    ]
    forward, anomalies_f = _primitive(conflict)
    reverse, anomalies_r = _primitive(list(reversed(conflict)))
    assert forward == reverse
    assert forward["trade_count"] == 0
    assert forward["close"] is None
    assert forward["quote_turnover"] == "0"
    assert forward["rejected_row_count"] == 2
    assert ANOMALY_DUPLICATE_CONFLICTING in anomalies_f
    assert ANOMALY_DUPLICATE_CONFLICTING in anomalies_r


# 11. known old schema (bybit_trade_v1) unaffected by numeric repair --------

def test_known_old_schema_bybit_trade_v1_numeric_fields_are_decimal_strings():
    primitive, anomalies = _primitive(
        [row("1751328000.0", price="4.35", size="100", trdid="1" * 32)], header=BASE_SCHEMA
    )
    assert primitive["schema_id"] == "bybit_trade_v1"
    assert primitive["quote_turnover"] == "435.00"
    assert anomalies == []


# 12. known RPI schema behavior unchanged by numeric repair -----------------

def test_known_rpi_schema_behavior_unchanged_by_numeric_repair():
    r = row("1751328000.0", price="4.35", size="100", trdid="1" * 32, rpi="0")
    primitive, anomalies = _primitive([r], header=RPI_SCHEMA)
    assert primitive["schema_id"] == "bybit_trade_v1_rpi"
    assert primitive["quote_turnover"] == "435.00"
    assert anomalies == []


# 13. zero-trade day: base_volume/quote_turnover are "0", not "0.0" ---------

def test_zero_trade_day_base_volume_and_quote_turnover_are_string_zero():
    """Matches Parser A's _empty_record and the frozen contract's
    missingness_semantics ("0 when trade_count=0") -- canonical zero
    representation, not a float 0.0 nor an arbitrary decimal spelling."""
    beyond_cutoff = row("1751500000.0", price="5", trdid="1" * 32)
    primitive, _ = daily_primitive(stream_id="s", utc_date="2025-07-01", header=BASE_SCHEMA,
                                    rows=[beyond_cutoff], historical_cutoff_utc="2025-07-01T23:59:59Z")
    assert primitive["trade_count"] == 0
    assert primitive["base_volume"] == "0"
    assert primitive["quote_turnover"] == "0"
    assert primitive["close"] is None


# --- property test: exhaustive permutations with precision-sensitive values -

def test_property_precision_sensitive_fixture_invariant_under_all_permutations():
    """Bounded N=4 fixture built from values that are individually adversarial
    to float64 (4.35*100 rounding error; 0.1/0.2 non-associative addition).
    Every one of the 24 permutations must yield the exact same canonical
    result -- not merely a result within tolerance."""
    trades = [
        row("1751328000.0", price="4.35", size="100", trdid="1" * 32),
        row("1751328100.0", price="0.1", size="1", trdid="2" * 32),
        row("1751328200.0", price="0.2", size="1", trdid="3" * 32),
        row("1751328300.0", price="100000000.123456789", size="1", trdid="4" * 32),
    ]
    seen = {_json_key(_primitive(list(perm))) for perm in itertools.permutations(trades)}
    assert len(seen) == 1, f"expected exactly one canonical result across all permutations, got {len(seen)}"

    primitive, anomalies = _primitive(trades)
    assert primitive["trade_count"] == 4
    assert primitive["quote_turnover"] == "100000435.423456789"
    assert anomalies == []
