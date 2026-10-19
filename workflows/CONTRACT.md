# Executor contract: adversarial-verification

Two executors implement this contract: `workflows/adversarial-verification.js`
(Claude Code, Workflow tool) and `workflows/adversarial-verification.rhai`
(Grok Build workflow). Both run the same fixture cases in
`workflows/fixture/cases/` and must produce the same results. Source: design
spec §4, `docs/superpowers/specs/2026-10-19-control-copy-design.md`.

## Conventions

- **Reports and predicates.** `X.field` names a field of the report an agent
  call returned; each check below names the report and field it reads. A check
  is false when the report is missing, the field is missing, or the field has
  the wrong type. A git report with `ok: false` fails every check on it, with
  one exception: a report whose `error` is `diff too large` still serves checks
  that do not read `diff`.
- **Stop** ends the run with `ok: false` at the stage named. **Fail the
  attempt** goes to [Failures](#failures).
- **Globs** (`rules.high_risk`, `rules.test_globs`, `forbid`) match the whole
  repo-relative path: `**` matches zero or more whole path segments, `*` any
  run of characters except `/`, `?` one character except `/`.
- **In `files` ∪ `tests`** means equal to a listed path, or under a listed
  entry that ends in `/`.
- **Docs path:** ends in `.md`, `.rst`, `.txt`, or `.adoc`, or starts with
  `docs/`. A **production path** is a path in `files` that is not a docs path.
- **Clean** means `porcelain == ""`. **Tracked-clean** means every line of
  `porcelain` starts with `??` (untracked files only; the index is empty).
- **`.git`** means the directory `git rev-parse --absolute-git-dir` prints. In
  a linked worktree that is the worktree's own git dir.

## 1. Inputs

| Arg | Type | Meaning |
|---|---|---|
| `repo` | str | Absolute repo path. Every agent works there. |
| `test_cmd` | str | Test command, run from `repo`. |
| `lint_cmd` | str, optional | Lint command. The gate runs lint only when it is given. |
| `plan_path` | str | The `superpowers:writing-plans` file. |
| `plan_hash` | str | sha256 hex of the plan file's bytes. |
| `branch` | str, optional | Branch to run on. Default: the current branch. |
| `rules` | `{high_risk: [glob], test_globs: [glob]}` | `high_risk` raises the complexity floor; `test_globs` splits review-fix paths. |
| `forbid` | `[glob]` | Paths no task may touch. |
| `level` | `"lite"` \| `"full"`, default `"lite"` | Which steps run, §5 [Levels](#levels). Any other value stops the run at stage `preflight`. |
| `review` | bool, default `true` | Run the review stage. Level `full` only. |
| `ponytail` | `"full"` \| `"ultra"` | Ponytail level pasted into every prompt. |
| `run_nonce` | str | New for every run. Pasted into every prompt. |
| `tasks` | `[{id, title, files, tests, kind, kind_source, complexity}]` | From the plan parser, §2. |
| `fixture` | object, optional | §8. |

A missing required arg or a wrong type stops the run at stage `preflight`
before any agent call.

## 2. Plan input

The entry skill parses the plan file in code
(`skills/run-plan/scripts/parse_plan.py`) before any agent runs and passes the
result as `tasks`:

- One task per `### Task N: <title>` heading outside code fences; `id` is
  `"N"`, `title` the heading text.
- Every backticked token on a `Create:`, `Modify:`, or `Delete:` line is a
  `files` path; every one on a `Test:` line is a `tests` path. `:line` ranges
  are stripped (`a.py:12-40` → `a.py`). A token without `/` takes the
  directory of the line's first token. Text after the first ` (` on such a line
  is ignored.
- Optional marker lines under a task, written by the owner or the plan
  author: `**Kind:** code|refactor|docs|test` and
  `**Complexity:** low|medium|high`. `superpowers:writing-plans` does not write
  them, so the skill says so when it starts.
- `kind` without a marker, derived in code: when `files` has no production
  path, `docs` if every path in `files` and `tests` is a docs path, otherwise
  `test` if `tests` is non-empty; anything else is `code`. A task with no
  paths at all is `code`, so validation flags it. `refactor` only ever comes
  from a marker. `kind_source` is `marker` or `derived`.
- `complexity` is the marker's value, or `null` without one.
- Validation stops the run before any edit, listing the tasks to fix or mark:
  a duplicate `id`; a `code` task with empty `files` or empty `tests`.
- Before the run starts, the skill shows each task's `kind` and `kind_source`.

## 3. Run state and branch

State file `.git/agent-shenanigans/<plan_hash>.json`:

```json
{"plan_hash": "<sha256 hex>", "run_start": "<sha>",
 "tasks": {"<id>": {"pre": "<sha>", "receipt": "<sha> or null"}}}
```

- `pre` is the task's pre-task SHA; `receipt` is the commit SHA after its
  `Task-Id` amend, written only after every check in step 6.
- Only the `git` agent's `write_state` action writes the file, at the points §5
  names. Prompts for `implement`, `skeptic`, `review`, `verify-finding`, and
  `fix-review` never mention it or the aside folder.
- The `git` agent copies `state_json` back by hand, and a long one-line copy
  can come back short. So a `read_state` whose `state_json` is not `""` and does
  not parse to an object, or a `write_state` whose `state_json` does not parse
  to the object written, is repeated once with a new `git` agent before the stop
  §5 names. Both checks compare parsed objects, never bytes. The Claude executor
  writes the state indented (`JSON.stringify(state, null, 2)`); Grok writes it
  compact.
- A task is done only when its `receipt` is an ancestor of `HEAD`. A
  `Task-Id` trailer in a commit message never marks a task done.
- Every run is a fresh run. Claude never passes `resumeFromRunId`; Grok never
  reattaches to an earlier agent. A restart is a new run, with a new
  `run_nonce`, that reads this file (§5, Run state).
- Branch: the resolved branch is `branch` if given, else the current branch.
  The run stops before checkout when that is the default branch, when the
  default branch cannot be determined, or when `HEAD` is detached. The tree
  must be clean, untracked files included.
- Aside folder `.git/agent-shenanigans/aside/`: `teeth/` holds added paths
  during one teeth step and `teeth_restore` empties it; `<since>.<n>/` holds
  untracked files moved by `move_untracked_aside` and the executor never
  empties it.
- The only reset is `git reset --keep <sha>`, never to a SHA below
  `run_start`. Restores use `git restore`. No other reset mode, no
  `git clean`, and no shelving of changes, in code or in any prompt.

## 4. The agent port

Each executor calls agents only through one helper,
`call(label, prompt, opts)`. It sets the model and effort (§6), passes the
label's output schema, rejects any model id containing `fable` before
spawning, and in fixture mode returns scripted output instead (§8).

### Labels

| Label | Tools | Output |
|---|---|---|
| `plan` | read-only | `{phases: [{name, subprojects: [{name, tasks: [{id, depends_on: [str], complexity, brief}]}]}]}` |
| `git` | execute | `GitReport` (below) |
| `test` | execute | `{test_exit: int, lint_exit: int \| null, tail: str}` |
| `implement` | all | `{summary: str, issues: [str]}` |
| `skeptic` | read-only | `{verdict: "pass" \| "fail", evidence: str}` |
| `review` | read-only | `{findings: [{file, issue, severity}]}` |
| `verify-finding` | read-only | `{real: bool, evidence: str}` |
| `fix-review` | all | `{summary: str}` |

- **read-only**: reads and searches files; no shell, no edits. These agents
  get the diff in their prompt.
- **execute**: has a shell, runs only the commands its prompt names, returns
  raw output, and judges nothing.
- **all**: full tools; edits and commits.
- `test` runs `test_cmd` in `repo`, then `lint_cmd` when given. `test_exit`
  and `lint_exit` are the exit codes; `lint_exit` is `null` without
  `lint_cmd`; `tail` is the last 200 lines of combined output.

### GitReport

`{ok: bool, error: str, head: str, tree: str, branch: str,
default_branch: str, porcelain: str, untracked: [str], name_status: str,
diff: str, last_message: str, base_is_ancestor: bool, state_json: str}`

The `git` prompt contains exactly one line `git action: <name> <params JSON>`,
for example `git action: reset_keep {"sha": "<sha>"}`. The agent runs that
action's commands in order and stops at the first failure. Then, whatever
happened, it fills every field. String fields hold the command's stdout with
trailing newlines removed.

| Field | Command |
|---|---|
| `head` | `git rev-parse HEAD` |
| `tree` | `git rev-parse HEAD^{tree}` |
| `branch` | `git branch --show-current` |
| `default_branch` | `git symbolic-ref --quiet --short refs/remotes/origin/HEAD` with the leading `origin/` removed; `""` when the command fails |
| `porcelain` | `git status --porcelain --untracked-files=all` |
| `untracked` | `git ls-files --others --exclude-standard`, one entry per line |
| `last_message` | `git log -1 --format=%B` |
| `name_status` | `git diff --no-renames --name-status <base> HEAD`; `""` without a base |
| `diff` | `git diff --no-renames <base>..HEAD`; `""` without a base |
| `base_is_ancestor` | `git merge-base --is-ancestor <base> HEAD` exits 0; `false` without a base |
| `state_json` | set only by `read_state` and `write_state`; `""` otherwise |

- `ok` is true when every action command exited 0 and every field command
  succeeded. `merge-base --is-ancestor` exiting 1 is a success (`false`), and
  a failing `symbolic-ref` gives `default_branch: ""`. `error` is `""`, or the
  failing command and the first 2000 characters of its stderr.
- When `diff` would exceed 200 000 characters, the report sets `ok: false`,
  `error: "diff too large"`, and `diff: ""`, and still fills the other fields.
- `<base>` is the action's `base` parameter; actions without one report no
  base.

### Git actions

| Action | Commands |
|---|---|
| `snapshot(base)` | None. `base` may be `""`. |
| `checkout_branch(name)` | `git switch <name>` when `git rev-parse --verify --quiet refs/heads/<name>` succeeds, else `git switch -c <name>`. |
| `read_state(plan_hash)` | `cat .git/agent-shenanigans/<plan_hash>.json` into `state_json`. A missing file gives `state_json: ""` with `ok: true`. |
| `write_state(plan_hash, json)` | `mkdir -p .git/agent-shenanigans`; write `json` byte for byte to `.git/agent-shenanigans/<plan_hash>.json.tmp`; `mv` it to `<plan_hash>.json`; `cat` the result into `state_json`. |
| `teeth_revert(base, paths)` | `.git/agent-shenanigans/aside/teeth/` must be absent or empty. Run `git diff --no-renames --name-status <base> HEAD`. For each listed path in `paths`: status `M`, `T`, or `D` → `git checkout <base> -- <path>`; status `A` → move the path to `.git/agent-shenanigans/aside/teeth/<path>`, creating parent folders. Any other status, or a path in `paths` the diff does not list, fails the action. Report fields use `base`. |
| `teeth_restore()` | `git restore --source=HEAD --staged --worktree -- :/` (puts back edits, additions, and deletions), then `rm -rf .git/agent-shenanigans/aside/teeth` (every file in it is back from `HEAD`). |
| `reset_keep(sha)` | `git reset --keep <sha>` |
| `move_untracked_aside(since)` | Move every path `git ls-files --others --exclude-standard` lists to `.git/agent-shenanigans/aside/<since>.<n>/<path>`, where `n` is the first integer from 1 whose folder does not exist (one `n` per call). |
| `amend_trailer(trailer)` | `before=$(git rev-parse HEAD^)`; `git commit --amend --no-edit --trailer "<trailer>"`; `test "$(git rev-parse HEAD^)" = "$before"`. For this action only, `base_is_ancestor` is that last command's result: `true` means the parent is unchanged. |

## 5. Steps and predicates

### Levels

`level` picks which steps run. Absent or `null` means `lite`.

| Step | `full` | `lite` |
|---|---|---|
| Preflight, plan stage (phases, deps, complexity), graph checks | yes | yes |
| Step 1: pre-task SHA, clean tree | yes | yes |
| Step 2: implement and its checks | yes | yes |
| Step 3: skeptic | yes | no |
| Step 4: teeth | by kind | no; every task records `teeth: "skipped:lite"` |
| Step 5: gate (docs-only scope for `docs` tasks, tests, lint when given, scope in `files` ∪ `tests`, outside `forbid`, branch) | yes | yes |
| Step 6: `Task-Id` amend and receipt | yes | yes |
| Failures: F1–F3 back to `pre`, then the retry rules | yes | yes |
| Restart from receipts | yes | yes |
| Review stage (§7) | when `review` is true | no; the run ends at stage `done` after the last task |

At `lite` the kind only picks the step 5 docs-only check; the skeptic question
and the step 4 check it would otherwise pick do not run. `S2.diff` is not
read, so a diff over the size limit does not fail the attempt.

### Preflight (stage `preflight`)

- **P1** `snapshot("")` → `P1`. Resolved branch `B` := `branch` if given, else
  `P1.branch`. Stop unless `P1.default_branch != ""`, `B != ""`,
  `B != P1.default_branch`, and `P1.porcelain == ""`.
- **P2**, only when `branch` is given and `branch != P1.branch`:
  `checkout_branch(B)` → `P2`. Stop unless `P2.branch == B` and
  `P2.porcelain == ""`.

### Plan (stage `plan`)

One `plan` call. Its prompt lists each task's `id`, `title`, `files`,
`tests`, and `kind`, and `plan_path` for the brief text. The executor ignores
any `files`, `tests`, or `kind` the output carries and checks in code:

- Every task `id` appears exactly once across all phases and subprojects, and
  the set of ids equals the set of `tasks[].id`.
- Every `depends_on` entry is a known id other than the task's own.
- No cycle: Kahn's algorithm places every task.
- Complexity: `tasks[i].complexity` when non-null, else the agent's value,
  which must be `low`, `medium`, or `high`. Then a floor raises it to `medium`
  when `files` has more than three paths or any `files` path matches a
  `rules.high_risk` glob. The floor never lowers.

Any failed check stops the run. No `git` action runs between P1/P2 and this
check. Tasks run one at a time in Kahn order; inside one wave, in `tasks`
order. The executor logs each wave's ids as parallel-eligible.

### Run state (stage `preflight`)

- `read_state(plan_hash)` → `ST`.
- **Fresh run**, when `ST.state_json == ""`: `run_start` := `ST.head`.
  `write_state` with `{plan_hash, run_start, tasks: {}}` → `W`. Stop unless
  `W.state_json` parses to the object written.
- **Restart**, otherwise. Stop unless `ST.state_json` parses to an object with
  `plan_hash == args.plan_hash`, a string `run_start`, and an object `tasks`.
  - `snapshot(run_start)` → `R0`. Stop unless `R0.base_is_ancestor` (`HEAD`
    descends from `run_start`) and `R0.porcelain == ""` (a dirty tree means an
    interrupted teeth step: stop and report it).
  - For each task with a non-null `receipt` `r`: `snapshot(r)` → `Rr`. The
    task is in the done set `D` only when `Rr.base_is_ancestor`.
  - Target `X` := `run_start` when `D` is empty. Otherwise `X` is the receipt
    of the task in `D` whose receipt is no other `D` task's `pre`; following
    `pre` links from it through `D`'s receipts must visit every task in `D`
    and end at `run_start`. Otherwise stop.
  - When `R0.head != X`: `reset_keep(X)` → `RK`. Stop unless `RK.head == X`
    and `RK.porcelain == ""`.
  - Set `receipt: null` for every task with a receipt outside `D`;
    `write_state` → `W`; stop unless `W.state_json` parses to the object
    written.
  - Tasks in `D` are skipped with outcome `done-before`.

### Per task (stage `task`, `task` = the id)

**Step 1, once per task.** `snapshot("")` → `S1`. Stop unless
`S1.porcelain == ""`. `pre` := `S1.head`. Set `tasks[id] = {pre,
receipt: null}`; `write_state` → `W`; stop unless `W.state_json` parses to
the object written.

Each attempt then runs steps 2–6.

**Step 2, implement.** One `implement` call. Its prompt carries the plan
brief, `title`, `files`, `tests`, `kind`, `forbid`, `test_cmd`, `lint_cmd`,
and "commit your work and leave the tree clean"; on a retry, also the failure
report and that the branch is back at `pre`. Then `snapshot(pre)` → `S2`.
Fail the attempt unless `S2.head != pre`, `S2.base_is_ancestor`, and
`S2.porcelain == ""`. `H` := `S2.head`; `T` := `S2.tree`; `changed` := the
paths in `S2.name_status`.

**Step 3, skeptic (`full` only).** One `skeptic` call with `S2.diff`,
`S2.name_status`, the brief, `files`, `tests`, and `forbid`, plus the
question for the kind. Fail the attempt without calling it unless `S2.ok`
(the diff fit).

- `code`: does the diff do what the brief says, and nothing outside it?
- `refactor`: is behaviour unchanged? If a path in `changed` is in `tests` or
  matches `rules.test_globs`, confirm no assertion was removed or weakened.
- `docs`: does the diff change documentation only?
- `test`: do the new tests assert real behaviour?

Fail the attempt unless `skeptic.verdict == "pass"`.

**Step 4, teeth by kind (`full` only).**

- `code`: `P` := `changed` ∩ `files`, minus every path in `tests`. Fail the
  attempt when `P` is empty. Otherwise `teeth_revert(pre, P)` → `TR`, then
  `test` → `TT`, then always `teeth_restore()` → `RS`.
  - Stop (no reset, no retry) unless `RS.head == H`, `RS.tree == T`, and `RS`
    is tracked-clean. Untracked files the test command wrote are not a
    failure.
  - Fail the attempt unless `TR.head == H` and `TT.test_exit` is an integer
    other than 0.
- `refactor`: no teeth. Its tests must pass at the gate; step 3 covers any
  test edit.
- `docs`: no teeth. Its scope check is in step 5.
- `test`: no teeth.

**Step 5, gate.** For kind `docs`, first fail the attempt unless every path
in `changed` is a docs path and none is in `tests` or matches
`rules.test_globs`; this runs at both levels, before the tests. Then `test` →
`G1`. Fail the attempt unless `G1.test_exit == 0`
and, when `lint_cmd` is given, `G1.lint_exit == 0`. Then `snapshot(pre)` →
`G2`. Fail the attempt unless `G2.head == H`, `G2.branch == B`,
`G2.branch != G2.default_branch`, `G2` is tracked-clean, every path in
`G2.name_status` is in `files` ∪ `tests`, and no path in `G2.name_status`
matches a `forbid` glob.

**Step 6, pass.** Requires step 2 and the gate; at `full`, also the skeptic,
and teeth unless the kind skips it.

- `snapshot("")` → `S6`. Fail the attempt unless `S6.head == G2.head` and
  `S6` is tracked-clean.
- `amend_trailer("Task-Id: <first 12 hex of plan_hash>/<id>")` → `A`. Stop
  (no reset, no retry) unless `A.ok`, `A.head != G2.head`,
  `A.tree == G2.tree`, `A.base_is_ancestor` (parent unchanged), and one line
  of `A.last_message` equals the trailer.
- Set `tasks[id].receipt` := `A.head`; `write_state` → `W`; stop unless
  `W.state_json` parses to the object written.
- When `A.untracked` is non-empty (files the test command wrote):
  `move_untracked_aside(pre)` → `MU`. Stop unless `MU.untracked == []` and
  `MU.porcelain == ""`.
- The task's outcome is `pass`.

### Failures

These stop the run with `HEAD` left as it is, with no reset and no retry: a
failed teeth restore (`RS`), a failed amend or post-amend check (`A`), and a
failed state write (`W`).

Any other failure runs, in order:

- **F1** `teeth_restore()` → `F1`. Stop unless `F1` is tracked-clean.
- **F2** `reset_keep(pre)` → `F2`. Stop unless `F2.head == pre`.
- **F3**, only when `F2.untracked` is non-empty:
  `move_untracked_aside(pre)` → `F3`. Stop unless `F3.untracked == []`.
- The last of these reports must have `porcelain == ""`; otherwise stop.

Then retry with a new `implement` agent, never the old one:

- Claude: the next attempt runs one tier up (low → medium → high); high
  stays high. At most two retries, three attempts in all.
- Grok: one retry, on the same model.
- When retries run out, stop with the task's outcome `fail`; `summary` names
  the predicate that failed last.

## 6. Models and modes

- **Claude.** `CLAUDE_MODELS = {low: "claude-haiku-5-5", medium:
  "claude-sonnet-5-5", high: "claude-opus-5-5"}`;
  `OTHER_MODEL = "claude-opus-5-5"`; `RUNNER_MODEL = "claude-haiku-5-5"`.
  `implement` gets the tier model for the attempt; `git` and `test` get
  `RUNNER_MODEL` (they run the commands named and return raw output, judging
  nothing); every other label (`plan`, `skeptic`, `review`, `verify-finding`,
  `fix-review`) gets `OTHER_MODEL`. Every call passes the
  full model id and `effort: "xhigh"`; no call inherits the session model.
  Read-only labels use agent type `agent-shenanigans:reader` (tools `Read`,
  `Grep`, `Glob`), never `Explore` or `Plan`.
- **Grok.** `GROK_MODEL = "grok-4.7"` on every `agent()` and
  `spawn_subagent` call. Grok's workflow `agent()` takes no effort, so effort
  `xhigh` is set when the workflow is launched; the entry skill refuses to
  start unless the session effort is `xhigh` and the route is the shell
  route.
- **No Fable.** `call` rejects a model id containing `fable` before spawning
  and stops the run at the current stage. The entry skill refuses to start in
  a session running on a Fable model.
- **What actually ran.** Read from the host's own record where one exists
  (Claude: the Workflow run journal; Grok: the child session's
  `summary.json`). A recorded model or effort that differs from the request
  fails the attempt. Where no record exists, `summary` says
  `model and effort: requested only`.
- **Prompts.** Every prompt starts with the modes block, then
  `Run nonce: <run_nonce>`. The modes block is `rules/modes.md` without its
  first (marker) line, with the ponytail level set to `ponytail`; caveman is
  `ultracave`. Each executor holds it as a constant kept equal to that file.
  The marker token never appears in a prompt.

## 7. Review stage (stage `review`)

Runs after every task passes, at level `full` when `review` is true;
otherwise the run ends at stage `done`.

- `snapshot(run_start)` → `RV`; stop unless `RV.ok`.
- Three `review` calls in one parallel batch, one per dimension, each given
  `RV.diff`, `RV.name_status`, `rules`, and `forbid`:
  1. claimed behaviour and interactions between the tasks;
  2. failure paths, lost work, and a success report that is false;
  3. forbidden changes and broken invariants named in the rules.
- One `verify-finding` call per finding, in one parallel batch. A finding is
  confirmed only when `real == true` and `evidence` is non-empty after
  trimming.
- No confirmed finding: the run ends at stage `done`.
- Fix scope, in code: the confirmed findings' `file` values, deduplicated,
  minus any that match a `forbid` glob. Those matching a `rules.test_globs`
  glob become `tests`; the rest become `files`. Both empty: stop.
- The fix runs as task `review-fix` through steps 1–6 with one attempt:
  `fix-review` replaces `implement`, and its prompt lists the confirmed
  findings with their evidence. It runs on `OTHER_MODEL` (Claude) or
  `GROK_MODEL`, outside the tier ladder. Its kind, set after step 2, is
  `code` when `changed` has a production path; else `docs` when every path in
  `changed` is a docs path in `files`; else `test`. So teeth runs only when it
  changed a production path, and never touches `tests`.
- Every stop inside `review-fix` is at stage `review`. On any failure: F1–F3
  back to its pre-fix SHA, then stop with `task: "review-fix"`. On pass the run ends at stage `done`.

## 8. Fixture

`args.fixture = {outputs: {<label>: [output, ...]}}`

- With a fixture present the executor never spawns. Each
  `call(label, ...)` returns that label's next output in order and records
  `{label, model, effort}` with the values `call` would have passed. A label
  with no outputs left returns `null`, which fails closed.
- Everything else runs unchanged: graph checks, predicates, the tier ladder,
  and the state writes, which are `git` calls like any other.
- `git` outputs are full `GitReport` objects. Leaving a field out exercises
  the fail-closed path for any check that reads it.
- A killed run is covered as a restart: the `restart-*` cases script the run
  state and `HEAD` an interrupted run leaves behind.
- Case file `workflows/fixture/cases/<name>.json`:
  `{name, args, fixture, expect: {ok, stage, task?, level?, outcomes: {id: outcome}}}`.
  The harness runs the executor with the case's `args` plus `fixture`. A case
  passes when `result.ok`, `result.stage`, `result.task` and `result.level`
  (each when given in `expect`), and each listed outcome match.
- Both executors run every case and must produce the same results.
  - Claude: `node --test tests/workflows/` runs every case through
    `workflows/fixture/harness.mjs`.
  - Grok: `python3 workflows/fixture/run_grok_case.py CASE.json [--rhai PATH]`
    runs one case through headless `~/.grok/bin/grok`, whose `workflow` tool
    runs the script with `validate_only: true`. The tool truncates a finished
    result, so the runner runs a temporary copy of the script with the case's
    args embedded and the result thrown. It prints the result JSON, then
    `PASS` or `FAIL` against `expect` (`ok`, `stage`, `task`, `level`,
    outcomes, and `summary` as a substring). It calls Grok, so it stays out
    of the test suite.

## 9. Result

`{ok: bool, stage: "plan" | "preflight" | "task" | "review" | "done",
task: str | null, summary: str, level: "lite" | "full" | null,
tasks: [{id, outcome: "pass" | "fail" | "done-before", attempts: int,
teeth: "ran" | "skipped:<kind>" | "skipped:lite", model: str}]}`

- `ok` is true only with `stage: "done"`.
- `stage` is where the run ended; `task` is the task it stopped in
  (`"review-fix"` for the fix), else `null`.
- `summary` says why the run stopped, naming the failed predicate's report
  and field, or what passed.
- `level` is the level the run used; `null` when the run stopped in the args
  check.
- `tasks` has one entry per task reached, in run order, with `review-fix`
  last when it ran. `attempts` counts `implement` (or `fix-review`) calls this
  run, `0` for `done-before`. `teeth` is `ran` when `teeth_revert` was called
  in the last attempt, else `skipped:lite` at level `lite` and
  `skipped:<kind>` at `full`. `model` is the model of the last `implement`
  or `fix-review` call, `""` for `done-before`.
