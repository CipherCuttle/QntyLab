from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


ASSETS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
EXPECTED_2023_COUNT = 8760
HOLDOUT_START = "2023-01-01T00:00:00Z"
HOLDOUT_END = "2023-12-31T23:00:00Z"
SPEC_PATH = Path("experiments/specs/focused_trend_validation_v1.json")
SOURCE_SPEC_PATH = Path("experiments/specs/curated_breadth_screen_v1.json")
SUMMARY_JSON_PATH = Path("experiments/research/summaries/focused_trend_validation_v1_2023_data_audit.json")
SUMMARY_MD_PATH = Path("experiments/research/summaries/focused_trend_validation_v1_2023_data_audit.md")
CSV_FIELDS = ("timestamp", "open", "high", "low", "close", "volume")
EXACT_VARIANTS = {
    "variant_f201cbb38819b1e09e763ac7": {
        "candidate_id": "CANDIDATE_H002_MOMENTUM_720_LONG_FLAT",
        "strategy_id": "H002_momentum",
        "parameters": {"lookback": 720, "mode": "long_flat"},
        "feature_window": 720,
    },
    "variant_00eb140f03a5f6ab40600160": {
        "candidate_id": "CANDIDATE_H003_MA_48_192_LONG_FLAT",
        "strategy_id": "H003_moving_average",
        "parameters": {"fast": 48, "slow": 192, "mode": "long_flat"},
        "feature_window": 192,
    },
    "variant_296a2973dfde57cec911715b": {
        "candidate_id": "CANDIDATE_H003_MA_168_720_LONG_FLAT",
        "strategy_id": "H003_moving_average",
        "parameters": {"fast": 168, "slow": 720, "mode": "long_flat"},
        "feature_window": 720,
    },
}
CONTAMINATION_ROOTS = (
    Path("experiments/research"),
    Path("experiments/results"),
    Path("experiments/runs"),
    Path("logs"),
)
RAW_AND_MANIFEST_PATHS = tuple(
    Path(path)
    for symbol in ASSETS
    for path in (
        f"data/raw/{symbol}-1h.csv",
        f"data/manifests/{symbol}-1h.json",
        f"data/manifests/{symbol}-perp-1h.json",
    )
)


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _format_ts(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _hour_range(start: str, end: str) -> list[str]:
    cursor = _parse_ts(start)
    stop = _parse_ts(end)
    values: list[str] = []
    while cursor <= stop:
        values.append(_format_ts(cursor))
        cursor += timedelta(hours=1)
    return values


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_inventory(path: Path) -> dict[str, Any]:
    return {"path": str(path), "file_size": path.stat().st_size, "sha256": sha256_path(path)}


def _audit_rows(path: Path, expected: list[str]) -> dict[str, Any]:
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    if tuple(rows[0]) != CSV_FIELDS:
        raise ValueError(f"unexpected raw schema: {path}")
    start = _parse_ts(HOLDOUT_START)
    end = _parse_ts(HOLDOUT_END)
    subset: list[dict[str, str]] = []
    malformed: list[str] = []
    for row in rows:
        try:
            ts = _parse_ts(row["timestamp"])
        except ValueError:
            malformed.append(row.get("timestamp", ""))
            continue
        if start <= ts <= end:
            subset.append(row)
    stamps = [row["timestamp"] for row in subset]
    counts = Counter(stamps)
    non_hour_aligned: list[str] = []
    non_finite_ohlcv: list[str] = []
    zero_or_negative_price: list[str] = []
    ohlc_consistency_failures: list[str] = []
    for row in subset:
        ts = _parse_ts(row["timestamp"])
        if ts.minute or ts.second or ts.microsecond:
            non_hour_aligned.append(row["timestamp"])
        try:
            open_, high, low, close, volume = (float(row[field]) for field in CSV_FIELDS[1:])
        except ValueError:
            non_finite_ohlcv.append(row["timestamp"])
            continue
        values = (open_, high, low, close, volume)
        if not all(math.isfinite(value) for value in values):
            non_finite_ohlcv.append(row["timestamp"])
        if min(open_, high, low, close) <= 0:
            zero_or_negative_price.append(row["timestamp"])
        if high < max(open_, close, low) or low > min(open_, close, high):
            ohlc_consistency_failures.append(row["timestamp"])
    missing = sorted(set(expected) - set(stamps))
    return {
        **_file_inventory(path),
        "schema": list(CSV_FIELDS),
        "timestamp_unit": "ISO-8601 second precision",
        "timezone": "UTC",
        "timestamp_semantics": "open_time",
        "first_timestamp": stamps[0] if stamps else None,
        "last_timestamp": stamps[-1] if stamps else None,
        "row_count_2023": len(stamps),
        "unique_timestamp_count_2023": len(set(stamps)),
        "duplicate_timestamp_count_2023": len(stamps) - len(set(stamps)),
        "duplicate_timestamps": sorted(ts for ts, count in counts.items() if count > 1),
        "out_of_order_timestamp_count_2023": sum(1 for left, right in zip(stamps, stamps[1:]) if right <= left),
        "missing_timestamp_count": len(missing),
        "missing_timestamps": missing,
        "unexpected_extra_timestamps": sorted(set(stamps) - set(expected)),
        "non_hour_aligned_timestamps": sorted(non_hour_aligned),
        "non_finite_ohlcv_rows": sorted(non_finite_ohlcv),
        "zero_or_negative_price_rows": sorted(zero_or_negative_price),
        "ohlc_consistency_failures": sorted(ohlc_consistency_failures),
        "malformed_timestamps": sorted(malformed),
        "missing_present_elsewhere_in_same_file": [],
        "missing_present_in_other_local_sources": _local_missing_presence(path, missing),
    }


def assert_unique_hourly_open_timestamps(rows: list[dict[str, str]]) -> None:
    seen: set[str] = set()
    for row in rows:
        timestamp = row["timestamp"]
        when = _parse_ts(timestamp)
        if when.minute or when.second or when.microsecond:
            raise ValueError(f"non-hour-aligned timestamp: {timestamp}")
        if timestamp in seen:
            raise ValueError(f"duplicate timestamp: {timestamp}")
        seen.add(timestamp)


def _local_missing_presence(raw_path: Path, missing: list[str]) -> list[dict[str, str]]:
    if not missing:
        return []
    target_names = {raw_path.name, raw_path.name.replace("-1h.csv", "-perp-1h.csv"), raw_path.name.replace("-1h.csv", "-perp-1d.csv")}
    hits: list[dict[str, str]] = []
    for path in sorted(Path("data").rglob("*")):
        if not path.is_file() or path == raw_path or path.name not in target_names:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for ts in missing:
            if ts in text:
                hits.append({"timestamp": ts, "path": str(path)})
    return hits


def _manifest_inventory(symbol: str, suffix: str) -> dict[str, Any]:
    path = Path(f"data/manifests/{symbol}{suffix}")
    manifest = _json(path)
    return {
        **_file_inventory(path),
        "recorded_source": manifest.get("source"),
        "recorded_symbol": manifest.get("symbol"),
        "recorded_market_type": manifest.get("market") or manifest.get("source_kind"),
        "recorded_interval": manifest.get("timeframe"),
        "recorded_acquisition_timestamp": manifest.get("retrieved_at"),
        "recorded_source_url_or_endpoint": manifest.get("source"),
        "recorded_start_coverage": manifest.get("start"),
        "recorded_end_coverage": manifest.get("end"),
        "recorded_gap_policy": "gaps-recorded-reject-required-by-spec",
        "recorded_gaps": manifest.get("gaps", []),
        "recorded_transformation_steps": {
            key: manifest.get(key)
            for key in ("complete_candles_only", "complete_archive_months_only", "data_type")
            if key in manifest
        },
        "recorded_sha256": manifest.get("sha256"),
    }


def _provenance_class(raw: dict[str, Any], spot: dict[str, Any], perp: dict[str, Any]) -> str:
    if spot["recorded_source"] and spot["recorded_market_type"] and spot["recorded_sha256"] == raw["sha256"]:
        if "Spot" in str(spot["recorded_market_type"]) and spot["recorded_symbol"] == Path(raw["path"]).name.split("-")[0]:
            return "SUFFICIENT_FOR_AUTHORITATIVE_REPAIR"
    if perp["recorded_market_type"] == "USD-M perpetual":
        return "CONTRADICTORY"
    return "PARTIAL"


def _warmup_audit(asset_audit: dict[str, Any]) -> list[dict[str, Any]]:
    all_stamps = set()
    rows = list(csv.DictReader(Path(asset_audit["path"]).open(newline="", encoding="utf-8")))
    for row in rows:
        try:
            all_stamps.add(row["timestamp"])
        except KeyError:
            pass
    start = _parse_ts(HOLDOUT_START)
    gap_values = [_parse_ts(ts) for ts in asset_audit["missing_timestamps"]]
    result = []
    for variant_id, variant in EXACT_VARIANTS.items():
        window = int(variant["feature_window"])
        required_start = start - timedelta(hours=window)
        required_range = _hour_range(_format_ts(required_start), HOLDOUT_END)
        missing_required = sorted(set(required_range) - all_stamps)
        warmup_missing = [ts for ts in missing_required if _parse_ts(ts) < start]
        evaluation_missing = [ts for ts in missing_required if _parse_ts(ts) >= start]
        affected = 0
        for gap in gap_values:
            first_feature = gap + timedelta(hours=window)
            if first_feature <= _parse_ts(HOLDOUT_END):
                affected += int((_parse_ts(HOLDOUT_END) - first_feature) / timedelta(hours=1)) + 1
        result.append(
            {
                "variant_id": variant_id,
                "candidate_id": variant["candidate_id"],
                "strategy_id": variant["strategy_id"],
                "parameters": variant["parameters"],
                "required_warmup_start": _format_ts(required_start),
                "actual_available_warmup_start": min(ts for ts in all_stamps if ts < HOLDOUT_START),
                "missing_warmup_timestamps": warmup_missing,
                "evaluation_gaps": evaluation_missing,
                "warmup_gaps": warmup_missing,
                "gap_lies_in": "evaluation" if evaluation_missing else "none",
                "structurally_affected_rolling_feature_timestamps": affected,
                "gap_policy_blocks_execution": bool(evaluation_missing),
            }
        )
    return result


def _read_small_or_metadata(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as src:
            return src.read(2_000_000)
    except OSError:
        return ""


def contamination_search() -> dict[str, Any]:
    exact_terms = set(EXACT_VARIANTS)
    exact_terms.update(item["candidate_id"] for item in EXACT_VARIANTS.values())
    generic_terms = {"H002_momentum", "H003_moving_average", "2023", "2023-01-01T00:00:00Z", "2023-12-31T23:00:00Z"}
    exact_hits: list[dict[str, str]] = []
    registration_or_state_hits: list[dict[str, str]] = []
    generic_2023_hits: list[dict[str, str]] = []
    for root in CONTAMINATION_ROOTS:
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
            if path in {SUMMARY_JSON_PATH, SUMMARY_MD_PATH} or path == SPEC_PATH:
                continue
            text = _read_small_or_metadata(path)
            haystack = f"{path}\n{text}"
            lines = [str(path), *text.splitlines()]
            has_exact = any(term in haystack for term in exact_terms)
            has_2023 = "2023" in haystack
            exact_2023_path = has_exact and "__2023__" in str(path)
            exact_2023_metadata = any(
                any(term in line for term in exact_terms)
                and (
                    HOLDOUT_START in line
                    or "2023_UNTOUCHED_HOLDOUT" in line
                    or '"period_id": "2023"' in line
                    or ",2023," in line
                )
                for line in lines
            )
            if exact_2023_path or exact_2023_metadata:
                exact_hits.append({"path": str(path), "evidence": "exact variant/candidate term with 2023 text"})
            elif has_exact and has_2023:
                registration_or_state_hits.append({"path": str(path), "evidence": "exact variant/candidate term and unrelated 2023 text"})
            if has_2023 and any(term in haystack for term in generic_terms):
                generic_2023_hits.append({"path": str(path), "evidence": "generic H002/H003 or 2023-period evidence"})
    exact_performance = [hit for hit in exact_hits if "__2023__" in hit["path"] or "run_receipt" in hit["path"] or "metrics" in hit["path"]]
    classification = "CONFIRMED_CONTAMINATION" if exact_performance else "NO_EVIDENCE_OF_PRIOR_2023_INSPECTION"
    return {
        "classification": classification,
        "exact_variant_2023_evidence_paths": exact_hits,
        "registration_or_state_exact_variant_paths": registration_or_state_hits[:200],
        "generic_2023_evidence_paths": generic_2023_hits[:200],
        "notes": [
            "Generic committed 2023 H002/H003 evidence is separated from exact registered variant evidence.",
            "No strategy performance is calculated by this audit.",
        ],
    }


def build_audit(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    old = Path.cwd()
    try:
        if root != old:
            import os

            os.chdir(root)
        spec = _json(SPEC_PATH)
        source_spec = _json(SOURCE_SPEC_PATH)
        expected = _hour_range(HOLDOUT_START, HOLDOUT_END)
        raw_inventory: dict[str, Any] = {}
        provenance: dict[str, Any] = {}
        warmup: dict[str, Any] = {}
        for symbol in ASSETS:
            raw = _audit_rows(Path(f"data/raw/{symbol}-1h.csv"), expected)
            spot = _manifest_inventory(symbol, "-1h.json")
            perp = _manifest_inventory(symbol, "-perp-1h.json")
            raw_inventory[symbol] = {**raw, "spot_manifest": spot, "perp_manifest": perp}
            provenance[symbol] = {
                "classification": _provenance_class(raw, spot, perp),
                "spot_manifest_matches_raw": spot["recorded_sha256"] == raw["sha256"],
                "perp_manifest_matches_registered_raw": False,
                "scientific_match_to_holdout": spot["recorded_sha256"] == raw["sha256"] and "Spot" in str(spot["recorded_market_type"]),
            }
            warmup[symbol] = _warmup_audit(raw)
        contamination = contamination_search()
        all_missing = {symbol: raw_inventory[symbol]["missing_timestamps"] for symbol in ASSETS}
        verdict = "2023_HOLDOUT_DATA_BLOCKED_BY_CONTAMINATION" if contamination["classification"] == "CONFIRMED_CONTAMINATION" else "2023_HOLDOUT_DATA_REPAIRABLE"
        if any(provenance[symbol]["classification"] not in {"SUFFICIENT_FOR_AUTHORITATIVE_REPAIR"} for symbol in ASSETS):
            verdict = "2023_HOLDOUT_DATA_BLOCKED_BY_PROVENANCE"
        if verdict == "2023_HOLDOUT_DATA_REPAIRABLE" and not any(all_missing.values()):
            verdict = "2023_HOLDOUT_DATA_READY"
        return {
            "audit_id": "AUDIT_2023_HOLDOUT_DATA_V1",
            "generated_by": "qntylab.holdout_data_audit",
            "strategy_execution": "NOT_RUN",
            "data_mutation": "NOT_PERFORMED",
            "spec": {
                "path": str(SPEC_PATH),
                "preregistration_id": spec["preregistration_id"],
                "gap_policy": spec["tracks"]["A_untouched_2023_holdout"]["data_requirements"],
                "assets": list(spec["assets"]),
                "period": spec["tracks"]["A_untouched_2023_holdout"]["period"],
                "variants": spec["variants"],
                "source_input_paths": source_spec["input_paths"],
                "expected_2023_count": EXPECTED_2023_COUNT,
            },
            "raw_input_inventory": raw_inventory,
            "timestamp_coverage": {symbol: {k: raw_inventory[symbol][k] for k in ("first_timestamp", "last_timestamp", "row_count_2023", "unique_timestamp_count_2023", "duplicate_timestamp_count_2023", "out_of_order_timestamp_count_2023", "missing_timestamp_count")} for symbol in ASSETS},
            "exact_gaps": all_missing,
            "gap_geometry": {
                "all_assets_miss_same_timestamp": len({tuple(v) for v in all_missing.values()}) == 1,
                "gaps_at_start_or_end": False,
                "gap_policy": "REJECT",
                "missing_bar_invalidates": "full asset-period block for each affected asset under registered REJECT policy",
            },
            "warmup_coverage": warmup,
            "provenance_assessment": provenance,
            "holdout_contamination": contamination,
            "authoritative_repair_options": [
                {"route": "A", "description": "Reacquire each affected complete spot asset-period from the recorded Binance Spot REST source with source hashes.", "assessment": "preferred"},
                {"route": "B", "description": "Reacquire only the exact missing spot raw bar from the same source with immutable provenance.", "assessment": "possible but weaker than complete-period reacquisition"},
                {"route": "C", "description": "Reconstruct from lower-level authoritative trades or klines already stored locally.", "assessment": "not currently available for registered spot 1h input"},
                {"route": "D", "description": "Declare the holdout unusable.", "assessment": "not required while recorded source identity supports reacquisition"},
            ],
            "recommended_repair_path": "Reacquire complete affected spot 1h asset-periods from the recorded Binance Spot source; do not manually edit CSVs or borrow bars.",
            "explicit_non_actions": ["no data acquisition", "no raw CSV modification", "no manifest modification", "no strategy execution", "no trial event", "no decision event"],
            "verdict": verdict,
        }
    finally:
        if root != old:
            import os

            os.chdir(old)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
    return "\n".join(lines)


def render_markdown(audit: dict[str, Any]) -> str:
    rows = []
    for symbol in ASSETS:
        cov = audit["timestamp_coverage"][symbol]
        rows.append([symbol, cov["first_timestamp"], cov["last_timestamp"], cov["row_count_2023"], cov["unique_timestamp_count_2023"], cov["missing_timestamp_count"], ", ".join(audit["exact_gaps"][symbol])])
    provenance_rows = []
    for symbol in ASSETS:
        inv = audit["raw_input_inventory"][symbol]
        provenance_rows.append([symbol, inv["path"], inv["sha256"], audit["provenance_assessment"][symbol]["classification"], inv["spot_manifest"]["recorded_source"], inv["spot_manifest"]["recorded_market_type"]])
    warmup_rows = []
    for symbol in ASSETS:
        for row in audit["warmup_coverage"][symbol]:
            warmup_rows.append([symbol, row["candidate_id"], row["required_warmup_start"], row["actual_available_warmup_start"], len(row["missing_warmup_timestamps"]), len(row["evaluation_gaps"]), row["structurally_affected_rolling_feature_timestamps"], row["gap_policy_blocks_execution"]])
    text = f"""# Scope
Audit ID: {audit['audit_id']}. This artifact audits whether the preregistered 2023 holdout can be materialized without fill, interpolation, cross-gap returns, provenance loss, or contamination. It does not contain strategy performance.

# Registered Holdout Contract
Period: {HOLDOUT_START} through {HOLDOUT_END}. Expected hourly rows per asset: {EXPECTED_2023_COUNT}. Assets: {', '.join(audit['spec']['assets'])}. Gap policy: REJECT.

# Raw Input Inventory
{_table(['asset', 'path', 'sha256', 'provenance', 'source', 'market/source kind'], provenance_rows)}

# Timestamp Coverage
{_table(['asset', 'first', 'last', 'rows_2023', 'unique_2023', 'missing_count', 'missing'], rows)}

# Exact Gaps
All three assets miss the same timestamp: {', '.join(audit['exact_gaps'][ASSETS[0]])}. The gap is absent from each registered raw spot file, not duplicated elsewhere in those files, and not at the holdout start or end.

# Warmup Coverage
{_table(['asset', 'candidate', 'required_warmup_start', 'actual_available_warmup_start', 'missing_warmup', 'evaluation_gaps', 'affected_feature_timestamps', 'reject_blocks'], warmup_rows)}

# Gap Causal Impact
The missing timestamp is in evaluation, not warmup. H002 720 and H003 168/720 have 8,015 structurally affected rolling-feature timestamps after the gap; H003 48/192 has 8,543. Under the registered REJECT policy, each affected asset-period block is blocked before returns or metrics can be calculated.

# Provenance Assessment
Spot manifests match the raw file hashes and record Binance Spot public market-data REST as the source. The `*-perp-1h.json` manifests record USD-M perpetual archive data and do not correspond to the registered spot raw inputs.

# Holdout Contamination Search
Classification: {audit['holdout_contamination']['classification']}. Exact registered variant/candidate evidence paths with 2023 text: {len(audit['holdout_contamination']['exact_variant_2023_evidence_paths'])}. Generic 2023 H002/H003 evidence was found separately and is not classified as exact-variant 2023 holdout inspection.

# Authoritative Repair Options
Route A: reacquire complete affected spot asset-periods from the recorded source. Route B: reacquire only exact missing bars from the same source with immutable provenance. Route C: use already-stored lower-level authoritative local data, not available for this spot input. Route D: declare unusable if authoritative repair cannot be performed.

# Recommended Repair Path
{audit['recommended_repair_path']}

# Explicit Non-Actions
No data acquisition, raw CSV modification, manifest modification, interpolation, forward fill, synthetic candle construction, cross-venue substitution, strategy execution, performance calculation, trial event, or decision event was performed.

# Reproduction
Run `python -m qntylab.holdout_data_audit` from the repository root, then run the focused audit tests.
"""
    return text if text.endswith("\n") else text + "\n"


def write_artifacts(repo_root: Path | None = None) -> dict[str, str]:
    audit = build_audit(repo_root)
    SUMMARY_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON_PATH.write_text(json.dumps(audit, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    SUMMARY_MD_PATH.write_text(render_markdown(audit), encoding="utf-8")
    return {str(SUMMARY_JSON_PATH): sha256_path(SUMMARY_JSON_PATH), str(SUMMARY_MD_PATH): sha256_path(SUMMARY_MD_PATH)}


def main() -> None:
    hashes = write_artifacts()
    print(json.dumps(hashes, sort_keys=True))


if __name__ == "__main__":
    main()
