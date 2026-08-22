# DSH Stage-A V1R3R2 launch-contract requalification V0

Project: `DSH_STAGE_A_V1R3R2_LAUNCH_CONTRACT_REQUALIFICATION_V0`.

Mode: bounded pre-live contract requalification against the already-qualified
physical DSH runtime. This phase is evidence and contract work only.

## Authority gate

The predecessor `DSH_RUNTIME_MATERIALIZATION_AND_LAUNCH_V0` is canonically
closed with `CLOSED_PASS_REQUALIFICATION_REQUIRED`. The historical qualified
contract remains immutable evidence:

`e3b623c58d0ce591baa9d0e07d9cf4dd802203d34a4a1b1521d29f75ca302ffa`.

This phase does not activate a project and does not issue execution, claim,
secret, provider, model, spend, Stage-B, Qnty, scientific, trading, capital,
promotion, or production authority.

## Contract method

The historical contract uses recursively key-sorted JSON serialized without
whitespace and SHA-256. Its qualified envelope is:

```json
{
  "projectId": "...",
  "RUNTIME_MANIFEST_DIGEST": "...",
  "EXECUTABLE_IDENTITY_DIGEST": "...",
  "LAUNCH_POLICY_DIGEST": "..."
}
```

The successor retains that envelope and canonicalization algorithm. Its launch
policy component combines the frozen Stage-A parent/child/claim/secret policy
with the physical materializer, launcher, toolchain, source, patch, build,
profile, and fail-closed verification bindings from the predecessor receipts.
No machine-local absolute path or timestamp is a digest input.

The predecessor `c98c…` candidate is recomputed under its own recorded Phase-D
envelope for audit, but is not accepted merely because the predecessor wrote it.
The successor digest is computed from the complete contract bytes.

## Evidence reuse

The predecessor runtime manifest, materialization receipt, boot receipt,
loopback receipt, digest evidence, and hostile review are reused. No runtime,
launcher, materializer, profile, or policy implementation bytes change in this
phase, so the full build and loopback qualification are not repeated.

## Verification

```sh
node --test test/contract-requalification.test.mjs
python -m pytest tests/test_dsh_stage_a_v1r3r2_launch_contract_requalification.py -q
python -m qntylab.project_context
python -m qntylab.project_context --json
python -m qntylab.project_context doctor --strict
python -m qntylab.project_context spine
python -m qntylab.project_context brief
python -m qntylab.project_context render --check
python -m qntylab.research_ledger doctor
git diff --check
```

One independent hostile review is required. If it finds no Critical or High
finding, no rereview is performed. Stop after the bounded commit and one draft
PR; do not create fresh live authorization or activation.
