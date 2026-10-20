// Runs every fixture case in workflows/fixture/cases/ through the Claude executor.
// Case format: workflows/CONTRACT.md §8. Optional expect fields extend it here:
// `git` lists the git actions in call order (each entry matches the listed params only;
// a trailing "..." allows more calls after), `implement` lists the implement models,
// `tasks` maps an id to result fields it must have, `summary` is a substring of the
// result summary, `calls` maps a label to how many times it was called, and `prompts` lists
// {label, n, includes}: the n-th call of that label has a prompt containing `includes`.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runCase } from '../../workflows/fixture/harness.mjs'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const SCRIPT = join(ROOT, 'workflows/adversarial-verification.js')
const CASES = join(ROOT, 'workflows/fixture/cases')
const READ_ONLY = ['plan', 'skeptic', 'review', 'verify-finding']

function gitActions(calls) {
  return calls.filter(k => k.label === 'git').map(k => {
    const [, action, params] = k.prompt.match(/^git action: (\S+) (.*)$/m)
    return { action, ...JSON.parse(params) }
  })
}

for (const file of readdirSync(CASES)) {
  test(file, async () => {
    const c = JSON.parse(readFileSync(join(CASES, file)))
    const { result, calls } = await runCase(SCRIPT, join(CASES, file))
    assert.equal(result.ok, c.expect.ok, result.summary)
    assert.equal(result.stage, c.expect.stage, result.summary)
    if ('task' in c.expect) assert.equal(result.task, c.expect.task)
    if ('level' in c.expect) assert.equal(result.level, c.expect.level)
    if (c.expect.summary) assert.ok(result.summary.includes(c.expect.summary), result.summary)
    for (const [id, outcome] of Object.entries(c.expect.outcomes ?? {}))
      assert.equal(result.tasks.find(t => t.id === id)?.outcome, outcome)
    for (const [id, want] of Object.entries(c.expect.tasks ?? {})) {
      const got = result.tasks.find(t => t.id === id) ?? {}
      for (const [k, v] of Object.entries(want)) assert.equal(got[k], v, `task ${id} ${k}`)
    }
    for (const k of calls) {
      assert.ok(/^claude-(haiku|sonnet|opus)-5-5$/.test(k.model), k.label)
      assert.equal(k.effort, 'xhigh')
      assert.equal(k.agentType, READ_ONLY.includes(k.label) ? 'shenanigans:reader' : undefined)
    }
    if (c.expect.git) {
      const open = c.expect.git.at(-1) === '...'
      const want = open ? c.expect.git.slice(0, -1) : c.expect.git
      const got = gitActions(calls).slice(0, open ? want.length : undefined)
      const pick = (g, w) => (w ? Object.fromEntries(Object.keys(w).map(k => [k, g[k]])) : g)
      assert.deepEqual(got.map((g, i) => pick(g, want[i])), want)
    }
    if (c.expect.implement)
      assert.deepEqual(calls.filter(k => k.label === 'implement').map(k => k.model), c.expect.implement)
    for (const [label, n] of Object.entries(c.expect.calls ?? {}))
      assert.equal(calls.filter(k => k.label === label).length, n, `${label} calls`)
    for (const { label, n, includes } of c.expect.prompts ?? [])
      assert.ok(calls.filter(k => k.label === label)[n]?.prompt.includes(includes), `${label} #${n}: ${includes}`)
  })
}

// The role stays the fixture key and the calls label; only the /workflows display label changes.
test('display labels name the subproject, task and step under the plan phase', async () => {
  const { calls, phases } = await runCase(SCRIPT, join(CASES, 'add-file.json'))
  assert.deepEqual(phases, ['Preflight', 'Plan', 'Phase 1', 'Review'])  // level full; review: false skips its agents
  const T = 'Core · task 1 · '
  assert.deepEqual(calls.map(k => `${k.label}=${k.display}`), [
    'git=git', 'plan=plan', 'git=git', 'git=git',
    `git=${T}git`, `git=${T}git`, `implement=${T}implement`, `git=${T}git`, `skeptic=${T}skeptic`,
    `git=${T}git`, `test=${T}teeth`, `git=${T}git`, `test=${T}gate`,
    `git=${T}git`, `git=${T}git`, `git=${T}git`, `git=${T}git`, `git=${T}git`,
  ])
})

test('display labels in the review stage', async () => {
  const { calls, phases } = await runCase(SCRIPT, join(CASES, 'review-fix-test-path.json'))
  assert.deepEqual(phases, ['Preflight', 'Plan', 'Phase 1', 'Review'])
  const shown = label => calls.filter(k => k.label === label).map(k => k.display)
  assert.deepEqual(shown('review'), ['review · behaviour', 'review · failures', 'review · invariants'])
  assert.deepEqual(shown('verify-finding'),
    ['verify · src/a.py', 'verify · tests/test_a.py', 'verify · src/b.py', 'verify · .github/ci.yml'])
  assert.deepEqual(shown('fix-review'), ['review · task review-fix · implement'])
  assert.ok(shown('git').includes('review · task review-fix · git'))
})

test('modes block equals rules/modes.md without its marker line', () => {
  const body = readFileSync(join(ROOT, 'rules/modes.md'), 'utf8').split('\n').slice(1).join('\n').trim()
  assert.ok(readFileSync(SCRIPT, 'utf8').includes(`const MODES = ${JSON.stringify(body)}`))
})
