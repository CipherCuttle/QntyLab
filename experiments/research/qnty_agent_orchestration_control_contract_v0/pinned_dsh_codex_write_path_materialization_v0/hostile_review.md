# Independent hostile review — PINNED_DSH_CODEX_WRITE_PATH_MATERIALIZATION_V0

- Class: `INDEPENDENT_HOSTILE_REVIEW` (not the implementation agent's own in-phase adversarial self-review).
- Reviewer: separate agent, read-only, explicitly barred from live product calls and from modifying files.
- Timing: after materialization + deterministic precheck, **before** the pre-live freeze and before the single live D4.
- Counts as reported: `CRITICAL = 1`, `HIGH = 6`, `MEDIUM = 3`, `LOW = 3`.
- Counts as recorded here: `CRITICAL = 1`, `HIGH = 7`, `MEDIUM = 3`, `LOW = 3`. The reviewer's `HIGH_COUNT`
  tally undercounted its own report by one; seven HIGH finding blocks were emitted and all seven were fixed.
- Disposition rule applied: fix `CRITICAL`/`HIGH` once, then at most one targeted rereview. `MEDIUM`/`LOW`
  are recorded, not fixed, except where a `MEDIUM` observation was already required by a `HIGH` fix.

## CRITICAL

### C1 — Runtime artifacts were gated on existence only; `lib/` is gitignored

The four generated runtime entrypoints the frozen driver imports were checked for *existence*, not for
*bytes*. Because `lib/` is `.gitignore`d, the clean-tracked-tree check is blind to them, so a stale or
tampered `lib/` — including a hand-written `subagent-codex` that spawns a decoy `codex app-server` and
writes `AFTER` itself — would have satisfied every gate and produced a PASS.

**Fixed.** Added `REQUIRED_ARTIFACT_SHA256` (the four hashes from the recorded reproducible build) and a
new `PINNED_DSH_RUNTIME_ARTIFACT_DRIFT` failure class. `classify_materialization` now fails closed on any
drift, and the runner re-hashes the artifacts at live-run time, immediately before the call. This binds
*execution* to *verification*. It is this phase's own build attestation, not an upstream-published one;
that limitation is stated in the code.

## HIGH

### H1 — `install_ok` / `build_ok` / `lockfile_unchanged` defaulted to `True` from unset env vars

Three of six materialization inputs failed **open** and were re-emitted as `FROZEN_LOCKFILE_OK` / `build: OK`.

**Fixed.** The runner now reads `materialization_record.json`; an absent record yields `install_ok = False`
and `build_ok = False`. `pnpm-lock.yaml` is re-hashed at run time against the pinned `LOCKFILE_SHA256`.

### H2 — The PASS branch ignored `status`, `error`, `bridgeExitCode`, and `parentLlm*`, and read only `ends[0]`

A receipt could report `stopReason: completed` alongside a dispose error, a non-zero exit, an active DSH
parent LLM, or a trailing `error` end, and still PASS.

**Fixed.** Added `receipt_integrity()`, which fail-closes on a non-D4 route marker, any parent-LLM activity,
a non-`COMPLETED` status, any error, a non-zero driver exit, and credential presence in the driver env.
`completed` is now computed over **all** recorded ends. Parent-LLM activity classifies as
`DSH_EFFECTIVE_CONFIG_DIVERGENCE`.

### H3 — "Exactly one live attempt" was unenforced; the receipt could be silently overwritten

**Fixed.** `main()` refuses to run when `d4_receipt.json` already exists, and an append-only
`d4_attempts.jsonl` line is written **before** the live call, so a crashed or discarded episode still
leaves a record.

### H4 — The harness timeout produced a receipt shape the classifier misread as a product turn error

The outer deadline emitted no `timedOut` and no `lifecycle`, so a wall-clock overrun was published as
`DSH_CODEX_TURN_ERROR` with `timed_out: false`, and the driver's stdout was discarded.

**Fixed.** The timeout branch now sets `timedOut: True` and
`inconclusiveInfra: D4_DRIVER_WALL_CLOCK_EXCEEDED`, and preserves the stdout/stderr digests.

### H5 — A driver crash or non-JSON stdout became a product FAIL claiming the provider was entered

`run_driver_observed` never returned `None`, so the `INCONCLUSIVE`-on-no-receipt branch was unreachable in
production and `dsh_provider_entered` was set unconditionally.

**Fixed.** Synthesized receipts carry `inconclusiveInfra: D4_DRIVER_PRODUCED_NO_PARSEABLE_RECEIPT`, and
`dsh_provider_entered` is now true only when the receipt carries the driver's own D4 route marker.

### H6 — `communicate()` could block forever on an inherited stderr pipe

DSH spawns the Codex child `detached` with `stderr: 'inherit'`, so a surviving MCP grandchild can hold the
pipe open; the timeout path's second `communicate()` had no timeout.

**Fixed.** The driver is launched with `start_new_session=True`, the timeout path terminates the whole
process group (SIGTERM then SIGKILL), the second drain is bounded at 15 s, and the streams are closed if it
still does not return.

### H7 — D4 requests no approval/sandbox policy and observed none, so a FAIL was not attributable

D1–D3 sent `approvalPolicy=never` + `workspaceWrite` and verified the echoed *effective* policy. DSH's
provider sends only `{cwd, ephemeral}` and answers approval requests with cancel/decline. The disposable
`/tmp` workspace is not in Profile A's trusted-projects list, so an approval-driven non-write could have
been misattributed to DSH, and two of the nine declared mechanisms were unreachable.

**Fixed.** The runner records the effective profile — `config.toml` digest before and after, resolved model,
configured MCP server names, `auth.json` key *names* and `auth_mode`, and whether the workspace is a trusted
project — and `DSH_EFFECTIVE_CONFIG_DIVERGENCE` is now reachable: an untrusted workspace with no write, or
any parent-LLM activity, classifies as configuration divergence rather than as an unexplained product error.
Product config mutation is detected by comparing the `config.toml` digest across the run.

## MEDIUM (recorded, not separately fixed)

- **M1 — Uncontrolled profile variance.** The one episode runs against a `CODEX_HOME` with 11 MCP servers and
  `model = gpt-5.6-luna`. Cold `npx` caches could consume the turn budget and land in the product-FAIL bucket.
  *Partly mitigated by the H7 fix:* the model, MCP server names, and config digest are now recorded, so the
  confound is visible in the record. The profile itself was deliberately not modified — the phase forbids
  product config changes, and Profile A is the subject under test.
- **M2 — "Subscription-backed" was asserted, never observed.** *Mitigated by the H7 fix:* `auth_mode` and the
  `OPENAI_API_KEY` slot state are now read (names and mode only, never values) and recorded as
  `subscription_backed`. Observed: `auth_mode = chatgpt`, API-key slot empty.
- **M3 — `processes[{signal: SIGTERM}]` and `parentLlm*` are hardcoded literals in the frozen driver.** The
  driver is inherited from PR #135 and must not be edited in this phase, so the literals remain. The H2 fix
  removes the danger for *this* phase's verdict by gating on those fields rather than trusting them, but a
  future phase reusing the receipt should not read `processes[].signal` as a measurement.

## LOW (recorded, not fixed)

- **L1 — `phase_verdict` labels post-materialization infra loss as `PINNED_DSH_MATERIALIZATION_BLOCKED`.**
  The allowed-verdict vocabulary is fixed at five by the phase contract, so no new verdict was added; the
  precise reason is carried in `classification.reason`.
- **L2 — Sampler snapshot race.** *Incidentally fixed while addressing H6:* the sampler now guards
  `observed` with a lock, exposes `snapshot()`, and performs a final sweep after stopping.
- **L3 — Three tests named invariants they could not fail.** Behavioural replacements were added for the
  ones covering CRITICAL/HIGH surface (artifact drift, receipt integrity, the consumed-episode guard,
  the wall-clock and unparseable-receipt shapes, and trusted/untrusted workspace classification). The
  remaining substring assertions are retained as cheap tripwires, not as the primary evidence.

## Outcome

- `OPEN_CRITICAL = 0`
- `OPEN_HIGH = 0`
- Targeted rereview: NOT USED. The contract permits "at most one"; all seven HIGH and the one CRITICAL were
  fixed with behavioural test coverage, and the phase proceeded to freeze without spending a second review.
