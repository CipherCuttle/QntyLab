from qntylab.jigsaw_fast_prospective_signal_discovery_input_feasibility_v0 import load, validate

def test_feasibility_authority_validates():
    validate()

def test_exact_frozen_batch_and_denominators():
    x = load()
    assert x["canonical_finalist_ids"] == ["JFPV1_02", "JFPV1_03", "JFPV1_04", "JFPV1_05", "JFPV1_10"]
    assert x["exploratory_denominator"] == 10
    assert x["confirmatory_family_size"] == 5

def test_blocked_batch_cannot_open_materialization_or_science():
    x = load()
    assert x["ready_finalist_count"] == 0
    assert all(value is False for key, value in x["authority"].items() if isinstance(value, bool))
    assert x["authority"]["capital_authority"] == "NONE"

def test_rds_panel_is_exact_and_btc_absence_is_explicit():
    x = load()
    assert len(x["rds_forensics"]["panel_symbols"]) == 20
    assert "BTCUSDT" not in x["rds_forensics"]["panel_symbols"]
    assert all(row["input_status"] == "BLOCKED_INPUT_CONTRACT" for row in x["finalist_feasibility"])
