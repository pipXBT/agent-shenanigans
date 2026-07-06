---
name: code-cleanup
description: "Use when a codebase needs deep, systematic cleanup — after agent-heavy sessions, before a big refactor or review, or for periodic hygiene. Triggers: 'code cleanup', 'deep cleanup', 'clean up the codebase', 'remove dead code', 'tidy weak types / AI slop', '/code-cleanup'. Fans out concern-scoped subagents that inherit this session's recon; dry-run by default, isolated git worktrees in edit mode."
---

# Code Cleanup

Recon once in this session, then fan out to nine forked subagents that inherit the
conversation — each owns exactly one cleanup concern. Reconcile their reports.

> **Adapted from** Samuel Reed's ([STRML](https://github.com/STRML))
> [`cc-skills`](https://github.com/STRML/cc-skills) `code-cleanup` command and
> `cc-fork` tool (MIT). This fork revises the concern set, adds worktree-isolated edit
> mode, and folds in a scope-discipline guard (see `references/cleanup-rules.md`).
> `scripts/cc-fork` is vendored verbatim from upstream.

**Dependency:** `cc-fork` on PATH. It ships with this skill at `scripts/cc-fork`. Symlink
it once to a stable spot so it's on PATH for every run — the skill's own location differs
between a plugin install and a symlink install, so resolve it rather than assuming `$PWD`:
```bash
CC_FORK="$(find "$HOME/.claude/plugins" "$HOME/.claude/skills" -path '*code-cleanup/scripts/cc-fork' 2>/dev/null | head -1)"
[ -n "$CC_FORK" ] || CC_FORK="${CLAUDE_PLUGIN_ROOT}/skills/code-cleanup/scripts/cc-fork"
ln -s "$CC_FORK" ~/.local/bin/cc-fork
```
Or invoke it by that resolved path. If `cc-fork` is missing, use the Agent-tool fallback at the end.

## Phase 1 — Recon (this session)

Build understanding **in the conversation, not in a file**. Everything said or read
here is inherited by every fork — don't hoard it in `.tmp/`.

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
   (`*.pre-*`, `*.backup`), dynamic-dispatch sites — anything forks must not touch.

**Then load the scope-discipline guard.** Read `references/cleanup-rules.md` and state
it aloud in the conversation, and read `.agent/rules.md` at the project root if it
exists. These become part of the context every fork inherits — they're the "when to
stop / don't over-correct" rules the per-concern mandates don't carry on their own.
Project `.agent/rules.md` wins over the defaults on conflict.

Summarize all of the above aloud. This is now the shared context every fork will see.

## Phase 2 — Ask mode, then fan out

Ask the user:

- **Dry-run** (default) — forks produce evidence-backed reports only. Safe for fragile
  codebases or first use.
- **Edit mode** — forks apply high-confidence fixes **each in its own git worktree**,
  run typecheck/tests there, and commit to a per-concern branch. Phase 3 merges the
  branches with a real 3-way merge instead of racing on a shared tree.

Default to dry-run if unclear.

### Edit mode only: one isolated worktree + branch per fork

In edit mode each fork edits its **own** checkout, so deletes and refactors can't
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

In dry-run mode, skip the block above — every fork reads the shared tree read-only.

### Fan out

```bash
mkdir -p .tmp/code-cleanup/reports

# In edit mode, append to each task:  Your working tree is <WT[slug]>. cd into it; make
# ALL edits, typecheck, tests, and your final `git commit` there (use absolute paths or
# `git -C`). Never touch the main checkout. In dry-run, omit that line.
TASKS=(
  "MODE=<edit|dry-run>. Mandate: Deduplicate (logic only). Find repeated *behavioral* logic across what you've seen. Apply DRY only where it cuts real complexity — never abstraction for its own sake; leave three-line repetition alone. Duplicated *type* shapes belong to fork 02, not you. Write assessment, changes (or proposals in dry-run), items skipped with reasons, and follow-ups to your report. End with: WROTE_REPORT."
  "MODE=<edit|dry-run>. Mandate: Consolidate types. You own ALL duplicated type/interface/struct definitions across files and packages. Move shared shapes to one source of truth; update every import. Report format same as above."
  "MODE=<edit|dry-run>. Mandate: Dead code. Run the tools confirmed installed in recon. Remove unreferenced exports, files, and dependencies — but grep the FULL tree (tests, configs, dynamic imports, reflection, serialization, plugin registries) before cutting. Report format same as above."
  "MODE=<edit|dry-run>. Mandate: Circular dependencies. Run madge/pydeps/equivalent. Break every cycle by inverting a dependency or extracting the shared piece; do NOT mask with lazy imports. Report format same as above."
  "MODE=<edit|dry-run>. Mandate: Weak types. Find every any/unknown/object/{}/Python Any/Go interface{}/Rust Box<dyn Any> and suppression comment. Read call sites and upstream types; replace with real types. Typecheck must end green. Report format same as above."
  "MODE=<edit|dry-run>. Mandate: Dead-path removal. Remove deprecated code, compat shims, fallback branches, feature flags long since defaulted, '// TODO: remove after X' that outlived X, AND dead defensive cruft — empty catches, silent fallbacks, speculative guards. Keep try/catch that handles real external input, documented failure modes, or caller-uncrossable boundaries. Every path should be the single canonical path. Report format same as above."
  "MODE=<edit|dry-run>. Mandate: Mechanical autofix. Run the formatters/linters confirmed in recon in autofix-only mode (eslint --fix, ruff --fix / ruff format, prettier, gofmt, rustfmt, cargo fmt). NO semantic edits — formatting and safe lint autofixes only. In dry-run, report the file list and rule counts. In EDIT mode, DO NOT edit in your worktree — a repo-wide formatter conflicts with every other branch by construction; instead report exactly which command to run, and Phase 3 applies it LAST on the merged tree. Report format same as above."
  "MODE=<edit|dry-run>. Mandate: Test hygiene. Find disabled/zombie tests: .only/.skip/xit/fdescribe, commented-out assertions, orphaned snapshots, dead fixtures, tests skipped with no tracking reference. Re-enable, delete, or flag with evidence. Do not weaken or delete a FAILING test to go green. Report format same as above."
  "MODE=<edit|dry-run>. Mandate: AI slop. Remove narration comments, 'replaced old Y with new Z' notes, commented-out code, obvious-from-code comments, stub scaffolds. Keep comments that explain why, constraints, or non-obvious invariants — rewrite them for a new reader, no references to prior versions. Report format same as above."
)

# Single cc-fork call; it snapshots this session's JSONL into N forks that resume the
# full recon as inherited context, and staggers launches itself.
cc-fork --stagger 5 --output-dir .tmp/code-cleanup/reports "${TASKS[@]}"
```

Substitute `edit` or `dry-run` into each task before running, and (edit mode only)
append each fork's worktree path per the comment above. `--stagger` spreads cache
warm-up across launches; raise it if you hit rate limits. Wall-clock is dominated by
the slowest fork, not the stagger.

## Phase 3 — Reconcile

1. Read every `.tmp/code-cleanup/reports/fork-NN.out` in full — do not grep-skim.
2. Surface each fork's findings inline for the user.
3. **Dry-run:** synthesize high-confidence changes vs a medium/low follow-up checklist;
   stop here.
4. **Edit mode — merge the worktree branches** onto an integration branch one at a time,
   in roughly safest-first order (`types`, `weak-types`, `dedup`, `cycles`, `dead-code`,
   `dead-paths`, `test-hygiene`, `ai-slop`). Resolve each `git merge` conflict by hand,
   preferring the more conservative change. Then apply the **autofix** command LAST on
   the merged tree (formatters are global and must run after semantic edits).
5. Run the full typecheck and test suite once more on the integrated result.
6. Commit per concern: `cleanup(types): …`, `cleanup(dead-code): …`, etc.
7. List medium/low-confidence findings as a follow-up checklist.
8. Clean up: `git worktree remove` each worktree, delete the `cleanup/*` branches you
   merged, and `rm -rf .tmp/code-cleanup/`.

## Rules

- **Scope is the mandate.** Fork 1 doesn't fix types. Fork 5 doesn't remove dead code.
  The full guard is in `references/cleanup-rules.md`; the load-bearing ones:
- **Stop at the diagnosed smell.** Don't broaden the task; report further findings.
- **Reachability before deletion.** No delete without checking dynamic/reflected/
  serialized/plugin/test-only uses.
- **No new abstraction.** Removing dead layers is in scope; adding one is not.
- **Evidence before edits.** No grep/AST/tool output, no edit.
- **Prove every fix.** Typecheck and tests pass after each batch, or it reverts.

## Fallback: no cc-fork

If `cc-fork` isn't on PATH, use the Agent tool with a **byte-identical prefix** across
the nine parallel spawns. The prefix must inline the full recon, the scope rules, and
each mandate — Agent-tool forks don't see conversation history. Stagger spawn #1 until
streaming confirms cache commit, then launch 2–9 in one message. Inferior (each fork
re-reads ambient context) but works with zero install. Edit-mode worktree isolation
still applies — give each spawn its worktree path.
