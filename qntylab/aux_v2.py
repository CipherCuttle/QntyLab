"""Foreground-only, resumable auxiliary acquisition for the frozen v2 union."""
from __future__ import annotations
import argparse, hashlib, json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from .data import fetch_perp, sha256

UNION_LEDGER_SHA = "d41cf6b15357d64b91709a9ccc9973da89a9fe9a93cc34388c58ba50fbec8e1d"
UNION_SHA = "cb75d98621f72e12beaed1ce41cb15d6ffad01e8be66eaf3ae07517e12c60153"
CUTOFF = "2026-06-30"

def load_union(path: Path) -> list[dict]:
    data=json.loads(path.read_text()); core={k:v for k,v in data.items() if k != "union_selected_sha256"}
    actual=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if len(data.get("symbols",[])) != 181 or data.get("universe_ledger_sha256") != UNION_LEDGER_SHA or data.get("union_selected_sha256") != UNION_SHA or actual != UNION_SHA: raise ValueError("frozen union verification failed")
    return data["symbols"]

def _receipt(root: Path, symbol: str) -> Path: return root / "data/archive/aux_v2" / f"{symbol}.json"

def _one(root: Path, item: dict) -> dict:
    symbol=item["symbol"]; receipt=_receipt(root,symbol)
    if receipt.exists():
        prior=json.loads(receipt.read_text())
        if prior.get("funding",{}).get("state") in {"VALID","NO_SOURCE_DATA"} and prior.get("premium",{}).get("state") in {"VALID","NO_SOURCE_DATA"}: return prior | {"reused":True}
    try:
        # Sprint-v1's archive parser preserves hourly premium close and settled funding timing.
        data=fetch_perp(symbol,"2020-01-01",root,end=datetime(2026,7,1,tzinfo=UTC))
        funding_path=root/"data/raw"/f"{symbol}-funding.csv"; perp_path=root/"data/raw"/f"{symbol}-perp-1h.csv"
        result={"symbol":symbol,"selected_start":item["first_selected"],"selected_end":item["last_selected"],"funding":{"state":"VALID","rows":data["funding_events"],"sha256":sha256(funding_path),"start":data["start"],"end":data["end"]},"premium":{"state":"VALID","rows":data["rows"],"sha256":sha256(perp_path),"start":data["start"],"end":data["end"]}}
    except ValueError as exc:
        result={"symbol":symbol,"selected_start":item["first_selected"],"selected_end":item["last_selected"],"funding":{"state":"NO_SOURCE_DATA","reason":str(exc)},"premium":{"state":"NO_SOURCE_DATA","reason":str(exc)}}
    receipt.parent.mkdir(parents=True,exist_ok=True); tmp=receipt.with_suffix(".json.tmp"); tmp.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n"); tmp.replace(receipt)
    return result

def run(root: Path, union_path: Path, workers: int=8) -> list[dict]:
    union=load_union(union_path); results=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(_one,root,item) for item in union]
        for n,future in enumerate(as_completed(futures),1):
            results.append(future.result())
            if n % 10 == 0 or n == len(union): print(f"QNTYLAB SPRINT V2 AUX complete {n}/{len(union)}",flush=True)
    return sorted(results,key=lambda x:x["symbol"])

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--workers",type=int,default=8); parser.add_argument("--union",type=Path,default=Path("experiments/data/sprint_v2_union_selected.json")); args=parser.parse_args(); root=Path(__file__).resolve().parents[1]
    print("QNTYLAB SPRINT V2 AUX\nunion: 181",flush=True); rows=run(root,root/args.union,args.workers)
    for kind in ("funding","premium"): print(f"{kind.upper()}: {dict(Counter(row[kind]['state'] for row in rows))}")
    print("=== AUXILIARY ACQUISITION RETURNED ===\nsymbols: 181\npending: 0")
if __name__ == "__main__": main()
