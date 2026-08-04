"""Source-resolved nine-symbol clean TSMOM evaluation."""
from __future__ import annotations
import csv, json, math
from datetime import UTC, datetime
from pathlib import Path
import numpy as np
from .clean_tsmom import aggregate_8h, signal

SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "LINKUSDT", "DOTUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT", "AVAXUSDT"]
EVAL = {"selection_date":"2026-04-22","warmup_start":"2026-03-01T00:00:00Z","start":"2026-04-23T00:00:00Z","end":"2026-08-01T00:00:00Z","tail_start":"2026-06-19T00:00:00Z","tail_end":"2026-08-01T00:00:00Z"}

def _dt(s): return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)

def _weights_v1(closes):
    return np.column_stack([signal(closes[:, i]) for i in range(closes.shape[1])]) / 9.0

def _weights_v2(closes):
    sig = np.column_stack([signal(closes[:, i]) for i in range(closes.shape[1])]); lr = np.log(closes[1:] / closes[:-1]); out = np.zeros_like(closes); heat = 0
    for t in range(90, len(closes)):
        vol = np.std(lr[t-89:t+1], axis=0, ddof=0); idx = np.flatnonzero((sig[t] == 1) & np.isfinite(vol) & (vol > 0))
        if len(idx):
            raw = 1 / vol[idx]; row = (len(idx) / 9) * raw / raw.sum(); out[t, idx] = row
            if out[t].sum() > 1: out[t] /= out[t].sum(); heat += 1
    return out, heat

def run_equity(closes, weights, timestamps, funding, start, end, cost_rate):
    begin, finish = int(_dt(start).timestamp()*1000), int(_dt(end).timestamp()*1000); ix = [i for i,t in enumerate(timestamps) if begin <= t < finish]; prev = np.zeros(len(SYMBOLS)); equity=10000.; rows=[]; fmap={(e['symbol'],int(e['timestamp'])):float(e['funding_rate']) for e in funding}
    if len(fmap) != len(funding): raise ValueError('duplicate funding event')
    turnover=fee=fpaid=freceived=0.; episodes=0
    for i in ix:
        if i == 0: continue
        new=weights[i-1]; price=closes[i]/closes[i-1]-1; pr=float(np.dot(prev,price)); fr=0.
        for j,s in enumerate(SYMBOLS):
            x=-prev[j]*fmap.get((s,timestamps[i]),0.); fr += x; freceived += max(x,0); fpaid += max(-x,0)
        turn=float(np.abs(new-prev).sum()); cost=turn*cost_rate; equity *= 1+pr+fr-cost; turnover += turn; fee += turn*cost_rate*2/3; episodes += int(np.count_nonzero((prev==0)&(new>0))); prev=new
        rows.append({'timestamp':timestamps[i],'price_return':pr,'funding_return':fr,'turnover':turn,'cost':cost,'equity':equity})
    final_turn=float(np.abs(prev).sum()); equity_liq=equity*(1-final_turn*cost_rate); rets=np.array([r['price_return']+r['funding_return']-r['cost'] for r in rows]); eq=np.array([r['equity'] for r in rows]); peak=np.maximum.accumulate(np.r_[10000.,eq])[1:]
    return {'valid_8h_bars':len(rows),'net_return':equity_liq/10000.-1,'sharpe':float(rets.mean()/rets.std(ddof=0)*math.sqrt(365*3)) if len(rets) and rets.std(ddof=0) else 0.,'maximum_drawdown':float((eq/peak-1).min()) if len(eq) else 0.,'turnover':turnover+final_turn,'fee_cost':fee,'slippage_cost':fee/2,'funding_paid':fpaid*10000,'funding_received':freceived*10000,'net_funding':(freceived-fpaid)*10000,'average_gross_exposure':float(np.mean([np.abs(weights[i-1]).sum() for i in ix if i])) if len(ix)>1 else 0.,'maximum_gross_exposure':float(np.abs(weights).sum(axis=1).max()),'position_episode_count':episodes,'equity_rows':rows}

def _load(path):
    with path.open(newline='',encoding='utf-8') as f: return list(csv.DictReader(f))

def build_panel(root):
    bars={}; funding=[]
    for s in SYMBOLS:
        rows=_load(root/'data/raw'/f'{s}-perp-1h.csv'); bars[s]=aggregate_8h(rows); funding += [dict(x, symbol=s) for x in _load(root/'data/raw'/f'{s}-funding.csv')]
    stamps=[int(r['timestamp']) for r in bars[SYMBOLS[0]]];
    if any([int(r['timestamp']) for r in bars[s]] != stamps for s in SYMBOLS): raise ValueError('common panel misalignment')
    closes=np.column_stack([[float(r['close']) for r in bars[s]] for s in SYMBOLS]); return stamps, closes, funding

def evaluate(root):
    stamps, closes, funding=build_panel(root); w1=_weights_v1(closes); w2,_=_weights_v2(closes); results={}
    for name,w in [('CLEAN_V1',w1),('CLEAN_V2',w2),('FLAT',np.zeros_like(w1)),('STATIC_EQUAL_NOTIONAL_BUY_AND_HOLD',np.full_like(w1,1/9)),('REBALANCED_EQUAL_WEIGHT_ALWAYS_LONG',np.full_like(w1,1/9))]:
        for regime,rate in [('base',0.00075),('stress',0.0015)]:
            results[f'{name}_{regime}']=run_equity(closes,w,stamps,funding,EVAL['start'],EVAL['end'],rate)
            results[f'{name}_{regime}_TAIL']=run_equity(closes,w,stamps,funding,EVAL['tail_start'],EVAL['tail_end'],rate)
    return {'symbols':SYMBOLS,'evaluation':EVAL,'results':results}

if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('root',type=Path); p.add_argument('--output',type=Path,required=True); a=p.parse_args(); a.output.write_text(json.dumps(evaluate(a.root),sort_keys=True,indent=2)+'\n'); print('CLEAN_TSMOM_V1_EVALUATION_COMPLETE')
