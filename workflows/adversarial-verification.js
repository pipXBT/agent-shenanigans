export const meta = {
  name: 'adversarial-verification',
  description: 'Run a writing-plans file one task at a time with skeptic, teeth, gate, and receipts (workflows/CONTRACT.md).',
  phases: [
    { title: 'Preflight', detail: 'args, branch, clean tree' },
    { title: 'Plan', detail: 'dependency graph, complexity, run state' },
    { title: 'Tasks', detail: 'implement, skeptic, teeth, gate, receipt' },
    { title: 'Review', detail: 'three reviewers, one verifier per finding, one fix' },
  ],
}

// Claude executor for workflows/CONTRACT.md. Agents return raw output; every check runs
// here in plain JS against the fields they return, and a missing field fails closed.

const CLAUDE_MODELS = { low: 'claude-haiku-5-5', medium: 'claude-sonnet-5-5', high: 'claude-opus-5-5' }
const OTHER_MODEL = 'claude-opus-5-5'
const READ_ONLY = ['plan', 'skeptic', 'review', 'verify-finding']
const LEVELS = ['low', 'medium', 'high']
const KINDS = ['code', 'refactor', 'docs', 'test']

// rules/modes.md without its marker line; tests/workflows/executor.test.mjs keeps them equal.
const MODES = "- In interactive sessions and in agents this repo starts: caveman at `ultracave` and ponytail at `full`, unless the user or the task prompt sets another level. Code, comments, commits, and docs stay normal English.\n- On Grok, where these plugins' hooks do not run, an interactive session reads the caveman plugin's `skills/ultracave/SKILL.md` and the ponytail skill at `full` at session start (the path is in `grok inspect`).\n- Effort `xhigh` for every agent this repo starts unless the user says a task is simple. Never use Fable. \"Opus 5\" means Opus 5.5.\n- For agents this repo starts, if another skill or prompt names a weaker model or lower effort, this file wins unless the user says otherwise. It does not change the models other tools choose for their own agents.\n- A headless run whose output a program parses (`claude -p`, `grok --prompt-file`, Plamen workers, debate seats) writes normal prose in its required format. This rule wins over every line above for those runs."

// The git port, CONTRACT.md §4.
const GIT_RULES = `You are the git step of a scripted workflow. Run only the commands of the one action named on the line below that starts with "git action:", in order, and stop at the first failure. Do not judge or fix anything. Then, whatever happened, fill every report field. String fields hold the command's stdout with trailing newlines removed.

".git" means the directory "git rev-parse --absolute-git-dir" prints. <base> is the action's base parameter; an action without one has no base.

Report fields:
- head: git rev-parse HEAD
- tree: git rev-parse HEAD^{tree}
- branch: git branch --show-current
- default_branch: git symbolic-ref --quiet --short refs/remotes/origin/HEAD with the leading "origin/" removed; "" when that command fails
- porcelain: git status --porcelain --untracked-files=all
- untracked: git ls-files --others --exclude-standard, one entry per line
- last_message: git log -1 --format=%B
- name_status: git diff --no-renames --name-status <base> HEAD; "" without a base
- diff: git diff --no-renames <base>..HEAD; "" without a base. Over 200000 characters: diff "", ok false, error "diff too large", every other field still filled.
- base_is_ancestor: true when git merge-base --is-ancestor <base> HEAD exits 0; false without a base
- state_json: set only by read_state and write_state; "" otherwise
- ok: true when every action command exited 0 and every field command succeeded. merge-base --is-ancestor exiting 1 is a success (false); a failing symbolic-ref gives default_branch "".
- error: "", or the failing command and the first 2000 characters of its stderr

Actions:
- snapshot(base): no commands. base may be "".
- checkout_branch(name): git switch <name> when git rev-parse --verify --quiet refs/heads/<name> succeeds, else git switch -c <name>
- read_state(plan_hash): cat .git/agent-shenanigans/<plan_hash>.json into state_json. A missing file gives state_json "" with ok true.
- write_state(plan_hash, json): mkdir -p .git/agent-shenanigans; write json byte for byte to .git/agent-shenanigans/<plan_hash>.json.tmp; mv it to .git/agent-shenanigans/<plan_hash>.json; cat the result into state_json
- teeth_revert(base, paths): .git/agent-shenanigans/aside/teeth/ must be absent or empty. Run git diff --no-renames --name-status <base> HEAD. For each path in paths: status M, T, or D: git checkout <base> -- <path>; status A: move the path to .git/agent-shenanigans/aside/teeth/<path>, creating parent folders. Any other status, or a path the diff does not list, fails the action.
- teeth_restore(): git restore --source=HEAD --staged --worktree -- :/ then rm -rf .git/agent-shenanigans/aside/teeth
- reset_keep(sha): git reset --keep <sha>
- move_untracked_aside(since): move every path git ls-files --others --exclude-standard lists to .git/agent-shenanigans/aside/<since>.<n>/<path>, where n is the first integer from 1 whose folder does not exist (one n per call)
- amend_trailer(trailer): before=$(git rev-parse HEAD^); git commit --amend --no-edit --trailer "<trailer>"; test "$(git rev-parse HEAD^)" = "$before". For this action only, base_is_ancestor is that last command's result.`

const STR = { type: 'string' }
const BOOL = { type: 'boolean' }
const list = items => ({ type: 'array', items })
const obj = properties => ({ type: 'object', properties, required: Object.keys(properties) })
const SCHEMAS = {
  plan: obj({ phases: list(obj({ name: STR, subprojects: list(obj({ name: STR, tasks: list(obj({
    id: STR, depends_on: list(STR), complexity: { type: 'string', enum: LEVELS }, brief: STR })) })) })) }),
  git: obj({ ok: BOOL, error: STR, head: STR, tree: STR, branch: STR, default_branch: STR, porcelain: STR,
    untracked: list(STR), name_status: STR, diff: STR, last_message: STR, base_is_ancestor: BOOL, state_json: STR }),
  test: obj({ test_exit: { type: 'integer' }, lint_exit: { type: ['integer', 'null'] }, tail: STR }),
  implement: obj({ summary: STR, issues: list(STR) }),
  skeptic: obj({ verdict: { type: 'string', enum: ['pass', 'fail'] }, evidence: STR }),
  review: obj({ findings: list(obj({ file: STR, issue: STR, severity: STR })) }),
  'verify-finding': obj({ real: BOOL, evidence: STR }),
  'fix-review': obj({ summary: STR }),
}

// A failed check. Inside a task attempt it fails the attempt; anywhere else it stops the run.
class Fail extends Error {}
// A failed check that stops the run even inside an attempt (CONTRACT.md §5, Failures).
class Stop extends Fail {}
const check = (ok, why) => { if (!ok) throw new Fail(why) }
async function stopping(f) {
  try { return await f() } catch (e) { throw e instanceof Fail ? new Stop(e.message) : e }
}

let stage = 'preflight'
let current = null
const results = []

// The only place agent() is called. Fixture mode returns the label's next scripted output.
async function call(label, prompt, opts = {}) {
  const o = { label, model: opts.model ?? OTHER_MODEL, effort: 'xhigh', schema: SCHEMAS[label] }
  if (READ_ONLY.includes(label)) o.agentType = 'agent-shenanigans:reader'
  if (o.model.toLowerCase().includes('fable')) throw new Stop(`refused model ${o.model}`)
  const modes = MODES.replaceAll('`full`', `\`${args.ponytail}\``)
  const full = `${modes}\n\nRun nonce: ${args.run_nonce}\n\n${prompt}`
  if (!args.fixture) return agent(full, o)
  const { schema, ...record } = o
  ;(args.fixture.calls ??= []).push({ ...record, prompt: full })
  return args.fixture.outputs?.[label]?.shift() ?? null
}

const git = (action, params) =>
  call('git', `Repo: ${args.repo} (cd there first)\n\n${GIT_RULES}\n\ngit action: ${action} ${JSON.stringify(params)}`)

// One field of a git report. A missing report, ok: false (except "diff too large" for
// fields other than diff), a missing field, or a wrong type fails the check.
function get(r, name, field, type) {
  const usable = r !== null && typeof r === 'object' &&
    (r.ok === true || (r.ok === false && r.error === 'diff too large' && field !== 'diff'))
  const v = usable ? r[field] : undefined
  check(type === 'array' ? Array.isArray(v) : typeof v === type,
    `${name}.${field}: ${usable ? 'missing or wrong type' : 'report missing or not ok'}`)
  return v
}

const isObj = v => v !== null && typeof v === 'object' && !Array.isArray(v)
const canon = v => Array.isArray(v) ? v.map(canon)
  : isObj(v) ? Object.fromEntries(Object.keys(v).sort().map(k => [k, canon(v[k])])) : v
const same = (a, b) => JSON.stringify(canon(a)) === JSON.stringify(canon(b))

const trackedClean = (r, name) =>
  get(r, name, 'porcelain', 'string').split('\n').every(l => l === '' || l.startsWith('??'))
// The paths of a --no-renames --name-status listing.
const changedPaths = ns => ns.split('\n').filter(Boolean).map(l => l.split('\t').at(-1))
// Equal to a listed path, or under a listed entry that ends in "/".
const listed = (p, list) => list.some(e => e === p || (e.endsWith('/') && p.startsWith(e)))
const isDocs = p => /\.(md|rst|txt|adoc)$/.test(p) || p.startsWith('docs/')
const matches = (p, globs) => globs.some(g => glob(g).test(p))

// Whole-path glob: ** spans whole segments, * and ? stay inside one segment.
const glob = g => new RegExp('^' + g.split(/(\*\*\/|\/\*\*$|\*\*|\*|\?)/).map(p =>
  p === '**/' ? '(?:.*/)?' : p === '/**' ? '(?:/.*)?' : p === '**' ? '.*' : p === '*' ? '[^/]*'
    : p === '?' ? '[^/]' : p.replace(/[.+^${}()|[\]\\]/g, '\\$&')).join('') + '$')

function checkArgs() {
  const a = args ?? {}
  const str = v => typeof v === 'string' && v !== ''
  const strs = v => Array.isArray(v) && v.every(s => typeof s === 'string')
  const bad = ['repo', 'test_cmd', 'plan_path', 'run_nonce'].filter(k => !str(a[k]))
  bad.push(...['lint_cmd', 'branch'].filter(k => a[k] != null && typeof a[k] !== 'string'))
  if (!/^[0-9a-f]{64}$/.test(a.plan_hash)) bad.push('plan_hash')
  if (!strs(a.rules?.high_risk) || !strs(a.rules?.test_globs)) bad.push('rules')
  if (!strs(a.forbid)) bad.push('forbid')
  if (a.review != null && typeof a.review !== 'boolean') bad.push('review')
  if (!['full', 'ultra'].includes(a.ponytail)) bad.push('ponytail')
  const ids = Array.isArray(a.tasks) ? a.tasks.map(t => t?.id) : null
  if (!ids || new Set(ids).size !== ids.length || !a.tasks.every(t => str(t?.id) && typeof t.title === 'string' &&
    strs(t.files) && strs(t.tests) && KINDS.includes(t.kind) && ['marker', 'derived'].includes(t.kind_source) &&
    (t.complexity == null || LEVELS.includes(t.complexity)))) bad.push('tasks')
  check(bad.length === 0, `args: missing or wrong type: ${bad.join(', ')}`)
}

// P1/P2: resolve the branch, refuse the default branch, require a clean tree.
async function preflight() {
  const P1 = await git('snapshot', { base: '' })
  const cur = get(P1, 'P1', 'branch', 'string')
  const def = get(P1, 'P1', 'default_branch', 'string')
  const B = args.branch ?? cur
  check(def !== '', 'P1.default_branch: empty, the default branch cannot be determined')
  check(B !== '', 'P1.branch: empty, HEAD is detached')
  check(B !== def, `P1.default_branch: ${B} is the default branch`)
  check(get(P1, 'P1', 'porcelain', 'string') === '', 'P1.porcelain: the tree is not clean')
  if (args.branch != null && args.branch !== cur) {
    const P2 = await git('checkout_branch', { name: B })
    check(get(P2, 'P2', 'branch', 'string') === B, `P2.branch: not on ${B} after checkout`)
    check(get(P2, 'P2', 'porcelain', 'string') === '', 'P2.porcelain: the tree is not clean after checkout')
  }
  return B
}

function planPrompt() {
  const tasks = args.tasks.map(t => `- id ${t.id}: ${t.title} (kind ${t.kind}; files: ${t.files.join(', ') || 'none'}; tests: ${t.tests.join(', ') || 'none'})`)
  return `You plan the run of an implementation plan. Do not change anything.
Repo: ${args.repo}
Plan file: ${args.plan_path}

Tasks:
${tasks.join('\n')}

Read each task's section in the plan file. Group the tasks into phases and subprojects. Return every task above exactly once, with:
- id: exactly as listed
- depends_on: the ids of the tasks that must land before it, never its own
- complexity: low, medium, or high
- brief: the task's full text from the plan file, verbatim`
}

// The plan stage: graph checks and complexity in code, then Kahn order by waves.
async function planOrder() {
  const plan = await call('plan', planPrompt())
  check(Array.isArray(plan?.phases), 'plan.phases: missing')
  const entries = []
  for (const ph of plan.phases) {
    check(Array.isArray(ph?.subprojects), 'plan: a phase has no subprojects list')
    for (const sp of ph.subprojects) {
      check(Array.isArray(sp?.tasks), 'plan: a subproject has no tasks list')
      entries.push(...sp.tasks)
    }
  }
  const byId = new Map(entries.map(e => [e?.id, e]))
  const ids = new Set(args.tasks.map(t => t.id))
  check(byId.size === entries.length, 'plan: a task id appears more than once')
  check(byId.size === ids.size && [...ids].every(id => byId.has(id)), 'plan: task ids differ from the plan file')
  const tasks = args.tasks.map(t => {
    const e = byId.get(t.id)
    check(Array.isArray(e.depends_on) && e.depends_on.every(d => d !== t.id && ids.has(d)),
      `plan: task ${t.id} depends_on names an unknown id or itself`)
    check(typeof e.brief === 'string', `plan: task ${t.id} has no brief`)
    const c = t.complexity ?? e.complexity
    check(LEVELS.includes(c), `plan: task ${t.id} complexity ${c} is not low, medium, or high`)
    const floor = t.files.length > 3 || t.files.some(p => args.rules.high_risk.some(g => glob(g).test(p)))
    return { ...t, depends_on: e.depends_on, brief: e.brief, complexity: floor && c === 'low' ? 'medium' : c }
  })
  const placed = new Set()
  const order = []
  while (order.length < tasks.length) {
    const wave = tasks.filter(t => !placed.has(t.id) && t.depends_on.every(d => placed.has(d)))
    check(wave.length > 0, `plan: dependency cycle among ${tasks.filter(t => !placed.has(t.id)).map(t => t.id).join(', ')}`)
    log(`parallel-eligible: ${wave.map(t => t.id).join(', ')}`)
    wave.forEach(t => placed.add(t.id))
    order.push(...wave)
  }
  return order
}

async function writeState(state) {
  const W = await git('write_state', { plan_hash: args.plan_hash, json: JSON.stringify(state) })
  const text = get(W, 'W', 'state_json', 'string')
  let back
  try { back = JSON.parse(text) } catch {}
  check(same(back, state), 'W.state_json: differs from the state written')
}

// The newest receipt: the one no other done task starts from. Following pre links from it
// must visit every done task and end at run_start, so a corrupt state never resets below it.
function restartTarget(state, done) {
  if (done.size === 0) return state.run_start
  const ids = [...done]
  const tips = ids.filter(id => !ids.some(o => o !== id && state.tasks[o].pre === state.tasks[id].receipt))
  check(tips.length === 1, 'ST.state_json: the receipts do not form one chain')
  const byReceipt = new Map(ids.map(id => [state.tasks[id].receipt, id]))
  let sha = state.tasks[tips[0]].receipt
  let steps = 0
  while (byReceipt.has(sha) && steps <= ids.length) {
    sha = state.tasks[byReceipt.get(sha)].pre
    steps++
  }
  check(steps === ids.length && sha === state.run_start, 'ST.state_json: the receipts do not chain back to run_start')
  return state.tasks[tips[0]].receipt
}

// Fresh run or restart. Returns the state and the ids done in an earlier run.
async function runState() {
  const ST = await git('read_state', { plan_hash: args.plan_hash })
  const text = get(ST, 'ST', 'state_json', 'string')
  const done = new Set()
  if (text === '') {
    const state = { plan_hash: args.plan_hash, run_start: get(ST, 'ST', 'head', 'string'), tasks: {} }
    await writeState(state)
    return { state, done }
  }
  let state
  try { state = JSON.parse(text) } catch {}
  check(isObj(state) && state.plan_hash === args.plan_hash && typeof state.run_start === 'string' &&
    isObj(state.tasks) && Object.values(state.tasks).every(t =>
      isObj(t) && typeof t.pre === 'string' && (t.receipt === null || typeof t.receipt === 'string')),
  'ST.state_json: not a run state for this plan')
  const R0 = await git('snapshot', { base: state.run_start })
  check(get(R0, 'R0', 'base_is_ancestor', 'boolean'), 'R0.base_is_ancestor: HEAD does not descend from run_start')
  check(get(R0, 'R0', 'porcelain', 'string') === '', 'R0.porcelain: the tree is dirty (an interrupted teeth step?)')
  const head = get(R0, 'R0', 'head', 'string')
  for (const [id, t] of Object.entries(state.tasks)) {
    if (t.receipt === null) continue
    const Rr = await git('snapshot', { base: t.receipt })
    if (get(Rr, `R(${id})`, 'base_is_ancestor', 'boolean')) done.add(id)
  }
  const X = restartTarget(state, done)
  if (head !== X) {
    const RK = await git('reset_keep', { sha: X })
    check(get(RK, 'RK', 'head', 'string') === X, `RK.head: the reset did not land on ${X}`)
    check(get(RK, 'RK', 'porcelain', 'string') === '', 'RK.porcelain: the tree is not clean after the reset')
  }
  for (const [id, t] of Object.entries(state.tasks)) if (!done.has(id)) t.receipt = null
  await writeState(state)
  return { state, done }
}

function implementPrompt(t, pre, failure) {
  const retry = failure ? `

An earlier attempt at this task failed: ${failure}
The branch is back at the pre-task commit ${pre}. Start again from there.` : ''
  return `Implement one task from a plan. Work in ${args.repo}, on the current branch.
Task ${t.id}: ${t.title} (kind ${t.kind})
Files: ${t.files.join(', ') || 'none'}
Tests: ${t.tests.join(', ') || 'none'}
Never touch paths matching: ${args.forbid.join(', ') || 'none'}
Test command: ${args.test_cmd}${args.lint_cmd ? `\nLint command: ${args.lint_cmd}` : ''}

Brief:
${t.brief}${retry}

Commit your work and leave the tree clean.`
}

const testPrompt = () => `Repo: ${args.repo} (cd there first)

You are the test step of a scripted workflow. Do not judge or fix anything.
1. Run: ${args.test_cmd}
2. ${args.lint_cmd ? `Run: ${args.lint_cmd}` : 'There is no lint command; skip this step.'}
Report test_exit (the exit code of step 1), lint_exit (the exit code of step 2, or null when it was skipped), and tail (the last 200 lines of their combined output).`

const SKEPTIC_QUESTIONS = {
  code: 'Does the diff do what the brief says, and nothing outside it?',
  refactor: 'Is behaviour unchanged?',
  docs: 'Does the diff change documentation only?',
  test: 'Do the new tests assert real behaviour?',
}

function skepticPrompt(t, nameStatus, diff, changed) {
  const testEdits = changed.filter(p => listed(p, t.tests) || matches(p, args.rules.test_globs))
  const extra = t.kind === 'refactor' && testEdits.length
    ? ` It changes test files (${testEdits.join(', ')}): confirm no assertion was removed or weakened.` : ''
  return `You are the skeptic for one task of a plan. Read the repo at ${args.repo} as needed; change nothing.
Task ${t.id}: ${t.title} (kind ${t.kind})
Files: ${t.files.join(', ') || 'none'}
Tests: ${t.tests.join(', ') || 'none'}
Forbidden paths: ${args.forbid.join(', ') || 'none'}

Brief:
${t.brief}

Changed paths (git diff --name-status):
${nameStatus}

Diff:
${diff}

Question: ${SKEPTIC_QUESTIONS[t.kind]}${extra}
Return verdict "pass" only when the answer is clearly yes, else "fail", with the evidence.`
}

// Steps 2-6 of one attempt (CONTRACT.md §5). A Fail fails the attempt; a Stop ends the run.
// `work` is step 2's agent call; a task with kind null (review-fix) gets its kind after it.
async function attempt(t, B, state, pre, failure, r,
  work = () => call('implement', implementPrompt(t, pre, failure), { model: r.model })) {
  await work()
  const S2 = await git('snapshot', { base: pre })
  const H = get(S2, 'S2', 'head', 'string')
  check(H !== pre, 'S2.head: equals the pre-task commit, nothing was committed')
  check(get(S2, 'S2', 'base_is_ancestor', 'boolean'), 'S2.base_is_ancestor: the pre-task commit is not an ancestor of HEAD')
  check(get(S2, 'S2', 'porcelain', 'string') === '', 'S2.porcelain: the tree is not clean after implement')
  const T = get(S2, 'S2', 'tree', 'string')
  const nameStatus = get(S2, 'S2', 'name_status', 'string')
  const changed = changedPaths(nameStatus)
  if (t.kind === null) {
    t = { ...t, kind: changed.some(p => listed(p, t.files)) ? 'code' : 'test' }
    r.teeth = `skipped:${t.kind}`
  }

  check(S2.ok === true, `S2.ok: ${S2.error}`)
  const sk = await call('skeptic', skepticPrompt(t, nameStatus, get(S2, 'S2', 'diff', 'string'), changed))
  check(sk?.verdict === 'pass', `skeptic.verdict: ${sk?.verdict ?? 'missing'}: ${sk?.evidence ?? ''}`)

  if (t.kind === 'code') {
    const P = changed.filter(p => listed(p, t.files) && !listed(p, t.tests))
    check(P.length > 0, 'S2.name_status: no production path in files changed')
    r.teeth = 'ran'
    const TR = await git('teeth_revert', { base: pre, paths: P })
    const TT = await call('test', testPrompt())
    const RS = await git('teeth_restore', {})
    await stopping(async () => {
      check(get(RS, 'RS', 'head', 'string') === H, 'RS.head: HEAD moved during teeth')
      check(get(RS, 'RS', 'tree', 'string') === T, 'RS.tree: the tree changed during teeth')
      check(trackedClean(RS, 'RS'), 'RS.porcelain: tracked changes remain after the teeth restore')
    })
    check(get(TR, 'TR', 'head', 'string') === H, 'TR.head: the teeth revert did not run on HEAD')
    check(Number.isInteger(TT?.test_exit) && TT.test_exit !== 0,
      `TT.test_exit: ${TT?.test_exit}, the tests do not fail without the change`)
  } else if (t.kind === 'docs') {
    const bad = changed.find(p => !isDocs(p) || listed(p, t.tests) || matches(p, args.rules.test_globs))
    check(!bad, `S2.name_status: ${bad} is not a documentation path`)
  }

  const G1 = await call('test', testPrompt())
  check(G1?.test_exit === 0, `G1.test_exit: ${G1?.test_exit}, the tests fail`)
  if (args.lint_cmd) check(G1.lint_exit === 0, `G1.lint_exit: ${G1.lint_exit}, lint fails`)
  const G2 = await git('snapshot', { base: pre })
  check(get(G2, 'G2', 'head', 'string') === H, 'G2.head: HEAD moved after implement')
  const branch = get(G2, 'G2', 'branch', 'string')
  check(branch === B, `G2.branch: ${branch} is not ${B}`)
  check(branch !== get(G2, 'G2', 'default_branch', 'string'), 'G2.default_branch: on the default branch')
  check(trackedClean(G2, 'G2'), 'G2.porcelain: tracked changes are not committed')
  for (const p of changedPaths(get(G2, 'G2', 'name_status', 'string'))) {
    check(listed(p, t.files) || listed(p, t.tests), `G2.name_status: ${p} is outside files and tests`)
    check(!matches(p, args.forbid), `G2.name_status: ${p} matches forbid`)
  }

  const S6 = await git('snapshot', { base: '' })
  check(get(S6, 'S6', 'head', 'string') === H, 'S6.head: HEAD moved after the gate')
  check(trackedClean(S6, 'S6'), 'S6.porcelain: tracked changes appeared after the gate')
  const trailer = `Task-Id: ${args.plan_hash.slice(0, 12)}/${t.id}`
  await stopping(async () => {
    const A = await git('amend_trailer', { trailer })
    check(A?.ok === true, `A.ok: ${A?.error}`)
    const receipt = get(A, 'A', 'head', 'string')
    check(receipt !== H, 'A.head: the amend made no new commit')
    check(get(A, 'A', 'tree', 'string') === get(G2, 'G2', 'tree', 'string'), 'A.tree: the amend changed the tree')
    check(get(A, 'A', 'base_is_ancestor', 'boolean'), 'A.base_is_ancestor: the amend changed the parent')
    check(get(A, 'A', 'last_message', 'string').split('\n').includes(trailer), `A.last_message: no line ${trailer}`)
    state.tasks[t.id].receipt = receipt
    await writeState(state)
    if (get(A, 'A', 'untracked', 'array').length) {
      const MU = await git('move_untracked_aside', { since: pre })
      check(get(MU, 'MU', 'untracked', 'array').length === 0, 'MU.untracked: files remain after moving them aside')
      check(get(MU, 'MU', 'porcelain', 'string') === '', 'MU.porcelain: the tree is not clean')
    }
  })
}

// F1-F3: back to the pre-task commit with a clean tree. Any failed check here stops the run.
async function restore(pre) {
  const F1 = await git('teeth_restore', {})
  check(trackedClean(F1, 'F1'), 'F1.porcelain: tracked changes remain after the restore')
  const F2 = await git('reset_keep', { sha: pre })
  check(get(F2, 'F2', 'head', 'string') === pre, `F2.head: the reset did not land on ${pre}`)
  let last = ['F2', F2]
  if (get(F2, 'F2', 'untracked', 'array').length) {
    const F3 = await git('move_untracked_aside', { since: pre })
    check(get(F3, 'F3', 'untracked', 'array').length === 0, 'F3.untracked: files remain after moving them aside')
    last = ['F3', F3]
  }
  check(get(last[1], last[0], 'porcelain', 'string') === '', `${last[0]}.porcelain: the tree is not clean`)
}

// Step 1: the pre-task commit, recorded in the run state.
async function begin(id, state) {
  const S1 = await git('snapshot', { base: '' })
  check(get(S1, 'S1', 'porcelain', 'string') === '', 'S1.porcelain: the tree is not clean')
  const pre = get(S1, 'S1', 'head', 'string')
  state.tasks[id] = { pre, receipt: null }
  await writeState(state)
  return pre
}

// Step 1, then up to three attempts, each one tier up from the last (high stays high).
async function runTask(t, B, state) {
  const r = { id: t.id, outcome: 'fail', attempts: 0, teeth: `skipped:${t.kind}`, model: '' }
  results.push(r)
  const pre = await begin(t.id, state)
  let failure = null
  for (let tier = LEVELS.indexOf(t.complexity); r.attempts < 3; tier = Math.min(tier + 1, 2)) {
    r.attempts++
    r.model = CLAUDE_MODELS[LEVELS[tier]]
    r.teeth = `skipped:${t.kind}`
    try {
      await attempt(t, B, state, pre, failure, r)
      r.outcome = 'pass'
      return
    } catch (e) {
      if (!(e instanceof Fail) || e instanceof Stop) throw e
      failure = `attempt ${r.attempts}: ${e.message}`
    }
    await restore(pre)
  }
  throw new Fail(`task ${t.id} failed 3 attempts; last: ${failure}`)
}

const DIMENSIONS = [
  'the behaviour the plan claims, and the interactions between the tasks',
  'failure paths, lost work, and a success report that is false',
  'forbidden changes, and broken invariants named in the rules',
]

const reviewPrompt = (dimension, nameStatus, diff) => `You review the whole branch after a plan ran. Read the repo at ${args.repo} as needed; change nothing.
Dimension: ${dimension}
Rules: ${JSON.stringify(args.rules)}
Forbidden paths: ${args.forbid.join(', ') || 'none'}

Changed paths (git diff --name-status):
${nameStatus}

Diff from the run start:
${diff}

Report only real problems in your dimension. Each finding has file (a repo-relative path), issue, and severity. Return an empty list when there are none.`

const verifyPrompt = (f, nameStatus, diff) => `A reviewer reported this finding about the branch. Try to prove it wrong. Read the repo at ${args.repo} as needed; change nothing.
File: ${f.file}
Issue: ${f.issue}
Severity: ${f.severity}

Changed paths (git diff --name-status):
${nameStatus}

Diff from the run start:
${diff}

Return real true only when the code confirms the problem, with the evidence (path, lines, what they do). Otherwise return real false.`

const fixPrompt = (t, pre) => `Fix the confirmed review findings below. Work in ${args.repo}, on the current branch (at ${pre}).
Files: ${t.files.join(', ') || 'none'}
Tests: ${t.tests.join(', ') || 'none'}
Change only those paths. Never touch paths matching: ${args.forbid.join(', ') || 'none'}
Test command: ${args.test_cmd}${args.lint_cmd ? `\nLint command: ${args.lint_cmd}` : ''}

Findings:
${t.brief}

Commit your work and leave the tree clean.`

// CONTRACT.md §7: three reviewers, one verifier per finding, one fix round as task review-fix.
async function reviewStage(B, state) {
  const RV = await git('snapshot', { base: state.run_start })
  const nameStatus = get(RV, 'RV', 'name_status', 'string')
  const diff = get(RV, 'RV', 'diff', 'string')
  const reviews = await parallel(DIMENSIONS.map(d => () => call('review', reviewPrompt(d, nameStatus, diff))))
  check(reviews.every(rv => Array.isArray(rv?.findings) &&
    rv.findings.every(f => isObj(f) && typeof f.file === 'string' && typeof f.issue === 'string')),
  'review.findings: a reviewer returned no usable report')
  const findings = reviews.flatMap(rv => rv.findings)
  const verdicts = await parallel(findings.map(f => () => call('verify-finding', verifyPrompt(f, nameStatus, diff))))
  check(verdicts.every(v => typeof v?.real === 'boolean' && typeof v.evidence === 'string'),
    'verify-finding: a verifier returned no usable report')
  const confirmed = findings.map((f, i) => ({ ...f, evidence: verdicts[i].evidence.trim(), real: verdicts[i].real }))
    .filter(f => f.real && f.evidence !== '')
  if (confirmed.length === 0) return `review: ${findings.length} findings, none confirmed`

  const files = []
  const tests = []
  for (const p of new Set(confirmed.map(f => f.file)))
    if (!matches(p, args.forbid)) (matches(p, args.rules.test_globs) ? tests : files).push(p)
  check(files.length + tests.length > 0, 'review: every confirmed finding is in a forbidden path')
  const t = { id: 'review-fix', title: 'Fix confirmed review findings', files, tests, kind: null,
    brief: confirmed.map(f => `- ${f.file}: ${f.issue} (${f.severity}). Evidence: ${f.evidence}`).join('\n') }

  current = t.id
  const r = { id: t.id, outcome: 'fail', attempts: 0, teeth: 'skipped:test', model: OTHER_MODEL }
  results.push(r)
  const pre = await begin(t.id, state)
  r.attempts = 1
  try {
    await attempt(t, B, state, pre, null, r, () => call('fix-review', fixPrompt(t, pre)))
  } catch (e) {
    if (!(e instanceof Fail) || e instanceof Stop) throw e
    await restore(pre)
    throw new Fail(`task ${t.id} failed; ${e.message}`)
  }
  r.outcome = 'pass'
  current = null
  return `review: fixed ${confirmed.length} confirmed findings`
}

async function run() {
  phase('Preflight')
  checkArgs()
  const B = await preflight()
  stage = 'plan'
  phase('Plan')
  const order = await planOrder()
  stage = 'preflight'
  const { state, done } = await runState()
  stage = 'task'
  phase('Tasks')
  for (const t of order) {
    current = t.id
    if (done.has(t.id)) {
      results.push({ id: t.id, outcome: 'done-before', attempts: 0, teeth: `skipped:${t.kind}`, model: '' })
      continue
    }
    await runTask(t, B, state)
  }
  current = null
  stage = 'review'
  phase('Review')
  const note = (args.review ?? true) ? `; ${await reviewStage(B, state)}` : ''
  stage = 'done'
  return { ok: true, stage, task: null, summary: `${results.length} tasks passed${note}`, tasks: results }
}

try {
  return await run()
} catch (e) {
  if (!(e instanceof Fail)) throw e
  return { ok: false, stage, task: current, summary: e.message, tasks: results }
}
