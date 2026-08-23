# Independent hostile review — DSH Stage-A claim transport repair V0

Review count: 1
Review verdict: PASS
Critical findings: 0
High findings: 0
Medium findings: 0
Low findings: 0
Targeted rereview used: false

## Scope challenged

- The canonical `EpisodeClaim` create-only transport now accepts only the frozen
  production claim namespace or the explicitly authorized disposable diagnostic
  namespace.
- A successful push is not accepted without an independent exact-SHA
  `ls-remote` verification.
- A nonzero, timeout, or ambiguous transport outcome cannot create a local
  receipt or enable replay.
- A different-SHA ref collision cannot overwrite the existing ref.
- Diagnostic evidence contains the required fields and deterministic credential
  redaction, without environment/config/credential-helper dumps.
- Registry and generated roadmap state close the consumed authority and grant no
  downstream or production authority.

## Evidence

- Focused suite: `97 passed` across the repair, legacy EpisodeClaim, canonical
  authorization, project-context, and protected V0R5 tests.
- Project-context doctor: `project context ok`.
- Generated roadmap check: `roadmap current`.
- Repository-wide collection was attempted and is environment-blocked only by
  unrelated missing optional modules: `retry` and `polars`.
- Disposable positive create committed and independently observed SHA
  `36e3085c18a747e3755097c97915f61f289d0835`; the duplicate control observed
  the same SHA without overwrite; both disposable refs were deleted and checked
  absent.
- Production V0R5 claim ref remained absent; the protected V0R5 local intent and
  lock remained present, with no receipt.

## Root-cause calibration

The exact historical V0R5 push diagnostic was not retained. The review therefore
records `HISTORICAL_ROOT_CAUSE_UNRESOLVED`. The supported reproduced mechanism
is narrower: the prior constructor rejected the authorized disposable diagnostic
namespace before Git transport, while the exact underlying create-only push
worked when exercised directly. That observation is not upgraded into certainty
about the historical V0R5 failure.

## Disposition

No Critical/High repair is required. No targeted rereview is used. The bounded
phase stops after the candidate changes, sanitized receipt, and one review.
