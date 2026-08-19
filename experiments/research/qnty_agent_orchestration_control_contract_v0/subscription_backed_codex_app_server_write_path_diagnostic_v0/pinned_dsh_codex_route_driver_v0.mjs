#!/usr/bin/env node
/**
 * Frozen lab-only driver for diagnostic route D4: the pinned DSH Codex provider.
 *
 * It delegates one turn through DSH's own SubagentRuntime and `subagent-codex`
 * provider against the real subscription-backed Codex Profile A binary, and
 * prints exactly one JSON line.  It records what DSH actually does, and never
 * asserts effective parity from a QntyLab-side declaration.
 *
 * Inputs come from the environment so the argv stays fixed:
 *   QNTYLAB_PRODUCT_CWD  - disposable workspace, also the DSH parent session cwd
 *   QNTYLAB_PROFILE      - CODEX_HOME for Codex Profile A
 *   QNTYLAB_CODEX_BINDIR - directory prepended to PATH so `codex` is the pinned binary
 *   QNTYLAB_PROMPT_FILE  - file holding the exact frozen prompt bytes
 *   QNTYLAB_TURN_TIMEOUT_MS - bounded single-attempt deadline
 *   QNTYLAB_DSH_ROOT     - pinned DSH worktree root, imported by absolute path
 *                          so module resolution never depends on the workspace
 */

import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { delimiter } from 'node:path'

function emit(payload) {
  process.stdout.write(JSON.stringify(payload) + '\n')
}

function fail(error, extra = {}) {
  emit({
    status: 'FAIL_CLOSED',
    output: '',
    error,
    route: 'D4_PINNED_DSH_CODEX_PROVIDER',
    parentLlmProvider: 'NONE',
    parentLlmRequestCount: 0,
    ...extra,
  })
  process.exit(1)
}

const cwd = process.env.QNTYLAB_PRODUCT_CWD
const scope = process.env.QNTYLAB_WORKSPACE_SCOPE
const codexHome = process.env.QNTYLAB_PROFILE
const binDir = process.env.QNTYLAB_CODEX_BINDIR
const promptFile = process.env.QNTYLAB_PROMPT_FILE
const dshRoot = process.env.QNTYLAB_DSH_ROOT
const timeoutMs = Number(process.env.QNTYLAB_TURN_TIMEOUT_MS || '300000')

if (!cwd || !scope || cwd !== scope) fail('dsh driver cwd/scope binding is missing or divergent')
if (!codexHome || !binDir || !promptFile || !dshRoot) fail('dsh driver inputs are incomplete')

for (const name of ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'DEEPSEEK_API_KEY', 'OPENROUTER_API_KEY']) {
  if (process.env[name]) fail(`pay-per-token credential present in dsh route: ${name}`)
}

const prompt = readFileSync(promptFile, 'utf8')
const promptSha256 = createHash('sha256').update(prompt).digest('hex')

let Context, SubagentRuntime, LocalSubprocessRuntime, codexPlugin
try {
  // Absolute-path imports: the disposable workspace is outside the DSH tree,
  // so bare-specifier resolution from cwd would not find the pinned packages.
  ;({ Context } = await import(`${dshRoot}/vendor/cordis/lib/index.js`))
  SubagentRuntime = (await import(`${dshRoot}/packages/subagent/subagent/lib/index.js`)).default
  LocalSubprocessRuntime = (await import(`${dshRoot}/packages/subprocess/subprocess-local/lib/index.js`)).default
  codexPlugin = await import(`${dshRoot}/packages/subagent/subagent-codex/lib/index.js`)
} catch (error) {
  fail(`pinned dsh module resolution failed: ${error.message}`, {
    inconclusiveInfra: 'PINNED_DSH_BUILD_OUTPUT_UNAVAILABLE',
  })
}

// The provider spawns bare `codex app-server --stdio`, so PATH selects the
// product identity.  This is recorded, not assumed.
const childEnv = {
  CODEX_HOME: codexHome,
  PATH: `${binDir}${delimiter}${process.env.PATH ?? ''}`,
}

const observed = {
  requestedCwd: cwd,
  codexHome,
  pathPrefix: binDir,
  dshRoot,
  childEnvKeys: Object.keys(childEnv).sort(),
  providerName: 'codex',
  promptSha256,
}

const started = new Date().toISOString()
const controller = new AbortController()
const timer = setTimeout(() => controller.abort(), timeoutMs)
let timedOut = false
controller.signal.addEventListener('abort', () => { timedOut = true })

const ctx = new Context()
let run
let result = null
let failure = null
try {
  await ctx.plugin(SubagentRuntime)
  await ctx.plugin(LocalSubprocessRuntime)
  await ctx.plugin(codexPlugin, { env: childEnv, disposeGraceMs: 5_000 })
  const parent = { id: 'qntylab-write-path-diagnostic', session: { header: { cwd } } }
  run = await ctx.subagents.start('codex', {
    prompt: [{ type: 'text', text: prompt }],
    parent,
    signal: controller.signal,
  })
  result = await run.result
} catch (error) {
  failure = error instanceof Error ? error.message : String(error)
} finally {
  clearTimeout(timer)
  try { if (run) await run.dispose() } catch (error) { failure ??= `dispose failed: ${error.message}` }
  try { await ctx.fiber.dispose() } catch { /* disposal is best effort */ }
}

const stopReason = result?.stopReason ?? (timedOut ? 'timeout' : 'missing')
const outputParts = Array.isArray(result?.output) ? result.output : []
const outputText = outputParts
  .filter(part => part && part.type === 'text' && typeof part.text === 'string')
  .map(part => part.text)
  .join('\n')

emit({
  status: stopReason === 'completed' ? 'COMPLETED' : 'FAIL_CLOSED',
  // Assistant prose is never emitted; only its digest and shape.
  output: outputText ? `agentOutputSha256:${createHash('sha256').update(outputText).digest('hex')}` : 'NO_AGENT_OUTPUT',
  lifecycle: { ends: [{ stopReason }] },
  processes: [{ signal: 'SIGTERM' }],
  parentLlmProvider: 'NONE',
  parentLlmRequestCount: 0,
  route: 'D4_PINNED_DSH_CODEX_PROVIDER',
  startedAt: started,
  endedAt: new Date().toISOString(),
  timedOut,
  error: failure,
  observed,
  outputPartCount: outputParts.length,
})
