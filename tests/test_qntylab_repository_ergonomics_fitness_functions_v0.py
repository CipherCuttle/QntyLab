"""QNTYLAB_REPOSITORY_ERGONOMICS_FITNESS_FUNCTIONS_V0 -- executable fitness functions (increment C6).

Fail-closed pytest fitness functions that permanently enforce the C1-C5 gains
of umbrella ``QNTYLAB_REPOSITORY_ERGONOMICS_AND_MODULARITY_CLEANUP_V0`` whose
governance decision is ``experiments/research/
qntylab_repository_ergonomics_and_modularity_cleanup_v0/decision.json``
(sha256 ``d2c27eda957ae9f1a650ccc886b391b3a9f5a06f4dbd25a53d1b711355e4e652``).

Scope contract (C6):
- TESTS + EVIDENCE ONLY.  No refactor, no CI change, no runtime change, no new
  framework: plain pytest plus small deterministic helpers over explicit roots.
- Every assertion follows the same shape: authoritative source + independent
  current observation + explicit comparison + fail-closed on missing evidence.
- Helpers are pure functions over an explicit ``root``/``path`` parameter
  (default = repo root) so negative controls can run against throwaway copies
  in ``tmp_path``; the real worktree is never mutated.
- No test depends on branch name, PR number, HEAD == parent, GitHub API,
  network, ``/tmp``, or run IDs.  Non-mutation checks compare the captured
  dirty set before/after and tolerate pre-existing dirtiness without
  false-failing.

Metric mapping (M1-M24 -> enforcing tests, UNMAPPED_C6_ACCEPTANCE_METRICS = 0)
is recorded in ``experiments/research/
qntylab_repository_ergonomics_and_modularity_cleanup_v0/
c6_repository_ergonomics_fitness_functions_v0/fitness_manifest.json``.

The C1 positive control is phase ``QNTYLAB_PROJECT_CONTEXT_AND_AUTHORITY_REGISTRY_V0``.
The old umbrella-id positive control now legitimately fails closed under the
C1 artifact-pointer cap and is deliberately NOT used here.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

UMBRELLA_ID = "QNTYLAB_REPOSITORY_ERGONOMICS_AND_MODULARITY_CLEANUP_V0"
C6_PROJECT_ID = "QNTYLAB_REPOSITORY_ERGONOMICS_FITNESS_FUNCTIONS_V0"
C6_EVIDENCE_DIR = (
    REPO_ROOT
    / "experiments/research/qntylab_repository_ergonomics_and_modularity_cleanup_v0"
    / "c6_repository_ergonomics_fitness_functions_v0"
)
DECISION_PATH = (
    REPO_ROOT
    / "experiments/research/qntylab_repository_ergonomics_and_modularity_cleanup_v0/decision.json"
)
DECISION_SHA256 = "d2c27eda957ae9f1a650ccc886b391b3a9f5a06f4dbd25a53d1b711355e4e652"
FORENSICS_DIR = "docs/forensics/QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0"
DELETION_MATRIX_REL = f"{FORENSICS_DIR}/deletion_matrix.json"
C2_METRICS_REL = (
    "experiments/research/qntylab_repository_ergonomics_and_modularity_cleanup_v0"
    "/c2_project_context_modularization_v0/metrics.json"
)
C5_METRICS_REL = (
    "experiments/research/qntylab_repository_ergonomics_and_modularity_cleanup_v0"
    "/c5_proven_delete_safe_slimming_v0/metrics.json"
)

# --------------------------------------------------------------------------
# C1 constants (authoritative source: decision.json acceptance_metrics; the
# values below are cross-checked against decision.json in the C1 tests).
# --------------------------------------------------------------------------
POSITIVE_CONTROL_PHASE_ID = "QNTYLAB_PROJECT_CONTEXT_AND_AUTHORITY_REGISTRY_V0"
PACKET_HARD_CAP_BYTES = 8192
PACKET_REDUCTION_BASIS_BYTES = 586444
PACKET_REDUCTION_MIN_PERCENT = 95
SAFETY_TIMEOUT_SECONDS = 120

# --------------------------------------------------------------------------
# C2 constants (authoritative source: C2 metrics.json dsh_token_counts +
# frozen token set; monolith bytes from C2 metrics pre).
# --------------------------------------------------------------------------
DSH_TOKENS = ("DSH", "DSH_STAGE", "STAGE_A", "dsh", "pinned_dsh", "stage-a", "Stage-A")
# Frozen counting method: grep -oE '<tokens>' FILE | wc -l.  grep -E uses
# POSIX leftmost-longest alternation; Python re is leftmost-first, so sorting
# the alternatives longest-first reproduces the frozen method's counts.
_DSH_TOKEN_RE = re.compile("|".join(re.escape(t) for t in sorted(DSH_TOKENS, key=len, reverse=True)))
GENERIC_MODULE_RELS = (
    "qntylab/project_context.py",
    "qntylab/project_context_core.py",
    "qntylab/project_context_registry.py",
    "qntylab/project_context_spine.py",
    "qntylab/project_context_brief.py",
)
SEAM_MODULE_REL = "qntylab/project_context_execution_authority.py"
C2_SIBLING_RELS = GENERIC_MODULE_RELS + (SEAM_MODULE_REL,)
C2_MONOLITH_BYTES_PRE = 110441  # C2 metrics size_metrics.pre.monolith bytes
# STRUCTURAL_POSTCONDITION bound derived from C2 closure: the composition root
# must never regrow past half the original monolith size.
COMPOSITION_ROOT_MAX_BYTES = C2_MONOLITH_BYTES_PRE // 2
# Still-valid C2 digests (verified at implementation time against the current
# bytes); the composition-root, execution-authority, and C2 test-file digests
# in the same C2 metrics field are PRE-compatibility-repair STALE and are
# deliberately NOT asserted.  Enforcement goes through frozen_hash_manifest.json.
C2_VALID_DIGEST_RELS = (
    "qntylab/project_context_core.py",
    "qntylab/project_context_registry.py",
    "qntylab/project_context_spine.py",
    "qntylab/project_context_brief.py",
)
COMPATIBILITY_SURFACE_SYMBOLS = (
    "validate_adr_registry",
    "validate_projects_registry",
    "validate_ecosystem_catalog",
    "load_context_sources",
    "context_text",
    "brief_text",
    "PROJECT_STATES",
    "execution_authority_projection",
    "DSH_STAGE_A_V1R3R2_EXECUTION_ID",
)

# --------------------------------------------------------------------------
# C3 constants (STRUCTURAL_POSTCONDITION: frozen current shape measured at the
# canonical parent; reductions and wall-times are OBSERVED_METRIC_NOT_GOVERNANCE_TARGET
# and are deliberately never asserted).
# --------------------------------------------------------------------------
CORE_WORKFLOW_REL = ".github/workflows/project-context.yml"
HEAVY_WORKFLOW_REL = ".github/workflows/project-context-heavy-replay.yml"
CORE_WORKFLOW_SHAPE = {"lines": 90, "jobs": 1, "operational_steps": 11}
HEAVY_WORKFLOW_SHAPE = {"lines": 333, "jobs": 1, "operational_steps": 13}
CORE_REQUIRED_TEST_FILES = (
    "tests/test_project_context_v0.py",
    "tests/test_context_spine_foundation_v0.py",
    "tests/test_context_spine_brief_v0.py",
    "tests/test_context_spine_orientation_completeness_v0.py",
)
# Heavy-replay-only command markers; if any of these appear in the core
# workflow the split has collapsed; if any disappear from heavy the split is broken.
HEAVY_ONLY_MARKERS = (
    "repository-deterministic.test.mjs",
    "prelive-enforcement.test.mjs",
    "host-qualified-runtime.test.mjs",
    "materialize-dsh-runtime",
    "materialize-stage-a-dsh-home",
)

# --------------------------------------------------------------------------
# C5 constants (authoritative source: deletion_matrix.json audit @
# be291300abb70f3ffc6ba0dd8b1bea570daf5377).
# --------------------------------------------------------------------------
C5_MODULE_COUNT = 135
# The six DELETE_SAFE candidate paths are read from deletion_matrix.json at
# test time (single authoritative source; the stems are deliberately not
# spelled out here so the C5 zero-reference sweep over tests/*.py stays clean).
DELETED_SIX_EXPECTED_COUNT = 6
# Governance-era 133 is HISTORICAL and must never be asserted as current.

# --------------------------------------------------------------------------
# Authority canonical field names (do not invent others).  Sources:
# docs/state/projects.toml umbrella row and the C1-C5 increment rows;
# qntylab/project_context_registry.py registry fields; execution-authority
# firewall defaults at qntylab/project_context_execution_authority.py.
# --------------------------------------------------------------------------
_UMBRELLA_AUTHORITY_FIELDS = (
    "scientific_execution_authorized",
    "real_data_access_authorized",
    "outcome_access_authorized",
    "provider_access_authorized",
    "claim_access_authorized",
    "claim_consumption_authorized",
    "router_authority",
    "qnty_authority",
    "qntyspot_authority",
    "trading_authority",
    "capital_authority",
    "downstream_authority",
)
_INCREMENT_AUTHORITY_FIELDS = (
    "evaluator_applicability",
    "evaluator_run_required",
    "evaluator_created",
    "runtime_authorized",
    "scientific_execution_authorized",
    "qnty_mutation_authorized",
    "qnty_agent_eval_mutation_authorized",
    "qntyspot_mutation_authorized",
    "trading_authority",
    "capital_authority",
    "signing_authority",
    "promotion_authority",
)
# Canonical union (the full non-escalation block carried by the C6 row).
ALL_AUTHORITY_FIELDS = tuple(dict.fromkeys(_UMBRELLA_AUTHORITY_FIELDS + _INCREMENT_AUTHORITY_FIELDS))
_AUTHORITY_BOOL_FIELDS = {
    "scientific_execution_authorized",
    "real_data_access_authorized",
    "outcome_access_authorized",
    "provider_access_authorized",
    "claim_access_authorized",
    "claim_consumption_authorized",
    "runtime_authorized",
    "qnty_mutation_authorized",
    "qnty_agent_eval_mutation_authorized",
    "qntyspot_mutation_authorized",
    "evaluator_run_required",
    "evaluator_created",
}
_AUTHORITY_NONE_FIELDS = {
    "router_authority",
    "qnty_authority",
    "qntyspot_authority",
    "trading_authority",
    "capital_authority",
    "downstream_authority",
    "signing_authority",
    "promotion_authority",
}
# evaluator_applicability takes the sentinel "NO_MATCH", not "NONE".
_AUTHORITY_NO_MATCH_FIELDS = {"evaluator_applicability"}
assert not _AUTHORITY_BOOL_FIELDS & _AUTHORITY_NONE_FIELDS
assert not _AUTHORITY_BOOL_FIELDS & _AUTHORITY_NO_MATCH_FIELDS
assert not _AUTHORITY_NONE_FIELDS & _AUTHORITY_NO_MATCH_FIELDS
# Per-row required sets mirror the exact C1-C5 registration convention: the
# umbrella row carries the access/authority block, increment rows carry the
# evaluator + mutation block, and the C6 row carries the full union.
REQUIRED_AUTHORITY_FIELDS_BY_ROW = {
    UMBRELLA_ID: _UMBRELLA_AUTHORITY_FIELDS,
    "QNTYLAB_AGENT_CONTEXT_PACKET_V0": _INCREMENT_AUTHORITY_FIELDS,
    "QNTYLAB_PROJECT_CONTEXT_MODULARIZATION_V0": _INCREMENT_AUTHORITY_FIELDS,
    "QNTYLAB_DEV_LOOP_CI_SPLIT_V0": _INCREMENT_AUTHORITY_FIELDS,
    "QNTYLAB_PYTHON_TOOLING_NORMALIZATION_V0": _INCREMENT_AUTHORITY_FIELDS,
    "QNTYLAB_PROVEN_DELETE_SAFE_SLIMMING_V0": _INCREMENT_AUTHORITY_FIELDS,
    C6_PROJECT_ID: ALL_AUTHORITY_FIELDS,
}
# Execution-authority firewall defaults (source: the expected_firewall literal
# block in the seam module, verified present at implementation time).
FIREWALL_EXPECTED = {
    "stage_b_authorized": "False",
    "qnty_runtime_authority": '"NONE"',
    "trading_authority": '"NONE"',
    "capital_authority": '"NONE"',
    "scientific_execution_authorized": "False",
    "promotion_authority": '"NONE"',
}

SAFETY_COMMANDS = (
    ("doctor --strict", [sys.executable, "-m", "qntylab.project_context", "doctor", "--strict"], "project context ok"),
    ("render --check", [sys.executable, "-m", "qntylab.project_context", "render", "--check"], "roadmap current"),
    ("research_ledger doctor", [sys.executable, "-m", "qntylab.research_ledger", "doctor"], "ledger ok"),
)


class FitnessFailure(AssertionError):
    """Raised by fail-closed helpers; missing evidence is never a PASS."""


# --------------------------------------------------------------------------
# Helpers (pure over explicit roots/paths so negative controls stay cheap).
# --------------------------------------------------------------------------
def sha256_path(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise FitnessFailure(f"FROZEN_UNREADABLE: {path}: {exc}") from exc


def read_text_fail_closed(path: Path, what: str) -> str:
    if not path.is_file():
        raise FitnessFailure(f"MISSING_EVIDENCE ({what}): {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FitnessFailure(f"UNREADABLE_EVIDENCE ({what}): {path}: {exc}") from exc


def load_json_fail_closed(path: Path, what: str) -> dict:
    text = read_text_fail_closed(path, what)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FitnessFailure(f"MALFORMED_EVIDENCE ({what}): {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise FitnessFailure(f"MALFORMED_EVIDENCE ({what}): {path}: not a JSON object")
    return data


def count_dsh_tokens(text: str) -> int:
    """Frozen C2 counting method: grep -oE '<tokens>' FILE | wc -l equivalent."""
    return len(_DSH_TOKEN_RE.findall(text))


def dsh_violations(module_texts: dict[str, str]) -> list[str]:
    """Nonzero DSH token count in any supplied module text is a violation."""
    return [
        f"{rel}: DSH token count {count_dsh_tokens(text)} != 0"
        for rel, text in module_texts.items()
        if count_dsh_tokens(text) != 0
    ]


def paths_present_violations(root: Path, rels) -> list[str]:
    return [rel for rel in rels if not (root / rel).is_file()]


def paths_absent_violations(root: Path, rels) -> list[str]:
    return [rel for rel in rels if (root / rel).exists()]


def authority_violations(record: dict, required_fields) -> list[str]:
    """Full non-escalation check: fail closed on missing required fields, and
    reject any canonical authority field that is not false / "NONE"."""
    violations: list[str] = []
    project_id = record.get("project_id", "<missing project_id>")
    for field in required_fields:
        if field not in record:
            violations.append(f"{project_id}: missing required authority field {field}")
    for field in ALL_AUTHORITY_FIELDS:
        if field not in record:
            continue
        value = record[field]
        if field in _AUTHORITY_BOOL_FIELDS:
            if value is not False:
                violations.append(f"{project_id}: {field} must be false, got {value!r}")
        elif field in _AUTHORITY_NONE_FIELDS:
            if value != "NONE":
                violations.append(f"{project_id}: {field} must be \"NONE\", got {value!r}")
        elif field in _AUTHORITY_NO_MATCH_FIELDS:
            if value != "NO_MATCH":
                violations.append(f"{project_id}: {field} must be \"NO_MATCH\", got {value!r}")
        else:  # pragma: no cover - ALL_AUTHORITY_FIELDS is exactly partitioned
            violations.append(f"{project_id}: {field} is not a canonical authority field")
    return violations


def verify_frozen_entry(root: Path, entry: dict) -> None:
    """Fail closed on MISSING / UNREADABLE / MISMATCH for one manifest entry."""
    if not isinstance(entry, dict) or "path" not in entry or "sha256" not in entry:
        raise FitnessFailure(f"MALFORMED frozen-hash manifest entry: {entry!r}")
    path = root / entry["path"]
    if not path.is_file():
        raise FitnessFailure(f"FROZEN_MISSING: {entry['path']}")
    observed = sha256_path(path)
    if observed != entry["sha256"]:
        raise FitnessFailure(
            f"FROZEN_MISMATCH: {entry['path']}: manifest {entry['sha256']} != observed {observed}"
        )


def parse_workflow(path: Path) -> tuple[int, dict]:
    """Parse a GitHub workflow YAML file.

    Uses pyyaml (verified importable at implementation time; pyyaml is a
    test-time dependency only).  If pyyaml is unavailable this helper fails
    closed rather than guessing.  Returns (line_count, parsed_mapping).
    """
    text = read_text_fail_closed(path, "workflow")
    try:
        import yaml  # noqa: PLC0415 - deliberate local import; test-time only
    except ImportError as exc:  # pragma: no cover - environment guard
        raise FitnessFailure(
            "pyyaml unavailable; workflow shape cannot be parsed safely (fail closed)"
        ) from exc
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise FitnessFailure(f"MALFORMED workflow: {path}: not a mapping")
    return len(text.splitlines()), data


def workflow_triggers(data: dict) -> dict:
    # pyyaml parses a bare `on:` key as boolean True (YAML 1.1); accept both.
    return data.get("on") or data.get(True) or {}


def workflow_jobs(data: dict) -> dict:
    jobs = data.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        raise FitnessFailure("workflow has no jobs mapping")
    return jobs


def workflow_operational_steps(data: dict) -> int:
    """Operational steps = steps carrying a run/uses payload."""
    count = 0
    for job in workflow_jobs(data).values():
        steps = job.get("steps") if isinstance(job, dict) else None
        if not isinstance(steps, list):
            raise FitnessFailure("workflow job has no steps list")
        for step in steps:
            if isinstance(step, dict) and ("run" in step or "uses" in step):
                count += 1
    return count


def workflow_run_payload(data: dict) -> str:
    """Concatenated run payload of all steps (for command-coverage checks)."""
    chunks: list[str] = []
    for job in workflow_jobs(data).values():
        for step in job.get("steps", []):
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                chunks.append(step["run"])
    return "\n".join(chunks)


def run_checked(args: list[str], cwd: Path = REPO_ROOT, timeout: int = SAFETY_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    """Run a command; fail closed on timeout, missing binary, or nonzero exit."""
    try:
        proc = subprocess.run(args, cwd=str(cwd), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise FitnessFailure(f"COMMAND_TIMEOUT after {timeout}s: {args}") from exc
    except OSError as exc:
        raise FitnessFailure(f"COMMAND_UNAVAILABLE: {args}: {exc}") from exc
    if proc.returncode != 0:
        raise FitnessFailure(
            f"COMMAND_FAILED ({proc.returncode}): {args}\n"
            f"stdout: {proc.stdout.decode(errors='replace')[:500]}\n"
            f"stderr: {proc.stderr.decode(errors='replace')[:500]}"
        )
    return proc


def git_dirty_set(root: Path = REPO_ROOT) -> frozenset[str]:
    proc = subprocess.run(["git", "status", "--porcelain"], cwd=str(root), capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise FitnessFailure(f"git status --porcelain failed in {root}: {proc.stderr.decode(errors='replace')}")
    return frozenset(proc.stdout.decode(errors="replace").splitlines())


def load_frozen_hash_manifest() -> dict:
    path = C6_EVIDENCE_DIR / "frozen_hash_manifest.json"
    manifest = load_json_fail_closed(path, "frozen_hash_manifest")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise FitnessFailure(f"MALFORMED frozen_hash_manifest: no entries in {path}")
    return manifest


def load_project_rows():
    """Canonical loading path for projects.toml rows (reuse, not a new parser)."""
    import qntylab.project_context as pc

    _, _, projects_registry = pc.load_context_sources(REPO_ROOT)
    return pc.validate_projects_registry(REPO_ROOT, projects_registry)


# --------------------------------------------------------------------------
# C1 packet fitness (M1-M5)
# --------------------------------------------------------------------------
def _run_packet_generation() -> bytes:
    proc = run_checked(
        [
            sys.executable,
            "-m",
            "qntylab.agent_context_packet_v0",
            "--phase-id",
            POSITIVE_CONTROL_PHASE_ID,
            "--root",
            str(REPO_ROOT),
        ]
    )
    return proc.stdout


class TestC1PacketFitness:
    def _decision_packet_bounds(self) -> tuple[int, int, int]:
        decision = load_json_fail_closed(DECISION_PATH, "umbrella decision.json")
        metrics = decision.get("acceptance_metrics")
        if not isinstance(metrics, dict):
            raise FitnessFailure("decision.json has no acceptance_metrics object")
        packet = metrics.get("packet")
        if not isinstance(packet, dict):
            raise FitnessFailure("decision.json acceptance_metrics has no packet object")
        cap = packet.get("hard_cap_bytes")
        if cap != PACKET_HARD_CAP_BYTES:
            raise FitnessFailure(f"decision.json hard_cap_bytes {cap!r} != {PACKET_HARD_CAP_BYTES}")
        reduction = metrics.get("DEFAULT_AGENT_CONTEXT_REDUCTION_PERCENT")
        if not isinstance(reduction, dict):
            raise FitnessFailure("decision.json has no DEFAULT_AGENT_CONTEXT_REDUCTION_PERCENT")
        minimum = reduction.get("minimum")
        if minimum != PACKET_REDUCTION_MIN_PERCENT:
            raise FitnessFailure(f"decision.json reduction minimum {minimum!r} != {PACKET_REDUCTION_MIN_PERCENT}")
        basis = str(reduction.get("basis", ""))
        match = re.search(r"(\d+)", basis)
        if not match or int(match.group(1)) != PACKET_REDUCTION_BASIS_BYTES:
            raise FitnessFailure(
                f"decision.json reduction basis does not declare the {PACKET_REDUCTION_BASIS_BYTES}-byte basis"
            )
        return cap, int(minimum), PACKET_REDUCTION_BASIS_BYTES

    def test_c1_packet_bytes_within_hard_cap_and_reduction(self):
        # M1 HARD_THRESHOLD: PACKET_BYTES <= 8192.
        # M2 HARD_THRESHOLD: (1 - packet_bytes / 586444) * 100 >= 95.
        cap, minimum, basis = self._decision_packet_bounds()
        packet_bytes = _run_packet_generation()
        if len(packet_bytes) > cap:
            raise FitnessFailure(f"M1_PACKET_OVER_CAP: {len(packet_bytes)} > {cap} B")
        reduction = (1 - len(packet_bytes) / basis) * 100
        if reduction < minimum:
            raise FitnessFailure(
                f"M2_REDUCTION_BELOW_THRESHOLD: {reduction:.2f}% < {minimum}% (packet {len(packet_bytes)} B)"
            )

    def test_c1_packet_determinism(self):
        # M3 STRUCTURAL_POSTCONDITION: two generations are byte-identical.
        first = _run_packet_generation()
        second = _run_packet_generation()
        if first != second:
            raise FitnessFailure(
                f"M3_PACKET_NONDETERMINISTIC: {len(first)} B vs {len(second)} B generations differ"
            )

    def test_c1_packet_generation_non_mutating(self):
        # M5 SAFETY_INVARIANT: generation leaves the worktree unchanged.
        before = git_dirty_set()
        _run_packet_generation()
        after = git_dirty_set()
        if after != before:
            raise FitnessFailure(
                "M5_PACKET_MUTATED_WORKTREE: dirty set changed; "
                f"new entries: {sorted(after - before)}"
            )

    def test_c1_packet_fail_closed_on_oversized_field(self):
        # M4 SAFETY_INVARIANT (negative control family 1): a synthetic
        # oversized field must fail closed through the module's own validation.
        from qntylab.agent_context_packet_v0 import (
            FIELD_ORDER,
            FIELD_VALUE_CAPS,
            AgentContextPacketError,
            render_packet,
        )

        values = {field: "" for field in FIELD_ORDER}
        target = FIELD_ORDER[0]
        values[target] = "x" * (FIELD_VALUE_CAPS[target] + 1)
        with pytest.raises(AgentContextPacketError):
            render_packet(values)

    def test_c1_packet_cap_and_reduction_enforcement_helpers(self):
        # Negative control family 1: enforcement helpers reject oversized /
        # under-reduced synthetic packets.
        cap, minimum, basis = self._decision_packet_bounds()
        oversized = b"x" * (cap + 1)
        with pytest.raises(FitnessFailure):
            if len(oversized) > cap:
                raise FitnessFailure(f"M1_PACKET_OVER_CAP: {len(oversized)} > {cap} B")
        synthetic = basis - 1000  # clearly above the 95%-reduction floor
        reduction = (1 - synthetic / basis) * 100
        with pytest.raises(FitnessFailure):
            if reduction < minimum:
                raise FitnessFailure(f"M2_REDUCTION_BELOW_THRESHOLD: {reduction:.2f}% < {minimum}%")


# --------------------------------------------------------------------------
# C2 modularity fitness (M6-M10)
# --------------------------------------------------------------------------
class TestC2ModularityFitness:
    def test_c2_dsh_tokens_absent_from_generic_modules(self):
        # M6 HARD_THRESHOLD: DSH token count == 0 in the five generic modules.
        texts = {
            rel: read_text_fail_closed(REPO_ROOT / rel, "C2 generic module") for rel in GENERIC_MODULE_RELS
        }
        violations = dsh_violations(texts)
        if violations:
            raise FitnessFailure("M6_DSH_IN_GENERIC_MODULES: " + "; ".join(violations))

    def test_c2_execution_authority_seam_sole_dsh_confinement(self):
        # M7 STRUCTURAL_POSTCONDITION: the seam still holds the DSH identities
        # (>0 tokens) and all six C2 sibling module paths exist.
        for rel in C2_SIBLING_RELS:
            if not (REPO_ROOT / rel).is_file():
                raise FitnessFailure(f"M7_MISSING_C2_SIBLING: {rel}")
        seam_text = read_text_fail_closed(REPO_ROOT / SEAM_MODULE_REL, "C2 seam module")
        if count_dsh_tokens(seam_text) == 0:
            raise FitnessFailure(
                "M7_SEAM_EMPTY: execution-authority seam no longer holds any DSH identity"
            )

    def test_c2_composition_root_structural_bound(self):
        # M8 STRUCTURAL_POSTCONDITION derived from C2 closure: the composition
        # root must stay below half the original monolith size so monolith
        # regrowth trips this bound (no percentage/wall-time semantics here).
        root_path = REPO_ROOT / "qntylab/project_context.py"
        text = read_text_fail_closed(root_path, "composition root")
        size = len(text.encode("utf-8"))
        if size >= COMPOSITION_ROOT_MAX_BYTES:
            raise FitnessFailure(
                f"M8_MONOLITH_REGROWTH: composition root {size} B >= {COMPOSITION_ROOT_MAX_BYTES} B "
                f"(half of C2 pre monolith {C2_MONOLITH_BYTES_PRE} B)"
            )

    def test_c2_compatibility_surface_symbols_resolve(self):
        # M9 STRUCTURAL_POSTCONDITION: the composition root still re-exports
        # the stable public surface including the PR250_P2 repair symbol.
        import qntylab.project_context as pc

        missing = [name for name in COMPATIBILITY_SURFACE_SYMBOLS if not hasattr(pc, name)]
        if missing:
            raise FitnessFailure(f"M9_COMPATIBILITY_SURFACE_BROKEN: missing {missing}")

    def test_c2_still_valid_module_digests_match_frozen_manifest(self):
        # M10 STRUCTURAL_POSTCONDITION: the four still-valid C2 digests are
        # bound through frozen_hash_manifest.json (POINTERS_OVER_COPIES); the
        # stale pre-repair digests are deliberately not asserted.
        manifest = load_frozen_hash_manifest()
        by_path = {entry["path"]: entry for entry in manifest["entries"]}
        for rel in C2_VALID_DIGEST_RELS:
            if rel not in by_path:
                raise FitnessFailure(f"M10_FROZEN_MANIFEST_GAP: {rel} is not bound in frozen_hash_manifest.json")
            verify_frozen_entry(REPO_ROOT, by_path[rel])


# --------------------------------------------------------------------------
# C3 CI shape fitness (M11-M15)
# --------------------------------------------------------------------------
class TestC3CiShapeFitness:
    def test_c3_core_workflow_shape(self):
        # M11 STRUCTURAL_POSTCONDITION: freeze the current split shape.
        lines, data = parse_workflow(REPO_ROOT / CORE_WORKFLOW_REL)
        observed = {
            "lines": lines,
            "jobs": len(workflow_jobs(data)),
            "operational_steps": workflow_operational_steps(data),
        }
        if observed != CORE_WORKFLOW_SHAPE:
            raise FitnessFailure(f"M11_CORE_SHAPE_DRIFT: {observed} != {CORE_WORKFLOW_SHAPE}")

    def test_c3_heavy_workflow_shape(self):
        # M12 STRUCTURAL_POSTCONDITION: freeze the current split shape.
        lines, data = parse_workflow(REPO_ROOT / HEAVY_WORKFLOW_REL)
        observed = {
            "lines": lines,
            "jobs": len(workflow_jobs(data)),
            "operational_steps": workflow_operational_steps(data),
        }
        if observed != HEAVY_WORKFLOW_SHAPE:
            raise FitnessFailure(f"M12_HEAVY_SHAPE_DRIFT: {observed} != {HEAVY_WORKFLOW_SHAPE}")

    def test_c3_triggers_and_permissions_unchanged(self):
        # M15 STRUCTURAL_POSTCONDITION: pull_request + push(master) +
        # workflow_dispatch and permissions contents: read on both workflows.
        for rel in (CORE_WORKFLOW_REL, HEAVY_WORKFLOW_REL):
            _, data = parse_workflow(REPO_ROOT / rel)
            triggers = workflow_triggers(data)
            for trigger in ("pull_request", "push", "workflow_dispatch"):
                if trigger not in triggers:
                    raise FitnessFailure(f"M15_TRIGGER_MISSING in {rel}: {trigger}")
            branches = (triggers.get("push") or {}).get("branches") or []
            if "master" not in branches:
                raise FitnessFailure(f"M15_PUSH_BRANCH_MISSING in {rel}: master")
            permissions = data.get("permissions")
            if not isinstance(permissions, dict) or permissions.get("contents") != "read":
                raise FitnessFailure(f"M15_PERMISSIONS_NOT_CONTENTS_READ in {rel}")

    def test_c3_core_required_command_coverage(self):
        # M14 STRUCTURAL_POSTCONDITION: the core workflow still runs the six
        # canonical dev-loop checks (no wall-time, no percentage semantics).
        _, data = parse_workflow(REPO_ROOT / CORE_WORKFLOW_REL)
        runs = workflow_run_payload(data)
        required = [
            "doctor --strict",
            "render --check",
            "project_context spine",
            "project_context brief",
            "research_ledger doctor",
            *CORE_REQUIRED_TEST_FILES,
        ]
        missing = [cmd for cmd in required if cmd not in runs]
        if missing:
            raise FitnessFailure(f"M14_CORE_COMMAND_COVERAGE_GAP: missing {missing}")

    def test_c3_heavy_not_collapsed_into_core(self):
        # M13 STRUCTURAL_POSTCONDITION: heavy-replay-only commands live in the
        # heavy workflow and nowhere in the core workflow.
        _, heavy = parse_workflow(REPO_ROOT / HEAVY_WORKFLOW_REL)
        _, core = parse_workflow(REPO_ROOT / CORE_WORKFLOW_REL)
        heavy_runs = workflow_run_payload(heavy)
        core_runs = workflow_run_payload(core)
        missing_from_heavy = [m for m in HEAVY_ONLY_MARKERS if m not in heavy_runs]
        leaked_into_core = [m for m in HEAVY_ONLY_MARKERS if m in core_runs]
        if missing_from_heavy:
            raise FitnessFailure(f"M13_HEAVY_LOST_COMMANDS: {missing_from_heavy}")
        if leaked_into_core:
            raise FitnessFailure(f"M13_HEAVY_FOLDED_INTO_CORE: {leaked_into_core}")


# --------------------------------------------------------------------------
# C4 tooling fitness (M16-M17)
# --------------------------------------------------------------------------
class TestC4ToolingFitness:
    def test_c4_pyproject_is_tool_only(self):
        # M16 STRUCTURAL_POSTCONDITION: pyproject.toml holds tool config only
        # (no [project], no [build-system], no dependency declarations).
        path = REPO_ROOT / "pyproject.toml"
        text = read_text_fail_closed(path, "pyproject.toml")
        data = tomllib.loads(text)
        for forbidden in ("project", "build-system"):
            if forbidden in data:
                raise FitnessFailure(f"M16_PYPROJECT_NOT_TOOL_ONLY: [{forbidden}] table present")
        for forbidden_token in ("install_requires", "dependencies"):
            if re.search(rf"^\s*{forbidden_token}\s*=", text, flags=re.MULTILINE):
                raise FitnessFailure(f"M16_PYPROJECT_DEPENDENCY_DECLARATION: {forbidden_token} present")
        pytest_options = (data.get("tool") or {}).get("pytest") or {}
        ini_options = pytest_options.get("ini_options")
        if not isinstance(ini_options, dict):
            raise FitnessFailure("M16_PYPROJECT_MISSING: [tool.pytest.ini_options]")
        if ini_options.get("addopts") != "":
            raise FitnessFailure(
                f"M16_PYPROJECT_ADDOPTS_DRIFT: addopts={ini_options.get('addopts')!r} != ''"
            )

    def test_c4_contract_test_gate_present(self):
        # M17 STRUCTURAL_POSTCONDITION: the C4 gate file exists (the gate
        # itself remains the enforcement; this is the cheap postcondition).
        rel = "tests/test_qntylab_python_tooling_normalization_v0.py"
        if not (REPO_ROOT / rel).is_file():
            raise FitnessFailure(f"M17_C4_GATE_MISSING: {rel}")


# --------------------------------------------------------------------------
# C5 slimming fitness (M18-M21)
# --------------------------------------------------------------------------
def _load_deletion_matrix() -> dict:
    return load_json_fail_closed(REPO_ROOT / DELETION_MATRIX_REL, "deletion_matrix.json")


def _deletion_matrix_rows() -> list[dict]:
    matrix = _load_deletion_matrix()
    rows = matrix.get("rows")
    if not isinstance(rows, list) or not rows:
        raise FitnessFailure("deletion_matrix.json has no rows")
    return rows


def _deletion_matrix_blocked_paths() -> tuple[list[str], list[str]]:
    frozen, active = [], []
    for row in _deletion_matrix_rows():
        classification = row.get("classification")
        path = row.get("candidate_path")
        if not isinstance(path, str) or not path:
            raise FitnessFailure(f"deletion_matrix row without candidate_path: {row!r}")
        if classification == "DELETE_BLOCKED_BY_FROZEN_BINDING":
            frozen.append(path)
        elif classification == "DELETE_BLOCKED_BY_ACTIVE_USE":
            active.append(path)
    if len(frozen) != 28 or len(active) != 8:
        raise FitnessFailure(
            f"deletion_matrix classification drift: {len(frozen)} frozen-binding / {len(active)} active-use"
        )
    return frozen, active


def _deleted_safe_paths() -> list[str]:
    paths = [
        row["candidate_path"]
        for row in _deletion_matrix_rows()
        if row.get("classification") == "DELETE_SAFE"
    ]
    if len(paths) != DELETED_SIX_EXPECTED_COUNT:
        raise FitnessFailure(
            f"deletion_matrix DELETE_SAFE drift: {len(paths)} != {DELETED_SIX_EXPECTED_COUNT}"
        )
    return paths


class TestC5SlimmingFitness:
    def test_c5_deleted_paths_absent(self):
        # M18 STRUCTURAL_POSTCONDITION: the six DELETE_SAFE candidates are
        # absent from both the filesystem and the git index.
        deleted_safe = _deleted_safe_paths()
        present = paths_absent_violations(REPO_ROOT, deleted_safe)
        if present:
            raise FitnessFailure(f"M18_DELETED_PATH_REAPPEARED: {present}")
        proc = subprocess.run(
            ["git", "ls-files", "--", *deleted_safe],
            cwd=str(REPO_ROOT),
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            raise FitnessFailure("git ls-files failed: " + proc.stderr.decode(errors="replace"))
        tracked = proc.stdout.decode(errors="replace").split()
        if tracked:
            raise FitnessFailure(f"M18_DELETED_PATH_STILL_TRACKED: {tracked}")

    def test_c5_blocked_candidates_present(self):
        # M19 STRUCTURAL_POSTCONDITION: all 36 blocked candidates remain.
        frozen, active = _deletion_matrix_blocked_paths()
        missing = paths_present_violations(REPO_ROOT, frozen + active)
        if missing:
            raise FitnessFailure(f"M19_BLOCKED_CANDIDATE_MISSING: {missing}")

    def test_c5_module_count_is_current_governance_count(self):
        # M20 STRUCTURAL_POSTCONDITION: qntylab module count == 135.  The
        # governance-era 133 is HISTORICAL and must never be asserted.
        observed = len(list((REPO_ROOT / "qntylab").glob("*.py")))
        if observed != C5_MODULE_COUNT:
            raise FitnessFailure(f"M20_MODULE_COUNT_DRIFT: {observed} != {C5_MODULE_COUNT}")

    def test_c5_metrics_artifact_arithmetic_integrity(self):
        # M21 HISTORICAL_OBSERVATION: recompute the C5 metrics artifact's own
        # arithmetic from its fields.  No global byte cap is asserted; the
        # 5473578 -> 5407499 bytes are HISTORICAL_OBSERVATION only.
        metrics = load_json_fail_closed(REPO_ROOT / C5_METRICS_REL, "C5 metrics.json")
        pre, post, deltas = metrics["pre"], metrics["post"], metrics["deltas"]
        files = pre.get("deleted_candidate_files")
        if not isinstance(files, list) or len(files) != 6:
            raise FitnessFailure("C5 metrics deleted_candidate_files is not a 6-row list")
        py_deleted = [f["bytes"] for f in files if f["path"].endswith(".py")]
        docs_deleted = [f["bytes"] for f in files if f["path"].endswith(".md")]
        if len(py_deleted) != 4 or len(docs_deleted) != 2:
            raise FitnessFailure("C5 metrics deleted_candidate_files kind split drifted")
        # 86329 - 20250 == 66079
        py_delta = pre["tracked_python_bytes"] - post["tracked_python_bytes"]
        if py_delta != 66079:
            raise FitnessFailure(f"C5 arithmetic: py delta {py_delta} != 66079")
        # The added-C5-py-bytes figure comes from the artifact's own deltas note.
        match = re.search(r"\+\s*(\d+)\s+py bytes", str(deltas.get("tracked_python_bytes", "")))
        if not match:
            raise FitnessFailure("C5 metrics deltas note does not declare the added py bytes")
        added_py_bytes = int(match.group(1))
        if sum(py_deleted) - added_py_bytes != py_delta:
            raise FitnessFailure(
                f"C5 arithmetic: {sum(py_deleted)} - {added_py_bytes} != {py_delta}"
            )
        # 91074 == 86329 + 3360 + 1385
        total_deleted = pre.get("deleted_candidate_total_bytes")
        if total_deleted != 91074 or sum(py_deleted) + sum(docs_deleted) != total_deleted:
            raise FitnessFailure(
                f"C5 arithmetic: deleted total {total_deleted} != {sum(py_deleted)} + {sum(docs_deleted)}"
            )
        # 139 - 4 == 135
        if pre["qntylab_python_modules"] - len(py_deleted) != post["qntylab_python_modules"]:
            raise FitnessFailure("C5 arithmetic: module-count delta inconsistent")
        blocked_pre = pre.get("blocked_candidates") or {}
        blocked_post = post.get("blocked_candidates") or {}
        if blocked_pre.get("total") != 36 or blocked_post.get("total") != 36:
            raise FitnessFailure("C5 arithmetic: blocked candidate totals drifted from 36")
        if blocked_pre.get("DELETE_BLOCKED_BY_FROZEN_BINDING") != 28:
            raise FitnessFailure("C5 arithmetic: frozen-binding count drifted from 28")
        if blocked_pre.get("DELETE_BLOCKED_BY_ACTIVE_USE") != 8:
            raise FitnessFailure("C5 arithmetic: active-use count drifted from 8")


# --------------------------------------------------------------------------
# Authority non-escalation (M22)
# --------------------------------------------------------------------------
class TestAuthorityNonEscalation:
    def test_authority_fields_closed_for_umbrella_and_all_increments(self):
        # M22 SAFETY_INVARIANT: every canonical authority field on the
        # umbrella and C1-C6 rows is false / "NONE"; missing rows or missing
        # required fields fail closed.
        rows = load_project_rows()
        for project_id, required in REQUIRED_AUTHORITY_FIELDS_BY_ROW.items():
            record = rows.get(project_id)
            if record is None:
                raise FitnessFailure(f"MISSING_ROW: no projects.toml row for {project_id}")
            violations = authority_violations(record, required)
            if violations:
                raise FitnessFailure("M22_AUTHORITY_ESCALATION: " + "; ".join(violations))

    def test_implementation_authorized_false_for_non_active_rows(self):
        # Registry field convention (qntylab/project_context_registry.py:
        # implementation_authorized must be boolean and true only for ACTIVE).
        rows = load_project_rows()
        for project_id, record in rows.items():
            if record.get("state") != "ACTIVE":
                if record.get("implementation_authorized") is not False:
                    raise FitnessFailure(
                        f"M22_IMPLEMENTATION_AUTHORIZED_ESCALATION: {project_id} "
                        f"state={record.get('state')!r} implementation_authorized="
                        f"{record.get('implementation_authorized')!r}"
                    )

    def test_execution_authority_firewall_defaults_hold(self):
        # The seam module's expected_firewall defaults must still close the
        # downstream firewall (lightest safe path: source-constant check).
        source = read_text_fail_closed(REPO_ROOT / SEAM_MODULE_REL, "execution-authority seam")
        match = re.search(r"expected_firewall = \{(.*?)\}", source, flags=re.DOTALL)
        if not match:
            raise FitnessFailure("M22_FIREWALL_BLOCK_NOT_FOUND in execution-authority seam")
        block = match.group(1)
        for field, literal in FIREWALL_EXPECTED.items():
            if f'"{field}": {literal}' not in block:
                raise FitnessFailure(
                    f"M22_FIREWALL_DEFAULT_DRIFT: {field} no longer defaults to {literal}"
                )


# --------------------------------------------------------------------------
# Frozen hash bindings (M23)
# --------------------------------------------------------------------------
class TestFrozenHashBindings:
    def test_frozen_hash_manifest_entries_all_match(self):
        # M23 SAFETY_INVARIANT: every manifest entry must exist, be readable,
        # and hash-match its recorded sha256.  MISSING/UNREADABLE/MISMATCH is
        # a failure, never a skip or pass-on-missing.  The manifest records
        # digests observed at implementation time (recorded evidence
        # independent of test-time bytes); the manifest is the pointer record,
        # never a file copy (POINTERS_OVER_COPIES).
        manifest = load_frozen_hash_manifest()
        entries = manifest["entries"]
        frozen_paths = [
            entry["path"]
            for entry in entries
            if entry.get("declaring_authority", {}).get("value") == "DELETE_BLOCKED_BY_FROZEN_BINDING"
        ]
        if len(frozen_paths) != 28:
            raise FitnessFailure(
                f"frozen_hash_manifest binds {len(frozen_paths)} frozen-binding paths, expected 28"
            )
        for entry in entries:
            verify_frozen_entry(REPO_ROOT, entry)

    def test_frozen_hash_manifest_binds_decision_and_matrix(self):
        manifest = load_frozen_hash_manifest()
        bound = {entry["path"] for entry in manifest["entries"]}
        required = {
            "experiments/research/qntylab_repository_ergonomics_and_modularity_cleanup_v0/decision.json",
            DELETION_MATRIX_REL,
            *C2_VALID_DIGEST_RELS,
        }
        missing = sorted(required - bound)
        if missing:
            raise FitnessFailure(f"FROZEN_MANIFEST_MISSING_BINDINGS: {missing}")


# --------------------------------------------------------------------------
# Repository health commands (M24)
# --------------------------------------------------------------------------
class TestRepositoryHealthCommands:
    @pytest.mark.parametrize(
        "label,args,marker",
        [(label, args, marker) for label, args, marker in SAFETY_COMMANDS],
        ids=[label for label, _, _ in SAFETY_COMMANDS],
    )
    def test_safety_command_passes_and_is_non_mutating(self, label, args, marker):
        # M24 SAFETY_INVARIANT: each canonical safety command exits 0 with its
        # expected stdout marker and leaves the worktree unchanged.  The
        # dirty-set comparison tolerates pre-existing dirtiness.
        before = git_dirty_set()
        proc = run_checked(args)
        after = git_dirty_set()
        if after != before:
            raise FitnessFailure(
                f"M24_COMMAND_MUTATED_WORKTREE ({label}); new entries: {sorted(after - before)}"
            )
        stdout = proc.stdout.decode(errors="replace")
        if marker not in stdout:
            raise FitnessFailure(
                f"M24_UNEXPECTED_STDOUT ({label}): expected marker {marker!r}, got {stdout[:200]!r}"
            )


# --------------------------------------------------------------------------
# Negative controls (self-test the fitness functions without mutating the
# real worktree; every control operates on tmp_path copies or synthetic data)
# --------------------------------------------------------------------------
class TestNegativeControls:
    """Demonstrations that the enforcement helpers fail closed on corruption.

    Families: (1) packet cap/reduction, (2) DSH injection, (3) workflow
    deleted/command removed, (4) deleted path reappears, (5) blocked path
    disappears, (6) authority flipped, (7) frozen digest mismatch.
    """

    def test_nc1_packet_cap_and_reduction_reject_synthetic_oversize(self):
        cap = PACKET_HARD_CAP_BYTES
        basis = PACKET_REDUCTION_BASIS_BYTES
        # Packet over cap:
        with pytest.raises(FitnessFailure):
            packet_bytes = b"x" * (cap + 1)
            if len(packet_bytes) > cap:
                raise FitnessFailure(f"M1_PACKET_OVER_CAP: {len(packet_bytes)} > {cap} B")
        # Reduction below threshold (synthetic 25000 B packet -> ~95.7%... use
        # a value that clearly violates the 95% floor):
        with pytest.raises(FitnessFailure):
            synthetic = basis - 1000
            reduction = (1 - synthetic / basis) * 100
            if reduction < PACKET_REDUCTION_MIN_PERCENT:
                raise FitnessFailure(f"M2_REDUCTION_BELOW_THRESHOLD: {reduction:.2f}%")

    def test_nc2_dsh_token_injected_into_generic_module_is_detected(self, tmp_path):
        original = read_text_fail_closed(REPO_ROOT / "qntylab/project_context_core.py", "core module")
        tampered = tmp_path / "project_context_core.py"
        tampered.write_text(original + "\n# DSH_STAGE negative-control marker\n", encoding="utf-8")
        text = tampered.read_text(encoding="utf-8")
        assert count_dsh_tokens(text) > 0
        violations = dsh_violations({"qntylab/project_context_core.py (tmp copy)": text})
        if not violations:
            raise FitnessFailure("negative control failed: DSH injection was NOT detected")

    def test_nc3_heavy_workflow_deleted_or_command_removed_is_detected(self, tmp_path):
        # (a) deleted workflow: fail closed.
        with pytest.raises(FitnessFailure):
            parse_workflow(tmp_path / "project-context-heavy-replay.yml")
        # (b) required heavy command removed from a tmp copy: detected.
        heavy_text = read_text_fail_closed(REPO_ROOT / HEAVY_WORKFLOW_REL, "heavy workflow")
        needle = "prelive-enforcement.test.mjs"
        lines = [ln for ln in heavy_text.splitlines() if needle not in ln]
        tampered = tmp_path / "heavy.yml"
        tampered.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _, data = parse_workflow(tampered)
        runs = workflow_run_payload(data)
        missing = [m for m in HEAVY_ONLY_MARKERS if m not in runs]
        if needle not in missing:
            raise FitnessFailure("negative control failed: removed heavy command was NOT detected")

    def test_nc4_deleted_path_reappearance_is_detected(self, tmp_path):
        rel = _deleted_safe_paths()[3]
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("negative control\n", encoding="utf-8")
        present = paths_absent_violations(tmp_path, [rel])
        if rel not in present:
            raise FitnessFailure("negative control failed: reappearance was NOT detected")

    def test_nc5_blocked_candidate_disappearance_is_detected(self, tmp_path):
        frozen, active = _deletion_matrix_blocked_paths()
        missing = paths_present_violations(tmp_path, frozen + active)
        if len(missing) != len(frozen) + len(active):
            raise FitnessFailure("negative control failed: empty tmp tree did not report all missing")

    def test_nc6_authority_flip_is_detected(self):
        record = {
            "project_id": "NEGATIVE_CONTROL_ROW",
            "runtime_authorized": False,
            "scientific_execution_authorized": False,
            "qnty_mutation_authorized": False,
            "qnty_agent_eval_mutation_authorized": False,
            "qntyspot_mutation_authorized": False,
            "trading_authority": "GRANTED",  # flipped from NONE
            "capital_authority": "NONE",
            "signing_authority": "NONE",
            "promotion_authority": "NONE",
            "evaluator_applicability": "NO_MATCH",
            "evaluator_run_required": False,
            "evaluator_created": False,
        }
        violations = authority_violations(record, _INCREMENT_AUTHORITY_FIELDS)
        if not any("trading_authority" in v for v in violations):
            raise FitnessFailure("negative control failed: authority flip was NOT detected")
        # Missing required field must also fail closed.
        incomplete = {k: v for k, v in record.items() if k != "runtime_authorized"}
        incomplete["trading_authority"] = "NONE"
        violations = authority_violations(incomplete, _INCREMENT_AUTHORITY_FIELDS)
        if not any("missing required authority field runtime_authorized" in v for v in violations):
            raise FitnessFailure("negative control failed: missing authority field was NOT detected")

    def test_nc7_frozen_digest_mismatch_is_detected(self, tmp_path):
        matrix = load_json_fail_closed(REPO_ROOT / DELETION_MATRIX_REL, "deletion_matrix.json")
        entry = {
            "path": "deletion_matrix.json",
            "sha256": hashlib.sha256(
                (REPO_ROOT / DELETION_MATRIX_REL).read_bytes()
            ).hexdigest(),
        }
        # The pristine copy verifies...
        (tmp_path / "deletion_matrix.json").write_bytes((REPO_ROOT / DELETION_MATRIX_REL).read_bytes())
        verify_frozen_entry(tmp_path, entry)
        # ...and altered bytes must fail closed.
        tampered = json.dumps(matrix | {"tampered": True}).encode()
        (tmp_path / "deletion_matrix.json").write_bytes(tampered)
        with pytest.raises(FitnessFailure, match="FROZEN_MISMATCH"):
            verify_frozen_entry(tmp_path, entry)
