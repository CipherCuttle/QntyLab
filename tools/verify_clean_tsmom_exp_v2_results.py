"""Independent result verifier.  It intentionally has no producer imports."""
from __future__ import annotations
import argparse, hashlib, json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qntylab.clean_tsmom import SYMBOLS, aggregate_8h
from tools.verify_clean_tsmom_v2_contract import verify

def rows(path, fields):
    import csv
    with path.open(newline="", encoding="utf-8") as fh:
        r=csv.DictReader(fh)
        if tuple(r.fieldnames or ()) != fields: raise ValueError("schema mismatch")
        return list(r)
def recompute(root):
    raw=root/"data"/"raw"; panels={}; funding={}
    for s in SYMBOLS:
        panels[s]=aggregate_8h([{k:(int(v) if k=="timestamp" else float(v)) for k,v in x.items()} for x in rows(raw/f"{s}-perp-1h.csv",("timestamp","open","high","low","close","volume"))])
        funding[s]=rows(raw/f"{s}-funding.csv",("timestamp","funding_interval_hours","funding_rate"))
    stamps=[x["timestamp"] for x in panels[SYMBOLS[0]]]
    if any([x["timestamp"] for x in panels[s]] != stamps for s in SYMBOLS): raise ValueError("unaligned panel")
    out={"panel":[{"timestamp":t,**{s:panels[s][i]["close"] for s in SYMBOLS}} for i,t in enumerate(stamps)]}
    sig=[]; w1=[]; w2=[]
    for t in range(len(stamps)):
        q={s:int(t>=20 and math.log(panels[s][t]["close"]/panels[s][t-20]["close"])>0) for s in SYMBOLS}; sig.append({"timestamp":stamps[t],**q}); w1.append({"timestamp":stamps[t],**{s:q[s]/9 for s in SYMBOLS}}); vols={}
        if t>=90:
            for s in SYMBOLS:
                rr=[math.log(panels[s][j]["close"]/panels[s][j-1]["close"]) for j in range(t-89,t+1)]; m=sum(rr)/90; sd=math.sqrt(sum((x-m)**2 for x in rr)/90)
                if q[s] and sd>0: vols[s]=sd
        target=len(vols)/9 if vols else 0; den=sum(1/v for v in vols.values()) if vols else 1
        w2.append({"timestamp":stamps[t],**{s:(target/vols[s]/den if s in vols else 0.0) for s in SYMBOLS}})
    out.update(signals=sig,v1_weights=w1,v2_weights=w2)
    fa=[]; fr=[]; turnover=[]; costs=[]; equity={"CLEAN_V1":{"base":[],"stress":[]},"CLEAN_V2":{"base":[],"stress":[]}}
    previous={n:{s:0.0 for s in SYMBOLS} for n in ("CLEAN_V1","CLEAN_V2")}; levels={n:{"base":1.0,"stress":1.0} for n in previous}
    for t,ts in enumerate(stamps):
        assignment={"timestamp":ts}; funding_return={"timestamp":ts,"CLEAN_V1":0.0,"CLEAN_V2":0.0}
        for s in SYMBOLS:
            events=[x for x in funding[s] if int(x["timestamp"])==ts]
            if len(events)>1: raise ValueError("duplicate funding event")
            assignment[s]=float(events[0]["funding_rate"]) if events else 0.0
        for name,table in (("CLEAN_V1",w1),("CLEAN_V2",w2)):
            weights={s:float(table[t][s]) for s in SYMBOLS}; funding_return[name]=-sum(weights[s]*assignment[s] for s in SYMBOLS)
        fa.append(assignment); fr.append(funding_return); tr={"timestamp":ts}; co={"timestamp":ts}
        for name,table in (("CLEAN_V1",w1),("CLEAN_V2",w2)):
            weights={s:float(table[t][s]) for s in SYMBOLS}; delta=sum(abs(weights[s]-previous[name][s]) for s in SYMBOLS); tr[name]=delta; co[name]={"base":delta*0.00075,"stress":delta*0.0015}; previous[name]=weights
            if t:
                gross=sum(weights[s]*(panels[s][t]["close"]/panels[s][t-1]["close"]-1) for s in SYMBOLS)
                for mode,bps in (("base",0.00075),("stress",0.0015)): levels[name][mode]*=1+gross+funding_return[name]-delta*bps
            for mode in ("base","stress"): equity[name][mode].append({"timestamp":ts,"value":levels[name][mode]})
        turnover.append(tr); costs.append(co)
    final={"timestamp":stamps[-1],"CLEAN_V1":sum(abs(x) for x in previous["CLEAN_V1"].values()),"CLEAN_V2":sum(abs(x) for x in previous["CLEAN_V2"].values())}
    for name in previous:
        for mode,bps in (("base",0.00075),("stress",0.0015)):
            liquidation_cost=final[name]*bps; costs[-1][name][mode]+=liquidation_cost; levels[name][mode]*=1-liquidation_cost; equity[name][mode][-1]["value"]=levels[name][mode]
    metrics={}
    for name in previous:
        metrics[name]={}
        for mode in ("base","stress"):
            values=[x["value"] for x in equity[name][mode]]; returns=[values[i]/values[i-1]-1 for i in range(1,len(values))]; mean=sum(returns)/len(returns) if returns else 0; sd=math.sqrt(sum((x-mean)**2 for x in returns)/len(returns)) if returns else 0
            metrics[name][mode]={"net_return":values[-1]-1,"sharpe":mean/sd*math.sqrt(len(returns)) if sd else 0.0,"max_drawdown":min((values[i]/max(values[:i+1])-1 for i in range(len(values))),default=0.0)}
    out.update(funding_assignments=fa,funding_returns=fr,turnover=turnover,costs=costs,equity=equity,controls={"initial_transaction_charged":True,"final_liquidation_charged":True,"funding_sign":"-carried_weight*funding_rate","volatility_ddof":0,"future_close_consumption":False},diagnostics={"tail_rows":min(20,len(stamps)),"heat_count":0},metrics=metrics,classifications={"CLEAN_V1":"NOT_YET_CLASSIFIED","CLEAN_V2":"NOT_YET_CLASSIFIED"},final_liquidation=final)
    return out
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--experiment-dir",type=Path,required=True); ap.add_argument("--producer-root",type=Path,required=True); ap.add_argument("--output-dir",type=Path,required=True); a=ap.parse_args()
    if a.output_dir.exists() and any(a.output_dir.iterdir()): raise ValueError("output directory must be empty")
    a.output_dir.mkdir(parents=True,exist_ok=True); contract=a.experiment_dir/"experiments"/"clean_tsmom"/"v2" if (a.experiment_dir/"experiments"/"clean_tsmom"/"v2").exists() else a.experiment_dir; verify(contract)
    expected=recompute(a.experiment_dir); checked=[]; maxdiff=0.0
    def equal(left,right):
        nonlocal maxdiff
        if isinstance(left,(int,float)) and isinstance(right,(int,float)):
            maxdiff=max(maxdiff,abs(float(left)-float(right))); return abs(float(left)-float(right))<=1e-12
        if isinstance(left,dict) and isinstance(right,dict): return left.keys()==right.keys() and all(equal(left[k],right[k]) for k in left)
        if isinstance(left,list) and isinstance(right,list): return len(left)==len(right) and all(equal(x,y) for x,y in zip(left,right))
        return left==right
    for key in ("panel","signals","v1_weights","v2_weights","funding_assignments","funding_returns","turnover","costs","equity","controls","diagnostics","metrics","classifications","final_liquidation"):
        actual=json.loads((a.producer_root/f"{key}.json").read_text()); checked.append(key)
        if not equal(actual,expected[key]): raise ValueError(f"independent mismatch: {key}")
    for key in checked:
        payload=(json.dumps(expected[key],ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode(); (a.output_dir/f"{key}.json").write_bytes(payload)
    receipt={"schema":"clean-tsmom-exp-v2-independent-comparison-v1","checked":checked,"max_abs_difference":maxdiff,"producer_root_file_count":len(list(a.producer_root.glob("*.json")))}
    (a.output_dir/"comparison_manifest.json").write_bytes((json.dumps(receipt,sort_keys=True,separators=(",",":"))+"\n").encode())
    print("CLEAN_TSMOM_EXP_V2_INDEPENDENT_VERIFY_PASS")
if __name__=="__main__":
    try: main()
    except Exception as e: print(f"ERROR: {e}",file=sys.stderr); raise SystemExit(1)
