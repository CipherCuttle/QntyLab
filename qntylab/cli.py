from __future__ import annotations
import argparse
from pathlib import Path
from .data import fetch
from .experiment import run
from . import IDENTITY

ROOT = Path(__file__).resolve().parents[1]
def main() -> None:
    parser=argparse.ArgumentParser(description=IDENTITY); sub=parser.add_subparsers(dest="cmd", required=True)
    p=sub.add_parser("fetch"); p.add_argument("--symbols", nargs="+", required=True); p.add_argument("--start", default="2021-01-01")
    p=sub.add_parser("run"); p.add_argument("spec", type=Path)
    a=parser.parse_args()
    if a.cmd == "fetch":
        for symbol in a.symbols: print(fetch(symbol, a.start, ROOT))
    else:
        result=run(a.spec, ROOT); print(IDENTITY); print(f"runs={len(result['results'])} output=experiments/results/sprint_v0_results.json")
if __name__ == "__main__": main()
