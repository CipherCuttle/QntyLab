import z from '@deepseek-ai/schemastery'
import { isAgentLoopRequest } from '@deepseek-ai/dsh-llm'
import { applyParentGuard, createParentGuard } from './guard.mjs'

export const name = 'qntylab-stage-a-parent-enforcement'
export const inject = ['llm']

export const Config = z.object({
  budgetStatePath: z.string().required(),
  claimStateDir: z.string().required(),
  claimRemote: z.string().required(),
  claimRef: z.string().required(),
  claimSourceRepo: z.string().required(),
  sessionNonce: z.string().required(),
  qntyLabRoot: z.string().required(),
  pythonExecutable: z.string().default('python'),
})

export function apply(ctx, config) {
  applyParentGuard(ctx, createParentGuard(config, { isAgentLoopRequest }))
}

export { createParentGuard }
