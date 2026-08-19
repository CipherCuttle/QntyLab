# Funding incremental forecast executor — hostile implementation review

Review count: exactly one.
Review target SHA: `f6f12994d65c3dfeaf7839de560e58ad99547c62` (candidate A).
Reviewed source:
`qntylab/jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py`
(sha256 `b894d4d9316bed6f8c4f7171b32692aff7b1f0eb32abd686a33fdb38425a7490`)
and its synthetic test suite
(sha256 `7de2bd14b2997b5aee9f8820b54a1819b8423da5b55d362a8ab7b0bb95bb6d30`).

Reviewer independence: this review was performed by the receiving
implementation orchestrator as a separate adversarial pass against the
already-frozen candidate commit, not by a third-party agent or human. That
limitation is recorded here rather than overstated: this is a single-actor
hostile review of an immutable target, and it is not an independent external
audit.

## Verdict

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 0 |
| Medium | 2 |
| Low | 4 |

Because Critical/High is zero, the bounded repair cycle was NOT triggered, no
repair pass was performed, and no targeted re-review was used. Per the phase
policy the implementation is not reopened for Medium/Low findings; none of
them invalidates the phase objective or evidence, violates a frozen contract,
or creates a fail-closed or safety defect.

## Attack surface examined, and what was found

**Temporal leakage — CLEAN.** Perturbing every RV24 target whose completion is
at or after evaluation origin *T* leaves *T*'s M0 and M1 forecasts bit-identical.
An end-to-end probe confirmed that tripling the RV24 target of the final
evaluation origin `2025-06-19` changes none of the 244 forecasts. Training rows
are re-verified after selection: any selected row whose origin or target
completion is not strictly before the forecast origin raises.

**Target-completion cutoff — CLEAN and STRICT.** `select_training_rows` admits a
row only when `target_completion < forecast_origin`. The equality case is
explicitly not admitted. The end-to-end signature of this is visible in the
training counts: origin `2024-10-19` trains on exactly the 365 development
origins, origin `2024-10-20` still trains on 365 (the `2024-10-19` row's target
completes exactly at `2024-10-20` and is therefore refused), and origin
`2024-10-21` trains on 366.

**Excluded boundary `2024-10-18` — CLEAN.** The origin is absent from
`forecast_row_origins()` by construction, `forecast_row_origins()` asserts the
three structural facts that justify the exclusion, re-introducing the row is
rejected as an extra origin, and a probe confirmed the boundary day is never a
training target. Its RV24 and funding-pressure *observations* are still
required, correctly, because they are legitimate lag and ECDF-history inputs
for later origins.

**Accidental real-outcome use / real-evidence loading — CLEAN.** The module
imports the canonical modules only for pure primitives and verified evidence
dataclasses. An AST check confirms it references none of
`load_verified_frozen_evidence`, `claim_authorization_once`,
`execute_authorized_frozen_experiment_v2`, `attest_v2_runtime`,
`compute_frozen_experiment`, `build_receipt_provenance`, any authorization
envelope type, `open`, `urlopen`, `eval`, `exec` or `__import__`, and performs
no filesystem write and no `requests`/`urllib`/`socket`/`subprocess` import.
The only filesystem touch is reading this module's own bytes for its identity
digest. Every evaluation entrypoint call additionally refuses any
`execution_mode` other than `SYNTHETIC_VALIDATION`.

**Model / feature / lag / threshold search — CLEAN.** There is no callable whose
name or body performs selection; the HAR windows `(1, 7, 30)`, the HAC lag `5`
and `alpha = 0.05` are module constants, and passing a different HAC lag or
alpha raises `ContractViolationError` rather than being honoured.

**HAR off-by-one — CLEAN.** `rv24_lags[k]` is the RV24 realized over
`(origin-(k+1)d, origin-k d]`, so `rv24_lags[0]` completes exactly at the
origin. Daily is `rv24_lags[0]`, weekly is the mean of lags 1..7 and monthly the
mean of lags 1..30, matching the frozen
`mean(RV24_prior_{t..t-6})` / `mean(RV24_prior_{t..t-29})` definition. A
calendar-alignment test re-derives every lag from the source grid.

**M0/M1 asymmetry — CLEAN.** `m1_design_row` is literally `m0_design_row` plus
one appended column and asserts both the nesting prefix and the exact
one-column width increase; the evaluation loop re-asserts the width relation at
every refit.

**Zero-floor asymmetry — CLEAN.** One shared `apply_nonnegative_floor` is
applied to both forecasts, and the source contains exactly two
`apply_nonnegative_floor(linear_forecast(` call sites.

**Clark-West sign — CLEAN.** `d_t = e0^2 - e1^2 + (f0 - f1)^2` matches the
frozen formula term for term; negating the difference series negates the
statistic exactly and strictly increases the one-sided p-value.

**HAC lag / defaults — CLEAN.** Bartlett weights are `1 - j/(L+1)`, the
autocovariance divisor is the full sample size `T` (not `T - j`), there is no
finite-sample correction, and all three conventions are asserted against an
independently written direct oracle and against a hand-computed alternating
series. A non-positive long-run variance fails closed instead of producing a
statistic.

**One-sided direction — CLEAN.** The p-value is the standard normal UPPER tail
of the statistic, so a larger positive statistic (M1 favoured) yields a smaller
p-value. Calibration at the frozen one-sided 5% critical value agrees with
`0.05` to better than 1e-20, and the routine is validated against `math.erfc`
across `|z| <= 9` to a relative error below 1e-12.

**Rank deficiency — CLEAN.** The normal equations are formed and solved in exact
rational arithmetic, so rank deficiency is an exact zero pivot, not a tolerance
decision. Duplicated columns, a constant non-intercept column, fewer
observations than regressors, and a whole-evaluation refit made collinear by a
degenerate funding percentile all raise `RankDeficientDesignError`. There is no
pseudo-inverse or regularization fallback.

**Missing / extra origin acceptance — CLEAN.** The RV24 and funding-pressure
grids must match the frozen day sets exactly; a dropped day, a day outside the
range, a dropped forecast row, an appended row, a duplicated row and a
reordered row are each rejected with a distinct fail-closed error.

**Non-finite numeric acceptance — CLEAN.** `NaN`, `Infinity`, `-Infinity`,
negative RV24, `float`, `str` and `None` are all refused at grid ingest and
again at row validation; a percentile outside `[0, 1]` is refused. `float` is
refused everywhere contract-visible so no binary floating point can enter.

**Nondeterminism — CLEAN in effect (see M-01).** Two runs on identical synthetic
input produce identical result digests, and a run under a hostile ambient
Decimal context (`prec=7`, `ROUND_UP`) produces the same digest. All
contract-visible arithmetic is exact rational with a single declared
quantization point; the two inexact steps run inside explicit fixed-precision
contexts.

**Low-level funding / RV duplication or drift — CLEAN.** The executor delegates
to `v2.select_latest_eligible_funding`, `v2.median_abs_funding`,
`v2.ecdf_percentile`, `v2.hourly_asset_returns`, `v2.market_returns`, `v2.rv24`
and `v2._utc`, and an AST check confirms it defines no local function with any
of those names. Foundation V0 fail-closed boundaries are untouched.

**Authority escalation / result recording / false claims — CLEAN.** The module
declares `DOWNSTREAM_AUTHORITY = CAPITAL_AUTHORITY = "NONE"`, carries a
uniformly false no-real-execution attestation, and its PASS label is
`FUNDING_PRESSURE_INCREMENTAL_VALUE_ESTABLISHED_EXPLORATORY_ONLY` with an
explicit claim boundary disclaiming materiality, economic significance,
causality, inverse funding effect, action utility, trading edge, State Observer
promotion, Router authority, Qnty authority, independent confirmation, sealed
evaluation and prospective status. Nothing is written to disk and no result
artifact is created.

## Findings

### M-01 (Medium) — the p-value precision guard is computed in the ambient Decimal context

In `standard_normal_upper_tail`, `guard = int(x * x / _LN_10) + 1` is evaluated
outside any `localcontext`, so the guard *size* depends on ambient interpreter
state (and an ambient trap on `Inexact` would raise there).

Not Critical/High: the guard only sizes extra working precision on top of a
fixed `+30`-digit margin, and the reported p-value is quantized to 40 digits.
Empirically the returned p-value is byte-identical across ambient contexts of
`prec` 1, 2, 7 and 300 under `ROUND_UP` and `ROUND_FLOOR` for statistics
spanning both algorithm branches, and a worst-case analysis bounds any guard
error at a few digits against a 30-digit margin. The determinism claim holds;
the isolation is nonetheless incomplete in principle.

Recommended in a future phase (not repaired here, per the bounded repair
policy): compute the guard inside an explicit context.

### M-02 (Medium) — the frozen panel is reused but not asserted against the preregistration

The executor takes the 20-member panel from `v2.PANEL` (which derives from the
digest-bound `provenance.PANEL`) and never asserts it equals
`feature_contract.panel` in the governing preregistration. The two are verified
byte-for-byte equal, in order, at this commit, and the panel cannot be exercised
against real evidence in this phase. But `MISSING_OR_SUBSTITUTED_PANEL_MEMBER`
is a declared kill condition, and a mechanical binding is absent.

Recommended: the separate execution-authorization phase MUST bind the panel to
the preregistration before any real run.

### L-01 (Low) — docstring says "partial pivoting", code selects the first nonzero pivot

With exact rational arithmetic there is no growth-factor motive for
largest-magnitude pivoting and the result is identical either way, so this is a
documentation-precision issue only. The actual rule is recorded correctly in
`execution_semantics_v0.json` as `FIRST_EXACTLY_NONZERO_PIVOT`.

### L-02 (Low) — `classify` returns `BLOCKED` only for the origin-count gate

Every other declared BLOCKED condition (source, panel, timing, PIT,
missingness, digest, execution boundary) raises an `IncrementalForecastError`
subclass instead of returning the string. That is strictly stronger fail-closed
behaviour — no result object can be produced at all — but the asymmetry could
mislead a reader of `classify` in isolation.

### L-03 (Low) — unreachable-effect branch in `select_training_rows`

The `elif completion == forecast_origin: continue` arm has no effect because the
preceding strict `if` already excludes it. It is deliberate
documentation-as-code marking the exact boundary; it is dead in effect.

### L-04 (Low) — one tautological leakage assertion in the test suite

`test_lagged_rv24_that_completes_after_the_origin_is_never_a_feature` asserts
`completion <= origin` over values constructed to satisfy it. The substantive
leakage guarantee is carried by
`test_future_targets_cannot_influence_any_forecast` and by the training-count
signature tests, so coverage is not actually reduced.

## Pre-existing baseline observation (not a finding against this phase)

Two tests fail at canonical master `83634e6` before any change from this phase:
`test_jigsaw_funding_pressure_execution_foundation_v0.py::test_load_verified_frozen_evidence_end_to_end_structural`
and
`test_jigsaw_funding_pressure_provenance_v0.py::test_verify_baseline_end_to_end_orchestration`,
both with `materializer byte mismatch: qntylab/binance_um_kline_1h.py`. The
frozen funding provenance baseline expects
`e5a333f3ce08bb95fa7ef6144fffc672cf14ddf2226dc74817db62beb987cdfa`; the file
currently hashes to
`10ec8bad1290cc102db835fa6cce49d501dd629c42e9e48c4084e74a853757d8`, changed by
the unrelated commit `d1a327a` ("qnty edge: add outcome-free order flow
readiness", 2026-08-16) without a corresponding baseline update. Reproduced in a
pristine worktree at `83634e6` containing none of this phase's files. Repairing
a frozen funding provenance baseline is outside this phase's authority and was
not attempted.
