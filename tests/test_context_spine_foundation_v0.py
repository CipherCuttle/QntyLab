"""Context Spine PR-A foundation contract.

These tests bind the foundation compiler to its invariants: it is a read-only,
deterministic projection of canonical local repository bytes, it fails closed on
malformed or mutually contradictory foundation state, it never claims
cross-repository observation it does not perform, and the generic engine holds
no instance history.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import socket
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
SPINE_COMMAND = [sys.executable, "-m", "qntylab.project_context", "spine"]


def _config(**authority: str) -> dict[str, Any]:
    keys = {
        "global_architecture_registry": "docs/ADR/registry.toml",
        "project_registry": "docs/state/projects.toml",
        "ecosystem_catalog": "docs/state/ecosystem.toml",
        "current_roadmap": "docs/CURRENT_ROADMAP.md",
        "research_ledger_root": "experiments/research",
    }
    keys.update(authority)
    return {"schema_version": 1, "repository_id": "LocalRepo", "authority": keys}


def _tracked_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "docs/ADR").mkdir(parents=True)
    (root / "docs/state").mkdir(parents=True)
    (root / "experiments/research").mkdir(parents=True)
    for relative in _config()["authority"].values():
        if relative != "experiments/research":
            (root / relative).write_text("tracked\n", encoding="utf-8")
    (root / "experiments/research/ledger.json").write_text("{}\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    return root


def _catalog(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 1,
        "ecosystem_id": "TEST_ECOSYSTEM",
        "architecture": {"architecture_authority": "ADR-GLOBAL", "scientific_north_star": "ADR-NORTH"},
        "repository": [
            {
                "repository_id": "LocalRepo",
                "durable_role": "LOCAL_ROLE",
                "default_branch": "master",
                "context_access": "LOCAL_CANONICAL_SOURCES",
                "adapter_status": "NOT_APPLICABLE",
            },
            {
                "repository_id": "RemoteRepo",
                "durable_role": "REMOTE_ROLE",
                "default_branch": "main",
                "context_access": "NARROW_READ_ONLY_ADAPTER",
                "adapter_status": "ADAPTER_NOT_IMPLEMENTED",
            },
        ],
    }
    value.update(overrides)
    return value


def _validate(tmp_path: Path, catalog: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    _tracked_root(tmp_path) if not (tmp_path / "repo").exists() else None
    return project_context.validate_ecosystem_catalog(config or _config(), catalog)


QNTYLAB_TOML = """schema_version = 1
repository_id = "LocalRepo"

[authority]
global_architecture_registry = "docs/ADR/registry.toml"
project_registry = "docs/state/projects.toml"
ecosystem_catalog = "docs/state/ecosystem.toml"
current_roadmap = "docs/CURRENT_ROADMAP.md"
research_ledger_root = "experiments/research"

[data]
registry_status = "NOT_ESTABLISHED"
"""

ADR_REGISTRY_TOML = """schema_version = 1

[[adr]]
adr_id = "ADR-GLOBAL"
path = "docs/ADR/global.md"
status = "CURRENT_GLOBAL"
authority_scope = "GLOBAL_ARCHITECTURE"

[[adr]]
adr_id = "ADR-NORTH"
path = "docs/ADR/north.md"
status = "CURRENT_GLOBAL_COMPANION"
authority_scope = "GLOBAL_SCIENTIFIC_NORTH_STAR"
"""

PROJECTS_TOML = """schema_version = 1

[[project]]
project_id = "PLACEHOLDER"
state = "PLANNED_NOT_AUTHORIZED"
authority_level = "NONE"
next_action = "Nothing is authorized."
implementation_authorized = false
authoritative_artifacts = ["docs/state/projects.toml"]
"""


def _ecosystem_toml(*, authority: str = "ADR-GLOBAL", north_star: str = "ADR-NORTH", local: str = "LocalRepo") -> str:
    return f"""schema_version = 1
ecosystem_id = "TEST_ECOSYSTEM"

[architecture]
architecture_authority = "{authority}"
scientific_north_star = "{north_star}"

[[repository]]
repository_id = "{local}"
durable_role = "LOCAL_ROLE"
default_branch = "master"
context_access = "LOCAL_CANONICAL_SOURCES"
adapter_status = "NOT_APPLICABLE"

[[repository]]
repository_id = "RemoteRepo"
durable_role = "REMOTE_ROLE"
default_branch = "main"
context_access = "NARROW_READ_ONLY_ADAPTER"
adapter_status = "ADAPTER_NOT_IMPLEMENTED"

"""


def _spine_root(tmp_path: Path, *, catalog: str | None = _ecosystem_toml(), config: str = QNTYLAB_TOML) -> Path:
    """A self-contained repository the compiler can be driven against end to end."""
    root = tmp_path / "spine-repo"
    (root / "docs/ADR").mkdir(parents=True)
    (root / "docs/state").mkdir(parents=True)
    (root / "experiments/research").mkdir(parents=True)
    files = {
        "qntylab.toml": config,
        "docs/ADR/registry.toml": ADR_REGISTRY_TOML,
        "docs/ADR/global.md": "global architecture\n",
        "docs/ADR/north.md": "scientific north star\n",
        "docs/CURRENT_ROADMAP.md": "roadmap\n",
        "docs/state/projects.toml": PROJECTS_TOML,
        "experiments/research/state.json": "{}\n",
    }
    if catalog is not None:
        files["docs/state/ecosystem.toml"] = catalog
    for relative, body in files.items():
        (root / relative).write_text(body, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "fixture"],
        check=True,
        env={"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "PATH": os.environ["PATH"]},
    )
    return root


def _spine_cli(root: Path, *command: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run([sys.executable, "-m", "qntylab.project_context", "--root", str(root), *command], cwd=ROOT, capture_output=True)


def _tracked_tree_digest(root: Path) -> str:
    listing = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], check=True, capture_output=True).stdout
    digest = hashlib.sha256(listing)
    for relative in sorted(name for name in listing.decode("utf-8").split("\0") if name):
        digest.update(relative.encode("utf-8"))
        digest.update(hashlib.sha256((root / relative).read_bytes()).digest())
    return digest.hexdigest()


def _git_dir(root: Path) -> Path:
    """The repository's Git directory, resolved without invoking Git.

    A linked worktree's ``.git`` is a file naming the real directory, so this
    has to be followed by hand to keep the measurement Git-free.
    """
    marker = root / ".git"
    if marker.is_dir():
        return marker
    return (root / marker.read_text(encoding="utf-8").split("gitdir:", 1)[1].strip()).resolve()


def _git_dir_snapshot(root: Path) -> dict[str, Any]:
    """Raw Git state read straight off disk.

    Deliberately shells out to nothing. A measurement that ran ``git status``
    would refresh the index stat cache itself and so hide exactly the write it
    is supposed to observe.
    """
    git_dir = _git_dir(root)
    commondir = git_dir / "commondir"
    common = (git_dir / commondir.read_text(encoding="utf-8").strip()).resolve() if commondir.exists() else git_dir
    index = git_dir / "index"
    packed_refs = common / "packed-refs"
    refs = []
    for base in {git_dir, common}:
        refs.extend((path.relative_to(base).as_posix(), path.read_bytes()) for path in (base / "refs").rglob("*") if path.is_file())
    return {
        "index_bytes": index.read_bytes() if index.exists() else None,
        "index_mtime_ns": index.stat().st_mtime_ns if index.exists() else None,
        "index_lock": (git_dir / "index.lock").exists(),
        "head": (git_dir / "HEAD").read_bytes(),
        "refs": sorted(refs),
        "packed_refs": packed_refs.read_bytes() if packed_refs.exists() else None,
    }


def _stale_stat_cache(root: Path) -> None:
    """Age every tracked file without changing a byte of it.

    This is the ordinary post-checkout condition, and the only state in which an
    otherwise read-only Git command rewrites the index.
    """
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            os.utime(path, (0, 0))


# --- Catalog validation -------------------------------------------------


def test_catalog_validation_pass(tmp_path: Path) -> None:
    normalized = _validate(tmp_path, _catalog())
    assert normalized["ecosystem_id"] == "TEST_ECOSYSTEM"
    assert normalized["local_repository_id"] == "LocalRepo"
    assert sorted(normalized["repositories"]) == ["LocalRepo", "RemoteRepo"]
    # The catalog carries ecosystem semantics only; it declares no source set.
    assert set(normalized) == {"ecosystem_id", "architecture_references", "repositories", "local_repository_id"}


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda catalog: catalog.update(schema_version=2), "schema_version"),
        (lambda catalog: catalog.pop("ecosystem_id"), "ecosystem_id"),
        (lambda catalog: catalog.pop("architecture"), r"\[architecture\]"),
        (lambda catalog: catalog["architecture"].pop("scientific_north_star"), "scientific_north_star"),
        (lambda catalog: catalog["architecture"].pop("architecture_authority"), "architecture_authority"),
        (lambda catalog: catalog.update(repository="not-a-list"), "must be an array"),
        (lambda catalog: catalog.update(repository=[]), "exactly one LOCAL_CANONICAL_SOURCES"),
        (lambda catalog: catalog["repository"].append(copy.deepcopy(catalog["repository"][0])), "duplicate ecosystem repository"),
        (lambda catalog: catalog["repository"][1].update(context_access="TOTALLY_NEW"), "unknown context_access"),
        (lambda catalog: catalog["repository"][1].update(adapter_status="ADAPTER_IMPLEMENTED"), "unknown adapter_status"),
        (lambda catalog: catalog["repository"][1].update(adapter_status="NOT_APPLICABLE"), "contradicts context_access"),
        (lambda catalog: catalog["repository"][0].update(adapter_status="ADAPTER_NOT_IMPLEMENTED"), "contradicts context_access"),
        (lambda catalog: catalog["repository"][0].update(context_access="NARROW_READ_ONLY_ADAPTER", adapter_status="ADAPTER_NOT_IMPLEMENTED"), "exactly one LOCAL_CANONICAL_SOURCES"),
        (lambda catalog: catalog["repository"][1].update(context_access="LOCAL_CANONICAL_SOURCES", adapter_status="NOT_APPLICABLE"), "exactly one LOCAL_CANONICAL_SOURCES"),
        (lambda catalog: catalog["repository"][0].pop("default_branch"), "default_branch"),
        (lambda catalog: catalog["repository"][0].pop("durable_role"), "durable_role"),
    ],
)
def test_malformed_foundation_fails_closed(tmp_path: Path, mutate: Any, message: str) -> None:
    catalog = _catalog()
    mutate(catalog)
    with pytest.raises(project_context.ProjectContextError, match=message):
        _validate(tmp_path, catalog)


def test_no_implemented_adapter_token_exists_at_this_schema_version() -> None:
    """A catalog cannot spell cross-repository observation that no code performs."""
    assert project_context.ADAPTER_STATUSES == frozenset({"NOT_APPLICABLE", "ADAPTER_NOT_IMPLEMENTED"})


# --- Derived context sources --------------------------------------------


def test_context_sources_are_derived_from_authority_not_declared_by_the_catalog() -> None:
    """The catalog has no say over which sources exist or where they rank."""
    catalog = tomllib.loads((ROOT / "docs/state/ecosystem.toml").read_text(encoding="utf-8"))
    assert "context_source" not in catalog
    assert "precedence_class" not in (ROOT / "docs/state/ecosystem.toml").read_text(encoding="utf-8")

    sources = project_context._context_sources(_config())
    assert sources["CANONICAL_GIT_IDENTITY"]["precedence_rank"] == 1
    assert sources["PROJECT_REGISTRY"]["precedence_rank"] == 2
    assert sources["GLOBAL_ARCHITECTURE_REGISTRY"]["precedence_rank"] == 3
    assert sources["RESEARCH_LEDGER_ROOT"]["precedence_rank"] == 4
    # A generated view stays below the contract it is generated from.
    assert sources["CURRENT_ROADMAP"]["precedence_rank"] == 6
    for source in sources.values():
        assert source["precedence_class"] == project_context.PRECEDENCE_CLASSES[source["precedence_rank"] - 1]


def test_every_authority_source_appears_exactly_once() -> None:
    """The source set is total over [authority], so none can be omitted or doubled."""
    config = _config()
    sources = project_context._context_sources(config)
    bound = [source["authority_key"] for source in sources.values() if source["authority_key"]]
    assert sorted(bound) == sorted(config["authority"])
    assert len(bound) == len(set(bound))
    assert len(sources) == len(config["authority"]) + 1  # plus the intrinsic Git identity


def test_exactly_one_intrinsic_canonical_git_identity_source_exists() -> None:
    sources = project_context._context_sources(_config())
    intrinsic = [source for source in sources.values() if source["source_kind"] == "INTRINSIC"]
    assert len(intrinsic) == 1
    assert intrinsic[0]["precedence_class"] == "CANONICAL_GIT_IDENTITY"
    assert intrinsic[0]["authority_key"] is None and intrinsic[0]["path"] is None
    # No file-backed source may occupy rank 1.
    assert [source["source_id"] for source in sources.values() if source["precedence_rank"] == 1] == ["CANONICAL_GIT_IDENTITY"]


def test_unclassified_authority_source_fails_closed() -> None:
    """Adding a canonical source without ranking it cannot silently shrink the packet."""
    with pytest.raises(project_context.ProjectContextError, match="no precedence class: new_canonical_registry"):
        project_context._context_sources(_config(new_canonical_registry="docs/state/projects.toml"))


def test_two_authority_keys_cannot_bind_the_same_path() -> None:
    """One file must not appear at two contradictory precedence ranks."""
    with pytest.raises(project_context.ProjectContextError, match="bind the same path"):
        project_context._context_sources(_config(current_roadmap="docs/state/projects.toml"))


def test_every_derived_source_is_owned_by_the_local_repository() -> None:
    config = _config()
    assert all(source["repository_id"] == config["repository_id"] for source in project_context._context_sources(config).values())


def test_authority_paths_cannot_reach_outside_the_repository(tmp_path: Path) -> None:
    root = _spine_root(tmp_path, config=QNTYLAB_TOML.replace('project_registry = "docs/state/projects.toml"', 'project_registry = "../outside.toml"'))
    with pytest.raises(project_context.ProjectContextError, match="repository-relative|escapes repository"):
        project_context.compile_context_spine(root)


# --- Compiled packet ----------------------------------------------------


def test_foundation_packet_schema_valid() -> None:
    packet = project_context.compile_context_spine(ROOT)
    assert packet["context_spine_version"] == project_context.CONTEXT_SPINE_VERSION
    assert packet["packet_status"] == project_context.CONTEXT_SPINE_COMPILED
    assert packet["conflicts"] == []
    assert set(packet) == {
        "architecture",
        "architecture_relevance_contract",
        "conflicts",
        "context_sources",
        "context_spine_version",
        "ecosystem_id",
        "external_repositories",
        "generated_from",
        "packet_status",
        "prohibitions",
        "repository",
    }
    assert packet["repository"]["context_access"] == "LOCAL_CANONICAL_SOURCES"
    assert all(source["repository_id"] == packet["repository"]["repository_id"] for source in packet["context_sources"])
    assert packet["architecture_relevance_contract"]["evaluation_status"] == "NOT_IMPLEMENTED"


def test_adr0007_resolves_as_global_architecture_and_adr0005_as_scientific_companion() -> None:
    architecture = project_context.compile_context_spine(ROOT)["architecture"]
    assert architecture["current_global"] == {
        "adr_id": "ADR-0007",
        "authority_scope": "GLOBAL_ARCHITECTURE",
        "path": "docs/ADR/0007-ecosystem-role-boundary-and-context-spine-governance.md",
        "status": "CURRENT_GLOBAL",
    }
    assert architecture["scientific_north_star"] == {
        "adr_id": "ADR-0005",
        "authority_scope": "GLOBAL_SCIENTIFIC_NORTH_STAR",
        "path": "docs/ADR/0005-qntylab-north-star-market-intelligence-architecture.md",
        "status": "CURRENT_GLOBAL_COMPANION",
    }
    assert architecture["scientific_north_star"]["authority_scope"] != architecture["current_global"]["authority_scope"]
    assert [item["adr_id"] for item in architecture["companions"]] == ["ADR-0005", "ADR-0006"]


def test_external_adapter_status_is_explicit_not_implemented() -> None:
    packet = project_context.compile_context_spine(ROOT)
    external = {record["repository_id"]: record for record in packet["external_repositories"]}
    assert sorted(external) == ["Qnty", "QntyAgentEval", "QntyPolicyGate"]
    for record in external.values():
        assert record["adapter_status"] == "ADAPTER_NOT_IMPLEMENTED"
        assert record["context_state"] == "UNAVAILABLE_WITHOUT_ADAPTER"
        assert record["context_access"] == "NARROW_READ_ONLY_ADAPTER"
    assert packet["repository"]["repository_id"] not in external


def test_git_identity_binds_bytes_without_creating_authority() -> None:
    packet = project_context.compile_context_spine(ROOT)
    identity = packet["generated_from"]["canonical_git_identity"]
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    assert identity["head_sha"] == head
    assert identity["worktree_status"] in {"CLEAN", "DIRTY"}
    assert packet["generated_from"]["git_identity_semantics"] == "GIT_IDENTITY_SELECTS_BYTES_NOT_SEMANTIC_AUTHORITY"
    # A commit ID must not appear anywhere an authority, status, or scope is decided.
    authority_surface = [packet["architecture"], packet["repository"], packet["external_repositories"], packet["context_sources"], packet["architecture_relevance_contract"]]
    assert head not in json.dumps(authority_surface)
    assert "GIT_IDENTITY_SELECTS_BYTES_AND_GRANTS_NO_SEMANTIC_AUTHORITY" in packet["prohibitions"]
    assert "CONTEXT_SPINE_IS_A_DERIVED_VIEW_AND_NEVER_AN_AUTHORITY_SOURCE" in packet["prohibitions"]


def test_packet_carries_no_host_path_or_wall_clock_leakage() -> None:
    serialized = project_context.context_spine_bytes(ROOT).decode("utf-8")
    assert str(ROOT) not in serialized
    for token in ("/home/", "/tmp/", "/Users/", "file://", "http://", "https://", "timestamp", "generated_at", "pid", "hostname"):
        assert token not in serialized
    # Every declared path is repository-relative.
    assert all(not Path(source["path"]).is_absolute() for source in json.loads(serialized)["context_sources"] if source["path"])


# --- Determinism and canonical serialization ----------------------------


def test_deterministic_same_input_same_output() -> None:
    assert project_context.context_spine_bytes(ROOT) == project_context.context_spine_bytes(ROOT)
    assert project_context.compile_context_spine(ROOT) == project_context.compile_context_spine(ROOT)


def test_canonical_serialization_stable_across_processes() -> None:
    first = subprocess.run(SPINE_COMMAND, cwd=ROOT, check=True, capture_output=True).stdout
    second = subprocess.run(SPINE_COMMAND, cwd=ROOT, check=True, capture_output=True).stdout
    assert first == second
    assert first == project_context.context_spine_bytes(ROOT) + b"\n"
    assert first == json.dumps(json.loads(first), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n"


def test_packet_is_insensitive_to_catalog_declaration_order(tmp_path: Path) -> None:
    blocks = _ecosystem_toml().split("\n\n")
    tables = [block for block in blocks if block.startswith("[[")]
    assert len(tables) == 2
    shuffled = "\n\n".join([block for block in blocks if not block.startswith("[[")] + list(reversed(tables)))
    forward_packet = project_context.compile_context_spine(_spine_root(tmp_path))
    reverse_packet = project_context.compile_context_spine(_spine_root(tmp_path / "shuffled", catalog=shuffled))
    for key in ("architecture", "context_sources", "external_repositories", "repository", "conflicts"):
        assert forward_packet[key] == reverse_packet[key]


# --- Fail-closed architecture conflict ----------------------------------


def _conflict_codes(catalog: dict[str, Any], config: dict[str, Any] | None = None) -> list[str]:
    adrs = {
        "ADR-GLOBAL": {"adr_id": "ADR-GLOBAL", "path": "docs/ADR/registry.toml", "status": "CURRENT_GLOBAL", "authority_scope": "GLOBAL_ARCHITECTURE"},
        "ADR-NORTH": {"adr_id": "ADR-NORTH", "path": "docs/ADR/registry.toml", "status": "CURRENT_GLOBAL_COMPANION", "authority_scope": "GLOBAL_SCIENTIFIC_NORTH_STAR"},
    }
    normalized = {
        "local_repository_id": catalog["repository"][0]["repository_id"],
        "architecture_references": catalog["architecture"],
        "context_sources": {},
    }
    conflicts, _ = project_context._architecture_conflicts(normalized, config or _config(), adrs, adrs["ADR-GLOBAL"])
    return [item["code"] for item in conflicts]


def test_architecture_conflict_detects_each_unreconciled_reference() -> None:
    assert _conflict_codes(_catalog()) == []
    catalog = _catalog()
    catalog["architecture"]["architecture_authority"] = "ADR-OTHER"
    assert _conflict_codes(catalog) == ["ARCHITECTURE_AUTHORITY_DISAGREEMENT"]
    catalog = _catalog()
    catalog["architecture"]["scientific_north_star"] = "ADR-GLOBAL"
    assert _conflict_codes(catalog) == ["SCIENTIFIC_NORTH_STAR_DISAGREEMENT"]
    catalog = _catalog()
    catalog["architecture"]["scientific_north_star"] = "ADR-MISSING"
    assert _conflict_codes(catalog) == ["SCIENTIFIC_NORTH_STAR_DISAGREEMENT"]
    catalog = _catalog()
    catalog["repository"][0]["repository_id"] = "OtherRepo"
    assert _conflict_codes(catalog) == ["REPOSITORY_IDENTITY_DISAGREEMENT"]


def test_reconciled_foundation_compiles_end_to_end(tmp_path: Path) -> None:
    root = _spine_root(tmp_path)
    packet = project_context.compile_context_spine(root)
    assert packet["packet_status"] == project_context.CONTEXT_SPINE_COMPILED
    assert packet["conflicts"] == []
    assert packet["architecture"]["scientific_north_star"]["adr_id"] == "ADR-NORTH"
    assert _spine_cli(root, "spine").returncode == 0


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"north_star": "ADR-GLOBAL"}, "SCIENTIFIC_NORTH_STAR_DISAGREEMENT"),
        ({"north_star": "ADR-ABSENT"}, "SCIENTIFIC_NORTH_STAR_DISAGREEMENT"),
        ({"authority": "ADR-NORTH"}, "ARCHITECTURE_AUTHORITY_DISAGREEMENT"),
        ({"local": "OtherRepo"}, "REPOSITORY_IDENTITY_DISAGREEMENT"),
    ],
    ids=["north-star-is-the-architecture-adr", "north-star-unregistered", "architecture-authority-mismatch", "repository-identity-mismatch"],
)
def test_architecture_conflict_fails_closed_end_to_end(tmp_path: Path, overrides: dict[str, str], code: str) -> None:
    root = _spine_root(tmp_path, catalog=_ecosystem_toml(**overrides))
    packet = project_context.compile_context_spine(root)
    assert packet["packet_status"] == project_context.ARCHITECTURE_CONFLICT
    assert [item["code"] for item in packet["conflicts"]] == [code]
    assert any("context spine conflict" in issue for issue in project_context.doctor(root))

    completed = _spine_cli(root, "spine")
    assert completed.returncode == 1
    # The conflict is reported rather than resolved: the packet still ships.
    assert json.loads(completed.stdout)["packet_status"] == "ARCHITECTURE_CONFLICT"
    assert _spine_cli(root, "doctor", "--strict").returncode == 1


COMPILED_INPUTS = ["docs/ADR/registry.toml", "docs/state/ecosystem.toml", "docs/state/projects.toml", "qntylab.toml"]


def _identity(root: Path) -> dict[str, Any]:
    return project_context.compile_context_spine(root)["generated_from"]["canonical_git_identity"]


def test_uncommitted_worktree_is_declared_not_bound_to_the_head_commit(tmp_path: Path) -> None:
    root = _spine_root(tmp_path)
    identity = _identity(root)
    assert identity["worktree_status"] == "CLEAN"
    assert identity["compiled_bytes_bound_to_head_sha"] is True
    assert identity["compiled_inputs"] == COMPILED_INPUTS
    assert identity["unbound_compiled_inputs"] == []

    (root / "docs/state/projects.toml").write_text(PROJECTS_TOML.replace("Nothing is authorized.", "Still nothing."), encoding="utf-8")
    dirty = _identity(root)
    assert dirty["head_sha"] == identity["head_sha"]
    assert dirty["worktree_status"] == "DIRTY"
    # The head commit does not contain the compiled bytes, and the packet says so.
    assert dirty["compiled_bytes_bound_to_head_sha"] is False
    assert dirty["unbound_compiled_inputs"] == ["docs/state/projects.toml"]


def test_declared_compiled_inputs_are_the_files_the_compiler_actually_parses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The binding claim must not drift away from what compilation reads."""
    root = _spine_root(tmp_path)
    opened: list[str] = []
    real_load = project_context._load_toml

    def record(path: Path) -> Any:
        opened.append(Path(path).resolve().relative_to(root.resolve()).as_posix())
        return real_load(path)

    monkeypatch.setattr(project_context, "_load_toml", record)
    identity = _identity(root)
    assert sorted(set(opened)) == identity["compiled_inputs"]


def test_an_index_bit_cannot_falsify_the_binding_claim(tmp_path: Path) -> None:
    """``assume-unchanged`` is a self-report about the index, not about the bytes."""
    root = _spine_root(tmp_path)
    (root / "docs/state/projects.toml").write_text(PROJECTS_TOML.replace("Nothing is authorized.", "Still nothing."), encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "update-index", "--assume-unchanged", "docs/state/projects.toml"], check=True)

    identity = _identity(root)
    # Git now reports a clean tree; the bytes that were compiled disagree.
    assert identity["worktree_status"] == "CLEAN"
    assert identity["compiled_bytes_bound_to_head_sha"] is False
    assert identity["unbound_compiled_inputs"] == ["docs/state/projects.toml"]


def test_unrelated_dirty_bytes_do_not_falsify_the_binding_claim(tmp_path: Path) -> None:
    """The two provenance statements stay distinct rather than collapsing."""
    root = _spine_root(tmp_path)
    (root / "docs/CURRENT_ROADMAP.md").write_text("hand edited\n", encoding="utf-8")

    identity = _identity(root)
    assert identity["worktree_status"] == "DIRTY"
    # The roadmap is a declared source the compiler locates and never reads, so it
    # contributes no compiled bytes for the binding claim to be about.
    assert identity["compiled_bytes_bound_to_head_sha"] is True
    assert "docs/CURRENT_ROADMAP.md" not in identity["compiled_inputs"]


def test_an_untracked_file_is_never_compiled_canonical_content(tmp_path: Path) -> None:
    root = _spine_root(tmp_path)
    (root / "docs/state/stray.toml").write_text("stray = true\n", encoding="utf-8")

    identity = _identity(root)
    assert identity["worktree_status"] == "DIRTY"
    assert identity["compiled_bytes_bound_to_head_sha"] is True
    assert identity["compiled_inputs"] == COMPILED_INPUTS


def test_architecture_conflict_blocks_generated_view_mutation(tmp_path: Path) -> None:
    root = _spine_root(tmp_path, catalog=_ecosystem_toml(north_star="ADR-ABSENT"))
    roadmap = root / "docs/CURRENT_ROADMAP.md"
    before = roadmap.read_bytes()
    assert project_context.render(root, check=False) == 1
    assert roadmap.read_bytes() == before, "a conflicting foundation must not rewrite a generated view"
    assert project_context.render(root, check=True) == 1
    assert _spine_cli(root, "render").returncode == 1
    assert roadmap.read_bytes() == before


def test_authority_source_may_not_retype_a_registered_adr_document(tmp_path: Path) -> None:
    """One canonical path may not occupy two mutually exclusive precedence classes."""
    config = QNTYLAB_TOML.replace('current_roadmap = "docs/CURRENT_ROADMAP.md"', 'current_roadmap = "docs/ADR/global.md"')
    root = _spine_root(tmp_path, config=config)
    adr = root / "docs/ADR/global.md"
    before = adr.read_bytes()

    packet = project_context.compile_context_spine(root)
    assert packet["packet_status"] == project_context.ARCHITECTURE_CONFLICT
    assert [item["code"] for item in packet["conflicts"]] == ["SOURCE_CLASSIFICATION_DISAGREEMENT"]
    assert any("context spine conflict" in issue for issue in project_context.doctor(root))
    assert _spine_cli(root, "spine").returncode == 1
    assert _spine_cli(root, "doctor", "--strict").returncode == 1

    # The misdirection this closes: a stale-roadmap message inviting the render
    # that would overwrite the architecture contract with a generated view.
    # Rejection now happens earlier than the conflict, at the write capability:
    # this ADR is not the one destination the roadmap writer can address, so the
    # attempt never gets as far as being a conflict about a generated view.
    check = _spine_cli(root, "render", "--check")
    assert check.returncode == 2
    assert b"written only to docs/CURRENT_ROADMAP.md" in check.stderr and b"stale" not in check.stderr
    assert _spine_cli(root, "render").returncode == 2
    assert adr.read_bytes() == before


def test_authority_source_may_not_retype_the_declaration_that_names_it(tmp_path: Path) -> None:
    config = QNTYLAB_TOML.replace('current_roadmap = "docs/CURRENT_ROADMAP.md"', 'current_roadmap = "qntylab.toml"')
    root = _spine_root(tmp_path, config=config)
    before = (root / "qntylab.toml").read_bytes()

    packet = project_context.compile_context_spine(root)
    assert packet["packet_status"] == project_context.ARCHITECTURE_CONFLICT
    assert [item["code"] for item in packet["conflicts"]] == ["SOURCE_CLASSIFICATION_DISAGREEMENT"]
    # The declaration is likewise outside the roadmap writer's one destination,
    # so render refuses the target rather than merely refusing while conflicted.
    with pytest.raises(project_context.ProjectContextError, match="written only to docs/CURRENT_ROADMAP.md"):
        project_context.render(root, check=False)
    assert (root / "qntylab.toml").read_bytes() == before


def test_agreeing_classification_of_one_path_is_not_a_conflict() -> None:
    """The guard rejects contradiction, not every restatement of a path."""
    adrs = {"ADR-GLOBAL": {"adr_id": "ADR-GLOBAL", "path": "docs/ADR/global.md"}}
    # ``global_architecture_registry`` is itself a REGISTERED_ARCHITECTURE_CONTRACT,
    # so naming a registered ADR document restates its class rather than competing
    # with it; ``current_roadmap`` is a generated view and does compete.
    assert project_context._source_classification_conflicts(_config(global_architecture_registry="docs/ADR/global.md"), adrs) == []
    assert project_context._source_classification_conflicts(_config(current_roadmap="docs/ADR/global.md"), adrs)
    assert project_context._source_classification_conflicts(_config(), adrs) == []


def test_conflicting_reference_is_never_silently_replaced(tmp_path: Path) -> None:
    root = _spine_root(tmp_path, catalog=_ecosystem_toml(north_star="ADR-ABSENT"))
    architecture = project_context.compile_context_spine(root)["architecture"]
    assert architecture["scientific_north_star"] == {"adr_id": "ADR-ABSENT", "authority_scope": None, "path": None, "status": "NOT_ESTABLISHED"}
    # The registered companion is still visible; it is simply not promoted into the vacancy.
    assert [item["adr_id"] for item in architecture["companions"]] == ["ADR-NORTH"]


def test_missing_catalog_fails_every_project_context_entry_point(tmp_path: Path) -> None:
    root = _spine_root(tmp_path, catalog=None)
    for call in (project_context.compile_context_spine, project_context.load_context_sources, project_context.context_data):
        with pytest.raises(project_context.ProjectContextError, match="ecosystem.toml|ecosystem_catalog"):
            call(root)
    assert project_context.doctor(root)
    assert _spine_cli(root, "spine").returncode == 2
    assert _spine_cli(root, "render", "--check").returncode == 2


# --- Read-only, no network, no cross-repository reach --------------------


def test_read_only_compilation() -> None:
    before_tree = _tracked_tree_digest(ROOT)
    before_git = _git_dir_snapshot(ROOT)

    project_context.compile_context_spine(ROOT)
    project_context.context_spine_bytes(ROOT)
    subprocess.run(SPINE_COMMAND, cwd=ROOT, check=True, capture_output=True)

    # The index is read back before anything else touches Git.
    assert _git_dir_snapshot(ROOT) == before_git
    assert _tracked_tree_digest(ROOT) == before_tree


@pytest.mark.parametrize(
    "command",
    [("spine",), ("--json",), (), ("doctor", "--strict"), ("render", "--check")],
    ids=["spine", "json", "default", "doctor-strict", "render-check"],
)
def test_read_commands_never_write_the_git_index(tmp_path: Path, command: tuple[str, ...]) -> None:
    """Every read entry point stays read-only, stale stat cache included."""
    root = _spine_root(tmp_path)
    assert project_context.render(root, check=False) == 0
    _stale_stat_cache(root)
    before_tree = _tracked_tree_digest(root)
    before_git = _git_dir_snapshot(root)

    completed = _spine_cli(root, *command)
    assert completed.returncode != 2, completed.stderr

    assert _git_dir_snapshot(root) == before_git
    assert _tracked_tree_digest(root) == before_tree
    assert not (root / ".git/index.lock").exists()


def test_git_reads_ignore_an_ambient_git_location(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An inherited GIT_DIR must not redirect the compiler at another repository."""
    root = _spine_root(tmp_path)
    other = _spine_root(tmp_path / "other")
    subprocess.run(["git", "-C", str(other), "rm", "-q", "docs/CURRENT_ROADMAP.md"], check=True)
    expected = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()

    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    monkeypatch.setenv("GIT_INDEX_FILE", str(other / ".git/index"))
    identity = _identity(root)
    assert identity["head_sha"] == expected
    assert identity["worktree_status"] == "CLEAN"
    # The binding is resolved against this repository's HEAD, not the ambient one.
    assert identity["compiled_bytes_bound_to_head_sha"] is True
    assert identity["unbound_compiled_inputs"] == []


def test_render_check_does_not_write_the_git_index(tmp_path: Path) -> None:
    """Gating render on the foundation must not cost it its read-only check path."""
    root = _spine_root(tmp_path)
    index = root / ".git/index"
    assert project_context.render(root, check=False) == 0
    # A stale stat cache is what would make a read command rewrite the index.
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            os.utime(path, (0, 0))
    before = (index.read_bytes(), index.stat().st_mtime_ns)
    assert project_context.render(root, check=True) == 0
    assert (index.read_bytes(), index.stat().st_mtime_ns) == before
    assert not (root / ".git/index.lock").exists()


# --- Generated-view write capability --------------------------------------
#
# ``render`` is the compiler's only writer.  Its allowed write set is exactly the
# canonical generated CURRENT_ROADMAP destination, expressed as a positive
# capability rather than a denylist: a repository path is refused because it is
# not the supported destination, never because a classifier recognised it as
# sensitive.  Paths no classifier has heard of, and paths that do not exist yet,
# are therefore protected by construction.


# Extra victims the fixture repository carries so the sweep spans the real
# exploit class rather than only the sources the compiler already parses.
CAPABILITY_VICTIMS = {
    "experiments/research/CANDIDATE-A/frozen_result.json": '{"immutable": "evidence"}\n',
    "experiments/receipts/receipt-0001.json": '{"immutable": "receipt"}\n',
    "qntylab/some_implementation.py": "SOURCE = 'implementation'\n",
    "notes/ordinary.txt": "an ordinary tracked file with no classification\n",
    "notes/nested/deeper/unknown.txt": "a nested path no classifier knows\n",
    "docs/CURRENT_ROADMAP.md.bak": "adjacent to the real destination\n",
}

# Repository-relative paths that are not the supported destination.  The list
# deliberately mixes classified and wholly unclassified paths to show that
# classification is not what protects them.
UNAUTHORIZED_DESTINATIONS = (
    "docs/ADR/global.md",
    "docs/ADR/registry.toml",
    "docs/state/projects.toml",
    "docs/state/ecosystem.toml",
    "qntylab.toml",
    "experiments/research/CANDIDATE-A/frozen_result.json",
    "experiments/receipts/receipt-0001.json",
    "qntylab/some_implementation.py",
    "notes/ordinary.txt",
    "notes/nested/deeper/unknown.txt",
    "docs/CURRENT_ROADMAP.md.bak",
    # A repository-relative path that does not exist yet: a future file must be
    # outside the capability before anyone creates it.
    "docs/FUTURE_VIEW.md",
    "experiments/research/CANDIDATE-B/not_created_yet.json",
)

# Spellings that name the supported destination without being it.  Accepting any
# of them would reintroduce configuration-controlled path construction through
# normalization rather than through a second declared literal.
EQUIVALENT_LOOKING_SPELLINGS = (
    "./docs/CURRENT_ROADMAP.md",
    "docs//CURRENT_ROADMAP.md",
    "docs/./CURRENT_ROADMAP.md",
    "docs/../docs/CURRENT_ROADMAP.md",
    "/docs/CURRENT_ROADMAP.md",
    "../spine-repo/docs/CURRENT_ROADMAP.md",
    "docs/CURRENT_ROADMAP.md/",
    "DOCS/CURRENT_ROADMAP.md",
)


def _capability_root(tmp_path: Path, *, current_roadmap: str) -> Path:
    """A spine repository carrying extra victims, with the roadmap redirected."""
    config = QNTYLAB_TOML.replace(
        'current_roadmap = "docs/CURRENT_ROADMAP.md"',
        f'current_roadmap = "{current_roadmap}"',
    )
    root = _spine_root(tmp_path, config=config)
    for relative, body in CAPABILITY_VICTIMS.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(body, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "victims"],
        check=True,
        env={"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "PATH": os.environ["PATH"]},
    )
    return root


def _repository_bytes(root: Path) -> dict[str, bytes]:
    """Every repository-content file by exact bytes, Git internals excluded.

    Exit status alone would not prove the invariant, so rejection is measured as
    byte identity across the whole working tree.
    """
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


@pytest.mark.parametrize("target", UNAUTHORIZED_DESTINATIONS + EQUIVALENT_LOOKING_SPELLINGS)
def test_render_refuses_every_destination_but_its_own(tmp_path: Path, target: str) -> None:
    """Any target but the canonical destination fails closed and writes nothing."""
    root = _capability_root(tmp_path, current_roadmap=target)
    before = _repository_bytes(root)

    with pytest.raises(project_context.ProjectContextError):
        project_context.render(root, check=False)
    assert _repository_bytes(root) == before, f"render mutated repository content targeting {target}"

    # The same through the CLI, which is how the capability is actually reachable.
    completed = _spine_cli(root, "render")
    assert completed.returncode == 2, completed.stderr
    assert _repository_bytes(root) == before, f"the CLI mutated repository content targeting {target}"
    assert _spine_cli(root, "render", "--check").returncode == 2
    assert _repository_bytes(root) == before


def test_render_writes_exactly_its_canonical_destination(tmp_path: Path) -> None:
    """The positive half of the invariant: the allowed write set is that one file."""
    root = _capability_root(tmp_path, current_roadmap="docs/CURRENT_ROADMAP.md")
    before = _repository_bytes(root)

    assert project_context.render(root, check=False) == 0

    after = _repository_bytes(root)
    changed = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
    assert changed == ["docs/CURRENT_ROADMAP.md"]
    assert after["docs/CURRENT_ROADMAP.md"].startswith(b"# GENERATED")
    # ``--check`` agrees with what was just written and stays read-only.
    assert project_context.render(root, check=True) == 0
    assert _repository_bytes(root) == after


def test_accepted_destination_set_is_exactly_one_over_the_whole_repository(tmp_path: Path) -> None:
    """Sweep the declaration across every tracked path: exactly one is accepted.

    This is the generalization the denylist could not offer.  It asserts the size
    and identity of the accepted set rather than enumerating forbidden targets,
    so a path added to the repository later is covered without editing a list.
    """
    root = _capability_root(tmp_path, current_roadmap="docs/CURRENT_ROADMAP.md")
    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files"], check=True, capture_output=True, text=True
    ).stdout.split()
    assert len(tracked) > 10, "the sweep needs a repository with paths of several kinds"

    accepted = []
    for candidate in [*tracked, *UNAUTHORIZED_DESTINATIONS, *EQUIVALENT_LOOKING_SPELLINGS]:
        try:
            project_context._generated_view_destination(
                root, _config(current_roadmap=candidate), project_context.CURRENT_ROADMAP_VIEW
            )
        except project_context.ProjectContextError:
            continue
        accepted.append(candidate)

    assert sorted(set(accepted)) == ["docs/CURRENT_ROADMAP.md"]


def test_write_capability_is_a_compiler_owned_contract() -> None:
    """A second destination must cost a contract edit, not a configuration edit.

    Pinning the whole mapping is deliberate: a future developer who adds an entry
    has to change this assertion, which is the point at which the capability is
    reviewed rather than quietly widened.
    """
    assert project_context.GENERATED_VIEW_DESTINATIONS == {"CURRENT_ROADMAP": "docs/CURRENT_ROADMAP.md"}
    assert set(project_context.GENERATED_VIEW_AUTHORITY_KEYS) == set(project_context.GENERATED_VIEW_DESTINATIONS)
    assert project_context.CURRENT_ROADMAP_VIEW in project_context.GENERATED_VIEW_DESTINATIONS
    for destination in project_context.GENERATED_VIEW_DESTINATIONS.values():
        assert not Path(destination).is_absolute() and ".." not in Path(destination).parts
    # The repository's own declaration matches the supported destination, which is
    # what makes the shipped configuration valid rather than merely tolerated.
    assert tomllib.loads((ROOT / "qntylab.toml").read_text(encoding="utf-8"))["authority"]["current_roadmap"] == (
        project_context.GENERATED_VIEW_DESTINATIONS[project_context.CURRENT_ROADMAP_VIEW]
    )


def test_declared_roadmap_is_reconciled_and_never_followed(tmp_path: Path) -> None:
    """Configuration declares; it does not grant. A mismatch is not repaired."""
    root = _capability_root(tmp_path, current_roadmap="docs/state/projects.toml")
    config, _, _ = project_context.load_context_sources(root)

    with pytest.raises(project_context.ProjectContextError, match="written only to docs/CURRENT_ROADMAP.md"):
        project_context._generated_view_destination(root, config, project_context.CURRENT_ROADMAP_VIEW)

    # Not silently redirected to the supported path either: a declaration the
    # repository did not make must not become a write somewhere else.
    assert (root / "docs/CURRENT_ROADMAP.md").read_bytes() == b"roadmap\n"


def test_rejected_target_never_reaches_a_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reconciliation completes before mutation, so rejection is not a late abort."""
    root = _capability_root(tmp_path, current_roadmap="experiments/receipts/receipt-0001.json")

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("render attempted a write with an unauthorized destination")

    monkeypatch.setattr(Path, "write_bytes", refuse)
    monkeypatch.setattr(Path, "write_text", refuse)
    with pytest.raises(project_context.ProjectContextError):
        project_context.render(root, check=False)
    with pytest.raises(project_context.ProjectContextError):
        project_context.render(root, check=True)


def test_capability_holds_while_the_foundation_also_conflicts(tmp_path: Path) -> None:
    """The capability is independent of the conflict gate, not layered behind it."""
    config = QNTYLAB_TOML.replace(
        'current_roadmap = "docs/CURRENT_ROADMAP.md"', 'current_roadmap = "docs/state/projects.toml"'
    )
    root = _spine_root(tmp_path, catalog=_ecosystem_toml(north_star="ADR-ABSENT"), config=config)
    before = _repository_bytes(root)

    with pytest.raises(project_context.ProjectContextError, match="written only to docs/CURRENT_ROADMAP.md"):
        project_context.render(root, check=False)
    assert _repository_bytes(root) == before


def test_compilation_does_not_inherit_render_write_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Context Spine compilation must not write")

    monkeypatch.setattr(project_context, "render", refuse)
    monkeypatch.setattr(Path, "write_bytes", refuse)
    monkeypatch.setattr(Path, "write_text", refuse)
    monkeypatch.setattr(Path, "mkdir", refuse)
    monkeypatch.setattr(Path, "unlink", refuse)
    assert project_context.compile_context_spine(ROOT)["packet_status"] == project_context.CONTEXT_SPINE_COMPILED


def test_no_network_required(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Context Spine compilation must not use the network")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    assert project_context.compile_context_spine(ROOT)["packet_status"] == project_context.CONTEXT_SPINE_COMPILED


def test_no_cross_repo_mutation_or_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    real_run = subprocess.run

    def record(command: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(list(command))
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(project_context.subprocess, "run", record)
    project_context.compile_context_spine(ROOT)

    assert calls, "the compiler is expected to read canonical Git identity"
    for command in calls:
        # Only read-only Git plumbing, and only ever against this repository.
        # ``--no-optional-locks`` is part of the contract: it is what keeps a read
        # from refreshing the index stat cache.
        assert command[:3] == ["git", "--no-optional-locks", "-C"]
        assert Path(command[3]).resolve() == ROOT.resolve()
        assert command[4] in {"rev-parse", "status", "ls-files", "symbolic-ref", "cat-file"}


def test_compilation_reads_no_repository_other_than_its_own(tmp_path: Path) -> None:
    packet = project_context.compile_context_spine(ROOT)
    catalog = tomllib.loads((ROOT / "docs/state/ecosystem.toml").read_text(encoding="utf-8"))
    declared = {record["repository_id"] for record in catalog["repository"]}
    assert declared - {packet["repository"]["repository_id"]}, "the ecosystem has external participants to keep honest"
    # Every source the compiler resolves is a path inside this repository.
    for source in packet["context_sources"]:
        assert source["repository_id"] == packet["repository"]["repository_id"]
        if source["path"] is not None:
            assert (ROOT / source["path"]).exists()
            assert not Path(source["path"]).is_absolute()


# --- Anti-entropy: no instance history in generic code -------------------


def _generic_foundation_text() -> str:
    return (ROOT / "qntylab/project_context.py").read_text(encoding="utf-8") + (ROOT / "docs/state/ecosystem.toml").read_text(encoding="utf-8")


def _registered_projects() -> list[dict[str, Any]]:
    return tomllib.loads((ROOT / "docs/state/projects.toml").read_text(encoding="utf-8"))["project"]


def test_no_project_id_hardcoding() -> None:
    text = _generic_foundation_text()
    project_ids = [record["project_id"] for record in _registered_projects()]
    assert project_ids, "the registry is expected to carry projects the engine must not know"
    assert [project_id for project_id in project_ids if project_id in text] == []


def test_no_candidate_id_hardcoding() -> None:
    text = _generic_foundation_text()
    # ``trials`` and ``summaries`` are ledger schema directories, not candidate scopes.
    ledger_names = sorted({path.name for path in (ROOT / "experiments/research").iterdir() if path.is_dir()} - {"trials", "summaries"})
    assert len(ledger_names) > 5, "the ledger is expected to carry candidate scopes the engine must not know"
    assert [name for name in ledger_names if name in text] == []


def test_no_historical_next_action_hardcoding() -> None:
    text = _generic_foundation_text()
    next_actions = {record["next_action"] for record in _registered_projects()}
    assert next_actions
    assert [action for action in next_actions if action in text] == []
    for token in ("next_action", "NEXT_ACTION", "implementation_authorized", "authority_level"):
        assert token not in (ROOT / "docs/state/ecosystem.toml").read_text(encoding="utf-8")


def test_generic_foundation_embeds_no_commit_or_digest_literals() -> None:
    import re

    assert re.search(r"\b[0-9a-f]{40}\b", _generic_foundation_text()) is None
    assert re.search(r"\b[0-9a-f]{64}\b", _generic_foundation_text()) is None


def test_generic_foundation_knows_only_ecosystem_level_vocabulary() -> None:
    catalog = tomllib.loads((ROOT / "docs/state/ecosystem.toml").read_text(encoding="utf-8"))
    assert set(catalog) == {"schema_version", "ecosystem_id", "architecture", "repository"}
    # The catalog references canonical authority; it never copies its prose.
    assert set(catalog["architecture"]) == {"architecture_authority", "scientific_north_star"}
    assert all(len(value) < 16 for value in catalog["architecture"].values())
    assert (ROOT / "docs/state/ecosystem.toml").stat().st_size < 8192


# --- Scientific and planning state is untouched ---------------------------


def test_context_spine_creates_no_planning_or_scientific_authority() -> None:
    packet = project_context.compile_context_spine(ROOT)
    # ``prohibitions`` names these concepts precisely in order to deny them.
    asserted = json.dumps({key: value for key, value in packet.items() if key != "prohibitions"}).lower()
    for token in ("next_action", "implementation_authorized", "candidate", "promotion", "handoff", "authority_ceiling", "survivor", "capital"):
        assert token not in asserted
    assert "CONTEXT_SPINE_DOES_NOT_CREATE_OR_TRANSITION_A_PERMITTED_NEXT_ACTION" in packet["prohibitions"]
    assert "CONTEXT_SPINE_DOES_NOT_MUTATE_ANY_REPOSITORY_OR_SCIENTIFIC_STATE" in packet["prohibitions"]


def test_existing_project_context_surface_is_unchanged() -> None:
    data = project_context.context_data(ROOT)
    assert "context_spine" not in data
    assert data["current_global_adr"]["adr_id"] == "ADR-0007"
    assert data["authority_conflicts_or_warnings"] == []
