import z from '@deepseek-ai/schemastery'

export const name = 'qntylab-stage-a-stub-provider'
export const inject = ['subagents', 'subprocess']

export const Config = z.object({
  providerName: z.string().required(),
  invocationPath: z.string().required(),
  stubExecutable: z.string().required(),
  responseMode: z.string().default('clean'),
  env: z.dict(z.string()).default({}),
})

function review(high) {
  return JSON.stringify({
    critical: [],
    high: high ? [{ id: 'H-STUB', summary: 'offline hostile finding' }] : [],
    medium: [],
    low: [],
    closure_blocking: high,
    summary: 'offline native stub review',
  })
}

export function apply(ctx, config) {
  let calls = 0
  ctx.subagents.registerProvider({
    name: config.providerName,
    capabilities: {},
    inheritsParentContext: false,
    async start(request) {
      calls += 1
      const parentCwd = request.parent.session.header.cwd
      const executableName = config.providerName === 'codex' ? 'codex' : 'claude'
      const resolvedExecutable = await ctx.subprocess.resolveExecutable(
        executableName,
        config.env,
        request.signal,
      )
      const child = ctx.subprocess.spawn({
        argv: [process.execPath, config.stubExecutable],
        cwd: parentCwd,
        stdio: { stdin: 'ignore', stdout: 'ignore', stderr: 'pipe' },
        graceMs: 1_000,
        env: {
          QNTYLAB_STUB_PROVIDER_NAME: config.providerName,
          QNTYLAB_STUB_INVOCATION_PATH: config.invocationPath,
          QNTYLAB_STUB_RESOLVED_EXECUTABLE: resolvedExecutable,
        },
      })
      const text = config.providerName === 'claude-code'
        ? review(config.responseMode === 'high-first' && calls === 1)
        : 'offline Codex native stub completed'
      const result = child.done.then(outcome => {
        if (outcome.exitCode !== 0) throw new Error(`offline native stub exited ${outcome.exitCode}`)
        return { output: [{ type: 'text', text }], stopReason: 'completed' }
      })
      return {
        id: `offline-${config.providerName}-${calls}`,
        signal: request.signal,
        result,
        cancel() {},
        async dispose() {
          if (child.pid > 0) {
            child.terminate()
            await child.waitForExit()
          }
          await child.done
        },
      }
    },
  })
}
