import z from '@deepseek-ai/schemastery'
import { isAgentLoopRequest } from '@deepseek-ai/dsh-llm'
import { applyParentGuard, createParentGuard } from './guard.mjs'

export const name = 'qntylab-stage-a-parent-enforcement'
export const inject = ['llm']

const SHA256_RE = /^[0-9a-fA-F]{64}$/
const EXACT_COMMIT_RE = /^[0-9a-fA-F]{40,64}$/
const REVOCATION_STATES = ['NOT_REVOKED', 'REVOKED', 'SUPERSEDED']

export const Config = z.object({
  budgetStatePath: z.string().required(),
  claimStateDir: z.string().required(),
  claimRemote: z.string().required(),
  claimRef: z.string().required(),
  claimSourceRepo: z.string().required(),
  sessionNonce: z.string().required(),
  // Claim binding — the COMPLETE binding the operational owner requires before
  // any irreversible claim. All fields must be present and well-formed BEFORE a
  // guard can be constructed. There is NO optional production semantics and NO
  // default revocationState: a missing or malformed value fails at Config
  // validation, ahead of guard construction and any claim reserve.
  authorizedExecutionSourceSha: z.string()
    .regex(EXACT_COMMIT_RE, 'authorized execution source SHA must be an exact immutable commit identity')
    .required(),
  executionContractRoot: z.string()
    .regex(SHA256_RE, 'execution contract root must be a valid sha256')
    .required(),
  runtimeIdentityDigest: z.string()
    .regex(SHA256_RE, 'runtime identity digest must be a valid sha256')
    .required(),
  executableIdentityDigest: z.string()
    .regex(SHA256_RE, 'executable identity digest must be a valid sha256')
    .required(),
  revocationState: z.enum(REVOCATION_STATES).required(),
  qntyLabRoot: z.string().required(),
  pythonExecutable: z.string().default('python'),
})

export function apply(ctx, config) {
  applyParentGuard(ctx, createParentGuard(config, { isAgentLoopRequest }))
}

export { createParentGuard }
