# Hostile review — Codex app-server write-path diagnostic V0

Reviews performed: **1** (plus **1** targeted re-review, because Critical/High
findings required repair).

Review class: `IN_PHASE_ADVERSARIAL_REVIEW`. This was an adversarial pass over
the frozen candidate conducted inside the phase, not a separately spawned
reviewer product. It is recorded that way deliberately rather than claimed as
external independence.

Scope reviewed:

- `qntylab/subscription_backed_codex_app_server_write_path_diagnostic_v0.py`
- `tests/test_subscription_backed_codex_app_server_write_path_diagnostic_v0.py`
- `tests/fixtures/fake_codex_app_server_v0.py`
- `qntylab_native_codex_app_server_bridge_v0.py`
- `pinned_dsh_codex_route_driver_v0.mjs`
- `run_diagnostic_ladder_v0.py`

## Findings

| # | Severity | Attack vector | Finding | Disposition |
|---|----------|---------------|---------|-------------|
| 1 | HIGH | timeout mislabeled as write denial | `classify_route` tested the auth-text inference *before* the observed timeout, so a stalled turn whose error text contained `login`/`401` would have been reported `AUTH_FAILURE` instead of `TURN_TIMEOUT`. A textual inference could outrank a directly observed terminal fact. | FIXED — timeout branch moved ahead of the inference; the inference is still retained as a recorded flag. |
| 2 | HIGH | declared parity mistaken for effective parity | The route receipt carried `declared_policy` and `effective_policy` side by side but never compared them, so a silent downgrade (e.g. effective `readOnly` under a declared `workspace-write`) would have been recorded without ever being flagged. This is the H2 hypothesis the phase exists to test. | FIXED — added computed `policy_parity` with `codex_home_matches`, `cwd_matches`, `approval_policy_matches`, `sandbox_class_matches`, `writable_root_covers_workspace`, `all_match`. |
| 3 | HIGH | sandbox override silently omitted | `declared_policy.thread_start_keys` / `turn_start_keys` were **hand-maintained literal lists**. Had the request dictionaries drifted, the receipt would have asserted fields that were never sent — evidence fabrication. | FIXED — both lists are now derived from the parameter dictionaries actually sent. |
| 4 | HIGH | write attempt inferred too loosely | `_write_attempt_observed` counted *any* `commandExecution` item as a write attempt, so a read-only `ls` would have produced `WRITE_ATTEMPT_OBSERVED` rather than `COMPLETED_NO_WRITE`, blurring two of the distinctions the phase must keep separate. | FIXED — only a `fileChange` item constitutes a write attempt; command execution is recorded separately as `command_execution_observed`. |
| 5 | HIGH | verdict fails open | `first_divergence` returned `NONE` when ladder stages were missing or skipped. `NONE` asserts *all write paths pass*, so an incomplete ladder could have produced the strongest possible claim. | FIXED — `NONE` now requires every stage to be explicitly `PASS`; anything else degrades to `UNKNOWN`. |
| 6 | MEDIUM | evidence loss on infrastructure failure | A child that could not be spawned raised out of `run_app_server_route`, destroying the receipt and forcing `INCONCLUSIVE_INFRA` where a classified `STARTUP_FAILURE` was available. | FIXED — startup failure is captured and returns a classified receipt with `startup_error`. |
| 7 | MEDIUM | raw transcript leaks credentials | Recorded product error text was truncated but not scrubbed. | FIXED — `_scrub` redacts credential-shaped runs before any product text is recorded. |
| 8 | LOW | wrong terminal notification | `turn_terminal()` matches `turn/completed` by method name without also matching the thread digest. Each route owns exactly one process and one ephemeral thread, so no cross-thread confusion is reachable. | ACCEPTED — documented, not changed. |

## Attack vectors checked and found already sound

- **Approval event silently swallowed** — every server request is recorded, answered, and counted; unknown methods receive an explicit `-32601` and are listed in `unsupported_server_requests`.
- **Bridge not frozen** — the native bridge and DSH driver are committed source with SHA256s in `prelive_manifest.json`; no `/tmp` helper carries implementation identity. The predecessor's ephemeral helper bytes are unrecoverable and this is stated rather than papered over.
- **Wrong CODEX_HOME / cwd / writable root** — all three are now read back from `initialize` and `thread/start` responses and compared (finding 2).
- **Subprocess pipe deadlock** — dedicated reader threads drain stdout and stderr; stderr is never retained, only hashed and counted.
- **Filesystem mutation inferred from prose** — `route_passed` depends solely on fixture bytes plus `changed_paths == ["fixture.txt"]`; the `prose_lies_about_write` scenario proves prose cannot manufacture a pass, and assistant text is stored only as a digest.
- **DSH before the native boundary is localized** — the runner marks D3/D4 `NOT_RUN_DUE_TO_EARLIER_DIVERGENCE` and returns as soon as D2 fails.
- **Hidden API credential use** — the four pay-per-token keys are removed without being read, presence is recorded as booleans, and the DSH driver independently fails closed if any is present.
- **Retries create multiple observations** — there is no retry path anywhere; each stage runs exactly once.
- **PR #134 / V1 mutation** — the work is additive-only on a new branch stacked on `e24b540`; the 69 predecessor plumbing and V1 permanence tests pass unchanged.

## Outcome

```text
CRITICAL = 0
HIGH     = 5   (all fixed)
MEDIUM   = 2   (both fixed; each corrupted evidence or created leak risk)
LOW      = 1   (accepted, documented)
TARGETED_REREVIEW_USED = YES
OPEN_CRITICAL = 0
OPEN_HIGH     = 0
```

The targeted re-review re-read every changed region: classification ordering,
parity computation and its receipt wiring, derived request keys, the write-attempt
rule, the strict divergence rule, startup capture, and scrubbing. No new
Critical/High findings. Deterministic suite: 39 passed.
