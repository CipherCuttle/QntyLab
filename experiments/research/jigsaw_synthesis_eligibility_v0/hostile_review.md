# Hostile review — Jigsaw Synthesis Eligibility V0 (F-03)

One independent hostile review per phase contract (Section 29). Reviewer was
a fresh agent instance with no authorship context, given only the frozen
candidate SHA and the attack checklist.

## Review target

`REVIEW_TARGET_SHA = 6cc98cf8a4052948db34de80705fc243977bd684`

Independently verified by the reviewer: no byte of the two source
`result.json` files or `experiments/research/jigsaw_index.json` changed;
full `tests/test_jigsaw_synthesis_v0.py` + `tests/test_jigsaw_index_v0.py`
suite passed (46/46 at that point); both `doctor` commands passed; the
5-piece/2-source F-02 census was unaffected by adding the synthesis
artifact (no self-ingestion); the RV24 outcome-formula mismatch and the
`B_CONTAINS_A` decision-window relation were independently recomputed from
the raw preregistrations and confirmed correct.

## Findings

```text
CRITICAL = 0, none found
HIGH = 2
MEDIUM = 0, none found
LOW = 2
```

**HIGH-1** — `qntylab/jigsaw_synthesis.py`, `_statement_text`,
`SAME_HISTORY_MULTI_PROPOSITION_CONTEXT` branch. The outcome clause branched
on raw `same_outcome`/`same_feature` values instead of the already-computed
`claim_relation`, checking `same_outcome == "YES"` first. An `IDENTICAL_CLAIM`
pair (`same_feature == YES` and `same_outcome == YES`) fell into that branch
and was described as testing "different features" — self-contradicting the
pair's own `same_feature` field. Not reached by the real 5-piece census (no
current pair is `IDENTICAL_CLAIM`), but a real, reproducible defect in code
explicitly designed to be generic for future pieces.

**HIGH-2** — same function, same branch. `CLAIM_RELATION_NOT_ESTABLISHED`
pairs fell through to the same wording as a genuine `DIFFERENT_CLAIM`
("different features and/or outcome definitions"), laundering an
unestablished comparison into confident negative prose even though the
structured `claim_relation` field correctly stayed conservative. This is
exactly the UNKNOWN→NO escalation pattern the phase brief prohibits (Section
6, Section 23-G) — reproduced with a synthetic same-source pair mirroring the
real funding-pressure piece's field shape (no top-level `feature`/`outcome`).

**LOW-1** — per-piece native `does_not_establish`/`non_escalation` lists
(already present in `native_payload`) are not additionally surfaced inside
`piece_inventory`/`synthesis_statements`; only the generic module-level
`prohibited_inferences` list is attached to statements. Substantively
covered already (the generic list bans State Snapshot/causal/trading/
aggregate claims); a completeness gap, not a false statement. Not repaired:
does not falsify the phase objective, invalidate evidence, or create a
trust-boundary risk.

**LOW-2** — `tests/test_jigsaw_synthesis_v0.py`,
`test_m_n_source_and_index_artifacts_byte_unchanged` calls
`write_synthesis(RESEARCH_ROOT)` against the real repository path rather
than an isolated `tmp_path`, mirroring the identical, already-reviewed
pattern in `tests/test_jigsaw_index_v0.py::test_l_source_artifacts_are_byte_unchanged_by_index_generation`
(which calls `write_index(RESEARCH_ROOT)` for the same reason: proving
regeneration doesn't corrupt the *other* protected files). Not repaired:
matches established, closed-phase repo convention exactly; determinism is
independently pinned by `test_o_two_independent_builds_are_byte_identical`.

## Repair

Both HIGH findings share one root cause and one fix: the statement-text
outcome clause now branches directly on `pair["claim_relation"]`
(`IDENTICAL_CLAIM` / `RELATED_DISTINCT_CLAIM` / `DIFFERENT_CLAIM` /
`CLAIM_RELATION_NOT_ESTABLISHED`) instead of re-deriving similar-but-subtly-
different logic from the raw `same_feature`/`same_outcome` fields a second
time. Two regression tests
(`test_identical_claim_statement_never_claims_different_features`,
`test_claim_relation_not_established_statement_never_asserts_confident_difference`)
reproduce the exact scenarios the reviewer found and pin the fix.

The committed `eligibility.json` for the real 5-piece/10-pair census changes
only in the wording of the 4 genuine `DIFFERENT_CLAIM` pairs (JH01↔JH03,
JH01↔JH04, JH02↔JH03, JH02↔JH04): "different features and/or outcome
definitions" → "different features and different outcome definitions",
since for those specific pairs both fields are in fact confirmed `NO`, not
merely defaulted. No pair in the real census is `IDENTICAL_CLAIM` or
`CLAIM_RELATION_NOT_ESTABLISHED`-*within*-`SHARED_FROZEN_HISTORY` (the four
`CLAIM_RELATION_NOT_ESTABLISHED` pairs are all funding-pressure pairs, which
are `OVERLAPPING_HISTORY_INDEPENDENCE_NOT_ESTABLISHED` →
`SEPARATE_ONLY` → no statement generated at all), so the real artifact was
never actually wrong — the bug was latent, reachable only by a future
piece — but it was a genuine defect in code documented as generic, and the
phase's determinism/generality requirement makes latent-but-reachable
exactly the class of bug this review exists to catch before it reaches real
data.

Full test suite after repair: 348 passed (`-k jigsaw`, excluding the two
pre-existing unrelated `polars` collection errors noted in F-02).

Per Section 29: two HIGH findings were repaired within frozen scope; per
"If C/H = 0: NO RE-REVIEW" / "ONE targeted re-review maximum" if repair
occurs, this record substitutes for a second full independent review since
the fix is small (~30 lines), mechanically verified by two new adversarial
tests reproducing the exact reported scenarios, confirmed by rerunning the
full test suite and all doctor commands, and does not touch any other part
of the module's derivation logic, source data, or the F-02 index.

## Post-review closure repair (candidate `994f128` → new candidate)

A closure-gate verification pass, run separately after CI on PR #50 went
green, found one additional **HIGH** fail-open defect not caught by the
first hostile review: `_independence_status` checked
`explicit_independent_replication` (a piece self-declaring
`explicit_independent_replication_of=<other piece id>`) *before* the
shared-frozen-history test (`same_snapshot_identity == YES` or
`same_source_artifact == YES`). A future piece could therefore declare
itself an independent replication of another piece while still
demonstrably sharing that piece's exact frozen snapshot, and the bare
declaration would win over the provenance fact — violating the phase's
core invariant that independence is established by provenance, not
assertion.

Not reached by the real 5-piece/10-pair census (no current piece carries
`explicit_independent_replication_of`), but real and reproducible, and
exactly the "false independence" / "prior-exposure-style laundering"
failure class Section 29 names as CRITICAL/HIGH focus — a self-declared
claim overriding a mechanically-verifiable provenance fact.

**Repair**: `_independence_status` now checks shared history first,
unconditionally, before anything else. `INDEPENDENT_REPLICATION_EXPLICITLY_ESTABLISHED`
is no longer derived from a bare declaration at all — no currently-indexed
field positively establishes empirical data independence (only
presence/absence of a matching `snapshot_id`, which at best proves
non-identity, never independence), and the phase contract forbids inventing
a new field merely to make the state reachable. The status therefore
becomes intentionally unreachable in V0; the `_explicit_independent_replication`
helper and its dead call site were removed rather than left as inert dead
code implying it still mattered. See `design_note.md` for the full
rationale.

Five targeted regression tests were added
(`test_closure_a_declared_replication_with_exact_snapshot_match_stays_shared_history`,
`test_closure_b_declared_replication_with_same_source_artifact_stays_shared_history`,
`test_closure_c_declared_replication_without_shared_history_never_grants_independent_confirmation`,
`test_closure_d_current_real_artifact_semantics_unchanged`,
`test_closure_e_existing_gates_still_pass`), reproducing exactly the
declared-replication-plus-shared-history scenario and confirming the real
artifact's digest and every existing non-escalation/determinism/staleness
gate are unaffected. Rebuilt `eligibility.json` is **byte-identical** to
the pre-repair artifact (digest `e3a2044e38f99457a78fcdd758e6816404cd9aa02746a787fe7c1344874b2e38`
unchanged) — this repair only closes a latent path unreachable by any
current piece; the real 5-piece census never exercised the bug.

Full suite after this repair: 353 passed (`-k jigsaw`, same two pre-existing
unrelated `polars` errors excluded). All doctors (`jigsaw_synthesis`,
`jigsaw_index`, `research_ledger`, `project_context --strict`,
`project_context render --check`) pass. No further broad review performed,
per the closure instruction to repair exactly this defect and stop.
