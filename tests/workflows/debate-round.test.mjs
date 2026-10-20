// workflows/debate-round.js with stub wrapper agents standing in for two seats.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runScript } from '../../workflows/fixture/harness.mjs'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const SCRIPT = join(ROOT, 'workflows/debate-round.js')
const ARGS = {
  repo: '/plugin', panel: '/plugin/skills/debate/panel.json', work_dir: '/d/round-1', plan: '/d/plan.md',
  seats: [
    { seat: 'skeptic-opus', persona: 'skeptic', host: 'opus' },
    { seat: 'architect-grok', persona: 'architect', host: 'grok' },
  ],
}
const reply = (seat, verdict) => ({ seat, verdict, exit: 0, output_path: `/d/round-1/${seat}/${seat}-output.md` })

async function run(replies, args = ARGS) {
  const calls = []
  const agent = async (prompt, opts) => {
    calls.push({ prompt, ...opts })
    return replies[prompt.match(/--seats '([^']+)'/)[1]]
  }
  const { result } = await runScript(SCRIPT, args, agent)
  return { result, calls }
}

test('one wrapper per seat, in its model phase, labeled with the persona', async () => {
  const { result, calls } = await run({
    'skeptic-opus': reply('skeptic-opus', 'APPROVED'), 'architect-grok': reply('architect-grok', 'REVISE') })
  assert.deepEqual(calls.map(k => [k.phase, k.label, k.model, k.effort, k.agentType]), [
    ['Opus 5.5', 'skeptic', 'claude-haiku-5-5', 'xhigh', undefined],
    ['Grok 4.7', 'architect', 'claude-haiku-5-5', 'xhigh', undefined],
  ])
  assert.ok(calls[0].prompt.includes("python3 '/plugin/skills/debate/scripts/run_seats.py' run " +
    "--panel '/plugin/skills/debate/panel.json' --work-dir '/d/round-1/skeptic-opus' --plan '/d/plan.md' " +
    "--seats 'skeptic-opus'"))
  assert.ok(calls[0].prompt.includes('run_in_background: true'))
  assert.ok(calls[0].prompt.includes("/d/round-1/skeptic-opus/summary.json"))
  assert.deepEqual(result, {
    requested: 2, returned: 2, verdicts: { 'skeptic-opus': 'APPROVED', 'architect-grok': 'REVISE' }, work_dir: '/d/round-1' })
})

test('a dead wrapper or a reply for another seat counts as no verdict', async () => {
  const { result } = await run({ 'skeptic-opus': null, 'architect-grok': reply('skeptic-opus', 'APPROVED') })
  assert.deepEqual(result.verdicts, { 'skeptic-opus': null, 'architect-grok': null })
  assert.equal(result.returned, 0)
  await assert.rejects(run({}, { ...ARGS, seats: [] }), /args/)
})
