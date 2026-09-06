"""C3 structure tests: QNTYLAB_DEV_LOOP_CI_SPLIT_V0 (DEV_LOOP_CI_SPLIT_V0).

Bounded structural inspection of the C3 CI split — NO GitHub Actions execution.

Enforces (per the frozen C3 contract):
1. TWO-WORKFLOW SHAPE — the C3 core + heavy-replay workflow files exist.
2. CORE REQUIRED COMMANDS — doctor --strict, render --check, spine, brief,
   research-ledger doctor, and the exact frozen core pytest selection.
3. HEAVY REQUIRED RESPONSIBILITIES — all known DSH/historical commands/actions
   moved from the monolith into the heavy replay workflow.
4. NO SILENT TEST DROP — every original operational CI step in the baseline
   coverage manifest maps to exactly one destination and its distinctive
   command fragment is present there; ORIGINAL_OPERATIONAL_CI_STEP_COVERAGE
   must be 100% with zero silently dropped steps.
5. PERMISSIONS NON-ESCALATION — both workflows remain contents: read.
6. TRIGGER NON-ESCALATION — no new trigger class beyond the monolith's
   pull_request / push(master) / workflow_dispatch(identity inputs).
7. IDENTITY SEMANTICS — tri-state identity modes and explicit checkout
   behavior remain present in both workflows.
8. HEAVY-ONLY TOKENS ABSENT FROM CORE — proves a real split, not cosmetic
   duplication of DSH runtime materialization / qualified DSH_HOME /
   production-owner heavy setup into the core dev-loop workflow.
9. CORE DOES NOT CALL HEAVY INLINE — no reusable-workflow/composite call or
   synchronous shell hop from core into heavy replay.

C3 is workflow topology only; this file asserts structure, not runtime
authority, and grants no research/evaluation/execution/claim/trading rights.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
CORE_WORKFLOW = WORKFLOW_DIR / "project-context.yml"
HEAVY_WORKFLOW = WORKFLOW_DIR / "project-context-heavy-replay.yml"
C3_ARTIFACT_DIR = (
    REPO_ROOT
    / "experiments"
    / "research"
    / "qntylab_repository_ergonomics_and_modularity_cleanup_v0"
    / "c3_dev_loop_ci_split_v0"
)
COVERAGE_MANIFEST = C3_ARTIFACT_DIR / "coverage_manifest.json"

CORE_PYTEST_SELECTION = (
    "python -m pytest -q tests/test_project_context_v0.py "
    "tests/test_context_spine_foundation_v0.py "
    "tests/test_context_spine_brief_v0.py "
    "tests/test_context_spine_orientation_completeness_v0.py"
)

CORE_REQUIRED_COMMANDS = [
    "python -m qntylab.project_context doctor --strict",
    "python -m qntylab.project_context render --check",
    "python -m qntylab.project_context spine > /dev/null",
    "python -m qntylab.project_context brief > /dev/null",
    "python -m qntylab.research_ledger doctor",
    CORE_PYTEST_SELECTION,
]

HEAVY_REQUIRED_RESPONSIBILITIES = [
    # A. repository-deterministic DSH execution-contract reconciliation
    "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_execution_contract_reconciliation_v0/test/repository-deterministic.test.mjs",
    # Node 22.22.0 setup
    "node-version: \"22.22.0\"",
    # Pinned DSH runtime materialization
    "materializePinnedSource",
    "applyCanonicalPatches",
    "installPinnedOffline",
    "buildPinnedRuntime",
    # pnpm store preparation for the governed offline install
    "pnpm@11.7.0",
    "fetch --frozen-lockfile",
    # Canonical patch application + frozen digest verification
    "codex-executable-binding.patch",
    "claude-hard-read-only.patch",
    "BLOCK_RUNTIME_IDENTITY",
    # Qualified Stage-A DSH_HOME materialization
    "materializeStageADshHome",
    "QNTYLAB_QUALIFIED_DSH_HOME",
    # Production @qntylab packages qualification
    "dsh-stage-a-gated-provider",
    "dsh-stage-a-parent-enforcement",
    # Production-owner claim-binding integration
    "prelive-enforcement.test.mjs",
    # Fixture cleanup before host checks
    "CI_FIXTURE_REMOVED_BEFORE_B",
    # Provenance receipt behavior
    "CI_FIXTURE_PURPOSE=REPOSITORY_DETERMINISTIC_A_CLAIM_INPUT_ONLY",
    "HOST_QUALIFIED_CLAIMED_BY_GITHUB=FALSE",
    # Host-qualified runtime preflight / historical repair regression surface
    "host-qualified-runtime.test.mjs",
]

HEAVY_ONLY_TOKENS_FORBIDDEN_IN_CORE = [
    "materializePinnedSource",
    "materializeStageADshHome",
    "QNTYLAB_QUALIFIED_DSH_HOME",
    "pnpm@11.7.0",
    "prelive-enforcement.test.mjs",
    "host-qualified-runtime.test.mjs",
    "repository-deterministic.test.mjs",
    "dsh_runtime_materialization_and_launch_v0",
    "dsh_stage_a_v1r3r2",
    "/var/tmp/qntylab-dsh-runtime-v0-final",
    "setup-node",
]

IDENTITY_MODES = ["CANDIDATE_HEAD", "SYNTHETIC_PR_MERGE_RESULT", "CANONICAL_MASTER"]

# Baseline operational-step fragments (mechanical no-silent-drop anchors).
BASELINE_STEP_FRAGMENTS = [
    "github.event.inputs.identity_mode",
    "actions/checkout@v4",
    "IDENTITY_MODE=",
    "actions/setup-python@v5",
    "python -m pip install pytest requests",
    "python -m qntylab.project_context doctor --strict",
    "python -m qntylab.project_context render --check",
    "python -m qntylab.project_context spine > /dev/null",
    "python -m qntylab.project_context brief > /dev/null",
    "python -m qntylab.research_ledger doctor",
    CORE_PYTEST_SELECTION,
    "repository-deterministic.test.mjs",
    "actions/setup-node@v4",
    "materializePinnedSource",
    "materializeStageADshHome",
    "prelive-enforcement.test.mjs",
    "CI_FIXTURE_REMOVED_BEFORE_B",
    "HOST_QUALIFIED_CLAIMED_BY_GITHUB=FALSE",
    "host-qualified-runtime.test.mjs",
]

# Mechanical no-silent-drop anchors keyed by the coverage manifest original_name.
# Each fragment is a distinctive substring of the original monolith step that
# must appear verbatim in the mapped destination workflow.
MECHANICAL_STEP_ANCHORS = {
    "Resolve identity mode": 'elif [ "${{ github.event_name }}" = "pull_request" ]; then',
    "Run actions/checkout@v4": "fetch-depth: 0",
    "Record identity mode": 'echo "IDENTITY_MODE=${{ steps.identity.outputs.mode }}" >> "$GITHUB_ENV"',
    "Run actions/setup-python@v5": 'python-version: "3.12"',
    "Run python -m pip install pytest requests": "python -m pip install pytest requests",
    "Run python -m qntylab.project_context doctor --strict": "python -m qntylab.project_context doctor --strict",
    "Run python -m qntylab.project_context render --check": "python -m qntylab.project_context render --check",
    "Run python -m qntylab.project_context spine > /dev/null": "python -m qntylab.project_context spine > /dev/null",
    "Run python -m qntylab.project_context brief > /dev/null": "python -m qntylab.project_context brief > /dev/null",
    "Run python -m qntylab.research_ledger doctor": "python -m qntylab.research_ledger doctor",
    "Run python -m pytest -q tests/test_project_context_v0.py tests/test_context_spine_foundation_v0.py tests/test_context_spine_brief_v0.py tests/test_context_spine_orientation_completeness_v0.py": CORE_PYTEST_SELECTION,
    "A. Repository-deterministic reconciliation checks": "repository-deterministic.test.mjs",
    "Run actions/setup-node@v4": 'node-version: "22.22.0"',
    "CI fixture: provision pinned DSH runtime at the frozen manifest path": "materializePinnedSource",
    "CI fixture: materialize qualified Stage-A DSH_HOME": "materializeStageADshHome",
    "A-claim. Production-owner claim-binding integration (repository-deterministic)": "prelive-enforcement.test.mjs",
    "CI fixture removal before step B": "CI_FIXTURE_REMOVED_BEFORE_B",
    "CI provenance receipt (deterministic, non-claim, non-secret)": "CI_FIXTURE_PURPOSE=REPOSITORY_DETERMINISTIC_A_CLAIM_INPUT_ONLY",
    "B. Host-qualified runtime preflight (reports GitHub vs host scope)": "host-qualified-runtime.test.mjs",
}


class StrictLoader(yaml.SafeLoader):
    """YAML loader that fails closed on duplicate mapping keys."""


def _no_duplicate_keys(loader, node, deep=False):
    keys = []
    for key_node, _value_node in node.value:
        keys.append(loader.construct_object(key_node, deep=deep))
    if len(keys) != len(set(map(repr, keys))):
        raise yaml.constructor.ConstructorError(
            None, None, f"duplicate YAML mapping keys detected: {keys}", node.start_mark
        )
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    lambda loader, node: _no_duplicate_keys(loader, node, deep=True),
)


def _load_workflow(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.load(text, Loader=StrictLoader)


def _job(wf: dict) -> dict:
    jobs = wf["jobs"]
    assert len(jobs) == 1, f"expected exactly one job, got {list(jobs)}"
    return next(iter(jobs.values()))


def _steps(wf: dict) -> list[dict]:
    return _job(wf)["steps"]


def _run_text(wf: dict) -> str:
    chunks: list[str] = []
    for step in _steps(wf):
        if "run" in step:
            chunks.append(step["run"])
        chunks.append(step.get("name", ""))
    return "\n".join(chunks)


def _full_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# (1) TWO-WORKFLOW SHAPE
# ---------------------------------------------------------------------------


def test_c3_two_workflow_shape_files_exist_and_parse() -> None:
    core = _load_workflow(CORE_WORKFLOW)
    heavy = _load_workflow(HEAVY_WORKFLOW)
    assert core["name"] == "Project Context"
    assert heavy["name"] == "Project Context Heavy Replay"
    assert set(core["jobs"]) == {"project-context"}
    assert set(heavy["jobs"]) == {"project-context-heavy-replay"}
    assert len(_steps(core)) == 11
    assert len(_steps(heavy)) == 13


# ---------------------------------------------------------------------------
# (2) CORE REQUIRED COMMANDS
# ---------------------------------------------------------------------------


def test_core_contains_required_commands_in_order() -> None:
    core = _load_workflow(CORE_WORKFLOW)
    run_blocks = [s.get("run", "") for s in _steps(core) if "run" in s]
    joined = "\n".join(run_blocks)
    cursor = 0
    for command in CORE_REQUIRED_COMMANDS:
        idx = joined.find(command, cursor)
        assert idx != -1, f"missing or out-of-order core command: {command!r}"
        cursor = idx + len(command)


def test_core_has_no_heavy_pytest_escalation() -> None:
    core = _load_workflow(CORE_WORKFLOW)
    run_blocks = [s.get("run", "") for s in _steps(core) if "run" in s]
    pytest_blocks = [b for b in run_blocks if "pytest" in b and "pytest -q" in b]
    assert pytest_blocks == [CORE_PYTEST_SELECTION]


# ---------------------------------------------------------------------------
# (3) HEAVY REQUIRED RESPONSIBILITIES
# ---------------------------------------------------------------------------


def test_heavy_contains_all_moved_responsibilities() -> None:
    heavy_text = _full_text(HEAVY_WORKFLOW)
    missing = [tok for tok in HEAVY_REQUIRED_RESPONSIBILITIES if tok not in heavy_text]
    assert missing == [], f"heavy replay workflow missing responsibilities: {missing}"


def test_heavy_preserves_a_claim_env_binding() -> None:
    heavy = _load_workflow(HEAVY_WORKFLOW)
    a_claim = [s for s in _steps(heavy) if s.get("name", "").startswith("A-claim")]
    assert len(a_claim) == 1
    env = a_claim[0].get("env", {})
    assert env.get("QNTYLAB_QUALIFIED_DSH_HOME") == "${{ steps.ci-dsh-home.outputs.qualified_dsh_home }}"


# ---------------------------------------------------------------------------
# (4) NO SILENT TEST DROP — manifest vs post-split destination commands
# ---------------------------------------------------------------------------


def test_coverage_manifest_mechanically_proves_100_percent_step_coverage() -> None:
    import json

    manifest = json.loads(COVERAGE_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["ORIGINAL_OPERATIONAL_CI_STEP_COVERAGE"] == "100%"
    completeness = manifest["coverage_completeness_check"]
    assert completeness["original_operational_steps"] == 19
    assert completeness["silently_dropped"] == 0
    steps = manifest["steps"]
    assert len(steps) == 19
    names = [s["original_name"] for s in steps]
    assert len(names) == len(set(names)), "duplicate manifest step names"
    assert set(names) == set(MECHANICAL_STEP_ANCHORS), "manifest/baseline anchor mismatch"
    core_text = _full_text(CORE_WORKFLOW)
    heavy_text = _full_text(HEAVY_WORKFLOW)
    for step in steps:
        destination = step["destination"]
        assert destination in {"CORE", "HEAVY_REPLAY"}, step
        anchor = MECHANICAL_STEP_ANCHORS[step["original_name"]]
        target = core_text if destination == "CORE" else heavy_text
        # Shared identity/bootstrap steps are duplicated verbatim in BOTH
        # workflows (semantic preservation), so check both for those steps.
        if step["classification"] in {"SHARED_IDENTITY_BOOTSTRAP", "CORE_SETUP"}:
            assert anchor in core_text or anchor in heavy_text, step["original_name"]
        else:
            assert anchor in target, (
                f"original step {step['original_name']!r} -> {destination} not represented"
            )


def test_baseline_step_fragment_anchor_count_matches_monolith() -> None:
    import json

    manifest = json.loads(COVERAGE_MANIFEST.read_text(encoding="utf-8"))
    assert len(BASELINE_STEP_FRAGMENTS) == 19
    destinations = {s["original_name"]: s["destination"] for s in manifest["steps"]}
    assert len(destinations) == 19
    core_text = _full_text(CORE_WORKFLOW)
    heavy_text = _full_text(HEAVY_WORKFLOW)
    for fragment in BASELINE_STEP_FRAGMENTS:
        assert fragment in core_text or fragment in heavy_text, (
            f"baseline step fragment dropped by the split: {fragment!r}"
        )


# ---------------------------------------------------------------------------
# (5) PERMISSIONS NON-ESCALATION
# ---------------------------------------------------------------------------


def test_permissions_non_escalation_in_both_workflows() -> None:
    for path in (CORE_WORKFLOW, HEAVY_WORKFLOW):
        wf = _load_workflow(path)
        assert wf["permissions"] == {"contents": "read"}, path
        text = _full_text(path)
        assert "write-all" not in text
        assert "secrets:" not in text.replace("non-secret", "")
        assert "id-token" not in text


# ---------------------------------------------------------------------------
# (6) TRIGGER NON-ESCALATION
# ---------------------------------------------------------------------------


def test_trigger_non_escalation_in_both_workflows() -> None:
    allowed = {"pull_request", "push", "workflow_dispatch"}
    for path in (CORE_WORKFLOW, HEAVY_WORKFLOW):
        wf = _load_workflow(path)
        on = wf[True]  # PyYAML parses bare `on:` as boolean True
        assert set(on) == allowed, (path, set(on))
        assert on["push"] == {"branches": ["master"]}
        assert on["pull_request"] is None
        dispatch = on["workflow_dispatch"]["inputs"]
        assert set(dispatch) == {"identity_mode", "pull_request_number"}
        assert dispatch["identity_mode"]["options"] == IDENTITY_MODES
        text = _full_text(path)
        for forbidden in ("schedule", "repository_dispatch", "workflow_call", "release:", "cron"):
            assert forbidden not in text, (path, forbidden)


# ---------------------------------------------------------------------------
# (7) IDENTITY SEMANTICS
# ---------------------------------------------------------------------------


def test_identity_semantics_present_in_both_workflows() -> None:
    for path in (CORE_WORKFLOW, HEAVY_WORKFLOW):
        wf = _load_workflow(path)
        steps = _steps(wf)
        run_text = _run_text(wf)
        for mode in IDENTITY_MODES:
            assert mode in run_text, (path, mode)
        assert "refs/heads/master" in run_text
        assert "refs/pull/" in run_text
        names = [s.get("name") for s in steps]
        assert "Resolve identity mode" in names, path
        assert "Record identity mode" in names, path
        checkout = [s for s in steps if s.get("uses") == "actions/checkout@v4"]
        assert len(checkout) == 1, path
        with_block = checkout[0].get("with", {})
        assert with_block.get("fetch-depth") == 0
        assert with_block.get("ref") == "${{ steps.identity.outputs.checkout_ref }}"
        assert 'echo "IDENTITY_MODE=${{ steps.identity.outputs.mode }}" >> "$GITHUB_ENV"' in run_text


# ---------------------------------------------------------------------------
# (8) HEAVY-ONLY TOKENS ABSENT FROM CORE
# ---------------------------------------------------------------------------


def test_heavy_only_tokens_absent_from_core() -> None:
    core_text = _full_text(CORE_WORKFLOW)
    present = [tok for tok in HEAVY_ONLY_TOKENS_FORBIDDEN_IN_CORE if tok in core_text]
    assert present == [], f"heavy-only responsibilities leaked into core: {present}"


# ---------------------------------------------------------------------------
# (9) CORE DOES NOT CALL HEAVY INLINE
# ---------------------------------------------------------------------------


def test_core_does_not_call_heavy_inline() -> None:
    core = _load_workflow(CORE_WORKFLOW)
    core_text = _full_text(CORE_WORKFLOW)
    assert "workflow_call" not in core_text
    run_text = _run_text(core)
    uses_text = "\n".join(s.get("uses", "") for s in _steps(core))
    assert "project-context-heavy-replay" not in run_text
    assert "project-context-heavy-replay" not in uses_text
    for heavy_marker in (
        "repository-deterministic.test.mjs",
        "host-qualified-runtime.test.mjs",
        "materializeStageADshHome",
    ):
        assert heavy_marker not in run_text, heavy_marker
    for step in _steps(core):
        uses = step.get("uses", "")
        assert not uses.startswith("."), f"local composite/reusable call in core: {uses}"
        assert not uses.startswith("docker://"), f"docker call in core: {uses}"
        if uses:
            assert uses.startswith("actions/"), f"unexpected action reference in core: {uses}"


def test_heavy_does_not_call_core_inline() -> None:
    heavy = _load_workflow(HEAVY_WORKFLOW)
    heavy_text = _full_text(HEAVY_WORKFLOW)
    assert "workflow_call" not in heavy_text
    assert "uses: ./" not in heavy_text
    run_text = _run_text(heavy)
    assert "python -m qntylab.project_context doctor" not in run_text
    for step in _steps(heavy):
        uses = step.get("uses", "")
        if uses:
            assert uses.startswith("actions/"), f"unexpected action reference: {uses}"
