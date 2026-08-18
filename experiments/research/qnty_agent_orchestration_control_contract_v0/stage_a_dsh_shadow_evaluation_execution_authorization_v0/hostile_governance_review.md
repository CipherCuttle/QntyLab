# Stage-A DSH Shadow Evaluation Execution Authorization V0 — Hostile Governance Review

Review identity: `ONE_INDEPENDENT_HOSTILE_GOVERNANCE_REVIEW`

Review scope: the new execution-authorization candidate, its project-registry
entry, the frozen Stage-A preregistration bindings, and the phase diff from
canonical base `efc208e1521b827f184779d8e8419d574bdd1c92`. The focused
authorization tests passed before this review. No DSH package was installed;
no arm, scorer, or historical task was executed.

Verdict: `PASS`

Hostile attack results:

1. Branch-local artifact self-activation — `not present`; the artifact records
   `AUTHORIZED_IF_CANONICAL`, requires presence in canonical `origin/master`,
   and explicitly marks branch-local self-authorization false.
2. More than one episode or duplicate initial dispatch — `not present`; the
   authority grants one episode, two arms, and one initial dispatch per arm.
3. Arm-order change or parallel execution — `not present`; the immutable order
   is `DSH_TREATMENT` then `NATIVE_BASELINE`, with parallel execution false.
4. Floating or substituted DSH — `not present`; commit, tag, package, version,
   source tree, profile, and config digest are pinned and identity mismatch
   fails closed.
5. Hidden DSH retries — `not present`; internal retries must be receipted and
   consume the frozen machine-retry ceiling.
6. Worker GitHub writes or leaked credentials — `not present`; worker writes
   are zero, write credentials are `NONE`, PR publication and merge are `NO`,
   and the trusted Git broker is not invoked by an arm.
7. Answer-key exposure or outcome adaptation — `not present`; workers cannot
   access sealed references or diffs, and scoring is released only after both
   arm outputs and receipts are sealed.
8. Task, scorer, intervention, gate, receipt, or hard-gate drift — `not
   present`; all required digests and the frozen hard-gate values are bound.
9. Model mismatch or fabricated provider build identity — `not present`; both
   arms require observable parity, provider is OpenAI, selector is `gpt-5`,
   and the provider build remains `NOT_EXPOSED` and unclaimed.
10. Harness-isolated causal claim — `not present`; the contrast remains
    `SYSTEM_LEVEL_COMPARISON` and harness attribution is forbidden.
11. Runtime, Qnty `NEXT_ACTION`, scientific, trading, or capital escalation —
    `not present`; each authority remains false or `NONE`, with `L0_SHADOW`
    preserved.
12. Order-flow contamination or mutation of another repository — `not
    present`; no protected order-flow path or external repository is in the
    phase diff.
13. Auto-merge or autonomous result publication — `not present`; both remain
    forbidden, and only local post-episode evidence materialization is allowed
    under the future controller boundary.
14. Experimental execution in this authorization phase — `not present`; DSH
   is not installed, neither arm ran, no scorer ran, no answer key was
   released, and no execution receipt was generated.

Findings:

- Critical: 0
- High: 1 (candidate-versus-canonical presence wording was initially too implicit)
- Medium: 0
- Low: 0
- C/H repair: completed
- Targeted re-review: used once
- Review-of-review: not performed

The review closes the governance candidate only. It authorizes no Stage-A
execution before canonical merge, no DSH installation in this phase, no
runtime implementation, evaluator creation, publication, merge, scientific
action, trading, capital action, or automatic merge.

Targeted wording rereview: the canonical-presence marker was tightened after
the initial review to make its candidate-freeze timestamp explicit. The
artifact now requires canonical-presence verification after merge; this
repair does not change the one-episode scope or any authority ceiling.

- Critical/High repair: 1 wording-boundary repair
- Targeted rereview: `CONSUMED`
- Targeted rereview verdict: `PASS`
