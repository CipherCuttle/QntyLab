import { record } from '../../../_seam.js'

class Run {
  constructor(stopReason, outputText) {
    this.result = Promise.resolve({
      stopReason,
      output: outputText ? [{ type: 'text', text: outputText }] : [],
    })
  }
  async dispose() { record({ event: 'run.dispose' }) }
}

export class Context {
  constructor() {
    this.registrations = []
    this.fiber = { dispose: async () => record({ event: 'fiber.dispose' }) }
    this.subagents = {
      start: async (name, options) => {
        record({
          event: 'subagents.start',
          provider: name,
          promptPartTypes: (options?.prompt ?? []).map(part => part?.type),
          parentId: options?.parent?.id ?? null,
          parentCwd: options?.parent?.session?.header?.cwd ?? null,
          hasSignal: Boolean(options?.signal),
          registrations: this.registrations,
        })
        const mode = process.env.QNTYLAB_FAKE_DSH_MODE ?? 'reach_start_only'
        if (mode === 'reach_start_only') {
          throw new Error('FAKE_DSH_SEAM_REACHED_START_NO_LIVE_CALL')
        }
        return new Run(
          process.env.QNTYLAB_FAKE_DSH_STOP_REASON ?? 'completed',
          process.env.QNTYLAB_FAKE_DSH_OUTPUT ?? '',
        )
      },
    }
  }
  async plugin(plugin, config) {
    this.registrations.push(plugin?.name ?? plugin?.pluginName ?? 'anonymous')
    record({ event: 'plugin', name: this.registrations.at(-1), configKeys: Object.keys(config ?? {}).sort() })
  }
}
