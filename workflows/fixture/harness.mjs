// Runs a Workflow-tool script against one fixture case (workflows/CONTRACT.md §8).
// The script body runs as an async function with the Workflow globals; `agent` throws,
// because a script given a fixture must never spawn.
import { readFile } from 'node:fs/promises'

const AsyncFunction = (async () => {}).constructor

// Runs a Workflow-tool script with `args` and the given `agent`; returns its result and phase() titles.
export async function runScript(scriptPath, args, agent) {
  const src = (await readFile(scriptPath, 'utf8')).replace('export const meta', 'const meta')
  // Like the Workflow tool: a thunk that throws resolves to null.
  const parallel = thunks => Promise.all(thunks.map(t => Promise.resolve().then(t).catch(() => null)))
  const budget = { total: null, spent: () => 0, remaining: () => Infinity }
  const phases = []
  const body = new AsyncFunction('agent', 'parallel', 'phase', 'log', 'args', 'budget', src)
  const result = await body(agent, parallel, t => phases.push(t), () => {}, args, budget)
  return { result, phases }
}

export async function runCase(scriptPath, casePath) {
  const c = JSON.parse(await readFile(casePath, 'utf8'))
  const args = { ...c.args, fixture: c.fixture }
  let spawned = false
  const agent = () => {
    spawned = true
    throw new Error('agent() called in fixture mode')
  }
  const { result, phases } = await runScript(scriptPath, args, agent)
  if (spawned) throw new Error('agent() called in fixture mode')
  return { result, phases, calls: args.fixture.calls ?? [] }
}
