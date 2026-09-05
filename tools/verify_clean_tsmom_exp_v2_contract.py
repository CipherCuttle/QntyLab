"""Compatibility entry point for the frozen EXP_V2 contract verifier."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.verify_clean_tsmom_v2_contract import verify

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    verify(parser.parse_args().root)
    print("CLEAN_TSMOM_EXP_V2_CONTRACT_VERIFY_PASS")
