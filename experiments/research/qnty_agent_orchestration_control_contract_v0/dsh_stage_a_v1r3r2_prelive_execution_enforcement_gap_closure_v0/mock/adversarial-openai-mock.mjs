import { createServer } from 'node:http'
import { randomUUID } from 'node:crypto'

export function createAdversarialOpenAiMock({
  model = 'gpt-5-mini',
  completionText = 'Qualification loopback response. No tool call.',
  behavior = 'success',
  toolScript = [],
} = {}) {
  const requests = []
  const sockets = new Set()
  const server = createServer((req, res) => {
    const bodyChunks = []
    req.on('data', chunk => bodyChunks.push(chunk))
    req.on('end', () => {
      let body
      try {
        body = JSON.parse(Buffer.concat(bodyChunks).toString('utf8') || '{}')
      } catch {
        res.writeHead(400, { 'content-type': 'application/json' })
        res.end(JSON.stringify({ error: { message: 'invalid JSON body' } }))
        return
      }
      requests.push({
        path: req.url,
        method: req.method,
        body,
        authorization: req.headers.authorization,
      })
      const scriptedTool = toolScript[requests.length - 1]
      if (behavior === 'connection') {
        req.socket.destroy()
        return
      }
      if (behavior === 'timeout') return
      if (behavior === '429' || behavior === '500') {
        const status = Number(behavior)
        res.writeHead(status, { 'content-type': 'application/json' })
        res.end(JSON.stringify({ error: { message: `offline ${behavior}`, type: 'offline_mock' } }))
        return
      }
      const id = `offline-cmpl-${randomUUID()}`
      const created = Math.floor(Date.now() / 1000)
      const base = { id, object: 'chat.completion.chunk', created, model }
      const responseChunks = scriptedTool === undefined
        ? [
        { ...base, choices: [{ index: 0, delta: { role: 'assistant', content: '' }, finish_reason: null }] },
        { ...base, choices: [{ index: 0, delta: { content: completionText }, finish_reason: null }] },
        { ...base, choices: [{ index: 0, delta: {}, finish_reason: 'stop' }] },
        ]
        : [
            {
              ...base,
              choices: [{
                index: 0,
                delta: {
                  role: 'assistant',
                  content: '',
                  tool_calls: [{
                    index: 0,
                    id: `offline-tool-${requests.length}`,
                    type: 'function',
                    function: { name: scriptedTool, arguments: '' },
                  }],
                },
                finish_reason: null,
              }],
            },
            {
              ...base,
              choices: [{
                index: 0,
                delta: {
                  tool_calls: [{
                    index: 0,
                    function: {
                      arguments: JSON.stringify({
                        description: 'offline hostile call',
                        prompt: `offline ${scriptedTool} task`,
                      }),
                    },
                  }],
                },
                finish_reason: null,
              }],
            },
            { ...base, choices: [{ index: 0, delta: {}, finish_reason: 'tool_calls' }] },
          ]
      res.writeHead(200, {
        'content-type': 'text/event-stream',
        'cache-control': 'no-cache',
        connection: 'keep-alive',
      })
      for (const chunk of responseChunks) res.write(`data: ${JSON.stringify(chunk)}\n\n`)
      res.end('data: [DONE]\n\n')
    })
  })
  server.on('connection', socket => {
    sockets.add(socket)
    socket.on('close', () => sockets.delete(socket))
  })
  return {
    server,
    requests,
    async listen(port = 0) {
      await new Promise((resolve, reject) => {
        server.once('error', reject)
        server.listen(port, '127.0.0.1', resolve)
      })
      const address = server.address()
      return `http://127.0.0.1:${address.port}`
    },
    async close() {
      for (const socket of sockets) socket.destroy()
      if (!server.listening) return
      await new Promise(resolve => server.close(resolve))
    },
  }
}
