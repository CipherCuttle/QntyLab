// V1R3R1 qualification-only scratch budget/controller gate. Mirrors the
// already-proven architecture in
// dsh_multi_agent_orchestration_stage_a_v1_hard_orchestration_authorization_v0/profile/qntylab-gated-provider/lib/gated-provider.mjs:
// reservation (authorize()) is awaited to completion BEFORE any adapter I/O
// (a rawProvider.start() call) is ever reached. This is a minimal, generic
// version of that same seam — a per-run request ceiling with no workflow
// state machine — for the V1R3R1 qualification's own scratch controller
// state (never the V1-hard-orchestration IMPLEMENT/TEST/REVIEW fixture,
// which is a different, task-specific gate).
import { readFileSync, writeFileSync, existsSync } from 'node:fs'

const MAX_PARENT_REQUEST_ATTEMPTS = 8

export function createBudgetGate(statePath) {
  function load() {
    if (!existsSync(statePath)) return { attempts: 0, log: [] }
    return JSON.parse(readFileSync(statePath, 'utf8'))
  }
  function save(state) {
    writeFileSync(statePath, JSON.stringify(state, null, 2))
  }
  return {
    // Reservation happens synchronously here, before the caller does any
    // adapter I/O — there is no I/O in this function at all, only a durable
    // counter increment, which is the strongest available proof that
    // reservation precedes adapter I/O: nothing can race it.
    authorize(toolName) {
      const state = load()
      const attemptNumber = state.attempts + 1
      const reservedAtUtc = new Date().toISOString()
      if (attemptNumber > MAX_PARENT_REQUEST_ATTEMPTS) {
        state.log.push({ attemptNumber, toolName, reservedAtUtc, decision: 'DENIED_CEILING' })
        save(state)
        throw new Error(`qualification-budget-gate: request ceiling reached (${MAX_PARENT_REQUEST_ATTEMPTS}); attempt ${attemptNumber} denied before adapter I/O`)
      }
      state.attempts = attemptNumber
      state.log.push({ attemptNumber, toolName, reservedAtUtc, decision: 'RESERVED' })
      save(state)
      return { attemptNumber, toolName, reservedAtUtc }
    },
  }
}
