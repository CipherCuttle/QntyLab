# JH01_V1_PRE_ORIGIN_PRODUCTION_PATH_REPAIR_V0 — Independent Hostile Review V0

- Reviewer: independent hostile review (read-only; no code modified)
- Phase: JH01_V1_PRE_ORIGIN_PRODUCTION_PATH_REPAIR_V0
- Branch under review: `ops/jh01-v1-pre-origin-production-path-repair-v0`
- Review method limitation: this review session had no command-execution tool
  available. All evidence below is from direct file inspection with line
  citations. Frozen-hash verification therefore relies on runtime assertions
  (Proofs 17/18) and the embedded constant in the frozen wrapper, not on an
  independent `sha256sum` run; a CI re-run of the E2E suite is recommended to
  close that gap.

## Scope reviewed

| Artifact | Citation |
|---|---|
| Source adapter | [`qntylab/jh01_v1_prospective_source_adapter_v0.py`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py) (whole file, 243 lines) |
| Production caller | [`qntylab/jh01_v1_prospective_production_caller_v0.py`](../../qntylab/jh01_v1_prospective_production_caller_v0.py) (whole file, 239 lines) |
| Fixtures | [`tests/_jh01_v1_prospective_fixtures.py`](../../tests/_jh01_v1_prospective_fixtures.py) |
| Adapter unit tests | [`tests/test_jh01_v1_prospective_source_adapter_v0.py`](../../tests/test_jh01_v1_prospective_source_adapter_v0.py) |
| Caller unit tests | [`tests/test_jh01_v1_prospective_production_caller_v0.py`](../../tests/test_jh01_v1_prospective_production_caller_v0.py) |
| E2E proofs | [`tests/test_jh01_v1_pre_origin_e2e_proof_v0.py`](../../tests/test_jh01_v1_pre_origin_e2e_proof_v0.py) |
| Systemd service | [`ops/systemd/user/jh01-v1-prospective-record.service`](../../ops/systemd/user/jh01-v1-prospective-record.service) |
| Systemd timer | [`ops/systemd/user/jh01-v1-prospective-record.timer`](../../ops/systemd/user/jh01-v1-prospective-record.timer) |
| Scheduler README | [`ops/systemd/user/README.md`](../../ops/systemd/user/README.md) |
| Frozen recorder (read-only reference) | [`qntylab/jh01_v1_prospective_recorder_implementation_v0.py:176-233`](../../qntylab/jh01_v1_prospective_recorder_implementation_v0.py:176) |
| Frozen operation wrapper (read-only reference) | [`qntylab/jh01_v1_prospective_operation_v0.py:364-387`](../../qntylab/jh01_v1_prospective_operation_v0.py:364) |
| Authority artifact | [`experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/jh01_v1_pre_origin_source_authority_resolution_v0.json`](../../experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/jh01_v1_pre_origin_source_authority_resolution_v0.json) |

## Frozen-invariant verification

- Recorder digest `4f5e1791…95ec1a`: embedded as
  `EXPECTED_RECORDER_SOURCE_DIGEST` at
  [`qntylab/jh01_v1_prospective_operation_v0.py:39`](../../qntylab/jh01_v1_prospective_operation_v0.py:39)
  and enforced against file bytes at runtime by
  [`_validate_recorder_lineage`](../../qntylab/jh01_v1_prospective_operation_v0.py:143)
  plus Proof 17 ([`test_jh01_v1_pre_origin_e2e_proof_v0.py:473-477`](../../tests/test_jh01_v1_pre_origin_e2e_proof_v0.py:473)).
- Wrapper digest `1176037f…67c41`: asserted at runtime by Proof 18
  ([`test_jh01_v1_pre_origin_e2e_proof_v0.py:480-484`](../../tests/test_jh01_v1_pre_origin_e2e_proof_v0.py:480))
  and preserved in the authority artifact
  (`preserved_identities.wrapper_implementation_identity`, authority JSON line 25).
- Authority artifact confirms `UNBOUND_OPERATIONAL_ADAPTER` scope,
  `RAW_PROVIDER_RESPONSE_PLUS_DETERMINISTIC_DIGEST_SUFFICIENT` provenance for
  REST, and `authorized_next_phase` equal to this phase (authority JSON lines
  9-13). No drift detected.
- Campaign firewall: all tests bind state to pytest `tmp_path`; the firewall
  guard scans the four new test modules for the real state dirname
  ([`test_jh01_v1_pre_origin_e2e_proof_v0.py:491-505`](../../tests/test_jh01_v1_pre_origin_e2e_proof_v0.py:491)).
  No test constructs the real state dir. No real acquisition/publication path
  exists in this changeset outside `--record-due`.

## Per-checklist-item verdicts

### 1. Boundary math vs frozen recorder semantics — PASS (with one note)

- Logical-close mapping: adapter enforces `open_ms == L − 1h`,
  `close_ms == L − 1ms`, `L == close_time + 1ms`
  ([`source_adapter_v0.py:96-102`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:96)),
  exactly matching frozen re-validation at
  [`recorder_implementation_v0.py:189`](../../qntylab/jh01_v1_prospective_recorder_implementation_v0.py:189).
- Origin boundary: rows with `logical_close > origin` are rejected, never
  dropped ([`source_adapter_v0.py:103-104`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:103));
  frozen validator additionally requires last close == origin and first ==
  first_required_close per symbol
  ([`recorder_implementation_v0.py:203-204`](../../qntylab/jh01_v1_prospective_recorder_implementation_v0.py:203)).
- Open/current bar: a row for `ORIGIN + 1h` is rejected (Proof 2 / unit twin).
- Month-boundary off-by-one: the August monthly archive's final logical close
  is 2026-09-01T00:00Z (open 2026-08-31T23:00Z). The adapter adds it to
  `covered`, so the REST tail starts at open 2026-09-01T00:00Z for close
  2026-09-01T01:00Z
  ([`source_adapter_v0.py:227-230`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:227));
  the overlapping September-1T00 REST row is suppressed by archive precedence
  ([`source_adapter_v0.py:232-233`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:232)).
  Proof 1 asserts exact close-set equality and duplicate-freeness through the
  frozen validator. No off-by-one found.
- Note (L4-adjacent): `_hour_ms` uses float `timestamp()*1000`; safe at
  current epoch magnitudes (float64 exact integers up to 2^53).

### 2. REST safety enforcement — PASS on contract, FAIL on internal consistency (H2)

Enforced correctly: exact 20-symbol panel via frozen constants
([`source_adapter_v0.py:46-48,87-88`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:46));
interval pinned to `"1h"` at request construction and row level
([`source_adapter_v0.py:32-33,134-135,96-97`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:134));
single USD-M endpoint constant, no venue/provider fallback anywhere;
deterministic boundaries from `request_bounds`
([`source_adapter_v0.py:60-68`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:60));
no imputation/dropping (every anomaly raises); raw 12-field tuple preserved on
the Bar ([`source_adapter_v0.py:109`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:109)),
sufficient for `raw_row_sha256` and full manifest regeneration (Proof 9,
including byte-sensitivity of the digest).
Defect: see H2 — the documented 404→`None` branch of the archive provider is
unreachable with the default opener.

### 3. Archive/REST composition — PARTIAL FAIL (H2, M3, M4)

- Duplicate suppression is correct and asymmetric (archive precedence):
  [`source_adapter_v0.py:214-234`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:214);
  intra-source duplicates would be caught by the frozen validator's
  duplicate-logical-close check
  ([`recorder_implementation_v0.py:195-197`](../../qntylab/jh01_v1_prospective_recorder_implementation_v0.py:195)).
- Absent monthly archive: intended behavior is provider returns `None` → hole
  falls to REST → if REST cannot fill it, `validate_bars` fails closed. In
  production the `None` path is dead code (H2): `urlopen` raises `HTTPError`
  on 404, which is caught as a transport failure
  ([`source_adapter_v0.py:174-186`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:174)).
  Net production behavior is fail-closed block (safe direction), but the
  designed resilience is non-functional and untested.
- Cache safety: there is no cache. Every attempt re-downloads all ~13 monthly
  archives × 20 symbols sequentially. This interacts badly with the scheduler
  window (see H1).

### 4. Caller composition — PASS

- `--record-due` owns no recorder logic and no second forecast implementation:
  bars come from the adapter, artifact assembly from the frozen wrapper's
  `_operational_artifact` using frozen `compute_models`
  ([`production_caller_v0.py:165-177`](../../qntylab/jh01_v1_prospective_production_caller_v0.py:165),
  [`operation_v0.py:390-426`](../../qntylab/jh01_v1_prospective_operation_v0.py:390)).
  No scientific metrics are computed anywhere in the caller.
- `--status`/`--dry-readiness` write-freedom: no ledger append, no retention
  package, no release occurs (Proof 12 proves zero ledger writes for
  record-due pre-origin; the dry-readiness test proves no `retention/` dir).
  However both modes do perform two non-campaign writes (state-dir `mkdir`
  and `git fetch` ref updates) — see M2.
- NOT_DUE fail-closed before 2026-09-15T00:00:00Z: guaranteed.
  `due_state` returns `NOT_DUE` when `now < origin`
  ([`operation_v0.py:383-384`](../../qntylab/jh01_v1_prospective_operation_v0.py:383))
  with `FIRST_LIVE_ORIGIN = datetime(2026, 9, 15, tzinfo=UTC)`
  ([`recorder_implementation_v0.py:36`](../../qntylab/jh01_v1_prospective_recorder_implementation_v0.py:36));
  the caller maps NOT_DUE to exit 3 before any collection
  ([`production_caller_v0.py:159-161,227-228`](../../qntylab/jh01_v1_prospective_production_caller_v0.py:159)).
  Proofs 12 and the caller-unit NOT_DUE tests assert zero REST-seam
  consultation and zero ledger writes.

### 5. target_commit pinning — PASS with one race gap (M1)

- Only derived values are used: `rev-parse origin/master` after an explicit
  `fetch origin`, full-SHA regex gate, HEAD equality, tracked-worktree
  cleanliness ([`production_caller_v0.py:63-82`](../../qntylab/jh01_v1_prospective_production_caller_v0.py:63)).
  Branch names, abbreviated SHAs, and caller-supplied SHAs are structurally
  impossible (no CLI parameter exists for target_commit; tests prove rejection
  of abbreviations and mismatched HEAD).
- Publication-time enforcement: frozen transport readback rejects a remote
  release pinned to a different commit (Proof 10) and ambiguous/digest-
  conflicting remote states fail closed with no ledger write (Proof 15).
- Gap: the preflight runs once at
  [`production_caller_v0.py:156`](../../qntylab/jh01_v1_prospective_production_caller_v0.py:156);
  nothing re-verifies HEAD/worktree after materialization and before
  publication. A mid-run worktree mutation yields a receipt pinning a commit
  whose tree no longer matches the executing code (M1).

### 6. Systemd units — PARTIAL FAIL (H1, M5; otherwise sound)

- ExecStart correctness: `--now "$(date -u +%Y-%m-%dT%H:00:00Z)"` is
  hour-aligned UTC. Relative to the frozen window `[t, t+1h)` with daily
  midnight origins, truncation of any trigger in 00:05–00:50 yields exactly
  `t`, strictly inside the window; truncation can only move `now` earlier
  within the same hour, never out of `[t, t+1h)`. Correct. A trigger delayed
  past 01:00 computes `--now=01:00` and writes terminal `ORIGIN_BLOCKED` —
  identical outcome to the next-day path under frozen semantics (L1 note).
- Secrets: none in units; credential discovery inherited; journal prints
  single-line JSON receipts without tokens
  ([`jh01-v1-prospective-record.service:7-11`](../../ops/systemd/user/jh01-v1-prospective-record.service:7)).
- Absolute paths throughout; `Persistent=false`, `AccuracySec=1s`,
  `RandomizedDelaySec=0` all present
  ([`jh01-v1-prospective-record.timer:24-30`](../../ops/systemd/user/jh01-v1-prospective-record.timer:24)).
- Reactivation: impossible. The caller CLI exposes only
  status/dry-readiness/record-due; activation exists solely in the frozen
  operation module API/CLI, which the unit never invokes.
- `SuccessExitStatus=3` masking: currently safe — `--record-due` returns 3
  only on NOT_DUE ([`production_caller_v0.py:227-228`](../../qntylab/jh01_v1_prospective_production_caller_v0.py:227));
  blocked paths return 2 and remain visible failures. Risk noted for future
  exit-3 paths (L3).
- Defects: H1 (start-timeout/window-budget non-determinism) and M5
  (`go` resolution for offline reverify not pinned in ExecStart).

### 7. Test suite honesty — MOSTLY HONEST (M3, M4)

- The 18 proofs are substantive: Proof 1 asserts exact close-set equality per
  symbol through the frozen validator; Proofs 2–8 assert specific rejection
  reasons; Proof 9 proves byte-sensitivity of the manifest digest; Proofs
  10–16 exercise real fail-closed branches with negative ledger-write
  assertions; Proofs 17–18 are runtime freeze checks. No tautological tests
  found.
- Overclaim: `test_absent_archive_month_fails_closed_instead_of_silent_acceptance`
  ([`test_jh01_v1_prospective_source_adapter_v0.py:137-139`](../../tests/test_jh01_v1_prospective_source_adapter_v0.py:137))
  passes only because the synthetic REST tail serves no March 2026 rows, so
  `validate_bars` sees a gap. It does not exercise the production 404 path
  (which cannot return `None`, see H2) and does not prove the claimed policy
  (M3).
- Coverage hole: `default_fetch_klines` and `default_archive_provider` — the
  only real-network code in the changeset, including the pagination loop and
  error mapping — have zero test coverage (M4).
- Firewall guard effectiveness: adequate for this suite (string scan of the
  four new modules + explicit tmp_path binding everywhere), though it cannot
  guard future modules.

### 8. Overall fail-closed posture — SOUND, two operational risks

Ways to silently write a wrong origin record: none found. Every wrong-input
path terminates in a raised exception before ledger append; ledger appends
occur only after transport publish + attestation + retention + offline
reverify inside the frozen wrapper
([`operation_v0.py:553-583`](../../qntylab/jh01_v1_prospective_operation_v0.py:553)).
Skipped-due-origin-without-evidence: not possible — a missed window always
terminates in an appended `ORIGIN_BLOCKED` event
([`operation_v0.py:544-548`](../../qntylab/jh01_v1_prospective_operation_v0.py:544)),
so skips always leave evidence. Residual risks are operational availability
(H1, H2, M5), not integrity.

## Findings

Severity counts: **Critical 0 · High 2 · Medium 5 · Low 4**

### H1 — Scheduler window budget is unverifiable and start-timeout behavior is unpinned; first live origin can be terminally missed — High

Evidence: every origin requires full re-materialization from
`first_required_close=2025-08-15T00:00:00Z` (frozen validator boundary check,
[`recorder_implementation_v0.py:203`](../../qntylab/jh01_v1_prospective_recorder_implementation_v0.py:203)),
i.e. ~13 monthly archives × 20 symbols = ~260 sequential HTTPS downloads plus
checksum fetches, each with `timeout=120.0`
([`source_adapter_v0.py:162-187`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:162)),
with no caching between attempts. The DUE window is one hour
([`operation_v0.py:385-387`](../../qntylab/jh01_v1_prospective_operation_v0.py:385))
with four attempts at 00:05/00:20/00:35/00:50. The service sets no explicit
`TimeoutStartSec=` ([`jh01-v1-prospective-record.service:30-37`](../../ops/systemd/user/jh01-v1-prospective-record.service:30));
whether a long-running oneshot inherits `DefaultTimeoutStartSec` (90 s) or
runs unbounded is version/build-dependent, and no timed rehearsal evidence
exists in the phase. If each attempt is killed early (or latency is
pathological), no attempt ever completes inside a window and the campaign
terminally blocks on 2026-09-15 with `ORIGIN_BLOCKED` — fail-closed, but the
phase objective (a working production path) is defeated.
Minimal fix: set an explicit `TimeoutStartSec=` sized by a measured rehearsal
(e.g. 10–15 min) in the unit; add a rehearsal receipt measuring end-to-end
materialization wall time; consider an attempt-local archive cache seam
(bytes+checksum memoization) so retries resume instead of restarting.

### H2 — Documented 404→None archive-absent branch is unreachable in production; designed resilience is dead code — High

Evidence: `default_archive_provider` documents "Returns ``None`` when the
archive object is absent (404)"
([`source_adapter_v0.py:170-172`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:170))
and contains `if response.status == 404: return None`
([`source_adapter_v0.py:176-177`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:176)).
With the default `opener=urlopen`, a 404 raises `HTTPError` before any
response object is returned; `HTTPError` is caught at
[`source_adapter_v0.py:185-186`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:185)
and converted to `SourceAdapterBlocked("archive transport failure")`. The
`None` path is exercised only by synthetic fakes. Consequence: a single
absent monthly archive (plausible across a 20-symbol × 13-month grid) hard-
blocks every attempt that day and terminally blocks the origin the next day,
instead of the designed graceful REST-tail recovery. Direction is fail-closed
(no wrong write), but the composition contract is not what production
executes, and the checklist expectation ("hole must fail closed via
validate_bars") is met only accidentally, via a different mechanism than
designed/tested.
Minimal fix: catch `HTTPError` and map `code == 404` to `return None` inside
`default_archive_provider`; add a fake-opener unit test exercising the real
function's 404 mapping and its transport-error fail-closed siblings.

### M1 — Preflight→publication race: target_commit pinned once, never re-verified before publication — Medium

Evidence: `canonical_target_commit` runs once at
[`production_caller_v0.py:156`](../../qntylab/jh01_v1_prospective_production_caller_v0.py:156);
materialization and publication follow with no recheck. A tracked-worktree
mutation between preflight and publication produces a receipt pinning a clean
commit whose tree no longer matches the executing code. Frozen transport
readback enforces remote consistency, not local-tree consistency.
Minimal fix: immediately before `operation_obj.record_due(...)`, re-run
`canonical_target_commit` and require the result to equal the pinned value;
block otherwise.

### M2 — `--status`/`--dry-readiness` are not provably write-free — Medium

Evidence: both construct `operation.Operation(root, state_dir)`
([`production_caller_v0.py:96,119`](../../qntylab/jh01_v1_prospective_production_caller_v0.py:96));
`OperationLedger.__init__` executes
`self.root.mkdir(parents=True, exist_ok=True)`
([`operation_v0.py:288`](../../qntylab/jh01_v1_prospective_operation_v0.py:288)),
creating the real state-dir hierarchy under `$XDG_STATE_HOME` when invoked
with defaults. Both modes also run `git fetch origin`
([`production_caller_v0.py:71`](../../qntylab/jh01_v1_prospective_production_caller_v0.py:71)),
mutating remote-tracking refs in `.git`. No ledger events or publications
occur, but the README/service comments' "read-only" claim is stronger than
reality, and directory creation slightly erodes the "real state dir untouched"
firewall phrasing.
Minimal fix: in read-only modes, pass a non-creating ledger probe (guard with
`path.exists()` before constructing `Operation`) or document the mkdir/fetch
side effects explicitly; optionally add `--no-fetch` semantics for `--status`.

### M3 — Misleading absent-archive test (overclaimed proof) — Medium

Evidence: [`test_jh01_v1_prospective_source_adapter_v0.py:137-139`](../../tests/test_jh01_v1_prospective_source_adapter_v0.py:137)
claims "fails closed instead of silent acceptance" but passes because the
synthetic REST tail covers only September 2026; the March 2026 hole becomes a
generic `validate_bars` source gap. It neither exercises the production 404
mapping (dead, H2) nor distinguishes the designed None→REST→gap chain from an
ordinary missing-data failure.
Minimal fix: rename/reframe the test to assert the actual mechanism, and add a
test driving `default_archive_provider` with a fake opener returning 404.

### M4 — Zero coverage of the real network functions (pagination, error mapping) — Medium

Evidence: `default_fetch_klines`
([`source_adapter_v0.py:123-159`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:123))
contains the only pagination logic in the changeset (cursor advance, 1000-row
pages, no-progress break) and `default_archive_provider` the checksum
retrieval; neither is imported by any test. A pagination defect (e.g. skipped
or duplicated page boundary) would surface only in production on the first
live origin. The `response.status != 200` branches are dead code with
`urlopen` (same mechanism as H2) and equally untested.
Minimal fix: add fake-opener unit tests covering: multi-page pagination
boundary, short-page termination, HTTPError/URLError/timeout mapping to
`SourceAdapterBlocked`, malformed-JSON mapping, and non-array payload.

### M5 — Offline sigstore reverify depends on unresolved `go` in the service context — Medium

Evidence: `record_due` defaults `go_binary=Path("go")`
([`production_caller_v0.py:153`](../../qntylab/jh01_v1_prospective_production_caller_v0.py:153));
ExecStart does not pass `--go-binary`
([`jh01-v1-prospective-record.service:33`](../../ops/systemd/user/jh01-v1-prospective-record.service:33));
README acknowledges go was absent at creation time
([`ops/systemd/user/README.md:104-109`](../../ops/systemd/user/README.md:104)).
A systemd user session typically has a minimal PATH; if `go` is not resolvable
at record time, every attempt exits 2 and the origin terminally blocks.
Minimal fix: resolve the absolute go path at install time and bake
`--go-binary /absolute/path` into ExecStart, or fail fast with a pre-install
check in the README install procedure.

### L1 — Delayed trigger past 01:00 writes terminal ORIGIN_BLOCKED via hour-aligned --now — Low

Evidence: hour-aligned truncation maps a delayed 00:50 trigger executing at
01:00:30 to `--now=01:00`, which lands in `BLOCKED_MISSED_WINDOW`
([`operation_v0.py:385-387`](../../qntylab/jh01_v1_prospective_operation_v0.py:385)).
The terminal outcome matches frozen semantics regardless (next-day evaluation
blocks the same origin), so no repair required; recorded for awareness.

### L2 — Hardcoded user-absolute paths in units and Documentation= — Low

Evidence: `/home/swirky/DevHub/repos/QntyLab` hardcoded in WorkingDirectory,
ExecStart, and Documentation=
([`jh01-v1-prospective-record.service:28,32-33`](../../ops/systemd/user/jh01-v1-prospective-record.service:28)).
Acceptable for a personal user unit; blocks portability and silently breaks if
the repo moves. Recorded, no repair required this phase.

### L3 — SuccessExitStatus=3 is a standing mask for any future exit-3 semantic — Low

Evidence: [`jh01-v1-prospective-record.service:34`](../../ops/systemd/user/jh01-v1-prospective-record.service:34).
Today exit 3 is emitted only for NOT_DUE
([`production_caller_v0.py:219,227-228`](../../qntylab/jh01_v1_prospective_production_caller_v0.py:219)).
If a later change adds another exit-3 meaning, failures would be silenced at
the unit level while remaining visible only in journal payload. Recorded;
suggest a comment-pinned invariant in the caller ("exit 3 means NOT_DUE only").

### L4 — Host-clock trust for --now; large forward skew could record an origin early — Low

Evidence: `--now` derives solely from host `date -u`
([`jh01-v1-prospective-record.service:33`](../../ops/systemd/user/jh01-v1-prospective-record.service:33));
`due_state` compares host time to frozen origins
([`operation_v0.py:383-387`](../../qntylab/jh01_v1_prospective_operation_v0.py:383)).
A severely mis-configured clock (jumping past an origin) would let the system
publish before the true origin instant, breaking the prospective claim while
all integrity checks still pass. Frozen semantics inherently rely on the
scheduler clock; recorded as accepted residual risk. Optional hardening:
refuse `--now` more than N minutes ahead of an independent lower bound, or
cross-check against the latest archive month's coverage.

## Checklist verdict summary

| # | Item | Verdict |
|---|---|---|
| 1 | Boundary math vs frozen semantics | PASS |
| 2 | REST safety enforcement | PASS on contract; H2 internal-consistency defect |
| 3 | Archive/REST composition | PARTIAL FAIL (H2; cache absence folded into H1) |
| 4 | Caller composition | PASS (M2 on write-free claim) |
| 5 | target_commit pinning | PASS (M1 race gap) |
| 6 | Systemd units | PARTIAL FAIL (H1, M5) |
| 7 | Test suite honesty | SUBSTANTIAL (M3, M4) |
| 8 | Fail-closed posture overall | SOUND (operational availability risks remain) |

## Overall verdict

HOSTILE_REVIEW = FAIL_WITH_CRITICAL_HIGH

(0 Critical, 2 High: H1 scheduler window-budget/start-timeout risk of
terminal first-origin miss; H2 unreachable 404→None archive-absent branch
defeating designed composition resilience. Both are in-phase repairable
without touching frozen bytes.)

---

# TARGETED REREVIEW ADDENDUM (H1/H2)

- Rereviewer: targeted rereview of the H1/H2 repairs only (read-only except
  this addendum; no code modified)
- Branch: `ops/jh01-v1-pre-origin-production-path-repair-v0`
- Method limitation: this rereview session had no command-execution tool
  available. `sha256sum`, `git diff/log`, and `python -m pytest` were NOT run.
  All evidence below is from direct file inspection with line citations. The
  reported suite result (54 passed across
  [`tests/test_jh01_v1_pre_origin_e2e_proof_v0.py`](../../tests/test_jh01_v1_pre_origin_e2e_proof_v0.py),
  [`tests/test_jh01_v1_prospective_source_adapter_v0.py`](../../tests/test_jh01_v1_prospective_source_adapter_v0.py),
  [`tests/test_jh01_v1_prospective_production_caller_v0.py`](../../tests/test_jh01_v1_prospective_production_caller_v0.py))
  is taken as the repairer's claim, consistent with the limitation disclosed
  in the original review header.

## Checklist item verdicts

### 1. H1 timeout/window coherence — PASS

- [`jh01-v1-prospective-record.service:40`](../../ops/systemd/user/jh01-v1-prospective-record.service:40)
  pins `TimeoutStartSec=840` explicitly; the version-dependent
  `DefaultTimeoutStartSec` inheritance ambiguity cited by H1 is eliminated.
- Coherence with the four-attempt schedule: consecutive triggers are 15 min
  (900 s) apart; 840 s < 900 s guarantees a running attempt is always killed
  before the next attempt slot, so each attempt keeps its own bounded budget
  and attempts can never overlap (systemd additionally refuses concurrent
  starts of the same unit).
- Window `[t, t+1h)` coherence: `--now` is computed once at trigger time and
  hour-aligned ([`jh01-v1-prospective-record.service:42`](../../ops/systemd/user/jh01-v1-prospective-record.service:42));
  `due_state` evaluates against `--now`, not completion time, so an attempt
  started at 00:50 that runs to 01:04 still evaluates origin `t = 00:00`
  correctly. A kill at 840 s terminates before any publication attempt can
  straddle the next slot; a mid-run kill leaves at most orphaned cache files
  (see item 2), never a partial ledger event (ledger appends occur only inside
  the frozen wrapper after full publication).
- Residual (Low, operational): the original H1 minimal fix also requested a
  timed rehearsal receipt measuring end-to-end wall time; none exists. The
  840 s bound is argued analytically (unit comment lines 32-39,
  [`ops/systemd/user/README.md:56-67`](../../ops/systemd/user/README.md:56)),
  and the digest-verified cache makes warm attempts far cheaper than cold.
  Not a Critical/High: worst case remains fail-closed `ORIGIN_BLOCKED`.

### 2. Digest-verified cache safety per authority clause — PASS

- Implementation: [`cached_archive_provider`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:199)
  ([`source_adapter_v0.py:199-237`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:199)).
- Reuse gate: an entry is reused only when BOTH `{key}.zip` and
  `{key}.CHECKSUM` exist AND the stored CHECKSUM's first token is 64 hex chars
  AND equals the SHA-256 of the cached bytes
  ([`source_adapter_v0.py:216-221`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:216));
  otherwise both files are discarded and a fresh authenticated download occurs
  ([`source_adapter_v0.py:222-225`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:222)).
  This satisfies "content-addressed or digest-verified before reuse".
- Persistence gate: downloaded bytes are written to cache only after the same
  digest verification ([`source_adapter_v0.py:229-232`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:229));
  digest-unverifiable downloads are returned unmodified and never persisted
  ([`source_adapter_v0.py:233-235`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:233)).
  Such bytes can reach the frozen archive admission
  (`bars_from_authenticated_archive`) exactly as in the uncached path, where
  the frozen helper re-verifies the published checksum and fails closed — no
  new path to `validate_bars`/`record_due` is created.
- Negative caching / staleness: absent months (404 → `None`) are NOT cached;
  every attempt re-probes ([`source_adapter_v0.py:226-227`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:226),
  asserted by [`test_jh01_v1_prospective_source_adapter_v0.py:291-304`](../../tests/test_jh01_v1_prospective_source_adapter_v0.py:291)).
  Monthly archives are immutable, so a self-consistent (bytes+checksum) entry
  cannot go stale relative to its URL.
- Location/traversal: the cache key is `sha256(url)` hex
  ([`source_adapter_v0.py:212-215`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:212)) —
  fixed-length hex filenames, no path-traversal or user-controlled component.
  The production caller roots the cache inside the campaign state dir,
  `<state-dir>/jh01_v1_source_archive_cache_v0/`
  ([`production_caller_v0.py:165-170`](../../qntylab/jh01_v1_prospective_production_caller_v0.py:165)),
  the same trust domain as the ledger. `--dry-readiness` does NOT wire the
  cache ([`production_caller_v0.py:126-131`](../../qntylab/jh01_v1_prospective_production_caller_v0.py:126)),
  preserving its write-free posture.
- Partial-write hazard: reuse requires both files plus digest equality, and
  the checksum file is written after the zip; a crash mid-write yields either
  a missing `.CHECKSUM` or a truncated/mismatched digest, all of which are
  discarded and re-downloaded. No torn entry can be reused.
- Residual (Low): an attacker with filesystem write access to the state dir
  could plant a self-consistent (bytes + matching self-computed digest) pair.
  That requires the same local trust domain as forging the ledger itself; not
  a network-reachable poisoning vector.

### 3. H2 404 mapping — PASS

- [`default_archive_provider`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:164)
  now catches `HTTPError` explicitly
  ([`source_adapter_v0.py:187-193`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:187)):
  `code == 404` → `return None` (absent month → REST tail); any other HTTP
  error → `SourceAdapterBlocked`. `URLError`/`TimeoutError` remain fail-closed
  ([`source_adapter_v0.py:194-195`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:194)).
  Exception ordering is correct (`HTTPError` subclasses `URLError` and is
  caught first).
- Reachability/correctness of the designed chain is proven end-to-end by
  [`test_absent_archive_via_http_404_composition_succeeds_through_rest_tail`](../../tests/test_jh01_v1_prospective_source_adapter_v0.py:197)
  ([`test_jh01_v1_prospective_source_adapter_v0.py:197-223`](../../tests/test_jh01_v1_prospective_source_adapter_v0.py:197)):
  every monthly archive 404s via a real-`HTTPError` fake opener → `None` →
  REST tail fills the entire required window → frozen `validate_bars` admits
  the composed set. Non-404 codes (403, 500) and `URLError` are asserted to
  raise `SourceAdapterBlocked`
  ([`test_jh01_v1_prospective_source_adapter_v0.py:173-183`](../../tests/test_jh01_v1_prospective_source_adapter_v0.py:173)).
- Over-broad swallowing: none beyond one narrow semantic looseness — a 404
  raised by the `.CHECKSUM` fetch (zip present, checksum object absent) shares
  the same `try` block and also maps to `None`
  ([`source_adapter_v0.py:183-192`](../../qntylab/jh01_v1_prospective_source_adapter_v0.py:183)),
  i.e. "present archive with missing checksum" degrades to the REST-tail path
  instead of a hard block. Direction remains fail-closed overall (an unfilled
  hole still fails closed in `validate_bars`); classified Low, no repair
  required this phase.

### 4. New Critical/High introduced by the repairs — NONE FOUND

- Test honesty: the new tests drive the real production functions
  (`default_archive_provider`, `cached_archive_provider`, `record_due`) with
  fake openers/providers via `monkeypatch.setattr` — no tautologies found.
  Coverage: 404→None mapping
  ([`test_jh01_v1_prospective_source_adapter_v0.py:167-170`](../../tests/test_jh01_v1_prospective_source_adapter_v0.py:167)),
  verified-reuse-with-zero-redownload
  ([`:226-245`](../../tests/test_jh01_v1_prospective_source_adapter_v0.py:226)),
  corrupt-entry discard+repair
  ([`:248-270`](../../tests/test_jh01_v1_prospective_source_adapter_v0.py:248)),
  never-persist-unverified
  ([`:273-288`](../../tests/test_jh01_v1_prospective_source_adapter_v0.py:273)),
  no-negative-caching
  ([`:291-304`](../../tests/test_jh01_v1_prospective_source_adapter_v0.py:291)),
  and production wiring asserting persisted `.zip`+`.CHECKSUM` pairs under
  `<state-dir>/jh01_v1_source_archive_cache_v0/`
  ([`test_jh01_v1_prospective_production_caller_v0.py:217-246`](../../tests/test_jh01_v1_prospective_production_caller_v0.py:217)).
- README documents the timeout sizing and cache policy
  ([`ops/systemd/user/README.md:56-89`](../../ops/systemd/user/README.md:56)).
- No state-dir writes outside the expected location; no attacker-controlled
  filename component; no mutable unverified cache enters `record_due`.

### 5. Frozen invariants — VERIFIED BY INSPECTION ONLY (execution unavailable)

- Pinned constants match the task-stated digests exactly:
  `FROZEN_RECORDER_SHA256 = 4f5e1791…95ec1a` and
  `FROZEN_WRAPPER_SHA256 = 1176037f…67c41`
  ([`test_jh01_v1_pre_origin_e2e_proof_v0.py:40-41`](../../tests/test_jh01_v1_pre_origin_e2e_proof_v0.py:40));
  the wrapper embeds the recorder digest at
  [`operation_v0.py:39`](../../qntylab/jh01_v1_prospective_operation_v0.py:39);
  runtime enforcement via Proofs 17/18
  ([`test_jh01_v1_pre_origin_e2e_proof_v0.py:473-484`](../../tests/test_jh01_v1_pre_origin_e2e_proof_v0.py:473))
  remains intact and untouched by the repairs. Neither frozen module appears
  among the repaired artifacts. An independent `sha256sum` was NOT executed
  (no command tool this session) — same disclosed limitation class as the
  original review; recommend a CI re-run of Proofs 17/18 to close the gap.

### 6. Real-ledger firewall — NOT INDEPENDENTLY VERIFIED (execution unavailable)

- The real ledger lives outside the workspace
  (`~/.local/state/qntylab/jh01_v1_real_prospective_operation_v0/jh01_v1_operation_events.jsonl`);
  neither reading it nor hashing it was possible this session. Structural
  evidence: the repairs write only under the injected `state_dir`; all new
  tests bind state to pytest `tmp_path`; the firewall guard scanning the test
  modules for the real state dirname remains intact
  ([`test_jh01_v1_pre_origin_e2e_proof_v0.py:491-505`](../../tests/test_jh01_v1_pre_origin_e2e_proof_v0.py:491)).
  Recommend a read-only `sha256sum` confirmation out-of-band against
  `37b41c23…e296cc`.

## Residual risks (classified)

| Risk | Severity | Note |
|---|---|---|
| No timed rehearsal receipt for the 840 s bound | Low | Analytic sizing + cache make terminal miss unlikely; failure mode remains fail-closed |
| 404 on `.CHECKSUM` fetch also maps to `None` | Low | Degrades to REST tail instead of hard block; still fails closed via `validate_bars` |
| Local state-dir writer could plant self-consistent cache pair | Low | Same trust domain as ledger forgery; not network-reachable |
| Frozen hashes / real ledger hash / 54-pass suite result not independently executed this session | Verification gap (not a code defect) | Close via CI re-run of Proofs 17/18 + out-of-band `sha256sum` |

TARGETED_REREVIEW = PASS_NO_OPEN_CRITICAL_HIGH
