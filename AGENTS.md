# agent-shenanigans — guide for AI agents

This repository is the control copy of one workflow that runs on Claude Code or Grok Build.
It is a **Claude Code plugin** (skills, agents, manifests) plus the files that keep both
hosts configured the same way. Grok Build loads the same `skills/<name>/SKILL.md` from its
plugin cache. If you are an AI agent working *in this repo*, read this first. (This file follows the `AGENTS.md`
convention; `CLAUDE.md` is symlinked to it.)

## Layout

```
.claude-plugin/     plugin.json + marketplace.json (plugin + marketplace manifests)
skills/<name>/      one skill each: SKILL.md (+ optional references/, scripts/)
agents/             agent types the workflow spawns (probe: no tools; reader: read-only)
workflows/          the adversarial-verification executors (.js for Claude, .rhai for Grok),
                    CONTRACT.md they both implement, and the shared fixture cases
rules/              modes.md, linked to ~/.claude/rules/ by doctor; carries the modes marker
lib/doctor/         the code behind ./doctor (Python standard library only)
doctor              the drift checker and fixer; reads stack.toml
stack.toml          every plugin, link, and setting each host must have
verified.json       plugin SHAs last verified, written by ./doctor --accept (absent until then)
tests/              unittest (Python) and node:test (workflows) suites
WORKFLOW.md         the end-to-end loop and the install steps
```

Claude Code discovers skills under `skills/` and agents under `agents/` automatically from
the plugin — no per-skill registration. The `.rhai` workflow is not loaded by the plugin;
`doctor` links it into Grok's workflows folder. The manifests declare the
plugin (`.claude-plugin/plugin.json`) and expose it as a one-plugin marketplace
(`.claude-plugin/marketplace.json`, `source: "./"`) so
`/plugin marketplace add pipXBT/agent-shenanigans` works.

Everything in this repo is owner-authored. Upstream plugins (superpowers, caveman, ponytail,
cc-codemaps) are installed as-is and declared in `stack.toml`, never copied here. Run
`./doctor` to check a machine against it.

## Bundled scripts (important)

A skill that ships an executable (today `debate/scripts/run_seats.py`) must **not**
hard-code `~/.claude/skills/<name>/...` — that path is wrong once the skill lives in
the plugin cache. Resolve the script at runtime instead: prefer
`${CLAUDE_PLUGIN_ROOT}/skills/<name>/scripts/...`, and fall back to discovery:
```bash
find "$HOME/.claude/plugins" "$HOME/.claude/skills" -path '*<name>/scripts/<file>' 2>/dev/null | head -1
```
See the commands in `skills/debate/SKILL.md` for the pattern.

## Adding or editing a skill

1. Create `skills/<name>/SKILL.md` with frontmatter:
   ```markdown
   ---
   name: my-skill
   description: "Use when ... [trigger phrases]. [What it does, one sentence.]"
   ---
   ```
   The `description` is the trigger surface — pack it with concrete trigger phrases and
   a clear use-case statement.
2. Put executable helpers in `skills/<name>/scripts/` (reference them plugin-relatively —
   see "Bundled scripts"), load-on-demand docs in `skills/<name>/references/`.
3. Add a row to the skills table in `README.md`.
4. Bump `version` in both manifests when cutting a release.

## Conventions

- Don't relabel third-party work as your own. Skills adapted from someone else's plugin
  must credit the source and name what changed (see `skills/debate/` → STRML's `cc-debate`).
  A verbatim copy of upstream work does not belong here.
- Never commit secrets. No API keys or tokens in any config or example.
- Keep each skill self-contained and single-purpose; if a `SKILL.md` is doing two jobs,
  split it.
- One `SKILL.md` per skill for both hosts. Put host differences in a Host section in that file. Do not add `SKILL.grok.md`.
