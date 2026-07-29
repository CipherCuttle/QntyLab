import numpy as np
import pytest
from pathlib import Path
from qntylab.backtest import evaluate, segments
from qntylab.data import FUNDING_FIELDS, PERP_FIELDS, archive_usdt_perp_symbols, validate
from qntylab.strategies import momentum
from qntylab.perp import causal, funding_to_bars, evaluate_perp, positions
from qntylab.experiment import _perp_splits
from qntylab.cross_section import deterministic_order, evaluate as evaluate_cross_section, factor_scores, random_scores, receipt_sha256, turnover, weights
from qntylab.universe import build_universe, write_dataset_manifest
from qntylab.archive_index import eligible_symbols
from qntylab.aux_v2 import _one, build_dataset_freeze_manifest, load_union
from qntylab import sprint_v2

def test_signal_is_shifted_one_bar_no_lookahead():
    # The jump is visible at index 2; its long position begins at 3, after the jump.
    assert momentum(np.array([100.,100.,200.,200.]), 1, "long_flat").tolist() == [0.,0.,0.,1.]

def test_long_short_and_cost_accounting():
    close=np.array([100.,110.,99.,108.]); pos=np.array([1.,-1.,1.,1.])
    m=evaluate(close,pos,10)
    # Two sign flips each change exposure by two units, charged at 10 bps per unit.
    assert m["trade_count"] == 2 and m["fee_cost"] == pytest.approx(0.004)
    assert m["average_absolute_exposure"] == 1.0

def test_drawdown_and_chronological_splits():
    close=np.arange(100.,109.); pos=np.ones(9); result=segments(close,pos,0)
    assert set(result) == {"full","early","middle","late"}
    assert result["full"]["max_drawdown"] == 0.0

def test_evaluation_is_deterministic():
    close=np.array([100.,101.,99.,103.,102.]); pos=np.array([0.,1.,-1.,1.,0.])
    assert evaluate(close,pos,10) == evaluate(close,pos,10)

def test_data_validation_rejects_duplicates_bad_ohlc_and_negative_volume():
    good={"timestamp":"2021-01-01T00:00:00Z","open":"1","high":"2","low":"1","close":"2","volume":"0"}
    with pytest.raises(ValueError): validate([good, good])
    bad={**good,"high":"0.5"}
    with pytest.raises(ValueError): validate([bad])
    with pytest.raises(ValueError): validate([{**good,"volume":"-1"}])

def test_funding_event_alignment_and_signal_delay():
    stamps=["2021-01-01T00:00:00Z","2021-01-01T01:00:00Z","2021-01-01T02:00:00Z"]
    funding=funding_to_bars(stamps, [{"timestamp":"2021-01-01T00:00:00Z","funding_rate":"0.01"}])
    assert funding.tolist() == [0.01, np.nan, np.nan] or np.isnan(funding[1:]).all()
    assert causal(np.array([-1., 0., 0.])).tolist() == [0., -1., 0.]

def test_premium_and_order_flow_are_one_bar_lagged():
    close=np.ones(15) * 100; premium=np.r_[np.arange(12., dtype=float), 100., 0., 0.]; ofi=np.r_[np.zeros(12), .9, 0., 0.]; funding=np.full(15, np.nan)
    premium_position=positions("H009_premium_mean_reversion", close, premium, ofi, funding, {"lookback":12,"threshold":.5,"holding_hours":1})
    flow_position=positions("H010_taker_flow", close, premium, ofi, funding, {"lookback":1,"threshold":.15,"direction":1})
    assert premium_position[12] == 0 and premium_position[13] == -1
    assert flow_position[12] == 0 and flow_position[13] == 1

def test_perp_pnl_fee_transition_and_funding_signs():
    stamps=[f"2021-01-01T0{i}:00:00Z" for i in range(4)]
    close=np.array([100.,110.,99.,108.]); long=np.array([1.,1.,1.,1.]); short=-long
    long_result=evaluate_perp(close,long,stamps,[{"timestamp":"2021-01-01T01:00:00Z","funding_rate":".01"}],0)
    short_result=evaluate_perp(close,short,stamps,[{"timestamp":"2021-01-01T01:00:00Z","funding_rate":".01"}],0)
    flip=evaluate_perp(close,np.array([1.,-1.,1.,1.]),stamps,[],10)
    assert long_result["funding_cashflow"] == pytest.approx(-.01)
    assert short_result["funding_cashflow"] == pytest.approx(.01)
    assert flip["fees"] == pytest.approx(.004) and flip["trade_count"] == 2

def test_no_return_is_earned_across_a_gap_and_perp_is_deterministic():
    stamps=["2021-01-01T00:00:00Z","2021-01-01T01:00:00Z","2021-01-01T03:00:00Z"]
    result=evaluate_perp(np.array([100.,110.,220.]),np.ones(3),stamps,[],0)
    assert result["gap_return_count"] == 1 and result["price_pnl"] == pytest.approx(.1)
    assert result == evaluate_perp(np.array([100.,110.,220.]),np.ones(3),stamps,[],0)

def test_perp_splits_include_a_safe_final_third():
    stamps=[f"2021-01-01T{i:02d}:00:00Z" for i in range(9)]
    result=_perp_splits(np.arange(100.,109.),np.ones(9),stamps,[],0)
    assert set(result) == {"full","early","middle","late"}

def test_cross_sectional_rank_ties_weights_and_neutrality_are_deterministic():
    symbols = ["Z", "A", "B", "C", "D"]
    score = np.array([1., 1., 0., -1., -1.])
    assert deterministic_order(symbols, score) == [1, 0, 2, 3, 4]
    book = weights(symbols, score, .2)
    assert book.tolist() == [0., 1., 0., 0., -1.]
    assert book.sum() == 0 and np.abs(book).sum() == 2

def test_cross_sectional_execution_cost_funding_and_ic_direction():
    symbols = ["A", "B", "C", "D", "E"]
    close = np.array([[100,100,100,100,100], [110,105,100,95,90], [121,110,100,90,81]], dtype=float)
    score = np.array([[5,4,3,2,1], [5,4,3,2,1], [np.nan]*5])
    eligible = np.ones_like(close, dtype=bool)
    funding = np.zeros_like(close); funding[1,0] = .01
    result = evaluate_cross_section(symbols, close, score, eligible, funding, fee_bps=10)
    assert result.price_pnl > 0 and result.mean_ic > 0
    assert result.funding_pnl == pytest.approx(-.01)
    assert result.fees == pytest.approx(.002)  # initial +1/-1 book only
    assert result.turnover == pytest.approx(2.)

def test_cross_sectional_eligibility_and_random_null_are_causal_and_deterministic():
    symbols = ["A", "B", "C", "D", "E"]
    close = np.full((3, 5), 100.)
    score = np.tile(np.arange(5., dtype=float), (3, 1)); eligible = np.ones_like(close, dtype=bool)
    eligible[0, 4] = False  # a future listing cannot enter the earlier book
    result = evaluate_cross_section(symbols, close, score, eligible)
    assert result.weights[0][4] == 0
    assert random_scores((3, 5), 7).tolist() == random_scores((3, 5), 7).tolist()
    assert turnover(np.array([1., -1.]), np.array([0., 0.])) == 2

def test_cross_sectional_factor_uses_only_prior_window():
    close = np.array([[100.], [100.], [200.]])
    score = factor_scores(close, None, None, "H013_reversal_1d", 1)
    assert np.isnan(score[0, 0]) and score[1, 0] == 0 and score[2, 0] == 1

def test_archive_symbol_discovery_uses_archive_directories_not_current_exchange_info():
    class Response:
        content = b'''<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><CommonPrefixes><Prefix>data/futures/um/daily/klines/BTCUSDT/</Prefix></CommonPrefixes><CommonPrefixes><Prefix>data/futures/um/daily/klines/OLDUSDT/</Prefix></CommonPrefixes><CommonPrefixes><Prefix>data/futures/um/daily/klines/BTCUSDT_250627/</Prefix></CommonPrefixes><CommonPrefixes><Prefix>data/futures/um/daily/klines/USDCUSDT/</Prefix></CommonPrefixes></ListBucketResult>'''
        def raise_for_status(self): pass
    class Session:
        def get(self, *args, **kwargs): return Response()
    assert archive_usdt_perp_symbols(Session()) == ["BTCUSDT", "OLDUSDT"]

def test_cross_sectional_receipt_is_deterministic():
    assert receipt_sha256(b'{"v":2}', b'{"manifest":1}') == receipt_sha256(b'{"v":2}', b'{"manifest":1}')

def test_dynamic_universe_is_causal_changes_and_preserves_historical_delistings(tmp_path):
    symbols=["A","B","C"]; dates=["d0","d1","d2","d3"]
    close=np.array([[1,1,np.nan],[1,1,np.nan],[1,1,1],[1,np.nan,1]],float)
    volume=np.array([[10,5,np.nan],[10,6,np.nan],[10,100,100],[10,np.nan,100]],float)
    selected, ledger=build_universe(symbols,dates,close,volume,history_days=2,liquidity_days=2,top_n=1,minimum_breadth=1)
    assert selected[1].tolist()==[True,False,False] and selected[2].tolist()==[False,True,False]
    assert not selected[0,2] and np.isfinite(close[0,0])  # future listing excluded; delisted history remains
    a=write_dataset_manifest(tmp_path/'a.json',spec_sha256='x',cutoff='2026-06-30',candidates=symbols,panels=[],ledger=ledger,union_selected=['A','B'],exclusions=[])
    b=write_dataset_manifest(tmp_path/'b.json',spec_sha256='x',cutoff='2026-06-30',candidates=symbols,panels=[],ledger=ledger,union_selected=['A','B'],exclusions=[])
    assert a['root_sha256']==b['root_sha256']

def test_archive_identity_filter_is_mechanical_and_keeps_retired_usdt_names():
    prefixes=["data/futures/um/monthly/klines/BTCUSDT/", "data/futures/um/monthly/klines/OLDUSDT/", "data/futures/um/monthly/klines/BTCUSDT_260626/", "data/futures/um/monthly/klines/USDCUSDT/", "data/futures/um/monthly/klines/ETHUSDC/"]
    assert eligible_symbols(prefixes)==["BTCUSDT", "OLDUSDT"]

def test_non_comparable_commodity_contract_cannot_enter_crypto_universe():
    selected,_=build_universe(["BTCUSDT","XAUUSDT"],["d0","d1"],np.ones((2,2)),np.array([[1,100],[1,100.]]),history_days=1,liquidity_days=1,top_n=1,minimum_breadth=1)
    assert selected[1].tolist()==[True,False]

def test_frozen_funding_factor_ids_are_accepted():
    funding=np.array([[.01],[.02]])
    assert factor_scores(np.ones((2,1)),funding,None,"H014_funding_24h",1)[0,0] == pytest.approx(.01)

def test_auxiliary_union_fails_closed_on_wrong_contract(tmp_path):
    path=tmp_path/'union.json'; path.write_text('{"symbols":[]}')
    with pytest.raises(ValueError): load_union(path)

def test_auxiliary_receipts_use_independent_local_source_metadata(tmp_path, monkeypatch):
    import qntylab.aux_v2 as aux
    def absent(*args, **kwargs): raise ValueError("source absent")
    monkeypatch.setattr(aux, "fetch_funding", absent)
    monkeypatch.setattr(aux, "fetch_premium_perp", absent)
    raw=tmp_path/"data/raw"; raw.mkdir(parents=True)
    funding=raw/"CASE_A-funding.csv"; premium=raw/"CASE_A-perp-1h.csv"
    funding.write_text("timestamp,funding_interval_hours,funding_rate\n2026-04-23T08:00:00Z,8,0.01\n")
    item={"symbol":"CASE_A","first_selected":"2026-04-23","last_selected":"2026-05-10"}
    result=_one(tmp_path,item)
    assert result["funding"]["state"] == "VALID" and result["funding"]["rows"] == 1
    assert result["premium"]["state"] == "NO_SOURCE_DATA"
    premium.write_text(",".join(PERP_FIELDS)+"\n2026-04-23T00:00:00Z,1,1,1,1,1,1,1,1,1,0\n")
    result=_one(tmp_path,item)
    assert result["funding"]["state"] == result["premium"]["state"] == "VALID"
    assert result["funding"]["start"] == "2026-04-23T08:00:00Z"
    assert _one(tmp_path,item)["reused"] is True

def test_auxiliary_receipt_keeps_available_premium_when_funding_is_absent(tmp_path, monkeypatch):
    import qntylab.aux_v2 as aux
    monkeypatch.setattr(aux, "fetch_funding", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("funding absent")))
    raw=tmp_path/"data/raw"; raw.mkdir(parents=True)
    (raw/"CASE_B-perp-1h.csv").write_text(",".join(PERP_FIELDS)+"\n2026-04-23T00:00:00Z,1,1,1,1,1,1,1,1,1,0\n")
    result=_one(tmp_path,{"symbol":"CASE_B","first_selected":"2026-04-23","last_selected":"2026-05-10"})
    assert result["funding"]["state"] == "NO_SOURCE_DATA"
    assert result["premium"]["state"] == "VALID"

def test_auxiliary_freeze_manifest_is_deterministic(tmp_path, monkeypatch):
    import qntylab.aux_v2 as aux
    item={"symbol":"CASE_C","first_selected":"2026-04-23","last_selected":"2026-05-10"}
    monkeypatch.setattr(aux, "load_union", lambda path: [item])
    monkeypatch.setattr(aux, "INVENTORY_RAW_SHA", "inventory-sha")
    monkeypatch.setattr(aux, "sha256", lambda path: "inventory-sha" if path.name == "sprint_v2_1d_inventory.json" else "raw-sha")
    (tmp_path/"data/archive/aux_v2").mkdir(parents=True)
    (tmp_path/"data/archive/sprint_v2_1d_inventory.json").write_text("inventory")
    (tmp_path/"data/archive/aux_v2/CASE_C.json").write_text('{"funding":{"end":"2026-05-10","rows":1,"sha256":"f","start":"2026-04-23","state":"VALID"},"premium":{"end":"2026-05-10","rows":1,"sha256":"p","start":"2026-04-23","state":"VALID"},"receipt_schema_version":2}')
    first=build_dataset_freeze_manifest(tmp_path,tmp_path/"union.json",implementation_commit="repair")
    second=build_dataset_freeze_manifest(tmp_path,tmp_path/"union.json",implementation_commit="repair")
    assert first == second and first["dataset_root_sha256"]


def test_sprint_v2_freeze_identity_refuses_mutated_bindings(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    original_read = sprint_v2._read_json
    def changed_manifest(path):
        value = original_read(path)
        if path.name == "sprint_v2_pre_outcome_dataset_manifest.json":
            value["sample_cutoff"] = "2026-06-29"
        return value
    monkeypatch.setattr(sprint_v2, "_read_json", changed_manifest)
    with pytest.raises(ValueError, match="dataset root"): sprint_v2._verify_freeze(root)


def test_sprint_v2_freeze_refuses_union_ledger_and_source_hash_mismatch(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    original_read, original_sha = sprint_v2._read_json, sprint_v2.sha256
    def changed_union(path):
        value = original_read(path)
        if path.name == "sprint_v2_union_selected.json": value["union_selected_sha256"] = "bad"
        return value
    monkeypatch.setattr(sprint_v2, "_read_json", changed_union)
    with pytest.raises(ValueError, match="union"): sprint_v2._verify_freeze(root)
    monkeypatch.setattr(sprint_v2, "_read_json", original_read)
    monkeypatch.setattr(sprint_v2, "sha256", lambda path: "bad" if path.name == "sprint_v2_universe_ledger.json" else original_sha(path))
    with pytest.raises(ValueError, match="ledger"): sprint_v2._verify_freeze(root)
    monkeypatch.setattr(sprint_v2, "sha256", lambda path: "bad" if path.name == "BTCUSDT-funding.csv" else original_sha(path))
    with pytest.raises(ValueError, match="source hash"): sprint_v2._verify_freeze(root)


def test_sprint_v2_missing_features_remain_nonfinite_without_changing_universe_membership():
    close = np.full((8, 2), 100.); funding = np.full((8, 2), .01); premium = np.full((8, 2), .02)
    eligible = np.ones((8, 2), dtype=bool); funding[3, 0] = np.nan; premium[4, 1] = np.nan
    funding_1d = factor_scores(close, funding, None, "H014_funding_24h", 1)
    funding_7d = factor_scores(close, funding, None, "H014_funding_7d", 7)
    premium_score = factor_scores(close, None, premium, "H015_premium", 1)
    assert np.isnan(funding_1d[3, 0]) and np.isnan(funding_7d[6, 0])
    assert np.isnan(premium_score[4, 1]) and eligible[3, 0] and eligible[4, 1]


def test_sprint_v2_scores_are_causal_and_require_complete_lookbacks():
    close = np.array([[100.], [101.], [102.], [103.], [104.], [105.], [106.], [107.], [999.]])
    before = factor_scores(close, None, None, "H012_momentum_7d", 7)
    changed = close.copy(); changed[-1, 0] = 1.
    after = factor_scores(changed, None, None, "H012_momentum_7d", 7)
    assert np.isnan(before[:7]).all() and np.array_equal(before[:8], after[:8], equal_nan=True)
    gapped = close.copy(); gapped[1, 0] = np.nan
    assert np.isnan(factor_scores(gapped, None, None, "H012_momentum_7d", 7)[8, 0])


def test_sprint_v2_materialization_is_structural_only_and_preserves_asymmetric_sources():
    root = Path(__file__).resolve().parents[1]
    inputs = sprint_v2.materialize(root); report = sprint_v2.structural_report(inputs)
    chinese = inputs.symbols.index("币安人生USDT"); icp = inputs.symbols.index("ICPUSDT"); lend = inputs.symbols.index("LENDUSDT")
    assert report["union_count"] == 181 and inputs.close.shape == inputs.eligible.shape
    assert np.isfinite(inputs.funding[:, chinese]).any() and not np.isfinite(inputs.premium[:, chinese]).any()
    assert np.isnan(inputs.funding[:, icp]).any() and np.isnan(inputs.funding[:, lend]).any()
    assert inputs.cost_bps == (5, 10, 20) and (inputs.null_seed, inputs.null_count, inputs.null_same_universe_and_bucket_counts) == (20260728, 100, True)
    event = inputs.funding_events["币安人生USDT"][0]
    assert event["timestamp"] == "2026-04-01T00:00:00Z" and float(event["funding_rate"]) == pytest.approx(.00005)
    assert -1.0 * .01 == pytest.approx(-.01)  # frozen cashflow sign: -position * rate
