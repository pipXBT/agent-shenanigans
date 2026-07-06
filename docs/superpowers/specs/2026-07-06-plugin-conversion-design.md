# Plugin conversion — design spec

**Date:** 2026-07-06
**Status:** Approved (brainstorming complete)
**Repo:** `agent-shenanigans`

## Overview

Convert `agent-shenanigans` from a symlink-installed skills repo into a **Claude
Code plugin**, installable via `/plugin`. Success criterion (user's words): *a
teammate can install the plugin and replicate the workflow.* Claude-only — the
multi-CLI (Grok Build) symlink path is dropped.

## Goals

- `/plugin marketplace add pipXBT/agent-shenanigans` + `/plugin install
  agent-shenanigans@agent-shenanigans` loads all 7 skills + the `/init` command.
- The bundled scripts (`spawn-parallel.py`, `cc-fork`) resolve correctly when the
  skill lives in the plugin cache, so `parallel-orchestrate` and `code-cleanup`
  actually run for a fresh installer.
- `WORKFLOW.md` + README document the plugin-install flow (this plugin +
  referenced `cc-codemaps` and `cc-debate` plugins).

## Non-goals (YAGNI)

- No change to any skill's analysis/behavior (only path plumbing + relocation).
- No multi-CLI install (Grok/OpenAI). `SKILL.grok.md` files are kept dormant.
- codemaps + cc-debate stay **referenced** plugins (not bundled).
- Do not rewrite the historical `parallel-orchestrate/docs/*` design docs (their
  hardcoded paths are historical record, not runtime).

## Decisions

| Decision | Choice |
|----------|--------|
| Distribution | Claude Code plugin only |
| `install.sh` | **Removed** (plugin replaces it) |
| `SKILL.grok.md` files | **Kept, dormant** (preserved; nothing wires them up) |
| Plugin + marketplace name | `agent-shenanigans` → `/plugin install agent-shenanigans@agent-shenanigans` |
| Version | `0.1.0` |
| Bundled-script paths | `${CLAUDE_PLUGIN_ROOT}` with a `~/.claude/skills/...` fallback |

## Target structure

```
agent-shenanigans/
├── .claude-plugin/
│   ├── plugin.json          NEW
│   └── marketplace.json     NEW
├── skills/                  NEW — git-mv the 7 skill dirs in here
│   ├── debate/  code-cleanup/  parallel-orchestrate/  skill-postmortem/
│   ├── goal-check/  session-learnings/  compound/
├── commands/init.md         (unchanged location)
├── WORKFLOW.md  README.md  AGENTS.md  LICENSE  docs/
└── install.sh               DELETED
```

## Component specs

### C1 — Manifests

`.claude-plugin/plugin.json`:
```json
{
  "name": "agent-shenanigans",
  "version": "0.1.0",
  "description": "A personal Claude Code workflow: debate, parallel-orchestrate, code-cleanup, skill-postmortem, goal-check, plus vendored session-learnings/compound and an /init command.",
  "author": { "name": "pipXBT", "url": "https://github.com/pipXBT" },
  "homepage": "https://github.com/pipXBT/agent-shenanigans",
  "repository": "https://github.com/pipXBT/agent-shenanigans",
  "license": "MIT",
  "keywords": ["workflow", "debate", "code-cleanup", "orchestration", "skills"]
}
```
`.claude-plugin/marketplace.json`:
```json
{
  "name": "agent-shenanigans",
  "description": "pipXBT's personal Claude Code workflow — debate, orchestrate, clean, capture.",
  "owner": { "name": "pipXBT", "url": "https://github.com/pipXBT" },
  "plugins": [
    { "name": "agent-shenanigans", "source": "./", "version": "0.1.0",
      "description": "Debate, parallel-orchestrate, code-cleanup, skill-postmortem, goal-check, session-learnings, compound + /init.",
      "author": { "name": "pipXBT" } }
  ]
}
```

### C2 — Relocate skills

`git mv <name> skills/<name>` for all 7 (debate, code-cleanup, parallel-orchestrate,
skill-postmortem, goal-check, session-learnings, compound). `git mv` preserves the
`SKILL.md`, `SKILL.grok.md`, `references/`, `scripts/`, `tests/`, and vendored
attribution intact.

### C3 — Plugin-portable script paths (the correctness fix)

**parallel-orchestrate/SKILL.md** — 5 hardcoded `~/.claude/skills/parallel-orchestrate/scripts/spawn-parallel.py`.
Add a one-time resolution near the top of the fanout section and use the variable
thereafter:
```bash
# Resolve the bundled spawn script whether installed as a plugin or a symlink:
PO_DIR="${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/parallel-orchestrate}"
PO_DIR="${PO_DIR:-$HOME/.claude/skills/parallel-orchestrate}"
PO_SCRIPT="$PO_DIR/scripts/spawn-parallel.py"
# Fallback if neither resolves (plugin cache path unknown):
[ -f "$PO_SCRIPT" ] || PO_SCRIPT="$(find "$HOME/.claude/plugins" -path '*parallel-orchestrate/scripts/spawn-parallel.py' 2>/dev/null | head -1)"
```
Replace each `python3 ~/.claude/skills/.../spawn-parallel.py` with `python3 "$PO_SCRIPT"`.

**code-cleanup/SKILL.md** — the `cc-fork` dependency note currently says it ships at
`scripts/cc-fork` and to symlink `"$PWD/scripts/cc-fork"`. Update the symlink source
to the plugin-aware path: `${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/skills/code-cleanup}/scripts/cc-fork`
(the Agent-tool fallback already covers the no-`cc-fork` case).

### C4 — Remove `install.sh`

`git rm install.sh`. All installer logic is superseded by `/plugin`.

### C5 — Doc rewrites

- **README** — replace `## Install`, `## Updating`, `## Removing a skill`,
  `## Two CLIs, one repo`, and the manual-symlink block with a single **Install
  (plugin)** section: the two `/plugin` commands + restart. Keep the skills table,
  Commands, Referenced plugins, See also, Credits. Update the top blurb (drop
  "and Grok Build").
- **WORKFLOW.md** — replace the `git clone + ./install.sh` install step with the
  three `/plugin` installs (agent-shenanigans, cc-codemaps, cc-debate).
- **AGENTS.md** — replace the two-CLI/symlink model + `install.sh` references with
  the plugin layout (`.claude-plugin/`, `skills/`, `commands/`); note
  `${CLAUDE_PLUGIN_ROOT}` for bundled scripts; keep the vendored-attribution rule.

### C6 — Local migration (author's machine)

Remove the now-stale/superseded symlinks (all superseded by the plugin), then
install the plugin:
- `~/.claude/skills/{debate,code-cleanup,goal-check,parallel-orchestrate,skill-postmortem}`
  (point at old top-level dirs — dangle after the move)
- `~/.claude/skills/{session-learnings,compound}` (point at `~/cc-skills` — now
  provided by the plugin; would duplicate)
- `~/.claude/commands/init.md` (points at `~/cc-skills` — now provided by the plugin)

Only remove symlinks resolving into `agent-shenanigans` **or** into the three
plugin-superseded cc-skills targets; leave all other symlinks (Hypershield,
plamen, other cc-skills) untouched.

## Rollout order

1. Convert (manifests, `git mv`, path fixes, remove install.sh, docs) on a branch.
2. Merge to `main` and **push** (a plugin must be on GitHub for `/plugin marketplace add pipXBT/...`).
3. Remove the superseded local symlinks (C6).
4. `/plugin marketplace add pipXBT/agent-shenanigans` + `/plugin install …`, restart.

## Acceptance criteria

- `.claude-plugin/plugin.json` + `marketplace.json` are valid JSON; `marketplace.json`
  lists one plugin, `source: "./"`.
- `skills/` contains all 7 skill dirs, each with its `SKILL.md`; `commands/init.md`
  present; no skill dirs remain at repo root; `install.sh` gone.
- `parallel-orchestrate/SKILL.md` contains no bare `~/.claude/skills/...python`
  invocation — all go through `$PO_SCRIPT`.
- README/WORKFLOW/AGENTS contain no `./install.sh` install instruction; the two
  `/plugin` commands for this plugin are present.
- Vendored attribution headers still present in `skills/session-learnings`,
  `skills/compound`, `commands/init.md`.
