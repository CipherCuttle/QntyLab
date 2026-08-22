#!/usr/bin/env node
// QntyLab qualification-only loopback OpenAI-compatible mock
// (DSH_STAGE_A_V1R3_LAUNCH_PLANE_QUALIFICATION_V0).
//
// The plan calls for reusing the pinned source's own
// `packages/test-support/llm-mock-server`. This offline qualification
// environment does not have a materialized pinned DSH checkout available to
// import that package from, so this file is a small, self-contained
// stand-in that satisfies the same behavioral contract the plan requires:
// bound to localhost only, exactly one deterministic plain-assistant
// completion per request, no tool call, and the request it received is
// inspectable afterward. This is a known, deliberate deviation from literal
// package reuse — flagged in PHASE.md rather than left silent — not a claim
// that this is the pinned package itself.
//
// It speaks the OpenAI Chat Completions wire shape
// (`POST /v1/chat/completions`) by default; pass `wireProtocol: 'responses'`
// if implementation-time verification against the pinned adapter's actual
// tests (`sdk-options.spec.ts` / `provider-apis.e2e.ts`) finds it speaks the
// Responses API instead — that check is a named PLAN RISK, not assumed here.
//
// CORRECTED IN V1R3R1 AGAINST THE REAL PINNED llm-pi-ai ADAPTER: real
// materialization proved the pinned `@earendil-works/pi-ai` openai-completions
// route always requests `stream: true`
// (`packages/llm/llm-pi-ai` -> `dist/api/openai-completions.js`) and parses
// an SSE `chat.completion.chunk` stream, throwing `Stream ended without
// finish_reason` on a single-shot plain JSON body — a real full-profile boot
// against the original plain-JSON version of this mock reproduced exactly
// that error and caused `dsh-llm-retry` to resend the request three
// additional times. This is a corrected QntyLab-owned mock generated
// directly from that evidence, not a silent assumption.

import { createServer } from 'node:http'
import { randomUUID } from 'node:crypto'

export function createQualificationMock({
  model = 'gpt-5-mini',
  completionText = 'Qualification loopback response. No tool call.',
  wireProtocol = 'chat.completions',
} = {}) {
  const requests = []

  const server = createServer((req, res) => {
    const chunks = []
    req.on('data', chunk => chunks.push(chunk))
    req.on('end', () => {
      let body
      try {
        body = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}')
      } catch {
        res.writeHead(400, { 'content-type': 'application/json' })
        res.end(JSON.stringify({ error: 'invalid JSON body' }))
        return
      }
      requests.push({ path: req.url, method: req.method, body, receivedAtUtc: new Date().toISOString() })

      if (wireProtocol === 'responses') {
        const responseBody = {
          id: 'qual-resp-1',
          object: 'response',
          model,
          status: 'completed',
          output: [
            {
              type: 'message',
              role: 'assistant',
              content: [{ type: 'output_text', text: completionText }],
            },
          ],
          usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
        }
        res.writeHead(200, { 'content-type': 'application/json' })
        res.end(JSON.stringify(responseBody))
        return
      }

      if (body.stream !== true) {
        const responseBody = {
          id: 'qual-cmpl-1',
          object: 'chat.completion',
          model,
          choices: [
            {
              index: 0,
              message: { role: 'assistant', content: completionText },
              finish_reason: 'stop',
            },
          ],
          usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
        }
        res.writeHead(200, { 'content-type': 'application/json' })
        res.end(JSON.stringify(responseBody))
        return
      }

      // Real pinned adapter path: emit a minimal, valid
      // `chat.completion.chunk` SSE stream — one role-opening chunk, one
      // content chunk carrying the whole deterministic completion text, one
      // finish_reason chunk, then `[DONE]`.
      const id = `qual-cmpl-${randomUUID()}`
      const created = Math.floor(Date.now() / 1000)
      const base = { id, object: 'chat.completion.chunk', created, model }
      const chunks_ = [
        { ...base, choices: [{ index: 0, delta: { role: 'assistant', content: '' }, finish_reason: null }] },
        { ...base, choices: [{ index: 0, delta: { content: completionText }, finish_reason: null }] },
        { ...base, choices: [{ index: 0, delta: {}, finish_reason: 'stop' }] },
      ]
      res.writeHead(200, {
        'content-type': 'text/event-stream',
        'cache-control': 'no-cache',
        connection: 'keep-alive',
      })
      for (const c of chunks_) res.write(`data: ${JSON.stringify(c)}\n\n`)
      res.write('data: [DONE]\n\n')
      res.end()
    })
  })

  return {
    server,
    requests,
    async listen(port = 0) {
      await new Promise((resolve, reject) => {
        server.once('error', reject)
        server.listen(port, '127.0.0.1', () => resolve())
      })
      const address = server.address()
      return `http://127.0.0.1:${address.port}`
    },
    async close() {
      await new Promise(resolve => server.close(() => resolve()))
    },
  }
}
