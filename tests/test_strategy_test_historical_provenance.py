from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from qntylab import strategy_test


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return proc.stdout.strip()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def fixture_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict[str, object], Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")

    raw = repo / "data/raw/SOLUSDT-1h.csv"
    raw.parent.mkdir(parents=True)
    old_bytes = b"timestamp,close\n2026-01-01T00:00:00Z,1\n2026-01-01T01:00:00Z,2\n"
    raw.write_bytes(old_bytes)
    source = repo / "evidence/source.json"
    source.parent.mkdir(parents=True)
    source.write_bytes(b'{"verified":true}\n')
    snapshot = repo / "data/manifests/SOLUSDT-1h.json"
    write_json(snapshot, {"rows": 2, "end": "2026-01-01T01:00:00Z", "sha256": sha(old_bytes)})
    git(repo, "add", "evidence/source.json", "data/manifests/SOLUSDT-1h.json")
    git(repo, "commit", "-m", "freeze provenance")
    commit = git(repo, "rev-parse", "HEAD")

    raw.write_bytes(old_bytes + b"2026-01-01T02:00:00Z,3\n")
    normalized = repo / "derived.csv"
    normalized.write_bytes(b"timestamp,close\n2026-01-01T00:00:00Z,1\n2026-01-01T01:00:00Z,2\n")
    manifest = repo / "manifest.json"
    manifest_value = {
        "normalization_id": "NORM_V1",
        "normalization_version": "V1",
        "reason_code": "HALT",
        "derived_path": "derived.csv",
        "derived_sha256": sha(normalized.read_bytes()),
        "source_resolution_artifact_path": "evidence/source.json",
        "source_resolution_artifact_sha256": sha(b'{"verified":true}\n'),
        "source_resolution_commit": commit,
        "authoritative_raw_path": "data/raw/SOLUSDT-1h.csv",
        "authoritative_raw_sha256": sha(old_bytes),
        "normalized_timestamp": "2026-01-01T01:00:00Z",
    }
    write_json(manifest, manifest_value)
    provenance: dict[str, object] = {
        "normalization_id": "NORM_V1",
        "normalization_version": "V1",
        "reason_code": "HALT",
        "derived_input_path": "derived.csv",
        "derived_input_sha256": sha(normalized.read_bytes()),
        "derived_manifest_path": "manifest.json",
        "derived_manifest_sha256": sha(manifest.read_bytes()),
        "source_resolution_artifact_path": "evidence/source.json",
        "source_resolution_artifact_sha256": sha(b'{"verified":true}\n'),
        "authoritative_raw_path": "data/raw/SOLUSDT-1h.csv",
        "authoritative_raw_sha256": sha(old_bytes),
        "normalized_timestamp": "2026-01-01T01:00:00Z",
        "source_resolution_git_commit": commit,
        "authoritative_raw_snapshot_manifest_path": "data/manifests/SOLUSDT-1h.json",
        "authoritative_raw_snapshot_manifest_git_commit": commit,
    }
    source.unlink()
    monkeypatch.chdir(repo)
    return repo, provenance, normalized, commit


def test_historical_provenance_accepts_exact_append_only_raw_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, provenance, normalized, _ = fixture_repo(tmp_path, monkeypatch)
    config_path = repo / "config.json"
    result = strategy_test.validate_normalization_provenance(
        provenance=provenance,
        normalized_input=normalized,
        input_sha256=sha(normalized.read_bytes()),
        config_path=config_path,
    )
    assert result is not None
    assert result["authoritative_raw_sha256"] == provenance["authoritative_raw_sha256"]


def test_historical_provenance_rejects_mutated_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, provenance, normalized, _ = fixture_repo(tmp_path, monkeypatch)
    raw = repo / "data/raw/SOLUSDT-1h.csv"
    raw.write_bytes(raw.read_bytes().replace(b",2\n", b",9\n", 1))
    with pytest.raises(ValueError, match="exact historical byte prefix"):
        strategy_test.validate_normalization_provenance(
            provenance=provenance,
            normalized_input=normalized,
            input_sha256=sha(normalized.read_bytes()),
            config_path=repo / "config.json",
        )


def test_historical_provenance_fails_if_git_evidence_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, provenance, normalized, _ = fixture_repo(tmp_path, monkeypatch)
    provenance["source_resolution_git_commit"] = "0" * 40
    with pytest.raises(FileNotFoundError, match="git object unavailable"):
        strategy_test.validate_normalization_provenance(
            provenance=provenance,
            normalized_input=normalized,
            input_sha256=sha(normalized.read_bytes()),
            config_path=repo / "config.json",
        )
