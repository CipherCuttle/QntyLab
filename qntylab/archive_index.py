"""Unsigned S3 object inventory for the immutable Sprint v2 acquisition plan."""
from __future__ import annotations

import hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from xml.etree import ElementTree

BUCKET = "data.binance.vision"
REGION = "ap-northeast-1"
ENDPOINT = f"https://s3-{REGION}.amazonaws.com/{BUCKET}"
ROOT = "data/futures/um/monthly/klines/"
NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}

def list_objects(prefix: str, *, delimiter: str | None = None, opener=urlopen) -> tuple[list[str], list[dict]]:
    """Return all paginated common prefixes and objects, without HEAD probes."""
    token = None; prefixes: list[str] = []; objects: list[dict] = []
    while True:
        query = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if delimiter: query["delimiter"] = delimiter
        if token: query["continuation-token"] = token
        with opener(ENDPOINT + "?" + urlencode(query), timeout=60) as response:
            root = ElementTree.fromstring(response.read())
        prefixes.extend(node.findtext("s3:Prefix", default="", namespaces=NS) for node in root.findall("s3:CommonPrefixes", NS))
        for node in root.findall("s3:Contents", NS):
            objects.append({"key": node.findtext("s3:Key", default="", namespaces=NS), "size": int(node.findtext("s3:Size", default="0", namespaces=NS)), "last_modified": node.findtext("s3:LastModified", default="", namespaces=NS)})
        if root.findtext("s3:IsTruncated", default="false", namespaces=NS).lower() != "true": break
        token = root.findtext("s3:NextContinuationToken", default="", namespaces=NS)
        if not token: raise ValueError("truncated S3 response missing continuation token")
    return sorted(set(prefixes)), sorted(objects, key=lambda row: row["key"])

def eligible_symbols(prefixes: list[str]) -> list[str]:
    excluded = {"USDCUSDT", "BUSDUSDT", "TUSDUSDT", "FDUSDUSDT"}
    values = [p.removeprefix(ROOT).removesuffix("/") for p in prefixes]
    return sorted(v for v in values if v.endswith("USDT") and "_" not in v and v not in excluded)

def inventory(cutoff: str, opener=urlopen) -> dict:
    prefixes, _ = list_objects(ROOT, delimiter="/", opener=opener); symbols = eligible_symbols(prefixes); records = []
    for symbol in symbols:
        _, objects = list_objects(f"{ROOT}{symbol}/1d/", opener=opener)
        months: dict[str, dict] = {}
        for item in objects:
            match = re.fullmatch(rf"{re.escape(ROOT)}{re.escape(symbol)}/1d/{re.escape(symbol)}-1d-(\d{{4}}-\d{{2}})\.zip(?:\.CHECKSUM)?", item["key"])
            if not match or match.group(1) > cutoff[:7]: continue
            month = months.setdefault(match.group(1), {"symbol": symbol, "year_month": match.group(1)})
            month["checksum_key" if item["key"].endswith(".CHECKSUM") else "zip_key"] = item["key"]
            month["size" if not item["key"].endswith(".CHECKSUM") else "checksum_size"] = item["size"]
            month["last_modified" if not item["key"].endswith(".CHECKSUM") else "checksum_last_modified"] = item["last_modified"]
        records.extend(value for value in months.values() if "zip_key" in value)
    result = {"listing_method": "unsigned S3 ListObjectsV2", "bucket": BUCKET, "region": REGION, "root_prefix": ROOT, "cutoff": cutoff, "historical_prefix_count": len(prefixes), "structurally_eligible_symbols": symbols, "objects": sorted(records, key=lambda r: (r["symbol"], r["year_month"]))}
    result["root_sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return result

def write_inventory(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
