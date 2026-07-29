"""Foreground-only, resumable auxiliary acquisition for the frozen v2 union."""
from __future__ import annotations
import argparse, hashlib, json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from .data import fetch_funding, fetch_premium_perp, load_funding, load_perp, sha256

UNION_LEDGER_SHA = "d41cf6b15357d64b91709a9ccc9973da89a9fe9a93cc34388c58ba50fbec8e1d"
UNION_SHA = "cb75d98621f72e12beaed1ce41cb15d6ffad01e8be66eaf3ae07517e12c60153"
CUTOFF = "2026-06-30"
RECEIPT_SCHEMA_VERSION = 2
INVENTORY_ROOT_SHA = "c087b76021e87916423a03faade252368640cb9037255fc3cd68d76b61e2a16e"
INVENTORY_RAW_SHA = "d662ebdfcdc75d745927f3434c70722a5ba65007f65385b883c44e19c2fd53da"

def load_union(path: Path) -> list[dict]:
    data=json.loads(path.read_text()); core={k:v for k,v in data.items() if k != "union_selected_sha256"}
    actual=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if len(data.get("symbols",[])) != 181 or data.get("universe_ledger_sha256") != UNION_LEDGER_SHA or data.get("union_selected_sha256") != UNION_SHA or actual != UNION_SHA: raise ValueError("frozen union verification failed")
    return data["symbols"]

def _receipt(root: Path, symbol: str) -> Path: return root / "data/archive/aux_v2" / f"{symbol}.json"

def _metadata(path: Path, loader) -> dict | None:
    if not path.exists(): return None
    rows = loader(path)
    if not rows: return None
    return {"state": "VALID", "rows": len(rows), "sha256": sha256(path), "start": rows[0]["timestamp"], "end": rows[-1]["timestamp"]}

def _result(item: dict, funding: dict, premium: dict) -> dict:
    return {"receipt_schema_version": RECEIPT_SCHEMA_VERSION, "symbol": item["symbol"], "selected_start": item["first_selected"], "selected_end": item["last_selected"], "funding": funding, "premium": premium}

def _reusable(prior: dict, funding: dict | None, premium: dict | None) -> bool:
    if prior.get("receipt_schema_version") != RECEIPT_SCHEMA_VERSION: return False
    for kind, actual in (("funding", funding), ("premium", premium)):
        recorded = prior.get(kind, {})
        if recorded.get("state") == "VALID" and recorded != actual: return False
        if recorded.get("state") == "NO_SOURCE_DATA" and actual is not None: return False
        if recorded.get("state") not in {"VALID", "NO_SOURCE_DATA"}: return False
    return True

def build_dataset_freeze_manifest(root: Path, union_path: Path, *, implementation_commit: str) -> dict:
    """Build the deterministic, pre-outcome auxiliary coverage binding for Sprint v2."""
    union = load_union(union_path)
    inventory = root / "data/archive/sprint_v2_1d_inventory.json"
    if sha256(inventory) != INVENTORY_RAW_SHA: raise ValueError("frozen inventory raw SHA mismatch")
    coverage = []
    for item in sorted(union, key=lambda value: value["symbol"]):
        receipt = json.loads(_receipt(root, item["symbol"]).read_text())
        if receipt.get("receipt_schema_version") != RECEIPT_SCHEMA_VERSION: raise ValueError("auxiliary receipt schema mismatch")
        row = {"symbol": item["symbol"], "selected_start": item["first_selected"], "selected_end": item["last_selected"]}
        for kind in ("funding", "premium"):
            source = receipt[kind]
            if source.get("state") == "VALID":
                row[kind] = {key: source[key] for key in ("state", "rows", "start", "end", "sha256")}
                row[kind]["selected_interval_fully_covered"] = source["start"] <= item["first_selected"] and item["last_selected"] <= source["end"]
            elif source.get("state") == "NO_SOURCE_DATA": row[kind] = {"state": "NO_SOURCE_DATA", "reason": source["reason"]}
            else: raise ValueError("auxiliary receipt is not terminal")
        coverage.append(row)
    result = {"manifest_version": 1, "canonicalization_domain": "UTF-8 JSON, keys sorted recursively, compact separators, SHA-256 over this object excluding dataset_root_sha256", "sprint": "v2_cross_sectional", "preregistration_commit": "b5c4f16", "load_bearing_commits": {"auxiliary_consumer": "7ab185f", "implementation_repair": implementation_commit, "preregistration": "b5c4f16", "universe": "310209e"}, "inventory": {"canonical_root_sha256": INVENTORY_ROOT_SHA, "raw_sha256": INVENTORY_RAW_SHA}, "broad_data": {"panels_valid": 789, "panels_total": 789, "rows": 586929, "recorded_gaps": 103, "rejected_panels": 0}, "mechanical_exclusions": ["XAGUSDT", "XAUUSDT", "TSLAUSDT"], "universe": {"ledger_sha256": UNION_LEDGER_SHA, "union_count": 181, "union_selected_sha256": UNION_SHA}, "sample_cutoff": CUTOFF, "auxiliary_coverage": coverage}
    result["dataset_root_sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return result

def write_dataset_freeze_manifest(path: Path, root: Path, union_path: Path, *, implementation_commit: str) -> dict:
    result = build_dataset_freeze_manifest(root, union_path, implementation_commit=implementation_commit)
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result

def _one(root: Path, item: dict) -> dict:
    symbol=item["symbol"]; receipt=_receipt(root,symbol)
    funding_path=root/"data/raw"/f"{symbol}-funding.csv"; premium_path=root/"data/raw"/f"{symbol}-perp-1h.csv"
    funding=_metadata(funding_path, load_funding); premium=_metadata(premium_path, load_perp)
    if receipt.exists():
        prior=json.loads(receipt.read_text())
        if _reusable(prior, funding, premium): return prior | {"reused":True}
    if funding is None:
        try: fetch_funding(symbol,item["first_selected"],root,end=datetime(2026,7,1,tzinfo=UTC)); funding=_metadata(funding_path, load_funding)
        except ValueError as exc: funding={"state":"NO_SOURCE_DATA","reason":str(exc)}
    if premium is None:
        try: fetch_premium_perp(symbol,item["first_selected"],root,end=datetime(2026,7,1,tzinfo=UTC)); premium=_metadata(premium_path, load_perp)
        except ValueError as exc: premium={"state":"NO_SOURCE_DATA","reason":str(exc)}
    result=_result(item,funding,premium)
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
