# DSH runtime materialization and offline launch V0

Project: `DSH_RUNTIME_MATERIALIZATION_AND_LAUNCH_V0`

Mode: bounded pre-live runtime materialization and offline launch qualification.

Canonical QntyLab master for this phase is `11837b905574a8847d4740852369c0ea352f843a`.
The phase has no live DSH authority, Stage-B authority, Qnty/scientific/trading/
capital authority, claim authority, or spend authority.

## Scope

This phase closes the infrastructure gap recorded by the prior
`BLOCK_RUNTIME_INFRA` episode. It adds a repository-native acquisition seam
that:

- clones only `https://github.com/deepseek-ai/deepseek-harness.git`;
- detaches at commit `99f6f02fecdb7dff40c3fbc9470f5907c29f74ca`;
- verifies tree `3bc8f89fe494a4755c188be354add4e8b1e7b188` and tag
  `dsh-v0.1.0-rc.7`;
- rejects dirty/untracked source, unsafe source paths, wrong remotes, and
  source substitutions;
- invokes exact `corepack pnpm@11.7.0 install --offline --frozen-lockfile`
  and `corepack pnpm@11.7.0 run build:lib`;
- applies the already-governed Codex executable-binding repair and Claude
  hard-read-only repair, preserving their historical patch identities;
- emits a sanitized materialization receipt and executable/runtime manifest;
- verifies the source identity, governed diff set, lockfile, toolchain,
  entrypoint, build digest, and executable fingerprints at launch; and
- launches the actual built DSH process against a loopback-only fake parent.

The phase reuses the canonical V1R3 launcher/materializer primitives where
compatible. It does not create a competing DSH runtime implementation.

## Evidence

- `evidence/materialization_receipt.json` — fresh source, patch, install, and
  build receipt.
- `evidence/runtime_manifest.json` — identity-bound runtime manifest.
- `evidence/boot_receipt.json` — actual built DSH `--help` process boot.
- `evidence/loopback_receipt.json` — actual full-profile headless boot with
  one loopback parent request and exact native child tool surface.
- `evidence/digests.json` — reproducible identity digests and reconciliation
  against historical qualified contract
  `e3b623c58d0ce591baa9d0e07d9cf4dd802203d34a4a1b1521d29f75ca302ffa`.

The independent replica was materialized at a separate scratch root. Its
source, lockfile, patch, runtime, and executable identities all matched.

Network evidence is configuration-plus-observation: the qualification route
was explicitly `127.0.0.1`, and the mock observed exactly one request. No
kernel network namespace was introduced. Git/package acquisition occurred
only during the explicitly permitted source/dependency materialization step.

## Boundary counters

No real provider secret was read or forwarded. No real OpenAI, DeepSeek, or
Anthropic model request occurred. No Codex or Claude child turn occurred. No
claim, episode activation, fixture execution, spend, Stage B, Qnty, trading,
capital, or scientific authority was created.

## Contract reconciliation

The physical Phase-D runtime is reproducible, but the historical `e3b…`
contract is not byte-identical: it records pnpm `11.22.0` and different
launch-policy bytes, while this phase binds the pinned `pnpm@11.7.0` and the
new acquisition/manifest gate. The narrow truthful result is
`REQUALIFICATION_REQUIRED`; the historical contract is not invalidated.

## Verification

```sh
node --test test/qntylab-dsh-runtime-v0.test.mjs
node --test ../dsh_stage_a_v1r3r2_claude_hard_read_only_repair_and_requalification_v0/test/qntylab-dsh-v1r3r2.test.mjs
python -m pytest tests/test_dsh_stage_a_v1r3_launch_plane_qualification.py -q
python -m qntylab.project_context render --check
python -m qntylab.research_ledger doctor
git diff --check
```

No live episode is started by this phase. Stop after the implementation,
qualification, one hostile review, commit, and draft PR.
