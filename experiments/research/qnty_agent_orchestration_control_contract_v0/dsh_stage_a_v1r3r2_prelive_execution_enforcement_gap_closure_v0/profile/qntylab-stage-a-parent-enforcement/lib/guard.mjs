import { spawnSync } from 'node:child_process'

export const MAX_OUTPUT_TOKENS = 4096
export const PROVIDER_INTERNAL_RETRIES = 0
export const SERIALIZATION_OVERHEAD_TOKENS = 4096

const SHA256_RE = /^[0-9a-fA-F]{64}$/
const EXACT_COMMIT_RE = /^[0-9a-fA-F]{40,64}$/
const REVOCATION_STATES = new Set(['NOT_REVOKED', 'REVOKED', 'SUPERSEDED'])

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

/**
 * Validate the complete claim binding BEFORE any irreversible claim is
 * COMMITTED. Fails closed on any missing/malformed value; never substitutes a
 * HEAD/master/origin/master identity, never sha256(source_sha), never defaults
 * revocationState.
 */
export function validateClaimBindingConfig(config) {
  for (const key of ['authorizedExecutionSourceSha', 'executionContractRoot', 'runtimeIdentityDigest', 'executableIdentityDigest']) {
    if (typeof config[key] !== 'string') throw new Error(`BLOCK_CLAIM_BINDING: ${key} is required`)
  }
  if (!EXACT_COMMIT_RE.test(config.authorizedExecutionSourceSha)) {
    throw new Error('BLOCK_CLAIM_BINDING: authorizedExecutionSourceSha must be an exact immutable commit identity')
  }
  if (!SHA256_RE.test(config.executionContractRoot)) {
    throw new Error('BLOCK_CLAIM_BINDING: executionContractRoot is not a valid sha256')
  }
  if (!SHA256_RE.test(config.runtimeIdentityDigest)) {
    throw new Error('BLOCK_CLAIM_BINDING: runtimeIdentityDigest is not a valid sha256')
  }
  if (!SHA256_RE.test(config.executableIdentityDigest)) {
    throw new Error('BLOCK_CLAIM_BINDING: executableIdentityDigest is not a valid sha256')
  }
  if (typeof config.revocationState !== 'string' || !REVOCATION_STATES.has(config.revocationState)) {
    throw new Error('BLOCK_CLAIM_BINDING: revocationState must be an explicit canonical state')
  }
  // Fail closed on revoked/superseded authority BEFORE any claim attempt,
  // budget reservation, or provider I/O. The Python seam also blocks these,
  // but the guard is the sole claim owner and must not even attempt a claim.
  if (config.revocationState === 'REVOKED' || config.revocationState === 'SUPERSEDED') {
    throw new Error(`BLOCK_CLAIM_BINDING: claim source authority is revoked or superseded: ${config.revocationState}`)
  }
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
    // The COMPLETE claim binding is validated and passed to the Python claim
    // entrypoint exactly as supplied. No value is replaced by HEAD, master,
    // origin/master, sha256(source_sha), or a hardcoded contract root; no
    // default revocationState is invented.
    validateClaimBindingConfig(config)
    command(config, [
      'claim', '--state-dir', config.claimStateDir,
      '--remote', config.claimRemote,
      '--ref', config.claimRef,
      '--source-repo', config.claimSourceRepo,
      '--session-nonce', config.sessionNonce,
      '--authorized-execution-source-sha', config.authorizedExecutionSourceSha,
      '--execution-contract-root', config.executionContractRoot,
      '--runtime-identity-digest', config.runtimeIdentityDigest,
      '--executable-identity-digest', config.executableIdentityDigest,
      '--revocation-state', config.revocationState,
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
