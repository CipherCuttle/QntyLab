import { appendFileSync } from 'node:fs'

const path = process.env.QNTYLAB_STUB_INVOCATION_PATH
const provider = process.env.QNTYLAB_STUB_PROVIDER_NAME
const resolvedExecutable = process.env.QNTYLAB_STUB_RESOLVED_EXECUTABLE
if (!path || !provider || !resolvedExecutable) throw new Error('offline native stub configuration missing')
appendFileSync(path, `${JSON.stringify({
  provider,
  resolvedExecutable,
  openAiSentinelPresent: Object.hasOwn(process.env, 'OPENAI_API_KEY'),
})}\n`, { encoding: 'utf8', mode: 0o600 })
