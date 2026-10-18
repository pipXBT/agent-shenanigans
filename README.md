# agent-shenanigans

A personal [Claude Code](https://claude.com/claude-code) **plugin** — my workflow for
non-trivial work: debate a plan, orchestrate the build, clean up, map the codebase, and
capture what was learned.

> **New here?** [`WORKFLOW.md`](./WORKFLOW.md) shows how these skills fit together into
> one end-to-end pipeline (bootstrap → think → debate → build → clean → map → capture),
> alongside superpowers and two referenced plugins.


## Install

```
/plugin marketplace add pipXBT/agent-shenanigans
/plugin install agent-shenanigans@agent-shenanigans
```

Restart Claude Code — all skills below plus the `/init` command load. For the full
pipeline you'll also want the two referenced plugins (below).

## Skills

| Skill | What it does |
|-------|--------------|
| [debate](./skills/debate/) | Multi-AI plan review before writing code — a Grok + ChatGPT + Claude reviewer panel runs in parallel, surfaces hidden assumptions and failure modes, debates contradictions, and returns an `APPROVED`/`REVISE` verdict with SHA-verified plans. |
| [parallel-orchestrate](./skills/parallel-orchestrate/) | Decompose a design doc into one feature per agent, then fan out one agent per feature into its own git worktree + branch, each inheriting the orchestrator's recon as live context. |
| [code-cleanup](./skills/code-cleanup/) | Deep, systematic cleanup — nine concern-scoped forks (dedup, dead code, weak types, dead paths, AI slop, …), each in its own worktree in edit mode, reconciled with a real 3-way merge. Dry-run by default. |
| [skill-postmortem](./skills/skill-postmortem/) | Review a skill against the sessions where it actually fired; categorize friction, confidence-rank, and propose evidence-backed edits — you approve each before it lands. |
| [check-in](./skills/check-in/) | Context-verified completion gate — a 3-judge Haiku panel (Literalist / Verifier / Skeptic) votes on whether a goal is *actually* met, checking a command + repo state, not just the transcript. |
| [session-learnings](./skills/session-learnings/) | Fold non-obvious commands, corrections, and gotchas into the project's `CLAUDE.md`. *Vendored verbatim from [STRML/cc-skills](https://github.com/STRML/cc-skills) (MIT).* |
| [compound](./skills/compound/) | After a hard-won fix, write root cause + solution into project memory for future sessions to auto-load. *Vendored verbatim from [STRML/cc-skills](https://github.com/STRML/cc-skills) (MIT).* |

> `debate` and `code-cleanup` also ship dormant Grok-native ports (`SKILL.grok.md`) from
> when this was a dual-CLI repo. Claude Code plugins are Claude-only, so the plugin does
> not wire them up — they remain in the source for manual Grok use.

## Command

| Command | What it does |
|---------|--------------|
| `/init` | Bootstrap a repo for Claude Code — writes `CLAUDE.md` + a language-detected `.devcontainer`. *Vendored verbatim from [STRML/cc-skills](https://github.com/STRML/cc-skills) (MIT).* Used instead of Claude's built-in `/init`. |

## Grok workflows

Grok Build workflows live in `grok/workflows/`. They are not part of the Claude
plugin, and `/plugin install` does not load them. `deep-research` and
`learn-traces` already ship with Grok, so they are not copied here.

On another machine, after Grok Build is installed:

```
git clone https://github.com/pipXBT/agent-shenanigans.git
./agent-shenanigans/grok/install.sh
```

That symlinks each workflow into `~/.grok/workflows/`. Re-run it after
`git pull`. A workflow that is already a real file there is left alone.

| Workflow | What it does |
|----------|----------------|
| [adversarial-verification](./grok/workflows/adversarial-verification.rhai) | One task at a time: implement, skeptic, teeth, then test and lint gates, with one fix round. After the last task, three reviewers and one skeptic per finding. |

Run it from Grok with `/adversarial-verification` or
`/workflow adversarial-verification`. It pauses until you pass an object:

- `repo` — absolute path the agents `cd` into
- `test_cmd` — the gate command
- `tasks` — `[{title, brief, plan}]`, or a single `title` plus `brief`
- Optional: `lint_cmd`, `branch`, `rules`, `forbid`, `base_sha`, `review` (default true)

It will not commit to `main`, push, stash, or add a `Co-Authored-By` trailer.
A second failure on the same task stops the run.

## Referenced plugins

Two pieces of the pipeline are separate plugins — install them too:

- **codemaps** — architecture maps via `/update-codemaps`:
  `/plugin marketplace add STRML/cc-codemaps` → `/plugin install cc-codemaps@cc-codemaps`.
- **debate backend** — the `/debate:*` commands the `debate` skill drives:
  `/plugin marketplace add STRML/cc-debate` → `/plugin install debate@cc-debate`.

And the planning engine the whole flow wraps: the **superpowers** plugin (`/brainstorm`,
writing-plans). See [`WORKFLOW.md`](./WORKFLOW.md) for how it all fits together.

## See also

Other [STRML/cc-skills](https://github.com/STRML/cc-skills) I run but didn't bundle —
grab them upstream: `recall`, `scan-diff`, `commit-and-verify`, `coderabbit-new`.

## Repo layout (for contributors)

See [`AGENTS.md`](./AGENTS.md). In short: skills live in `skills/<name>/SKILL.md`, the
slash-command in `commands/`, and the plugin manifests in `.claude-plugin/`. Bundled
scripts are resolved at runtime via `${CLAUDE_PLUGIN_ROOT}` (with a discovery fallback),
so they work wherever the plugin is installed.

## Credits

- [`debate`](./skills/debate/) adapts Sam Reed's ([STRML](https://github.com/STRML))
  [`cc-debate`](https://github.com/STRML/cc-debate) + [`cc-skills`](https://github.com/STRML/cc-skills)
  (MIT). The `/debate:*` commands run on the upstream `cc-debate` plugin; this repo carries
  a customized reviewer panel and a Grok-native port.
- [`code-cleanup`](./skills/code-cleanup/) adapts STRML's `cc-skills` `code-cleanup` command
  and `cc-fork` tool (MIT, © Samuel Reed) — `scripts/cc-fork` vendored verbatim; this repo
  revises the concern set, adds worktree-isolated edit mode, and a scope-discipline guard
  distilled from [`ciembor/agent-rules-books`](https://github.com/ciembor/agent-rules-books)
  (Maciej Ciemborowicz).
- [`session-learnings`](./skills/session-learnings/), [`compound`](./skills/compound/), and
  [`/init`](./commands/init.md) are **vendored verbatim** from STRML's `cc-skills`
  (MIT, © Samuel Reed) — each carries an attribution header, otherwise unmodified.
- [`/update-codemaps`](https://github.com/STRML/cc-codemaps) is **referenced** as the
  `cc-codemaps` plugin — Sam maintains it upstream.

## License

[MIT](./LICENSE). Do whatever you want; no warranty.
