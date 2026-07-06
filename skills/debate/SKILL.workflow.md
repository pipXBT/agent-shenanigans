# Debate — Claude Code Workflow engine port

A third engine for the debate panel, alongside the acpx engine (`/debate:all`,
cc-debate plugin) and the Grok Build port (`SKILL.grok.md`): run the reviewer
panel on Claude Code's **Workflow tool** — no external CLIs, no acpx, no
subprocess PATH. Use it when acpx is broken or unavailable in the environment
(see "Engine selection" in SKILL.md), or whenever you want schema-enforced
verdicts instead of regexing them out of prose.

Invoking this port counts as Workflow opt-in: the Workflow tool's gate
explicitly allows "the user invoked a skill whose instructions tell you to
call Workflow".

## What changes vs the acpx engine

| | acpx engine | Workflow engine |
|---|---|---|
| Reviewer processes | external CLIs (codex/gemini/grok/claude) via acpx | Workflow `agent()` calls (Claude models) |
| Verdict extraction | regex `VERDICT: (APPROVED\|REVISE)` from prose | **schema-forced** structured output |
| Failure mode | reviewers can exit 1 while the runner exits 0 | a dead agent returns `null` — visible, filterable |
| Model diversity | multi-vendor | Claude-only; persona diversity + model-tier mixing (`opus`/`sonnet`/`haiku`) |
| Plan delivery | `plan.md` file in the work dir | embedded in each agent prompt (workflow agents have no conversation context) |

Evidence note (2026-06, 6+ sessions): when acpx was broken, all-Claude
persona panels still converged on 7/7 REVISE rounds with 10+ unanimous real
findings, and plans reached APPROVED through normal revision rounds — the
multi-vendor diversity loss is real but has not blunted the panel in practice.

## What stays the same

- **Personas + config**: read the same `~/.claude/debate-acpx.json`; each
  reviewer's `system_prompt` becomes the head of its agent prompt. (The
  `agent`/`timeout` fields are acpx-specific — ignore them; map models below.)
- **Round discipline**: max 3 revision rounds; verification passes don't
  burn budget; revisions are made by the orchestrator IN the main
  conversation and shown to the user, exactly as the acpx skill specifies.
- **SHA gates + journaling**: keep using `~/.claude/debate-scripts/`
  `debate-setup.sh`, `record-round.sh`, `safe-cleanup.sh` from the main
  loop. Write `plan.md` to the work dir before each round so
  `record-round.sh` binds verdicts to the exact bytes reviewed, and refuse
  to report APPROVED for a plan whose SHA no reviewer saw (Step 6a/6.5 of
  the acpx skill apply unchanged).
- **Read everything**: the structured `findings[]` replace prose skims, but
  each finding's `detail` must still be read in full before synthesis.

## The panel as a Workflow

One workflow per round. Synthesis, contradiction detection, revision, and
user interaction stay in the MAIN loop between rounds (they need judgment
and the user); the workflow only fans out the panel and returns structure.

```js
export const meta = {
  name: 'debate-panel',
  description: 'One debate round: every reviewer persona reviews the plan in parallel',
  phases: [{ title: 'Review' }],
}
// args = { plan: string, reviewers: [{name, persona, model?}], context?: string }
const VERDICT = {
  type: 'object',
  required: ['verdict', 'findings'],
  properties: {
    verdict: { type: 'string', enum: ['APPROVED', 'REVISE'] },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['severity', 'title', 'detail'],
        properties: {
          severity: { type: 'string', enum: ['CRITICAL', 'MAJOR', 'MINOR'] },
          title: { type: 'string' },
          detail: { type: 'string' },
          planQuote: { type: 'string' },
        },
      },
    },
  },
}
phase('Review')
const results = await parallel(args.reviewers.map(r => () =>
  agent(
    `${r.persona}\n\n` +
    (args.context ? `Context from the prior round:\n${args.context}\n\n` : '') +
    `Review the following implementation plan. Quote the plan where possible.\n\n` +
    `<plan>\n${args.plan}\n</plan>`,
    { label: r.name, phase: 'Review', schema: VERDICT, model: r.model }
  ).then(v => ({ reviewer: r.name, ...v }))
))
return results.filter(Boolean)
```

Orchestrator loop per round:

1. `bash ~/.claude/debate-scripts/debate-setup.sh` (round 1 only) → work dir.
2. Write the current plan to `<WORK_DIR>/plan.md`.
3. Build `reviewers` from `~/.claude/debate-acpx.json` (`name` + `system_prompt`
   → `persona`). Model mapping: keep heavyweight lenses (skeptic, architect)
   on `opus`; the rest may run `sonnet` for cost — or omit `model` to inherit
   the session model. This is the only diversity axis; vary it.
4. Invoke `Workflow({name|scriptPath, args: {plan, reviewers}})`. Pass `plan`
   as a real string in args — NOT a path; workflow agents can't see your CWD
   conventions and must not depend on reading files.
5. Read every finding in full. Synthesize: unanimous / unique / contradictions.
6. `record-round.sh <WORK_DIR> <round> <verdict>`.
7. Contradictions → debate pass: re-invoke the SAME workflow with only the
   disagreeing reviewers and `context` = both positions quoted verbatim.
8. Any REVISE → revise the plan in the main conversation (show the user),
   rewrite `plan.md`, increment the round, go to 4. All APPROVED → final
   report with the SHA self-check from the acpx skill (Step 6a); if you
   edited the plan after the last panel, run a verification pass (Step 6.5)
   — re-invoke the workflow with only the affected reviewers and the diff
   summary in `context` — before claiming APPROVED.
9. `safe-cleanup.sh <WORK_DIR>` (it refuses if the plan drifted past the
   last APPROVED SHA — same trap as the acpx engine, same resolution).

## Sizing

Each reviewer re-reads the full plan: a 7-lens panel over a 1,500-line plan
costs roughly 7× the plan in input per round. That is the intended price of
the panel (same as acpx). Keep panels ≤ 8 reviewers; for quick checks use 3
(skeptic, architect, pragmatist).

## Failure handling

- An agent that dies returns `null` — `filter(Boolean)` and REPORT the
  missing lens in the synthesis ("pager-duty did not return — N/M panel").
  Never silently shrink the panel.
- If the Workflow tool itself is unavailable (no opt-in context, restricted
  session), fall back to named Agent-tool subagents with the same persona
  prompts and ask each to END with `VERDICT: APPROVED|REVISE` — the
  pre-Workflow manual pattern. It works; it just costs you the schema.
