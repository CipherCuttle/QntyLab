import { spawnSync } from 'node:child_process'

export const MAX_OUTPUT_TOKENS = 4096
export const PROVIDER_INTERNAL_RETRIES = 0
export const SERIALIZATION_OVERHEAD_TOKENS = 4096

function gateEnvironment(qntyLabRoot) {
  return {
    PATH: process.env.PATH ?? '',
    PYTHONPATH: qntyLabRoot,
    PYTHONUNBUFFERED: '1',
  }
}

function runPython(config, args) {
  const result = spawnSync(
    config.pythonExecutable,
    ['-m', 'qntylab.dsh_stage_a_v1r3r2_prelive_enforcement', ...args],
    {
      cwd: config.qntyLabRoot,
      env: gateEnvironment(config.qntyLabRoot),
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  )
  if (result.error) throw result.error
  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout || 'QntyLab parent gate denied').trim())
  }
  return JSON.parse(result.stdout)
}

export function inputTokenUpperBound(options) {
  const serialized = JSON.stringify({
    system: options.system,
    messages: options.messages,
    tools: options.tools,
    temperature: options.temperature,
    reasoningEffort: options.reasoningEffort,
    stop: options.stop,
  })
  // Every BPE token consumes at least one UTF-8 byte of model-facing text.
  // Doubling the complete internal request serialization plus fixed structural
  // overhead conservatively covers adapter field reshaping and chat framing.
  return (2 * Buffer.byteLength(serialized, 'utf8')) + SERIALIZATION_OVERHEAD_TOKENS
}

function containsUnpricedModality(value) {
  if (Array.isArray(value)) return value.some(containsUnpricedModality)
  if (value === null || typeof value !== 'object') return false
  if (
    typeof value.type === 'string'
    && /(?:image|audio|video|file)/i.test(value.type)
  ) return true
  return Object.values(value).some(containsUnpricedModality)
}

export function validateParentOptions(options, isAgentLoopRequest) {
  if (options.provider !== 'openai' || options.model !== 'gpt-5-mini') {
    throw new Error('BLOCK_COST: unexpected parent provider/model route')
  }
  if (!isAgentLoopRequest(options) || options.purpose !== undefined) {
    throw new Error('BLOCK_COST: auxiliary or non-agent-loop route denied')
  }
  if (!Number.isSafeInteger(options.maxTokens) || options.maxTokens <= 0 || options.maxTokens > MAX_OUTPUT_TOKENS) {
    throw new Error(`BLOCK_COST: request maxTokens must be within 1..${MAX_OUTPUT_TOKENS}`)
  }
  // This frozen price schedule covers text tokens only. Fail closed instead
  // of pretending that byte-length bounds price media or file modalities.
  if (containsUnpricedModality(options.messages)) {
    throw new Error('BLOCK_COST: unpriced non-text modality denied')
  }
  return inputTokenUpperBound(options)
}

export function createParentGuard(config, { isAgentLoopRequest, command = runPython } = {}) {
  if (typeof isAgentLoopRequest !== 'function') throw new Error('parent agent-loop classifier is required')
  let claimCompletedInThisProcess = false
  let logicalAttempts = 0

  function ensureClaim() {
    if (claimCompletedInThisProcess) return
    command(config, [
      'claim', '--state-dir', config.claimStateDir,
      '--remote', config.claimRemote,
      '--ref', config.claimRef,
      '--source-repo', config.claimSourceRepo,
      '--session-nonce', config.sessionNonce,
    ])
    // This in-memory bit deliberately is not durable. A process restart sees
    // the durable claim and fails closed instead of replaying the episode.
    claimCompletedInThisProcess = true
  }

  return {
    reserve(options) {
      const inputUpperBound = validateParentOptions(options, isAgentLoopRequest)
      ensureClaim()
      logicalAttempts += 1
      return command(config, [
        'reserve-parent', '--state', config.budgetStatePath,
        '--provider', options.provider, '--model', options.model,
        '--agent-loop', 'true', '--max-output-tokens', String(options.maxTokens),
        '--input-token-upper-bound', String(inputUpperBound),
        '--provider-internal-retries', String(PROVIDER_INTERNAL_RETRIES),
      ])
    },
    snapshot() {
      return { claimCompletedInThisProcess, logicalAttempts }
    },
  }
}

export function applyParentGuard(ctx, guard) {
  ctx.on('llm/stream', (options, next) => {
    return async function* guardedParentStream() {
      guard.reserve(options)
      // next() is the first operation that can reach the selected adapter.
      yield* next()
    }()
  }, { global: true, prepend: true })
}
