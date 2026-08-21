import test from 'node:test'
import assert from 'node:assert/strict'
import { createGatedProvider, createMirroredGatedProvider } from '../lib/gated-provider.mjs'

function gateFor({ role = 'codex_initial', allow = true } = {}) {
  const events = []
  return {
    events,
    authorize(toolName) {
      events.push(`authorize:${toolName}`)
      if (!allow) throw new Error('denied')
      return { token: `${role}-1`, tool_name: toolName, role }
    },
    complete(grant, payload) {
      events.push(`complete:${grant.role}:${payload.status}`)
    },
  }
}

function rawProvider(calls, value = { ok: true }) {
  return {
    capabilities: {},
    async start() {
      calls.push('raw-start')
      return { id: 'run-1', result: Promise.resolve(value), dispose: async () => {} }
    },
  }
}

test('authorization precedes the pinned DSH provider start seam', async () => {
  const calls = []
  const gate = gateFor()
  const provider = createGatedProvider({ providerName: 'qntylab-gated-codex', toolName: 'subagent_codex', rawProvider: rawProvider(calls), gate })
  const run = await provider.start({})
  await run.result
  assert.deepEqual(calls, ['raw-start'])
  assert.deepEqual(gate.events, ['authorize:subagent_codex', 'complete:codex_initial:CHILD_COMPLETED'])
})

test('a denied gate never reaches the raw provider', async () => {
  const calls = []
  const gate = gateFor({ allow: false })
  const provider = createGatedProvider({ providerName: 'qntylab-gated-codex', toolName: 'subagent_codex', rawProvider: rawProvider(calls), gate })
  await assert.rejects(provider.start({}), /denied/)
  assert.deepEqual(calls, [])
})

test('review-required routing admits Claude only through its gated provider', async () => {
  const calls = []
  const gate = gateFor({ role: 'claude_initial' })
  const provider = createGatedProvider({ providerName: 'qntylab-gated-claude-code', toolName: 'subagent_claude_code', rawProvider: rawProvider(calls, { output: [{ type: 'text', text: '{"critical":[],"high":[],"medium":[],"low":[],"closure_blocking":false,"summary":"clean"}' }] }), gate })
  const run = await provider.start({})
  await run.result
  assert.deepEqual(calls, ['raw-start'])
  assert.equal(gate.events[0], 'authorize:subagent_claude_code')
})

test('replacement after authorization blocks before native raw start', async () => {
  const calls = []
  const first = rawProvider(calls)
  const replacement = rawProvider(calls)
  let current = first
  const gate = gateFor()
  const provider = createGatedProvider({
    providerName: 'qntylab-gated-codex',
    toolName: 'subagent_codex',
    rawProvider: first,
    resolveCurrent: () => current,
    gate,
  })
  current = replacement
  await assert.rejects(provider.start({}), /disappeared or was replaced/)
  assert.deepEqual(calls, [])
  assert.deepEqual(gate.events, [
    'authorize:subagent_codex',
    'complete:codex_initial:CHILD_FAILED',
  ])
})

test('malformed Claude review settles as malformed review exactly once', async () => {
  const calls = []
  const gate = gateFor({ role: 'claude_initial' })
  const provider = createGatedProvider({
    providerName: 'qntylab-gated-claude-code',
    toolName: 'subagent_claude_code',
    rawProvider: rawProvider(calls, { output: [{ type: 'text', text: '{not-json' }] }),
    gate,
  })
  const run = await provider.start({})
  await assert.rejects(run.result, /JSON|property name/)
  await run.dispose()
  assert.deepEqual(gate.events, [
    'authorize:subagent_claude_code',
    'complete:claude_initial:MALFORMED_REVIEW',
  ])
})

test('raw removal and reappearance mount a gated provider once per generation', () => {
  const events = []
  const rawOne = { name: 'codex', capabilities: {}, inheritsParentContext: false }
  const rawTwo = { name: 'codex', capabilities: {}, inheritsParentContext: false }
  const gated = { name: 'qntylab-gated-codex' }
  let present = rawOne
  let disposer
  const ctx = {
    subagents: {
      getProvider: name => name === 'codex' ? present : undefined,
      registerProvider: provider => { events.push(`mount:${provider.name}`); disposer = () => events.push('unmount'); return disposer },
    },
    on: (event, callback) => {
      if (event === 'subagent/provider-added') ctx.added = callback
      if (event === 'subagent/provider-removed') ctx.removed = callback
    },
  }
  const mirror = createMirroredGatedProvider({
    providerName: gated.name,
    toolName: 'subagent_codex',
    rawName: 'codex',
    ctx,
    gate: gateFor(),
  })
  assert.equal(mirror.mountedRaw, rawOne)
  ctx.removed('codex')
  present = rawTwo
  ctx.added(rawTwo)
  assert.deepEqual(events, ['mount:qntylab-gated-codex', 'unmount', 'mount:qntylab-gated-codex'])
  mirror.remove()
})
