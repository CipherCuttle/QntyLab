import { spawnSync } from 'node:child_process'

function scrubbedEnvironment(qntyLabRoot) {
  return {
    PATH: process.env.PATH ?? '',
    PYTHONPATH: qntyLabRoot,
    PYTHONUNBUFFERED: '1',
  }
}

export function reviewResultFromChild(value) {
  if (value && typeof value === 'object' && Array.isArray(value.output)) {
    const text = value.output
      .filter(block => block && block.type === 'text' && typeof block.text === 'string')
      .map(block => block.text)
      .join('')
    return JSON.parse(text)
  }
  if (value && typeof value === 'object' && !Array.isArray(value)) return value
  if (typeof value === 'string') return JSON.parse(value)
  throw new Error('Claude child did not return the required JSON review object')
}

export function createQntyLabGateClient({ statePath, qntyLabRoot, pythonExecutable = 'python' }) {
  function call(args) {
    const result = spawnSync(
      pythonExecutable,
      ['-m', 'qntylab.dsh_stage_a_v1_hard_orchestration', '--state', statePath, ...args],
      {
        cwd: qntyLabRoot,
        env: scrubbedEnvironment(qntyLabRoot),
        encoding: 'utf8',
        stdio: ['ignore', 'pipe', 'pipe'],
      },
    )
    if (result.error) throw result.error
    if (result.status !== 0) throw new Error((result.stderr || 'QntyLab gate denied').trim())
    return JSON.parse(result.stdout)
  }
  return {
    authorize(toolName) {
      return call(['authorize', toolName])
    },
    complete(grant, { status = 'CHILD_COMPLETED', reviewResult } = {}) {
      const args = ['complete', '--token', grant.token, '--tool', grant.tool_name, '--role', grant.role, '--status', status]
      if (reviewResult !== undefined) args.push('--review-json', JSON.stringify(reviewResult))
      return call(args)
    },
  }
}

export function createGatedProvider({ providerName, toolName, rawProvider, gate }) {
  return {
    name: providerName,
    capabilities: rawProvider.capabilities,
    inheritsParentContext: rawProvider.inheritsParentContext,
    async start(request) {
      // This is the DSH SubagentProvider.start seam. The persisted grant is
      // obtained before rawProvider.start can reach native Codex/Claude spawn.
      const grant = await Promise.resolve(gate.authorize(toolName))
      let settled = false
      const settle = async (status, reviewResult) => {
        if (settled) return
        settled = true
        await Promise.resolve(gate.complete(grant, { status, reviewResult }))
      }
      try {
        const run = await rawProvider.start(request)
        const result = Promise.resolve(run.result).then(
          async value => {
            const reviewResult = grant.role.startsWith('claude_') ? reviewResultFromChild(value) : undefined
            await settle('CHILD_COMPLETED', reviewResult)
            return value
          },
          async error => {
            await settle('CHILD_FAILED')
            throw error
          },
        )
        return {
          ...run,
          result,
          async dispose() {
            try {
              return await run.dispose()
            } finally {
              await settle('CHILD_TIMEOUT')
            }
          },
        }
      } catch (error) {
        await settle('CHILD_FAILED')
        throw error
      }
    },
  }
}
