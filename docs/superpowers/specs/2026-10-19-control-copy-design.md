# agent-shenanigans as a control copy — design

Date: 2026-10-19. Status: **OWNER-ACCEPTED** (2026-10-19), revision 4.
Debate rounds 1–3 each ended 14/14 REVISE, with the Opus judge also REVISE
each round; no persona split between Opus and Grok in any round. Revision 4
applies every round-3 finding and judge must-fix item. Those revision-4
changes are open items, addressed but not reviewed: restart and run state,
implement-step checks, teeth on deletions and renames, the failure and reset
path, plan-file parsing of `kind`, refactor and test-only tasks, the review
fix round's scope, the Grok retry, plugin SHA sources, seat allowlists, the
spawn probe, the Grok modes line, and the scripted fixture.

## Intent

This repo becomes the single control copy of one authored workflow that runs on
either host — Claude Code or Grok Build — depending on which one is open. It
holds only work the owner wrote. Everything written by someone else is
installed from upstream as-is and declared here, never copied here, so nothing
in the repo can silently go stale against its source.

Why now: a recon on 2026-10-19 found drift everywhere. Facts below were
re-checked after every plugin auto-updated at about 05:05 UTC that day.

- Claude Code does not have the agent-shenanigans plugin installed. The
  `compound`, `session-learnings`, `/init`, and `/code-cleanup` it runs come from
  symlinks into `~/cc-skills`, a STRML clone 16 commits behind `origin/main`
  with a 49-line local edit to `commands/code-cleanup.md`. Upstream has since
  deleted `bin/cc-fork` (909a8ee, "superseded by native subagent forks") and
  `commands/init.md` (f0e879f).
- Grok Build runs agent-shenanigans from its own clone at `a2b97fa` (the
  registry metadata still says `af40824`). Uncommitted checkout edits are live
  on neither host.
- `~/.grok/skills` holds 44 entries. Several are stale forks that win the bare
  `/name` over the plugin version: superpowers `writing-plans`,
  `subagent-driven-development`, `using-git-worktrees`, plus `compound`,
  `session-learnings`, `skill-postmortem`, `parallel-orchestrate`. Two more,
  `code-cleanup` and `debate`, are directories whose `SKILL.md` links to a
  `SKILL.grok.md` path the repo no longer has.
- Grok also reads `~/.claude/commands`, so the `~/cc-skills`
  `code-cleanup.md` and `init.md` links win bare `/code-cleanup` and `/init`
  on Grok as well.
- `~/.grok/workflows/adversarial-verification.rhai` is a real file, identical
  to the repo copy today, not a link.
- Two owner-authored skills, `model-policy` and `debate-panel`, exist only in
  `~/.grok/skills`, outside any repo. Both were made by `/learn`.
- Caveman and ponytail have no default level configured; neither config file
  exists.
- The cc-debate plugin auto-updated from 2.2.2 to 3.2.0. The owner's debate
  flow (direct Grok CLI, effort passthrough, Opus judge) lives in a local edit
  to the 2.2.2 plugin cache. 3.2.0 drops it, and its SessionStart hook repoints
  `~/.claude/debate-scripts` to 3.2.0, which hung a debate run on 2026-10-19.

## The workflow being controlled (owner's words, condensed)

1. `superpowers:brainstorming` produces a design spec.
2. The repo's debate skill reviews the spec; revise until approved.
3. `superpowers:writing-plans` produces the implementation plan.
4. A multi-agent workflow executes the plan. Every agent runs caveman `ultra`
   (id `ultracave`) and ponytail `full` (or `ultra` when the run asks for it).
5. `/update-codemaps`.

Code cleanup runs the same loop, with `/code-cleanup` as the executor.

### The implementation stage, always

- Split the build into **phases**; each phase into **subprojects**; each
  subproject into a **task list**.
- Every task declares its **dependencies**, so the run knows what can execute
  in parallel and what must be sequential.
- Every task gets a **complexity** rating and a model to match:
  - Grok: always the strongest Grok model at effort `xhigh`.
  - Claude: always effort `xhigh`, model Haiku 5.5 (low), Sonnet 5.5 (medium),
    or Opus 5.5 (high).
- **Claude only:** when an implementation agent fails adversarial verification,
  the retry is a *new* implementation agent one tier higher.

## Goals

1. One declarative list (`stack.toml`) of every plugin, link, and setting each
   host needs.
2. One command (`./doctor`) that checks a machine against that list and, with
   `--fix`, writes the files it owns and prints the rest.
3. The same behaviour on both hosts: caveman `ultracave`, ponytail `full`,
   effort `xhigh`, no Fable, "Opus 5" means Opus 5.5, for the main session and
   every agent this repo starts. Model and effort are explicit spawn
   parameters wherever the host's spawn API takes them; the modes block is
   pasted into every prompt this repo writes; a probe checks what actually
   arrived. A text file covers what no parameter can set. One exception:
   debate seats (§6) run with caveman and ponytail off, because their output
   is parsed and the panel compares reasoning, not style.
4. The implementation workflow above exists for both hosts, behind one
   contract and one scripted fixture that both executors run, and is started
   the same way on each.
5. The repo contains only owner-authored work. An adaptation of upstream work
   (today `code-cleanup` and the debate personas) is owner work when it
   credits its source and names its delta; a verbatim copy never is.

## Non-goals

- Re-implementing or patching any upstream plugin (caveman, ponytail,
  superpowers, cc-codemaps).
- Managing plugins unrelated to this workflow (vercel, taste-skill, figma,
  Plamen, etc.). `doctor` ignores what `stack.toml` does not name.
- Supporting hosts other than Claude Code and Grok Build.
- Controlling the model, effort, or modes of agents this repo does not start
  (Plamen workers and subagents, other plugins' subagents).

## Anti-goals (failure even if it "works")

- Any file in this repo that is a copy of upstream work.
- `doctor --fix` deleting anything. It moves, to a per-run backup folder.
- A subagent this repo starts that silently runs without the modes, or on the
  wrong model or effort.
- A bare `/name` on either host resolving to a stale copy instead of the
  declared source.
- An implementation run that loses a task's work, removes a commit it did not
  make, or marks a task done that did not pass.
- A debate seat or probe agent that can write, post, or act outside reading.

## Decided by the owner

- Install upstream as-is; nothing copied into this repo.
- Drop `compound`, `session-learnings`, and `/init`. (`/STRML-init` was first
  chosen; upstream deleted its target, so it is dropped with the repo's
  host-file delta. The built-in `/init` serves.)
- Debate (step 2) is the same on both hosts: one set of personas, and **every
  persona runs on both Opus 5.5 and the strongest Grok model, at `xhigh`**.
  The two models reason differently on the same persona; that difference is
  the point.
- Debate runs from a **repo-owned seat runner**, not cc-debate. Upstream
  cc-debate 3.2.0 cannot run this panel: its selector never reuses a model, so
  two models fill 2 of 14 seats; it drops effort on Opus and Grok seats; it has
  no Grok transport; and `/debate:all` spawns a Fable teammate.
- Grok seats may review private-repo code (code is sent to xAI).
- `code-cleanup` uses **fresh tiered agents** per mandate (written brief, tier
  model, `xhigh`). The native fork cannot set a model, and upstream deleted
  `cc-fork`.
- The shape below (stack list + doctor + modes file + two-host implementation
  workflow) — approved in conversation.

## Components

### 1. `stack.toml`

Declares, per host:

- **Plugins**: name, source (marketplace id or git URL, plus subdir when the
  vendor ships one), the exact install id on each host, the required state on
  each host (`enabled` or `absent`), and the commit SHA last verified by a
  probe.
  - Plugins keep tracking upstream through each host's auto-update; the SHA is
    a record, not a lock. Never compare version strings.
  - Where the SHA comes from: on Claude, `gitCommitSha` of the
    `~/.claude/plugins/installed_plugins.json` entry whose `installPath` is
    loaded (Claude's plugin caches are plain copies, not git checkouts). On
    Grok, `git rev-parse HEAD` of the loaded directory for a Git install; for
    a Local install that is a copy (ponytail, `skills-de21f7e8`), the HEAD of
    its source checkout (`~/.grok/marketplace-cache/350a43727a88bc9c`) plus a
    content hash of the copy, so a stale copy shows. Never `registry.json`.
  - Required `enabled`: caveman, ponytail, superpowers, cc-codemaps,
    agent-shenanigans. Claude superpowers is
    `superpowers@claude-plugins-official`.
  - Required `absent`: `superpowers@superpowers-marketplace`,
    `explanatory-output-style@claude-code-plugins`, and
    `explanatory-output-style@claude-plugins-official`. Claude-installed
    plugins load on Grok whatever Claude's `enabledPlugins` says (`grok
    inspect` shows the explanatory hook running there), so "disabled" cannot
    hold on Grok; the state is `absent`, and `doctor` prints
    `claude plugin uninstall <id>`.
  - cc-debate (`debate@cc-debate`) becomes `absent` once the repo seat runner
    passes its dry run, which writes a stamp `doctor` reads (§6). Until then it
    is informational. While it is installed, the repo's debate skill does not
    claim `/debate:all` or "run debate" as triggers.
- **Links**:
  - `~/.grok/workflows/adversarial-verification.rhai` → repo.
  - `~/.claude/rules/agent-shenanigans.md` → repo `rules/modes.md` (§3).
  - The Claude workflow script is not linked; the entry skill passes its
    plugin path to the Workflow tool (§4).
- **Clones**: none. Nothing in the workflow depends on `~/cc-skills` any more.
  `doctor` never writes to it.
- **Retire list**: names that must be absent at user level on both hosts
  (§2).
- **Settings** (each a single key, patched in place):
  - `$XDG_CONFIG_HOME/caveman/config.json` (default `~/.config/...`) →
    `defaultMode = "ultracave"`.
  - `$XDG_CONFIG_HOME/ponytail/config.json` → `defaultMode = "full"`.
  - Grok `~/.grok/config.toml` → `[models] default = "grok-4.7"` (file says
    `grok-4.6`) and `default_reasoning_effort = "xhigh"`. The existing
    `[model."grok-4.7"] context_window = 500000` is load-bearing.
    `[ui] fork_secondary_model` is the fork pane, not subagent routing; leave
    it alone. `[features] subagent_model_inheritance` is set to `false` only if
    the probe shows it rejects an explicit `model`. `[paths] extra_rule_dirs`
    only as the §3 fallback (the table does not exist yet; `doctor` may create
    it).
  - Claude `~/.claude/settings.json` → top-level `effortLevel = "xhigh"`
    (already set). The `modelSettings` entries (five per-model `effortLevel`
    keys, including `claude-fable-5-1`) are left alone.

Known facts the builder can rely on:

- Caveman 4.0.1 resolves its mode `CAVEMAN_DEFAULT_MODE` → repo
  `.caveman.json` / `.caveman/config.json` → user config → `caveman`. A repo
  file set to `off` also suppresses its `SubagentStart` injection. `claude -p`
  and SDK sessions start in `manual` (no ruleset) unless
  `CAVEMAN_DEFAULT_MODE` is set. The `ultracave` skill has
  `disable-model-invocation: true`, so a model cannot load it by name; it can
  read the skill file.
- Ponytail 5.3.2 resolves `PONYTAIL_DEFAULT_MODE` → user config → `full`,
  accepts `off`, ships a `SubagentStart` hook, and has no headless exemption.
- Neither plugin's hooks run on Grok: Grok reads plugin hooks only from
  `hooks/hooks.json`, and both plugins declare them elsewhere.
- Grok reads Claude-installed plugins' skills, agents, and hooks (tagged
  `[claude]` in `grok inspect`), `~/.claude/commands`, and scans `~/.claude/`
  including `~/.claude/rules/` under `compat.claude.rules` (on). Grok's view of
  plugin state comes from `grok inspect`, not `grok plugin list` (native
  installs only) and not Claude's `enabledPlugins`.
- Some shells put the cmux `grok` wrapper, which installs cmux hooks, ahead of
  the real binary. `doctor` and the debate runner always call
  `~/.grok/bin/grok`.
- `~/.grok/config.toml` sets `[ui] permission_mode = "always-approve"`, which
  headless Grok inherits; Grok's `--permission-mode plan` does not stop tools
  under it.
- `~/.claude/settings.json` sets `permissions.defaultMode = "auto"`,
  `outputStyle = "Terse"`, and denies `Bash(git reset --hard*)`. Agents and
  `claude -p` inherit all three.
- A cleanup on 2026-08-07 removed `.md` files from `~/.claude/rules` to cut
  always-loaded context. If that happens again, `doctor` reports the link as
  missing.
- Claude Workflow `agent()` takes `model`, `effort`, `isolation`, `agentType`;
  it inherits the session model when `model` is omitted, returns no model id,
  and on `resumeFromRunId` replays cached results. The `Explore` and `Plan`
  agent types skip CLAUDE.md and rules.
- Grok workflow `agent()` takes `label`, `phase`, `capability_mode`,
  `output_schema`, `agent_type`, `model`, `isolation_worktree`, `resume_from`
  (no effort), and returns `agent_id`, `success`, `output`, `cancelled`,
  `tokens_used`, `duration_ms` (no model). Grok's "daemon route" does not run
  `.rhai` at all and its `host.agent` takes no `model`.
- `claude` takes `--model`, `--effort`, `--tools`, `--strict-mcp-config`,
  `--settings`; `grok` takes `-m`, `--reasoning-effort`, `--prompt-file`,
  `--tools`, `--disallowed-tools`, `--sandbox`, `--no-subagents`,
  `--disable-web-search`, and the hidden `--no-memory`.
- In `claude -p`, `--permission-mode plan` wrote a plan file under
  `~/.claude/plans/` on 2026-10-19; it is not used for seats.

### 2. `./doctor`

A single stdlib-only Python script at the repo root.

- `./doctor` — read-only report, grouped by host: missing, wrong state,
  version mismatch between hosts, "updated since verified", the
  agent-shenanigans install differing from this checkout's `HEAD`, shadowed (a
  user-level copy that wins a bare `/name` over the declared source), retired
  names present, settings that differ, links missing or pointing elsewhere,
  Grok on the daemon route or a generated `adversarial-verification.js`
  present, and probe results missing, failing, or stale.
- Exit codes: `0` clean, `1` drift (every item above), `2` could not check (a
  CLI missing, a file unparseable). Informational, never affecting the exit
  code: unmanaged entries, cc-debate before its retirement stamp, and an
  auto-installed xAI copy (Grok `official_marketplace_auto_installed = true`)
  whose SHA matches the other host. A machine in the declared state exits `0`.
- `./doctor --fix` writes only what it owns:
  - Settings keys. JSON files are parsed and only the declared key changes.
    TOML is edited by line inside the target table (creating `[paths]` only
    for the §3 fallback), since `tomllib` cannot write. After the edit the
    file is re-parsed and the write is refused unless `[models] default`,
    `default_reasoning_effort`, the `grok-4.7` `context_window = 500000`, and
    `fork_secondary_model` are as expected. Writes go to a temp file, then an
    atomic rename. A file that does not parse is left alone and reported.
  - The two mode configs. A missing file is created with only `defaultMode`;
    an existing file changes only `defaultMode`.
  - Declared symlinks, only when the target exists. A real file at the link
    path moves to the run folder first.
  - Retired names: moved to the run folder (absence is the winner), with two
    exceptions: `model-policy` and `debate-panel` move only after the spawn
    probe passes on both hosts and bare `/debate` resolves to the repo skill.
    The dead `~/.grok/skills/code-cleanup` and `~/.grok/skills/debate`
    directories are retired names.
  - Collisions (a user-level skill or command with the same name as one a
    declared plugin ships): move it to the run folder, run that host's
    resolution probe (Grok: `~/.grok/bin/grok inspect`; Claude: builder's
    call), and move it back if the declared source does not win. Each step is
    a manifest line. `~/.claude/commands/code-cleanup.md` is attempted only
    after §5's safety rules are in the repo skill, and must pass the probe on
    both hosts, since Grok reads that directory too.
  - It never runs `claude plugin` or `grok plugin`, and never touches a git
    clone. It prints those commands in order: uninstall, install, enable,
    then "re-run `./doctor --fix`".
- Every `--fix` run takes a lock and gets a run folder
  `~/.agent-shenanigans-backup/<YYYY-MM-DDTHHMMSS>/` with a pre-image of every
  file it changes (relative paths kept) and an append-only `manifest.tsv`, one
  line per completed action: `patched`, `created`, `linked`, `moved`,
  `moved-back`.
- `./doctor --rollback <run-id>` undoes that run's actions in reverse, file by
  file: a patched file gets its pre-image; a created file or link moves to the
  run folder (never deleted); a moved file moves back. It never writes through
  a symlink: a link is moved aside before its pre-image is restored. A file
  whose live content is not what the run wrote is skipped and reported; the
  rest proceed. A rolled-back run does not block rollback of earlier runs.
- Day one is two `--fix` runs with the printed plugin commands between them.
- `./doctor --accept` records the loaded SHAs as verified, only when both
  hosts load the same SHA for each plugin, the agent-shenanigans install
  matches this checkout's `HEAD`, and both probe results are passing and newer
  than the last SHA change.

#### Probe

Two parts, both required before `--accept`:

- **Spawn probe**, run once per host from a session: the entry skill's
  `--probe` mode spawns one agent through the §4 spawn call with no tools at
  all (Claude: a repo agent type whose tool list is empty, never `Explore` or
  `Plan`; Grok: a capability mode without file, shell, or search tools), from
  a scratch directory outside this repo. The probe prompt carries no modes
  paste, no token, no path, and no mention of this repo. The agent returns
  the token on the modes file's marker line and any mode-activation text it
  received. Pass on Claude needs the token plus hook-only activation strings
  for caveman `ultracave` and ponytail `full`; pass on Grok needs the token
  (Grok has no hooks; its agents get the modes from §4's paste). The host's
  run record must show no tool call. The skill adds the requested model and
  effort, whatever the host recorded, the Grok route (shell or daemon), and
  writes `~/.agent-shenanigans-probe/<host>.json`.
- **Seat probe**, run by `doctor`: one tiny argv per seat type (§6). It checks
  that text returns and the verdict parses, that the tool list the seat
  reports at start is exactly the allowlist, and that a prompted write
  attempt is refused. File-write checks are scoped to the seat's cwd, the
  reviewed repo, and `~/.claude/plans/` (both CLIs always write session
  transcripts elsewhere).

### 3. Modes file

One short, owner-authored file, `rules/modes.md` in the repo (the only file in
that directory), linked to `~/.claude/rules/agent-shenanigans.md`. Claude
loads `~/.claude/rules/*.md` into every session; Grok scans
`~/.claude/rules/` under `compat.claude.rules`. If the probe shows Grok does
not load it, `doctor` sets Grok's `[paths] extra_rule_dirs` to the repo's
`rules/` directory. Nothing goes in `~/.claude/CLAUDE.md`, so Plamen's
managed markers are never touched.

Contents:

- First line: `agent-shenanigans modes <random hex token>` — the token is
  fixed in the repo and never appears in any prompt this repo writes.
- In interactive sessions and in agents this repo starts: caveman at
  `ultracave` and ponytail at `full`, unless the user or the task prompt sets
  another level. Code, comments, commits, and docs stay normal English.
- On Grok, where these plugins' hooks do not run, an interactive session
  reads the caveman plugin's `skills/ultracave/SKILL.md` and the ponytail
  skill at `full` at session start (the path is in `grok inspect`).
- Effort `xhigh` for every agent this repo starts unless the user says a task
  is simple. Never use Fable. "Opus 5" means Opus 5.5.
- For agents this repo starts, if another skill or prompt names a weaker model
  or lower effort, this file wins unless the user says otherwise. It does not
  change the models other tools choose for their own agents.
- A headless run whose output a program parses (`claude -p`, `grok
  --prompt-file`, Plamen workers, debate seats) writes normal prose in its
  required format. This rule wins over every line above for those runs.

What it cannot do: set a model or an effort, or guarantee a mode in an agent.
§4, §5, and §6 set model and effort where the spawn API takes them, and §4
and §5 paste the modes block (without the marker line) into every prompt they
write, on both hosts, whether or not the probe passes.

Accepted side effect (owner's call to revisit): the file loads in every
session on the machine, including Plamen audits; its scope lines keep it out
of Plamen's model choices and parsed output.

### 4. Implementation workflow, both hosts

One contract, `workflows/CONTRACT.md`, and one scripted fixture. Both
executors run the fixture as their acceptance test.

#### Plan input

- The entry skill reads the `superpowers:writing-plans` file in code, before
  any agent runs, and passes the result in the executor's arguments:
  - Each `### Task N` section's `Create:` and `Modify:` paths become `files`,
    with `:line` ranges stripped; `Test:` paths become `tests`.
  - Optional marker lines the contract defines, written under a task by the
    owner or the plan author: `**Kind:** code|refactor|docs|test` and
    `**Complexity:** low|medium|high`. writing-plans does not write them, so
    the skill says so when it starts.
  - Without a `Kind:` marker, `kind` is derived in code: no production path in
    `files` makes `docs` if every path is documentation, otherwise `test` if
    `tests` is non-empty; anything else is `code`. `refactor` only ever comes
    from a marker.
  - Validation in code stops the run before any edit when a `code` task has
    empty `files` or empty `tests`, listing the tasks for the owner to fix or
    mark.
  - Before the run starts, the skill shows each task's `kind` and whether it
    was marked or derived.
- **Plan** stage: one read-only agent groups the tasks into phases and
  subprojects and returns `depends_on`, a complexity, and a brief per task.
  The executor ignores any `files`, `tests`, or `kind` it returns. It
  validates the graph in code (unique ids, known deps, no cycles).
- Complexity: the agent's value; a `Complexity:` marker replaces it; then a
  floor raises it to at least `medium` when the task touches more than three
  files or a `rules.high_risk` path. The floor never lowers.

#### Run state and branch

- Inputs: `repo`, `test_cmd`, the plan path, optional `lint_cmd` (the gate
  runs lint only when it is given), `branch`, `rules` (`high_risk`,
  `test_globs`), `forbid`, `review` (default true), `ponytail`
  (`full` | `ultra`).
- Resolve the branch name first: the `branch` input, else the current branch.
  If that name is the repo's default branch, or the default branch cannot be
  determined, stop before checkout. If `branch` was given and differs from the
  current branch, check it out or create it. Require a clean tree
  (`git status --porcelain` empty, untracked included).
- Run state lives in `.git/agent-shenanigans/<plan-hash>.json`: the plan
  hash (sha256 of the plan file), the run-start SHA, each task's pre-task SHA,
  and a pass receipt per task (the commit SHA after its amend). Only the
  executor's git step writes it, and only after the checks below. Implementer
  prompts never mention it.
- Every run is a fresh run. A Claude run is never resumed with
  `resumeFromRunId`; each run passes a run nonce in its prompts.
- Restart reads the run state. A task is done only if it has a receipt whose
  SHA is an ancestor of `HEAD`. If the tree is dirty, stop and report (an
  interrupted teeth step). Otherwise commits after the last receipt, or after
  the run-start SHA if there is none, are removed with
  `git reset --keep <that SHA>`. Never reset below the run-start SHA; stop if
  `HEAD` does not descend from it.

#### Tasks

One task at a time on both hosts, in dependency order. The executor logs which
tasks were parallel-eligible. Every diff below uses `--no-renames`. Per task:

1. Record the pre-task SHA (`HEAD`) in the run state; require a clean tree.
2. Implement. The implementer commits its work. Then require: `HEAD` differs
   from the pre-task SHA, the pre-task SHA is an ancestor of `HEAD`, and the
   tree is clean. Otherwise the attempt fails.
3. Skeptic (read-only) reviews `git diff --no-renames <pre-task SHA>..HEAD`,
   and checks no `forbid` path is touched.
4. Teeth, for `kind: code`:
   - Take `git diff --no-renames --name-status <pre-task SHA> HEAD` ∩ `files`.
     Modified and deleted paths are checked out from the pre-task SHA; added
     paths are moved to `.git/agent-shenanigans/aside/`. `tests` are never
     touched.
   - Run the tests; they must fail.
   - Restore with `git restore --source=HEAD --staged --worktree -- :/`
     (puts back edits, additions, and deletions), then empty the aside folder.
     Tracked state must match `HEAD` and `HEAD` must be unchanged; untracked
     files the test command wrote are not a failure.
   - `refactor` never runs teeth: its existing tests must pass, and if it
     changed a test file the skeptic must confirm no assertion was removed or
     weakened. `docs` skips teeth and fails if its diff touches any test or
     production path. `test` skips teeth and the skeptic confirms the new
     tests assert real behaviour.
5. Gate: test (and lint when given) pass; the diff's paths are within
   `files` ∪ `tests` and outside `forbid`; the branch is the resolved
   non-default branch.
6. Pass needs step 2's checks, skeptic, gate, and teeth unless the task's
   `kind` skips it. Then, with `HEAD` still the SHA the gate checked and the
   index empty, amend to add `Task-Id: <plan-hash prefix>/<id>`. After the
   amend, `HEAD^{tree}` and the parent must be unchanged and the message must
   carry the trailer. Then write the receipt.

Failures:

- A failed teeth restore, a failed amend, or a failed post-amend check stops
  the run with `HEAD` left as it is: no reset, no retry.
- Any other failure: restore the tree to `HEAD` as in step 4, then
  `git reset --keep <pre-task SHA>` (the user's settings deny
  `git reset --hard` and `git clean -fd`), move untracked files created since
  the pre-task SHA to `.git/agent-shenanigans/aside/`, require a clean tree,
  and retry:
  - Claude: a new implementation agent one tier up (Haiku → Sonnet → Opus),
    given the brief, the failure report, and that the branch is back at the
    pre-task SHA; at most two retries; Opus retries at Opus.
  - Grok: one retry by a new agent on the same model, given the same three
    things. `resume_from` is not used.
  - When retries run out, the run stops and reports the task and why.

#### Review

Three read-only reviewers on distinct dimensions, one adversarial verifier per
finding, one fix round. Before the fix agent runs, the executor derives its
`files` and `tests` in code from the verified findings' paths, split by
`rules.test_globs`; `forbid` still applies. The fix goes through steps 1–6 as
task `review-fix` (teeth only when it changed a production path), outside the
tier ladder. On failure the branch is reset to the pre-fix SHA and the run
stops.

#### Checks fail closed

Neither executor can run shell from its own script. Every git or test step is
done by an agent that returns raw output — `git rev-parse HEAD`,
`git rev-parse HEAD^{tree}`, `git status --porcelain`,
`git diff --no-renames --name-status`, `git branch --show-current`,
`git log -1 --format=%B`, `git merge-base --is-ancestor` exit code, the test
and lint exit codes — and the executor checks the predicate named at that step
against the SHAs it recorded. A failed predicate or a missing field stops the
run (or fails the attempt, as listed above).

#### Models and modes

- Claude: every `agent()` call passes an explicit full model id
  (`claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`) and
  `effort: "xhigh"`. Implementation agents get the tier model; every other
  agent gets `claude-opus-5-5`. No agent inherits the session model.
  Read-only agents use a repo agent type with read-only tools, never
  `Explore` or `Plan`.
- Grok: every `agent()` and `spawn_subagent` call passes `model: "grok-4.7"`.
  Grok workflow `agent()` takes no effort, so effort `xhigh` is set when the
  workflow is launched, and the entry skill refuses to start unless the
  session effort is `xhigh` and the route is the shell route.
- Model ids come from tables in the executor's code; an id containing `fable`
  is rejected before spawn. The entry skill refuses to start in a session
  running on a Fable model.
- The model and effort that actually ran are read from the host's own record
  where one exists (builder verifies: the Claude Workflow run journal; Grok's
  child session `summary.json`). A recorded value that differs from the
  request fails the task. Where no record exists, the result says "requested
  only" and the probe is the evidence.
- Every prompt the executor writes starts with the modes block (caveman
  `ultracave`, ponytail from the `ponytail` input, marker line omitted), on
  both hosts.

#### Scale

A run spawns about seven agents per task plus the review stage. The entry
skill states the expected agent count before it starts. If the Claude host's
workflow size guideline would trim the run, the owner raises "Dynamic workflow
size" in `/config`.

#### Per host

- **Grok**: `grok/workflows/adversarial-verification.rhai`, rewritten to the
  contract. Today it diffs and checks out `HEAD~1`, judges `teeth_ok` and
  `test_ok` by agent opinion, resumes the implementer on failure, pastes
  caveman `ultra`, and commits the review fix after tests and lint only; all
  of that changes.
- **Claude**: a new Workflow-tool script in the repo, same contract.
- **Entry point**: one repo skill (name: builder's call; avoid
  `implement`/`execute-plan`, which Grok bundles, and the workflow's own name).
  It parses the plan file (above), refuses a Fable session, and starts the
  host's executor with the same arguments: the Workflow tool with `scriptPath`
  set to the script in the installed plugin on Claude, the named workflow on
  Grok. It also has the `--probe` mode (§2).

#### Fixture

A scratch repo plus a scripted agent port: both executors accept stub agents
that return fixed graphs and fixed raw git and test fields, with inputs to
inject a failure or a kill. Each case states its expected outcome:

- adds a production file: passes;
- deletes a production file, and renames one: pass, with teeth restoring both;
- `docs` task: passes with teeth skipped; a `docs` task whose implementer
  commits nothing: fails at step 2;
- `test` task: passes with teeth skipped;
- `refactor` that edits a test: passes when the skeptic confirms no weakened
  assertion, fails when it does not;
- first attempt fails the gate, retry passes;
- a fixed cyclic graph: rejected before any commit;
- killed before any receipt: restart resets to the run-start SHA;
- killed after a receipt with a receipt-less commit on top: restart removes
  only that commit;
- a killed commit carrying a forged `Task-Id` but no receipt: treated as not
  done;
- review fix that edits a test: the test stays out of teeth.

Both executors must produce the same outcomes.

### 5. code-cleanup

Only §4's spawn rule carries over, not its task machine:

- Each mandate is a fresh agent with a written brief (the Phase 1 recon
  pasted), a fixed tier, explicit model and effort, and the modes block. On
  Claude it is spawned with Workflow `agent()`, the call the probe covers; on
  Grok with `spawn_subagent` on `grok-4.7`. The native fork is not used, since
  it cannot set a model.
- The skill keeps its own modes: dry-run by default; edit mode gives each
  mandate its own git worktree and branch, and Phase 3 reconciles them. Its
  mandates are behaviour-preserving, so there is no teeth step; the reconcile
  runs the repo's verify scripts.
- `skills/code-cleanup/scripts/cc-fork` is removed.
- First, before any other change in this section: the 49 lines of safety rules
  in the `~/cc-skills` local edit (hard exclusions, dirty-tree and
  default-branch pre-flight, run the repo's verify scripts at reconcile, "the
  boundary outranks the mandate", recovery rules) are ported into
  `skills/code-cleanup`, read from the clone without changing it. Today's
  Claude and Grok `/code-cleanup` both run that edited file, not the repo
  skill.

### 6. Debate panel, both hosts

- **Panel config**: `skills/debate/panel.json` in the repo, the 14 seats of
  today's `~/.claude/debate-acpx.json`: seven personas — Skeptic, Architect,
  Pragmatist, Bullshit Detector, Constraint Engineer, Pager Duty, Future Me —
  each as `<persona>-opus` (`claude-opus-5-5`) and `<persona>-grok`
  (`grok-4.7`), all `effort: "xhigh"`, with system prompt and timeout. It
  replaces `debate-acpx.example.json`. The runner reads only this file.
- **Seat runner**: one stdlib script in `skills/debate/scripts/` that runs the
  requested seats in parallel and writes `<seat>-output.md`,
  `<seat>-exit.txt`, and the logged argv per seat. The session starts it in
  the background and waits for it (a round can take 30 minutes; Claude's
  foreground shell limit is 10). The same script runs on both hosts. Seats
  are read-only by allowlist, not denylist:
  - Opus seats: `claude -p --model claude-opus-5-5 --effort xhigh
    --tools Read,Grep,Glob --strict-mcp-config
    --settings '{"outputStyle":"default"}'`, Claude's nested-session variables
    unset, `CAVEMAN_DEFAULT_MODE=off`, `PONYTAIL_DEFAULT_MODE=off`.
  - Grok seats: `~/.grok/bin/grok --prompt-file … -m grok-4.7
    --reasoning-effort xhigh --tools <read-only list> --no-subagents
    --disable-web-search --no-memory --output-format plain`, with MCP off
    (builder confirms the flag; `--sandbox` read-only if `--tools` cannot
    exclude MCP).
  - The runner adds one plain-prose line to every seat prompt, so Grok seats
    (no env switch) match Opus seats. Seats write plain prose on both models,
    so a persona split comes from reasoning, not output style. *(My call.)*
  - Model ids come from the panel file; an id containing `fable` is rejected.
  - The runner depends on neither `~/.claude/debate-scripts` nor any plugin
    cache. Its first successful full dry run writes
    `~/.agent-shenanigans-probe/seat-dry-run.json`, the stamp that moves
    cc-debate to `absent`.
- **Prompt**: the runner appends one instruction asking the seat to end with a
  line that starts with the word VERDICT, a colon, and then APPROVED or
  REVISE. The instruction is phrased so it contains no line the parser would
  match.
- **Verdict parse**: strip leading `*`, `_`, backticks, `#`, and `>`; take the
  last line that
  begins with `VERDICT:` (case-insensitive) and whose first word after it is
  `APPROVED` or `REVISE`. Persona suffixes on that line parse. No such line
  counts as not returned. A seat whose process timed out counts only if that
  line is its last non-empty line.
- **Round rule**: a round is APPROVED only when every requested seat returned,
  every verdict is APPROVED, and the plan hash matches. The plan hash is the
  sha256 of the exact plan bytes sent to the seats, stored in the round's
  folder and compared with the plan file before the verdict is recorded. A
  persona whose two runs disagree therefore makes the round REVISE; the REVISE
  side's findings go into the revision. Missing seats are re-run once in the
  same round; if still missing, the round is REVISE with "N/<requested>
  returned".
- **Subsets** name whole personas, report N/<requested>, and never produce the
  final APPROVED.
- **Synthesis**: unanimous / unique / contradiction lists, plus a 7-row table:
  persona | Opus verdict | Grok verdict | agree/split. Contradictions go to a
  targeted exchange between the seats involved. The exchange only supplies
  text for the next revision; it never changes a seat's or the round's
  verdict.
- **Round discipline**: max 3 revision rounds, read every review in full. At
  the cap with any seat still REVISE, stop and report the open items. The
  owner may then sign off explicitly; that is recorded as `OWNER-ACCEPTED`
  with the open items listed, never as APPROVED, and lets step 3 proceed.
  There is no separate judge: the round rule is mechanical, so a judge could
  not change the verdict. *(My call.)*
- **Cost and time**: a full round is 14 xhigh reviews; wall clock is bounded by
  the slowest seat's timeout (Grok 1800 s). Three rounds is up to 42 reviews
  plus targeted exchanges.
- This replaces the four-persona Grok-only panel in `skills/debate/SKILL.md`,
  the acpx setup text, `skills/debate/SKILL.workflow.md`, and the Grok-only
  `debate-panel` skill.

### 7. Repo contents after the change

Keep (owner-authored): `skills/code-cleanup` (with the ported safety rules,
without `scripts/cc-fork`), `skills/check-in`, `skills/skill-postmortem`,
`skills/debate` (personas, panel file, seat runner, round rule), the entry
skill and its probe agent type, `workflows/CONTRACT.md` and its fixture, both
workflow scripts, `rules/modes.md`, `stack.toml`, `doctor`, `WORKFLOW.md`,
`README.md`, `AGENTS.md`, manifests.

Remove: `skills/compound`, `skills/session-learnings`, `commands/init.md`,
`skills/code-cleanup/scripts/cc-fork`, `skills/debate/SKILL.workflow.md`,
`grok/install.sh` (superseded by `doctor`), `debate-acpx.example.json`.
Uncommitted edits from 2026-10-19 to the removed files are discarded with
them; the rest of those edits (check-in Opus naming, superpowers attribution)
stay or are rewritten by this change.

Docs: `WORKFLOW.md` describes the loop above and says "run `./doctor`" as the
install step for both hosts. `README.md` credits upstream projects by link
only. `AGENTS.md` drops the "vendored" paragraph and the bundled-script
example that names `cc-fork`.

## Left to the builder (verify, then decide)

- Whether Grok loads `~/.claude/rules/*.md` (else `extra_rule_dirs`), and
  whether Grok workflow `agent()` and `spawn_subagent` agents receive it.
- Whether Workflow-tool agents trigger caveman's and ponytail's
  `SubagentStart` hooks, and the exact hook-only strings the spawn probe
  checks.
- How to give a Claude Workflow agent an empty or read-only tool set (a repo
  agent definition used through `agentType`), and the Grok capability mode
  with no tools.
- Which Grok setting keeps subagents on `grok-4.7` when `model` is passed, and
  whether `subagent_model_inheritance` rejects an explicit `model`.
- Where each host records the model and effort an agent actually ran on, and
  how to detect Grok's route.
- The Grok seat flags that remove write, shell, and MCP tools.
- Whether a `claude -p` flag keeps `~/.claude/CLAUDE.md` (Plamen's identity)
  out of Opus seats without dropping OAuth; if none, record that Opus seats
  carry it and Grok seats do not.
- How each host installs agent-shenanigans so the checkout is the source of
  truth (Grok: local path vs GitHub; Claude: local marketplace vs GitHub).
- Claude's resolution probe for a bare `/name`.
- Whether Haiku 5.5 accepts `xhigh`. If not, the low tier is Sonnet 5.5.
- Tier per code-cleanup mandate.
- `doctor` output format and flag names beyond `--fix`, `--rollback`,
  `--accept`.

## Open questions for the owner

- The other `~/cc-skills` links in `~/.claude/skills` — `recall`, `scan-diff`,
  `commit-and-verify`, `coderabbit-new`, `visual-css-refinement` — and Grok's
  real copies of the same names: keep as declared links, or drop?
- The other owner-looking entries in `~/.grok/skills` — `build-status`,
  `create-workflow`, `orchestrator-handoff`, `rate-limit-resume`, `safe-pause`
  — bring into the repo, leave unmanaged, or drop?
- `~/cc-skills/skills/debate/SKILL.md` is untracked in that clone, so it is
  not upstream and may be owner work: bring in, or drop?
- Parallel execution of independent tasks. Round 1 found it unsafe with the
  teeth step on one working tree, so both executors run one task at a time and
  log parallel-eligible tasks. The upgrade path is worktree isolation per task
  with a merge-then-gate step.

Until answered, the first three default to "unmanaged, left alone". The same
default covers `~/.claude/commands/check-pr-reviews.md` (into `~/cc-skills`)
and `~/.claude/skills/handoff` (into `~/Hypershield`).
