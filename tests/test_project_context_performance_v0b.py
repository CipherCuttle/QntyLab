from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from qntylab import project_context


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repo(tmp_path: Path, *, tracked: tuple[str, ...] = ()) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    for relative in tracked:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("tracked\n", encoding="utf-8")
    if tracked:
        _git(root, "add", "--", *tracked)
    return root


def test_snapshot_accepts_tracked_file_and_preserves_nul_delimited_names(tmp_path: Path) -> None:
    newline_name = "line\nname.md"
    root = _repo(tmp_path, tracked=("artifact.md", newline_name))
    snapshot = project_context.RepositorySnapshot.acquire(root)

    assert snapshot.contains_file("artifact.md")
    assert snapshot.contains_file(newline_name)
    assert project_context._authority_path(root, newline_name, label="newline artifact", snapshot=snapshot) == root / newline_name

    (root / "untracked.md").write_text("untracked\n", encoding="utf-8")
    with pytest.raises(project_context.ProjectContextError, match="not Git-tracked"):
        project_context._authority_path(root, "untracked.md", label="untracked artifact", snapshot=snapshot)


def test_missing_symlink_traversal_and_outside_paths_remain_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path, tracked=("artifact.md",))
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    (root / "link.md").symlink_to(outside)
    snapshot = project_context.RepositorySnapshot.acquire(root)

    (root / "artifact.md").unlink()
    with pytest.raises(project_context.ProjectContextError, match="must be a file|escapes repository"):
        project_context._authority_path(root, "artifact.md", label="deleted artifact", snapshot=snapshot)
    with pytest.raises(project_context.ProjectContextError, match="symlink|escapes repository"):
        project_context._authority_path(root, "link.md", label="symlink artifact", snapshot=snapshot)
    with pytest.raises(project_context.ProjectContextError, match="repository-relative"):
        project_context._authority_path(root, "../outside.md", label="traversal artifact", snapshot=snapshot)


def test_tracked_directory_requires_a_tracked_descendant(tmp_path: Path) -> None:
    root = _repo(tmp_path, tracked=("tracked-dir/child.md",))
    (root / "empty-dir").mkdir()
    snapshot = project_context.RepositorySnapshot.acquire(root)

    assert project_context._authority_directory(root, "tracked-dir", label="tracked directory", snapshot=snapshot) == root / "tracked-dir"
    with pytest.raises(project_context.ProjectContextError, match="not Git-tracked"):
        project_context._authority_directory(root, "empty-dir", label="empty directory", snapshot=snapshot)


def test_default_context_uses_one_census_and_no_per_artifact_ls_files(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    real_run = project_context.subprocess.run

    def record(command: object, *args: object, **kwargs: object):
        if isinstance(command, (list, tuple)) and command and command[0] == "git":
            calls.append(list(command))
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(project_context.subprocess, "run", record)
    project_context.context_data(Path(__file__).resolve().parents[1])

    ls_files = [command for command in calls if "ls-files" in command]
    assert len(ls_files) == 1
    assert "--cached" in ls_files[0]
    assert "-z" in ls_files[0]
    assert not any("--error-unmatch" in command for command in ls_files)


def test_default_context_validates_each_registry_once(monkeypatch: pytest.MonkeyPatch) -> None:
    counts = {"load": 0, "projects": 0, "adrs": 0}
    real_load = project_context.load_context_sources
    real_projects = project_context.validate_projects_registry
    real_adrs = project_context.validate_adr_registry

    def load(*args: object, **kwargs: object):
        counts["load"] += 1
        return real_load(*args, **kwargs)

    def projects(*args: object, **kwargs: object):
        counts["projects"] += 1
        return real_projects(*args, **kwargs)

    def adrs(*args: object, **kwargs: object):
        counts["adrs"] += 1
        return real_adrs(*args, **kwargs)

    monkeypatch.setattr(project_context, "load_context_sources", load)
    monkeypatch.setattr(project_context, "validate_projects_registry", projects)
    monkeypatch.setattr(project_context, "validate_adr_registry", adrs)
    project_context.context_data(Path(__file__).resolve().parents[1])

    assert counts == {"load": 1, "projects": 1, "adrs": 1}


def test_standalone_helper_reacquires_after_index_mutation(tmp_path: Path) -> None:
    root = _repo(tmp_path, tracked=("artifact.md",))
    stale = project_context.RepositorySnapshot.acquire(root)
    (root / "new.md").write_text("new\n", encoding="utf-8")
    _git(root, "add", "--", "new.md")

    with pytest.raises(project_context.ProjectContextError, match="not Git-tracked"):
        project_context._authority_path(root, "new.md", label="new artifact", snapshot=stale)
    assert project_context._authority_path(root, "new.md", label="new artifact") == root / "new.md"
