# goal-check Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Also consult **superpowers:writing-skills** for `SKILL.md` conventions and skill verification.

**Goal:** Add a `goal-check` skill to `agent-shenanigans` — a context-verifying goal-completion gate: a 3-judge Haiku panel (Literalist / Verifier / Skeptic, majority vote) that confirms a claimed goal against real evidence (a check command's output + repo state), not just the transcript.

**Architecture:** A pure prose `SKILL.md` (no scripts). The invoking/orchestrating agent supplies the condition, an optional check command, and context. The skill gathers a baseline evidence bundle once, spawns three Haiku Agent-tool subagents in parallel (each may pull more context — hybrid), tallies a 2-of-3 majority, and emits a parseable verdict with actionable gaps.

**Tech Stack:** Markdown skill (`SKILL.md` + YAML frontmatter); Claude Code Agent tool with `model: haiku`; symlink install via the repo's `install.sh`. Claude-only for v1 (Grok port deferred). `acpx` is intentionally NOT used — it is broken in this environment, so the panel runs as Agent subagents.

**Spec:** `docs/superpowers/specs/2026-06-01-goal-check-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `goal-check/SKILL.md` | The entire skill: frontmatter triggers + the 4-step procedure + 3 judge prompts + verdict format + edge cases. New. |
| `README.md` | Add one row to the "Skills in this repo" table. Modify. |
| `install.sh` | No change — auto-discovers any top-level dir containing `SKILL.md`. |

No scripts, no `references/`, no `SKILL.grok.md` in v1 (YAGNI — added only if a Grok port is requested).

---

## Task 1: Author the `goal-check/SKILL.md`

> **Post-implementation note (2026-06-01):** the canonical `SKILL.md` is the live
> file. The verbatim content below was refined during code review (commit
> `cc7831b`) with four changes — (1) the verdict block's `GAPS` carries raw deduped
> strings while the imperative phrasing lives in the prose guidance; (2) `CONFIDENCE`
> is surfaced per judge in the Step-4 verdict line; (3) the trigger `/goal-check`
> became `run goal-check` (no real slash command exists); (4) the Step-1 transcript
> bullet gained an "omit if no prior conversation (CI gate)" clause. Re-create from
> the live file, not this snapshot.

**Files:**
- Create: `goal-check/SKILL.md`

- [ ] **Step 1: Create the skill directory and write `SKILL.md`**

Write `goal-check/SKILL.md` with EXACTLY this content:

````markdown
---
name: goal-check
description: "Use to rigorously confirm a goal or completion condition is ACTUALLY met before declaring work done — the context-verifying alternative to Claude Code's built-in /goal evaluator (which judges only the conversation transcript). Runs a 3-judge Haiku panel (Literalist / Verifier / Skeptic) that checks the claim against real evidence — runs a check command and inspects repo state — and returns a majority verdict with actionable gaps. Triggers: 'is the goal met', 'verify the goal', 'check goal completion', 'confirm the goal is done', 'goal gate', '/goal-check'."
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
- Clip the slice of the transcript that states what was done / claimed.
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

Count MET votes. **>= 2 of 3 -> MET; otherwise NOT MET.** Confidence is
informational (it does not change the count). A judge that errored or returned
unparseable output counts as a NOT_MET abstention; note the degraded panel.

### 4. Emit the verdict (to the caller)

```
GOAL <MET | NOT MET> (<met-count>/3)
  Literalist -> <MET|NOT_MET>: <reason>
  Verifier   -> <MET|NOT_MET>: <reason>
  Skeptic    -> <MET|NOT_MET>: <reason>
```

If **NOT MET**, follow with consolidated guidance — the union of all `GAPS`, written
as imperatives ("To satisfy the goal: ...") so it feeds straight into the next work
iteration.

Always end with a parseable block:
```
VERDICT: MET | NOT_MET
VOTES: <met-count>/3
GAPS: [ ... ]
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
````

- [ ] **Step 2: Verify the frontmatter is valid and complete**

Run (this repo is cloned at `/Users/shawnhopkinson/PipXBT_Repo/agent-shenanigans`):
```bash
cd /Users/shawnhopkinson/PipXBT_Repo/agent-shenanigans
head -5 goal-check/SKILL.md
python3 -c "import sys,yaml; d=yaml.safe_load(open('goal-check/SKILL.md').read().split('---')[1]); assert d['name']=='goal-check'; assert 'description' in d and len(d['description'])>50; print('frontmatter OK:', d['name'])"
```
Expected: prints `frontmatter OK: goal-check` (the `name` is exactly `goal-check`; a non-trivial `description` is present). If `yaml` is unavailable, visually confirm the first block is `---`-delimited with `name:` and `description:` keys.

- [ ] **Step 3: Confirm the skill is self-contained**

Verify by inspection that `SKILL.md` depends on no scripts and no `references/` (those are out of scope for v1). The judge prompts and verdict format are inline. A prose *mention* of a future `SKILL.grok.md` port in the Notes section is expected documentation — not a dependency — so the check below deliberately does not match that filename.

Run:
```bash
grep -nE "scripts/|references/" goal-check/SKILL.md || echo "self-contained OK (no external refs)"
```
Expected: `self-contained OK (no external refs)`.

- [ ] **Step 4: Commit**

```bash
git add goal-check/SKILL.md
git commit -m "feat(goal-check): context-verified goal-completion gate skill

3-judge Haiku panel (Literalist/Verifier/Skeptic, majority vote) that confirms
a claimed goal against real evidence — runs a check command + reads repo state,
not just the transcript. Judge only, no loop; the calling orchestrator supplies
the goal. Pure SKILL.md; Agent-tool Haiku subagents (acpx is broken in this env).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Wire it into the repo (README + install discovery)

**Files:**
- Modify: `README.md` (the "Skills in this repo" table)

- [ ] **Step 1: Add the README table row**

In `README.md`, find the skills table (header row `| Skill | What it does | CLIs |`). Add this row after the `skill-postmortem` row:

```markdown
| [goal-check](./goal-check/) | Context-verified goal-completion gate. An orchestrating agent hands it a completion condition (and optionally a check command); the skill gathers real evidence — runs the check, reads repo state — then a 3-judge Haiku panel (Literalist / Verifier / Skeptic) votes by majority on whether the goal is *actually* met, returning actionable gaps. The rigorous alternative to the built-in `/goal` evaluator's transcript-only judging. | Claude |
```

- [ ] **Step 2: Verify `install.sh` discovers the new skill**

Run:
```bash
./install.sh --dry-run | grep -i goal-check
```
Expected: a dry-run line showing `goal-check [claude]` would be linked into `~/.claude/skills/`. (No row for grok-native, since there is no `SKILL.grok.md` — Grok reads it via `~/.claude/skills/` compatibility.)

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(goal-check): add skill to README table

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Behavioural verification (the "tests")

Skills are prose, so verification is a guided dry-run of the procedure against the
spec's fixtures. For each, walk the SKILL.md procedure and confirm the verdict shape
and outcome. Record the result; if the skill text produces the wrong outcome, fix
`SKILL.md` and re-run.

- [ ] **Step 1: Build a throwaway fixture repo**

Run:
```bash
TMP="$(mktemp -d)"; cd "$TMP"
mkdir -p src test
cat > test/run.sh <<'SH'
#!/usr/bin/env bash
# Fixture check command. Passes only if src/feature.txt contains "DONE".
grep -q DONE src/feature.txt && { echo "1 passed"; exit 0; } || { echo "0 passed, 1 failed"; exit 1; }
SH
chmod +x test/run.sh
echo "Fixture repo at: $TMP"
```
Expected: prints a temp path containing `test/run.sh` and an (initially absent) `src/feature.txt`.

- [ ] **Step 2: Test A — false-MET trap (the key case)**

Setup: condition = "the feature is complete and `test/run.sh` passes"; the transcript
*claims* "I finished the feature", but `src/feature.txt` does NOT contain `DONE`.

Run the check command the skill would run:
```bash
cd "$TMP"; echo "in progress" > src/feature.txt; ./test/run.sh; echo "exit=$?"
```
Expected: `0 passed, 1 failed` / `exit=1`.

Walk the procedure: the evidence bundle carries `exit=1`. The Verifier and Skeptic
must vote NOT_MET despite the transcript's claim; majority -> **NOT MET**, with a gap
like `"test/run.sh fails: feature.txt missing DONE"`. Confirm SKILL.md's procedure
yields this. **This is the behaviour the built-in transcript-only judge would get
wrong** — assert the skill does not.

- [ ] **Step 3: Test B — true MET**

Run:
```bash
cd "$TMP"; echo "DONE" > src/feature.txt; ./test/run.sh; echo "exit=$?"
```
Expected: `1 passed` / `exit=0`.

Walk the procedure: evidence bundle carries `exit=0` and `feature.txt` contains
`DONE`. All three lenses should vote MET; majority -> **MET (3/3)**, empty `GAPS`,
and the parseable block reads `VERDICT: MET`. Confirm SKILL.md yields this.

- [ ] **Step 4: Test C — no check command**

Setup: condition = "the docs read well" with no runnable check and none inferable.
Walk the procedure: per the "No check command" edge case, the verdict must be
labelled **"unverified — transcript only"** (NOT a silent context-verified MET).
Confirm SKILL.md's edge-case text produces this label.

- [ ] **Step 5: Clean up the fixture and commit any SKILL.md fixes**

```bash
rm -rf "$TMP"
cd /Users/shawnhopkinson/PipXBT_Repo/agent-shenanigans   # back to the repo
git diff --quiet goal-check/SKILL.md && echo "no fixes needed" || git commit -am "fix(goal-check): align SKILL.md with behavioural verification

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
Expected: either `no fixes needed`, or a commit recording the corrections the dry-runs surfaced.

---

## Task 4: Activate locally (optional — touches the live environment)

> This symlinks the skill into `~/.claude/skills/` so it is loadable. It is an
> install action, not a repo change. Skip if the user prefers to run `install.sh`
> themselves. A running `claude` session must be restarted to pick up a new skill.

- [ ] **Step 1: Symlink the skill in**

```bash
./install.sh goal-check
```
Expected: `ok goal-check [claude] (linked)` (or `already linked`).

- [ ] **Step 2: Verify the symlink**

```bash
ls -l ~/.claude/skills/goal-check
```
Expected: a symlink pointing at the repo's `goal-check/` directory.

---

## Definition of Done

- `goal-check/SKILL.md` exists with valid frontmatter (`name: goal-check`, trigger-packed `description`) and the full 4-step procedure, 3 judge prompts, verdict format, and edge cases.
- `README.md` skills table has the `goal-check` row.
- `install.sh --dry-run` discovers the skill.
- Behavioural fixtures pass: false-MET trap -> NOT MET; true MET -> MET; no-check-command -> "unverified — transcript only".
- All committed on `feature/goal-check-skill`; ready for the user's merge/PR decision (superpowers:finishing-a-development-branch).

## Verification results (2026-06-01)

The behavioural fixtures were run **live** — the actual 3-judge Haiku panel was
spawned via the Agent tool (`model: haiku`), exactly as `SKILL.md` prescribes — not
merely walked through on paper.

- **Test A — false-MET trap:** check command exits 1 (`feature.txt` lacks `DONE`)
  while the worker's transcript claims "it's complete and working." Panel returned
  **NOT MET (0/3)** — all three judges overrode the false claim on the exit code +
  file state. This is the exact case the built-in transcript-only `/goal` evaluator
  gets wrong. ✅
- **Test B — true MET:** `feature.txt` = `DONE`, check exits 0, truthful claim.
  Panel returned **MET (3/3)**. The Skeptic independently re-ran the check command
  (5 tool calls) before conceding — the hybrid "judges may pull more context" path
  exercised live. ✅
- **Test C — no check command:** confirmed by inspection that `SKILL.md`'s edge-case
  text labels the verdict **"unverified — transcript only"** rather than emitting a
  silent context-verified MET. ✅

Tests D (partial completion — multi-clause condition, one clause unmet) and E
(degraded panel — one judge errors → NOT_MET abstention + note) from the spec's
testing strategy were **deferred**: the false-MET trap (A) exercises the most
important discrimination, and the SKILL.md text already specifies both behaviours.
Behavioural coverage by the three live runs is sufficient for v1.

No `SKILL.md` changes were required by verification.
