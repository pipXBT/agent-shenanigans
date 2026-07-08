---
name: check-in
description: "Use to rigorously confirm a goal or completion condition is ACTUALLY met before declaring work done — the context-verifying alternative to Claude Code's built-in /goal evaluator (which judges only the conversation transcript). A 3-judge Haiku advisory panel (Literalist / Verifier / Skeptic) weighs the claim against real evidence — a check command's output plus repo state — then an Opus 4.8 overseer reconciles the panel and issues the authoritative MET/NOT_MET verdict with actionable gaps. Triggers: 'is the goal met', 'verify the goal', 'check goal completion', 'confirm the goal is done', 'goal gate', 'run check-in'."
---

# check-in — context-verified goal-completion gate

Confirm a goal is *actually* met, with evidence — not just because the transcript
claims it. This is the rigorous companion to the built-in `/goal` command: `/goal`'s
evaluator reads only the conversation; `check-in` runs a check command and reads
the repo, has three cheap Haiku judges weigh in, then an **Opus 4.8 overseer** renders
the authoritative verdict.

Use this when completion is *claimed* and a wrong "done" is costly: before a handoff,
before a merge, before clearing a goal. It renders a verdict — it does **not** loop
or do the work; the caller acts on the verdict.

`check-in` cannot replace the `/goal` command itself (built-in commands win at
parse time). Run `/goal` — or any work loop — for the iteration; invoke `check-in`
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
- Assemble these into one **evidence bundle** you hand to every judge and the
  overseer, so all four judge the same ground truth.

### 2. Convene the advisory panel — 3 Haiku judges, in parallel

Spawn **all three in a single response** (so they run concurrently) using the Agent
tool with **`model: haiku`**. Give each: the condition, the full evidence bundle, its
lens prompt below, and license to Read/Grep for more if its lens needs it. The panel
**advises**; it does not decide — its votes and gaps are input to the overseer (Step 4).

> **Why Agent subagents and not `/debate` / acpx:** the `/debate` panel runs on
> acpx, which depends on external agent CLIs that aren't always installed (and are
> broken in some environments). Agent-tool subagents are the portable substitute and
> let you pin the exact model tier each judge needs — cheap Haiku panelists, an
> Opus 4.8 overseer.

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

### 3. Tally the panel (advisory signal only)

Count MET votes for a quick lean — **>= 2 of 3 is the panel's MET lean** — and note
each judge's confidence. This tally does **not** decide the verdict; it is context for
the overseer. A judge that errored or returned unparseable output counts as a NOT_MET
abstention; carry that (and the degraded panel) into the overseer's bundle so it can
weigh the panel accordingly.

### 4. Convene the overseer — one Opus 4.8 judge (the deciding vote)

Spawn a single Agent with **`model: opus`** (Opus 4.8). Give it: the condition, the
full evidence bundle, the panel tally from Step 3, and all three judges' raw returns
(votes, confidences, reasons, gaps). The overseer has **final say in both directions** —
it may ratify the panel or overturn it either way.

> **Overseer prompt:**
> You are the deciding judge. Three cheap judges have already weighed this evidence;
> treat their votes and gaps as *advice, not answer* — do not defer to their majority.
> Independently re-derive whether EVERY clause of the condition is *demonstrated* by
> the evidence (the check command's output and the repo state), not merely claimed.
> Adopt a panel gap only if the evidence supports it, discard one the evidence
> refutes, and raise any clause all three judges missed. You have license to Read/Grep
> the repo to settle any point the bundle leaves open. Your verdict is authoritative;
> the panel's majority does not bind you.

The overseer may reason through the clauses first, then **ends** its reply with
exactly this block — the caller extracts the **last** such block, so any preamble is
harmless (a strong model will usually think out loud before it commits):
```
VERDICT: MET | NOT_MET
CONFIDENCE: 0.0-1.0
OVERRULED_PANEL: true | false   # true if your VERDICT differs from the panel's >=2/3 lean
REASON: two or three sentences — if OVERRULED_PANEL, say what the panel got wrong
GAPS: ["...", ...]   # empty if MET
```

If the overseer errors or returns unparseable output, do **not** silently fall back to
the panel majority — the deciding vote is missing. Report the gate as
**"undecided — overseer failed"** (which is not a MET) and surface the panel tally so
the caller can retry or escalate.

### 5. Emit the verdict (to the caller)

The headline verdict is the **overseer's**. Show the panel beneath it as advisory
context, and call out on the header line when the overseer overruled the panel — an
overturned majority is a notable event the caller should see.

```
GOAL <MET | NOT MET> — decided by Opus overseer<; OVERRULES panel | >
  Overseer   -> <MET|NOT_MET> (<confidence>): <reason>
  --- advisory panel (<met-count>/3) ---
  Literalist -> <MET|NOT_MET> (<confidence>): <reason>
  Verifier   -> <MET|NOT_MET> (<confidence>): <reason>
  Skeptic    -> <MET|NOT_MET> (<confidence>): <reason>
```

If **NOT MET**, follow with consolidated guidance — the overseer's `GAPS` (it has
already reconciled the panel's), rewritten as imperatives ("To satisfy the goal: ...")
so it feeds straight into the next work iteration.

Always end with a parseable block (a downstream parser reads the **last** such block
in the reply). `VERDICT` is the overseer's authoritative call; `PANEL` is the advisory
tally; `GAPS` carries the overseer's reconciled gap strings:
```
VERDICT: MET | NOT_MET
PANEL: <met-count>/3
OVERRULED_PANEL: true | false
GAPS: ["<raw gap>", ...]
```

## Edge cases

- **No check command and none inferable** -> say so and ask the caller for one. If
  there is genuinely nothing to run, proceed transcript-only but label the verdict
  **"unverified — transcript only"**, so a weak judgment is never mistaken for a
  context-verified one.
- **Check command fails to run** (missing tool / bad path) -> put the failure in the
  bundle; "could not verify" is evidence the goal is NOT demonstrably met.
- **Overseer errors or returns unparseable output** -> the deciding vote is missing;
  report **"undecided — overseer failed"** (not MET) with the panel tally attached, so
  the caller retries rather than trusting an unratified pass. Do NOT fall back to the
  panel majority — under "final say" the panel never decides.
- **Vague / unfalsifiable condition** -> the Literalist flags that it has no
  checkable clauses; the overseer returns that to the caller to sharpen the goal
  rather than guessing MET.

## Notes

- Pure prose skill — no scripts. The panel tally is advisory and by hand; the
  overseer's single verdict is authoritative.
- Uses the Agent tool with pinned models: **haiku** for the three panelists, **opus**
  (Opus 4.8) for the overseer. Claude Code only for now. A Grok-native port using
  `spawn_subagent` + a fast model for the panel and a frontier model for the overseer
  is a clean future addition (`SKILL.grok.md`).

---

*Part of [agent-shenanigans](https://github.com/pipXBT/agent-shenanigans).*
