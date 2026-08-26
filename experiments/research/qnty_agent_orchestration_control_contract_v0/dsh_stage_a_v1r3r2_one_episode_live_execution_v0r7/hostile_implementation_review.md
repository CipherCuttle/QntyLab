# V0R7 activation hostile review

Review count: 1
Review verdict: `HOSTILE_REVIEW_PASS`
Critical findings: 0
High findings: 0
Medium findings: 0
Low findings: 2
Targeted rereview used: false

## Review scope

Independent hostile implementation review of the staged, uncommitted V0R7
activation candidate on branch
`agent/dsh-stage-a-v1r3r2-one-episode-live-execution-activation-v0r7`
(worktree `/var/tmp/qntylab-v0r7-activation-worktree`, HEAD
`908dfed34b5f22bb99e77c146a757a8e6299064c`). Exactly five staged files:

1. `experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_one_episode_live_execution_v0r7/activation.json` (new)
2. `docs/state/projects.toml` (new `[[project]]` entry + minimal `activation_exists` flip)
3. `docs/CURRENT_ROADMAP.md` (regenerated, one projected line)
4. `tests/test_dsh_stage_a_v1r3r2_one_episode_live_execution_activation_v0r7.py` (new)
5. `tests/test_dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r7.py` (stale-bind repair)

All twelve attack vectors A1–A12 were attacked individually; canonical truth
was re-derived mechanically from Git inside the worktree, not taken from the
candidate's own claims.

## Review method

Read-only review. Explicitly: no secret file was read, stat'ed, or hashed
(`~/.secrets/openai_api_key_stage_a` untouched); no provider or model calls;
no DSH runs; no claim refs or state directories created; no fixture execution;
no commits; no PR. Evidence gathered via `git cat-file`, `git ls-tree`,
`git rev-list --parents`, `git diff --cached`, `git status`, sha256 recomputation,
read-only `git ls-remote` / `git show-ref` (as invoked by the candidate's own
focused tests), static inspection of all changed files and of `guard.mjs`,
and one run of the focused pytest suite:

```
python -m pytest tests/test_dsh_stage_a_v1r3r2_one_episode_live_execution_activation_v0r7.py tests/test_dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r7.py -q
16 passed in 1.38s
```

## Findings

Attack-vector verdicts:

- **A1 authorization byte substitution — PASS.** The candidate binds both the
  exact blob (`564aa9592f818900c79a8bea4f3954cb460fd132`) and sha256
  (`e3543b3a0163f783b7e4404bfccc60d9fe2ad2bc898d11e81e0dd13a90000da8`) of
  `authorization.json` at `908dfed…`. Both were independently re-derived from
  Git and match. The activation test recomputes the working-tree sha256
  (`test_..._activation_v0r7.py:74`) and resolves the blob from the pinned
  `origin/master` tree (`:75`); since `origin/master` itself is asserted equal
  to `908dfed…` (`:65`), a stale or fabricated hash cannot pass without also
  moving the pinned merge commit.
- **A2 authorization merge substitution — PASS.** `908dfed…` is bound as
  `canonical_authorization_merge`/`authorization_merge` with exact parents
  `[2c0804ae…, a8f1d3eb…]` (`activation.json:33-37,50-55`; registry entry;
  test `:70-73` asserts `rev-list --parents -n 1` equals exactly
  `[merge, p1, p2]`). `a8f1d3eb…` is separately bound as
  `candidate_commit` (`activation.json:49`) and `2c0804ae…` as the authorized
  execution source (`:16`); neither is equated to the merge anywhere, and the
  test asserts `AUTHORIZED_EXECUTION_SOURCE_SHA != AUTHORIZATION_MERGE`
  (`:100`).
- **A3 branch-local self-activation — PASS.** Branch-local bytes grant no
  effective authority: `effective_execution_authority: false`,
  `branch_local_effective_execution_authority: false`,
  `activation_effective: "AFTER_EXACT_CANONICAL_MERGE_ONLY"`,
  `branch_local_candidate_does_not_self_authorize: true`
  (`activation.json:11-14,38`). The test proves inertness structurally:
  `cat-file -e 908dfed:<activation path>` must fail (`:127`), i.e. the
  artifact does not exist on canonical master yet, and the authority
  projection must not mark the project effective (`:275`).
- **A4 source/root conflation — PASS.** `authorized_execution_source_sha`
  (`2c0804ae…`, git commit object) and `execution_contract_root`
  (`cf1aff07…`, content-addressed sha256) are separate fields with an explicit
  `source_root_invariant` block asserting independent binding and
  `root_not_sha256_of_source: true` (`activation.json:16-27`); no field
  equates them, and the test freezes both independently (`:95-100`).
- **A5 stale predecessor contract substitution — PASS.** The qualified digest
  is `cf1aff07…` everywhere (`activation.json:17,87,102,163`); the historical
  predecessor `e16872fc…` appears only inside explicit rejection lists
  (`historical_predecessor_contract_digest` context at `:88` with
  `historical_contract_substitution_allowed: false` at `:95`, and
  `superseded_digest_rejected` at `:111-113`). No V0R5/V0R6-era digest is
  used as the live binding.
- **A6 claim-owner duplication — PASS.** Sole owner is bound verbatim:
  `sole_owner = "parent_enforcement_guard_ensureClaim_inside_reserve_before_next"`,
  owner path ends in `lib/guard.mjs`, `owner_binding =
  "ensureClaim() invoked inside reserve() before next()"`
  (`activation.json:147-149`). Verified against actual source:
  `ensureClaim()` defined at guard.mjs:118, invoked inside `reserve()` at
  line 145, `next()` first reached at line 166. No second owner, no
  caller-selectable namespace/ref/semantic ids (`:165-167` all false), no
  pre-claim shell orchestration (`:152,158-159`).
- **A7 pre-claim provider I/O — PASS.** The artifact's
  `action_time_gate_order` (`activation.json:319-342`) is byte-for-byte the
  same 22-gate sequence as canonical `authorization.json` at blob
  `564aa959…` (extracted and compared element-wise: identical). Order
  preserves CLAIM COMMITTED (gate 19/20) before provider I/O (gate 21);
  secret read (gate 17) precedes claim creation (gate 19) and follows all
  non-secret gates (gate 16). Test additionally asserts the relative order of
  the three critical gates (`:200-204`).
- **A8 replay/second-episode leakage — PASS.** All replay/retry/rerun/
  second-episode flags are false in both artifact (`episode_identity:136-140`,
  `terminal_semantics:401-407`) and test assertions (`:140-147`). V0R5
  protection accurately describes observed state: directory contains exactly
  `{claim-intent.json, claim.lock}`, no receipt, `BLOCK_NEVER_REPLAY`
  (`:190-203`; test verifies on disk `:189-194`). V0R6 protection records
  `CLOSED_BLOCKED` with all controls false (`:204-214`). Both marked
  `mutated_during_activation: false`.
- **A9 secret read during activation — PASS.** `construction_receipts`
  records `secret_reads: 0` (`activation.json:343-355`), asserted verbatim by
  the test (`:161-173`); `activation_phase_secret_reads: 0` and
  `real_secret_path_never_used_during_activation: true` (`:312-313`). No code
  path in the changeset touches the secret — the tests perform only git read
  commands, JSON/TOML reads, and `project_context render --check`. This
  reviewer did not read, stat, or hash the secret.
- **A10 QntySpot/state collateral mutation — PASS.** `git status --short` in
  the worktree shows exactly the five declared files staged and nothing else
  (no unstaged modifications, no untracked files). `data/`, QntySpot state,
  ledger files, and `qntylab/` sources are untouched.
- **A11 Stage-B/downstream authority leakage — PASS.** `authority_firewall`
  is uniformly false/NONE including `stage_b_authorized: false`,
  `qnty_runtime_authority: "NONE"`, `trading_authority: "NONE"`,
  `capital_authority: "NONE"`, `promotion_authority: "NONE"`,
  `broader_production_authority: "NONE"` (`activation.json:369-388`); mirrored
  in the registry entry. The roadmap addition projects under "Queued — not
  authorized" with `PLANNED_NOT_AUTHORIZED` and an explicitly prohibitive
  next-action string; it implies no live authority.
- **A12 activation accidentally executes episode — PASS.** Static inspection
  of both test files shows no DSH invocation, no provider call, no claim
  creation, no fixture execution; subprocess use is limited to read-only git
  commands (`rev-parse`, `merge-base --is-ancestor`, `rev-list`,
  `cat-file -e`, `ls-remote`, `show-ref --verify`) and
  `python -m qntylab.project_context render --check`. `ls-remote`/`show-ref`
  absence checks are read-only. `episode_claimed_initial` /
  `episode_consumed_initial` are false and asserted (`:140-141`), and the
  focused run completed green with zero side effects (16 passed).

Disclosed deviations vs precedent:

- `hostile_review_verdict = "PENDING"` — precedent-consistent: three existing
  entries at HEAD `908dfed…` already carry `"PENDING"` for phases whose review
  had not yet occurred. Post-merge semantics unambiguous because the verdict
  field is review bookkeeping, not authority; all effective-authority fields
  remain false.
- `candidate_state = "ACTIVE_CANDIDATE"` — new registry enum value with no
  direct precedent at HEAD (existing values include
  `CANONICAL_AUTHORIZATION_EFFECTIVE`, `CLOSED_BLOCKED`,
  `CANONICAL_CONTINUATION_BOUND`). See Low finding L-1.
- The modified authorization test's `CURRENT_CANONICAL_MASTER` re-freeze
  follows the V0R6 precedent pattern exactly: artifact-bound base constant
  kept separate from the advanced current master, plus an ancestor check
  (`merge-base --is-ancestor CANONICAL_MASTER CURRENT_CANONICAL_MASTER`),
  mirroring how the V0R6 test separated its repair merge from the then-current
  master. Minimal three-line semantic diff; no weakening of any prior
  assertion.

Severity-classified findings:

- Critical: none.
- High: none.
- Medium: none.
- Low:
  - **L-1** — `candidate_state = "ACTIVE_CANDIDATE"`
    (`docs/state/projects.toml`, new V0R7 entry) introduces a new registry
    enum value without precedent at HEAD `908dfed…`. Mitigated: the canonical
    `state` field remains `PLANNED_NOT_AUTHORIZED`, `activation_authorized =
    false`, all effective-authority fields are false, and the new test asserts
    the project does not project as effective
    (`test_..._activation_v0r7.py:247-275`). Cosmetic taxonomy risk only; no
    post-merge semantic ambiguity because effectiveness is gated on
    `state`/`activation_authorized`, not `candidate_state`.
  - **L-2** — `test_one_episode_claim_tuple_and_zero_activity` performs a
    live `git ls-remote origin` (`test_..._activation_v0r7.py:175`), making
    the focused suite dependent on network reachability of the origin remote.
    Read-only and safe, but could fail spuriously offline. Not a correctness
    or security defect.

## Disposition

PASS. All twelve attack vectors A1–A12 verdict PASS with mechanically
re-derived evidence; canonical binds (merge `908dfed…` with parents
`[2c0804ae…, a8f1d3eb…]`, authorization blob `564aa959…` / sha256
`e3543b3a…`, claim impl blob `6275cdbe…` / sha256 `086b4612…`, source
`2c0804ae…` and contract root `cf1aff07…` independently bound) all match Git
truth exactly. The candidate is provably inert until a separate exact
canonical activation merge, consumes no episode, reads no secret, creates no
claim, and grants no downstream authority. The focused suite is green
(16 passed). The two Low findings require no repair and do not block merge.
No Critical or High item requires repair.
