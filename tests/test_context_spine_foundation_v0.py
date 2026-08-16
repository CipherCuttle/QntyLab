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
        "context_source": [
            {
                "source_id": "CANONICAL_GIT_IDENTITY",
                "repository_id": "LocalRepo",
                "precedence_class": "CANONICAL_GIT_IDENTITY",
                "source_kind": "INTRINSIC",
            },
            {
                "source_id": "PROJECT_REGISTRY",
                "repository_id": "LocalRepo",
                "precedence_class": "REPOSITORY_MACHINE_READABLE_AUTHORITY_STATE",
                "source_kind": "FILE",
                "authority_key": "project_registry",
            },
            {
                "source_id": "RESEARCH_LEDGER",
                "repository_id": "LocalRepo",
                "precedence_class": "APPEND_ONLY_LEDGER_OR_IMMUTABLE_RECEIPT",
                "source_kind": "DIRECTORY",
                "authority_key": "research_ledger_root",
            },
        ]
        + [
            {
                "source_id": source_id,
                "repository_id": "LocalRepo",
                "precedence_class": precedence_class,
                "source_kind": "FILE",
                "authority_key": authority_key,
            }
            for source_id, authority_key, precedence_class in (
                ("ARCHITECTURE_REGISTRY", "global_architecture_registry", "REGISTERED_ARCHITECTURE_CONTRACT"),
                ("ECOSYSTEM_CATALOG", "ecosystem_catalog", "REPOSITORY_MACHINE_READABLE_AUTHORITY_STATE"),
                ("GENERATED_ROADMAP", "current_roadmap", "DETERMINISTIC_GENERATED_VIEW"),
            )
        ],
    }
    value.update(overrides)
    return value


def _validate(tmp_path: Path, catalog: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    root = tmp_path / "repo"
    if not root.exists():
        _tracked_root(tmp_path)
    return project_context.validate_ecosystem_catalog(root, config or _config(), catalog)


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

[[context_source]]
source_id = "CANONICAL_GIT_IDENTITY"
repository_id = "{local}"
precedence_class = "CANONICAL_GIT_IDENTITY"
source_kind = "INTRINSIC"

[[context_source]]
source_id = "PROJECT_REGISTRY"
repository_id = "{local}"
precedence_class = "REPOSITORY_MACHINE_READABLE_AUTHORITY_STATE"
source_kind = "FILE"
authority_key = "project_registry"

[[context_source]]
source_id = "ECOSYSTEM_CATALOG"
repository_id = "{local}"
precedence_class = "REPOSITORY_MACHINE_READABLE_AUTHORITY_STATE"
source_kind = "FILE"
authority_key = "ecosystem_catalog"

[[context_source]]
source_id = "ARCHITECTURE_REGISTRY"
repository_id = "{local}"
precedence_class = "REGISTERED_ARCHITECTURE_CONTRACT"
source_kind = "FILE"
authority_key = "global_architecture_registry"

[[context_source]]
source_id = "RESEARCH_LEDGER"
repository_id = "{local}"
precedence_class = "APPEND_ONLY_LEDGER_OR_IMMUTABLE_RECEIPT"
source_kind = "DIRECTORY"
authority_key = "research_ledger_root"

[[context_source]]
source_id = "GENERATED_ROADMAP"
repository_id = "{local}"
precedence_class = "DETERMINISTIC_GENERATED_VIEW"
source_kind = "FILE"
authority_key = "current_roadmap"

[[context_source]]
source_id = "DATASET_REGISTRY"
repository_id = "{local}"
precedence_class = "REPOSITORY_MACHINE_READABLE_AUTHORITY_STATE"
source_kind = "NOT_ESTABLISHED"
availability_key = "data.registry_status"
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


# --- Catalog validation -------------------------------------------------


def test_catalog_validation_pass(tmp_path: Path) -> None:
    normalized = _validate(tmp_path, _catalog())
    assert normalized["ecosystem_id"] == "TEST_ECOSYSTEM"
    assert normalized["local_repository_id"] == "LocalRepo"
    assert sorted(normalized["repositories"]) == ["LocalRepo", "RemoteRepo"]
    assert normalized["context_sources"]["RESEARCH_LEDGER"]["precedence_rank"] == 4


def test_precedence_rank_follows_the_adr_ladder_and_is_not_catalog_controlled(tmp_path: Path) -> None:
    catalog = _catalog()
    catalog["context_source"][1]["precedence_rank"] = 1
    sources = _validate(tmp_path, catalog)["context_sources"]
    assert sources["CANONICAL_GIT_IDENTITY"]["precedence_rank"] == 1
    assert sources["PROJECT_REGISTRY"]["precedence_rank"] == 2
    assert sources["RESEARCH_LEDGER"]["precedence_rank"] == 4
    assert sources["GENERATED_ROADMAP"]["precedence_rank"] == 6
    for source in sources.values():
        assert source["precedence_rank"] == project_context.PRECEDENCE_CLASSES.index(source["precedence_class"]) + 1


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda catalog: catalog.update(schema_version=2), "schema_version"),
        (lambda catalog: catalog.pop("ecosystem_id"), "ecosystem_id"),
        (lambda catalog: catalog.pop("architecture"), r"\[architecture\]"),
        (lambda catalog: catalog["architecture"].pop("scientific_north_star"), "scientific_north_star"),
        (lambda catalog: catalog.update(repository="not-a-list"), "must be an array"),
        (lambda catalog: catalog["repository"].append(copy.deepcopy(catalog["repository"][0])), "duplicate ecosystem repository"),
        (lambda catalog: catalog["repository"][1].update(context_access="TOTALLY_NEW"), "unknown context_access"),
        (lambda catalog: catalog["repository"][1].update(adapter_status="ADAPTER_IMPLEMENTED"), "unknown adapter_status"),
        (lambda catalog: catalog["repository"][1].update(adapter_status="NOT_APPLICABLE"), "contradicts context_access"),
        (lambda catalog: catalog["repository"][0].update(adapter_status="ADAPTER_NOT_IMPLEMENTED"), "contradicts context_access"),
        (lambda catalog: catalog["repository"][0].update(context_access="NARROW_READ_ONLY_ADAPTER", adapter_status="ADAPTER_NOT_IMPLEMENTED"), "exactly one LOCAL_CANONICAL_SOURCES"),
        (lambda catalog: catalog["repository"][1].update(context_access="LOCAL_CANONICAL_SOURCES", adapter_status="NOT_APPLICABLE"), "exactly one LOCAL_CANONICAL_SOURCES"),
        (lambda catalog: catalog["repository"][0].pop("default_branch"), "default_branch"),
        (lambda catalog: catalog["context_source"].append(copy.deepcopy(catalog["context_source"][1])), "duplicate context source"),
        (lambda catalog: catalog["context_source"][1].update(precedence_class="MOST_IMPORTANT"), "unknown precedence_class"),
        (lambda catalog: catalog["context_source"][1].update(source_kind="SOCKET"), "unknown source_kind"),
        (lambda catalog: catalog["context_source"][1].update(authority_key="undeclared_key"), "authority key is not declared"),
        (lambda catalog: catalog["context_source"][1].pop("authority_key"), "authority_key"),
        (lambda catalog: catalog["context_source"][0].update(authority_key="project_registry"), "may not bind an authority key"),
        (lambda catalog: catalog["context_source"][0].update(precedence_class="ORIENTATION_PROSE"), "canonical Git identity and intrinsic kind must agree"),
        (lambda catalog: catalog["context_source"][1].update(availability_key="data.registry_status"), "may not bind an availability key"),
        (lambda catalog: catalog["context_source"].pop(1), "no context source"),
        (lambda catalog: catalog["context_source"][2].update(source_kind="FILE"), "must be a file"),
        (lambda catalog: catalog["context_source"][1].update(source_kind="DIRECTORY"), "must be a non-symlink directory"),
        (lambda catalog: catalog.update(context_source=[]), "exactly one canonical Git identity"),
    ],
)
def test_malformed_foundation_fails_closed(tmp_path: Path, mutate: Any, message: str) -> None:
    catalog = _catalog()
    mutate(catalog)
    with pytest.raises(project_context.ProjectContextError, match=message):
        _validate(tmp_path, catalog)


def test_canonical_git_identity_class_cannot_be_claimed_by_a_tracked_file(tmp_path: Path) -> None:
    """A generated prose view must not be classifiable as the canonical Git identity."""
    catalog = _catalog()
    catalog["context_source"][-1]["precedence_class"] = "CANONICAL_GIT_IDENTITY"
    with pytest.raises(project_context.ProjectContextError, match="canonical Git identity and intrinsic kind must agree"):
        _validate(tmp_path, catalog)


def test_exactly_one_canonical_git_identity_source_is_required(tmp_path: Path) -> None:
    catalog = _catalog()
    catalog["context_source"].append({**copy.deepcopy(catalog["context_source"][0]), "source_id": "SECOND_GIT_IDENTITY"})
    with pytest.raises(project_context.ProjectContextError, match="exactly one canonical Git identity"):
        _validate(tmp_path, catalog)
    catalog = _catalog()
    catalog["context_source"].pop(0)
    with pytest.raises(project_context.ProjectContextError, match="exactly one canonical Git identity"):
        _validate(tmp_path, catalog)


def test_one_authority_key_cannot_be_bound_at_two_precedence_ranks(tmp_path: Path) -> None:
    catalog = _catalog()
    catalog["context_source"].append(
        {
            "source_id": "PROJECT_REGISTRY_AGAIN",
            "repository_id": "LocalRepo",
            "precedence_class": "NON_AUTHORITATIVE_CONVENIENCE",
            "source_kind": "FILE",
            "authority_key": "project_registry",
        }
    )
    with pytest.raises(project_context.ProjectContextError, match="bound by more than one context source"):
        _validate(tmp_path, catalog)


def test_every_declared_authority_source_must_be_classified(tmp_path: Path) -> None:
    """Adding a canonical source without cataloguing it cannot silently shrink the packet."""
    catalog = _catalog()
    config = _config(new_canonical_registry="docs/state/projects.toml")
    with pytest.raises(project_context.ProjectContextError, match="have no context source: new_canonical_registry"):
        project_context.validate_ecosystem_catalog(_tracked_root(tmp_path), config, catalog)


def test_unestablished_source_must_name_the_key_that_owns_its_status(tmp_path: Path) -> None:
    catalog = _catalog()
    unestablished = {
        "source_id": "FUTURE_SOURCE",
        "repository_id": "LocalRepo",
        "precedence_class": "REPOSITORY_MACHINE_READABLE_AUTHORITY_STATE",
        "source_kind": "NOT_ESTABLISHED",
    }
    catalog["context_source"].append(unestablished)
    with pytest.raises(project_context.ProjectContextError, match="availability_key"):
        _validate(tmp_path, catalog)
    unestablished["availability_key"] = "data.absent_key"
    with pytest.raises(project_context.ProjectContextError, match="does not resolve: data.absent_key"):
        _validate(tmp_path, catalog)


def test_unestablished_source_disagreeing_with_its_owner_is_an_architecture_conflict(tmp_path: Path) -> None:
    root = _spine_root(tmp_path, config=QNTYLAB_TOML.replace('registry_status = "NOT_ESTABLISHED"', 'registry_status = "ESTABLISHED"'))
    packet = project_context.compile_context_spine(root)
    assert packet["packet_status"] == project_context.ARCHITECTURE_CONFLICT
    assert [item["code"] for item in packet["conflicts"]] == ["CONTEXT_SOURCE_AVAILABILITY_DISAGREEMENT"]
    # The catalog's claim is reported, not quietly overwritten by the owning key.
    source = next(item for item in packet["context_sources"] if item["source_id"] == "DATASET_REGISTRY")
    assert source["availability"] == "NOT_ESTABLISHED"
    assert _spine_cli(root, "spine").returncode == 1


def test_context_source_owned_by_another_repository_is_rejected_because_no_adapter_exists(tmp_path: Path) -> None:
    catalog = _catalog()
    catalog["context_source"][1]["repository_id"] = "RemoteRepo"
    with pytest.raises(project_context.ProjectContextError, match="unimplemented cross-repository adapter"):
        _validate(tmp_path, catalog)


def test_context_source_owner_must_be_a_declared_ecosystem_repository(tmp_path: Path) -> None:
    catalog = _catalog()
    catalog["context_source"][1]["repository_id"] = "UnknownRepo"
    with pytest.raises(project_context.ProjectContextError, match="not an ecosystem repository"):
        _validate(tmp_path, catalog)


def test_catalog_cannot_reach_outside_the_repository(tmp_path: Path) -> None:
    root = _tracked_root(tmp_path)
    config = _config(project_registry="../outside.toml")
    with pytest.raises(project_context.ProjectContextError, match="repository-relative|escapes repository"):
        project_context.validate_ecosystem_catalog(root, config, _catalog())


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
    assert len(tables) > 5
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


def test_uncommitted_worktree_is_declared_not_bound_to_the_head_commit(tmp_path: Path) -> None:
    root = _spine_root(tmp_path)
    identity = project_context.compile_context_spine(root)["generated_from"]["canonical_git_identity"]
    assert identity["worktree_status"] == "CLEAN"
    assert identity["compiled_bytes_bound_to_head_sha"] is True

    (root / "docs/state/projects.toml").write_text(PROJECTS_TOML.replace("Nothing is authorized.", "Still nothing."), encoding="utf-8")
    dirty = project_context.compile_context_spine(root)["generated_from"]["canonical_git_identity"]
    assert dirty["head_sha"] == identity["head_sha"]
    assert dirty["worktree_status"] == "DIRTY"
    # The head commit does not contain the compiled bytes, and the packet says so.
    assert dirty["compiled_bytes_bound_to_head_sha"] is False


def test_architecture_conflict_blocks_generated_view_mutation(tmp_path: Path) -> None:
    root = _spine_root(tmp_path, catalog=_ecosystem_toml(north_star="ADR-ABSENT"))
    roadmap = root / "docs/CURRENT_ROADMAP.md"
    before = roadmap.read_bytes()
    assert project_context.render(root, check=False) == 1
    assert roadmap.read_bytes() == before, "a conflicting foundation must not rewrite a generated view"
    assert project_context.render(root, check=True) == 1
    assert _spine_cli(root, "render").returncode == 1
    assert roadmap.read_bytes() == before


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
    before = _tracked_tree_digest(ROOT)
    before_status = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain=v1", "-uall"], check=True, capture_output=True).stdout
    before_head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], check=True, capture_output=True).stdout

    project_context.compile_context_spine(ROOT)
    project_context.context_spine_bytes(ROOT)
    subprocess.run(SPINE_COMMAND, cwd=ROOT, check=True, capture_output=True)

    assert _tracked_tree_digest(ROOT) == before
    assert subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain=v1", "-uall"], check=True, capture_output=True).stdout == before_status
    assert subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], check=True, capture_output=True).stdout == before_head


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
        assert command[:2] == ["git", "-C"]
        assert Path(command[2]).resolve() == ROOT.resolve()
        assert command[3] in {"rev-parse", "status", "ls-files", "symbolic-ref"}


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
    assert set(catalog) == {"schema_version", "ecosystem_id", "architecture", "repository", "context_source"}
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
