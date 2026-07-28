from __future__ import annotations
import argparse
from pathlib import Path
from .data import fetch, fetch_perp, fetch_funding
from .experiment import run, run_perp
from . import IDENTITY

ROOT = Path(__file__).resolve().parents[1]
def main() -> None:
    parser=argparse.ArgumentParser(description=IDENTITY); sub=parser.add_subparsers(dest="cmd", required=True)
    p=sub.add_parser("fetch"); p.add_argument("--symbols", nargs="+", required=True); p.add_argument("--start", default="2021-01-01")
    p=sub.add_parser("fetch-perp"); p.add_argument("--symbols", nargs="+", required=True); p.add_argument("--start", default="2021-01-01")
    p=sub.add_parser("fetch-funding"); p.add_argument("--symbols", nargs="+", required=True); p.add_argument("--start", default="2021-01-01")
    p=sub.add_parser("run"); p.add_argument("spec", type=Path)
    a=parser.parse_args()
    if a.cmd == "fetch":
        for symbol in a.symbols: print(fetch(symbol, a.start, ROOT))
    elif a.cmd == "fetch-perp":
        for symbol in a.symbols: print(fetch_perp(symbol, a.start, ROOT))
    elif a.cmd == "fetch-funding":
        for symbol in a.symbols: print(fetch_funding(symbol, a.start, ROOT))
    else:
        runner = run_perp if a.spec.name == "sprint_v1_perp.json" else run
        result=runner(a.spec, ROOT); print(IDENTITY); print(f"runs={len(result['results'])}")
if __name__ == "__main__": main()
