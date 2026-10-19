---
name: run-plan
description: "Use to execute a superpowers:writing-plans file one task at a time with a skeptic, a teeth check, a test gate, and a receipt per task, then a three-reviewer pass. Triggers: 'run the plan', 'execute the implementation plan', '/agent-shenanigans:run-plan'. With --probe it instead checks that agents this repo starts get the modes and have no tools."
---

# run-plan: entry point for adversarial-verification

Parse a plan file in code, show the owner what will run, then start the host's executor with the
arguments `workflows/CONTRACT.md` section 1 defines. The executor does the work; this skill only
checks, launches, and reports. Claude Code runs `workflows/adversarial-verification.js`; Grok Build
runs `workflows/adversarial-verification.rhai`.

`<plugin dir>` is the plugin root, the folder that holds `skills/`, `agents/`, `rules/`, and
`workflows/`. Claude sets `CLAUDE_PLUGIN_ROOT`; on Grok use the folder this file was loaded from.

## Run a plan

1. **Inputs.** Take from the owner's message, and ask once for what is missing:
   - the plan file (absolute path), and the repo it applies to (default: `git rev-parse --show-toplevel`);
   - `test_cmd` (required), `lint_cmd` (optional), `branch` (optional);
   - `rules` = `{high_risk: [glob], test_globs: [glob]}` and `forbid: [glob]`, each defaulting to `[]`;
   - `review` (default `true`; `false` when the owner says no review) and `ponytail` (`"full"`, or `"ultra"` when the owner asks).
2. **Refuse a Fable session.** If this session's model id contains `fable` (any case), stop and say so.
3. **Grok only.** Refuse unless the session effort is `xhigh` (confirm it; if it cannot be read, refuse).
   Refuse when `adversarial-verification.js` exists in `~/.grok/workflows`: that is the daemon route
   (a workflow converted to JS), which does not run the `.rhai` executor. Otherwise treat the route as
   the shell route. If `adversarial-verification.rhai` is missing from `~/.grok/workflows`, stop and tell the owner to run `./doctor --fix`.
4. **Parse.** Run `python3 "${CLAUDE_PLUGIN_ROOT:-<plugin dir>}/skills/run-plan/scripts/parse_plan.py" "<plan_path>"`.
   It prints `{plan_hash, tasks, errors}` and exits 1 when `errors` is non-empty. Show each error and stop.
5. **Show the tasks.** A table of `id`, `title`, `kind`, `kind_source` (`marker` or `derived`), and `complexity`
   (`null` shows as "plan agent decides"). Say that `superpowers:writing-plans` does not write the optional
   `**Kind:**` and `**Complexity:**` marker lines, so every `derived` kind came from the task's paths and the
   owner can add markers and rerun if one is wrong.
6. **State the cost.** Expect about seven agents per task, plus three reviewers and one verifier per finding:
   `7 x <tasks> + 3` before findings, more with retries. Wait for the owner to say go.
7. **Nonce.** `python3 -c "import secrets; print(secrets.token_hex(16))"` gives `run_nonce`. A new one every run.
8. **Launch** with `args` = `{repo, test_cmd, lint_cmd, plan_path, plan_hash, branch, rules, forbid, review, ponytail, run_nonce, tasks}`.
   `plan_hash` and `tasks` come from step 4 unchanged. Leave out `lint_cmd` and `branch` when not given. Never pass `fixture`.
   - **Claude Code.** `Workflow({scriptPath: "<plugin dir>/workflows/adversarial-verification.js", args})`.
     Never pass `resumeFromRunId`.
   - **Grok Build.** Run the named workflow `adversarial-verification` with the same `args`, at effort `xhigh`.
9. **Report** the result object: `ok`, `stage`, `task`, `summary`, and the per-task `outcome`, `attempts`, `teeth`, `model`.

Never resume a run. If a run stops or is killed, a restart is a new run of this skill with a new
`run_nonce`; the executor reads the saved run state itself (`CONTRACT.md` section 3).

## `--probe`

Checks, once per host from a session in another repo, that an agent this repo starts gets the modes
from the host's own hooks and rules (not from a paste), has no tools, and ran on the model and effort
asked for. It writes `~/.agent-shenanigans-probe/<claude|grok>.json`, which `./doctor` reads. Do not
run a plan in this mode.

1. `PROBE_DIR=$(mktemp -d)` and `cd "$PROBE_DIR"`. The session's working directory must be outside the
   plugin root and outside this repo; if it cannot be, stop.
2. **Prompt**, exactly, with no modes text, token, path, or repo name beyond the prefix quoted in item 1:

   ```text
   This is a capability check. Answer from what is already in your context. Call no tool.
   1. Quote exactly every line of your context that starts with "agent-shenanigans modes", or write NONE.
   2. Quote exactly any text of your context that says a mode is active, with its level, or write NONE.
   3. Quote the working directory line you were given, or write NONE.
   4. List every tool you can call, or write NONE.
   ```

3. **Spawn one agent.**
   - **Claude Code.** One Workflow with the prompt in `args.prompt`:

     ```js
     export const meta = { name: 'run-plan-probe', description: 'Spawn one tool-less agent and return its answer' }
     return await agent(args.prompt, { label: 'probe', agentType: 'agent-shenanigans:probe', model: 'claude-opus-5-5', effort: 'xhigh' })
     ```

   - **Grok Build.** `spawn_subagent` with a capability mode that has no file, shell, or search tool, `model: "grok-4.7"`.
     If the spawn rejects `model`, set `model_param_rejected` true and spawn again without it.
4. **Read the host's record** of that agent: on Claude the Workflow run journal and the agent's transcript
   (`journal.jsonl`, `agent-<id>.jsonl` in the run's transcript folder); on Grok the child session's `summary.json`.
   `tool_calls` is the number of tool calls it shows. `recorded` is the `{model, effort}` it shows, or `null` if the
   record has none (then say `model and effort: requested only` in `detail`). If no record can be found, stop: a
   missing record is not a pass.
5. **Token.** Read the first line of `rules/modes.md` (`agent-shenanigans modes <token>`). `token_seen` is true only
   when the agent's quoted line holds that token.
6. **Route.** Grok: `shell`, or `daemon` when `adversarial-verification.js` exists in `~/.grok/workflows`. Claude: `null`.
7. **Write the file.** `shas` is the JSON `python3 "<plugin dir>/doctor" --shas` prints now (doctor marks the probe stale
   when these differ from the loaded SHAs). `written_at` is epoch seconds
   (`python3 -c "import time; print(time.time())"`). `cwd` is the working directory the agent quoted, else the
   session's `pwd`. `mkdir -p ~/.agent-shenanigans-probe`, then write:

   ```json
   {"host": "claude|grok", "passed": true, "token_seen": true, "activation": "<the text quoted for item 2, or NONE>",
    "requested": {"model": "claude-opus-5-5|grok-4.7", "effort": "xhigh"},
    "recorded": {"model": "...", "effort": "..."}, "route": "shell|daemon|null",
    "model_param_rejected": false, "cwd": "<dir>", "tool_calls": 0, "written_at": 0.0,
    "shas": {"agent-shenanigans": "<sha>"}, "detail": "<why it failed, or empty>"}
   ```

   `recorded` is `null` when the host kept none; `detail` is read by `./doctor` when `passed` is false.
8. **`passed`.** All of these, else false with the reason in `detail`: `tool_calls` is 0; the agent listed no tool
   in item 4; `cwd` is outside the plugin root; `recorded`, when not `null`, equals `requested`.
   Claude also needs `token_seen` and `activation` text from the caveman and ponytail hooks that names
   `ultracave` and `full` (the hook lines read `CAVEMAN MODE ACTIVE — mode: ultracave` and
   `PONYTAIL MODE ACTIVE — level: full`; seen at the first live probe, 2026-10-20). A line copied from
   `rules/modes.md` does not count: it must be hook text. Grok has no hooks; it needs `token_seen` only.
9. Print the file and one line saying passed or why not.

### Runbook: Haiku at `xhigh` (once per Claude install)

The executor runs low-complexity tasks on `claude-haiku-5-5` at `xhigh`. Checked 2026-10-20: the host accepted it
and recorded `claude-haiku-5-5` at `xhigh`. Re-check after a Claude Code update that changes models. In the same
probe session spawn one Workflow `agent()` with `model: "claude-haiku-5-5", effort: "xhigh"` and a trivial prompt.
If the host rejects that effort, change `CLAUDE_MODELS.low` in `workflows/adversarial-verification.js` to
`claude-sonnet-5-5` and write here that low-tier tasks run on Sonnet. Update `CONTRACT.md` section 6 and any executor test that names the Haiku model to match.
