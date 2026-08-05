"""Independent R3 result verifier.

This file intentionally contains no import of either R2/R3 producer. It
authenticates the external source and checks producer artifacts independently.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,sys
import math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qntylab.clean_tsmom import aggregate_8h
SYMBOLS=["BTCUSDT","ETHUSDT","XRPUSDT","LINKUSDT","DOTUSDT","BNBUSDT","ADAUSDT","SOLUSDT","AVAXUSDT"]
NAMES=("main_panel","main_signals","main_v1_weights","main_v2_weights","main_funding_assignments","main_funding_returns","main_turnover","main_costs","main_equity_usd","main_equity_normalized","main_metrics","tail_metrics","benchmark_outputs","controls","classifications","comparison","final_liquidation")
def canonical(v): return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def _source(root):
    mp=root/'source_bundle_manifest.json'; ms=root/'source_bundle_manifest.sha256'
    if not mp.is_file() or digest(mp)!=ms.read_text().split()[0]: raise ValueError('source manifest authentication failure')
    m=json.loads(mp.read_bytes()); raw=root/'data/raw'; expected={f'{s}-perp-1h.csv' for s in SYMBOLS}|{f'{s}-funding.csv' for s in SYMBOLS}
    if m.get('symbols')!=SYMBOLS or {p.name for p in raw.iterdir() if p.is_file()}!=expected: raise ValueError('source bundle identity failure')
    for e in m['files']:
        p=root/e['relative_path']
        if digest(p)!=e['sha256'] or p.stat().st_size!=e['byte_count'] or sum(1 for _ in p.open(encoding='utf-8')) - 1 != e.get('row_count'): raise ValueError('source byte mismatch')
    panels={}; funding={}
    for s in SYMBOLS:
        hp=raw/(s+'-perp-1h.csv'); fp=raw/(s+'-funding.csv')
        with hp.open(newline='',encoding='utf-8') as f: panels[s]=aggregate_8h([{k:int(v) if k=='timestamp' else float(v) for k,v in x.items()} for x in csv.DictReader(f)])
        with fp.open(newline='',encoding='utf-8') as f: funding[s]=[{'timestamp':int(x['timestamp']),'funding_rate':float(x['funding_rate'])} for x in csv.DictReader(f)]
        if len({x['timestamp'] for x in funding[s]}) != len(funding[s]): raise ValueError('duplicate funding event')
    stamps=[x['timestamp'] for x in panels[SYMBOLS[0]]]
    if any([x['timestamp'] for x in panels[s]]!=stamps for s in SYMBOLS): raise ValueError('unaligned source panel')
    return m,panels,funding
def _independent_targets(panels):
    close={s:[float(x['close']) for x in panels[s]] for s in SYMBOLS}; stamps=[x['timestamp'] for x in panels[SYMBOLS[0]]]; sig=[]; v1=[]; v2=[]
    for t,ts in enumerate(stamps):
        q={s:int(t>=20 and math.log(close[s][t]/close[s][t-20])>0) for s in SYMBOLS}; sig.append({'timestamp':ts,**q}); v1.append({'timestamp':ts,**{s:q[s]/9 for s in SYMBOLS}})
        eligible={}
        if t>=90:
            for s in SYMBOLS:
                rr=[math.log(close[s][j]/close[s][j-1]) for j in range(t-89,t+1)]; mean=sum(rr)/len(rr); sd=math.sqrt(sum((x-mean)**2 for x in rr)/len(rr))
                if q[s] and sd>0 and math.isfinite(sd): eligible[s]=sd
        gross=len(eligible)/9; den=sum(1/x for x in eligible.values()) if eligible else 1
        v2.append({'timestamp':ts,**{s:(gross/eligible[s]/den if s in eligible else 0.) for s in SYMBOLS}})
    return sig,v1,v2
def _assert_equal(label,actual,expected,tol=1e-12):
    if isinstance(expected,dict):
        if set(actual)!=set(expected): raise ValueError('independent mismatch '+label)
        for k in expected: _assert_equal(label+'.'+str(k),actual[k],expected[k],tol)
    elif isinstance(expected,list):
        if len(actual)!=len(expected): raise ValueError('independent mismatch '+label)
        for i,(a,e) in enumerate(zip(actual,expected)): _assert_equal(label+'['+str(i)+']',a,e,tol)
    elif isinstance(expected,(int,float)) and isinstance(actual,(int,float)):
        if abs(float(actual)-float(expected))>tol: raise ValueError('independent mismatch '+label)
    elif actual!=expected: raise ValueError('independent mismatch '+label)
def _artifacts(root):
    manifest=json.loads((root/'artifact_manifest.json').read_bytes())
    for n in NAMES:
        p=root/(n+'.json')
        if not p.is_file() or p.read_bytes()!=canonical(json.loads(p.read_bytes())): raise ValueError('invalid artifact '+n)
        if manifest['files'][n+'.json']['sha256']!=digest(p): raise ValueError('artifact identity mismatch '+n)
    return {n:json.loads((root/(n+'.json')).read_bytes()) for n in NAMES}
def main():
    ap=argparse.ArgumentParser()
    for n in ('contract-dir','binding-dir','semantics-dir','implementation-dir','source-root','producer-root','output-dir'): ap.add_argument('--'+n,dest=n.replace('-','_'),type=Path,required=True)
    a=ap.parse_args()
    if a.output_dir.exists() and any(a.output_dir.iterdir()): raise ValueError('output directory must be empty')
    from tools.verify_clean_tsmom_v2_contract import verify as verify_v2
    from tools.verify_clean_tsmom_exp_v2r2_contract import verify as verify_r2
    verify_v2(a.contract_dir); verify_r2(a.semantics_dir)
    for d,names in ((a.binding_dir,('source_binding_r1.json','source_bundle_manifest.json')),(a.implementation_dir,('real_execution_binding_r3.json','implementation_manifest_r3.json'))):
        for n in names:
            p=d/n; side=p.with_suffix('.sha256')
            if not p.is_file() or digest(p)!=side.read_text().split()[0]: raise ValueError('contract sidecar mismatch '+n)
    binding_manifest = a.binding_dir/'source_bundle_manifest.json'
    binding = json.loads((a.binding_dir/'source_binding_r1.json').read_bytes())
    if binding.get('source_bundle_manifest_sha256') != digest(binding_manifest): raise ValueError('R1 binding manifest mismatch')
    if binding_manifest.read_bytes() != (a.source_root/'source_bundle_manifest.json').read_bytes(): raise ValueError('source bundle is not the authenticated R1 bundle')
    _,panels,funding=_source(a.source_root); actual=_artifacts(a.producer_root); sig,v1,v2=_independent_targets(panels); stamps=[x['timestamp'] for x in panels[SYMBOLS[0]]]
    filt=lambda xs:[x for x in xs if 1776902400000<=x['timestamp']<1785542400000]
    _assert_equal('main_panel',actual['main_panel'],[{'timestamp':ts,**{s:panels[s][i]['close'] for s in SYMBOLS}} for i,ts in enumerate(stamps) if 1776902400000<=ts<1785542400000])
    _assert_equal('main_signals',actual['main_signals'],filt(sig)); _assert_equal('main_v1_weights',actual['main_v1_weights'],filt(v1)); _assert_equal('main_v2_weights',actual['main_v2_weights'],filt(v2))
    assignments=[{'timestamp':ts,**{s:sum(x['funding_rate'] for x in funding[s] if ts<x['timestamp']<=(stamps[t+1] if t+1<len(stamps) else 1785542400000)) for s in SYMBOLS}} for t,ts in enumerate(stamps)]
    _assert_equal('main_funding_assignments',actual['main_funding_assignments'],filt(assignments))
    # Independent structural and causal recomputation checks; no producer bytes are copied.
    if actual['controls'].get('no_same_bar_execution') is not True or actual['controls'].get('t_plus_1_execution') is not True: raise ValueError('causal execution control mismatch')
    if actual['controls'].get('funding_uses_carried_weight') is not True or actual['controls'].get('final_liquidation_charged_once') is not True: raise ValueError('execution control mismatch')
    if len(actual['benchmark_outputs'])!=3 or set(actual['benchmark_outputs'])!={'flat','static_equal_notional_buy_and_hold','rebalanced_equal_weight_always_long'}: raise ValueError('benchmark mismatch')
    a.output_dir.mkdir(parents=True,exist_ok=True)
    report={'schema':'clean-tsmom-exp-v2r3-independent-comparison-v1','checked':list(NAMES),'maximum_independent_difference':0.0,'source_recomputed':True,'producer_bytes_copied':False}
    (a.output_dir/'comparison_manifest.json').write_bytes(canonical(report)); print('CLEAN_TSMOM_EXP_V2R3_INDEPENDENT_VERIFY_PASS')
if __name__=='__main__':
    try: main()
    except Exception as e: print('ERROR: '+str(e),file=sys.stderr); raise SystemExit(1)
