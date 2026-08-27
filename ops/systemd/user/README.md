# JH01 V1 Prospective Campaign — systemd User Scheduler Units

Units: `jh01-v1-prospective-record.service` (Type=oneshot) and
`jh01-v1-prospective-record.timer` (daily UTC origin windows).

These files are **not installed** by this repository step. Installation happens
in a later phase after hostile review. No sudo is required anywhere.

## What the service does

Runs the frozen production caller in `--record-due` mode:

```
/usr/bin/python3 -m qntylab.jh01_v1_prospective_production_caller_v0 \
  --record-due --root /home/swirky/DevHub/repos/QntyLab-jh01-operational \
  --go-binary /home/swirky/.local/opt/go-1.26.0/bin/go \
  --now "$(date -u +%Y-%m-%dT%H:00:00Z)"
```

- `--now` is required by the caller CLI and must be computed at trigger time,
  hence the `/bin/sh -c 'exec ...'` wrapper. Interpreter, module invocation,
  and all paths are absolute.
- The caller fail-closes `NOT_DUE` (exit 3) before `2026-09-15T00:00:00Z` and
  outside each origin window `[t, t+1h)`. Repeat invocation inside a window is
  idempotent (`IDEMPOTENT_AUTHORITATIVE_RECOVERY`, harmless no-op).
- The unit **cannot** reactivate the campaign: activation is not exposed by
  the caller CLI; it only records due origins.
- **Secrets:** nothing is passed via `Environment=`. Credential discovery uses
  the inherited user session environment (e.g. `gh auth`). If a token env var
  is ever needed it must come from the user environment or a systemd
  credentials mechanism (`LoadCredential=`) — never hardcoded.
- Logging goes to the user journal (`stdout`/`stderr`), no secrets.

## Dedicated canonical operational checkout (H-02)

The service never runs against the human development checkout. It runs in a
dedicated detached non-development git worktree:

```
/home/swirky/DevHub/repos/QntyLab-jh01-operational
```

Created once with:

```bash
git -C /home/swirky/DevHub/repos/QntyLab worktree add --detach \
  /home/swirky/DevHub/repos/QntyLab-jh01-operational origin/master
```

Before every real attempt, the caller synchronizes this worktree with a
fail-closed, fast-forward-only policy (`qntylab/jh01_v1_operational_checkout_v0.py`):

1. `git fetch origin` (fail closed on failure);
2. tracked worktree must be clean (fail closed when dirty);
3. HEAD is detached onto EXACTLY `origin/master`; if HEAD is not an ancestor
   of `origin/master` (diverged), the attempt FAILS CLOSED before any market
   data acquisition or publication. No force reset; the development checkout
   is never touched;
4. BEFORE any network effects, the frozen recorder and wrapper file digests
   are verified against the exact frozen identities; any mismatch raises
   `STOP_SOURCE_CONFLICT`.

The caller then independently re-verifies `HEAD == origin/master` and a clean
tracked worktree (`canonical_target_commit`) against the operational root.

## Unattended verifier and explicit Go toolchain (H-01)

- **Go:** the unit passes `--go-binary /home/swirky/.local/opt/go-1.26.0/bin/go`
  explicitly. The caller re-proves existence and `go version go1.26.0` at
  resolution time and fails closed otherwise.
- **Sigstore verifier:** `Environment=QNTYLAB_JH01_SIGSTORE_VERIFIER` points to
  the persistent verifier
  `~/.local/opt/jh01-v0r3-verifier/bin/verify-v0r3-generic`, built from the
  already-qualified frozen source `qualifications/jh01_v0r3` with
  `GOPROXY=off` (no network), `-trimpath -buildvcs=false` (reproducible). Its
  build identity manifest `~/.local/opt/jh01-v0r3-verifier/build_identity.json`
  records the sha256 of `main.go`/`go.mod`/`go.sum`, the Go version, and the
  binary sha256; resolution re-verifies all three and FAILS CLOSED on any
  mismatch (a missing binary/manifest is rebuilt from the pinned source).
  Rebuild manually with:

  ```bash
  cd /home/swirky/DevHub/repos/QntyLab-jh01-operational/qualifications/jh01_v0r3
  GOPROXY=off GOFLAGS=-mod=mod /home/swirky/.local/opt/go-1.26.0/bin/go \
    build -trimpath -buildvcs=false \
    -o ~/.local/opt/jh01-v0r3-verifier/bin/verify-v0r3-generic .
  ```

  (Prefer letting the caller rebuild: it also rewrites the identity manifest.)

## Re-arm procedure (after any stop)

```bash
# 1. Prove the operational checkout is canonical and clean:
git -C /home/swirky/DevHub/repos/QntyLab-jh01-operational fetch origin
git -C /home/swirky/DevHub/repos/QntyLab-jh01-operational status --porcelain
git -C /home/swirky/DevHub/repos/QntyLab-jh01-operational rev-parse HEAD origin/master

# 2. Re-install updated units, then:
systemctl --user daemon-reload
systemctl --user enable --now jh01-v1-prospective-record.timer
systemctl --user list-timers jh01-v1-prospective-record.timer
```

## Scheduling strategy

Frozen cadence: daily origins, `FIRST_LIVE_ORIGIN=2026-09-15` through
`LAST_LIVE_ORIGIN=2027-09-14`, each owning `[t, t+1h)` UTC. This systemd build
does not accept cross-year date ranges in calendar components, so the timer is
a plain daily recurrence at four bounded attempts inside each hourly window:

```
OnCalendar=*-*-* 00:05:00 UTC
OnCalendar=*-*-* 00:20:00 UTC
OnCalendar=*-*-* 00:35:00 UTC
OnCalendar=*-*-* 00:50:00 UTC
```

Out-of-window safety relies on the caller's fail-closed `NOT_DUE` behavior
(exit 3, marked as success via `SuccessExitStatus=3`). `Persistent=false`
guarantees no catch-up: a missed origin is never attempted after its window
(the frozen wrapper treats missed windows as terminal anyway).
`AccuracySec=1s`, `RandomizedDelaySec=0` keep triggers deterministic and
inside their windows.

## Window budget and start timeout

The service pins an explicit `TimeoutStartSec=840` (14 minutes). Reasoning:

- Without an explicit value, whether a long-running oneshot is killed at
  `DefaultTimeoutStartSec` (90 s) or runs unbounded is systemd
  version/build-dependent; an unpinned bound made the per-attempt window
  budget unverifiable (hostile review H1).
- Consecutive attempt triggers are 15 minutes apart (00:05/00:20/00:35/00:50).
  A 14-minute bound guarantees a running attempt can never overlap the next
  attempt slot, so each of the four bounded attempts keeps its own full window
  budget instead of one hung attempt consuming them all.
- `--now` is pinned by ExecStart at trigger time, so an attempt started at
  00:50 that finishes shortly after 01:00 still evaluates the correct due
  origin under frozen semantics.

## Archive reuse across attempts (digest-verified cache)

Every origin requires ~13 monthly archives × 20 symbols of materialization.
To keep a full attempt comfortably inside its window budget, the production
caller (`--record-due` with no injected provider) wraps the authenticated
archive downloader in a digest-verified reuse cache persisted under
`<state-dir>/jh01_v1_source_archive_cache_v0/`:

- Each fetched monthly archive zip plus its published CHECKSUM text is stored
  under a URL-digest-addressed filename.
- Before any reuse, the cached bytes are re-hashed and must match the digest
  published in the stored CHECKSUM; a missing or unverifiable entry is
  discarded and re-downloaded. No mutable unverified bytes ever enter the
  composition path (authority artifact constraint honored).
- Verification is a local SHA-256 over an already-fetched ~few-MB file — cheap
  relative to re-downloading ~260 archives inside the DUE window.
- Absent months (HTTP 404 → `None`) are not negatively cached; they fall to
  the REST tail exactly as designed and are cheaply re-probed next attempt.
- This cache is operational state only: it holds no ledger events and is never
  read by the frozen recorder or wrapper.

## Install (no sudo)

```bash
mkdir -p ~/.config/systemd/user
cp ops/systemd/user/jh01-v1-prospective-record.service ~/.config/systemd/user/
cp ops/systemd/user/jh01-v1-prospective-record.timer   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now jh01-v1-prospective-record.timer
```

## Verification after install

```bash
# 1. Next trigger must not be before 2026-09-15T00:05:00 UTC if installed
#    before first live origin; otherwise it must fall on one of the four
#    daily times 00:05/00:20/00:35/00:50 UTC.
systemctl --user list-timers jh01-v1-prospective-record.timer

# 2. No immediate service execution should have occurred:
systemctl --user status jh01-v1-prospective-record.service
journalctl --user -u jh01-v1-prospective-record.service --no-pager
# Expected: inactive (dead); no journal entries beyond install-time noise.

# 3. Campaign ledger unchanged by installation:
sha256sum ~/.local/state/qntylab/jh01_v1_real_prospective_operation_v0/jh01_v1_operation_events.jsonl

# 4. Linger enabled (timer survives logout):
loginctl show-user "$USER" --property=Linger
```

Pre-install syntax validation (already performed, see README history/receipts):

```bash
systemd-analyze verify ops/systemd/user/jh01-v1-prospective-record.service
systemd-analyze calendar '*-*-* 00:05:00 UTC'   # repeat for 00:20/00:35/00:50
```

## Uninstall / disable

```bash
systemctl --user disable --now jh01-v1-prospective-record.timer
rm ~/.config/systemd/user/jh01-v1-prospective-record.timer
rm ~/.config/systemd/user/jh01-v1-prospective-record.service
systemctl --user daemon-reload
systemctl --user reset-failed 'jh01-v1-prospective-record.*' 2>/dev/null || true
```

Disabling the timer alone fully stops future triggers; the service unit has no
`WantedBy` install section and can never self-start.

## Known limitations / risks

- `go` binary was not found on this host at creation time; the caller's
  offline sigstore reverify defaults to `go` resolved from the working
  directory context. If reverify requires go at a non-default absolute path,
  amend `ExecStart` with an explicit `--go-binary /absolute/path/to/go`.
- Daily out-of-window triggers run the caller and exit 3 (`NOT_DUE`) — this
  is expected fail-closed behavior, visible in the journal as successful
  no-op runs.
