# Independent hostile review — Phase D

Review count: **1**

Review scope: final materializer, launcher, receipts, final materialized source,
loopback run, and independent replica.
Outcome: **PASS** — Critical 0, High 0, Medium 0, Low 0. Targeted rereview:
not required.

## Attacks and receipts

1. **Floating source / wrong commit / wrong tree / wrong tag / wrong remote** —
   rejected by the exact constants and Git verification; final source reports
   commit `99f6f02fecdb7dff40c3fbc9470f5907c29f74ca`, tree
   `3bc8f89fe494a4755c188be354add4e8b1e7b188`, tag `dsh-v0.1.0-rc.7`, and
   the expected GitHub remote.
2. **Dirty checkout / path traversal / unsafe symlink** — acquisition refuses
   non-empty targets, checks the Git tree, permits only symlinks resolving
   inside the checkout, and launch rejects unexpected untracked or changed
   paths. The final patched diff is exactly the five governed source files.
3. **Dependency drift / lockfile mutation / wrong pnpm** — the only install
   path is exact `corepack pnpm@11.7.0 install --offline --frozen-lockfile`;
   the receipt binds the lockfile digest and actual version `11.7.0`.
4. **Stale build / entrypoint substitution / PATH substitution** — the launch
   gate requires the qualified built CLI digest, absolute entrypoint, static
   executable fingerprints, and the predecessor launcher’s realpath-resolved
   spawn paths. The reused launch-plane tests include fingerprint and TOCTOU
   negative controls.
5. **Manifest substitution / launcher bypass** — the phase gate checks source
   Git identity, governed diff set, lockfile, patch digests, package-manager
   invocation, build command, build digest, launcher identity, and all four
   executable identities before delegating to the canonical launcher preflight.
6. **Repair omission or replacement** — both governed patch digests match the
   historical QntyLab artifacts and both applied during each fresh build.
7. **Secret leakage / provider traffic / hidden child calls** — the final
   loopback receipt records a fake key, `127.0.0.1` routing, one mock request,
   zero external provider requests, zero real secret reads, zero model calls,
   zero Codex/Claude turns, and zero spend. The synthetic sentinel was absent
   from the child environment.
8. **Fake runtime mistaken for real DSH** — the decisive process used the
   materialized built entrypoint `/var/tmp/qntylab-dsh-runtime-v0-final/source/apps/cli/lib/bin.js`;
   the safe boot printed the real DSH CLI help, and the full-profile run
   produced the deterministic loopback completion.
9. **Uncontrolled second runtime / reproducibility laundering** — the final
   independent replica used a separate scratch root and matched source,
   lockfile, patch, runtime, and executable identities. No second live or
   provider run occurred.
10. **Overclaiming authority** — receipts and qualification state explicitly
    keep claims, spend, Stage B, Qnty, science, trading, and capital at zero or
    `NONE`; the network statement is limited to configuration-plus-observation,
    without a kernel namespace guarantee.

No Critical or High finding remained open. This review does not issue or renew
the historical live contract; `e3b623c58d0ce591baa9d0e07d9cf4dd802203d34a4a1b1521d29f75ca302ffa`
requires requalification because this phase binds exact pnpm 11.7.0 and new
launch-policy bytes.
