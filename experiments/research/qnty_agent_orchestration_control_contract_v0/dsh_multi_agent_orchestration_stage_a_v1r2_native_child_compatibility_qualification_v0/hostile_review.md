# Independent hostile review — DSH Stage-A V1R2 native child compatibility qualification

Review scope: one static/offline review of the V1R2 compatibility module,
tests, qualification receipt, and project-registry binding. No OpenAI parent,
DSH parent, model-backed Codex turn, model-backed Claude turn, Stage-A
fixture, secret, or paid command was invoked during this review.

## Attack surface

- package/SDK version compared with an unrelated native CLI version;
- fake or incomplete zero-model compatibility evidence;
- accidental Codex `turn/start` or Claude API/model invocation;
- unstable executable fingerprinting, symlink/launcher confusion, or PATH drift;
- auth/config/token leakage;
- historical V1R1 evidence rewriting;
- live authority, ACTIVE successor, Stage B, or scientific/trading/capital leakage.

## Findings

- Critical: 0
- High: 0
- Medium: 0
- Low: 0

## Evidence reviewed

- V1R1 package/CLI values remain separate and the historical execution receipt
  remains `STAGE_A_V1R1_BLOCK_CHILD_INFRA` with `episode_consumed=false`.
- The V1R2 gate compares complete native fingerprints and typed SDK identity;
  no package/CLI version equality is used.
- Codex sends only `initialize`, `initialized`, and `thread/start`; the receipt
  records zero turns, usage events, task execution, and a quiesced process.
- Claude uses a non-executing SDK spawn seam plus a real `--help` parser probe;
  no prompt or API request is sent.
- Fingerprints include resolved path, realpath, product output, and entrypoint
  digest; auth stores, HOME contents, and credential values are not hashed or
  persisted.
- The project is `CLOSED_PASS`, implementation is unauthorized after closure,
  and the registry records no ACTIVE successor.

## Verdict

`PASS_NARROW_HOSTILE_REVIEW`
