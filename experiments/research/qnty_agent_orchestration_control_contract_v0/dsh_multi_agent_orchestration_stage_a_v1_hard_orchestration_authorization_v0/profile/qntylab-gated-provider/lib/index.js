import z from '@deepseek-ai/schemastery'
import { createGatedProvider, createQntyLabGateClient } from './gated-provider.mjs'

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
  const rawProvider = ctx.subagents.getProvider(config.rawProvider)
  if (rawProvider === undefined) {
    throw new Error(`qntylab-gated-provider: raw provider is not registered: ${config.rawProvider}`)
  }
  ctx.subagents.registerProvider(createGatedProvider({
    providerName: config.providerName,
    toolName: config.toolName,
    rawProvider,
    gate: createQntyLabGateClient(config),
  }))
}

export { createGatedProvider, createQntyLabGateClient }
