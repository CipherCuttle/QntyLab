from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/order-flow-prospective-v1-recorder-qualification.yml"


def test_qualification_workflow_has_no_live_schedule_or_provider_access() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "workflow_dispatch:" in text
    assert "pull_request:" in text
    assert "schedule:" not in text
    assert "fapi.binance.com" not in lowered
    assert "/fapi/v1/klines" not in lowered
    assert "market_data" not in lowered
    assert "contents: write" in text
    assert text.count("contents: write") == 1
    assert "publish immutable synthetic recorder ledger" in text
    assert "without repository checkout" in text
    assert "https://uploads.github.com/repos/$GITHUB_REPOSITORY/releases/$RELEASE_ID/assets" in text
    assert "Cannot delete asset from an immutable release" in text
    assert "independently restore exact recorder ledger bytes" in text


def test_qualification_workflow_uses_canonical_master_only_for_manual_stage() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "if: github.event_name == 'workflow_dispatch'" in text
    assert "ref: master" in text
    assert "build_synthetic_qualification_ledger" in text
    assert "synthetic recorder qualification only" in text
    assert "real_market_data_access_authorized" not in text
