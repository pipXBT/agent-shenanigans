# My Claude Code workflow

This is how I run any non-trivial change in Claude Code, end to end. The idea in
one line: **[superpowers](https://github.com/anthropics/claude-code) does the
thinking — brainstorm, plan, execute — and the skills in this repo wrap that core
in a `debate → build → clean → map → capture` loop.** Everything here installs as one
Claude Code plugin (plus two referenced plugins — codemaps and the debate backend).

If you only read one thing, read the pipeline table.

## The pipeline

| # | Stage | Invoke | When |
|---|-------|--------|------|
| 0 | **Bootstrap** | `/init` | First time in a new repo — writes `CLAUDE.md` + a language-detected `.devcontainer`. |
| 1 | **Think** | superpowers `/brainstorm` → writing-plans | Any non-trivial change: turn an idea into a design, then a task-by-task plan. |
| 2 | **Pressure-test** | `/debate:all` | Send the plan (or a stubborn bug) to a **Grok + ChatGPT + Claude** reviewer panel *before* writing code. They argue out contradictions and return `APPROVED` / `REVISE`. |
| 3 | **Build** | superpowers subagent execution · ultracode Workflow | Execute the approved plan. |
| 4 | **Clean** | `/code-cleanup` | Right after the build lands — dedup, dead code, weak types, dead paths, AI slop, run by worktree-isolated forks so nothing collides. |
| 5 | **Map** | `/update-codemaps` | After cleanup — regenerate the token-lean architecture maps in `codemaps/` so the *next* session starts with accurate context. |
| 6 | **Capture** | `skill-postmortem` · `session-learnings` · `compound` | Close the loop: review a skill that misbehaved, fold session lessons into `CLAUDE.md`, and write hard-won fixes to project memory. |
| ✓ | **Gate** (anytime) | `check-in` | Wherever a wrong "done" is costly — a 3-judge, evidence-checked completion gate that runs a check command and reads repo state, not just the transcript. |

## Stage detail

**0 · `/init`** — bootstraps a repo for Claude Code. Analyzes structure, writes a
starter `CLAUDE.md` (commands + conventions), and scaffolds a `.devcontainer`
with a base image chosen from the detected language. I use this instead of
Claude's built-in `/init`.

**1 · Think (superpowers)** — `/brainstorm` refines an idea into a design spec;
writing-plans turns the spec into bite-sized, testable tasks. This is the one
stage that stays entirely in superpowers — it's the engine, not something this
repo replaces.

**2 · `/debate:all`** — the highest-leverage quality gate. A panel of independent
reviewers (my default panel spans Claude/Opus, ChatGPT/Codex, and Grok personas)
reads the plan in parallel, surfaces hidden assumptions and failure modes,
debates the contradictions, and converges on a verdict with a SHA-verified plan.
Also works on a nasty bug: paste the symptom + suspect code and let the panel
theorize. Runs on the `cc-debate` plugin under the hood.

**3 · Build** — execute the approved plan with superpowers subagent execution or
an ultracode Workflow.

**4 · `/code-cleanup`** — deep, systematic cleanup after the feature is in.
Nine concern-scoped forks (dedup, type consolidation, dead code, circular deps,
weak types, dead paths, mechanical autofix, test hygiene, AI slop), each in its
own worktree in edit mode, reconciled with a real 3-way merge. Dry-run by default.

**5 · `/update-codemaps`** — regenerates `codemaps/` (a token-lean architecture
map that loads at session start). Do this after cleanup so the maps reflect the
*post-cleanup* structure. Ships as the separate `cc-codemaps` plugin.

**6 · Capture** — three ways to make the work compound:
- `skill-postmortem` — review a skill against the sessions where it actually
  fired, and propose evidence-backed edits.
- `session-learnings` — fold non-obvious commands, corrections, and gotchas into
  the project's `CLAUDE.md` before you `/clear` or compact.
- `compound` — after a hard-won fix, write the root cause + solution to project
  memory so future sessions auto-load it.

**✓ · `check-in`** — a completion gate you can drop anywhere. It runs a check
command, reads repo state, and has three Haiku judges (Literalist / Verifier /
Skeptic) vote on whether the goal is *actually* met, returning actionable gaps.

## Mine vs borrowed

| Tool | Origin |
|------|--------|
| `debate`, `code-cleanup`, `skill-postmortem`, `check-in` | Mine (some forked from STRML, then developed further). |
| `session-learnings`, `compound`, `/init` | [STRML/cc-skills](https://github.com/STRML/cc-skills) — vendored verbatim (MIT), credited in each file. |
| `/update-codemaps` | [STRML/cc-codemaps](https://github.com/STRML/cc-codemaps) — referenced as a plugin (not vendored). |
| `/brainstorm`, writing-plans, subagent execution | Anthropic **superpowers** plugin — the planning/execution engine this loop wraps. |

## Install

```
# 1. This plugin (all the skills + the /init command)
/plugin marketplace add pipXBT/agent-shenanigans
/plugin install agent-shenanigans@agent-shenanigans

# 2. codemaps (separate plugin)
/plugin marketplace add STRML/cc-codemaps
/plugin install cc-codemaps@cc-codemaps

# 3. debate command backend (separate plugin — the /debate:* commands)
/plugin marketplace add STRML/cc-debate
/plugin install debate@cc-debate

# 4. superpowers (the planning/execution engine) — install per its own instructions,
#    then use /brainstorm + writing-plans
```

Restart Claude Code after installing plugins so new skills and commands load.
