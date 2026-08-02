from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable


ASSETS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
AUDIT_DATE = "2023-03-24"
GAP_HOUR = "2023-03-24T13:00:00Z"
WINDOW_HOURS = (
    "2023-03-24T11:00:00Z",
    "2023-03-24T12:00:00Z",
    "2023-03-24T13:00:00Z",
    "2023-03-24T14:00:00Z",
    "2023-03-24T15:00:00Z",
)
SPOT_ARCHIVE_ROOT = "https://data.binance.vision/data/spot/daily"
SPOT_REST_ROOT = "https://data-api.binance.vision"
SUMMARY_JSON_PATH = Path("experiments/research/summaries/focused_trend_validation_v1_2023_source_resolution.json")
SUMMARY_MD_PATH = Path("experiments/research/summaries/focused_trend_validation_v1_2023_source_resolution.md")
RAW_PATHS = tuple(Path(f"data/raw/{symbol}-1h.csv") for symbol in ASSETS)
SPEC_PATH = Path("experiments/specs/focused_trend_validation_v1.json")
LEDGER_PATHS = (
    Path("experiments/research/candidates.jsonl"),
    Path("experiments/research/decisions.jsonl"),
    Path("experiments/research/trials/2026.jsonl"),
)
PERP_MANIFEST_PATHS = tuple(Path(f"data/manifests/{symbol}-perp-1h.json") for symbol in ASSETS)


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def format_ts(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def hour_key_from_ms(value: str | int) -> str:
    dt = datetime.fromtimestamp(int(value) / 1000, UTC).replace(minute=0, second=0, microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def ms(value: str) -> int:
    return int(parse_ts(value).timestamp() * 1000)


def default_fetch(url: str) -> HttpResponse:
    request = urllib.request.Request(url, headers={"User-Agent": "qntylab-source-resolution/1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status = int(getattr(response, "status", response.getcode()))
            return HttpResponse(status=status, body=response.read())
    except urllib.error.HTTPError as exc:
        return HttpResponse(status=int(exc.code), body=exc.read())


def require_three_assets(assets: tuple[str, ...] = ASSETS) -> None:
    if assets != ASSETS or len(assets) != 3:
        raise ValueError("source resolution is bounded to exactly BTCUSDT, ETHUSDT, SOLUSDT")


def require_spot_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc not in {"data.binance.vision", "data-api.binance.vision"}:
        raise ValueError(f"non-Binance authoritative source rejected: {url}")
    if "/futures/" in parsed.path or "/um/" in parsed.path or "fapi" in parsed.path:
        raise ValueError(f"Binance Futures source rejected: {url}")
    if parsed.netloc == "data.binance.vision" and "/data/spot/" not in parsed.path:
        raise ValueError(f"non-Spot archive source rejected: {url}")
    if parsed.netloc == "data-api.binance.vision" and not parsed.path.startswith("/api/v3/"):
        raise ValueError(f"non-Spot REST source rejected: {url}")


def archive_url(symbol: str, kind: str) -> str:
    if kind == "trades":
        return f"{SPOT_ARCHIVE_ROOT}/trades/{symbol}/{symbol}-trades-{AUDIT_DATE}.zip"
    if kind == "aggTrades":
        return f"{SPOT_ARCHIVE_ROOT}/aggTrades/{symbol}/{symbol}-aggTrades-{AUDIT_DATE}.zip"
    if kind == "klines_1m":
        return f"{SPOT_ARCHIVE_ROOT}/klines/{symbol}/1m/{symbol}-1m-{AUDIT_DATE}.zip"
    if kind == "klines_1h":
        return f"{SPOT_ARCHIVE_ROOT}/klines/{symbol}/1h/{symbol}-1h-{AUDIT_DATE}.zip"
    raise ValueError(f"unknown archive kind: {kind}")


def fetch_to_tmp(url: str, tmp_root: Path, fetch: Callable[[str], HttpResponse]) -> dict[str, Any]:
    require_spot_url(url)
    response = fetch(url)
    name = urllib.parse.urlparse(url).path.strip("/").replace("/", "__")
    path = tmp_root / name
    path.write_bytes(response.body)
    return {
        "url": url,
        "tmp_path": str(path),
        "status": response.status,
        "byte_count": len(response.body),
        "sha256": sha256_bytes(response.body),
    }


def official_checksum_hash(checksum_bytes: bytes) -> str:
    text = checksum_bytes.decode("utf-8").strip()
    if not text:
        raise ValueError("empty official checksum")
    return text.split()[0]


def verify_archive_checksum(archive: dict[str, Any], checksum: dict[str, Any]) -> dict[str, Any]:
    if archive["status"] != 200 or checksum["status"] != 200:
        raise ValueError("archive and official checksum must both be HTTP 200")
    official = official_checksum_hash(Path(checksum["tmp_path"]).read_bytes())
    if archive["sha256"] != official:
        raise ValueError("official checksum mismatch")
    return {
        "archive_url": archive["url"],
        "checksum_url": checksum["url"],
        "archive_status": archive["status"],
        "checksum_status": checksum["status"],
        "archive_byte_count": archive["byte_count"],
        "checksum_byte_count": checksum["byte_count"],
        "archive_sha256": archive["sha256"],
        "checksum_file_sha256": checksum["sha256"],
        "official_sha256": official,
        "verified": True,
    }


def read_zip_csv_rows(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as zf:
        names = sorted(name for name in zf.namelist() if not name.endswith("/"))
        if len(names) != 1:
            raise ValueError(f"expected one CSV member in {path}")
        with zf.open(names[0]) as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8", newline="")
            return [row for row in csv.reader(text)]


def decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.00000001")), "f")


def empty_hour_stats() -> dict[str, Any]:
    return {
        "count": 0,
        "first_trade_timestamp": None,
        "last_trade_timestamp": None,
        "base_volume": "0.00000000",
        "quote_volume": "0.00000000",
    }


def hourly_trade_stats(rows: list[list[str]], kind: str) -> tuple[dict[str, Any], dict[str, Any]]:
    stats = {hour: empty_hour_stats() for hour in WINDOW_HOURS}
    last_before: dict[str, Any] | None = None
    first_after: dict[str, Any] | None = None
    gap_start = parse_ts(GAP_HOUR)
    gap_end = gap_start + timedelta(hours=1)
    for row in rows:
        if not row:
            continue
        if row[0] == "id" or row[0] == "agg_trade_id":
            continue
        if kind == "trades":
            price = Decimal(row[1])
            qty = Decimal(row[2])
            quote = Decimal(row[3])
            timestamp_ms = int(row[4])
            identifier = row[0]
        elif kind == "aggTrades":
            price = Decimal(row[1])
            qty = Decimal(row[2])
            quote = price * qty
            timestamp_ms = int(row[5])
            identifier = row[0]
        else:
            raise ValueError(f"unknown trade kind: {kind}")
        timestamp = datetime.fromtimestamp(timestamp_ms / 1000, UTC)
        trade = {
            "id": identifier,
            "timestamp": format_ts(timestamp),
            "price": str(price),
            "base_quantity": str(qty),
            "quote_quantity": decimal_text(quote),
        }
        if timestamp < gap_start:
            last_before = trade
        if timestamp >= gap_end and first_after is None:
            first_after = trade
        hour = hour_key_from_ms(timestamp_ms)
        if hour not in stats:
            continue
        bucket = stats[hour]
        bucket["count"] += 1
        bucket["base_volume"] = decimal_text(Decimal(bucket["base_volume"]) + qty)
        bucket["quote_volume"] = decimal_text(Decimal(bucket["quote_volume"]) + quote)
        if bucket["first_trade_timestamp"] is None:
            bucket["first_trade_timestamp"] = format_ts(timestamp)
        bucket["last_trade_timestamp"] = format_ts(timestamp)
    return stats, {"last_before_gap": last_before, "first_after_gap": first_after}


def kline_coverage(rows: list[list[str]], interval: str) -> dict[str, Any]:
    starts = {hour: [] for hour in WINDOW_HOURS}
    for row in rows:
        if not row or row[0] == "open_time":
            continue
        hour = hour_key_from_ms(row[0])
        if hour in starts:
            starts[hour].append(format_ts(datetime.fromtimestamp(int(row[0]) / 1000, UTC)))
    expected_per_hour = 60 if interval == "1m" else 1
    missing_by_hour: dict[str, list[str]] = {}
    for hour in WINDOW_HOURS:
        hour_start = parse_ts(hour)
        if interval == "1m":
            expected = {format_ts(hour_start + timedelta(minutes=i)) for i in range(60)}
        else:
            expected = {format_ts(hour_start)}
        missing_by_hour[hour] = sorted(expected - set(starts[hour]))
    return {
        "interval": interval,
        "present_count_by_hour": {hour: len(starts[hour]) for hour in WINDOW_HOURS},
        "missing_count_by_hour": {hour: len(missing_by_hour[hour]) for hour in WINDOW_HOURS},
        "missing_timestamps_by_hour": missing_by_hour,
    }


def rest_url(path: str, params: dict[str, Any]) -> str:
    return f"{SPOT_REST_ROOT}{path}?{urllib.parse.urlencode(params)}"


def fetch_rest_json(url: str, fetch: Callable[[str], HttpResponse]) -> dict[str, Any]:
    require_spot_url(url)
    response = fetch(url)
    body_sha = sha256_bytes(response.body)
    parsed: Any = None
    if response.status == 200:
        parsed = json.loads(response.body.decode("utf-8"))
    return {
        "url": url,
        "status": response.status,
        "byte_count": len(response.body),
        "body_sha256": body_sha,
        "json": parsed,
    }


def rest_evidence(symbol: str, fetch: Callable[[str], HttpResponse]) -> dict[str, Any]:
    start = ms("2023-03-24T11:00:00Z")
    end = ms("2023-03-24T15:59:59.999Z")
    gap_start = ms("2023-03-24T13:00:00Z")
    gap_end = ms("2023-03-24T13:59:59.999Z")
    requests = [
        fetch_rest_json(rest_url("/api/v3/klines", {"symbol": symbol, "interval": "1m", "startTime": start, "endTime": end, "limit": 1000}), fetch),
        fetch_rest_json(rest_url("/api/v3/klines", {"symbol": symbol, "interval": "1h", "startTime": start, "endTime": end, "limit": 1000}), fetch),
        fetch_rest_json(rest_url("/api/v3/aggTrades", {"symbol": symbol, "startTime": gap_start, "endTime": gap_end, "limit": 1000}), fetch),
    ]
    klines_1m = kline_coverage([[str(row[0]), *[str(x) for x in row[1:]]] for row in requests[0]["json"]], "1m") if requests[0]["status"] == 200 else None
    klines_1h = kline_coverage([[str(row[0]), *[str(x) for x in row[1:]]] for row in requests[1]["json"]], "1h") if requests[1]["status"] == 200 else None
    gap_agg_count = len(requests[2]["json"]) if requests[2]["status"] == 200 else None
    return {
        "requests": [{k: v for k, v in request.items() if k != "json"} for request in requests],
        "request_count": len(requests),
        "klines_1m": klines_1m,
        "klines_1h": klines_1h,
        "gap_agg_trade_count": gap_agg_count,
    }


def source_contract(root: Path) -> dict[str, Any]:
    spec = json.loads((root / SPEC_PATH).read_text(encoding="utf-8"))
    if spec["tracks"]["A_untouched_2023_holdout"]["assets"] != list(ASSETS):
        raise ValueError("focused holdout assets changed")
    contracts = {}
    for symbol in ASSETS:
        manifest_path = root / f"data/manifests/{symbol}-1h.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source = str(manifest.get("source", ""))
        source_kind = str(manifest.get("source_kind", ""))
        require_spot_url(source)
        if "Spot" not in source_kind:
            raise ValueError(f"{symbol} registered source is not Binance Spot")
        contracts[symbol] = {
            "manifest_path": str(manifest_path.relative_to(root)),
            "source": source,
            "source_kind": source_kind,
            "raw_path": f"data/raw/{symbol}-1h.csv",
            "raw_sha256": sha256_path(root / f"data/raw/{symbol}-1h.csv"),
            "manifest_sha256": sha256_path(manifest_path),
        }
    return contracts


def compare_sources(asset: dict[str, Any]) -> dict[str, Any]:
    trade_gap = asset["trades"]["hourly"][GAP_HOUR]["count"]
    agg_gap = asset["aggTrades"]["hourly"][GAP_HOUR]["count"]
    archive_1m_missing = asset["klines_1m"]["coverage"]["missing_count_by_hour"][GAP_HOUR]
    archive_1h_missing = asset["klines_1h"]["coverage"]["missing_count_by_hour"][GAP_HOUR]
    rest = asset["rest"]
    rest_ok = all(request["status"] == 200 for request in rest["requests"])
    rest_1m_missing = rest["klines_1m"]["missing_count_by_hour"][GAP_HOUR] if rest["klines_1m"] else None
    rest_1h_missing = rest["klines_1h"]["missing_count_by_hour"][GAP_HOUR] if rest["klines_1h"] else None
    rest_agg_gap = rest["gap_agg_trade_count"]
    agreement = (
        rest_ok
        and trade_gap == 0
        and agg_gap == 0
        and rest_agg_gap == 0
        and archive_1m_missing == 60
        and archive_1h_missing == 1
        and rest_1m_missing == 60
        and rest_1h_missing == 1
    )
    return {
        "archive_trade_gap_count": trade_gap,
        "archive_agg_trade_gap_count": agg_gap,
        "archive_1m_missing_in_gap": archive_1m_missing,
        "archive_1h_missing_in_gap": archive_1h_missing,
        "rest_agg_trade_gap_count": rest_agg_gap,
        "rest_1m_missing_in_gap": rest_1m_missing,
        "rest_1h_missing_in_gap": rest_1h_missing,
        "rest_all_status_200": rest_ok,
        "rest_and_archives_agree": agreement,
    }


def classify_asset(asset: dict[str, Any]) -> str:
    comparison = asset["cross_source_comparison"]
    if not comparison["rest_and_archives_agree"]:
        return "2023_HOLDOUT_SOURCE_CONTRACT_UNRESOLVED"
    if comparison["archive_trade_gap_count"] == 0 and comparison["archive_agg_trade_gap_count"] == 0:
        return "AUTHORITATIVE_NO_TRADE_INTERVAL_CONFIRMED"
    if comparison["archive_1h_missing_in_gap"] == 1:
        return "AUTHORITATIVE_KLINE_OMISSION_WITH_TRADES_CONFIRMED"
    return "2023_HOLDOUT_SOURCE_CONTRACT_UNRESOLVED"


def classify_resolution(assets: dict[str, Any]) -> str:
    values = {asset["classification"] for asset in assets.values()}
    if values == {"AUTHORITATIVE_NO_TRADE_INTERVAL_CONFIRMED"}:
        return "AUTHORITATIVE_NO_TRADE_INTERVAL_CONFIRMED"
    if values == {"AUTHORITATIVE_KLINE_OMISSION_WITH_TRADES_CONFIRMED"}:
        return "AUTHORITATIVE_KLINE_OMISSION_WITH_TRADES_CONFIRMED"
    return "2023_HOLDOUT_SOURCE_CONTRACT_UNRESOLVED"


def resolve(root: Path = Path("."), fetch: Callable[[str], HttpResponse] = default_fetch) -> dict[str, Any]:
    root = root.resolve()
    require_three_assets()
    contracts = source_contract(root)
    with TemporaryDirectory(prefix="qntylab_source_resolution_") as tmp:
        tmp_root = Path(tmp)
        assets: dict[str, Any] = {}
        archive_request_count = 0
        for symbol in ASSETS:
            asset: dict[str, Any] = {"source_contract": contracts[symbol], "archives": {}}
            for kind in ("trades", "aggTrades", "klines_1m", "klines_1h"):
                url = archive_url(symbol, kind)
                archive = fetch_to_tmp(url, tmp_root, fetch)
                checksum = fetch_to_tmp(f"{url}.CHECKSUM", tmp_root, fetch)
                archive_request_count += 2
                verification = verify_archive_checksum(archive, checksum)
                rows = read_zip_csv_rows(Path(archive["tmp_path"]))
                asset["archives"][kind] = verification
                if kind == "trades":
                    hourly, boundary = hourly_trade_stats(rows, kind)
                    asset["trades"] = {"hourly": hourly, **boundary}
                elif kind == "aggTrades":
                    hourly, boundary = hourly_trade_stats(rows, kind)
                    asset["aggTrades"] = {"hourly": hourly, **boundary}
                elif kind == "klines_1m":
                    asset["klines_1m"] = {"coverage": kline_coverage(rows, "1m")}
                elif kind == "klines_1h":
                    asset["klines_1h"] = {"coverage": kline_coverage(rows, "1h")}
            asset["last_pre_halt_trade"] = asset["trades"]["last_before_gap"]
            asset["first_post_halt_trade"] = asset["trades"]["first_after_gap"]
            if asset["last_pre_halt_trade"] and asset["first_post_halt_trade"]:
                delta = parse_ts(asset["first_post_halt_trade"]["timestamp"]) - parse_ts(asset["last_pre_halt_trade"]["timestamp"])
                asset["duration_between_boundary_trades_seconds"] = int(delta.total_seconds())
            asset["previous_official_kline_close"] = _previous_kline_close(root / f"data/raw/{symbol}-1h.csv")
            asset["first_post_halt_official_trade_price"] = asset["first_post_halt_trade"]["price"] if asset["first_post_halt_trade"] else None
            asset["rest"] = rest_evidence(symbol, fetch)
            asset["cross_source_comparison"] = compare_sources(asset)
            asset["classification"] = classify_asset(asset)
            assets[symbol] = asset
        finding = classify_resolution(assets)
        result = {
            "schema_version": "1.0.0",
            "resolution_id": "RESOLVE_AUTHORITATIVE_SOURCE_CONTRACT_FOR_MISSING_2023_SPOT_KLINE",
            "generated_by": "qntylab.resolve_holdout_source",
            "scope": {
                "assets": list(ASSETS),
                "gap_hour": GAP_HOUR,
                "audit_window_hours": list(WINDOW_HOURS),
                "source_contract": "Binance Spot public market data only",
            },
            "existing_gap": {symbol: [GAP_HOUR] for symbol in ASSETS},
            "assets": assets,
            "request_counts": {
                "archive_and_checksum_requests": archive_request_count,
                "rest_requests": sum(asset["rest"]["request_count"] for asset in assets.values()),
                "total_requests": archive_request_count + sum(asset["rest"]["request_count"] for asset in assets.values()),
            },
            "source_contract_finding": finding,
            "permitted_next_step": _next_step(finding),
            "explicit_non_actions": [
                "no paid data",
                "no third-party data",
                "no futures data substitution",
                "no raw production data changes",
                "no synthetic candle creation",
                "no holdout-spec amendment",
                "no strategy execution",
                "no backtest",
                "no trial event",
                "no decision event",
            ],
            "production_file_hashes": _production_hashes(root),
        }
    return result


def _previous_kline_close(path: Path) -> str | None:
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["timestamp"] == "2023-03-24T12:00:00Z":
                return row["close"]
    return None


def _next_step(finding: str) -> str:
    if finding == "AUTHORITATIVE_NO_TRADE_INTERVAL_CONFIRMED":
        return "PREREGISTER_BINANCE_SPOT_HALT_NORMALIZATION_V1"
    if finding == "AUTHORITATIVE_KLINE_OMISSION_WITH_TRADES_CONFIRMED":
        return "PREREGISTER_TRADE_DERIVED_KLINE_RECONSTRUCTION_V1"
    return "REPLACE_HISTORICAL_HOLDOUT_WITH_PREREGISTERED_FORWARD_SHADOW"


def _production_hashes(root: Path) -> dict[str, str]:
    paths = [*RAW_PATHS, SPEC_PATH, *LEDGER_PATHS, *PERP_MANIFEST_PATHS]
    return {str(path): sha256_path(root / path) for path in paths if (root / path).exists()}


def write_artifacts(result: dict[str, Any], root: Path = Path(".")) -> dict[str, str]:
    json_path = root / SUMMARY_JSON_PATH
    md_path = root / SUMMARY_MD_PATH
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_bytes(canonical_bytes(result) + b"\n")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return {str(SUMMARY_JSON_PATH): sha256_path(json_path), str(SUMMARY_MD_PATH): sha256_path(md_path)}


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Scope",
        f"Resolution ID: {result['resolution_id']}. Assets: {', '.join(result['scope']['assets'])}. Gap hour: {result['scope']['gap_hour']}. Source contract: Binance Spot public market data only.",
        "",
        "# Existing Gap",
        "The committed 2023 holdout audit records one absent 1h spot kline per asset at 2023-03-24T13:00:00Z.",
        "",
        "# Official Sources",
    ]
    for symbol, asset in result["assets"].items():
        for kind, archive in asset["archives"].items():
            lines.append(f"- {symbol} {kind}: {archive['archive_url']}")
    lines.extend(["", "# Archive Checksum Verification"])
    for symbol, asset in result["assets"].items():
        for kind, archive in asset["archives"].items():
            lines.append(
                f"- {symbol} {kind}: archive_status={archive['archive_status']} checksum_status={archive['checksum_status']} "
                f"archive_bytes={archive['archive_byte_count']} archive_sha256={archive['archive_sha256']} "
                f"checksum_sha256={archive['checksum_file_sha256']} verified={archive['verified']}"
            )
    lines.extend(["", "# Hourly Trade Counts"])
    lines.append("| asset | source | hour | count | first | last | base_volume | quote_volume |")
    lines.append("| --- | --- | --- | ---: | --- | --- | ---: | ---: |")
    for symbol, asset in result["assets"].items():
        for source in ("trades", "aggTrades"):
            for hour, stats in asset[source]["hourly"].items():
                lines.append(
                    f"| {symbol} | {source} | {hour} | {stats['count']} | {stats['first_trade_timestamp']} | "
                    f"{stats['last_trade_timestamp']} | {stats['base_volume']} | {stats['quote_volume']} |"
                )
    lines.extend(["", "# Kline Coverage"])
    for symbol, asset in result["assets"].items():
        one_m = asset["klines_1m"]["coverage"]["missing_count_by_hour"]
        one_h = asset["klines_1h"]["coverage"]["missing_count_by_hour"]
        lines.append(f"- {symbol}: archive 1m missing by hour {one_m}; archive 1h missing by hour {one_h}.")
    lines.extend(["", "# Cross-Source Comparison"])
    for symbol, asset in result["assets"].items():
        lines.append(f"- {symbol}: {json.dumps(asset['cross_source_comparison'], sort_keys=True)}")
    lines.extend(["", "# Last Pre-Halt Trade"])
    for symbol, asset in result["assets"].items():
        lines.append(f"- {symbol}: {json.dumps(asset['last_pre_halt_trade'], sort_keys=True)}")
    lines.extend(["", "# First Post-Halt Trade"])
    for symbol, asset in result["assets"].items():
        lines.append(f"- {symbol}: {json.dumps(asset['first_post_halt_trade'], sort_keys=True)}")
    lines.extend(
        [
            "",
            "# Source-Contract Finding",
            result["source_contract_finding"],
            "",
            "# Permitted Next Step",
            result["permitted_next_step"],
            "",
            "# Explicit Non-Actions",
        ]
    )
    lines.extend(f"- {item}" for item in result["explicit_non_actions"])
    lines.extend(
        [
            "",
            "# Reproduction",
            "Run `python -m qntylab.resolve_holdout_source` from the repository root. The resolver downloads only official Binance Spot public archives/checksums into a temporary directory, queries Spot REST market-data endpoints, verifies checksums, and rewrites this deterministic JSON and Markdown artifact.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    result = resolve(Path("."))
    hashes = write_artifacts(result, Path("."))
    print(json.dumps({"source_contract_finding": result["source_contract_finding"], "artifact_hashes": hashes}, sort_keys=True))


if __name__ == "__main__":
    main()
