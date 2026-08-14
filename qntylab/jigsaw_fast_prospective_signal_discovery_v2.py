"""Outcome-blind capability snapshot generator for Jigsaw fast lane V2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RDS_DIGEST = "c0fa7dc0e51c7680fccbd7e7cdd0945fcd63af3e8c75809a24aa3b216868b9ac"
RDS_CONTRACT = ROOT / "docs/forensics/RESEARCH_DATA_SPINE_V0_CONTRACT.md"
RDS_MANIFEST = ROOT / "experiments/research/jigsaw_funding_pressure_volatility_v0/pit_coverage_evidence_v0/manifests"
BTC_MANIFEST = ROOT / "data/manifests/BTCUSDT-perp-1h.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_capability_snapshot() -> dict:
    panel_manifest = sorted(RDS_MANIFEST.glob("*-perp-1h-hourly-input-v0.json"))
    symbols = [json.loads(p.read_text())["symbol"] for p in panel_manifest]
    panel_bytes = [(ROOT / "data/raw" / f"{symbol}-perp-1h.csv").is_file() for symbol in symbols]
    return {
        "schema_version": "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_V2_DATA_CAPABILITIES_V0",
        "generated_from": [
            "docs/forensics/RESEARCH_DATA_SPINE_V0_CONTRACT.md",
            "docs/forensics/RESEARCH_DATA_SPINE_V0_CLOSURE.md",
            "experiments/research/jigsaw_funding_pressure_volatility_v0/pit_coverage_evidence_v0/manifests/*.json",
            "data/manifests/BTCUSDT-perp-1h.json",
        ],
        "raw_market_values_interpreted": False,
        "capabilities": [
            {
                "capability_id": "CAP_V2_RDS_FIXED_PANEL_OHLCV",
                "source_identity": "rds-v0-" + RDS_DIGEST,
                "source_contract_identity": "RESEARCH_DATA_SPINE_V0",
                "source_digests": {
                    "snapshot_digest": RDS_DIGEST,
                    "contract_sha256": _sha256(RDS_CONTRACT),
                    "panel_manifest_sha256": [_sha256(p) for p in panel_manifest],
                },
                "instruments": symbols,
                "coverage_start": "2023-10-19T00:00:00Z",
                "coverage_end": "2025-06-19T23:00:00Z",
                "interval": "1h",
                "available_fields": ["instrument_instance_id", "symbol", "bar_open_time", "bar_close_time", "open", "high", "low", "close", "volume"],
                "timestamp_semantics": "bar_open_time identity; bar_close_time = bar_open_time + 1h",
                "safe_known_after": "bar_close_time",
                "venue": "Binance",
                "market_type": "USD-M perpetual",
                "fixed_panel_semantics": "exact certified 20-symbol fixed panel; no substitutions",
                "source_bytes_currently_available": all(panel_bytes),
                "source_bytes_authenticated": True,
                "source_reuse_permitted": True,
                "network_required": False,
                "existing_materialization_identity": "rds-v0-" + RDS_DIGEST,
                "lifecycle_universe_limitations": "fixed panel only; no lifecycle or relisting assertion",
                "capability_status": "REUSABLE_CANONICAL",
            },
            {
                "capability_id": "CAP_V2_JFP03_BTCUSDT_OHLCV",
                "source_identity": "data/manifests/BTCUSDT-perp-1h.json",
                "source_contract_identity": "BINANCE_USD_M_PERPETUAL_1H_MATERIALIZER_V0",
                "source_digests": {"manifest_sha256": _sha256(BTC_MANIFEST)},
                "instruments": ["BTCUSDT"],
                "coverage_start": "2021-01-01T00:00:00Z",
                "coverage_end": "2026-06-30T23:00:00Z",
                "interval": "1h",
                "available_fields": ["open", "high", "low", "close", "volume", "fundingRate"],
                "timestamp_semantics": "manifested 1h source bars; gaps are separately declared",
                "safe_known_after": "bar_close_time",
                "venue": "Binance",
                "market_type": "USD-M perpetual",
                "fixed_panel_semantics": None,
                "source_bytes_currently_available": (ROOT / "data/raw/BTCUSDT-perp-1h.csv").is_file(),
                "source_bytes_authenticated": True,
                "source_reuse_permitted": False,
                "network_required": True,
                "existing_materialization_identity": None,
                "lifecycle_universe_limitations": "single-symbol lineage; declared archive gaps; separate from RDS snapshot",
                "capability_status": "EVIDENCE_ONLY_NOT_REUSABLE",
            },
        ],
    }


if __name__ == "__main__":
    print(json.dumps(build_capability_snapshot(), indent=2, sort_keys=True))
