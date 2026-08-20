# Hostile governance review — clean C replication authorization V0

Review count: one independent hostile review.

Scope: authorization artifact only. No DSH, Codex, canary, or product invocation
was performed by this phase.

## Attacks and disposition

- Hidden C→D treatment delta: PASS. The artifact freezes C's request shape and
  prompt identity, requires `C_TO_D_PRODUCT_REQUEST_DELTA_COUNT = 0`, and blocks
  any nonzero delta before consumption.
- Observation misclassified as treatment: PASS. Profile reads, hashes, safe
  metadata, and ephemeral raw snapshots are explicitly observational and do not
  authorize configuration changes.
- Profile or secret leakage: PASS. Raw bytes are private ephemeral-only, never
  printed, serialized, committed, or sent to a model. Durable evidence is
  limited to hashes, safe metadata, and redacted semantic findings.
- Baseline drift and restoration loopholes: PASS. The authorization baseline is
  `cb07d9468bb9f7e21b3cc507b20f31a6bffbc8328ef5b250bd7f9a12141ab6c7`; a later
  mismatch is `PRELIVE_BLOCKED`, with no restoration authority.
- Alternate profile loopholes: PASS. Alternate `CODEX_HOME`, alternate profile,
  profile normalization, and config restoration are prohibited.
- Multiple invocation and retry loopholes: PASS. Exactly one later D exposure,
  zero retries, and an irrevocable marker immediately before invocation are
  frozen. Every post-marker outcome consumes the exposure.
- Mutation counted as clean: PASS. Any before/after hash mismatch is
  `PROFILE_MUTATED_RECORDED` and disqualifies `CLEAN_CONFIRMATION_PASS`.
- Fixture proof: PASS. Clean confirmation requires expected write, exact
  `changed_paths = ["fixture.txt"]`, and no unauthorized writes.
- Concurrent process confounding: PASS. Exact before/after bytes and optional
  observational timing are required to classify mutation; the artifact does not
  infer causality from mtime alone.
- JSON-RPC `-32600`: PASS. Its presence is preserved but is not itself a
  failure; lifecycle ordering and fatality remain required.
- Exact-root-cause overclaim: PASS. Clean confirmation updates to strong
  sandbox ownership support only; exact historical root cause remains unproven.

Critical: 0

High: 0

Targeted rereview: NOT USED. No Critical/High repair was required.

Review conclusion: ACCEPTABLE GOVERNANCE-ONLY AUTHORIZATION, effective only
after canonical merge and not a live execution.
