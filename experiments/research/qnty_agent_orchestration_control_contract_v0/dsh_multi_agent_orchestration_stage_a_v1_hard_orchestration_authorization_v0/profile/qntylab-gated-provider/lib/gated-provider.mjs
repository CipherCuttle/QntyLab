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

export function createGatedProvider({ providerName, toolName, rawProvider, resolveCurrent = () => rawProvider, gate }) {
  return {
    name: providerName,
    capabilities: rawProvider.capabilities,
    inheritsParentContext: rawProvider.inheritsParentContext,
    async start(request) {
      // This is the DSH SubagentProvider.start seam. The persisted grant is
      // obtained before rawProvider.start can reach native Codex/Claude spawn.
      const grant = await Promise.resolve(gate.authorize(toolName))
      // The authorization reservation is intentionally before this identity
      // check. A provider removal/replacement after reservation consumes the
      // grant and blocks infrastructure without reaching native start().
      const current = resolveCurrent()
      if (current !== rawProvider) {
        await Promise.resolve(gate.complete(grant, { status: 'CHILD_FAILED' }))
        throw new Error('qntylab-gated-provider: raw provider disappeared or was replaced')
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
            if (grant.role.startsWith('claude_')) {
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

  // Register both listeners before observing current presence. This mirrors
  // pinned tool-subagent and is safe when either provider fiber activates first.
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
