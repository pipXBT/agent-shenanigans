---
name: code-cleanup
description: "Use when a codebase needs deep, systematic cleanup — after agent-heavy sessions, before a big refactor or review, or for periodic hygiene. Triggers: 'code cleanup', 'deep cleanup', 'clean up the codebase', 'remove dead code', 'tidy weak types / AI slop', '/code-cleanup'. Fans out nine concern-scoped subagents, each on a fixed model tier and briefed with the recon; dry-run by default, isolated git worktrees in edit mode."
---

# Code Cleanup

Recon once in this session, then spawn nine fresh agents. Each owns one cleanup concern,
gets a written brief, and runs on a fixed model at `xhigh`. Reconcile their reports. See
**Host** for how each host spawns them.

> **Adapted from** Samuel Reed's ([STRML](https://github.com/STRML))
> [`cc-skills`](https://github.com/STRML/cc-skills) `code-cleanup` command (MIT). This
> version revises the concern set, adds worktree-isolated edit mode, folds in a
> scope-discipline guard (see `references/cleanup-rules.md`), and carries the owner's
> safety rules for repos with vendored or pinned trees. It spawns tiered agents with a
> written brief instead of forking this chat.

> **A repo may override this file.** If `.claude/commands/code-cleanup.md` exists in the
> project, it wins. Read it and follow it instead. Repos with frozen vendored trees or
> hash-pinned artefacts should have one.

## Hard exclusions

Nine mandates that say *delete unreferenced code* and *remove narration comments* are
dangerous in any repo that vendors third-party source or keeps a deliberate record of past
mistakes. **"Unreferenced" is not the same as "unused"**: a pristine diff target, a
provenance copy, or the source a build artefact was generated from is imported by nothing
and load-bearing anyway.

No agent may create, modify, move or delete anything under:

```
vendor/ third_party/ external/ lib/ (submodules)   any tracked upstream copy
node_modules/ target/ build/ dist/ .venv/          build output
**_pb2.py **.pb.go **/generated/**                 generated code (match at any depth)
any file a manifest, lockfile or checksum pins     regenerating it to pass is forbidden
```

Establish the real list in Phase 1 step 8 and **write it into every agent's brief
verbatim**. A fresh agent has seen nothing, so the brief is the only constraint it has.

If the repo declares its own invariants (a `CLAUDE.md`, an `AGENTS.md`, a
`scripts/verify-*.sh`, a required CI check), those bind every agent and are named
explicitly in each mandate.

## Modes

Paste this block at the top of every agent brief. An agent does not inherit a slash-command mode.

```
Follow the caveman skill at ultracave and the ponytail skill at full.
If the user invoked ponytail ultra, use ultra instead of full.
Caveman ultracave: fragments, one word when one word is enough, each fact once. Keep not, never, no, only, and except. Do not invent abbreviations. Do not use arrows.
Ponytail full: smallest change that finishes the mandate. No extra options, wrappers, or abstractions. Deletion beats addition. End with what you skipped and the risk.
Ponytail ultra also questions any part the mandate does not justify, and does not do that part.
Code, comments, and commit messages stay normal English.
Effort xhigh. Do not lower effort. Never use Fable.
```

## Host

Same recon, same nine mandates, same worktrees, same reconcile. Every brief starts with **Modes**.

**Tiers.** The model is fixed per mandate. Mechanical work goes to Haiku, local judgment to
Sonnet, the one design-heavy mandate to Opus.

| Slug | Concern | Claude model |
|------|---------|--------------|
| `dedup` | Deduplicate logic | `claude-sonnet-5-5` |
| `types` | Consolidate types | `claude-sonnet-5-5` |
| `dead-code` | Dead code | `claude-sonnet-5-5` |
| `cycles` | Circular dependencies | `claude-opus-5-5` |
| `weak-types` | Weak types | `claude-sonnet-5-5` |
| `dead-paths` | Dead-path removal | `claude-sonnet-5-5` |
| `autofix` | Mechanical autofix | `claude-haiku-5-5` |
| `test-hygiene` | Test hygiene | `claude-sonnet-5-5` |
| `ai-slop` | AI slop | `claude-haiku-5-5` |

- **Claude Code.** One Workflow `agent()` per mandate, each with the tier model above and
  `effort: "xhigh"`. No agent inherits the session model. The brief carries the full recon and
  exclusion list, because `agent()` does not see this chat. Do not pass `isolation: "worktree"`:
  edit mode creates its own worktrees in Phase 2. Pass the shared brief and the nine tasks as
  `args`:

  ```js
  export const meta = { name: 'code-cleanup', description: 'One tiered agent per cleanup mandate' }
  const { prefix, tasks } = args   // prefix: Modes + exclusions + recon + rules; tasks: [{slug, model, task}]
  return await parallel(tasks.map(t => () =>
    agent(`${prefix}\n\n${t.task}`, { label: t.slug, model: t.model, effort: "xhigh" })))
  ```

  A `null` result means that agent died: rerun that mandate alone. If a spawn rejects `xhigh` on
  `claude-haiku-5-5`, run `autofix` and `ai-slop` on `claude-sonnet-5-5` and say so in the summary.
- **Grok Build.** Launch the nine mandates with `spawn_subagent` (`background: true`, omit
  `subagent_type`) in one turn, passing `model: "grok-4.7"` when the tool accepts it. The Claude
  tiers do not apply: every mandate runs on `grok-4.7`. Not yet checked: whether `spawn_subagent`
  has a `model` field. Read its schema in a Grok session before the first run. If it has none, the
  agent runs on the session model, so confirm the session is on `grok-4.7` at `xhigh` before
  spawning. Stagger if you hit a rate limit. Collect with `get_command_or_subagent_output`.

Each agent writes `<REPORTS>/<slug>.out` and ends with `WROTE_REPORT`. `<REPORTS>` is the
absolute path of `.tmp/code-cleanup/reports` in the main checkout.

## Phase 1 — Recon (this session)

Build understanding in the conversation, then write it out as one recon block. That block, not
the chat, is what every agent gets. Don't hoard it in `.tmp/`.

Work through:

1. **Languages and package managers.** Read every root manifest. Note workspace layout.
2. **Build / typecheck / test / lint commands.** From manifests + any `Makefile` /
   `justfile` / `turbo.json` / `nx.json`.
3. **Tree.** `tree -L 3 -I 'node_modules|dist|build|target|.venv|__pycache__'` at root;
   per-package in a monorepo.
4. **Entry points and public API.** `main`, `exports`, `bin`, `[[bin]]`, `[lib]`,
   framework conventions.
5. **Config surface.** tsconfig, ESLint, `ruff.toml`, `clippy.toml`, `.editorconfig`.
6. **Test layout.** Where tests live, the runner, coverage tool.
7. **Tool availability.** Verify which are installed and actually run: `knip`,
   `ts-prune`, `madge`, `vulture`, `deadcode`, `cargo machete`, `cargo udeps`,
   `pydeps`, `depcheck`, plus formatters/linters (`eslint`, `ruff`, `prettier`,
   `gofmt`, `rustfmt`). Note which work.
8. **Landmines.** Generated code, vendored code, protobuf output, backup files
   (`*.pre-*`, `*.backup`), dynamic-dispatch sites — anything agents must not touch.
   Produce a concrete **path list**, not a description; you will paste it into every
   mandate. Check `.gitmodules`, any checksum manifest, and every `.gitignore`.
9. **Pre-flight.** Confirm the tree is clean and the repo's own guards (its verify scripts,
   typecheck, tests) are green *before* any agent runs. A cleanup that starts dirty cannot
   attribute damage. Never start on the default branch; switch to a working branch first.

**Then load the scope-discipline guard.** Read `references/cleanup-rules.md`, and read
`.agent/rules.md` at the project root if it exists. Both go into the shared brief in full.
They're the "when to stop / don't over-correct" rules the per-concern mandates don't carry on
their own. Project `.agent/rules.md` wins over the defaults on conflict.

Assemble the brief prefix: **Modes**, then the exclusion path list, then the recon block, then
the rules. Inherited context is not a constraint, so nothing is left to be "seen".

## Phase 2 — Ask mode, then spawn

Ask the user:

- **Dry-run** (default) — agents produce evidence-backed reports only. Safe for fragile
  codebases or first use.
- **Edit mode** — agents apply high-confidence fixes **each in its own git worktree**,
  run typecheck/tests there, and commit to a per-concern branch. Phase 3 merges the
  branches with a real 3-way merge instead of racing on a shared tree.

Default to dry-run if unclear.

### Edit mode only: one isolated worktree + branch per agent

In edit mode each agent edits its **own** checkout, so deletes and refactors can't
collide mid-flight; git surfaces genuine conflicts at merge time. First guard the tree,
then create the worktrees:

```bash
# Refuse to run edit mode on a dirty tree without explicit confirmation.
[ -z "$(git status --porcelain)" ] || { echo "Working tree is dirty — confirm before edit mode."; }

BASE="$(git rev-parse HEAD)"
WT_ROOT="$(git rev-parse --show-toplevel)/../$(basename "$(git rev-parse --show-toplevel)")-cleanup-worktrees"
SLUGS=(dedup types dead-code cycles weak-types dead-paths autofix test-hygiene ai-slop)
declare -A WT
for s in "${SLUGS[@]}"; do
  WT[$s]="$WT_ROOT/$s"
  git worktree add -b "cleanup/$s" "${WT[$s]}" "$BASE"
done
```

In dry-run mode, skip the block above — every agent reads the shared tree read-only.

### The nine tasks

```bash
mkdir -p .tmp/code-cleanup/reports
```

Each task is `MODE=<edit|dry-run>.`, then the mandate text below, then the report line:
"Write assessment, changes (or proposals in dry-run), items skipped with reasons, and
follow-ups to `<REPORTS>/<slug>.out`. End with: WROTE_REPORT." In edit mode, also append: "Your
working tree is `<WT[slug]>`. cd into it; make ALL edits, typecheck, tests, and your final
`git commit` there (use absolute paths or `git -C`). Never touch the main checkout." In
dry-run, omit that line. Substitute `edit` or `dry-run` into each task before spawning.

- `dedup` — "Mandate: Deduplicate (logic only). Find repeated *behavioral* logic across what you've seen. Apply DRY only where it cuts real complexity — never abstraction for its own sake; leave three-line repetition alone. Duplicated *type* shapes belong to the `types` mandate, not you."
- `types` — "Mandate: Consolidate types. You own ALL duplicated type/interface/struct definitions across files and packages. Move shared shapes to one source of truth; update every import."
- `dead-code` — "Mandate: Dead code. Run the tools confirmed installed in recon. Remove unreferenced exports, files, and dependencies — but grep the FULL tree (tests, configs, dynamic imports, reflection, serialization, plugin registries) before cutting."
- `cycles` — "Mandate: Circular dependencies. Run madge/pydeps/equivalent. Break every cycle by inverting a dependency or extracting the shared piece; do NOT mask with lazy imports."
- `weak-types` — "Mandate: Weak types. Find every any/unknown/object/{}/Python Any/Go interface{}/Rust Box<dyn Any> and suppression comment. Read call sites and upstream types; replace with real types. Typecheck must end green."
- `dead-paths` — "Mandate: Dead-path removal. Remove deprecated code, compat shims, fallback branches, feature flags long since defaulted, '// TODO: remove after X' that outlived X, AND dead defensive cruft — empty catches, silent fallbacks, speculative guards. Keep try/catch that handles real external input, documented failure modes, or caller-uncrossable boundaries. Every path should be the single canonical path."
- `autofix` — "Mandate: Mechanical autofix. Run the formatters/linters confirmed in recon in autofix-only mode (eslint --fix, ruff --fix / ruff format, prettier, gofmt, rustfmt, cargo fmt) and never over an excluded path. NO semantic edits — formatting and safe lint autofixes only. In dry-run, report the file list and rule counts. In EDIT mode, DO NOT edit in your worktree — a repo-wide formatter conflicts with every other branch by construction; instead report exactly which command to run, and Phase 3 applies it LAST on the merged tree."
- `test-hygiene` — "Mandate: Test hygiene. Find disabled/zombie tests: .only/.skip/xit/fdescribe, commented-out assertions, orphaned snapshots, dead fixtures, tests skipped with no tracking reference. Re-enable, delete, or flag with evidence. Do not weaken or delete a FAILING test to go green."
- `ai-slop` — "Mandate: AI slop. Remove narration comments, 'replaced old Y with new Z' notes, commented-out code, obvious-from-code comments, stub scaffolds. Keep comments that explain why, constraints, or non-obvious invariants — rewrite them for a new reader, no references to prior versions."

Where the repo keeps a deliberate record of corrections — rows saying a previous reading was
wrong, `was:` statuses, superseded notes — tell the `ai-slop` agent to keep them. They read
exactly like the narration it is sent to remove, and they are usually the most expensive thing
in the tree to reconstruct.

## Phase 3 — Reconcile

1. Read every `<REPORTS>/<slug>.out` in full — do not grep-skim.
2. Surface each agent's findings inline for the user.
3. **Dry-run:** synthesize high-confidence changes vs a medium/low follow-up checklist;
   stop here.
4. **Edit mode — merge the worktree branches** onto an integration branch one at a time,
   in roughly safest-first order (`types`, `weak-types`, `dedup`, `cycles`, `dead-code`,
   `dead-paths`, `test-hygiene`, `ai-slop`). Resolve each `git merge` conflict by hand,
   preferring the more conservative change. Then apply the **autofix** command LAST on
   the merged tree (formatters are global and must run after semantic edits).
5. Run the full typecheck and test suite once more on the integrated result, **plus the
   repo's own invariant or verification scripts**, reading exit codes rather than output.
   A cleanup that passes the tests and breaks a pinned tree is the failure mode this step
   exists for. Then confirm nothing excluded moved:

   ```bash
   git status --short <every excluded path>          # must print nothing
   git diff --stat "$BASE" -- <every excluded path>  # edit mode: must print nothing
   git submodule status --recursive | grep -E '^[+-]' || echo "submodules pinned"
   ```
6. Commit per concern: `cleanup(types): …`, `cleanup(dead-code): …`, etc.
7. List medium/low-confidence findings as a follow-up checklist.
8. Clean up: `git worktree remove` each worktree, delete the `cleanup/*` branches you
   merged, and `rm -rf .tmp/code-cleanup/`.

## Rules

- **Scope is the mandate.** The `dedup` agent doesn't fix types. The `weak-types` agent doesn't
  remove dead code. The full guard is in `references/cleanup-rules.md`; the load-bearing ones:
- **Stop at the diagnosed smell.** Don't broaden the task; report further findings.
- **Reachability before deletion.** No delete without checking dynamic/reflected/
  serialized/plugin/test-only uses.
- **No new abstraction.** Removing dead layers is in scope; adding one is not.
- **Evidence before edits.** No grep/AST/tool output, no edit.
- **Prove every fix.** Typecheck and tests pass after each batch, or it reverts.
- **The boundary outranks the mandate.** If an agent's mandate implies touching an excluded path, the mandate is wrong for that file. Report it; do not resolve it.
- **Never weaken a guard to make a check pass** — not a lint config, not a test, not a checksum manifest. A truthful red beats a false green.
- **Recovery is not a judgement call.** If a boundary was crossed, restore the paths from `HEAD` (`git restore --staged --worktree -- <paths>`; for submodules `git submodule foreach --recursive 'git restore --staged --worktree .'`), or in edit mode drop that branch's changes to them before merging. Re-run the guards, and record which mandate's wording caused it.
