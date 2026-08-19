# V0R1 independent hostile review

Review candidate: `2e77c94a79ac4b84263d7d8920dd74956ab6441d`
Predecessor V0 head: `ca06d85e9e2e56e16563b25cf8998ff6f8cd9218`

This review was performed in a separate detached read-only worktree. The
reviewer did not modify implementation files and made no subscription-product
calls.

## H1 — exact `process_exit` schema

- Removed `disposed`: rejected.
- Removed every required nested member: rejected.
- Scalar, list, null, wrong-type, bool/int-confusion, and extra-member probes:
  rejected.
- Contradictory timeout, signal, exit-code, lifecycle, and unstarted states:
  rejected.
- PASS requires the complete role-specific nested schema and consistent
  terminal evidence.

## H2 — verified bytes equal executed bytes

- Prompt swap immediately before each role invocation: frozen prompt bytes
  remained the bytes handed to the driver.
- Prompt swap/restore and manifest swap/restore: no mutable reread affected
  invocation bytes.
- Symlink source handoff: rejected by the bootstrap.
- The bootstrap retains the one-read manifest and source byte objects; the
  controller requires that bundle and derives prompt paths and role timeouts
  from the validated frozen contract bytes.
- No controller prompt or manifest path reread was found.

## Cross-cutting regression

The reviewer attacked the conjunctive machine result and fail-closed role
dependency gates. A missing role PASS, malformed receipt, or consumed marker
does not produce overall PASS or start downstream roles.

```text
CRITICAL = 0
HIGH = 0
MEDIUM = 0
LOW = 0
OPEN_CRITICAL = 0
OPEN_HIGH = 0
```

Targeted re-review: not used.

Deterministic review command:

```text
PYTHONPATH=. pytest -q tests/test_subscription_backed_native_product_execution_qualification_v0.py tests/test_subscription_backed_product_execution_plumbing_v0.py tests/test_subscription_backed_codex_app_server_write_path_diagnostic_v0.py
105 passed
```
