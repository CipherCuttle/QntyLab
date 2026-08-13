# JFP03 V0R1 Historical Scientific Execution Authorization — Hostile Review

Review scope: the staged authorization candidate on `agent/jfp03-v0r1-scientific-execution-authorization`, limited to the frozen executor, targeted tests, project-context registration, roadmap entry, and authorization artifact. The review did not open any object under `data/archive`, invoke `execute_once` or `load_frozen_klines`, compute the historical result, or use network/source access.

## Verdict

`BLOCKED_AUTHORIZATION_CLOSURE`

Severity counts:

- CRITICAL: 0
- HIGH: 2
- MEDIUM: 1
- LOW: 0

Both HIGH findings require correction before this authorization may close. At most one targeted re-review is permitted after the fixes.

## Findings

### HIGH-01 — The one-shot claim is worktree-local and does not prevent replay from another worktree or clone

The authorization is a portable Git-backed grant, but the only consumption record is created at the ordinary worktree-relative path `experiments/research/jigsaw_fast_prospective_signal_discovery_v0/execution/v0r1/historical_scientific_execution_started.json`. `claim_execution` uses `O_EXCL` and fsync at that path (`qntylab/jfp03_v0r1_historical_scientific_execution.py:606-652`). This is durable and race-safe only for concurrent processes resolving the same filesystem path. A second Git worktree or clone begins without that file, still sees canonical `historical_scientific_execution_runs_consumed = 0`, and can independently pass verification and create its own claim. The current repository demonstrably has multiple worktrees, so this is not hypothetical.

The targeted replay test (`tests/test_jfp03_v0r1_historical_scientific_execution_authorization.py:275-282`) invokes the claimant twice against one temporary root and therefore cannot detect cross-worktree replay.

Required fix: use a repository-wide, compare-and-create consumption mechanism shared by all eligible execution worktrees, or bind the authorization canonically to one uniquely identified execution workspace and fail everywhere else. The execution itself may remain network-free; a claim in the Git common directory can cover worktrees of one clone, while truly cross-clone one-shot authority requires a shared/canonical claim transport or an explicit narrower authority model. Preserve claim-before-source-open, crash consumption, fsync durability, and no-replay semantics, and add a test with two distinct worktree roots competing for the same authorization.

### HIGH-02 — Executor identity omits the Python/NumPy/numerical backend runtime

The authorization freezes the Python source SHA and the JSON executor-contract digest (`historical_scientific_execution_authorization.json:28-31`), and `verify_frozen_bindings` checks both (`qntylab/jfp03_v0r1_historical_scientific_execution.py:557-563`). Neither identity binds or verifies the Python version, NumPy version, platform floating-point assumptions, or BLAS/LAPACK implementation. The model uses `numpy.linalg.lstsq`, `numpy.linalg.inv`, and `numpy.linalg.matrix_rank` (`qntylab/jfp03_v0r1_historical_scientific_execution.py:391-400`), whose floating-point results and rank decisions can vary across NumPy/LAPACK builds. Those values directly determine gamma, HAC variance, p-values, partial R2, and inclusive threshold classifications.

The current environment is Python 3.14.4 and NumPy 2.3.5, but those identities are absent from both the authorization and `executor_contract`; the project also has no visible environment lock binding this execution. A later runtime can therefore produce a different scientific result while satisfying the same frozen executor identity. Combined with HIGH-01, alternate runtimes could also be tried through separate worktrees, creating a post-outcome selection channel.

Required fix: freeze and verify a hermetic numerical-runtime identity before the sole claim/source access. At minimum bind the Python implementation/version, exact NumPy version, architecture, and BLAS/LAPACK backend/build identity, preferably through an immutable environment/container digest. Emit that identity in the result. Tests must reject runtime drift. Merely recording the runtime after computation is insufficient.

### MEDIUM-01 — Terminal multiplicity output labels JFP03 as still ready for execution

`multiplicity_family` always assigns JFP03 status `READY_FOR_AUTHORIZED_EXECUTION` (`qntylab/jfp03_v0r1_historical_scientific_execution.py:441-449`). The same function is used after successful classification and for both blocked terminal paths (`qntylab/jfp03_v0r1_historical_scientific_execution.py:824-859`). This can yield a top-level terminal result of `DISCOVERY_SUPPORTED_WITHIN_FROZEN_SCOPE`, `NO_DISCOVERY_SUPPORT_FOUND`, `BLOCKED_CANDIDATE`, or `BLOCKED_GLOBAL` while the ordered family row says JFP03 is merely ready. The preregistration requires completed or blocked runs to emit ordered candidate results with terminal classifications.

Required hardening: pass the actual JFP03 terminal classification into the family constructor and assert consistency between the family row and top-level result. This does not alter the fixed family-size-three denominator or fabricate values for blocked candidates.

## Hostile attack matrix

- Look-ahead: PASS. AFI and every HAR regressor use data with logical close boundary at or before `t`; the target starts at `t+1h`.
- Off-by-one close boundaries: PASS. A kline closes logically at `open_time + 1h`; returns are indexed by logical close boundary. The first HAR-720 uses returns `t-719h..t`, requiring closes `t-720h..t`.
- HAR contamination: PASS. Frozen 1/24/168/720 windows end at `t` and contain no target return.
- Target overlap: PASS. Target boundaries are exactly `t+1h..t+24h` and are asserted disjoint from HAR-720.
- Wrong AFI denominator: PASS. Source field 7 is total quote-asset volume and field 10 is taker-buy quote-asset volume.
- Signed-versus-absolute confusion: PASS. AFI is exactly `abs(2 * taker_buy_quote_volume / total_quote_volume - 1)`.
- Row dropping: PASS. Exact ordered source coverage and all 43,848 scheduled rows are mandatory; missing, duplicate, nonfinite, or zero-denominator inputs fail closed.
- Common-sample mismatch: PASS. Baseline and full matrices are slices of one finite array and use the same response/sample.
- HAC lag/implementation: PASS. Bartlett/Newey-West lags 1 through 24, no lag selection and no finite-sample correction match the frozen contract. Runtime identity remains blocked by HIGH-02.
- Partial R2: PASS. Both nested OLS fits share the sample and use `(SSE_baseline - SSE_full) / SSE_baseline`, gated inclusively at 0.001.
- Multiplicity denominator and blocked null p-values: PASS WITH MEDIUM-01. JFP03 uses `min(1, 3*p)` and raw alpha `0.05/3`; JFP01/JFP02 remain ordered with null scientific values rather than fabricated p=1. Terminal status propagation is inconsistent.
- Direction bypass: PASS. Support requires strictly positive gamma in addition to inference and materiality gates.
- Post-outcome tuning: FAIL via HIGH-02 and HIGH-01. Constants/source bytes are frozen, but runtime selection is not, and worktree-local replay permits alternate executions.
- Executor identity drift: FAIL via HIGH-02. Source bytes and executor-contract digest match the staged authorization, but dependent numerical runtime identity is not frozen.
- Replayability: FAIL via HIGH-01. Same-path replay and crash survival pass; cross-worktree/cross-clone replay does not.
- Scientific-result authority escalation: PASS. Authorization and result envelope deny Jigsaw synthesis, State Snapshot, Forecaster, Router, Qnty, paper trading, trading, promotion, and capital authority.

## Verification evidence

- Staged executor SHA recomputed as `615901b5d320fda720e927ba3581e538f4ecd711a29166afbbcc7a3f756ef792`, matching the authorization.
- Executor-contract digest recomputed as `52f074fe564a2dbbea923dae7b561b652baba9b3a0d159ef67368686b1dab04f`, matching the authorization.
- Authorization self-digest recomputed successfully.
- Synthetic/metadata-only targeted tests plus project-context tests: `45 passed`.
- `python -m qntylab.project_context`: clean authority interpretation, active project `none`, no warnings.

No historical scientific value or result was computed by this review.
