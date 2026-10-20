# The workflow

This repo is the control copy of one workflow that runs the same way on **Claude Code** or
**Grok Build**, whichever is open. The loop in one line:

**brainstorm → debate → write the plan → run the plan → clean up → map the code.**

What is mine and what is not: the debate runner, the plan executors, the entry skills,
`./doctor` and the modes file are owner-authored and live in this repo. Everything written by
someone else (superpowers, caveman, ponytail, cc-codemaps) is installed from upstream as-is and
only declared in [`stack.toml`](./stack.toml); nothing of theirs is copied here.

## Install

Both hosts, from a checkout of this repo. `./doctor` compares the machine to `stack.toml`. It
never deletes (it moves to `~/.agent-shenanigans-backup/<run-id>/`) and never runs `claude
plugin` or `grok plugin`; it prints those commands for you to run.

1. `./doctor` — read-only report. On a fresh machine expect exit 1 and the drift list
   (0 clean, 1 drift, 2 could not check).
2. `./doctor --fix` — patches the settings keys it owns, creates the caveman and ponytail mode
   configs and the declared links, and retires stale copies. Then run the `claude plugin` and
   `grok plugin` commands it prints: uninstall the explanatory-output-style and duplicate
   superpowers installs, and install shenanigans from this checkout on both hosts.
3. `./doctor --fix` again. Collision moves now pass their probes.
4. Probes. Run `/shenanigans:execute --probe` in a Claude session and `/execute --probe`
   in a Grok session, each from a directory outside this repo. Then `./doctor --seat-probe`.
5. One full debate on any spec with the repo debate skill. It writes the seat dry-run stamp.
   Run `./doctor --fix` once more: it retires `model-policy` and `debate-panel`, and prints the
   cc-debate uninstall.
6. `./doctor --accept`, then `./doctor` — expect exit 0.

The plugin was called `agent-shenanigans` before 2026-10-20; its commands are now
`/shenanigans:<skill>`. To move an existing install, run
`claude plugin uninstall agent-shenanigans@agent-shenanigans`, then
`claude plugin install shenanigans@agent-shenanigans`. On Grok, run
`~/.grok/bin/grok plugin uninstall agent-shenanigans`, then
`~/.grok/bin/grok plugin install <repo> --trust`. `./doctor --fix` prints these too.

Other flags: `./doctor --rollback <run-id>` undoes one `--fix` run from its backup folder, and
`./doctor --shas` prints the loaded plugin SHAs as JSON. Re-run `./doctor` after any plugin
update; `--accept` records the new SHAs as verified once both hosts load the same ones.

## The loop

| # | Stage | Invoke | What it gives you |
|---|-------|--------|-------------------|
| 1 | **Brainstorm** | `superpowers:brainstorming` | A design spec. |
| 2 | **Debate** | `shenanigans:debate` | Verdict on the spec from a 14-seat panel. |
| 3 | **Plan** | `superpowers:writing-plans` | A task-by-task plan file. |
| 4 | **Run** | `shenanigans:execute` | The plan executed task by task, each task gated; `--full` adds a skeptic, teeth, and a review pass. |
| 5 | **Clean** | `/code-cleanup` | Nine tiered agents sweep the result. Same loop, `/code-cleanup` as the executor. |
| 6 | **Map** | `/update-codemaps` | Fresh `codemaps/` for the next session. |
| ✓ | **Gate** | `check-in` | Evidence-checked "is it actually done", anywhere a wrong "done" is costly. |

Stages 1 and 3 stay entirely in superpowers; stage 6 is the cc-codemaps plugin.

### 2 · Debate

Seven personas (Skeptic, Architect, Pragmatist, Bullshit Detector, Constraint Engineer, Pager
Duty, Future Me), each run on Opus 5.5 and on Grok 4.7, both at `xhigh`: 14 seats from
`skills/debate/panel.json`, run by the repo's own seat runner on both hosts. Seats are read-only.
On Claude Code a round runs as the `debate-round` workflow, so `/workflows` shows each seat.

The round rule is mechanical. A round is **APPROVED** only when every requested seat returned,
every verdict is `APPROVED`, and the plan hash the seats saw matches the plan file. A persona
whose two models disagree makes the round **REVISE**. Subsets never produce the final APPROVED.
Revise and repeat for at most 3 rounds. At the cap with any seat still REVISE, stop and report
the open items; the owner may then sign off with **OWNER-ACCEPTED**, recorded with the open items
listed. It is never APPROVED, and it lets step 3 proceed.

### 4 · Run the plan

`execute` reads the plan file in code, shows each task's `kind` and `complexity`, states the
agent count, and waits for go. Claude Code starts `workflows/adversarial-verification.js` through
the Workflow tool; Grok Build runs `workflows/adversarial-verification.rhai`. Both implement
[`workflows/CONTRACT.md`](./workflows/CONTRACT.md) and pass the same fixture cases. `execute` is
lite by default (implement, test gate, receipt); `--full` adds the skeptic, teeth, and the review pass.

- **Phases.** A read-only plan agent groups tasks into phases and subprojects and gives each
  task `depends_on`, a complexity, and a brief. Tasks run one at a time in dependency order;
  parallel-eligible ones are logged. Optional `**Kind:**` and `**Complexity:**` marker lines under
  a task override what is derived; `superpowers:writing-plans` does not write them.
- **Tiers.** Complexity picks the model, always at `xhigh`: Claude uses Haiku 5.5 (low), Sonnet
  5.5 (medium) or Opus 5.5 (high); Grok uses `grok-4.7`. A failed Claude task is retried by a new
  agent one tier up (at most two retries); Grok retries once on the same model.
- **Teeth.** For a `code` task, the executor reverts the task's production files to their
  pre-task state and runs the tests: they must fail. Then it restores everything and runs the
  gate. A passing task gets a `Task-Id` trailer and a receipt in
  `.git/agent-shenanigans/<plan-hash>.json`; a restart trusts receipts, not commit messages.
  Skeptic, test and lint gate, path scope (`files`, `tests`, `forbid`) and the branch check
  surround it. It never runs on the default branch.
- **Review.** After the last task: three read-only reviewers, one verifier per finding, one fix
  round.

### 5 · Clean up

`/code-cleanup` recons once, then spawns nine fresh agents, one per concern, each on a fixed model
tier at `xhigh`. Dry-run by default; edit mode gives each its own git worktree, reconciled with a
3-way merge and the repo's verify scripts.

## Mine vs borrowed

| Piece | Origin |
|-------|--------|
| `debate` runner and panel, `execute` and the two executors, `check-in`, `skill-postmortem`, `./doctor`, `stack.toml`, `rules/modes.md` | Owner-authored, in this repo. |
| `code-cleanup`, the debate personas | Owner-authored adaptations of [STRML/cc-skills](https://github.com/STRML/cc-skills) and [STRML/cc-debate](https://github.com/STRML/cc-debate) (Samuel Reed, MIT); each credits its source and names what changed. |
| `superpowers:brainstorming`, `superpowers:writing-plans` | [obra/superpowers](https://github.com/obra/superpowers) (Jesse Vincent), installed as-is. |
| caveman | [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman), installed as-is. |
| ponytail | [ponytail](https://github.com/DietrichGebert/ponytail), installed as-is. |
| `/update-codemaps` | [STRML/cc-codemaps](https://github.com/STRML/cc-codemaps), installed as-is. |
