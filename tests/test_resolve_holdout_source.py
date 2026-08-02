from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

import pytest

from qntylab import resolve_holdout_source as resolver


def _zip(rows: list[list[str]]) -> bytes:
    payload = io.StringIO()
    writer = csv.writer(payload, lineterminator="\n")
    writer.writerows(rows)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.csv", payload.getvalue())
    return out.getvalue()


def _rest_klines(interval: str) -> list[list[object]]:
    rows = []
    step = 60_000 if interval == "1m" else 3_600_000
    start = resolver.ms("2023-03-24T11:00:00Z")
    end = resolver.ms("2023-03-24T15:59:59.999Z")
    cur = start
    while cur <= end:
        hour = resolver.hour_key_from_ms(cur)
        if hour != resolver.GAP_HOUR:
            rows.append([cur, "1", "1", "1", "1", "1", cur + step - 1, "1", 1, "1", "1", "0"])
        cur += step
    return rows


def _archive_rows(kind: str, *, trade_in_gap: bool = False) -> list[list[str]]:
    if kind == "trades":
        rows = [
            ["1", "100.00", "2.00000000", "200.00000000", str(resolver.ms("2023-03-24T11:01:00Z")), "false", "true"],
            ["2", "101.00", "1.00000000", "101.00000000", str(resolver.ms("2023-03-24T12:59:59.999Z")), "false", "true"],
            ["3", "102.00", "3.00000000", "306.00000000", str(resolver.ms("2023-03-24T14:00:00Z")), "false", "true"],
        ]
        if trade_in_gap:
            rows.insert(2, ["9", "100.50", "1.00000000", "100.50000000", str(resolver.ms("2023-03-24T13:01:00Z")), "false", "true"])
        return rows
    if kind == "aggTrades":
        rows = [
            ["1", "100.00", "2.00000000", "1", "1", str(resolver.ms("2023-03-24T11:01:00Z")), "false", "true"],
            ["2", "101.00", "1.00000000", "2", "2", str(resolver.ms("2023-03-24T12:59:59.999Z")), "false", "true"],
            ["3", "102.00", "3.00000000", "3", "3", str(resolver.ms("2023-03-24T14:00:00Z")), "false", "true"],
        ]
        if trade_in_gap:
            rows.insert(2, ["9", "100.50", "1.00000000", "9", "9", str(resolver.ms("2023-03-24T13:01:00Z")), "false", "true"])
        return rows
    if kind == "klines_1h":
        return [
            [str(resolver.ms("2023-03-24T11:00:00Z")), "1", "1", "1", "1", "1", "0", "1", "1", "1", "1", "0"],
            [str(resolver.ms("2023-03-24T12:00:00Z")), "1", "1", "1", "1", "0", "0", "0", "0", "0", "0", "0"],
            [str(resolver.ms("2023-03-24T14:00:00Z")), "1", "1", "1", "1", "1", "0", "1", "1", "1", "1", "0"],
            [str(resolver.ms("2023-03-24T15:00:00Z")), "1", "1", "1", "1", "1", "0", "1", "1", "1", "1", "0"],
        ]
    rows = []
    for hour in resolver.WINDOW_HOURS:
        if hour == resolver.GAP_HOUR:
            continue
        start = resolver.parse_ts(hour)
        for minute in range(60):
            ts = int((start.timestamp() + minute * 60) * 1000)
            rows.append([str(ts), "1", "1", "1", "1", "1", "0", "1", "1", "1", "1", "0"])
    return rows


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path
    (root / "experiments/specs").mkdir(parents=True)
    (root / "experiments/research").mkdir(parents=True)
    (root / "data/raw").mkdir(parents=True)
    (root / "data/manifests").mkdir(parents=True)
    spec = {
        "tracks": {
            "A_untouched_2023_holdout": {
                "assets": list(resolver.ASSETS),
            }
        }
    }
    (root / resolver.SPEC_PATH).write_text(json.dumps(spec), encoding="utf-8")
    for ledger in resolver.LEDGER_PATHS:
        (root / ledger).parent.mkdir(parents=True, exist_ok=True)
        (root / ledger).write_text("", encoding="utf-8")
    for symbol in resolver.ASSETS:
        raw = root / f"data/raw/{symbol}-1h.csv"
        raw.write_text("timestamp,open,high,low,close,volume\n2023-03-24T12:00:00Z,1,1,1,1.23000000,0\n", encoding="utf-8")
        manifest = {
            "source": "https://data-api.binance.vision/api/v3/klines",
            "source_kind": "Binance Spot public market-data REST",
            "symbol": symbol,
        }
        (root / f"data/manifests/{symbol}-1h.json").write_text(json.dumps(manifest), encoding="utf-8")
        (root / f"data/manifests/{symbol}-perp-1h.json").write_text('{"market":"USD-M perpetual"}', encoding="utf-8")
    return root


class FakeFetch:
    def __init__(self, *, archive_trade_in_gap: bool = False, rest_trade_in_gap: bool = False, rest_1h_in_gap: bool = False):
        self.archive_trade_in_gap = archive_trade_in_gap
        self.rest_trade_in_gap = rest_trade_in_gap
        self.rest_1h_in_gap = rest_1h_in_gap
        self.calls: list[str] = []

    def __call__(self, url: str) -> resolver.HttpResponse:
        self.calls.append(url)
        if url.endswith(".CHECKSUM"):
            archive = self._archive_bytes(url.removesuffix(".CHECKSUM"))
            return resolver.HttpResponse(200, f"{resolver.sha256_bytes(archive)} file.zip\n".encode())
        if "data.binance.vision" in url:
            return resolver.HttpResponse(200, self._archive_bytes(url))
        if "/api/v3/klines" in url:
            interval = "1h" if "interval=1h" in url else "1m"
            rows = _rest_klines(interval)
            if interval == "1h" and self.rest_1h_in_gap:
                rows.insert(2, [resolver.ms(resolver.GAP_HOUR), "1", "1", "1", "1", "0", 0, "0", 0, "0", "0", "0"])
            return resolver.HttpResponse(200, json.dumps(rows).encode())
        if "/api/v3/aggTrades" in url:
            rows = [{"a": 1, "p": "1", "q": "1", "T": resolver.ms("2023-03-24T13:01:00Z")}] if self.rest_trade_in_gap else []
            return resolver.HttpResponse(200, json.dumps(rows).encode())
        raise AssertionError(url)

    def _archive_bytes(self, url: str) -> bytes:
        kind = "klines_1m"
        if "aggTrades" in url:
            kind = "aggTrades"
        elif "trades" in url:
            kind = "trades"
        elif "/1h/" in url:
            kind = "klines_1h"
        return _zip(_archive_rows(kind, trade_in_gap=self.archive_trade_in_gap and kind in {"trades", "aggTrades"}))


def test_exactly_three_assets_are_examined():
    resolver.require_three_assets()
    with pytest.raises(ValueError, match="exactly"):
        resolver.require_three_assets(("BTCUSDT", "ETHUSDT"))


def test_only_binance_spot_sources_are_accepted():
    resolver.require_spot_url("https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1h/x.zip")
    resolver.require_spot_url("https://data-api.binance.vision/api/v3/klines")
    with pytest.raises(ValueError, match="Futures"):
        resolver.require_spot_url("https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1h/x.zip")
    with pytest.raises(ValueError, match="non-Binance"):
        resolver.require_spot_url("https://example.com/data/spot/daily/x.zip")


def test_official_checksum_verification_is_required(tmp_path):
    archive = tmp_path / "a.zip"
    checksum = tmp_path / "a.zip.CHECKSUM"
    archive.write_bytes(b"abc")
    checksum.write_text("bad a.zip\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        resolver.verify_archive_checksum(
            {"url": "u", "status": 200, "byte_count": 3, "sha256": resolver.sha256_bytes(b"abc"), "tmp_path": str(archive)},
            {"url": "c", "status": 200, "byte_count": checksum.stat().st_size, "sha256": resolver.sha256_path(checksum), "tmp_path": str(checksum)},
        )


def test_zero_trade_classification_requires_trade_and_aggtrade_agreement():
    asset = {
        "cross_source_comparison": {
            "rest_and_archives_agree": True,
            "archive_trade_gap_count": 0,
            "archive_agg_trade_gap_count": 1,
            "archive_1h_missing_in_gap": 1,
        }
    }
    assert resolver.classify_asset(asset) == "AUTHORITATIVE_KLINE_OMISSION_WITH_TRADES_CONFIRMED"


def test_missing_kline_alone_cannot_prove_a_trading_halt():
    asset = {
        "cross_source_comparison": {
            "rest_and_archives_agree": False,
            "archive_trade_gap_count": 0,
            "archive_agg_trade_gap_count": 0,
            "archive_1h_missing_in_gap": 1,
        }
    }
    assert resolver.classify_asset(asset) == "2023_HOLDOUT_SOURCE_CONTRACT_UNRESOLVED"


def test_any_trade_inside_hour_prevents_zero_trade_classification():
    stats, _ = resolver.hourly_trade_stats(_archive_rows("trades", trade_in_gap=True), "trades")
    assert stats[resolver.GAP_HOUR]["count"] == 1


def test_archive_and_rest_disagreement_fails_closed(tmp_path):
    result = resolver.resolve(_fixture_root(tmp_path), fetch=FakeFetch(rest_trade_in_gap=True))
    assert result["source_contract_finding"] == "2023_HOLDOUT_SOURCE_CONTRACT_UNRESOLVED"


def test_no_raw_production_file_is_changed(tmp_path):
    root = _fixture_root(tmp_path)
    before = {str(path): resolver.sha256_path(root / path) for path in resolver.RAW_PATHS}
    resolver.resolve(root, fetch=FakeFetch())
    after = {str(path): resolver.sha256_path(root / path) for path in resolver.RAW_PATHS}
    assert after == before


def test_no_strategy_path_is_invoked():
    source = Path(resolver.__file__).read_text(encoding="utf-8")
    assert "import qntylab.strategy_test" not in source
    assert "from .strategy_test" not in source
    assert "python -m qntylab.strategy_test" not in source
    assert "import qntylab.backtest" not in source
    assert "from .backtest" not in source


def test_no_trial_or_decision_event_is_added(tmp_path):
    root = _fixture_root(tmp_path)
    before = {str(path): resolver.sha256_path(root / path) for path in resolver.LEDGER_PATHS}
    resolver.resolve(root, fetch=FakeFetch())
    after = {str(path): resolver.sha256_path(root / path) for path in resolver.LEDGER_PATHS}
    assert after == before


def test_output_ordering_and_hashes_are_deterministic(tmp_path):
    root = _fixture_root(tmp_path)
    left = resolver.resolve(root, fetch=FakeFetch())
    right = resolver.resolve(root, fetch=FakeFetch())
    assert resolver.sha256_bytes(resolver.canonical_bytes(left)) == resolver.sha256_bytes(resolver.canonical_bytes(right))
    assert list(left["assets"]) == list(resolver.ASSETS)


def test_perpetual_manifests_remain_untouched(tmp_path):
    root = _fixture_root(tmp_path)
    before = {str(path): resolver.sha256_path(root / path) for path in resolver.PERP_MANIFEST_PATHS}
    resolver.resolve(root, fetch=FakeFetch())
    after = {str(path): resolver.sha256_path(root / path) for path in resolver.PERP_MANIFEST_PATHS}
    assert after == before
