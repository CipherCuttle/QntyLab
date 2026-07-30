"""Metadata-only storage feasibility measurement for frozen R1 BOM v3."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from qntylab.r1_input_bom import canonical_bytes


SAMPLE_PER_YEAR_POSITION = 24
DENSE_SYMBOL_POINTS = 36
HIGH_LOW_STREAM_COUNT = 16
MAJOR_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT", "ADAUSDT", "SUIUSDT", "PEPEUSDT", "1000PEPEUSDT")
POSITIONS = ("early", "middle", "late")


def _days(start: str, end: str) -> list[str]:
    cursor, last = date.fromisoformat(start[:10]), date.fromisoformat(end[:10])
    result = []
    while cursor <= last:
        result.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return result


def _point(start: str, end: str, position: str) -> str:
    days = _days(start, end)
    index = {"early": 0, "middle": (len(days) - 1) // 2, "late": len(days) - 1}[position]
    return days[index]


def _stream_count(stream: dict) -> int:
    return sum(row["expected_object_count"] for row in stream["market_acquisition_plan"]["structural_required_intervals"])


def _structural_intervals(bom: dict) -> list[dict]:
    rows = []
    for stream in bom["required_acquisition"]["streams"]:
        for interval in stream["market_acquisition_plan"]["structural_required_intervals"]:
            rows.append({"stream_id": stream["stream_id"], "symbol": stream["symbol"], **interval,
                         "url_template": stream["market_acquisition_plan"]["object_url_template"]})
    return rows


def deterministic_sample(bom: dict) -> list[dict]:
    """Return a fixed stratified sample of frozen structural market objects."""
    intervals = _structural_intervals(bom)
    selected: dict[tuple[str, str], dict] = {}
    def add(interval: dict, utc_date: str, stratum: str) -> None:
        selected.setdefault((interval["stream_id"], utc_date), {"stream_id": interval["stream_id"], "symbol": interval["symbol"], "utc_date": utc_date, "url": interval["url_template"].format(utc_date=utc_date), "strata": []})["strata"].append(stratum)

    years = range(2021, 2027)
    for year in years:
        for position in POSITIONS:
            candidates = []
            for interval in intervals:
                start, end = max(interval["start_utc"][:10], f"{year}-01-01"), min(interval["end_utc"][:10], f"{year}-12-31")
                if start <= end:
                    utc_date = _point(start, end, position)
                    rank = sha256(f"r1-bom-v3|year={year}|position={position}|{interval['stream_id']}|{utc_date}".encode()).hexdigest()
                    candidates.append((rank, interval, utc_date))
            for _rank, interval, utc_date in sorted(candidates)[:SAMPLE_PER_YEAR_POSITION]:
                add(interval, utc_date, f"year={year}:{position}")

    streams = bom["required_acquisition"]["streams"]
    ranked = sorted(streams, key=lambda stream: (_stream_count(stream), stream["stream_id"]))
    for label, group in (("low-object-count", ranked[:HIGH_LOW_STREAM_COUNT]), ("high-object-count", ranked[-HIGH_LOW_STREAM_COUNT:])):
        for stream in group:
            for interval in stream["market_acquisition_plan"]["structural_required_intervals"]:
                for position in POSITIONS:
                    add({"stream_id": stream["stream_id"], "symbol": stream["symbol"], **interval, "url_template": stream["market_acquisition_plan"]["object_url_template"]}, _point(interval["start_utc"], interval["end_utc"], position), label)

    by_symbol = {stream["symbol"]: stream for stream in streams}
    for symbol in MAJOR_SYMBOLS:
        stream = by_symbol.get(symbol)
        if not stream:
            continue
        for interval in stream["market_acquisition_plan"]["structural_required_intervals"]:
            values = _days(interval["start_utc"], interval["end_utc"])
            for index in range(min(DENSE_SYMBOL_POINTS, len(values))):
                offset = round(index * (len(values) - 1) / max(1, min(DENSE_SYMBOL_POINTS, len(values)) - 1))
                add({"stream_id": stream["stream_id"], "symbol": symbol, **interval, "url_template": stream["market_acquisition_plan"]["object_url_template"]}, values[offset], "major-symbol-dense")
    return [{**row, "strata": sorted(set(row["strata"]))} for _key, row in sorted(selected.items())]


def probe_size(item: dict, opener=urlopen) -> dict:
    """Use HEAD, with a one-byte range fallback only when length is absent."""
    request = Request(item["url"], method="HEAD", headers={"Accept-Encoding": "identity"})
    try:
        with opener(request, timeout=30) as response:
            length = response.headers.get("Content-Length")
            if length and length.isdigit() and int(length) > 0:
                return {**item, "state": "SIZE_KNOWN", "method": "HEAD_CONTENT_LENGTH", "http_status": response.status, "compressed_bytes": int(length), "body_bytes_transferred": 0}
    except HTTPError as error:
        state = "SOURCE_ABSENT" if error.code in {404, 410} else "TRANSPORT_FAILURE"
        return {**item, "state": state, "method": "HEAD", "http_status": error.code, "compressed_bytes": None, "body_bytes_transferred": 0}
    except (URLError, TimeoutError, OSError) as error:
        return {**item, "state": "TRANSPORT_FAILURE", "method": "HEAD", "detail": str(error), "compressed_bytes": None, "body_bytes_transferred": 0}
    request = Request(item["url"], headers={"Range": "bytes=0-0", "Accept-Encoding": "identity"})
    try:
        with opener(request, timeout=30) as response:
            content_range = response.headers.get("Content-Range", "")
            total = content_range.rsplit("/", 1)[-1]
            if total.isdigit() and int(total) > 0:
                response.read(1)
                return {**item, "state": "SIZE_KNOWN", "method": "RANGE_CONTENT_RANGE", "http_status": response.status, "compressed_bytes": int(total), "body_bytes_transferred": 1}
            return {**item, "state": "SIZE_UNKNOWN", "method": "RANGE_CONTENT_RANGE", "http_status": response.status, "compressed_bytes": None, "body_bytes_transferred": 0}
    except HTTPError as error:
        state = "SOURCE_ABSENT" if error.code in {404, 410} else "TRANSPORT_FAILURE"
        return {**item, "state": state, "method": "RANGE_CONTENT_RANGE", "http_status": error.code, "compressed_bytes": None, "body_bytes_transferred": 0}
    except (URLError, TimeoutError, OSError) as error:
        return {**item, "state": "TRANSPORT_FAILURE", "method": "RANGE_CONTENT_RANGE", "detail": str(error), "compressed_bytes": None, "body_bytes_transferred": 0}


def _nearest_rank(values: list[int], percentile: int) -> int:
    return sorted(values)[max(0, (len(values) * percentile + 99) // 100 - 1)]


def summarize(bom: dict, probes: list[dict], free_bytes: int) -> dict:
    sizes = [row["compressed_bytes"] for row in probes if row["state"] == "SIZE_KNOWN"]
    if not sizes:
        raise ValueError("no successful size probes")
    planned = sum(_stream_count(stream) for stream in bom["required_acquisition"]["streams"])
    distribution = {"count": len(sizes), "minimum": min(sizes), "p25": _nearest_rank(sizes, 25), "median": _nearest_rank(sizes, 50), "p75": _nearest_rank(sizes, 75), "p90": _nearest_rank(sizes, 90), "p95": _nearest_rank(sizes, 95), "p99": _nearest_rank(sizes, 99), "maximum": max(sizes), "arithmetic_mean": sum(sizes) / len(sizes)}
    point = round(distribution["arithmetic_mean"] * planned)
    conservative = distribution["p90"] * planned
    status = "R1_FULL_RAW_RETENTION_DOES_NOT_FIT" if point > free_bytes - 30 * 1024**3 else "R1_STORAGE_FOOTPRINT_INCONCLUSIVE"
    by_year = {}
    for year in sorted({row["utc_date"][:4] for row in probes if row["state"] == "SIZE_KNOWN"}):
        values = [row["compressed_bytes"] for row in probes if row["state"] == "SIZE_KNOWN" and row["utc_date"].startswith(year)]
        by_year[year] = {"count": len(values), "minimum": min(values), "median": _nearest_rank(values, 50), "maximum": max(values), "arithmetic_mean": sum(values) / len(values)}
    stream_counts = {stream["stream_id"]: _stream_count(stream) for stream in bom["required_acquisition"]["streams"]}
    sampled_streams = {}
    for row in probes:
        if row["state"] == "SIZE_KNOWN":
            sampled_streams.setdefault(row["stream_id"], []).append(row["compressed_bytes"])
    stream_estimates = sorted(({"stream_id": stream_id, "sample_count": len(values), "sample_mean_bytes": sum(values) / len(values), "frozen_structural_object_count": stream_counts[stream_id], "estimated_bytes": round(sum(values) / len(values) * stream_counts[stream_id])} for stream_id, values in sampled_streams.items()), key=lambda row: (-row["estimated_bytes"], row["stream_id"]))
    top_contribution = {str(count): {"sampled_streams_covered": min(count, len(stream_estimates)), "estimated_bytes": sum(row["estimated_bytes"] for row in stream_estimates[:count])} for count in (1, 5, 10, 25)}
    return {"planned_structural_market_objects": planned, "sample_distribution": distribution,
            "probe_states": {state: sum(row["state"] == state for row in probes) for state in sorted({row["state"] for row in probes})},
            "metadata_request_count": len(probes), "body_bytes_transferred": sum(row["body_bytes_transferred"] for row in probes),
            "size_by_year": by_year, "heavy_tail": {"sampled_stream_estimates": stream_estimates[:25], "top_stream_contribution": top_contribution, "scope": "sample-mean extrapolations among sampled streams; not an exact whole-corpus census"},
            "market_raw_footprint_estimate": {"method": "sample arithmetic mean times frozen structural object count", "point_estimate_bytes": point, "conservative_p90_bytes": conservative, "funding_bytes": "UNKNOWN_NOT_PROBED", "total_bytes": "AT_LEAST_MARKET_ESTIMATE"},
            "decision": status}


def write_receipt(root: Path, probes: list[dict], summary: dict) -> dict:
    bom_path = root / "experiments/data/r1_population_raw_acquisition_bom_v3.json"
    bom_bytes = bom_path.read_bytes()
    receipt = {"artifact": "r1_raw_storage_footprint_v1", "bom_v3_sha256": sha256(bom_bytes).hexdigest(), "required_acquisition_sha256": json.loads(bom_bytes)["required_acquisition_sha256"], "outcome_embargo": True,
               "sample_algorithm": {"seed": "r1-bom-v3", "per_year_position": SAMPLE_PER_YEAR_POSITION, "positions": POSITIONS, "high_low_stream_count": HIGH_LOW_STREAM_COUNT, "major_symbols": MAJOR_SYMBOLS, "dense_symbol_points": DENSE_SYMBOL_POINTS},
               "probes": probes, "summary": summary}
    (root / "experiments/data/r1_raw_storage_footprint_v1.json").write_bytes(canonical_bytes(receipt))
    report = "\n".join(["# R1 raw storage footprint v1", "", "## VERDICT", "", summary["decision"], "", "## METHOD", "", "Deterministic BOM-bound metadata-only HEAD sampling; no full object bodies were downloaded.", "", "## COUNTS", "", f"- Metadata requests: {summary['metadata_request_count']}", f"- Full-body bytes transferred: {summary['body_bytes_transferred']}", f"- Point market estimate bytes: {summary['market_raw_footprint_estimate']['point_estimate_bytes']}", f"- Conservative p90 market estimate bytes: {summary['market_raw_footprint_estimate']['conservative_p90_bytes']}"])
    (root / "experiments/results/R1_RAW_STORAGE_FOOTPRINT_V1.md").write_text(report + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--reuse-receipt", type=Path)
    args = parser.parse_args()
    root = Path.cwd(); bom = json.loads((root / "experiments/data/r1_population_raw_acquisition_bom_v3.json").read_text())
    if args.reuse_receipt:
        probes = json.loads(args.reuse_receipt.read_text())["probes"]
    else:
        sample = deterministic_sample(bom)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            probes = list(pool.map(probe_size, sample))
    import shutil
    summary = summarize(bom, probes, shutil.disk_usage(root).free)
    if args.write:
        print(json.dumps(write_receipt(root, probes, summary), sort_keys=True))
