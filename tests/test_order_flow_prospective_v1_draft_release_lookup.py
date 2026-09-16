from __future__ import annotations

from types import SimpleNamespace

import pytest

from qntylab import order_flow_prospective_v1_operation as operation


def test_release_snapshot_falls_back_to_matching_draft_listing(monkeypatch):
    tag = f"{operation.RELEASE_PREFIX}000001-0123456789abcdef01234567"
    draft = {
        "tag_name": tag,
        "draft": True,
        "immutable": False,
        "assets": [],
    }

    monkeypatch.setattr(
        operation,
        "_run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="HTTP 404: Not Found",
        ),
    )
    monkeypatch.setattr(operation, "_list_evidence_releases", lambda: [draft])

    assert operation._release_snapshot(tag) == draft


def test_release_snapshot_rejects_duplicate_matching_drafts(monkeypatch):
    tag = f"{operation.RELEASE_PREFIX}000001-0123456789abcdef01234567"
    draft = {
        "tag_name": tag,
        "draft": True,
        "immutable": False,
        "assets": [],
    }

    monkeypatch.setattr(
        operation,
        "_run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="HTTP 404: Not Found",
        ),
    )
    monkeypatch.setattr(
        operation,
        "_list_evidence_releases",
        lambda: [draft, dict(draft)],
    )

    with pytest.raises(operation.OperationBlocked, match="multiple evidence releases"):
        operation._release_snapshot(tag)
