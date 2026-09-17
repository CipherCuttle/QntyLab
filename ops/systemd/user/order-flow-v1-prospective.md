# Order Flow Prospective V1 — Hetzner migration candidate

**MIGRATION CANDIDATE ONLY — LAPTOP REMAINS SOLE ACTIVE WRITER.**
**DO NOT MERGE OR START HETZNER TIMER WITHOUT EXPLICIT OWNER CUTOVER AUTHORITY.**

This change prepares an isolated runtime on the existing trusted non-US Hetzner
Qnty VM. It does not install, enable, or start a scheduler. During candidate
qualification the laptop timer stays active. `/srv/qnty` and its repository,
state, services, and timers must remain untouched.

The non-scientific host qualification is recorded in
`experiments/research/qnty_edge_discovery_order_flow_v1/hetzner_host_migration_v1.json`.
Binance first-party USD-M `/fapi/v1/time` returned HTTP 200 over verified TLS;
no payload was persisted and no campaign observation was fetched. The receipt
is operational evidence only, not scientific evidence.

## Qualification blockers

On 2026-09-17, the host had Python 3.12.3 and working user systemd, but no `gh`
executable, no unattended sudo, and `Linger=no`. `/srv` was not writable by
`viktor`; creation of the dedicated tree and enabling linger were denied.
The repo and venv are therefore **not prepared**. Cutover is blocked until:

- The dedicated tree is provisioned for `viktor` and a clean full-history clone
  and Python 3.12 venv are verified at the exact paths below.
- `gh` is installed on the service PATH and unattended authenticated release
  write access to `CipherCuttle/QntyLab` is available. Public clone access does
  not establish write capability. Do not copy laptop credentials or expose tokens.
- `loginctl show-user viktor -p Linger` reports `yes` and user systemd works.

The operation uses the Python standard library; offline tests require
`pytest==8.4.2`. No project package installation is required. Do not seed the
state directory, copy a ledger, or install/enable/start Order Flow units during
this implementation phase.

## Candidate runtime bindings

| Surface | Exact target |
| --- | --- |
| User / HOME | `viktor` / `/home/viktor` |
| Repository | `/srv/qntylab-orderflow/repo` |
| Python 3.12 | `/srv/qntylab-orderflow/venv/bin/python` |
| Campaign state | `/srv/qntylab-orderflow/state/order_flow_prospective_v1` |
| Installed user units | `/home/viktor/.config/systemd/user/` |
| Contextualized host digest | `541ef1512288f24b4b831d975a58b8b4918ba84c70f922c5a677bae8c08d458e` |

The host fingerprint algorithm is unchanged: SHA256 of the campaign context
plus the hexadecimal SHA256 of the raw `/etc/machine-id` bytes. Only the final
contextualized digest is recorded. The former laptop fingerprint fails against
the migration candidate. `XDG_STATE_HOME` and `--state-dir` cannot override the
canonical state location.

## Separate owner-authorized single-writer cutover

The following sequence is documentation only; it is **not authorized by this
candidate phase**. Resolve all qualification blockers before beginning.

1. STOP LAPTOP TIMER (disable it for subsequent boots), then verify the laptop
   service is inactive. Allow any healthy in-flight invocation to finish; do not
   terminate a writer. Confirm no Order Flow writer remains active.
2. Verify no draft exists and the latest evidence release is published,
   immutable, complete, and matches the laptop ledger. Stop on any discrepancy.
3. MERGE the migration PR only with explicit owner cutover authority.
4. Canonicalize the clean Hetzner repository to the exact resulting merge SHA;
   require HEAD == origin/master == that SHA. Verify Python 3.12 and auth again.
5. Install the exact canonical service and timer bytes under the `viktor` user
   unit directory and reload user systemd. Keep the timer stopped at this point.
6. Run `canonical_preflight` with the exact Hetzner repository and require PASS.
7. With empty local campaign state and both schedulers stopped, restore using
   the existing `reconcile_canonical_ledger` path from the latest immutable
   GitHub release, and independently verify its bytes and head. Do not fabricate
   a ledger, copy the laptop ledger, or invoke `record_due` for restoration.
8. START HETZNER TIMER, verify a natural current-window observation and its
   immutable anchor, and confirm the laptop timer stays disabled. Do not
   manually start the service or invoke `--record-due` as an extra retry.

Merge alone cannot activate Hetzner: no Order Flow units are installed there by
this phase and no deployment hook is added. The existing laptop service fetches
master before each invocation, so merging before the explicit stop would break
laptop collection through the new host/unit bindings. This is why the stop and
in-flight completion gates precede merge.

## Frozen collection boundary

The timer remains byte-identical: attempts at :05, :20, :35, and :50 UTC,
`Persistent=false`, no randomized delay. The service retains its clean-worktree
check, fetch of master, detached checkout, 840-second timeout, journal logging,
and `SuccessExitStatus=3` for `NOT_DUE`.

Before provider access, the runtime reconciles with the canonical immutable
GitHub release chain. Expired closes become `WINDOW_MISSED` without provider
fetches and each event is anchored before progressing. Missing local evidence
is restored from immutable remote history; divergence fails closed. No existing
release may be edited, deleted, or recreated.

Source and recorder bytes, symbols, exchange, logical-close grid, recording
window, and origin are frozen. No backfill, replacement origins, source
substitution, interim scientific evaluation, Router/Qnty/QntySpot use, trading,
signing, submission, or capital authority is granted. The active project
lifecycle is unchanged. GitHub Actions remains offline CI-only for this campaign.
