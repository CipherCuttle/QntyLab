"""JFPV3 R3 transport-window repair.

This successor preserves the frozen JFPV3 scientific contracts and R2 collector
state machine while correcting only the Binance USD-M kline request boundary.

This module deliberately exposes no activation or collection runtime. A later,
separately Git-backed authorization must provide the operational wrapper after
R3 is canonical.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from qntylab import jfp_v3_shadow as r2

ROOT = Path(__file__).resolve().parents[1]
R3_IMPLEMENTATION_MANIFEST = (
    "experiments/research/jigsaw_fast_prospective_signal_discovery_v3/"
    "collector_v0r3/implementation_manifest.json"
)
R2_CANONICAL_MERGE = "bc4f3a327f23d057da1ad970e9eeb7ed2fe10c91"
R2_IMPLEMENTATION_DIGEST = "3f80bcd2dd60aaae6e1307883cca2e996f631f7bbc3b76037eafef8450167e2b"
R2_MANIFEST_DIGEST = "b1ca7d2bb5025b272bfdcd871a1889f6f25842c2be83c479d19ebad16075520e"


class BinanceUmTransport(r2.BinanceUmTransport):
    """Binance USD-M transport with close-window -> open-window translation."""

    def bars(
        self, symbol: str, start: datetime, end: datetime
    ) -> tuple[bytes, str, list[dict[str, Any]]]:
        symbol = r2._validate_symbol(symbol)
        start, end = r2.ensure_utc(start), r2.ensure_utc(end)
        if end < start:
            raise r2.ContractError("bar window end precedes start")

        # The collector contract is expressed in inclusive logical close times,
        # while Binance /fapi/v1/klines selects rows by candle open time.
        open_start = start - timedelta(hours=1)
        open_end = end - timedelta(hours=1)
        raw = self.requester(
            "GET",
            self.OHLCV_ENDPOINT,
            {
                "symbol": symbol,
                "interval": "1h",
                "startTime": int(open_start.timestamp() * 1000),
                "endTime": int(open_end.timestamp() * 1000),
            },
        )
        rows = json.loads(raw)
        bars = [
            {
                "symbol": symbol,
                "close_time": r2.stamp(
                    datetime.fromtimestamp((int(row[0]) + 3_600_000) / 1000, UTC)
                ),
                "close": row[4],
                "interval": "1h",
                "source_id": "binance-futures-klines",
                "raw_digest": r2.bytes_digest(raw),
            }
            for row in rows
        ]
        return raw, "binance-futures-klines", bars


def implementation_identity(repo_root: Path = ROOT) -> dict[str, Any]:
    """Verify the R3 repair bytes against their frozen manifest."""
    manifest_path = repo_root / R3_IMPLEMENTATION_MANIFEST
    manifest = r2.load_json(manifest_path)
    if manifest.get("parent_r2_canonical_merge") != R2_CANONICAL_MERGE:
        raise r2.ContractError("R3 parent R2 merge mismatch")
    if manifest.get("parent_r2_implementation_digest") != R2_IMPLEMENTATION_DIGEST:
        raise r2.ContractError("R3 parent R2 implementation mismatch")
    if manifest.get("parent_r2_manifest_digest") != R2_MANIFEST_DIGEST:
        raise r2.ContractError("R3 parent R2 manifest mismatch")
    for relative, expected in manifest.get("files", {}).items():
        path = repo_root / relative
        if not path.is_file() or r2.bytes_digest(path.read_bytes()) != expected:
            raise r2.ContractError(f"R3 implementation content mismatch: {relative}")
    return {
        "implementation_digest": manifest.get("implementation_digest"),
        "manifest_digest": r2.bytes_digest(manifest_path.read_bytes()),
        "manifest_path": R3_IMPLEMENTATION_MANIFEST,
    }


def validate_repair_lineage(
    repo_root: Path = ROOT, *, current_sha: str | None = None
) -> dict[str, Any]:
    """Bind R3 to canonical R2 ancestry and unchanged PR-A scientific contracts."""
    current_sha = current_sha or r2.git_sha(repo_root)
    if not r2.is_ancestor(repo_root, R2_CANONICAL_MERGE, current_sha):
        raise r2.ContractError("R3 requires canonical R2 ancestry")
    binding = r2.bind_pr_a(repo_root, current_sha=current_sha)
    identity = implementation_identity(repo_root)
    return {
        "current_sha": current_sha,
        "r2_canonical_merge": R2_CANONICAL_MERGE,
        "r3_implementation_digest": identity["implementation_digest"],
        "pr_a_artifact_digests": binding["artifact_digests"],
        "activation_authority": "NONE",
        "collection_authority": "NONE",
    }
