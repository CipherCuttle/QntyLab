# JFPV3 PR-B R1 hostile repair review

Review count: exactly one independent hostile review.

## Findings

- Critical: none.
- High: runtime canonicality must not trust a stale local origin/master. Repaired with a fresh fetch in `resolve_runtime_canonical_state` and an explicit `fresh_remote_reconciliation` receipt field.
- High: a future merge must be accepted without changing source constants. Repaired with runtime HEAD/origin-master equality plus immutable historical ancestry and content-manifest checks.
- Medium: callers could bypass canonicality by supplying only a current SHA. Repaired by requiring `origin_master_sha`, clean state, and lineage in `validate_activation`.
- Low: the old name `CANONICAL_MASTER` could invite reuse. Removed; historical anchors have explicit V0/PR-A names.

## Targeted rereview

- Future merge SHA regression: PASS; a synthetic final merge distinct from all historical anchors validates when runtime canonicality and ancestry are supplied.
- Stale master, feature branch, dirty tree, wrong activation SHA, missing lineage, implementation tamper, and contract tamper: PASS; all fail closed.
- PR-A immutability: PASS; manifest and scientific contract digests are unchanged.
- Prospective firewall: PASS; no real metadata/OHLCV or scientific values accessed.

Final findings: Critical 0, High 0, Medium 0, Low 0.
