---
name: goal-check
description: "Use to rigorously confirm a goal or completion condition is ACTUALLY met before declaring work done — the context-verifying alternative to Claude Code's built-in /goal evaluator (which judges only the conversation transcript). Runs a 3-judge Haiku panel (Literalist / Verifier / Skeptic) that checks the claim against real evidence — runs a check command and inspects repo state — and returns a majority verdict with actionable gaps. Triggers: 'is the goal met', 'verify the goal', 'check goal completion', 'confirm the goal is done', 'goal gate', 'run goal-check'."
---

# goal-check — context-verified goal-completion gate

Confirm a goal is *actually* met, with evidence — not just because the transcript
claims it. This is the rigorous companion to the built-in `/goal` command: `/goal`'s
evaluator reads only the conversation; `goal-check` runs a check command and reads
the repo, then has three Haiku judges vote.

Use this when completion is *claimed* and a wrong "done" is costly: before a handoff,
before a merge, before clearing a goal. It renders a verdict — it does **not** loop
or do the work; the caller acts on the verdict.

`goal-check` cannot replace the `/goal` command itself (built-in commands win at
parse time). Run `/goal` — or any work loop — for the iteration; invoke `goal-check`
at the claimed finish line for a context-verified second opinion.

## Inputs (the calling agent / orchestrator supplies)

1. **Condition** — the goal / completion condition, verbatim. *(required)*
2. **Check command** — a command whose output evidences the goal (e.g. `npm test`,
   `forge test --match-path test/Auth.t.sol`, `cargo build`, `ruff check .`).
   *(optional — infer one from the condition if absent; if none is sensible, see
   "No check command" under Edge cases)*
3. **Context** — files / paths / the transcript region that matter. *(optional)*

## Procedure

### 1. Gather the baseline evidence bundle (you, the main agent — once)

- Run the check command. Capture **stdout, stderr, and exit code** in full.
- Read the relevant files; clip the sections that bear on the condition.
- Clip the slice of the transcript that states what was done / claimed *(omit if invoked without prior conversation context — e.g. a pure CI-style gate)*.
- Assemble these into one **evidence bundle** you hand to every judge, so all three
  judge the same ground truth.

### 2. Convene the panel — 3 Haiku judges, in parallel

Spawn **all three in a single response** (so they run concurrently) using the Agent
tool with **`model: haiku`**. Give each: the condition, the full evidence bundle, its
lens prompt below, and license to Read/Grep for more if its lens needs it.

> **Why Agent subagents and not `/debate` / acpx:** acpx is broken in this
> environment. Agent-tool subagents are the working substitute and let you pin the
> small, cheap Haiku model this gate is meant to use.

**Judge A — Literalist:**
> Decompose the completion condition into every atomic clause. For each clause,
> decide whether the evidence *demonstrates* it (not merely claims it). The goal is
> MET only if EVERY clause is satisfied. Report any clause you cannot confirm as a
> gap.

**Judge B — Verifier:**
> Trust artifacts, not narration. Ignore any "I did X" that is not backed by the
> command output or the file/repo state. Re-derive whether each clause is proven by
> the evidence; if the check command did not actually exercise a clause, treat that
> clause as unproven.

**Judge C — Skeptic:**
> Adversarially argue the goal is NOT met. Hunt the missed clause, the stale or
> cached evidence, the untested path, the edge case, the "passes locally but the
> condition asked for more." Concede MET only if you genuinely cannot build a case
> against it.

Each judge returns exactly:
```
VOTE: MET | NOT_MET
CONFIDENCE: 0.0-1.0
REASON: one or two sentences
GAPS: ["...", ...]   # empty if MET
```

### 3. Aggregate — majority

Count MET votes. **>= 2 of 3 -> MET; otherwise NOT MET.** Confidence does not
change the count, but surface it per judge in the verdict (Step 4) so a 2/3 MET
carried by low-confidence votes reads as a weaker gate. A judge that errored or
returned unparseable output counts as a NOT_MET abstention; note the degraded panel.

### 4. Emit the verdict (to the caller)

```
GOAL <MET | NOT MET> (<met-count>/3)
  Literalist -> <MET|NOT_MET> (<confidence>): <reason>
  Verifier   -> <MET|NOT_MET> (<confidence>): <reason>
  Skeptic    -> <MET|NOT_MET> (<confidence>): <reason>
```

If **NOT MET**, follow with consolidated guidance — the deduplicated union of the
judges' `GAPS`, rewritten as imperatives ("To satisfy the goal: ...") so it feeds
straight into the next work iteration.

Always end with a parseable block. Its `GAPS` field carries the judges' raw gap
strings (deduplicated union) — the imperative phrasing lives in the guidance prose
above, not here:
```
VERDICT: MET | NOT_MET
VOTES: <met-count>/3
GAPS: ["<raw gap>", ...]
```

## Edge cases

- **No check command and none inferable** -> say so and ask the caller for one. If
  there is genuinely nothing to run, proceed transcript-only but label the verdict
  **"unverified — transcript only"**, so a weak judgment is never mistaken for a
  context-verified one.
- **Check command fails to run** (missing tool / bad path) -> put the failure in the
  bundle; "could not verify" is evidence the goal is NOT demonstrably met.
- **Vague / unfalsifiable condition** -> the Literalist flags that it has no
  checkable clauses; return that to the caller to sharpen the goal rather than
  guessing MET.

## Notes

- Pure prose skill — no scripts. The 3-vote tally is by hand (trivial).
- Claude Code only for now (uses the Agent tool). A Grok-native port using
  `spawn_subagent` + a fast model is a clean future addition (`SKILL.grok.md`).

---

*Part of [agent-shenanigans](https://github.com/pipXBT/agent-shenanigans).*
