import test from 'node:test'
import assert from 'node:assert/strict'
import { createGatedProvider } from '../lib/gated-provider.mjs'

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
