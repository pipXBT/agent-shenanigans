# agent-shenanigans

The control copy of my [Claude Code](https://claude.com/claude-code) and Grok Build workflow:
brainstorm, debate the spec, plan, run the plan with verification, clean up, map the code. One
plugin, one declared stack, the same behaviour on either host.

> **New here?** [`WORKFLOW.md`](./WORKFLOW.md) walks the loop and the install steps.

## What is mine and what is not

The debate seat runner, the plan executors, the entry skills, `doctor`, and the modes file are
owner-authored and live in this repo. Upstream plugins (superpowers, caveman, ponytail,
cc-codemaps) are installed as-is and declared in [`stack.toml`](./stack.toml); nothing of theirs is
copied here, so nothing here can go stale against its source.

## Install

```
git clone https://github.com/pipXBT/agent-shenanigans.git
cd agent-shenanigans
./doctor           # report drift against stack.toml (exit 0 clean, 1 drift, 2 could not check)
./doctor --fix     # patch what doctor owns, print the plugin commands to run
```

`doctor` never deletes (it moves to `~/.agent-shenanigans-backup/<run-id>/`) and never runs
`claude plugin` or `grok plugin`. The full day-one sequence, with the probes, is in
[`WORKFLOW.md`](./WORKFLOW.md#install). Restart the host after installing plugins.

| Command | What it does |
|---------|--------------|
| `./doctor` | Read-only drift report, grouped by host. |
| `./doctor --fix` | Patch settings, create links, retire stale copies; print the plugin commands. |
| `./doctor --rollback <run-id>` | Undo one `--fix` run from its backup folder. |
| `./doctor --seat-probe` | Run the debate seat runner's probe. |
| `./doctor --accept` | Record the loaded plugin SHAs as verified, when both hosts agree. |
| `./doctor --shas` | Print the loaded plugin SHAs as JSON. |

## Skills

| Skill | What it does |
|-------|--------------|
| [debate](./skills/debate/) | Review a spec or plan with a 14-seat panel: seven personas, each on Opus 5.5 and Grok 4.7 at `xhigh`. A mechanical round rule gives `APPROVED` or `REVISE`; after 3 rounds the owner may record `OWNER-ACCEPTED`. |
| [run-plan](./skills/run-plan/) | Execute a `superpowers:writing-plans` file task by task: skeptic, teeth check, test gate, and a receipt per task, then a three-reviewer pass. `--probe` checks that agents this repo starts get the modes and have no tools. |
| [code-cleanup](./skills/code-cleanup/) | Deep cleanup by nine fresh tiered agents, one per concern (dedup, dead code, weak types, dead paths, AI slop, ...). Dry-run by default; worktree per mandate in edit mode. |
| [check-in](./skills/check-in/) | Context-verified completion gate: a three-judge panel advises an overseer that decides whether a goal is actually met, from a check command and repo state, not just the transcript. |
| [skill-postmortem](./skills/skill-postmortem/) | Review a skill against the sessions where it fired; rank friction by confidence and propose edits you approve one by one. |

One `SKILL.md` per skill, loaded by both hosts; a **Host** section names what differs.

## Layout

See [`AGENTS.md`](./AGENTS.md) for the repo map and how to add a skill. The executor contract is
[`workflows/CONTRACT.md`](./workflows/CONTRACT.md).

## Credits

- [obra/superpowers](https://github.com/obra/superpowers) (Jesse Vincent): `brainstorming`,
  `writing-plans`, and the planning habit this loop wraps. Installed as-is.
- [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) and
  [ponytail](https://github.com/DietrichGebert/ponytail): the terse and minimal modes every agent
  here runs in. Installed as-is.
- [STRML/cc-skills](https://github.com/STRML/cc-skills) and
  [STRML/cc-debate](https://github.com/STRML/cc-debate) (Samuel Reed, MIT): [`code-cleanup`](./skills/code-cleanup/)
  and the [`debate`](./skills/debate/) personas are adaptations that credit their source and
  name what changed. The seat runner and panel file are my own.
- [STRML/cc-codemaps](https://github.com/STRML/cc-codemaps): `/update-codemaps`. Installed as-is.
- [`ciembor/agent-rules-books`](https://github.com/ciembor/agent-rules-books) (Maciej
  Ciemborowicz): the scope-discipline guard in `code-cleanup`.

## License

[MIT](./LICENSE). Do whatever you want; no warranty.
