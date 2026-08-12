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

```
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
