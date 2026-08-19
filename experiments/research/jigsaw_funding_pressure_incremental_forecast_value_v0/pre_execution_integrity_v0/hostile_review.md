# Funding incremental pre-execution integrity reconciliation — hostile review

Review count: exactly one.
Review target: the frozen reconciliation candidate on
`agent/funding-incremental-pre-execution-integrity-reconciliation-v0`, branched
from canonical master `cc93a6b4dd234087bb007002e144f0ea9278ea2b` (merge of
PR #147).

Reviewed change set (the complete diff against canonical master):

| Path | Status |
| --- | --- |
| `qntylab/jigsaw_funding_pressure_provenance_v0.py` | modified — the integrity repair |
| `tests/test_jigsaw_funding_pressure_provenance_v0.py` | modified — receipt assertion + 18 hostile identity tests |
| `qntylab/jigsaw_funding_pressure_incremental_pre_execution_integrity_v0.py` | new — the reconciliation verifier |
| `tests/test_funding_incremental_pre_execution_integrity_v0.py` | new — 48 outcome-blind tests |
| `experiments/.../pre_execution_integrity_v0/` | new — phase artifacts |

Reviewer independence: performed by the receiving reconciliation orchestrator
as a separate adversarial pass against its own candidate, not by a third party.
That limitation is recorded rather than overstated: this is a single-actor
hostile review, not an independent external audit.

## Verdict

| Severity | Count |
| --- | --- |
| Critical | 0 |
| Medium | 1 |
| High | 0 |
| Low | 3 |

Critical/High is zero, so the bounded repair cycle was NOT triggered, no repair
pass was performed, and no targeted re-review was used. None of the Medium/Low
findings invalidates the phase objective, violates a frozen invariant, or
creates a fail-closed or safety defect.

## Attack surface examined, and what was found

**Historical hash laundering — CLOSED.** The forbidden repair is to overwrite
the frozen `file_sha256` with the current worktree hash. It is refused: with
`qntylab/binance_um_kline_1h.py`'s frozen entry replaced by its live hash
`10ec8bad…`, `verify_historical_materializer_identity` raises
`historical materializer identity mismatch … at 98e9dbcb…`. A hash matching
*neither* anchor is refused identically — the check is conjunctive over all
anchors, not `any`.

**Replacing producer provenance with current code identity — CLOSED.** The
identity proof never reads the working tree. `historical_materializer_digest`
resolves `<commit>:<path>` to a blob id, type-checks the object, and hashes
`git cat-file blob` output. The live file is read in exactly one place, to
*report* `diverged_from_current_worktree`, and that value is never compared
against the frozen record.

**Moving the anchors to a commit that contains the current bytes — CLOSED.**
This is the subtler laundering route: point `required_git_ancestors` at
`d1a327a` (where the materializer changed) and the current hash would
authenticate. It is refused twice over. First, `required_git_ancestors` lives
inside `provenance_baseline_v0.json` and is covered by that file's
`provenance_baseline_digest`, so editing it breaks the self-digest that
`verify_baseline` and `verify_historical_provenance` both check *before* the
identity step. Second, the identity check independently requires
`tuple(anchors) == (PREREG_SHA, PIT_V1_SHA)`, so a baseline naming different
anchors than the ones `verify_git_ancestry` proved is refused. An attacker must
therefore break a SHA-256 self-digest *and* edit the module constants, and the
digest is the binding authority. Probed directly: refused with
`baseline Git anchors do not match the verified ancestry set`.

**Silent evidence mutation — CLOSED.** `git diff origin/master -- experiments/
docs/` is empty; no frozen artifact under `data/`, no
`provenance_baseline_v0.json`, no `preregistration.json`, and nothing in
`implementation_v0/` is modified. The baseline's self-digest still recomputes to
`sha256:902be224…` and the frozen materializer pair still reads
`e5a333f3…` / `e2b9c7d9…`, asserted by test.

**Git object / ref ambiguity — CLOSED.** Anchors must be full lowercase 40-hex
and must `cat-file -t` as `commit`. Abbreviated (`98e9dbc`), ref-shaped
(`HEAD`, `refs/heads/master`), revision-expression (`…5569^`), uppercase and
empty anchors are each refused with `not a full 40-hex object id`. Passing the
materializer's own **blob** id as an anchor is refused with
`not a commit object`; passing a **tree** id likewise. Naming a directory
instead of a file is refused with `is not a blob`, which also closes the
gitlink/submodule and symlink routes (a symlink blob hashes its target string,
so it cannot collide with the frozen content hash).

**Panel order mismatch — CLOSED.** Equality is Python list equality on `str`,
so order is load-bearing. Swapping the first two members of `v2.PANEL` raises
`panel order mismatch`, and reversing `required_git_ancestors` is refused
separately.

**Panel substitution — CLOSED.** Replacing `REEFUSDT` with `DOGEUSDT` — the
declared `MISSING_OR_SUBSTITUTED_PANEL_MEMBER` kill condition — raises
`panel substitution` naming the missing and extra members. Dropping a member
and appending an extra are refused the same way. Drift injected into
`provenance.PANEL` (the root that `v2.PANEL` derives from) is also caught,
because the preregistration is the comparison reference, not the modules.

**Weak prereg digest binding — CLOSED.** The panel check refuses to run at all
unless the preregistration's declared digest **and** its recomputed canonical
digest both equal `d7ec718a…`, and unless its status is
`PREREGISTERED_NOT_EXECUTED`. A tampered preregistration carrying a correct
panel is still refused, so the panel can never be validated against an
unbound contract.

**Executor identity drift — CLOSED.** Eight identities are bound by exact
digest: executor source, executor test, V2, Foundation V0, source binding,
implementation manifest, origin schedule and execution semantics — plus the
implementation-authority and synthetic-validation artifacts, the
preregistration file bytes, and the frozen implementation SHA
`f6f12994…`. Drift in any one raises `source identity drift` or
`artifact identity drift`. The executor's own `implementation_identity()` is
cross-checked against the frozen record, so a module that lies about itself is
caught too.

**M-01 runtime-context nondeterminism — CLOSED, and characterised precisely.**
The finding is real: at
`jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py:820`,
`guard = int(x * x / _LN_10) + 1` evaluates in the ambient context. Measured
across 29 hostile ambient contexts (`prec` 1/2/7/28/300 × four rounding modes,
eight individual traps, an exponent squeeze, and a combined nuisance-trap
context), the executor produced **zero** divergent digests. Two configurations
— an ambient `Inexact` or `Rounded` trap — raise `decimal.Inexact` /
`decimal.Rounded` at exactly that line. Raising is fail-closed: it cannot emit
a different number. Under the frozen `scientific_runtime()` contract all 24
preflighted contexts, including both trapping ones, reproduce the frozen
synthetic digest `sha256:1fca55eb…`, with zero failures. No fail-closed
reproducibility defect was demonstrated, so the STOP-and-classify branch of the
phase policy was correctly not taken, and the frozen algorithm was correctly
left untouched.

**Accidental outcome access — CLOSED.** The reconciliation module names no
real-evidence entrypoint: `load_verified_frozen_evidence`,
`execute_authorized_frozen_experiment_v2`, `claim_authorization_once`,
`compute_frozen_experiment` and `build_receipt_provenance` each appear exactly
once, in the forbidden-names tuple that the test asserts against. It imports no
`requests`, `urllib`, `socket` or `subprocess`, contains no `write_text` /
`write_bytes`, and no `eval(` / `exec(`. Its only filesystem access is reading
files it hashes.

**Scientific execution hidden inside a "validation" — CLOSED.** The single
executor invocation passes `execution_mode=SYNTHETIC_VALIDATION`, and the
executor refuses every other value including the lowercase spelling. Rows come
from the frozen implementation phase's own synthetic generator, imported rather
than reimplemented. No evaluation origin is consumed: the preflight evaluates
synthetic rows, and `evaluation_origins_consumed` is a literal `0`. See L-03 for
the residual.

**Result creation — CLOSED.** The module writes nothing. The one artifact this
phase generates, `reconciliation_receipt.json`, was audited token by token: it
contains no fractional number anywhere, and the only occurrences of `mse`,
`clark_west` and `p_value` are the negative attestation keys
`real_mse_computed: false`, `real_clark_west_computed: false`,
`real_p_value_computed: false`. No forecast, loss, statistic or classification
exists in the repository at phase closure, and a test globs the experiment
directory to assert no `result.json` / `execution_result.json` /
`scientific_result.json` / `receipt.json` appeared.

**Authority escalation — CLOSED.** Every authority constant is a module-level
literal, not a computed value: `SCIENTIFIC_EXECUTION_AUTHORIZED`,
`REAL_EVALUATION_OUTCOME_ACCESS_AUTHORIZED` and `DATA_ACQUISITION_AUTHORIZED`
are `False`; downstream, Router, Qnty, trading and capital authority are all
`"NONE"`. The receipt's `next_action` explicitly disclaims creating, implying
or containing the execution authorization.

**Order Flow / JH01 collateral damage — CLOSED.** No Order Flow, JH01,
`binance_um_kline_1h.py` or `binance_um_funding_settlement.py` file is modified.
Order Flow's 12-field materializer extension is left exactly as `d1a327a` left
it; the repair accommodates it rather than reverting it.

**Regression in what the verifier still catches — CLOSED.** Evidence-byte
tampering still fails (`evidence byte mismatch`), the 505-file evidence loop is
untouched, the untracked-materializer continuity check still fires, an empty
`materializer_files` list is refused rather than passing vacuously, and the
identity result is consumed by `verify_baseline`'s return value so it cannot rot
into dead code.

## Findings

### M-01r (Medium) — `verify_historical_materializer_identity` trusts its caller for the baseline self-digest

The function's laundering resistance rests on `required_git_ancestors` being
digest-protected, but it does not itself call
`verify_self_digest(baseline, "provenance_baseline_digest")`. Both production
call sites — `verify_baseline` and `integrity.verify_historical_provenance` —
verify the self-digest immediately before calling it, so the composed behaviour
is correct today. A future caller could invoke it on an unverified dict and lose
that protection.

Not Critical/High: no such caller exists, the anchor-equality check against the
module constants remains an independent barrier even on an unverified dict, and
the phase's own acceptance gates run through the verified paths. Not repaired
here, per the bounded repair policy — moving the self-digest check inside the
function is a one-line hardening for a future phase, and doing it now would also
require rewriting the hostile tests that deliberately pass tampered baselines.

### L-01 (Low) — the current-HEAD `require_tracked` check is vestigial under the new semantics

Historical identity is now proven entirely from Git objects, so asserting the
materializer path is still tracked at HEAD constrains no bytes. It is retained
deliberately — dropping a currently-satisfied invariant would be an unrequested
weakening — and is documented in the docstring as repository continuity only,
explicitly not part of the identity proof. The residual cost is that a
legitimate future *rename* of the shared materializer would fail historical
provenance for a non-historical reason.

### L-02 (Low) — a missing path at an anchor surfaces as the generic git failure

`historical_materializer_digest` carries a specific
`does not resolve to an object at <commit>` message, but
`git rev-parse --verify --quiet` already exits non-zero for a missing path, so
`_git_text` raises `git command failed: [...]` first and the specific branch is
reached only for a resolvable-but-non-SHA output. Both are fail-closed and the
failing command is printed in full; this is message precision only. The test
accepts either message rather than asserting a reachability the code does not
have.

### L-03 (Low) — the preflight's synthetic blindness depends on the caller's factory

`run_synthetic_runtime_preflight` takes a `synthetic_rows_factory`. Nothing in
its signature prevents a future caller from handing it real rows. The practical
barrier is structural rather than syntactic: the frozen executor has no code
path that can obtain real frozen evidence (established by AST check in the
implementation-freeze review), it refuses every execution mode but
`SYNTHETIC_VALIDATION`, and this phase's only caller imports the frozen
synthetic generator. Recorded rather than repaired; a future execution
authorization binds its own evidence identity explicitly.

### L-04 (Low) — the preflight is slow

The hostile-context sweep runs the full 609-row / 244-origin synthetic
evaluation once per context, twice per context counting the unwrapped
comparison. The reconciliation test file takes roughly seven minutes. That is
the price of breadth over the ambient-context surface and is accepted for a
one-shot integrity phase; it is noted so it is not mistaken for a hang.

## Pre-existing baseline observation (not a finding against this phase)

Three test modules fail to collect at canonical master `cc93a6b`, before any
change from this phase: `tests/test_jfp_v2_pr_c.py`,
`tests/test_jigsaw_harvest_execution_v0.py` and
`tests/test_research_data_spine_v0.py`, all with
`ModuleNotFoundError: No module named 'polars'`. The dependency is absent from
the environment. None of the three files is touched by this phase. Installing or
vendoring a third-party dependency is outside this phase's authority and was not
attempted.

The two materializer-byte failures recorded as a pre-existing baseline
observation by the implementation-freeze review —
`test_jigsaw_funding_pressure_provenance_v0.py::test_verify_baseline_end_to_end_orchestration`
and
`test_jigsaw_funding_pressure_execution_foundation_v0.py::test_load_verified_frozen_evidence_end_to_end_structural`
— are the defect this phase repaired, and both now pass.
