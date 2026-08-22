import { spawnSync } from 'node:child_process'

function scrubbedGateEnvironment(qntyLabRoot) {
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

export function createGateClient({ statePath, qntyLabRoot, pythonExecutable = 'python' }) {
  function call(args) {
    const result = spawnSync(
      pythonExecutable,
      ['-m', 'qntylab.dsh_stage_a_v1r3r2_prelive_enforcement', ...args],
      {
        cwd: qntyLabRoot,
        env: scrubbedGateEnvironment(qntyLabRoot),
        encoding: 'utf8',
        stdio: ['ignore', 'pipe', 'pipe'],
      },
    )
    if (result.error) throw result.error
    if (result.status !== 0) {
      throw new Error((result.stderr || result.stdout || 'QntyLab child gate denied').trim())
    }
    return JSON.parse(result.stdout)
  }
  return {
    authorize(toolName, providerName, background = false) {
      return call([
        'authorize-child', '--state', statePath, '--tool', toolName,
        '--provider', providerName, ...(background ? ['--background'] : []),
      ])
    },
    complete(grant, { status = 'CHILD_COMPLETED', reviewResult } = {}) {
      const args = [
        'complete-child', '--state', statePath, '--token', grant.token,
        '--tool', grant.tool_name, '--role', grant.role, '--status', status,
      ]
      if (reviewResult !== undefined) args.push('--review-json', JSON.stringify(reviewResult))
      return call(args)
    },
  }
}

export function createGatedProvider({
  providerName,
  rawProviderName,
  toolName,
  rawProvider,
  resolveCurrent = () => rawProvider,
  gate,
}) {
  return {
    name: providerName,
    capabilities: rawProvider.capabilities,
    inheritsParentContext: rawProvider.inheritsParentContext,
    async start(request) {
      // The durable transition reservation completes before rawProvider.start,
      // the native Codex/Claude spawn boundary.
      const grant = await Promise.resolve(gate.authorize(toolName, rawProviderName, false))
      const current = resolveCurrent()
      if (current !== rawProvider) {
        await Promise.resolve(gate.complete(grant, { status: 'RAW_PROVIDER_REPLACED' }))
        throw new Error('qntylab-stage-a-gated-provider: raw provider disappeared or changed')
      }
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
            let reviewResult
            if (grant.role === 'claude_review' || grant.role === 'claude_rereview') {
              try {
                reviewResult = reviewResultFromChild(value)
              } catch (error) {
                await settle('MALFORMED_REVIEW')
                throw error
              }
            }
            await settle('CHILD_COMPLETED', reviewResult)
            return value
          },
          async error => {
            await settle('RAW_RESULT_FAILED')
            throw error
          },
        )
        return {
          ...run,
          result,
          async dispose() {
            try {
              return await run.dispose()
            } catch (error) {
              await settle('DISPOSE_FAILED')
              throw error
            } finally {
              await settle('CHILD_TIMEOUT')
            }
          },
        }
      } catch (error) {
        await settle('RAW_START_FAILED')
        throw error
      }
    },
  }
}

export function createMirroredGatedProvider({ providerName, toolName, rawName, ctx, gate }) {
  let disposeGated
  let mountedRaw

  function mount(rawProvider) {
    if (disposeGated !== undefined) return
    mountedRaw = rawProvider
    const wrapped = createGatedProvider({
      providerName,
      rawProviderName: rawName,
      toolName,
      rawProvider,
      resolveCurrent: () => ctx.subagents.getProvider(rawName),
      gate,
    })
    disposeGated = ctx.subagents.registerProvider(wrapped)
  }

  function remove() {
    if (disposeGated === undefined) return
    disposeGated()
    disposeGated = undefined
    mountedRaw = undefined
  }

  ctx.on('subagent/provider-added', provider => {
    if (provider.name === rawName) mount(provider)
  })
  ctx.on('subagent/provider-removed', name => {
    if (name === rawName) remove()
  })
  const present = ctx.subagents.getProvider(rawName)
  if (present !== undefined) mount(present)
  return { remove, get mountedRaw() { return mountedRaw } }
}
