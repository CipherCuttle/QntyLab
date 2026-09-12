"""JFPV3 R3 transport-window repair.

This successor preserves the frozen JFPV3 scientific contracts and R2 collector
state machine while correcting the Binance USD-M kline request boundary.  The
public `bars(start, end)` contract is expressed in logical *close* timestamps;
Binance `startTime`/`endTime` select klines by *open* timestamp.  Therefore each
REST bound is shifted back exactly one hour.

No activation or network access occurs on import.
"""
from __future__ import annotations

import argparse
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
    """Verify the R3 successor bytes against its frozen manifest."""
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


def activate_shadow_runtime(
    ledger: r2.ReceiptLedger, *, repo_root: Path = ROOT, now: datetime | None = None
) -> dict[str, Any]:
    """Perform the existing guarded activation under the repaired R3 identity."""
    state = r2.resolve_runtime_canonical_state(repo_root, refresh=True)
    if not state["canonical"]:
        raise r2.ContractError("activation requires fresh clean canonical master")
    if not r2.is_ancestor(repo_root, R2_CANONICAL_MERGE, state["head_sha"]):
        raise r2.ContractError("R3 activation requires canonical R2 ancestry")
    binding = r2.bind_pr_a(repo_root, current_sha=state["head_sha"])
    identity = implementation_identity(repo_root)
    activation_time = r2.ensure_utc(now or datetime.now(UTC))
    record = {
        "activation_master_sha": state["head_sha"],
        "collector_implementation_sha": identity["implementation_digest"],
        "preregistration_digest": binding["artifact_digests"]["preregistration.json"],
        "universe_contract_digest": binding["artifact_digests"]["universe_contract.json"],
        "source_contract_digest": binding["artifact_digests"]["source_contract.json"],
        "scientific_contract_digest": binding["artifact_digests"]["scientific_contract.json"],
        "schedule_contract_digest": binding["artifact_digests"]["schedule_contract.json"],
        "activation_timestamp": r2.stamp(activation_time),
        "shadow_run_id": (
            f"{r2.GENERATION_ID}-R3-"
            f"{activation_time.strftime('%Y%m%dT%H%M%SZ')}-{state['head_sha'][:12]}"
        ),
    }
    return r2.activate_shadow(
        ledger,
        record,
        r2.schedule(activation_time),
        canonical_state=state,
        binding=binding,
        expected_implementation_sha=identity["implementation_digest"],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m qntylab.jfp_v3_shadow_r3")
    parser.add_argument(
        "command",
        choices=("verify-config", "activate-shadow", "collect-due", "status", "verify-receipts"),
    )
    parser.add_argument("--ledger", type=Path, default=Path("data/jfp_v3_shadow/events.jsonl"))
    args = parser.parse_args(argv)

    if args.command == "verify-config":
        payload = {
            "pr_a": r2.bind_pr_a(),
            "r3": implementation_identity(),
        }
        print(json.dumps(payload, sort_keys=True))
        return 0

    ledger = r2.ReceiptLedger(args.ledger)
    if args.command == "status":
        print(json.dumps(r2.status(ledger), sort_keys=True))
        return 0
    if args.command == "verify-receipts":
        print(json.dumps(ledger.verify(), sort_keys=True))
        return 0
    if args.command == "activate-shadow":
        print(json.dumps(activate_shadow_runtime(ledger), sort_keys=True))
        return 0
    if args.command == "collect-due":
        result = r2.collect_due(
            r2.Collector(ledger),
            BinanceUmTransport(r2.UrllibRequester()),
            now=datetime.now(UTC),
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    raise r2.ContractError("unsupported R3 command")


if __name__ == "__main__":  # pragma: no cover
    main()
