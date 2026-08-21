import z from '@deepseek-ai/schemastery'
import { isAgentLoopRequest } from '@deepseek-ai/dsh-llm'
import { spawnSync } from 'node:child_process'

export const name = 'qntylab-parent-budget'
export const inject = ['llm']

export const Config = z.object({
  statePath: z.string().required(),
  qntyLabRoot: z.string().required(),
  pythonExecutable: z.string().default('python'),
})

function reserve(config, options) {
  const result = spawnSync(
    config.pythonExecutable,
    ['-m', 'qntylab.dsh_stage_a_v1r1_cli', '--state', config.statePath, 'reserve-parent', '--provider', options.provider, '--model', options.model, '--max-tokens', String(options.maxTokens ?? ''), '--retry-max', '0', '--agent-loop', String(isAgentLoopRequest(options)), ...(options.purpose === undefined ? [] : ['--purpose', options.purpose])],
    { cwd: config.qntyLabRoot, env: { PATH: process.env.PATH ?? '', PYTHONPATH: config.qntyLabRoot, PYTHONUNBUFFERED: '1' }, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] },
  )
  if (result.status !== 0) throw new Error((result.stderr || 'parent LLM request denied').trim())
}

export function apply(ctx, config) {
  ctx.on('llm/stream', (options, next) => {
    return async function* guardedParentStream() {
      reserve(config, options)
      yield* next()
    }()
  }, { global: true, prepend: true })
}
