# One hostile review — SUBSCRIPTION_BACKED_STAGE_A_V1_COMPARATOR_VALIDITY_REPAIR_V0

Review count: 1 (this is the single independent hostile review of this narrow
repair phase; the PR #131 freeze review is a separate, already-consumed review
and is not reopened here).

Review method: independent static and mechanical inspection of
`comparator_validity_repair_v0/amendment.json`,
`comparator_validity_repair_v0/execution_authorization_amendment.json`,
`qntylab/subscription_backed_stage_a_v1_comparator_validity_v0.py`,
`tests/test_subscription_backed_stage_a_v1_comparator_validity_v0.py`, the
unchanged frozen V1 and V0 contracts, and `docs/state/projects.toml`; plus an
exhaustive brute-force reachability sweep of the classifier over 262,144
evidence shapes (65,536 per correctness cell) and a `git diff` byte audit
against canonical master `332bf46a5543b852197547ffd850b563039c75e5`.

The historical task was not executed. No product worker was dispatched. No
answer key was released. No network call was made.

## Attack results

1. **Can 0/0 still reach any PASS state?** PASS. Machine-proven NO. The
   exhaustive sweep over all 65,536 `0/0` evidence shapes — every combination
   of intervention counts, seal flags, presence flags, capacity events, hard
   gate failures, ambiguity flags, canonicality, and firewall state — yields
   zero PASS classifications. `R5_BOTH_ARMS_INCORRECT_BENCHMARK_INVALID`
   precedes `R6_PRIMARY_NONINFERIORITY_RULES`, so the primary comparator is
   never reached with both scores zero.

2. **Does the repair accidentally require the baseline to be correct?** PASS.
   The final clause of `COMPARISON_VALID` is a disjunction,
   `any(arm.correctness_score == 1 for arm in arms)`, not a baseline
   predicate. `comparison_valid` returns `True` for `1/0`. The frozen
   invariant is `AT_LEAST_ONE_ARM_CORRECT`, never `BASELINE_MUST_WIN`.

3. **Can DSH 1 / Native 0 be incorrectly classified INVALID?** PASS. `R5`
   fires only when both scores are exactly `0`. With `1/0` and no intervention
   regression the classifier returns
   `STAGE_A_V1_PASS_WITH_INCREMENTAL_VALUE`; the sweep finds ten distinct
   PASS-classified `1/0` shapes and zero `1/0` benchmark-invalid shapes.

4. **Does capacity invalidation get confused with benchmark invalidity?**
   PASS with a MEDIUM observation (M-01 below). They are distinct frozen
   constants at distinct precedence ranks, and `R3` strictly outranks `R5`,
   so a throttled episode can never be recorded as a scientific benchmark
   result and a benchmark-invalid episode can never be recorded as an
   environment fault. The observation concerns provenance enforcement, not
   confusion of the two outcomes.

5. **Can missing evidence look like 0 and enter benchmark-invalid rather than
   FAIL_CLOSED?** PASS. `R4_MISSING_OR_MALFORMED_SCORER_EVIDENCE_FAIL_CLOSED`
   precedes `R5`. `_scorer_evidence_is_well_formed` requires
   `scorer_result_present` and a correctness score that is literally an `int`
   in `(0, 1)`; `None`, out-of-range, non-integer, and ambiguous-intervention
   evidence all raise `FailClosed`. Absence is never coerced to zero. An
   earlier draft admitted `True` here because `True == 1` in Python; that hole
   was found by the phase's own test matrix and closed with an exact-type
   check before freeze.

6. **Can an unsealed arm be interpreted as incorrect=0?** PASS.
   `R1_AUTHORITY_FIREWALL_OR_UNSEALED_RECEIPT_FAIL_CLOSED` raises before any
   score is read, for either arm independently.

7. **Did the amendment add another authorized episode?** PASS.
   `authorized_episode_count_after_repair = 1`,
   `cumulative_authorized_episode_count = 1`,
   `additional_episode_added = false`, `second_episode_allowed = false`, and
   the prior authorization's own `authorized_episode_count = 1` is asserted
   equal in test. The frozen controller's `episode_count != 1` preflight and
   its single-episode `_episode_started` guard are untouched, so the machine
   ceiling is unchanged. Rescue rerun is forbidden after both invalid
   classifications.

8. **Did any existing task/scorer/product/role identity change?** PASS. A
   `git diff` against canonical master shows exactly one modified tracked
   file, `docs/state/projects.toml`, with 105 insertions and zero deletions;
   every other change is a new file. All six bound digests were recomputed
   from the files on disk and match the values frozen in PR #131. The
   historical task bytes, BASE, sealed references, product identities, role
   mapping, arm order, DSH commit/tree/tag, zero-fee rule, answer-key
   firewall, retry ceilings, intervention schema, scoring propositions, and
   the binary correctness function are all byte-identical.

9. **Can a branch-local amendment self-authorize execution?** PASS. `classify`
   raises `FailClosed` when
   `comparator_validity_amendment_canonical` is false. The authorization
   amendment is `AUTHORIZED_IF_CANONICAL` with
   `branch_local_execution_authorized = false`,
   `effective_only_after_canonical_merge = true`, and
   `branch_local_candidate_cannot_self_authorize = true`.

10. **Can this repair create runtime/trading/capital authority?** PASS. The
    new module imports only `dataclasses` and four symbols from the frozen
    controller; an AST audit shows no filesystem, subprocess, socket, or
    network access and no module-level side effect. Both amendment artifacts
    pin `current_max_autonomy = L0_SHADOW` with every runtime, DSH runtime,
    Qnty NEXT_ACTION, trading, capital, and auto-merge authority false or
    `NONE`.

## Findings

CRITICAL: 0

HIGH: 0

MEDIUM: 1

- **M-01 — capacity-invalidation provenance is documented, not machine-proven.**
  `ArmScorerResult.capacity_invalidation_events` is specified as receipt-derived
  only, so that capacity invalidation can never be inferred from a correctness
  score. The classifier consumes the field and cannot itself prove where the
  value came from. Mitigating context: the frozen receipt schema owns
  `rate_limit_events`, the frozen deterministic controller is the only producer,
  and the field's only reachable effect is a non-PASS classification that grants
  no authority and forbids rescue rerun. Not repaired: below the
  Critical/High repair threshold for this phase, and closing it would require
  changing the frozen receipt schema, which this append-only repair must not do.

LOW: 2

- **L-01 — `R3` above `R4` softens a would-be fail-closed.** Because capacity
  invalidation is evaluated before missing-evidence, a spurious capacity event
  on an arm with absent scorer output yields
  `STAGE_A_V1_INVALID_ENVIRONMENT_OR_PRODUCT_CAPACITY` rather than
  `FAIL_CLOSED`. No authority is gained: both are non-PASS, both consume the
  single authorized episode, and both forbid rescue rerun. The ordering is
  deliberate — placing every missing-evidence condition above capacity would
  make the already-frozen capacity outcome unreachable, silently mutating PR
  #131 semantics.

- **L-02 — one cell moves from FAIL to INVALID_BENCHMARK.** With `0/0`
  correctness and treatment intervention strictly greater than baseline, the
  pre-repair semantics returned `STAGE_A_V1_FAIL`; the repaired precedence
  returns `STAGE_A_V1_INVALID_BENCHMARK_BOTH_ARMS_INCORRECT`, because benchmark
  invalidity (rank 5) precedes the primary rules (rank 6). This is disclosed in
  `amendment.json` under `known_precedence_consequence` rather than hidden. It
  creates no PASS path, grants no authority the prior FAIL did not grant, and
  reflects that an intervention comparison on a task neither arm solved is not
  informative about orchestration.

Targeted rereview consumed: NO. No Critical or High finding was raised, so no
Critical/High repair occurred and the single permitted targeted rereview was not
triggered.

Verdict: PASS — the repair is append-only, pre-dispatch, digest-preserving,
authority-neutral, adds no episode, and machine-proves
`ZERO_ZERO_PASS_REACHABLE = NO`.
