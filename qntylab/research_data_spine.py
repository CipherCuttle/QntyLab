"""Immutable, verified OHLCV snapshot seam for Research Data Spine V0.

This module is deliberately a local, bounded infrastructure primitive.  It
materializes one fixed logical relation into Parquet and verifies it before a
consumer can read a bounded window.  It has no network or research-outcome
channel.
"""
from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

import polars as pl


SCHEMA_VERSION = "RESEARCH_DATA_SPINE_V0"
DATASET_ID = "FUNDING_PRESSURE_V1_OHLCV_20_SYMBOL"
RECIPE_ID = "qntylab.research_data_spine"
RECIPE_VERSION = "v0"
INTERVAL = timedelta(hours=1)
SOURCE_FIELDS = ("timestamp", "open", "high", "low", "close", "volume")
LOGICAL_FIELDS = (
    "instrument_instance_id",
    "symbol",
    "bar_open_time",
    "bar_close_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
)
SCHEMA_IDENTITY = {"schema_version": SCHEMA_VERSION, "columns": list(LOGICAL_FIELDS), "types": ["utf8"] * len(LOGICAL_FIELDS)}


class ResearchDataSpineError(RuntimeError):
    """A snapshot or its bounded input contract is invalid."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _sha_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ResearchDataSpineError(f"canonical UTC Z timestamp required: {value!r}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResearchDataSpineError(f"invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.astimezone(UTC) != parsed:
        raise ResearchDataSpineError(f"UTC timestamp required: {value!r}")
    if parsed.minute or parsed.second or parsed.microsecond:
        raise ResearchDataSpineError(f"hour-aligned timestamp required: {value!r}")
    return parsed


def _stamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def instrument_instance_id(symbol: str) -> str:
    if not isinstance(symbol, str) or not symbol or symbol.strip() != symbol:
        raise ResearchDataSpineError(f"invalid symbol: {symbol!r}")
    return f"binance-usdm-perpetual-funding-pressure-v1:{symbol}"


def _validate_ohlcv(row: Mapping[str, str]) -> None:
    if set(row) != set(SOURCE_FIELDS):
        raise ResearchDataSpineError(f"source row fields must be exactly {list(SOURCE_FIELDS)}")
    _timestamp(row["timestamp"])
    try:
        values = {field: Decimal(row[field]) for field in SOURCE_FIELDS[1:]}
    except (InvalidOperation, ValueError) as exc:
        raise ResearchDataSpineError("OHLCV values must be finite decimal lexemes") from exc
    if not all(value.is_finite() for value in values.values()) or min(values.values()) < 0:
        raise ResearchDataSpineError("OHLCV values must be finite and non-negative")
    if min(values["open"], values["high"], values["low"], values["close"]) <= 0:
        raise ResearchDataSpineError("OHLC prices must be positive")
    if values["high"] < max(values["open"], values["low"], values["close"]) or values["low"] > min(values["open"], values["high"], values["close"]):
        raise ResearchDataSpineError("OHLC ordering is invalid")


def _logical_rows(symbol: str, source_rows: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    if not source_rows:
        raise ResearchDataSpineError(f"empty source partition: {symbol}")
    result: list[dict[str, str]] = []
    for source in source_rows:
        _validate_ohlcv(source)
        opened = _timestamp(source["timestamp"])
        result.append(
            {
                "instrument_instance_id": instrument_instance_id(symbol),
                "symbol": symbol,
                "bar_open_time": source["timestamp"],
                "bar_close_time": _stamp(opened + INTERVAL),
                "open": source["open"],
                "high": source["high"],
                "low": source["low"],
                "close": source["close"],
                "volume": source["volume"],
            }
        )
    opens = [_timestamp(row["bar_open_time"]) for row in result]
    if len(set(opens)) != len(opens):
        raise ResearchDataSpineError(f"duplicate bar opening time: {symbol}")
    if opens != sorted(opens):
        raise ResearchDataSpineError(f"source bars are not in strict timestamp order: {symbol}")
    if any(later - earlier != INTERVAL for earlier, later in zip(opens, opens[1:])):
        raise ResearchDataSpineError(f"hourly coverage gap: {symbol}")
    return result


def _partition_payload(rows: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "schema_identity": SCHEMA_IDENTITY,
        "partition_identity": {"instrument_instance_id": rows[0]["instrument_instance_id"], "symbol": rows[0]["symbol"]},
        "ordered_rows": rows,
    }


def _coverage(rows: list[dict[str, str]]) -> dict[str, Any]:
    return {"interval": "PT1H", "gap_policy": "REJECT", "first_bar_open_time": rows[0]["bar_open_time"], "last_bar_open_time": rows[-1]["bar_open_time"], "continuous": True}


def _partition_manifest(rows: list[dict[str, str]]) -> dict[str, Any]:
    symbol = rows[0]["symbol"]
    return {
        "partition_id": f"symbol={symbol}",
        "relative_path": f"partitions/{symbol}.parquet",
        "instrument_identity": {"instrument_instance_id": rows[0]["instrument_instance_id"], "symbol": symbol},
        "logical_digest": _digest(_partition_payload(rows)),
        "parquet_byte_sha256": None,
        "row_count": len(rows),
        "first_bar_open_time": rows[0]["bar_open_time"],
        "last_bar_open_time": rows[-1]["bar_open_time"],
        "schema_identity": SCHEMA_IDENTITY,
        "coverage": _coverage(rows),
    }


def _snapshot_semantics(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Identity data only: never incidental Parquet bytes or runtime details."""
    return {
        "schema_version": manifest["schema_version"],
        "dataset_id": manifest["dataset_id"],
        "source_certificate_identity": manifest["source_certificate_identity"],
        "source_evidence_digest": manifest["source_evidence_digest"],
        "ordered_partitions": [
            {
                "partition_id": part["partition_id"],
                "instrument_identity": part["instrument_identity"],
                "logical_digest": part["logical_digest"],
                "row_count": part["row_count"],
                "first_bar_open_time": part["first_bar_open_time"],
                "last_bar_open_time": part["last_bar_open_time"],
                "schema_identity": part["schema_identity"],
                "coverage": part["coverage"],
            }
            for part in manifest["ordered_partitions"]
        ],
        "time_semantics": manifest["time_semantics"],
        "recipe": manifest["recipe"],
    }


def _snapshot_digest(manifest: Mapping[str, Any]) -> str:
    return _digest(_snapshot_semantics(manifest))


def _validate_manifest_shape(manifest: Mapping[str, Any]) -> None:
    required = {"schema_version", "dataset_id", "snapshot_id", "snapshot_digest", "source_certificate_identity", "source_evidence_digest", "ordered_partitions", "time_semantics", "recipe", "writer_runtime"}
    if set(manifest) != required:
        raise ResearchDataSpineError("manifest fields are not the frozen V0 shape")
    if manifest["schema_version"] != SCHEMA_VERSION or manifest["dataset_id"] != DATASET_ID:
        raise ResearchDataSpineError("unsupported snapshot schema or dataset")
    parts = manifest["ordered_partitions"]
    if not isinstance(parts, list) or not parts:
        raise ResearchDataSpineError("non-empty ordered partitions required")
    symbols = [part.get("instrument_identity", {}).get("symbol") for part in parts]
    if symbols != sorted(symbols) or len(symbols) != len(set(symbols)):
        raise ResearchDataSpineError("partitions must have unique canonical symbol order")


def _as_utf8_frame(rows: list[dict[str, str]]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema={field: pl.String for field in LOGICAL_FIELDS}, strict=True).select(LOGICAL_FIELDS)


def _rows_from_frame(frame: pl.DataFrame) -> list[dict[str, str]]:
    if list(frame.schema) != list(LOGICAL_FIELDS) or any(dtype != pl.String for dtype in frame.schema.values()):
        raise ResearchDataSpineError("stored Parquet schema does not match frozen logical schema")
    return [{field: row[field] for field in LOGICAL_FIELDS} for row in frame.to_dicts()]


def verify_snapshot(snapshot_path: Path, expected_snapshot_digest: str) -> dict[str, Any]:
    """Verify a whole V0 snapshot before any consumer receives rows."""
    path = Path(snapshot_path)
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchDataSpineError("snapshot manifest is unreadable") from exc
    _validate_manifest_shape(manifest)
    actual_digest = _snapshot_digest(manifest)
    if expected_snapshot_digest != actual_digest or manifest["snapshot_digest"] != actual_digest:
        raise ResearchDataSpineError("snapshot digest mismatch")
    if manifest["snapshot_id"] != f"rds-v0-{actual_digest}":
        raise ResearchDataSpineError("snapshot id does not bind snapshot digest")
    for part in manifest["ordered_partitions"]:
        target = path / part["relative_path"]
        if not target.is_file() or _sha_file(target) != part["parquet_byte_sha256"]:
            raise ResearchDataSpineError(f"Parquet byte integrity failed: {part.get('partition_id')}")
        try:
            rows = _rows_from_frame(pl.read_parquet(target))
        except Exception as exc:  # Polars provides version-specific exceptions.
            raise ResearchDataSpineError(f"Parquet read/schema failed: {part.get('partition_id')}") from exc
        identity = part["instrument_identity"]
        if not rows or any(row["symbol"] != identity["symbol"] or row["instrument_instance_id"] != identity["instrument_instance_id"] for row in rows):
            raise ResearchDataSpineError(f"stored partition identity failed: {part.get('partition_id')}")
        if rows != sorted(rows, key=lambda row: row["bar_open_time"]):
            raise ResearchDataSpineError(f"stored partition ordering failed: {part.get('partition_id')}")
        source_rows = [{"timestamp": row["bar_open_time"], **{field: row[field] for field in SOURCE_FIELDS[1:]}} for row in rows]
        checked = _logical_rows(identity["symbol"], source_rows)
        if rows != checked or _digest(_partition_payload(rows)) != part["logical_digest"]:
            raise ResearchDataSpineError(f"logical partition integrity failed: {part.get('partition_id')}")
        if _coverage(rows) != part["coverage"]:
            raise ResearchDataSpineError(f"partition coverage failed: {part.get('partition_id')}")
    return manifest


def materialize_snapshot(*, source_rows_by_symbol: Mapping[str, Sequence[Mapping[str, str]]], expected_symbols: Sequence[str], source_certificate_identity: str, source_evidence_digest: str, evidence_root: Path) -> dict[str, Any]:
    """Materialize one local snapshot, rejecting every unfrozen input shape."""
    if not isinstance(source_certificate_identity, str) or len(source_certificate_identity) != 71 or not source_certificate_identity.startswith("sha256:") or any(char not in "0123456789abcdef" for char in source_certificate_identity[7:]):
        raise ResearchDataSpineError("source certificate identity must be a sha256 identifier")
    if not isinstance(source_evidence_digest, str) or len(source_evidence_digest) != 71 or not source_evidence_digest.startswith("sha256:") or any(char not in "0123456789abcdef" for char in source_evidence_digest[7:]):
        raise ResearchDataSpineError("source evidence digest must be a sha256 identifier")
    expected = list(expected_symbols)
    if not expected or expected != sorted(expected) or len(expected) != len(set(expected)):
        raise ResearchDataSpineError("expected symbols must be a non-empty unique canonical-order sequence")
    if sorted(source_rows_by_symbol) != expected:
        raise ResearchDataSpineError("source composition does not match the frozen expected symbols")
    logical = {symbol: _logical_rows(symbol, rows) for symbol, rows in source_rows_by_symbol.items()}
    parts = [_partition_manifest(logical[symbol]) for symbol in sorted(logical)]
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": DATASET_ID,
        "snapshot_id": None,
        "snapshot_digest": None,
        "source_certificate_identity": source_certificate_identity,
        "source_evidence_digest": source_evidence_digest,
        "ordered_partitions": parts,
        "time_semantics": {"bar_open_time": "SOURCE_BAR_OPEN_TIME", "bar_close_time": "bar_open_time + PT1H", "safe_known_after": ">= bar_close_time", "availability_claim": "NO_HISTORICAL_ARCHIVE_OR_VENDOR_AVAILABILITY_RECONSTRUCTION"},
        "recipe": {"id": RECIPE_ID, "version": RECIPE_VERSION, "logical_schema_identity": SCHEMA_IDENTITY},
        "writer_runtime": {"library": "polars", "version": pl.__version__, "format": "parquet", "compression": "zstd", "statistics": True, "row_group_size": 10_000},
    }
    digest = _snapshot_digest(manifest)
    manifest["snapshot_digest"] = digest
    manifest["snapshot_id"] = f"rds-v0-{digest}"
    root = Path(evidence_root)
    target = root / "snapshots" / manifest["snapshot_id"]
    if target.exists():
        verify_snapshot(target, digest)
        return {"snapshot_path": target, "snapshot_id": manifest["snapshot_id"], "snapshot_digest": digest, "reused": True, "manifest": verify_snapshot(target, digest)}
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rds-v0-", dir=target.parent) as temp_name:
        temporary = Path(temp_name)
        (temporary / "partitions").mkdir()
        for part in parts:
            symbol = part["instrument_identity"]["symbol"]
            output = temporary / part["relative_path"]
            _as_utf8_frame(logical[symbol]).write_parquet(output, compression="zstd", statistics=True, row_group_size=10_000, use_pyarrow=False)
            part["parquet_byte_sha256"] = _sha_file(output)
        (temporary / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n", encoding="utf-8")
        if target.exists():
            verify_snapshot(target, digest)
        else:
            temporary.replace(target)
    verified = verify_snapshot(target, digest)
    return {"snapshot_path": target, "snapshot_id": manifest["snapshot_id"], "snapshot_digest": digest, "reused": False, "manifest": verified}


def _certificate_identity(certificate: Mapping[str, Any]) -> str:
    declared = certificate.get("pit_coverage_certificate_v1_digest")
    body = {key: value for key, value in certificate.items() if key != "pit_coverage_certificate_v1_digest"}
    actual = "sha256:" + _digest(body)
    if declared != actual:
        raise ResearchDataSpineError("source certificate digest mismatch")
    return actual


def _load_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
    except OSError as exc:
        raise ResearchDataSpineError(f"cannot read certified source: {path}") from exc
    if not rows or any(set(row) != set(SOURCE_FIELDS) for row in rows):
        raise ResearchDataSpineError(f"certified source schema mismatch: {path}")
    return [{field: row[field] for field in SOURCE_FIELDS} for row in rows]


def materialize_certified_funding_pressure_v1(*, repository_root: Path, evidence_root: Path) -> dict[str, Any]:
    """Materialize the sole real V0 composition from its local certified evidence."""
    root = Path(repository_root)
    base = root / "experiments/research/jigsaw_funding_pressure_volatility_v0"
    try:
        certificate = json.loads((base / "pit_coverage_certificate_v1.json").read_text(encoding="utf-8"))
        extension = json.loads((base / "pit_coverage_evidence_v1/extension_manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchDataSpineError("certified Funding Pressure evidence is unavailable") from exc
    certificate_identity = _certificate_identity(certificate)
    if "sha256:" + _digest(extension) != certificate.get("extension_manifest_digest"):
        raise ResearchDataSpineError("extension manifest digest mismatch")
    census = certificate.get("ohlcv_census")
    if not isinstance(census, list) or len(census) != 20:
        raise ResearchDataSpineError("exact 20-symbol certified panel required")
    extension_rows = extension.get("rows")
    if not isinstance(extension_rows, list):
        raise ResearchDataSpineError("extension rows are unavailable")
    extension_by_symbol = {row.get("symbol"): {field: row.get(field) for field in SOURCE_FIELDS if field != "timestamp"} | {"timestamp": row.get("timestamp")} for row in extension_rows}
    if len(extension_by_symbol) != 20:
        raise ResearchDataSpineError("extension must contain exactly one row per symbol")
    source_rows: dict[str, list[dict[str, str]]] = {}
    for item in census:
        symbol = item.get("symbol")
        relative = item.get("v0_normalized_path")
        if not isinstance(symbol, str) or not isinstance(relative, str):
            raise ResearchDataSpineError("invalid certified census entry")
        path = base / relative
        if _sha_file(path) != item.get("v0_normalized_sha256"):
            raise ResearchDataSpineError(f"source substitution or mutation: {symbol}")
        prefix = extension_by_symbol.get(symbol)
        if prefix is None or any(not isinstance(value, str) for value in prefix.values()):
            raise ResearchDataSpineError(f"extension identity mismatch: {symbol}")
        source_rows[symbol] = [prefix, *_load_csv(path)]
        logical = _logical_rows(symbol, source_rows[symbol])
        if len(logical) != item.get("rows_per_symbol") or logical[0]["bar_open_time"] != item.get("source_bar_open_start") or logical[-1]["bar_open_time"] != item.get("source_bar_open_end"):
            raise ResearchDataSpineError(f"certified coverage mismatch: {symbol}")
    return materialize_snapshot(source_rows_by_symbol=source_rows, expected_symbols=sorted(source_rows), source_certificate_identity=certificate_identity, source_evidence_digest=certificate["ohlcv_evidence_set_digest_v1"], evidence_root=evidence_root)


def read_window(*, snapshot_path: Path, expected_snapshot_digest: str, requested_symbols: Sequence[str], start: str, end: str) -> pl.DataFrame:
    """Read only a certified inclusive symbol/time window; no best-effort mode."""
    manifest = verify_snapshot(Path(snapshot_path), expected_snapshot_digest)
    symbols = list(requested_symbols)
    if not symbols or symbols != sorted(symbols) or len(symbols) != len(set(symbols)):
        raise ResearchDataSpineError("requested symbols must be a unique canonical-order sequence")
    start_at, end_at = _timestamp(start), _timestamp(end)
    if start_at > end_at:
        raise ResearchDataSpineError("requested window start must not follow end")
    by_symbol = {part["instrument_identity"]["symbol"]: part for part in manifest["ordered_partitions"]}
    frames = []
    for symbol in symbols:
        part = by_symbol.get(symbol)
        if part is None:
            raise ResearchDataSpineError(f"symbol is outside snapshot composition: {symbol}")
        if start < part["first_bar_open_time"] or end > part["last_bar_open_time"]:
            raise ResearchDataSpineError(f"requested time window is outside certified coverage: {symbol}")
        frames.append(pl.read_parquet(Path(snapshot_path) / part["relative_path"]).filter((pl.col("bar_open_time") >= start) & (pl.col("bar_open_time") <= end)))
    return pl.concat(frames, how="vertical").sort(["instrument_instance_id", "bar_open_time"])


def funding_pressure_ohlcv_window_adapter(**kwargs: Any) -> dict[str, Any]:
    """Consumer A: shape-only adapter; it computes no funding state or outcome."""
    frame = read_window(**kwargs)
    manifest = verify_snapshot(Path(kwargs["snapshot_path"]), kwargs["expected_snapshot_digest"])
    return {"snapshot_id": manifest["snapshot_id"], "snapshot_digest": manifest["snapshot_digest"], "bars": frame.select(["symbol", "bar_open_time", "bar_close_time", "close"]).to_dicts()}


def generic_panel_window_consumer(**kwargs: Any) -> dict[str, Any]:
    """Consumer B: independent bounded panel reader; it makes no market claim."""
    frame = read_window(**kwargs)
    manifest = verify_snapshot(Path(kwargs["snapshot_path"]), kwargs["expected_snapshot_digest"])
    return {"snapshot_id": manifest["snapshot_id"], "snapshot_digest": manifest["snapshot_digest"], "row_count": frame.height, "symbols": frame.get_column("symbol").unique().sort().to_list()}


def default_evidence_root() -> Path:
    configured = os.environ.get("QNTYLAB_EVIDENCE_ROOT")
    return Path(configured) if configured else Path.home() / ".qntylab" / "evidence"
