from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

import qntylab.pinned_dsh_provider_boundary_repair_v0 as repair


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests/fixtures/pinned_dsh_provider_boundary_v0"
FIXTURE_SOURCE = FIXTURE_ROOT / repair.PROVIDER_SOURCE_PATH
EXPECTED_IDENTITY = {
    "repository": repair.DSH_REPOSITORY,
    "commit": repair.DSH_COMMIT,
    "tree": repair.DSH_TREE,
    "tag": repair.DSH_TAG,
    "tracked_status": "",
    "matches": True,
}


def _fake_git(root: Path, *args: str) -> str:
    del root
    return {
        ("rev-parse", "HEAD"): repair.DSH_COMMIT,
        ("rev-parse", "HEAD^{tree}"): repair.DSH_TREE,
        ("tag", "--points-at", "HEAD"): repair.DSH_TAG,
        ("status", "--porcelain", "--untracked-files=no"): "",
    }[args]


def _fixture_with_git(tmp_path: Path) -> Path:
    root = tmp_path / "pinned-dsh"
    shutil.copytree(FIXTURE_ROOT, root)
    (root / ".git").mkdir()
    return root


def test_real_pinned_source_identity_is_observed_when_materialized_locally():
    root = Path("/home/swirky/DevHub/dsh-pinned-materialization-v0")
    if not (root / ".git").exists():
        pytest.skip("local pinned DSH checkout is not available")
    identity = repair.inspect_pinned_identity(root)
    assert identity == EXPECTED_IDENTITY


def test_materializer_exercises_real_provider_source_path(monkeypatch, tmp_path):
    monkeypatch.setattr(repair, "_git", _fake_git)
    root = _fixture_with_git(tmp_path)
    output = tmp_path / "materialized"

    record = repair.materialize_provider_boundary(root, output)

    assert record["dsh"] == EXPECTED_IDENTITY
    assert record["provider_source_path"] == repair.PROVIDER_SOURCE_PATH
    assert record["upstream_source_sha256"] == repair.UPSTREAM_SOURCE_SHA256
    assert record["upstream_preimage_sha256"] == repair.UPSTREAM_PREIMAGE_SHA256
    assert record["repaired_postimage_sha256"] == repair.REPAIRED_POSTIMAGE_SHA256
    assert record["semantic_delta_count"] == 2
    assert record["output_is_outside_upstream"] is True
    captured = repair.captured_thread_start_contract(output / repair.PROVIDER_SOURCE_PATH)
    captured["cwd"] = "/offline/workspace"
    assert repair.validate_thread_start_contract(captured, "/offline/workspace") == {
        "cwd": "/offline/workspace",
        "ephemeral": True,
        "approvalPolicy": "never",
        "sandbox": "workspace-write",
    }


def test_exact_source_preimage_and_postimage_are_bound():
    source = FIXTURE_SOURCE.read_text(encoding="utf-8")
    start = source.index(repair.PREIMAGE_METHOD_START)
    end = source.index(repair.PREIMAGE_METHOD_END, start)
    span = source[start:end]
    assert hashlib.sha256(source.encode()).hexdigest() == repair.UPSTREAM_SOURCE_SHA256
    assert hashlib.sha256(span.encode()).hexdigest() == repair.UPSTREAM_PREIMAGE_SHA256
    repaired, patch = repair._repaired_source(source)
    assert patch["semantic_delta_count"] == 2
    start = repaired.index(repair.PREIMAGE_METHOD_START)
    end = repaired.index(repair.PREIMAGE_METHOD_END, start)
    assert hashlib.sha256(repaired[start:end].encode()).hexdigest() == repair.REPAIRED_POSTIMAGE_SHA256


def test_wrong_identity_fails_closed(monkeypatch, tmp_path):
    def wrong_git(root: Path, *args: str) -> str:
        value = _fake_git(root, *args)
        return "wrong" if args == ("rev-parse", "HEAD") else value

    monkeypatch.setattr(repair, "_git", wrong_git)
    root = _fixture_with_git(tmp_path)
    with pytest.raises(repair.ProviderBoundaryError, match="identity"):
        repair.materialize_provider_boundary(root, tmp_path / "out")


def test_wrong_preimage_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(repair, "_git", _fake_git)
    root = _fixture_with_git(tmp_path)
    source = root / repair.PROVIDER_SOURCE_PATH
    source.write_text(source.read_text(encoding="utf-8").replace("ephemeral: true", "ephemeral: false", 1), encoding="utf-8")
    with pytest.raises(repair.ProviderBoundaryError, match="preimage"):
        repair.materialize_provider_boundary(root, tmp_path / "out")


def test_malformed_policy_fails_closed_and_no_fallback_exists():
    valid = {"cwd": "/w", "ephemeral": True, "approvalPolicy": "never", "sandbox": "workspace-write"}
    assert repair.validate_thread_start_contract(valid, "/w")["sandbox"] == "workspace-write"
    with pytest.raises(repair.ProviderBoundaryError):
        repair.validate_thread_start_contract({**valid, "sandboxPolicy": {}}, "/w")
    with pytest.raises(repair.ProviderBoundaryError):
        repair.validate_thread_start_contract({**valid, "sandbox": "read-only"}, "/w")


def test_no_forbidden_permission_layers_or_semantic_changes():
    before = FIXTURE_SOURCE.read_text(encoding="utf-8")
    after, _ = repair._repaired_source(before)
    start_before = before.index(repair.PREIMAGE_METHOD_START)
    end_before = before.index(repair.PREIMAGE_METHOD_END, start_before)
    start_after = after.index(repair.PREIMAGE_METHOD_START)
    end_after = after.index(repair.PREIMAGE_METHOD_END, start_after)
    assert before[:start_before] + before[end_before:] == after[:start_after] + after[end_after:]
    repaired_span = after[start_after:end_after]
    assert repaired_span.count("approvalPolicy: 'never'") == 1
    assert repaired_span.count("sandbox: 'workspace-write'") == 1
    assert not any(field in repaired_span for field in repair.FORBIDDEN_PROVIDER_FIELDS)
    assert repair.semantic_repair_delta() == [
        {"path": "thread/start.params.approvalPolicy", "before": "<ABSENT>", "after": "never"},
        {"path": "thread/start.params.sandbox", "before": "<ABSENT>", "after": "workspace-write"},
    ]


def test_no_product_process_or_profile_authority_is_in_repair_module():
    text = (ROOT / "qntylab/pinned_dsh_provider_boundary_repair_v0.py").read_text(encoding="utf-8")
    assert "subprocess.run" in text
    assert "app-server" not in text.lower()
    assert "node " not in text.lower()
    assert "config.toml" not in text
    assert "CODEX_HOME" not in text
    assert "trust_level" not in text


def test_c_and_d_contract_and_historical_results_are_not_rewritten():
    auth = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_provider_boundary_final_closeout_authorization_v0/authorization.json"
    assert "26b4f3cadef2d03ed9b0a8f2bc4b30e99bc1a970daca1a26a333dec1eeafd44b" in auth.read_text()
    assert '"classification": "INCONCLUSIVE_INFRA"' in auth.read_text()
    assert '"classification": "PROFILE_MUTATED_RECORDED"' in auth.read_text()
