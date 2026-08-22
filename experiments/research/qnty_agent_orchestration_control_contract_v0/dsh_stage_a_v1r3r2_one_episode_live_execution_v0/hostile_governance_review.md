# Hostile governance review — DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0

This single independent hostile review attacks the activation candidate's
authority boundary, predecessor binding, runtime identity, claim mechanism,
episode and budget limits, Claude policy, and zero-live-action receipts.

## Review result

- Critical: 0
- High: 0
- Medium: 0
- Low: 0

The branch-local candidate cannot self-authorize: its effective predecessor is
PR #182 at reviewed head `cdf5282c4cae4dd219fad1dbe6020db475ad6381`, and the
candidate base and canonical merge are exact `origin/master` SHA
`0dbd9ee0dceb9c6dab9781816230b5518c1de490`. The candidate remains ineffective
until this activation PR is independently reviewed and merged.

The candidate binds the exact V1R3R2 launch, manifest, executable, launch
policy, Codex repair, and Claude repair digests, while rejecting the old V1R3R1
authority. It binds the pinned DSH commit/tree/tag, the fresh create-only
remote claim ref plus local O_EXCL receipt, and requires both claim halves
before provider I/O. The claim is not created during activation.

The post-merge execution project is bounded to exactly one initially
unconsumed episode, no second episode, no whole-episode retry, and one draft
closure PR. Parent and child ceilings remain unchanged, Claude is hard
Read/Glob/Grep-only with no persistence or MCP, and the fixture/workspace
containment rules are preserved.

No secret is read; DSH, model, child, fixture, and spend counters remain zero;
Stage B and Qnty, trading, capital, scientific, and QntyAgentEval authority
remain denied. No targeted rereview is required.
