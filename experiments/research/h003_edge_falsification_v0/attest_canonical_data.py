"""Reproduce and attest the frozen H003 SOLUSDT 1h input bytes only.

This utility performs public market-data acquisition and byte identity checks.
It does not import a strategy module, run a backtest, mutate the research
ledger, or produce an edge/verdict artifact.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from qntylab.data import fetch

SYMBOL = "SOLUSDT"
START = "2021-01-01T00:00:00"
# qntylab.data.fetch selects the latest complete candle one hour before this
# instant's UTC hour.  21:03 therefore freezes the final open at 20:00.
FROZEN_RETRIEVAL_INSTANT = datetime(2026, 9, 8, 21, 3, 17, 228114, tzinfo=UTC)
EXPECTED_SHA256 = "64bdb27a31003b0de25f3802affa8b412143a50bc8a5b76a399924626b01174a"
EXPECTED_ROWS = 49831
EXPECTED_START = "2021-01-01T00:00:00Z"
EXPECTED_END = "2026-09-08T20:00:00Z"
EXPECTED_GAPS = [
    "2021-02-11T03:00:00+00:00 -> 2021-02-11T05:00:00+00:00 (2:00:00)",
    "2021-03-06T01:00:00+00:00 -> 2021-03-06T03:00:00+00:00 (2:00:00)",
    "2021-04-20T01:00:00+00:00 -> 2021-04-20T04:00:00+00:00 (3:00:00)",
    "2021-04-25T04:00:00+00:00 -> 2021-04-25T08:00:00+00:00 (4:00:00)",
    "2021-08-13T01:00:00+00:00 -> 2021-08-13T06:00:00+00:00 (5:00:00)",
    "2021-09-29T06:00:00+00:00 -> 2021-09-29T09:00:00+00:00 (3:00:00)",
    "2023-03-24T12:00:00+00:00 -> 2023-03-24T14:00:00+00:00 (2:00:00)",
]


def attest(root: Path) -> dict:
    manifest = fetch(SYMBOL, START, root, interval="1h", end=FROZEN_RETRIEVAL_INSTANT)
    observed = {
        "symbol": manifest["symbol"],
        "timeframe": manifest["timeframe"],
        "rows": manifest["rows"],
        "start": manifest["start"],
        "end": manifest["end"],
        "sha256": manifest["sha256"],
        "gaps": manifest["gaps"],
        "source": manifest["source"],
        "source_kind": manifest["source_kind"],
        "complete_candles_only": manifest["complete_candles_only"],
    }
    expected = {
        "symbol": SYMBOL,
        "timeframe": "1h",
        "rows": EXPECTED_ROWS,
        "start": EXPECTED_START,
        "end": EXPECTED_END,
        "sha256": EXPECTED_SHA256,
        "gaps": EXPECTED_GAPS,
        "source": "https://data-api.binance.vision/api/v3/klines",
        "source_kind": "Binance Spot public market-data REST",
        "complete_candles_only": True,
    }
    mismatches = {
        key: {"expected": expected[key], "observed": observed[key]}
        for key in expected
        if observed[key] != expected[key]
    }
    return {
        "schema": "H003_EDGE_FALSIFICATION_V0_INPUT_ATTESTATION",
        "canonical_expected_sha256": EXPECTED_SHA256,
        "canonical_match": not mismatches,
        "observed": observed,
        "mismatches": mismatches,
        "authority": {
            "research_result": "NONE",
            "strategy_execution": "FORBIDDEN",
            "qnty_acceptance": "NONE",
            "qntyspot_policy": "NONE",
            "capital": "NONE",
            "signing": "NONE",
            "submission": "NONE",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Attest frozen H003 SOLUSDT input bytes; no strategy execution")
    parser.add_argument("--out", type=Path, help="optional path for canonical JSON attestation")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="h003-input-attestation-") as directory:
        result = attest(Path(directory))

    encoded = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["canonical_match"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
