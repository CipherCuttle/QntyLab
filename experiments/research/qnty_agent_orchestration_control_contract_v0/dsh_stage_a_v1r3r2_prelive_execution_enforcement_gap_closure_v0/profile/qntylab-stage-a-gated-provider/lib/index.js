import z from '@deepseek-ai/schemastery'
import { createGateClient, createGatedProvider, createMirroredGatedProvider } from './gated-provider.mjs'

export const name = 'qntylab-stage-a-gated-provider'
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
  return createMirroredGatedProvider({
    providerName: config.providerName,
    toolName: config.toolName,
    rawName: config.rawProvider,
    ctx,
    gate: createGateClient(config),
  })
}

export { createGateClient, createGatedProvider }
