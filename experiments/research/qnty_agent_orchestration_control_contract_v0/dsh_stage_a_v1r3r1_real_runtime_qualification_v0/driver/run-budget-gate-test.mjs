import { createBudgetGate } from '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1/mock/qualification-budget-gate.mjs'

const gate = createBudgetGate('/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1/state/budget-gate.json')

for (let i = 1; i <= 8; i += 1) {
  const grant = gate.authorize('subagent_codex')
  console.log(`attempt ${i}: RESERVED`, grant)
}

try {
  gate.authorize('subagent_codex')
  console.log('attempt 9: UNEXPECTEDLY RESERVED (FAIL)')
  process.exit(1)
} catch (err) {
  console.log('attempt 9: DENIED as expected ->', err.message)
}
