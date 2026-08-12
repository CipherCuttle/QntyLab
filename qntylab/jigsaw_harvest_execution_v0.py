"""Verified transport bridge for the frozen Jigsaw Harvest V0 implementation.

This module deliberately binds an explicit, already-materialized Research Data
Spine snapshot to the frozen Harvest seams.  It neither materializes data nor
changes the Harvest formulas, statistics, or preregistration.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import jigsaw_harvest_v0 as harvest
from . import research_data_spine as spine


CANONICAL_EXECUTION_BASE = "1cc9025a73a354ef6994356078ec1407ffb51a91"
REVIEWED_HARVEST_IMPLEMENTATION_SHA = "a1271c3330956e7c6a61a2d6dade71858581b69c"
_COMMIT_SHA_LENGTH = 40


class ExecutionBridgeError(ValueError):
    """The bridge receipt cannot bind the frozen implementation identity."""


def _utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise spine.ResearchDataSpineError(f"invalid verified timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise spine.ResearchDataSpineError("verified timestamps must be timezone-aware")
    return parsed.astimezone(UTC)


def _require_commit_sha(value: str) -> str:
    if not isinstance(value, str) or len(value) != _COMMIT_SHA_LENGTH or any(character not in "0123456789abcdef" for character in value):
        raise ExecutionBridgeError("execution_bridge_sha must be a lowercase 40-character commit SHA")
    return value


def _manifest_universe(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(part["instrument_identity"]["symbol"] for part in manifest["ordered_partitions"])


def _read_verified_bars(*, snapshot_path: Path) -> dict[str, tuple[harvest.BarClose, ...]]:
    """Read the fixed coverage only after whole-snapshot identity verification."""
    manifest = spine.verify_snapshot(snapshot_path, harvest.EXPECTED_SNAPSHOT_DIGEST)
    universe = _manifest_universe(manifest)
    harvest.validate_real_snapshot_identity(
        snapshot_id=manifest["snapshot_id"],
        snapshot_digest=manifest["snapshot_digest"],
        universe=universe,
    )
    frame = spine.read_window(
        snapshot_path=snapshot_path,
        expected_snapshot_digest=harvest.EXPECTED_SNAPSHOT_DIGEST,
        requested_symbols=universe,
        start=harvest.FIRST_BAR_OPEN,
        end=harvest.LAST_BAR_OPEN,
    )
    bars: dict[str, list[harvest.BarClose]] = {symbol: [] for symbol in harvest.UNIVERSE}
    for row in frame.to_dicts():
        symbol = row["symbol"]
        bars[symbol].append(
            harvest.BarClose(
                bar_open_time=_utc(row["bar_open_time"]),
                close=float(row["close"]),
                safe_known_after=_utc(row["bar_close_time"]),
            )
        )
    return {symbol: tuple(bars[symbol]) for symbol in harvest.UNIVERSE}


def _frozen_regressions(rows: Sequence[harvest.DesignRow]) -> list[dict[str, Any]]:
    """Select frozen design columns and delegate all statistical work to Harvest."""
    columns = {
        "JH01_RV_PERSISTENCE": ([row.rv24_prior for row in rows], [row.rv24_future for row in rows]),
        "JH02_DISPERSION_TO_RV": ([row.dispersion24 for row in rows], [row.rv24_future for row in rows]),
        "JH03_BREADTH_TO_RETURN": ([row.breadth7d for row in rows], [row.market_return_future for row in rows]),
        "JH04_DRAWDOWN_TO_RETURN": ([row.drawdown_depth30d for row in rows], [row.market_return_future for row in rows]),
    }
    raw = {
        proposition_id: harvest._ols_hac(proposition_id=proposition_id, x=columns[proposition_id][0], y=columns[proposition_id][1])
        for proposition_id in harvest.PROPOSITION_IDS
    }
    adjusted = harvest.holm_adjust({proposition_id: raw[proposition_id][3] for proposition_id in harvest.PROPOSITION_IDS})
    return [
        {
            "proposition_id": proposition_id,
            "beta": raw[proposition_id][0],
            "hac_standard_error": raw[proposition_id][1],
            "hac_confidence_interval_95": list(raw[proposition_id][2]),
            "raw_p_value_two_sided": raw[proposition_id][3],
            "holm_adjusted_p_value": adjusted[proposition_id],
            "classification": harvest.classify(
                beta=raw[proposition_id][0],
                interval=raw[proposition_id][2],
                holm_p=adjusted[proposition_id],
            ),
        }
        for proposition_id in harvest.PROPOSITION_IDS
    ]


def execute_verified_snapshot(*, snapshot_path: Path, execution_bridge_sha: str) -> dict[str, Any]:
    """Execute the frozen four-proposition Harvest against one verified snapshot.

    The caller must supply the finalized bridge commit SHA.  This function has
    no network, acquisition, materialization, or fallback path.
    """
    bridge_sha = _require_commit_sha(execution_bridge_sha)
    bars = _read_verified_bars(snapshot_path=Path(snapshot_path))
    rows = harvest._build_design_rows(bars_by_symbol=bars)
    results = _frozen_regressions(rows)
    if [result["proposition_id"] for result in results] != list(harvest.PROPOSITION_IDS):
        raise AssertionError("all and only the frozen proposition results are required")
    receipt: dict[str, Any] = {
        "experiment_id": harvest.EXPERIMENT_ID,
        "preregistration_digest": harvest.PREREGISTRATION_DIGEST,
        "canonical_execution_base": CANONICAL_EXECUTION_BASE,
        "reviewed_harvest_implementation_sha": REVIEWED_HARVEST_IMPLEMENTATION_SHA,
        "execution_bridge_sha": bridge_sha,
        "implementation_identity": bridge_sha,
        "execution_mode": "REAL_FROZEN_SNAPSHOT",
        "snapshot_id": harvest.EXPECTED_SNAPSHOT_ID,
        "snapshot_digest": harvest.EXPECTED_SNAPSHOT_DIGEST,
        "observation_count": harvest.OBSERVATION_COUNT,
        "hac_lag": harvest.HAC_LAG,
        "result_order": list(harvest.PROPOSITION_IDS),
        "ordered_proposition_ids": list(harvest.PROPOSITION_IDS),
        "results": results,
        "throughput": {
            "snapshot_reused": True,
            "new_data_acquisitions": 0,
            "new_data_qualification_phases": 0,
            "data_infrastructure_changes": 0,
        },
        "authority": harvest.AUTHORITY,
        "explicit": {
            "scientific_authority": "EXPLORATORY_ASSOCIATION_ONLY",
            "router_authority": "NONE",
            "qnty_authority": "NONE",
            "trading_authority": "NONE",
        },
    }
    receipt["result_digest"] = harvest.result_digest(receipt)
    return receipt
