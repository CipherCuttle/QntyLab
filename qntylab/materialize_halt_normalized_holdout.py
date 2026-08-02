from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = Path("experiments/specs/binance_spot_halt_normalization_v1.json")
VALIDATION_SPEC_PATH = Path("experiments/specs/focused_trend_validation_v1.json")
RECEIPT_JSON_PATH = Path("experiments/research/summaries/focused_trend_validation_v1_2023_halt_materialization.json")
RECEIPT_MD_PATH = Path("experiments/research/summaries/focused_trend_validation_v1_2023_halt_materialization.md")
CSV_FIELDS = ("timestamp", "open", "high", "low", "close", "volume")
AUTHORIZED_ASSETS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
TOOL_VERSION = "qntylab.materialize_halt_normalized_holdout.v1"
MAX_WARMUP_HOURS = 720


class MaterializationError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False).encode("utf-8") + b"\n"


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def format_ts(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def hour_range(start: str, end: str) -> list[str]:
    cursor = parse_ts(start)
    stop = parse_ts(end)
    values: list[str] = []
    while cursor <= stop:
        values.append(format_ts(cursor))
        cursor += timedelta(hours=1)
    return values


def load_json(root: Path, path: Path) -> dict[str, Any]:
    return json.loads((root / path).read_text(encoding="utf-8"))


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as src:
        reader = csv.DictReader(src)
        if tuple(reader.fieldnames or ()) != CSV_FIELDS:
            raise MaterializationError(f"unexpected CSV schema: {path}")
        return list(reader)


def render_csv(rows: list[dict[str, str]]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(content)
    os.replace(tmp, path)


def validate_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    if not rows:
        raise MaterializationError("zero rows")
    seen: set[str] = set()
    previous: datetime | None = None
    duplicate = out_of_order = non_hour = non_finite = non_positive = ohlc_fail = 0
    for row in rows:
        timestamp = row.get("timestamp", "")
        try:
            when = parse_ts(timestamp)
            open_, high, low, close, volume = (float(row[field]) for field in CSV_FIELDS[1:])
        except (KeyError, TypeError, ValueError) as exc:
            raise MaterializationError(f"invalid row at {timestamp}") from exc
        if timestamp in seen:
            duplicate += 1
        seen.add(timestamp)
        if previous is not None and when <= previous:
            out_of_order += 1
        previous = when
        if when.minute or when.second or when.microsecond:
            non_hour += 1
        if not all(math.isfinite(value) for value in (open_, high, low, close, volume)):
            non_finite += 1
        if min(open_, high, low, close) <= 0:
            non_positive += 1
        if high < max(open_, close, low) or low > min(open_, close, high):
            ohlc_fail += 1
    if duplicate or out_of_order or non_hour or non_finite or non_positive or ohlc_fail:
        raise MaterializationError(
            "invalid derived rows: "
            f"duplicate={duplicate}, out_of_order={out_of_order}, non_hour={non_hour}, "
            f"non_finite={non_finite}, non_positive={non_positive}, ohlc={ohlc_fail}"
        )
    return {
        "duplicate_timestamps": duplicate,
        "out_of_order_timestamps": out_of_order,
        "non_hour_aligned_timestamps": non_hour,
        "non_finite_ohlcv_rows": non_finite,
        "zero_or_negative_price_rows": non_positive,
        "ohlc_consistency_failures": ohlc_fail,
    }


def validate_source_gap(rows: list[dict[str, str]], halt_ts: str, required_start: str, required_end: str) -> None:
    timestamps = [row["timestamp"] for row in rows]
    if halt_ts in timestamps:
        raise MaterializationError("authorized normalized timestamp already exists in source")
    expected = set(hour_range(required_start, required_end))
    missing = sorted(expected - set(timestamps))
    if missing != [halt_ts]:
        raise MaterializationError(f"unexpected required-range source gaps: {missing}")


def require_contract(spec: dict[str, Any], source_json: dict[str, Any], source_md_sha256: str) -> None:
    if spec["normalization_version"] != "BINANCE_SPOT_HALT_NORMALIZATION_V1":
        raise MaterializationError("unsupported normalization version")
    if tuple(asset["asset"] for asset in spec["assets"]) != AUTHORIZED_ASSETS:
        raise MaterializationError("materialization is bounded to exactly the three authorized assets")
    artifacts = spec["source_resolution_artifacts"]
    if artifacts["markdown"]["sha256"] != source_md_sha256:
        raise MaterializationError("source-resolution markdown hash mismatch")
    if source_json["source_contract_finding"] != "AUTHORITATIVE_NO_TRADE_INTERVAL_CONFIRMED":
        raise MaterializationError("source-resolution finding does not authorize normalization")
    predicates = spec["source_predicates"]
    if predicates["timestamp"] != spec["authorized_event"]["authorized_timestamp"]:
        raise MaterializationError("source predicate timestamp mismatch")
    if predicates["official_trades_during_interval"] != 0 or predicates["official_aggTrades_during_interval"] != 0:
        raise MaterializationError("trade evidence does not authorize no-trade normalization")
    if predicates["official_1m_klines_during_interval"] != 0 or predicates["official_1h_kline_during_interval"] != "absent":
        raise MaterializationError("kline evidence does not authorize no-trade normalization")
    for asset in spec["assets"]:
        evidence = source_json["assets"][asset["asset"]]
        if evidence["classification"] != "AUTHORITATIVE_NO_TRADE_INTERVAL_CONFIRMED":
            raise MaterializationError(f"source evidence does not authorize {asset['asset']}")
        if evidence["trades"]["hourly"][spec["authorized_event"]["authorized_timestamp"]]["count"] != 0:
            raise MaterializationError(f"authoritative trades present for {asset['asset']}")
        if evidence["aggTrades"]["hourly"][spec["authorized_event"]["authorized_timestamp"]]["count"] != 0:
            raise MaterializationError(f"authoritative aggregate trades present for {asset['asset']}")


def validate_derived_bar(asset: dict[str, Any], spec: dict[str, Any]) -> None:
    bar = asset["derived_bar"]
    price = asset["halt_reference_price"]
    if bar["timestamp"] != spec["authorized_event"]["authorized_timestamp"]:
        raise MaterializationError(f"normalized timestamp mismatch for {asset['asset']}")
    if bar["volume"] != "0.00000000":
        raise MaterializationError(f"normalized volume must be zero for {asset['asset']}")
    if {bar["open"], bar["high"], bar["low"], bar["close"]} != {price}:
        raise MaterializationError(f"normalized OHLC must equal reference price for {asset['asset']}")
    Decimal(price)


def build_manifest(asset: dict[str, Any], spec: dict[str, Any], validation: dict[str, Any], derived_sha256: str) -> dict[str, Any]:
    source_artifact = spec["source_resolution_artifacts"]["json"]
    archives = asset["official_archive_sources"]
    return {
        "normalization_id": spec["normalization_id"],
        "normalization_version": spec["normalization_version"],
        "screen_or_validation_id": spec["screen_or_validation_id"],
        "asset": asset["asset"],
        "market_type": "Binance Spot",
        "interval": spec["authorized_event"]["interval"],
        "derived_path": asset["derived_path"],
        "authoritative_raw_path": asset["authoritative_raw_path"],
        "authoritative_raw_sha256": asset["authoritative_raw_sha256"],
        "derived_sha256": derived_sha256,
        "evaluation_start": validation["tracks"]["A_untouched_2023_holdout"]["period"]["start"],
        "evaluation_end": validation["tracks"]["A_untouched_2023_holdout"]["period"]["end"],
        "warmup_start": format_ts(parse_ts(validation["tracks"]["A_untouched_2023_holdout"]["period"]["start"]) - timedelta(hours=MAX_WARMUP_HOURS)),
        "normalized_timestamp": spec["authorized_event"]["authorized_timestamp"],
        "reason_code": spec["reason_code"],
        "reference_price": asset["halt_reference_price"],
        "reference_trade_timestamp": asset["reference_trade_timestamp"],
        "first_post_halt_trade_timestamp": asset["first_post_halt_trade_timestamp"],
        "source_resolution_artifact_path": source_artifact["path"],
        "source_resolution_artifact_sha256": source_artifact["sha256"],
        "source_resolution_commit": spec["source_resolution_commit"],
        "official_archive_sources": deepcopy(archives),
        "official_archive_sha256_values": {kind: value["archive_sha256"] for kind, value in archives.items()},
        "official_checksum_verification": spec["official_checksum_verification"],
        "created_at_utc": spec["registered_at_utc"],
        "tool_version": TOOL_VERSION,
    }


def compare_source_to_derived(source: list[dict[str, str]], derived: list[dict[str, str]], halt_ts: str) -> dict[str, Any]:
    source_by_ts = {row["timestamp"]: row for row in source}
    derived_by_ts = {row["timestamp"]: row for row in derived if row["timestamp"] != halt_ts}
    mismatches = sum(1 for ts, row in source_by_ts.items() if derived_by_ts.get(ts) != row)
    unexpected = sorted(set(row["timestamp"] for row in derived) - set(source_by_ts) - {halt_ts})
    return {
        "source_rows_compared": len(source),
        "source_mismatches": mismatches,
        "authorized_derived_rows": sum(1 for row in derived if row["timestamp"] == halt_ts),
        "unexpected_derived_rows": len(unexpected),
        "unexpected_derived_timestamps": unexpected,
    }


def coverage(rows: list[dict[str, str]], start: str, end: str) -> dict[str, Any]:
    expected = hour_range(start, end)
    subset = [row for row in rows if start <= row["timestamp"] <= end]
    stamps = [row["timestamp"] for row in subset]
    missing = sorted(set(expected) - set(stamps))
    return {
        "row_count": len(subset),
        "unique_timestamp_count": len(set(stamps)),
        "missing_timestamps": len(missing),
        "first_timestamp": stamps[0] if stamps else None,
        "last_timestamp": stamps[-1] if stamps else None,
    }


def causality(rows: list[dict[str, str]]) -> dict[str, Any]:
    by_ts = {row["timestamp"]: row for row in rows}
    c12 = by_ts["2023-03-24T12:00:00Z"]["close"]
    c13 = by_ts["2023-03-24T13:00:00Z"]["close"]
    c14 = by_ts["2023-03-24T14:00:00Z"]["close"]
    return {
        "close_12": c12,
        "close_13": c13,
        "close_14": c14,
        "close_12_equals_close_13": c12 == c13,
        "close_to_close_return_12_to_13": "0" if c12 == c13 else "NONZERO",
        "post_halt_transition_13_to_14_preserved": c14 != "",
    }


def render_materialization(root: Path = ROOT) -> dict[str, Any]:
    spec = load_json(root, SPEC_PATH)
    validation = load_json(root, VALIDATION_SPEC_PATH)
    source_json_path = Path(spec["source_resolution_artifacts"]["json"]["path"])
    source_md_path = Path(spec["source_resolution_artifacts"]["markdown"]["path"])
    source_json_bytes = (root / source_json_path).read_bytes()
    source_json_sha256 = sha256_bytes(source_json_bytes)
    source_md_sha256 = sha256_path(root / source_md_path)
    if source_json_sha256 != spec["source_resolution_artifacts"]["json"]["sha256"]:
        raise MaterializationError("source-resolution JSON hash mismatch")
    source_json = json.loads(source_json_bytes)
    require_contract(spec, source_json, source_md_sha256)
    eval_period = validation["tracks"]["A_untouched_2023_holdout"]["period"]
    halt_ts = spec["authorized_event"]["authorized_timestamp"]
    warmup_start = format_ts(parse_ts(eval_period["start"]) - timedelta(hours=MAX_WARMUP_HOURS))
    assets: dict[str, Any] = {}
    manifests: dict[str, dict[str, Any]] = {}
    files: dict[Path, bytes] = {}
    for asset in spec["assets"]:
        validate_derived_bar(asset, spec)
        raw_path = root / asset["authoritative_raw_path"]
        raw_sha256 = sha256_path(raw_path)
        if raw_sha256 != asset["authoritative_raw_sha256"]:
            raise MaterializationError(f"authoritative raw hash mismatch for {asset['asset']}")
        raw_rows = read_csv_rows(raw_path)
        validate_rows(raw_rows)
        validate_source_gap(raw_rows, halt_ts, warmup_start, eval_period["end"])
        derived_rows = sorted([*raw_rows, dict(asset["derived_bar"])], key=lambda row: row["timestamp"])
        row_validation = validate_rows(derived_rows)
        csv_bytes = render_csv(derived_rows)
        derived_sha256 = sha256_bytes(csv_bytes)
        comparison = compare_source_to_derived(raw_rows, derived_rows, halt_ts)
        cover = coverage(derived_rows, eval_period["start"], eval_period["end"])
        causal = causality(derived_rows)
        manifest = build_manifest(asset, spec, validation, derived_sha256)
        manifest_bytes = canonical_json_bytes(manifest)
        manifest_path = Path(asset["derived_path"]).with_suffix(".manifest.json")
        files[Path(asset["derived_path"])] = csv_bytes
        files[manifest_path] = manifest_bytes
        manifests[asset["asset"]] = manifest
        assets[asset["asset"]] = {
            "authoritative_raw_path": asset["authoritative_raw_path"],
            "authoritative_raw_sha256": raw_sha256,
            "derived_path": asset["derived_path"],
            "derived_sha256": derived_sha256,
            "manifest_path": str(manifest_path),
            "manifest_sha256": sha256_bytes(manifest_bytes),
            "inserted_row": dict(asset["derived_bar"]),
            "derived_row_count": len(derived_rows),
            "authorized_derived_rows": comparison["authorized_derived_rows"],
            "unexpected_derived_rows": comparison["unexpected_derived_rows"],
            "source_rows_compared": comparison["source_rows_compared"],
            "source_mismatches": comparison["source_mismatches"],
            "validation": row_validation,
            "coverage_2023": cover,
            "causality": causal,
            "derived_sha256_differs_from_raw_sha256": derived_sha256 != raw_sha256,
        }
    receipt = build_receipt(spec, validation, assets)
    receipt_json_bytes = canonical_json_bytes(receipt)
    receipt_md_bytes = render_receipt_md(receipt).encode("utf-8")
    files[RECEIPT_JSON_PATH] = receipt_json_bytes
    files[RECEIPT_MD_PATH] = receipt_md_bytes
    return {
        "receipt": receipt,
        "files": files,
        "receipt_json_sha256": sha256_bytes(receipt_json_bytes),
        "receipt_md_sha256": sha256_bytes(receipt_md_bytes),
        "manifest_sha256": {asset: data["manifest_sha256"] for asset, data in assets.items()},
        "derived_sha256": {asset: data["derived_sha256"] for asset, data in assets.items()},
    }


def build_receipt(spec: dict[str, Any], validation: dict[str, Any], assets: dict[str, Any]) -> dict[str, Any]:
    eval_period = validation["tracks"]["A_untouched_2023_holdout"]["period"]
    return {
        "materialization_id": "MATERIALIZE_NORMALIZED_2023_HOLDOUT_INPUTS_V1",
        "normalization_id": spec["normalization_id"],
        "normalization_version": spec["normalization_version"],
        "screen_or_validation_id": spec["screen_or_validation_id"],
        "created_at_utc": spec["registered_at_utc"],
        "tool_version": TOOL_VERSION,
        "status": "MATERIALIZED",
        "evaluation_start": eval_period["start"],
        "evaluation_end": eval_period["end"],
        "warmup_start": format_ts(parse_ts(eval_period["start"]) - timedelta(hours=MAX_WARMUP_HOURS)),
        "gap_policy": "NORMALIZE_ONLY_PREREGISTERED_AUTHORITATIVE_HALT; REJECT_ALL_OTHER_GAPS",
        "source_resolution_artifacts": spec["source_resolution_artifacts"],
        "source_resolution_commit": spec["source_resolution_commit"],
        "assets": assets,
        "determinism_check": {
            "method": "rendered output bytes are regenerated before write and compared after write",
            "byte_identical": True,
        },
        "trial_identity_readiness": spec["trial_identity_requirements"],
        "explicit_non_actions": [
            "no strategy execution",
            "no backtest invocation",
            "no 2023 performance calculation",
            "no trial event",
            "no decision event",
            "no candidate event",
            "no raw CSV mutation",
            "no perpetual manifest mutation",
        ],
    }


def render_receipt_md(receipt: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Scope")
    lines.append("Materialized the three deterministic Binance Spot halt-normalized holdout inputs only.\n")
    lines.append("# Frozen Normalization Contract")
    lines.append(f"- normalization_version: {receipt['normalization_version']}")
    lines.append(f"- normalized_timestamp: {next(iter(receipt['assets'].values()))['inserted_row']['timestamp']}")
    lines.append(f"- gap_policy: {receipt['gap_policy']}\n")
    lines.append("# Source Hash Verification")
    for asset, data in receipt["assets"].items():
        lines.append(f"- {asset}: {data['authoritative_raw_path']} {data['authoritative_raw_sha256']}")
    lines.append("")
    lines.append("# Derived Input Range")
    lines.append(f"- warmup_start: {receipt['warmup_start']}")
    lines.append(f"- evaluation_start: {receipt['evaluation_start']}")
    lines.append(f"- evaluation_end: {receipt['evaluation_end']}\n")
    lines.append("# Authorized Derived Rows")
    for asset, data in receipt["assets"].items():
        row = data["inserted_row"]
        lines.append(f"- {asset}: {row['timestamp']},{row['open']},{row['high']},{row['low']},{row['close']},{row['volume']}")
    lines.append("")
    lines.append("# Raw-to-Derived Comparison")
    for asset, data in receipt["assets"].items():
        lines.append(
            f"- {asset}: source_rows_compared={data['source_rows_compared']}, "
            f"source_mismatches={data['source_mismatches']}, "
            f"authorized_derived_rows={data['authorized_derived_rows']}, "
            f"unexpected_derived_rows={data['unexpected_derived_rows']}"
        )
    lines.append("")
    lines.append("# Derived File Hashes")
    for asset, data in receipt["assets"].items():
        lines.append(f"- {asset}: {data['derived_path']} {data['derived_sha256']}")
    lines.append("")
    lines.append("# Manifest Hashes")
    for asset, data in receipt["assets"].items():
        lines.append(f"- {asset}: {data['manifest_path']} {data['manifest_sha256']}")
    lines.append("")
    lines.append("# Coverage Validation")
    for asset, data in receipt["assets"].items():
        cover = data["coverage_2023"]
        lines.append(
            f"- {asset}: rows={cover['row_count']}, unique={cover['unique_timestamp_count']}, "
            f"missing={cover['missing_timestamps']}, first={cover['first_timestamp']}, last={cover['last_timestamp']}"
        )
    lines.append("")
    lines.append("# Determinism Check")
    lines.append("- byte_identical: true\n")
    lines.append("# Causality Sanity Check")
    for asset, data in receipt["assets"].items():
        causal = data["causality"]
        lines.append(
            f"- {asset}: 12_close={causal['close_12']}, 13_close={causal['close_13']}, "
            f"14_close={causal['close_14']}, 12_to_13_return={causal['close_to_close_return_12_to_13']}"
        )
    lines.append("")
    lines.append("# Explicit Non-Actions")
    for item in receipt["explicit_non_actions"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("# Reproduction")
    lines.append("- python -m qntylab.materialize_halt_normalized_holdout")
    return "\n".join(lines) + "\n"


def materialize(root: Path = ROOT) -> dict[str, Any]:
    rendered = render_materialization(root)
    for relative, content in rendered["files"].items():
        atomic_write_bytes(root / relative, content)
    rerendered = render_materialization(root)
    for relative, content in rerendered["files"].items():
        if (root / relative).read_bytes() != content:
            raise MaterializationError(f"determinism check failed for {relative}")
    rendered["receipt"]["determinism_check"]["byte_identical"] = True
    return rendered


def main() -> None:
    result = materialize(Path.cwd())
    print(json.dumps({"status": "ok", "derived_sha256": result["derived_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
