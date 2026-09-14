# Order Flow Prospective V1 — local activation

This scheduler is intentionally local. The post-repair live probe passed from
the trusted non-US operator host, while GitHub-hosted US runners were blocked
by the frozen Binance USD-M source. GitHub Actions therefore remains CI-only;
it must not perform real provider access for this campaign.

The operational checkout is separate from the development checkout:

```bash
cd /home/swirky/DevHub/repos/QntyLab
git fetch origin master

test ! -e /home/swirky/DevHub/repos/QntyLab-orderflow-operational
git worktree add --detach \
  /home/swirky/DevHub/repos/QntyLab-orderflow-operational \
  origin/master
```

Before enabling the timer, verify GitHub CLI authentication. The local caller
uses `gh` only to publish and independently restore immutable cumulative
evidence releases; it does not use GitHub Actions for source acquisition.

```bash
gh auth status

cd /home/swirky/DevHub/repos/QntyLab-orderflow-operational
/usr/bin/python3 -m qntylab.order_flow_prospective_v1_operation \
  --status \
  --root /home/swirky/DevHub/repos/QntyLab-orderflow-operational
```

Install the user units without sudo:

```bash
mkdir -p ~/.config/systemd/user
cp /home/swirky/DevHub/repos/QntyLab-orderflow-operational/ops/systemd/user/order-flow-v1-prospective-record.service \
  ~/.config/systemd/user/
cp /home/swirky/DevHub/repos/QntyLab-orderflow-operational/ops/systemd/user/order-flow-v1-prospective-record.timer \
  ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable --now order-flow-v1-prospective-record.timer
systemctl --user list-timers order-flow-v1-prospective-record.timer
systemctl --user status order-flow-v1-prospective-record.timer --no-pager
```

Do **not** manually invoke `--record-due` as an extra retry. The four timer
attempts per UTC hour are the bounded retry budget. `Persistent=false` prevents
systemd catch-up. If a logical close is already outside its one-hour recording
window, the caller records `WINDOW_MISSED` without provider access and never
backfills it.

The first real warmup logical close is `2026-09-15T00:00:00Z`. Interim model
evaluation, p-values, support decisions, Router/Qnty/QntySpot use, trading,
signing, submission, and capital authority remain forbidden.


## Canonical state + host binding

Production recording is pinned to `/home/swirky/.local/state/qntylab/order_flow_prospective_v1`. `XDG_STATE_HOME` and
`--state-dir` are not authority overrides for canonical recording. Before any
provider access, the runtime verifies a campaign-specific contextual fingerprint
of `/etc/machine-id` against the Git-backed trusted-host binding and reconciles
the local cumulative ledger with the latest immutable GitHub evidence release.
A missing/older local ledger is restored from the remote immutable head; any
divergence, competing draft, or more-than-one unanchored local event fails
closed. The reusable raw machine-id digest is not stored in Git.
