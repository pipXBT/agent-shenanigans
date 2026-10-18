# agent-shenanigans — guide for AI agents

This repository is a **Claude Code plugin**: a bundle of skills, one slash-command,
and the manifests that make it installable via `/plugin`. If you are an AI agent
working *in this repo*, read this first. (This file follows the `AGENTS.md`
convention; `CLAUDE.md` is symlinked to it.)

## Layout

```
.claude-plugin/     plugin.json + marketplace.json (plugin + marketplace manifests)
skills/<name>/      one skill each: SKILL.md (+ optional references/, scripts/)
commands/<name>.md  Claude slash-commands (e.g. /init)
grok/workflows/     Grok Build workflows (*.rhai). Not loaded by the Claude plugin.
grok/install.sh     symlinks grok/workflows/*.rhai into ~/.grok/workflows/
WORKFLOW.md         the end-to-end pipeline these compose into
```

Claude Code discovers skills under `skills/` and commands under `commands/`
automatically from the plugin — no per-skill registration. The manifests declare the
plugin (`.claude-plugin/plugin.json`) and expose it as a one-plugin marketplace
(`.claude-plugin/marketplace.json`, `source: "./"`) so
`/plugin marketplace add pipXBT/agent-shenanigans` works.

A few skills/commands are **vendored verbatim** from
[STRML/cc-skills](https://github.com/STRML/cc-skills) with an attribution header
(`session-learnings`, `compound`, `/init`).

## Bundled scripts (important)

A skill that ships an executable (e.g. `parallel-orchestrate/scripts/spawn-parallel.py`,
`code-cleanup/scripts/cc-fork`) must **not** hard-code `~/.claude/skills/<name>/...` —
that path is wrong once the skill lives in the plugin cache. Resolve the script at
runtime instead: prefer `${CLAUDE_PLUGIN_ROOT}/skills/<name>/scripts/...`, and fall
back to discovery:
```bash
find "$HOME/.claude/plugins" "$HOME/.claude/skills" -path '*<name>/scripts/<file>' 2>/dev/null | head -1
```
See `skills/parallel-orchestrate/SKILL.md` Preflight for the canonical pattern.

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

## Adding a command

Slash commands go in `commands/<name>.md` (a markdown file with a `description` in
frontmatter). They load from the plugin automatically. A vendored command carries the
same attribution header as a vendored skill.

## Conventions

- Don't relabel third-party work as your own. Skills adapted from someone else's plugin
  must credit the source (see `skills/debate/` → STRML's `cc-debate`).
- Never commit secrets. Config examples ship as `*.example.json` with prompts and agent
  names only — no API keys or tokens.
- Keep each skill self-contained and single-purpose; if a `SKILL.md` is doing two jobs,
  split it.
- Dormant `SKILL.grok.md` files remain from the dual-CLI era; the plugin ignores them.
