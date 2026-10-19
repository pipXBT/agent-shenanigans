// Runs a Workflow-tool script against one fixture case (workflows/CONTRACT.md §8).
// The script body runs as an async function with the Workflow globals; `agent` throws,
// because a script given a fixture must never spawn.
import { readFile } from 'node:fs/promises'

const AsyncFunction = (async () => {}).constructor

export async function runCase(scriptPath, casePath) {
  const src = (await readFile(scriptPath, 'utf8')).replace('export const meta', 'const meta')
  const c = JSON.parse(await readFile(casePath, 'utf8'))
  const args = { ...c.args, fixture: c.fixture }
  let spawned = false
  const agent = () => {
    spawned = true
    throw new Error('agent() called in fixture mode')
  }
  // Like the Workflow tool: a thunk that throws resolves to null.
  const parallel = thunks => Promise.all(thunks.map(t => Promise.resolve().then(t).catch(() => null)))
  const budget = { total: null, spent: () => 0, remaining: () => Infinity }
  const body = new AsyncFunction('agent', 'parallel', 'phase', 'log', 'args', 'budget', src)
  const result = await body(agent, parallel, () => {}, () => {}, args, budget)
  if (spawned) throw new Error('agent() called in fixture mode')
  return { result, calls: args.fixture.calls ?? [] }
}
