import copy

from qntylab.r1_identity_model_audit import FALSE_SPLITS, canonical_bytes, refine_domain


def row(symbol, ident, start, *, state="IDENTITY_AMBIGUOUS", end="OPEN_AT_HISTORICAL_CUTOFF", lifecycle="OPEN_AT_CUTOFF_CORROBORATED"):
    return {"instrument_instance_id": ident, "source_candidate_id": f"bybit|{symbol}|linearperpetual", "symbol": symbol, "base": symbol.removesuffix("USDT"), "quote": "USDT", "contract_type": "LinearPerpetual", "lineage": "x", "start_time": start, "start_state": "FIRST_CAUSAL_TRADABILITY_EVIDENCE", "end_time": None, "end_state": end, "identity_state": state, "lifecycle_state": lifecycle, "evidence_references": ["tardis_catalog"], "ambiguity_reasons": [], "temporal": {}}


def frozen(rows):
    return {"artifact": "old", "cutoff_utc": "2026-06-30T23:59:59Z", "candidate_population_count": len(rows) // 2,
            "accounted_candidate_count": len(rows) // 2, "candidate_accounting": [{"source_candidate_id": r["source_candidate_id"], "instance_ids": [r["instrument_instance_id"]]} for r in rows[::2]], "instances": rows}


def test_source_timestamp_difference_merges_without_affirmative_reuse():
    old = frozen([row("ETHUSDT", "old", "2020-01-01T00:00:00Z"), row("ETHUSDT", "new", "2021-01-01T00:00:00Z")])
    refined = refine_domain(old)
    assert len(refined["instances"]) == 1
    assert refined["instances"][0]["identity_state"] == "SINGLE_IDENTITY_NO_AFFIRMATIVE_DISCONTINUITY"


def test_affirmative_mon_reuse_stays_split_but_prior_terminal_is_not_invented():
    old = frozen([row("MONUSDT", "old", "2024-01-01T00:00:00Z"), row("MONUSDT", "new", "2025-01-01T00:00:00Z")])
    refined = refine_domain(old)
    assert len(refined["instances"]) == 2
    assert any(r["end_state"] == "AMBIGUOUS_TERMINAL" for r in refined["instances"])


def test_refinement_is_input_order_invariant_and_canonical():
    old = frozen([row("ETHUSDT", "old", "2020-01-01T00:00:00Z"), row("ETHUSDT", "new", "2021-01-01T00:00:00Z")])
    assert canonical_bytes(refine_domain(old)) == canonical_bytes(refine_domain(copy.deepcopy(old)))
    assert "ETHUSDT" in FALSE_SPLITS
