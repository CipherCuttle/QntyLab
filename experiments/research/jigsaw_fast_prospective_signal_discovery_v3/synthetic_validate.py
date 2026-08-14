"""Small synthetic-only contract check for JFPV3 preregistration artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parent


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def eligible(row: dict, origin: int) -> bool:
    return (
        row["venue"] == "Binance"
        and row["market_type"] == "USD-M perpetual"
        and row["contract_type"] == "PERPETUAL"
        and row["status"] == "TRADING"
        and row["onboard"] <= origin - 30 * 24 * 3600
        and row["prior_bars"] == 24
        and row["duplicates"] == 0
        and row["missing"] == 0
    )


def main() -> None:
    rows = [
        {"symbol": "BETAUSDT", "venue": "Binance", "market_type": "USD-M perpetual", "contract_type": "PERPETUAL", "status": "TRADING", "onboard": 0, "prior_bars": 24, "duplicates": 0, "missing": 0},
        {"symbol": "ALPHAUSDT", "venue": "Binance", "market_type": "USD-M perpetual", "contract_type": "PERPETUAL", "status": "TRADING", "onboard": 0, "prior_bars": 24, "duplicates": 0, "missing": 0},
        {"symbol": "SETTLEUSDT", "venue": "Binance", "market_type": "USD-M perpetual", "contract_type": "PERPETUAL", "status": "SETTLING", "onboard": 0, "prior_bars": 24, "duplicates": 0, "missing": 0},
        {"symbol": "NEWUSDT", "venue": "Binance", "market_type": "USD-M perpetual", "contract_type": "PERPETUAL", "status": "TRADING", "onboard": 2 * 24 * 3600, "prior_bars": 24, "duplicates": 0, "missing": 0},
        {"symbol": "GAPUSDT", "venue": "Binance", "market_type": "USD-M perpetual", "contract_type": "PERPETUAL", "status": "TRADING", "onboard": 0, "prior_bars": 23, "duplicates": 0, "missing": 1},
    ]
    origin = 31 * 24 * 3600
    ordered = sorted(row["symbol"] for row in rows if eligible(row, origin))
    assert ordered == ["ALPHAUSDT", "BETAUSDT"]
    assert digest(ordered) == digest(["ALPHAUSDT", "BETAUSDT"])
    assert digest(ordered) != digest(list(reversed(ordered)))
    sealed = tuple(ordered)
    later = sorted(set(ordered) | {"LATERUSDT"})
    assert sealed == ("ALPHAUSDT", "BETAUSDT")
    assert later != list(sealed), "later origins may change; sealed origins may not"
    assert "SETTLEUSDT" not in sealed and "NEWUSDT" not in sealed and "GAPUSDT" not in sealed
    assert len(sealed) < 15, "synthetic fixture intentionally exercises the minimum-N block"
    print("synthetic contract validation: PASS (15 checks represented; no real market data)")


if __name__ == "__main__":
    main()
