import z from '@deepseek-ai/schemastery'
import { createGatedProvider, createMirroredGatedProvider, createQntyLabGateClient } from './gated-provider.mjs'

export const name = 'qntylab-gated-provider'
export const inject = ['subagents']

export const Config = z.object({
  providerName: z.string().required(),
  rawProvider: z.string().required(),
  toolName: z.string().required(),
  statePath: z.string().required(),
  qntyLabRoot: z.string().required(),
  pythonExecutable: z.string().default('python'),
})

export function apply(ctx, config) {
  // Lifecycle listeners are installed before the presence check. Raw provider
  // fibers and this gate may activate in either order; neither path performs
  // an invalid apply-time lookup or waits on patch-list order.
  return createMirroredGatedProvider({
    providerName: config.providerName,
    toolName: config.toolName,
    rawName: config.rawProvider,
    ctx,
    gate: createQntyLabGateClient(config),
  })
}

export { createGatedProvider, createQntyLabGateClient }
