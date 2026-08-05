"""Independent static verifier for the Clean TSMOM EXP_V2 preregistration."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

UNIVERSE = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "LINKUSDT", "DOTUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT", "AVAXUSDT"]
CONTRACTS = ("source_contract.json", "v1_equal_weight.json", "v2_inverse_vol.json", "evaluation_v2.json")


def verify(root: Path) -> None:
    if sorted(path.name for path in root.iterdir() if path.is_file()) != sorted(("README.md", *CONTRACTS, "source_manifest.json", *(name.replace(".json", ".sha256") for name in (*CONTRACTS, "source_manifest.json")))):
        raise ValueError("unexpected or missing EXP_V2 contract files")
    for name in CONTRACTS + ("source_manifest.json",):
        payload = (root / name).read_bytes()
        json.loads(payload)
        expected = (root / name.replace(".json", ".sha256")).read_text(encoding="utf-8").split()[0]
        if hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError(f"checksum mismatch: {name}")
    source = json.loads((root / "source_contract.json").read_text(encoding="utf-8"))
    v1 = json.loads((root / "v1_equal_weight.json").read_text(encoding="utf-8"))
    v2 = json.loads((root / "v2_inverse_vol.json").read_text(encoding="utf-8"))
    evaluation = json.loads((root / "evaluation_v2.json").read_text(encoding="utf-8"))
    if source["universe"] != v1["universe"] or source["universe"] != v2["universe"] or source["universe"] != evaluation["universe"]:
        raise ValueError("universe mismatch")
    if source["universe"] != UNIVERSE or any(symbol in source["universe"] for symbol in ("MATICUSDT", "POLUSDT")):
        raise ValueError("universe is not the frozen nine symbols")
    if v2["volatility_lookback_returns"] != 90 or v2["volatility_ddof"] != 0 or v2["decision_close_window"] != "r_(t-89)..r_t":
        raise ValueError("causal V2 semantics changed")
    if evaluation["result_status"] != "NOT_YET_RUN":
        raise ValueError("evaluation is not preregistration-only")
    forbidden = ("net_return", "sharpe", "max_drawdown", "PRELIMINARY_KILLED", "19196a8d40d2cde7")
    if any(token in path.read_text(encoding="utf-8") for path in root.rglob("*") if path.is_file() for token in forbidden):
        raise ValueError("prohibited result material present")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    verify(parser.parse_args().root)
    print("CLEAN_TSMOM_EXP_V2_CONTRACT_VERIFY_PASS")
