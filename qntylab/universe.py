"""Archive-backed, point-in-time daily universe construction for Sprint v2."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
import numpy as np

# Archive names that unambiguously denote commodity, rather than crypto, perps.
NON_COMPARABLE_SYMBOLS = frozenset({"XAGUSDT", "XAUUSDT"})


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_universe(symbols: list[str], dates: list[str], close: np.ndarray, quote_volume: np.ndarray, *, history_days: int, liquidity_days: int, top_n: int, minimum_breadth: int) -> tuple[np.ndarray, list[dict]]:
    """Select only from observations through each UTC date; no filled gaps."""
    if close.shape != quote_volume.shape or close.shape != (len(dates), len(symbols)):
        raise ValueError("daily panel shape mismatch")
    selected = np.zeros_like(close, dtype=bool); ledger = []
    for t, day in enumerate(dates):
        liquid = np.full(len(symbols), np.nan)
        for j in range(len(symbols)):
            prior = close[:t + 1, j]
            if np.isfinite(prior).sum() < history_days: continue
            sample = quote_volume[max(0, t - liquidity_days + 1):t + 1, j]
            if np.isfinite(sample).sum() < liquidity_days: continue
            liquid[j] = np.median(sample)
        order = sorted((j for j in range(len(symbols)) if symbols[j] not in NON_COMPARABLE_SYMBOLS and np.isfinite(liquid[j])), key=lambda j: (-liquid[j], symbols[j]))
        picked = order[:top_n] if len(order) >= minimum_breadth else []
        selected[t, picked] = True
        ledger.append({"date": day, "eligible_count": len(order), "selected_count": len(picked), "selected_symbols": [symbols[j] for j in picked], "liquidity_rank": [{"symbol": symbols[j], "trailing_median_quote_volume": float(liquid[j]), "rank": i + 1} for i, j in enumerate(order)]})
    return selected, ledger


def write_dataset_manifest(path: Path, *, spec_sha256: str, cutoff: str, candidates: list[str], panels: list[dict], ledger: list[dict], union_selected: list[str], exclusions: list[str]) -> dict:
    ledger_bytes = json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode()
    result = {"sprint": "v2_cross_sectional", "cutoff": cutoff, "spec_sha256": spec_sha256, "candidate_discovery": "Binance Vision USD-M daily kline archive directories", "candidate_count": len(candidates), "candidates_sha256": hashlib.sha256("\n".join(candidates).encode()).hexdigest(), "panels": panels, "daily_universe_ledger_sha256": hashlib.sha256(ledger_bytes).hexdigest(), "union_selected": union_selected, "exclusions": exclusions, "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    fingerprint = {key: value for key, value in result.items() if key != "retrieved_at"}
    canonical = json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode()
    result["root_sha256"] = hashlib.sha256(canonical).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result
