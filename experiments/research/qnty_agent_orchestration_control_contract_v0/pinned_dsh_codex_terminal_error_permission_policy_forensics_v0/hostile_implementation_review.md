# Hostile implementation review

## Scope

This is the single independent hostile review required by the implementation
authorization for `PINNED_DSH_CODEX_TERMINAL_ERROR_PERMISSION_POLICY_FORENSICS_V0`.
It reviews the final implementation tree before prelive freeze and checks the
causal boundary, identity pins, evidence integrity, credential gate, crash-safe
consumption, and workspace-change boundary.

An external Claude review was attempted once but was unavailable because the
provider reported its session limit. The review below is therefore an
independent read-only repository review performed as a separate checklist,
with no product execution and no historical episode rerun. No second external
review or retry was made.

## Hostile checks

| Check | Result | Evidence |
| --- | --- | --- |
| Historical A is not runnable by this module | PASS | CLI exposes only `fake-diff`, `freeze`, and `run-live`; no historical driver invocation exists. |
| Intervention has exactly one semantic wire delta | PASS | `fake_app_server_request_diff.json` contains only `thread/start.params.approvalPolicy`, absent → `never`. |
| No sandbox, runtime roots, capability, model, prompt, or identity change | PASS | Request-shape tests compare initialize and turn payloads byte-for-byte; the patch changes only thread-start policy. |
| DSH and Codex identities remain pinned | PASS | Contract and freeze bind DSH commit/tree/tag and Codex 0.147.0 plus binary digest. |
| Evidence is materially richer than the predecessor | PASS | Receipt schema preserves request/response observations, turn id/lifecycle, terminal error details, JSON-RPC code, tool/approval/sandbox signals, exit/timeout, digests, and fixture paths. |
| Control artifacts cannot contaminate the disposable workspace diff | PASS | Control directory, prompt, trace, and wrapper are outside the product workspace. |
| Partial JSONL input cannot silently lose a request | PASS | Wrapper buffers incomplete stdin lines until the next chunk or EOF. |
| Timeout remains crash-safe and recorded | PASS | Consumed marker is written before subprocess execution; timeout is converted into a receipt and `INCONCLUSIVE_INFRA`. |
| Profile A mutation is detected | PASS | Config hash is recorded before and after the canary; mutation is fail-closed as `INCONCLUSIVE_INFRA`. |
| Credential values are not stored | PASS | API-key names are checked presence-only; receipt sanitization removes authorization, cookie, token, and API-key fields. |
| Unauthorized workspace writes are fail-closed | PASS | Snapshot comparison requires exactly `fixture.txt`; all other changes are recorded as unauthorized. |
| Retry path is absent | PASS | Consumed marker existence blocks subsequent live invocation; no retry loop exists. |

## Findings

No Critical or High findings remain open. The final review found no defect that
undermines the one-variable intervention, invalidates the receipt, or weakens
the fail-closed canary contract. No targeted rereview is required.

## Review verdict

`HOSTILE_REVIEW_PASS`

The implementation is eligible for immutable prelive freeze, subject to the
separate runtime identity, credential, request-delta, and clean-tree gates.
