export const meta = {
  name: 'debate-round',
  description: 'Run one debate round: one wrapper agent per seat runs run_seats.py for that seat and returns its verdict.',
  whenToUse: 'Started by the debate skill on Claude Code with {repo, panel, work_dir, plan, seats}, all paths absolute. Run run_seats.py collect on work_dir afterwards.',
  phases: [
    { title: 'Opus 5.5 seats', detail: 'one Haiku wrapper per Opus seat; the label names the real reviewer' },
    { title: 'Grok 4.7 seats', detail: 'one Haiku wrapper per Grok seat; the label names the real reviewer' },
  ],
}

// Each seat runs as its own sub-run in <work_dir>/<seat>/, started by a thin Haiku wrapper so
// /workflows shows one agent per seat. The wrappers judge nothing: run_seats.py runs the seat,
// and `run_seats.py collect` merges the sub-runs into <work_dir>/summary.json afterwards.
// The script cannot read panel.json, so the skill passes `seats` as [{seat, persona, host, model, effort}].
// The model column in /workflows shows the wrapper (Haiku); the label carries the seat's real model and effort.

const PHASES = { opus: 'Opus 5.5 seats', grok: 'Grok 4.7 seats' }
const VERDICTS = ['APPROVED', 'REVISE']
const SCHEMA = {
  type: 'object',
  properties: {
    seat: { type: 'string' },
    verdict: { type: ['string', 'null'], enum: [...VERDICTS, null] },
    exit: { type: ['integer', 'null'] },
    output_path: { type: 'string' },
  },
  required: ['seat', 'verdict', 'exit', 'output_path'],
}

const abs = v => typeof v === 'string' && v.startsWith('/')
const seats = args?.seats
const ok = ['repo', 'panel', 'work_dir', 'plan'].every(k => abs(args?.[k])) &&
  Array.isArray(seats) && seats.length > 0 && new Set(seats.map(s => s?.seat)).size === seats.length &&
  seats.every(s => /^[\w-]+$/.test(s?.seat ?? '') && typeof s.persona === 'string' && Object.hasOwn(PHASES, s.host) &&
    [s.model, s.effort].every(v => typeof v === 'string' && v !== '') && !s.model.includes('fable'))
if (!ok) throw new Error('args: need absolute repo, panel, work_dir and plan, and seats: [{seat, persona, host: "opus" | "grok", model, effort}], each seat once, no fable model')

// Single-quoted for the shell.
const q = s => `'${s.replaceAll("'", "'\\''")}'`

function prompt(seat) {
  const dir = `${args.work_dir}/${seat}`
  const cmd = `python3 ${q(`${args.repo}/skills/debate/scripts/run_seats.py`)} run --panel ${q(args.panel)} ` +
    `--work-dir ${q(dir)} --plan ${q(args.plan)} --seats ${q(seat)}`
  return `You start one debate seat and report how it ended. Do only this.

1. With the Bash tool and run_in_background: true, run exactly this command, once:
${cmd}
2. Wait for the notification that the command finished. A seat can take an hour. Do not poll. Never kill the process, and never run anything else that writes.
3. Once it has finished, read ${dir}/summary.json. verdict is its verdicts["${seat}"]: "APPROVED", "REVISE", or null. It is null when the file is missing or has no verdict for the seat.
4. Return seat "${seat}", that verdict, exit (the command's exit code, or null when you could not see it), and output_path "${dir}/${seat}-output.md".`
}

const replies = await parallel(seats.map(s => () => agent(prompt(s.seat), {
  label: `${s.persona} · ${s.model} ${s.effort}`, phase: PHASES[s.host], model: 'claude-haiku-5-5', effort: 'xhigh', schema: SCHEMA,
})))
// A dead wrapper, or a reply about another seat, is no verdict.
const verdicts = Object.fromEntries(seats.map((s, i) => {
  const r = replies[i]
  return [s.seat, r?.seat === s.seat && VERDICTS.includes(r.verdict) ? r.verdict : null]
}))
return {
  requested: seats.length,
  returned: Object.values(verdicts).filter(v => v !== null).length,
  verdicts,
  work_dir: args.work_dir,
}
