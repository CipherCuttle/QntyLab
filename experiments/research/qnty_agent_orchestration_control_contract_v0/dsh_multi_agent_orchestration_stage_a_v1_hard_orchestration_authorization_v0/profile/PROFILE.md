# Stage-A V1 hard-gated runnable profile

This profile is the frozen V1 integration contract for the pinned DSH
materialization. Copy `package.json`, `cordis.patch.yml`, and the
`qntylab-gated-provider/` directory to
`$DSH_HOME/profiles/stage-a-v1-hard-orchestration/` in the disposable build.

The two raw providers register their normal DSH names (`codex` and
`claude-code`). The QntyLab plugin then registers
`qntylab-gated-codex` and `qntylab-gated-claude-code`, each implementing the
real pinned `SubagentProvider.start(request)` seam. Its first operation is a
synchronous JSON CLI authorization against the crash-safe QntyLab checkpoint;
only a successful grant reaches the raw provider. The model-facing tools are
bound exclusively to the gated names. The pinned `dsh-base` generic
`tool-subagent` (`spawn`), `tool-subagent-fork` (`fork`), `tool-workflow`, and
`tool-ralph` child-creation rows, plus their generic child control/backends,
are explicitly disabled in this profile. The final composed model-facing
child surface therefore contains only `subagent_codex` and
`subagent_claude_code`; a raw provider, alias, fork, or workflow route is not
executable.

The disabled-row decision is based on the pinned commit
`99f6f02fecdb7dff40c3fbc9470f5907c29f74ca`, specifically
`packages/bundle/base/cordis.patch.yml` and the pinned
`packages/workflow/tool-workflow/README.md` / `packages/workflow/tool-ralph/README.md`
semantics. The offline profile tests apply the actual id-patch composition
rules to those discovered base rows and inspect the final enabled surface.

Before launching DSH, set `QNTYLAB_ROOT` to the QntyLab checkout,
`QNTYLAB_DSH_STAGE_A_STATE_PATH` to the phase checkpoint, and
`QNTYLAB_PYTHON` to the intended Python executable. The gate helper passes
only `PATH`, `PYTHONPATH`, and `PYTHONUNBUFFERED` to its own process; it never
forwards OpenAI or child-provider credentials.

Offline proof:

```sh
node qntylab-gated-provider/test/gated-provider.test.mjs
```

No live DSH, OpenAI, Codex, Claude, or parent-model call is part of this
authorization repair.
