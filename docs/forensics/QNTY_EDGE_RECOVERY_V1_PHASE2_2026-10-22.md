# QNTY EDGE RECOVERY V1 — PHASE 2 GIT HANDOFF

**Date:** 2026-10-22 UTC  
**Classification:** ADMIN / READ-ONLY OPERATIONAL FORENSICS  
**Decision:** `PUBLICATION_ACTIVE_SEP24_GAP_UNEXPLAINED` / `H001_NOT_AUTHORIZED` / `EDGE_UNPROVEN`

This is an operational evidence handoff, **not** a scientific trial, an authority change, a production deployment, a wallet operation, an experiment-result inspection, or merge approval.

## Source and packaging boundary

- Repository: `CipherCuttle/QntyLab`, default-branch parent SHA `c09c5ad942aadffecdb7287f1e688f56fa9d704c`.
- Branch: `handoff/orderflow-gap-triage-readonly-20261022-v1` (unmerged).
- Files added, with no existing source, preregistration, timer, runtime, or authority file changed:
  - `ops/forensics/qnty_orderflow_host_triage_v1.sh`
  - `tests/ops/test_orderflow_metadata_host_triage_v1.py`
  - this report.
- The original previous-session handoff referenced a shell artifact with SHA-256 `d31bfe92c10839c9614dbfcffdd6f61c90d394cfa404bffb0f763d90c921ff`. That script's original bytes were **not available** when packaging. This branch contains a **new, non-identical replacement** with locally computed SHA-256 `aca1629638105aa825feb34a292d0f8033456ffe4e8ffd7cbdcf5e4c33927d15`. Do **not** conflate their identities.
- Local container could not clone the repository because public DNS to GitHub was unavailable. Therefore canonical `python -m qntylab.project_context` and `... brief` were **not run**. The receiving Codex must execute those before operational work or accepting the branch. A canonical conflict requires `SOURCE_CONFLICT` / STOP.

## Verify — public immutable release metadata only

- Order Flow evidence release #227 was published **2026-09-24 10:05:23 UTC**.
- Release #228 was published **2026-09-24 21:20:26 UTC**: **11h15m03s publication gap**.
- Releases #228–#234 were subsequently published rapidly; **not** proof of lawful backfill or valid hourly origin coverage.
- Release #903 published **2026-10-22 14:05:54 UTC**, marked immutable, with exactly one `order_flow_prospective_v1_events.jsonl` asset and GitHub asset metadata digest `sha256:30d5a5ea9efbee7f7dc4ba1e59997657abc0a3038c2ae9bf933eeb9f9cbec764`.
- `#227`: https://github.com/CipherCuttle/QntyLab/releases/tag/order-flow-v1-evidence-000227-6d5c3ed361621071971cff42
- `#228`: https://github.com/CipherCuttle/QntyLab/releases/tag/order-flow-v1-evidence-000228-e8681e6f886313ddc5cec8d7
- `#903`: https://github.com/CipherCuttle/QntyLab/releases/tag/order-flow-v1-evidence-000903-a2714c1f37e823d5489d1ed6
- Existing forensic issue #297: https://github.com/CipherCuttle/QntyLab/issues/297#issuecomment-6342816904

No scientific asset bytes, market feature observations, outcomes, coefficients, p-values, or Hetzner journal contents were fetched by this review. Publication recency is verified; full hash-chain continuity, validity of origin windows, and precise failure mechanism are **not** verified.

## Verify — replacement host script

- `bash -n ops/forensics/qnty_orderflow_host_triage_v1.sh`: **PASS** in the isolated preparation environment.
- `python3 -m pytest -q tests/ops/test_orderflow_metadata_host_triage_v1.py`: **2 passed** in the isolated preparation environment, with fake `systemctl`/`journalctl` and `SECRET_CANARY` data.
- The helper uses user-scoped read-only systemd/journalctl queries on two bounded UTC windows. It emits *only* allowlisted unit fields, journal entry/hour/priority counts and unique structured invocation **counts**. It never emits journal `MESSAGE`, arbitrary stderr or invocation IDs.
- Its output explicitly marks `host_identity_verified=false` and `collector_user_identity_verified=false`. Queries that fail return exit 2 and leave the affected data UNKNOWN. It does **not** certify host identity, scheduler correctness, origin coverage, no backfill, scientific integrity, or an edge.
- **Not run on the actual qualified Hetzner collector host**. A separate on-host review is required.

## Required Codex continuation (bounded)

1. On a clean local QntyLab checkout: `git status --short`, `python -m qntylab.project_context`, `python -m qntylab.project_context brief`, inspect authority conflicts and existing host/forensics tooling. If this is not possible, record `BLOCKED_ENVIRONMENT` and STOP; do not invent results.
2. Verify exact branch files, script SHA-256, `bash -n`, and synthetic tests. Host/operator must be independently matched to canonical qualified identities **before** interpreting any journal evidence.
3. **Only if** the already-qualified host/user is accessible under existing authority, run `bash ops/forensics/qnty_orderflow_host_triage_v1.sh` locally on that host, as its service user. Retain a redacted metadata-only receipt; never paste unsanitized journal messages.
4. Correlate the September 24 unit/priority/hour metadata with independently verified GitHub release **metadata**; determine `PUBLICATION_FAILURE`, `TIMER_OR_SERVICE_FAILURE`, `HOST_OR_AUTH_FAILURE`, `VISIBILITY_ARTIFACT`, or `UNKNOWN`, with a defensible evidence trail. Do not infer that release publication certifies valid research rows.
5. Review-only output: exact commands, sha, source refs, PASS/FAIL/BLOCK classification and remaining uncertainties. Stop. Leave issue #297 open unless the complete host and release classification is independently supported.

## H001 separate gate — unchanged

Qnty PR #336 (`5af1160e6fdb27fb7332adaacab35d7eef890ebe`) remains review-only; independent scientific contract acceptance is missing. Its synthetic null calibration is hard-disabled. Frozen one-sided 95% exact Clopper–Pearson upper bound must be <=0.075 for each of six null DGPs over 2,000 outer replications; under that frozen rule the maximum passing rejection count is 130. The calculation is **not** a calibration run or scientific clearance.

Reference: https://github.com/CipherCuttle/Qnty/pull/336

## Hard STOP

No service restart, scheduled-run injection, source substitution, backfill, release alteration, interim outcomes, H001 calibration, result reanalysis, contract mutation, trial, live trade, leverage, signing, broadcast, merge, or deploy. Order Flow's preregistered window and outcome-only tail end at **2027-01-14 00:00 UTC**; terminal evaluation requires separately authorized governance.

**Verdict:** `HANDOFF_READY / HOST_TRIAGE_PENDING / EDGE_UNPROVEN / NO_TRADING_AUTHORITY`.
