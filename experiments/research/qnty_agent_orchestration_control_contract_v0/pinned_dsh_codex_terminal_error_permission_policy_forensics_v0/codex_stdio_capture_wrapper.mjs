#!/usr/bin/env node
import { createHash } from 'node:crypto'
import { appendFileSync } from 'node:fs'
import { spawn } from 'node:child_process'

const trace = process.env.QNTYLAB_RPC_TRACE
const target = process.env.QNTYLAB_REAL_CODEX_BINARY
if (!trace || !target) process.exit(91)
const scrub = value => {
  if (typeof value === 'string') return value.replace(/(Bearer\s+)[^\s"']+/gi, '$1<REDACTED>').slice(0, 300)
  if (Array.isArray(value)) return value.map(scrub)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).filter(([k]) => !/authorization|cookie|token|api[_-]?key/i.test(k)).map(([k, v]) => [k, scrub(v)]))
  return value
}
const record = value => appendFileSync(trace, JSON.stringify(scrub(value)) + '\n')
const child = spawn(target, process.argv.slice(2), { stdio: ['pipe', 'pipe', 'pipe'], env: process.env })
let stdoutInput = ''
let stdinInput = ''
let stdoutBytes = 0
let stderrBytes = 0
const stdoutHash = createHash('sha256')
const stderrHash = createHash('sha256')
const consume = (direction, chunk) => {
  const text = chunk.toString('utf8')
  if (direction === 'stdout') stdoutHash.update(chunk), stdoutBytes += chunk.length
  else stderrHash.update(chunk), stderrBytes += chunk.length
  if (direction === 'stdout') {
    stdoutInput += text
    const lines = stdoutInput.split('\n')
    stdoutInput = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.trim()) continue
      try {
        const json = JSON.parse(line)
        record({ direction: 'event', ...json })
      } catch {
        record({ direction: 'event', kind: 'non_json', bytes: Buffer.byteLength(line) })
      }
    }
  }
}
process.stdin.on('data', chunk => {
  stdinInput += chunk.toString('utf8')
  const lines = stdinInput.split('\n')
  stdinInput = lines.pop() ?? ''
  for (const line of lines) {
    if (!line.trim()) continue
    try { const json = JSON.parse(line); record({ direction: 'request', ...json }) } catch { record({ direction: 'request', kind: 'non_json', bytes: Buffer.byteLength(line) }) }
  }
  child.stdin.write(chunk)
})
process.stdin.on('end', () => child.stdin.end())
child.stdout.on('data', chunk => { consume('stdout', chunk); process.stdout.write(chunk) })
child.stderr.on('data', chunk => { consume('stderr', chunk); process.stderr.write(chunk) })
child.on('exit', (code, signal) => {
  record({ direction: 'process', child_exit_code: code, child_signal: signal, stdout_bytes: stdoutBytes, stdout_sha256: stdoutHash.digest('hex'), stderr_bytes: stderrBytes, stderr_sha256: stderrHash.digest('hex') })
  process.exit(code ?? 1)
})
