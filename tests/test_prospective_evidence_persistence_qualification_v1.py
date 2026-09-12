from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/prospective-evidence-persistence-qualification-v1.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_qualification_is_manual_synthetic_and_non_scientific() -> None:
    text = _workflow_text()
    lowered = text.lower()

    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert '"authority":"NONE"' in text
    assert '"scientific_evidence":false' in text
    assert "not scientific evidence" in lowered
    assert "h003" not in lowered
    assert "binance" not in lowered
    assert "market" not in lowered


def test_only_persist_job_has_repository_write_authority() -> None:
    text = _workflow_text()

    assert text.count("contents: write") == 1
    assert text.count("contents: read") >= 3
    assert "Download staged fixture without repository checkout" in text


def test_draft_assets_are_addressed_by_numeric_release_id() -> None:
    text = _workflow_text()

    assert "gh release upload" not in text
    assert "releases/$RELEASE_ID/assets?name=$QUAL_ASSET_NAME" in text
    assert '"https://api.github.com/repos/$GITHUB_REPOSITORY/releases/$RELEASE_ID"' in text
    assert "-X PATCH" in text
    assert "find_release" in text
    assert "find_release || true" not in text
    assert 'if [ "$FIND_STATUS" -eq 1 ]; then' in text
    assert "Qualification release lookup failed with status" in text


def test_qualification_proves_anchor_restore_and_immutability() -> None:
    text = _workflow_text()

    assert 'jq -r \'.immutable\'' in text
    assert '"sha256:$EXPECTED_SHA256"' in text
    assert "releases/assets/$ASSET_ID" in text
    assert "-X DELETE" in text
    assert "Immutable qualification asset was unexpectedly deletable" in text
    assert "cmp \"$EXPECTED\" \"$RESTORED\"" in text
    assert "Independent restore matched exact synthetic bytes" in text


def test_artifact_actions_are_pinned() -> None:
    text = _workflow_text()

    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in text
    assert "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093" in text
