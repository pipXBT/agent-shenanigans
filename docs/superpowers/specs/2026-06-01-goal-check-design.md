# goal-check — context-verified goal-completion gate

**Date:** 2026-06-01
**Status:** Approved design — ready for implementation plan
**Repo:** `agent-shenanigans`

## Summary

A new skill, `goal-check`, that an orchestrating agent invokes to answer one
question rigorously: **"is this goal actually met?"** It runs a small panel of
Haiku judges that verify the claimed completion against *real context* — the
output of a check command and the actual repository state — not just the
conversation transcript.

It is the rigorous alternative to Claude Code's built-in `/goal` evaluator. The
built-in `/goal` already uses a fast model (Haiku) to judge completion after each
turn, but that judge **only reads the conversation transcript** — it never runs a
command or reads a file. `goal-check` closes that blind spot. The skill does
**not** run an autonomous loop; it renders a verdict that the calling agent acts
on.

## Motivation

### What the built-in `/goal` does today

`/goal <completion condition>` (Claude Code v2.1.139+) sets a completion condition
and works autonomously across turns. After every turn a fast model (Haiku by
default) reads the condition + transcript and returns met / not-met + a reason; if
not met, the reason is fed back as guidance and another turn starts. The evaluator
**does not run commands or read files independently** — it judges only what the
main agent has surfaced in the conversation.

### The gap

A judge that reads only the transcript can be fooled by a confident-but-wrong
"I've done X." The costly failure mode of any completion gate is a **false MET**:
work stops while the goal is not actually satisfied. `goal-check` makes the verdict
survive (a) decomposition into every clause of the condition, (b) independent
verification against artifacts, and (c) an adversary actively arguing "not done."

### Why this can't literally override `/goal`

`/goal` is a **built-in CLI command**, recognized at parse time before any skill.
A skill cannot shadow the name `/goal`. So `goal-check` ships under its own name
and invocation surface. Intended use: run the built-in `/goal` (or any work loop)
for the autonomous iteration, and invoke `goal-check` when completion is *claimed*,
for a context-verified second opinion before declaring done. It also runs
standalone any time.

## Scope

**In scope (v1):**
- A single `goal-check/SKILL.md` (pure prose-driven skill, no scripts).
- A 3-judge Haiku panel via the Agent tool, majority vote.
- Hybrid evidence model: orchestrator gathers a baseline bundle once; judges may
  pull more context.
- A structured, parseable verdict for the calling orchestrator.
- A row in `README.md`; auto-discovered by `install.sh`.

**Out of scope (v1):**
- No autonomous work loop (the skill judges; the caller loops).
- No `SKILL.grok.md` variant (Claude-only for v1 — uses the Agent tool; a Grok port
  via `spawn_subagent` is a clean later addition, noted below).
- No installed hooks, no `ORCHESTRATION-STATE`/INBOX coupling — the skill is
  general; the calling agent supplies the goal.
- No reconciliation/debate round between judges (majority of independent votes;
  revisit only if false verdicts are observed).

## Architecture

### Role and boundary

`goal-check` is a **reusable judge**, not an orchestrator. The boundary is a single
call:

- **Input** (the calling agent / orchestrator supplies):
  1. `condition` — the goal / completion condition text (required).
  2. `check_command` — a command whose output evidences the goal, e.g.
     `npm test`, `forge test --match-path …`, `cargo build`. Optional; if omitted
     the skill infers a candidate from the condition or asks the caller.
  3. `context` — which files / paths / transcript region matter. Optional.
- **Output**: a verdict — `MET | NOT MET`, the vote count, per-judge one-liners,
  and (when NOT MET) consolidated actionable guidance, plus a small parseable block.

The skill can be understood, used, and tested through that one interface without
reading its internals.

### Flow

```
orchestrator invokes goal-check(condition, check_command?, context?)
        │
   ① main model gathers the BASELINE evidence bundle:
        - run check_command → capture stdout, stderr, exit code
        - read the named/relevant files → clip pertinent sections
        - clip the transcript slice describing what was done / claimed
        - assemble into one evidence-bundle string
        │
   ② spawn 3 Haiku judges IN PARALLEL (Agent tool, model: haiku,
      all three Agent calls in a single response so they run concurrently):
        - Literalist : split the condition into atomic clauses; a clause is
                       satisfied only with evidence; MET only if ALL pass.
        - Verifier   : trust artifacts, not claims; does the command output +
                       repo state independently prove each clause?
        - Skeptic    : adversarial; build the strongest case it is NOT met —
                       missed clause, stale evidence, untested path, edge case.
        Each judge receives the evidence bundle and MAY Read/Grep more if its
        lens needs it (hybrid). Each returns:
            { vote: MET | NOT_MET, confidence: 0..1, reason: "...", gaps: [...] }
        │
   ③ aggregate (majority): ≥2 of 3 vote MET → MET; otherwise NOT MET.
        │
   ④ emit verdict to the orchestrator:
        - header: "GOAL <MET | NOT MET> (n/3)"
        - one line per judge: lens → vote → one-sentence reason
        - if NOT MET: consolidated guidance = the union of `gaps`, phrased as
          imperatives ("To satisfy the goal: …") so it feeds straight into the
          next work iteration (mirrors how built-in /goal feeds its reason back)
        - a fenced parseable block, e.g.:
            VERDICT: NOT_MET
            VOTES: 1/3
            GAPS: ["lint not run", "auth test file absent"]
```

### Component design

**The skill (`SKILL.md`).** Frontmatter `name: goal-check` + a trigger-packed
`description`. Body prescribes the four-step flow, the three judge prompt
templates (inline), the evidence-bundle format, the majority rule, and the verdict
format. No scripts; the 3-vote tally is done by hand (trivial).

**The three judges (Agent-tool subagents, `model: haiku`).** Each is a fresh
subagent given: the condition, the evidence bundle, its lens-specific prompt, and
permission to Read/Grep for more. Each returns the structured verdict object as its
final message. Distinct lenses give *diverse* failure detection rather than three
copies of the same judgment.

### Key decisions

| Decision | Choice | Why |
|---|---|---|
| Skill role | Judge only, no loop | Lightest; the debate-with-context is the whole value. Looping is the built-in's / caller's job. |
| Evidence model | Hybrid (bundle once, judges may pull more) | Deterministic shared ground truth + adaptive depth; reproducible disagreement signal without blinding judges. |
| Panel | 3 lenses (Literalist / Verifier / Skeptic), majority vote | Diverse detection; majority tolerates one overly-picky judge; Skeptic specifically guards the false-MET failure mode. |
| Judge runtime | Agent-tool subagents, `model: haiku` | `acpx` (used by the `debate` skill) is broken in this environment; Agent subagents are the proven substitute and let us pin the small/cheap model. |
| Inputs | Calling agent / orchestrator passes them in | Keeps the skill general and HyperShield-agnostic; fits `agent-shenanigans` as a public skill. |
| Implementation | Pure `SKILL.md`, no scripts | Portable (Claude + future Grok), zero maintenance, matches `debate`/`handoff` conventions. |
| Grok variant | Deferred | Uses the Agent tool (Claude-specific); a `spawn_subagent` port is a clean later addition. |

## Error handling / edge cases

- **No check command available and none inferable** → the skill states this and asks
  the caller for one (or proceeds transcript-only, clearly labelling the verdict as
  *unverified — transcript only*, so a weak judgment is never mistaken for a
  context-verified one).
- **Check command fails to run** (missing tool, bad path) → surface the failure in
  the bundle; judges treat "could not verify" as evidence the goal is NOT
  demonstrably met (conservative).
- **A judge subagent errors / returns unparseable output** → count it as a NOT_MET
  abstention for the majority (conservative default), and note the degraded panel in
  the verdict.
- **Condition is vague / unfalsifiable** → the Literalist surfaces that the condition
  has no checkable clauses; the verdict flags it back to the caller to sharpen the
  goal rather than guessing.

## Testing strategy

Skills are prose, so verification is behavioural — drive the skill on fixtures and
assert the verdict:

1. **True MET** — condition + a check command that passes + repo state that
   genuinely satisfies every clause → expect `MET (3/3)` or `(2/3)`.
2. **False MET trap** — transcript loudly claims success but the check command
   fails / a clause is unmet → expect `NOT MET`, with the Verifier and/or Skeptic
   carrying the dissent and the gap named in the guidance.
3. **Partial completion** — multi-clause condition, one clause unmet → Literalist
   catches the missed clause → `NOT MET` with that clause in `gaps`.
4. **No check command** → verdict labelled *unverified — transcript only* (not a
   silent context-verified MET).
5. **Degraded panel** — one judge errors → verdict still emitted, panel noted.

## Files to create / modify

- `goal-check/SKILL.md` — new (the whole skill).
- `README.md` — add a row to the skills table.
- `install.sh` — no change (auto-discovers any top-level dir with `SKILL.md`).

## Open questions

None blocking. Settled defaults the user may revisit at spec review:
- Directory name `goal-check`.
- Claude-only for v1 (Grok port deferred).
