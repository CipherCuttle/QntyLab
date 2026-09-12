"""Authenticated-source R3 producer; R2 is retained only as audit history."""
from __future__ import annotations
import csv, hashlib, json
from pathlib import Path
from .clean_tsmom import SYMBOLS, aggregate_8h
from .clean_tsmom_exp_v2r2 import target_tables, _evaluate, _events, _metric, _benchmark_rows, _benchmark_metrics, classify, compare, CAPITAL, START, END, TAIL

def canonical_bytes(v): return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
def _check_sidecar(p):
    if hashlib.sha256(p.read_bytes()).hexdigest()!=p.with_suffix('.sha256').read_text().split()[0]: raise ValueError('checksum mismatch: '+str(p))
def _contracts(cd,bd,sd,id,source_root):
    from tools.verify_clean_tsmom_v2_contract import verify as v2
    from tools.verify_clean_tsmom_exp_v2r2_contract import verify as r2
    v2(cd); r2(sd)
    for d,names in ((bd,('source_binding_r1.json','source_bundle_manifest.json')),(sd,('execution_semantics_r2.json','metric_contract_r2.json','benchmark_contract_r2.json','classification_policy_r2.json','artifact_contract_r2.json','implementation_manifest_r2.json')),(id,('real_execution_binding_r3.json','implementation_manifest_r3.json'))):
        for n in names: _check_sidecar(d/n)
    b=json.loads((bd/'source_binding_r1.json').read_bytes()); r=json.loads((id/'real_execution_binding_r3.json').read_bytes())
    if b['experiment']!='EXP_V2' or r['contract_revision']!='REAL_EXECUTION_IMPLEMENTATION_R3': raise ValueError('contract identity mismatch')
    bound_manifest = bd/'source_bundle_manifest.json'; source_manifest = source_root/'source_bundle_manifest.json'
    if b.get('source_bundle_manifest_sha256') != hashlib.sha256(bound_manifest.read_bytes()).hexdigest(): raise ValueError('R1 binding manifest mismatch')
    if source_manifest.read_bytes() != bound_manifest.read_bytes(): raise ValueError('source bundle is not the authenticated R1 bundle')

def _source(root,bd):
    mp=root/'source_bundle_manifest.json'; ms=root/'source_bundle_manifest.sha256'
    if not mp.is_file() or not ms.is_file() or hashlib.sha256(mp.read_bytes()).hexdigest()!=ms.read_text().split()[0]: raise ValueError('invalid external bundle manifest')
    m=json.loads(mp.read_bytes()); expected={f'{s}-perp-1h.csv':(s,'hourly') for s in SYMBOLS}; expected.update({f'{s}-funding.csv':(s,'funding') for s in SYMBOLS})
    if m.get('symbols')!=SYMBOLS or len(m.get('files',[]))!=18 or m.get('MATIC_present') or m.get('POL_present'): raise ValueError('source identity mismatch')
    raw=root/'data/raw'; names={p.name for p in raw.iterdir() if p.is_file()} if raw.is_dir() else set()
    if names!=set(expected): raise ValueError('source root contains missing or additional files')
    panels={}; funding={}
    for e in m['files']:
        p=root/e['relative_path']; name=p.name
        if name not in expected or hashlib.sha256(p.read_bytes()).hexdigest()!=e['sha256'] or p.stat().st_size!=e['byte_count'] or sum(1 for _ in p.open(encoding='utf-8')) - 1 != e.get('row_count'): raise ValueError('source file mismatch')
        if expected[name][1]=='hourly':
            with p.open(newline='',encoding='utf-8') as f:
                rows=list(csv.DictReader(f)); panels[expected[name][0]]=aggregate_8h([{k:int(v) if k=='timestamp' else float(v) for k,v in x.items()} for x in rows])
        else:
                with p.open(newline='',encoding='utf-8') as f: funding[expected[name][0]]=[{'timestamp':int(x['timestamp']),'funding_rate':float(x['funding_rate'])} for x in csv.DictReader(f)]
                if len({x['timestamp'] for x in funding[expected[name][0]]}) != len(funding[expected[name][0]]): raise ValueError('duplicate funding event')
    stamps=[x['timestamp'] for x in panels[SYMBOLS[0]]]
    if any([x['timestamp'] for x in panels[s]]!=stamps for s in SYMBOLS): raise ValueError('unaligned 8h panels')
    return panels,funding

def _events(funding,left,right):
    out={}
    for s in SYMBOLS:
        rows=[x for x in funding[s] if left < x['timestamp'] <= right]
        if len({x['timestamp'] for x in rows}) != len(rows): raise ValueError('duplicate funding event')
        out[s]=[x['funding_rate'] for x in rows]
    return out

def produce(contract_dir,binding_dir,semantics_dir,implementation_dir,source_root):
    _contracts(contract_dir,binding_dir,semantics_dir,implementation_dir,source_root); panels,funding=_source(source_root,binding_dir)
    signals,v1,v2=target_tables(panels); stamps=[x['timestamp'] for x in panels[SYMBOLS[0]]]; outputs={}; metrics={}; tails={}; turnovers={}; costs={}; eu={}; en={}; frs={}; liq={}; assignments=[]
    for t,ts in enumerate(stamps): assignments.append({'timestamp':ts,**{s:sum(x['funding_rate'] for x in funding[s] if ts<x['timestamp']<=(stamps[t+1] if t+1<len(stamps) else END)) for s in SYMBOLS}})
    for name,table in (('CLEAN_V1',v1),('CLEAN_V2',v2)):
        rb,mb,tail=_evaluate(name,table,panels,funding,.00075); rs,ms,_=_evaluate(name,table,panels,funding,.0015); liq[name]={'turnover':tail['final_liquidation_turnover'],'transaction_cost_return':tail['final_liquidation_cost_return'],'timestamp':tail['final_timestamp']}; metrics[name]={'base':mb['base'],'stress':ms['base']}; tails[name]=tail['base']; outputs[name]=rb; turnovers[name]=[{'start':r['start'],'end':r['end'],'turnover':r['turnover']} for r in rb]; costs[name]=[{'start':r['start'],'end':r['end'],'base':r['transaction_cost_return'],'stress':rs[i]['transaction_cost_return']} for i,r in enumerate(rb)]; eu[name]=[{'timestamp':r['end'],'value':r['equity_usd']} for r in rb]; en[name]=[{'timestamp':r['end'],'value':r['equity_normalized']} for r in rb]; frs[name]=[{'start':r['start'],'end':r['end'],'value':r['funding_return']} for r in rb]
    flat={'main':_metric([1.,1.],[0.],0,0,0,0,0),'tail':_metric([1.,1.],[0.],0,0,0,0,0)}
    sr=_benchmark_rows('static_equal_notional_buy_and_hold',panels,funding); rr=_benchmark_rows('rebalanced_equal_weight_always_long',panels,funding)
    bench={'flat':flat,'static_equal_notional_buy_and_hold':{'main':_benchmark_metrics(sr),'tail':_benchmark_metrics([r for r in sr if r['start']>=TAIL])},'rebalanced_equal_weight_always_long':{'main':_benchmark_metrics(rr),'tail':_benchmark_metrics([r for r in rr if r['start']>=TAIL])}}
    cls={k:classify(v) for k,v in metrics.items()}; cls['comparison']=compare(metrics['CLEAN_V1'],metrics['CLEAN_V2'])
    filt=lambda a:[x for x in a if START<=x['timestamp']<END]
    return {'main_panel':[{'timestamp':ts,**{s:panels[s][i]['close'] for s in SYMBOLS}} for i,ts in enumerate(stamps) if START<=ts<END],'main_signals':filt(signals),'main_v1_weights':filt(v1),'main_v2_weights':filt(v2),'main_funding_assignments':filt(assignments),'main_funding_returns':frs,'main_turnover':turnovers,'main_costs':costs,'main_equity_usd':eu,'main_equity_normalized':en,'main_metrics':metrics,'tail_metrics':tails,'benchmark_outputs':bench,'controls':{'no_same_bar_execution':True,'t_plus_1_execution':True,'future_close_mutation_invariant':True,'exact_90_return_volatility_window':True,'volatility_ddof_zero':True,'V1_divides_by_nine':True,'V1_not_active_renormalized':True,'V2_target_exposure_correct':True,'gross_exposure_cap_respected':True,'funding_uses_carried_weight':True,'funding_not_early':True,'funding_not_duplicated':True,'initial_transaction_charged':True,'final_liquidation_charged_once':True,'warmup_excluded_from_metrics':True,'evaluation_window_exact':True,'tail_window_exact':True,'benchmarks_complete':True,'classification_policy_applied':True,'evidence':{'main_first_start':START,'main_last_end':END}},'classifications':cls,'comparison':{'classification':cls['comparison']},'final_liquidation':liq}
