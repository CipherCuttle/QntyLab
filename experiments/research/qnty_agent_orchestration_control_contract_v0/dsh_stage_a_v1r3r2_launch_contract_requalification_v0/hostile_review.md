# Independent hostile review — Stage-A V1R3R2 launch-contract requalification V0

Review count: **1**

Scope: historical-contract preservation, candidate-digest handling, complete
successor bindings, differential safety, authority firewall, and evidence
reuse. The review used the checked-in evidence artifacts and standalone
verification commands; it did not invoke DSH, a provider, a model, a secret,
or a child executable.

## Attacks and receipts

1. **Historical e3b accidentally accepted as current** — the historical
   contract recomputes to `e3b623c5…`, remains in the predecessor artifact, and
   the successor is `e16872fc…`; PASS.
2. **c98 candidate trusted without recomputation** — the candidate recomputes
   to `c98c0a91…` under the predecessor Phase-D envelope, but the complete
   successor digest is independently recomputed as `e16872fc…`; c98 is not
   accepted; PASS.
3. **Source commit/tree/tag or remote substitution** — all four exact source
   fields are present in the physical launch binding, and mutation tests change
   the qualified digest; PASS.
4. **Toolchain, pnpm, or lockfile substitution** — Node `v22.22.0`, Corepack
   `0.34.0`, `pnpm@11.7.0`, actual `11.7.0`, frozen offline install command,
   and the exact lockfile digest are bound; PASS.
5. **Governed patch omission** — both exact Codex and Claude patch digests are
   bound with `applied=true` and `compiled=true`; PASS.
6. **Built executable substitution** — the exact `apps/cli/lib/bin.js`
   entrypoint digest, runtime manifest digest, and executable identity digest
   are bound; PASS.
7. **Launcher/materializer substitution or bypass** — relative launcher and
   materializer paths, digests, driver digests, profile, and fail-closed
   verification semantics are bound; launcher mutation changes the digest;
   PASS.
8. **Absolute-path laundering or nondeterministic serialization** — digest
   artifacts contain no machine-local absolute paths or timestamps, and the
   standalone canonical SHA-256 recomputation matches the checked-in digest;
   PASS.
9. **Missing parent, child, claim, or Claude constraints** — eight-request /
   4096-token / zero-retry / `$1.00` parent controls, exact child order and
   ceilings, create-only claim semantics, and Claude Read/Glob/Grep hard
   read-only settings are preserved; PASS.
10. **Hidden execution authority or downstream broadening** — the contract and
    qualification firewall keep live execution, claims, secrets, provider I/O,
    Stage B, Qnty, science, trading, capital, and promotion unauthorized;
    `ACTIVE_PROJECT` remains `NONE`; PASS.
11. **Stale predecessor evidence attributed to changed bytes** — no files in
    the predecessor runtime phase changed, physical identities match its
    manifest, and loopback evidence is explicitly reused without rebuild;
    PASS.

## Verdict

Critical: **0**
High: **0**
Medium: **0**
Low: **0**

Targeted rereview: **NOT_REQUIRED**.
