---
name: code-cleanup
description: "Run a structured 9-fork parallel code cleanup (dry-run by default). Deep recon, then concern-scoped subagents for dedup, type consolidation, dead code, circular deps, weak types, dead-path removal, mechanical autofix, test hygiene, and AI slop. Each fork inherits a shared scope-discipline guard so it stops at its mandate instead of over-refactoring. Uses native spawn_subagent with monitoring; isolated git worktrees in edit mode. Triggers: 'run code cleanup', 'deep cleanup', '9-fork hygiene', '/code-cleanup'."
---

# Code Cleanup (Grok Native)

Deep recon, then fan out nine concern-scoped subagents via Grok's native toolset
(`spawn_subagent`, background tasks, monitoring). No `cc-fork` / Claude session dirs.

> **Adapted from** Samuel Reed's ([STRML](https://github.com/STRML))
> [`cc-skills`](https://github.com/STRML/cc-skills) `code-cleanup` command + `cc-fork`
> tool (MIT), ported to Grok's native `spawn_subagent` and monitoring primitives. This
> fork revises the concern set, adds worktree-isolated edit mode, and folds in the
> scope-discipline guard inlined below.

## Philosophy

- **Safety first.** Dry-run by default. Edit only when explicitly told `edit`.
- **Evidence-based.** Every finding backed by grep, AST, runtime checks, or call-site reading.
- **Mandate discipline.** Each fork owns exactly one dimension. No scope creep.
- **Landmine awareness.** Generated output, backups, vendored assets, one-off scripts are off-limits.
- **Reconciliation is mandatory.** Raw fork reports are not the final answer.

## When to Use

- After heavy parallel agent sessions (multiple waves of changes).
- When you suspect duplication, weak typing, dead defensive cruft, or AI narration comments.
- Periodic "spring cleaning" on mature codebases; before a big refactor or review.

Trigger phrases: "run code cleanup", "deep cleanup", "9-fork hygiene", `/code-cleanup`.

## Phase 1: Recon (always performed)

Build shared understanding by exploring:

1. Languages, package managers, workspace layout (pyproject.toml, package.json, …).
2. Build/test/lint commands and entry points.
3. Directory tree (respecting ignore patterns).
4. Public API and main modules.
5. Config surface (ruff, mypy, eslint, pytest, pre-commit, …).
6. Test layout and coverage approach.
7. Availability of static-analysis tools AND formatters/linters (note what's missing:
   vulture/pydeps/madge/knip + eslint/ruff/prettier/gofmt/rustfmt).
8. **Landmines** — generated dirs, vendored code, backups (`*.pre-*`, `*.backup`),
   historical artifacts, one-off scripts, dynamic-dispatch sites.

If `.agent/rules.md` (or `.grok/code-cleanup.md`) exists at the repo root, read it —
its rules/landmines/priorities are injected into every fork and **win over the defaults
below on conflict**.

All of this context — recon + the scope-discipline guard + project rules — is injected
into every fork.

## Scope-discipline guard (inject into every fork)

The per-concern mandates say *what* to clean; these say *how far* to go. A cleanup
agent's failure mode is **over-correction**. Every fork must obey:

1. **Clean within your mandate only.** Working code isn't automatically done, but only
   tidy what your mandate names. If cleanup spreads into unrelated areas, cut back to
   the smallest change that satisfies the mandate; report the rest as follow-ups.
2. **Separate structural from behavioral change.** Never disguise a feature, migration,
   or rewrite as cleanup. Preserve observable behavior. Never weaken or delete a
   *failing* test to go green.
3. **No speculative abstraction.** Removing a wrapper/interface/superclass with no real
   caller is in scope; adding one is not.
4. **Reachability before deletion.** Delete dead code only after checking reflected,
   serialized, generated, plugin-facing, dynamic, and test-only uses. Grep the full tree.
5. **Rule of Three.** Tolerate two duplicates; consolidate on the third unless the
   similarity is coincidental.
6. **Untested area = legacy.** No trustworthy test on the code you're changing →
   characterize it first or downgrade to a dry-run report. Don't rewrite blind.
7. **Evidence before edits.** No grep/AST/tool output → no edit.
8. **Prove every fix.** Typecheck and tests pass after each batch, or it reverts.

A fork is **done** when its mandated smell is gone in the files it owns and the next
change would be speculative, cross another fork's mandate, or alter behavior.

## Phase 2: Parallel fork execution (the 9 mandates)

Launch exactly these nine subagents with `spawn_subagent` (`background: true`):

| Fork | Mandate | Focus |
|------|---------|-------|
| 01 | Deduplicate (logic) | Repeated *behavioral* logic that adds real complexity. Type dedup → fork 02. |
| 02 | Consolidate types | ALL duplicated type/interface/struct definitions across modules. |
| 03 | Dead code | Unreferenced exports/functions/files (extreme care for dynamic usage). |
| 04 | Circular dependencies | Import cycles (AST graph when no pydeps/madge). |
| 05 | Weak types | `Any`, loose `object`, `interface{}`, suppressions — tighten with evidence. |
| 06 | Dead-path removal | Deprecated shims, defaulted flags, "remove after X" that outlived X, AND empty catches / silent fallbacks / speculative guards. Keep try/except handling real external input. |
| 07 | Mechanical autofix | Formatter + safe lint autofix only (ruff/eslint --fix, prettier, gofmt, rustfmt). No semantic edits. In edit mode this runs LAST on the merged tree, not in a parallel worktree (formatters are global). |
| 08 | Test hygiene | Disabled/zombie tests: `.only`/`.skip`/`xit`, commented assertions, orphaned snapshots, dead fixtures. Never delete a failing test to go green. |
| 09 | AI slop | Narration comments, "replaced X with Y", commented-out code, session artifacts. Keep why/constraint/invariant comments, rewritten clean. |

### Execution rules (hard requirements)

- Every fork receives the full recon + the scope-discipline guard + project rules + its
  exact mandate.
- All forks run `background: true`; stagger launches ~10–20s to avoid stampedes.
- Every fork writes `.tmp/code-cleanup/reports/fork-XX-<slug>.out` and ends with the
  line `WROTE_REPORT.`
- Dry-run is the default; edit mode must be explicitly passed and confirmed.
- Forks respect all landmines from recon.

### Edit mode: isolated git worktrees

Never run edit mode on a dirty working tree without explicit confirmation. For edit
runs, give each semantic fork (all except 07-autofix) its own worktree + branch so
parallel deletes can't collide:

```bash
BASE="$(git rev-parse HEAD)"
ROOT="$(git rev-parse --show-toplevel)"
for s in dedup types dead-code cycles weak-types dead-paths test-hygiene ai-slop; do
  git worktree add -b "cleanup/$s" "$ROOT/../$(basename "$ROOT")-cleanup-worktrees/$s" "$BASE"
done
```

Each fork makes ALL edits/tests/commits inside its assigned worktree (use absolute
paths or `git -C`), never the main checkout. Reconciliation merges the branches.

## Phase 3: Reconciliation

1. Read **every** report file in full (do not skim).
2. Surface overlapping findings; resolve conflicts conservatively.
3. Produce a synthesized summary: high-confidence changes, a medium/low checklist, and
   cross-cutting themes.
4. **Dry-run:** stop here.
5. **Edit mode:** merge each `cleanup/*` branch onto an integration branch one at a time
   (safest-first: types, weak-types, dedup, cycles, dead-code, dead-paths,
   test-hygiene, ai-slop), resolving conflicts by hand. Apply the **autofix** command
   LAST on the merged tree. Run full typecheck/tests. Commit per concern.
6. Clean up: `git worktree remove` each worktree, delete merged `cleanup/*` branches,
   and `.tmp/code-cleanup/` only after user approval.

## Tooling notes (Grok-specific)

- Primary mechanism: `spawn_subagent` (general-purpose) + `get_command_or_subagent_output`
  for monitoring.
- `run_terminal_command` with high timeouts for long analysis inside forks.
- When advanced static tools are missing, forks fall back to `grep` + custom Python AST
  scripts — expected and documented.
- `todo_write` is encouraged for the main agent during long reconciliation.

## Customization

Projects override behavior via `.agent/rules.md` (or `.grok/code-cleanup.md`) at the
repo root: read during recon and injected as project-specific rules/landmines/
priorities into every fork.
