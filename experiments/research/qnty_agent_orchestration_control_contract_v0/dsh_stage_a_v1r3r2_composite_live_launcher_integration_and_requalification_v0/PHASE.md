# DSH Stage-A V1R3R2 Composite Live Launcher Integration and Requalification V0

## Authority firewall

This phase is bounded to implementation and offline requalification of one
composite launch boundary. It does not authorize a live episode, a provider
or model call, a real secret read, a claim, spend, Stage B, Qnty, scientific,
trading, capital, or promotion authority.

The physical DSH runtime, source bytes, lockfile, governed DSH patches, and
built CLI are frozen inputs. The only intended production change is the
composite launcher/policy envelope that binds the physical launcher to the
existing Stage-A policy. The offline provider overlay is a qualification-only,
loopback-and-fake-sentinel substitution; it is additive and canonical policy
is applied first.

## Identity

- Project: `DSH_STAGE_A_V1R3R2_COMPOSITE_LIVE_LAUNCHER_INTEGRATION_AND_REQUALIFICATION_V0`
- Canonical base: `36890e7487ed5038c3149d33ae3bfbee0335ae5e`
- Historical predecessor: `e16872fc1f419e5253d633bbdf35e936bb58e34a7636decb8eda688113658e82`
- Pinned DSH source: `deepseek-ai/deepseek-harness@99f6f02fecdb7dff40c3fbc9470f5907c29f74ca` / tree `3bc8f89fe494a4755c188be354add4e8b1e7b188` / tag `dsh-v0.1.0-rc.7`
- Runtime manifest digest: `0e09b9d9d977f73d146c4a35d497cc93bd046bae016e1b1a6a52b481f07731b3`
- Executable identity digest: `ae07ece34c88b3ebaebd7452df8d136c82935f9c8ec9df16a40e50a2582a2fd9`
- Qualified composite contract digest: `a392f82efd5cf97e20a6ce4353597a8a7210e8638cc17e5a4209cc1003eee4be`

The predecessor contract remains historical evidence. The successor digest is
computed from current pinned component bytes and does not import the old
digest machinery or accept the predecessor as the current contract.

## Reproduction and change

The pre-change physical launcher passed its physical identity checks, but the
old Stage-A launcher rejected the predecessor contract while its historical
digest machinery rejected the current runtime manifest. This was classified as
`COMPOSITE_BINDING_GAP`.

The successor adds:

1. a fresh digest/contract envelope for the physical runtime, executable set,
   Stage-A policy bytes, qualified profile, and composite launcher;
2. action-time revalidation immediately before DSH spawn;
3. a canonical-policy-first offline overlay that inserts only loopback stub
   provider IDs and disables the raw provider IDs;
4. disposable-process qualification for clean review and bounded repair paths;
5. explicit negative controls for identity drift, policy drift, route drift,
   workspace escape, forged receipts, and offline-boundary escape.

During qualification, the first overlay composition attempt was rejected by
DSH because it tried to replace a provider row by name. That additive overlay
was repaired to disable the canonical raw rows and insert new stub rows. The
clean rerun passed with empty stderr; this was the only implementation repair
and is not a production-runtime byte change.

## Qualification boundary

Two disposable DSH processes exercised the real pinned CLI/runtime through the
composite launcher:

- clean path: one fake Codex and one fake Claude invocation;
- repair path: two fake Codex and two fake Claude invocations, with a
  high-first review response and bounded repair.

Both runs used a loopback parent, the exact fake sentinel
`QNTYLAB_FAKE_COMPOSITE_NOT_REAL`, disposable workspaces and DSH homes, and
the exact native executable paths from the qualified identity. They recorded
zero public-provider requests, real model calls, real Codex/Claude turns, real
secret reads, claims created, and spend. The local Git claim-control harness
created disposable local receipts only; it did not create an authoritative
remote claim.

## Terminal disposition

The implementation and offline qualification pass. A later, separately
authorized phase may construct a fresh one-episode live authorization bound
only to the successor digest. This phase does not construct, activate, or
execute that episode.
