from __future__ import annotations

import copy
from pathlib import Path

import pytest

from experiments.research.h003_edge_falsification_v0 import attest_canonical_data as module


def _expected_manifest() -> dict:
    return {
        "symbol": module.SYMBOL,
        "timeframe": "1h",
        "rows": module.EXPECTED_ROWS,
        "start": module.EXPECTED_START,
        "end": module.EXPECTED_END,
        "sha256": module.EXPECTED_SHA256,
        "gaps": list(module.EXPECTED_GAPS),
        "source": "https://data-api.binance.vision/api/v3/klines",
        "source_kind": "Binance Spot public market-data REST",
        "complete_candles_only": True,
    }


def test_attestation_accepts_only_exact_frozen_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    expected = _expected_manifest()

    def fake_fetch(symbol: str, start: str, root: Path, interval: str, end):
        assert symbol == "SOLUSDT"
        assert start == "2021-01-01T00:00:00"
        assert interval == "1h"
        assert end == module.FROZEN_RETRIEVAL_INSTANT
        assert root == tmp_path
        assert (root / "data" / "manifests").is_dir()
        return copy.deepcopy(expected)

    monkeypatch.setattr(module, "fetch", fake_fetch)
    result = module.attest_classified(tmp_path)

    assert result["status"] == "CANONICAL_MATCH"
    assert result["canonical_match"] is True
    assert result["mismatches"] == {}
    assert result["error"] is None
    assert result["observed"]["sha256"] == module.EXPECTED_SHA256
    assert module._exit_code(result) == 0


@pytest.mark.parametrize(
    ("key", "replacement"),
    [
        ("rows", 49830),
        ("start", "2021-01-01T01:00:00Z"),
        ("end", "2026-09-08T19:00:00Z"),
        ("sha256", "0" * 64),
        ("gaps", []),
        ("source", "https://example.invalid"),
        ("complete_candles_only", False),
    ],
)
def test_attestation_fails_closed_on_any_material_identity_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    key: str,
    replacement,
) -> None:
    manifest = _expected_manifest()
    manifest[key] = replacement
    monkeypatch.setattr(module, "fetch", lambda *args, **kwargs: copy.deepcopy(manifest))

    result = module.attest_classified(tmp_path)

    assert result["status"] == "MISMATCH"
    assert result["canonical_match"] is False
    assert key in result["mismatches"]
    assert result["error"] is None
    assert module._exit_code(result) == 2


def test_acquisition_exception_yields_classified_noncanonical_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def failing_fetch(*args, **kwargs):
        raise RuntimeError("public data endpoint unavailable")

    monkeypatch.setattr(module, "fetch", failing_fetch)
    result = module.attest_classified(tmp_path)

    assert result["status"] == "ACQUISITION_ERROR"
    assert result["canonical_match"] is False
    assert result["observed"] is None
    assert result["mismatches"] == {}
    assert result["expected"]["sha256"] == module.EXPECTED_SHA256
    assert result["error"] == {
        "classification": "ACQUISITION_ERROR",
        "exception_type": "RuntimeError",
        "message": "public data endpoint unavailable",
    }
    assert module._exit_code(result) == 3


def test_attestation_has_no_strategy_backtest_or_ledger_surface() -> None:
    source = Path(module.__file__).read_text(encoding="utf-8")

    forbidden = (
        "qntylab.strategies",
        "qntylab.backtest",
        "qntylab.strategy_test",
        "qntylab.research_ledger",
        "append_canonical_event",
        "CANDIDATE_REOPENED",
        "send_transaction",
        "sign_transaction",
        "submit_transaction",
    )
    for token in forbidden:
        assert token not in source

    assert module.EXPECTED_SHA256 == "64bdb27a31003b0de25f3802affa8b412143a50bc8a5b76a399924626b01174a"
    assert module.EXPECTED_ROWS == 49831
    assert len(module.EXPECTED_GAPS) == 7
    assert module.FROZEN_RETRIEVAL_INSTANT.isoformat() == "2026-09-08T21:03:17.228114+00:00"


def test_attestation_authority_is_explicitly_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(module, "fetch", lambda *args, **kwargs: _expected_manifest())
    result = module.attest_classified(tmp_path)

    assert result["authority"] == {
        "research_result": "NONE",
        "strategy_execution": "FORBIDDEN",
        "qnty_acceptance": "NONE",
        "qntyspot_policy": "NONE",
        "capital": "NONE",
        "signing": "NONE",
        "submission": "NONE",
    }
