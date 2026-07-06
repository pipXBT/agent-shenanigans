# Workflow consolidation — design spec

**Date:** 2026-07-06
**Status:** Approved (brainstorming complete; ready for implementation plan)
**Repo:** `agent-shenanigans`

## Overview

Make `agent-shenanigans` the single home and documented pipeline for the
non-superpowers workflow the author runs in Claude Code. Superpowers remains the
planning/execution engine (`/brainstorm`, writing-plans, subagent execution) and
is **out of scope**. This repo becomes the debate → execute → cleanup → codemaps →
capture loop that wraps it, plus the `WORKFLOW.md` a teammate reads to adopt the
whole loop.

## Goals

- One `git clone` + `./install.sh` (+ one `/plugin` command) gives a teammate the
  author's full non-superpowers surface.
- A `WORKFLOW.md` that documents the end-to-end pipeline as the shareable artifact.
- Bring the two Sam-authored skills and one command the author uses **verbatim**
  into the repo with correct attribution, so the repo is self-describing.

## Non-goals (YAGNI)

- No changes to the superpowers setup.
- Do **not** vendor `codemaps` (it is a maintained plugin with 11 language
  reference files — referenced, not copied).
- Do **not** vendor the four out-of-scope cc-skills utilities (`recall`,
  `scan-diff`, `commit-and-verify`, `coderabbit-new`) — a README "see also" points
  at their upstream.
- Do **not** develop `init` — vendor it verbatim.
- No push to GitHub as part of this work (author pushes when ready).

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | **Hybrid** — vendor small verbatim skills/command; reference the codemaps plugin | Matches the repo's existing fork-when-developed / reference-when-heavy philosophy |
| Scope | **Pipeline only** | Repo tells one clean workflow story; utilities stay upstream |
| `init` | **Vendor verbatim** (credited) | Author runs Sam's init unchanged today; no reason to fork yet |

## Workflow → source map (context)

| Step | Skill/cmd | Source today | Disposition |
|------|-----------|--------------|-------------|
| Plan | superpowers | Anthropic plugin | out of scope (stays) |
| Debate | `debate` | agent-shenanigans | keep (author's, developed) |
| Execute | `parallel-orchestrate` / Workflow | agent-shenanigans / built-in | keep / built-in |
| Cleanup | `code-cleanup` | agent-shenanigans | keep (author's, developed) |
| Codemaps | `update-codemaps` | `cc-codemaps` plugin (STRML) | **reference** |
| Postmortem | `skill-postmortem` | agent-shenanigans | keep |
| Learnings | `session-learnings` | `cc-skills` (STRML) | **vendor verbatim** |
| Compound | `compound` | `cc-skills` (STRML) | **vendor verbatim** |
| Bootstrap | `init` | `cc-skills` (STRML) | **vendor verbatim** (as a command) |
| Gate | `goal-check` | agent-shenanigans | keep |

## Final repo layout

```
agent-shenanigans/
├── WORKFLOW.md            ← NEW · centerpiece pipeline doc
├── README.md             ← updated
├── AGENTS.md (=CLAUDE.md)← updated (commands convention + pipeline pointer)
├── install.sh            ← extended: link commands/*.md → ~/.claude/commands/
├── LICENSE (MIT)
├── debate/  code-cleanup/  parallel-orchestrate/  skill-postmortem/  goal-check/   (author's)
├── session-learnings/SKILL.md   ← NEW vendored (STRML, MIT, credited)
├── compound/SKILL.md            ← NEW vendored (STRML, MIT, credited)
├── commands/
│   └── init.md                 ← NEW vendored (STRML, MIT, credited) — first command in repo
└── docs/superpowers/specs/2026-07-06-workflow-consolidation-design.md   ← this file
```

`codemaps` is referenced via: `/plugin marketplace add STRML/cc-codemaps` then
`/plugin install cc-codemaps@cc-codemaps`.

## Component specs

### C1 — Vendor `session-learnings` and `compound`

Each is a single `SKILL.md` upstream (no scripts/references). Copy each to
`<name>/SKILL.md`, then insert an attribution blockquote immediately after the
YAML frontmatter:

```markdown
> Vendored verbatim from Samuel Reed's ([STRML](https://github.com/STRML))
> [`cc-skills`](https://github.com/STRML/cc-skills) (MIT). Unmodified; upstream
> remains canonical.
```

Both are **Claude-only** (session-learnings hooks `/clear` + `PreCompact`;
compound writes Claude project memory) — no `SKILL.grok.md`.

### C2 — Vendor `init` as the repo's first command

Create top-level `commands/` and copy Sam's `init.md` to `commands/init.md`. Add
the same attribution as a comment/blockquote under the frontmatter. Command is
Claude-only.

### C3 — Extend `install.sh` for commands

- Add an `install_commands()` step: for each `commands/*.md`, symlink into
  `$CLAUDE_SKILLS_DIR`'s sibling `~/.claude/commands/<name>.md` (introduce
  `CLAUDE_COMMANDS_DIR="${CLAUDE_COMMANDS_DIR:-$HOME/.claude/commands}"`).
- Commands install under `--target claude` and `--target both`; skipped under
  `--target grok` (Grok handles commands differently).
- The existing skill-discovery loop already ignores `commands/` (no `SKILL.md`),
  so no regression. Reuse the existing `link()` helper (honors dry-run,
  don't-clobber-real-files, confirm-relink).
- Preserve `--dry-run`, `--help` (the help sed range may need widening if header
  comments grow), and named-target filtering.

### C4 — `WORKFLOW.md` (new)

Sections:
1. **Thesis** — superpowers for thinking; this repo for the pipeline around it.
2. **The pipeline**, in order, each step naming its skill + when to fire:
   `/init` → superpowers `/brainstorm` + writing-plans → `/debate:all` on the
   plan/bug → execute (superpowers subagents / ultracode Workflow /
   `parallel-orchestrate` for branch-per-feature fanout) → `/code-cleanup` →
   `/update-codemaps` → capture (`skill-postmortem` / `session-learnings` /
   `compound`); `goal-check` as the completion gate.
3. **Mine vs borrowed** table.
4. **Install summary** — clone + `./install.sh` + the two `/plugin` commands.

### C5 — README + AGENTS.md updates

- README: add `session-learnings` and `compound` rows to the skills table
  (marked vendored / Claude-only); add a short **Commands** subsection for
  `/init`; add a **Referenced plugins** note for codemaps with the install
  commands; add a **See also** line → `STRML/cc-skills` for the out-of-scope
  utilities; link `WORKFLOW.md` near the top; extend the **Credits** section to
  list the three vendored pieces + the referenced plugin.
- AGENTS.md: document the `commands/` directory convention (Claude-only, linked
  by `install.sh`) and add a one-line pointer to `WORKFLOW.md`.

## Local migration note (author only)

Re-running `install.sh` will offer to repoint the author's existing
`session-learnings` / `compound` / `init` symlinks from `~/cc-skills` →
`agent-shenanigans` (the `link()` helper prompts before relinking a symlink that
points elsewhere). One confirm migrates the daily setup to the consolidated repo.
Fresh teammate clones hit no conflict.

## Acceptance criteria

- `./install.sh --dry-run` shows: 7 skills linked (5 author + 2 vendored) and
  1 command (`init`) linked; `--target grok` shows the 2 vendored skills via
  compatibility note and **no** command link.
- Vendored files are byte-identical to upstream except the added attribution
  block; each carries the STRML/MIT credit.
- `WORKFLOW.md` names every pipeline step and the exact skill/command/plugin for
  each, and the two `/plugin` commands for codemaps.
- README skills table row count matches the installed skill count; no secrets or
  personal paths introduced.
- Nothing pushed to GitHub.
