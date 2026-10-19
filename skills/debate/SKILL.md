---
name: debate
description: "Use for multi-AI plan review before writing code. Get second opinions from Codex, Gemini, Opus, DeepSeek, etc. Triggers: 'debate the plan', 'multi-model review', 'run debate', 'get reviewer feedback', 'second opinion on this approach', '/debate:all'."
---

# Debate — Multi-AI Plan Review

Before implementing any non-trivial plan, send it to a panel of independent AI reviewers (Codex, Gemini, Claude Opus, Mercury, DeepSeek, etc.) running in parallel. They surface hidden assumptions, failure modes, and structural issues, debate contradictions, and produce a consensus verdict (APPROVED / REVISE).

This is the highest-leverage quality gate in the toolkit. Use it on design specs, implementation plans, architecture changes, and any work where "I wish I had caught that earlier" is a risk.

## Host

Read this before any command in this file.

- **Grok Build.** Skip acpx, `/debate:*`, `~/.claude/debate-acpx.json`, and `SKILL.workflow.md`. Run **Grok Build — panel** at the bottom of this file.
- **Claude Code.** Run the acpx engine below. If the acpx preflight fails, use `SKILL.workflow.md` in this directory. Do not run the Grok panel.

## Prerequisites (one-time)

**Claude Code.** Grok Build skips everything until **Grok Build — panel**.

```bash
# 1. acpx (unified agent protocol client)
npm install -g acpx@latest

# 2. jq (required by scripts)
brew install jq   # macOS
```

## Initial Setup

```bash
# Interactive reviewer configuration (recommended)
/debate:acpx-setup
```

This walks you through:
- Detecting installed agent CLIs (codex, gemini, opencode, etc.)
- Creating OpenRouter/LiteLLM agents for models not natively supported
- Probing connectivity
- Generating a starter `~/.claude/debate-acpx.json`

## Config (`~/.claude/debate-acpx.json`)

Reviewers are defined here. Example with three local Opus personas:

```json
{
  "reviewers": {
    "skeptic": {
      "agent": "opus",
      "timeout": 240,
      "system_prompt": "You are The Skeptic. ..."
    },
    "architect": { ... },
    "pragmatist": { ... }
  }
}
```

Mix and match any acpx-supported agents: `codex`, `gemini`, `claude`, `opencode`, custom OpenRouter models (DeepSeek R1, Mercury, Kimi, etc.), LiteLLM local models, etc.

See `/debate:acpx-setup` output for the current panel and any missing auth.

## Engine selection (Claude Code)

Grok Build does not use this list. It uses **Grok Build — panel**. Claude Code picks acpx, and uses the Workflow port when acpx fails:

1. **acpx** (`/debate:all`, cc-debate plugin) — multi-vendor CLIs. Use when
   acpx subprocesses actually work in this environment.
2. **Claude Code Workflow port** (`debate/SKILL.workflow.md`, alongside this
   file) — the panel as a Workflow script with schema-forced verdicts; no
   external CLIs. Use when acpx is broken/unavailable, or when you want
   structured findings instead of regexing verdicts from prose.
3. **Grok Build panel** — the section at the bottom of this file. Not acpx. Not `SKILL.workflow.md`.

**The external-CLI path is the flaky one — probe it, don't trust it.**
Observed failure modes (different sessions, same environment): (a) every
reviewer exits 1 "claude CLI not installed" — acpx subprocesses not on PATH
(fixed by invoke-acpx.sh's direct-CLI bypass IF `claude`/`grok` are on PATH);
(b) the grok lenses exit 1 again weeks later — CLI auth drift — forcing a
mid-debate re-run of those lenses as Agent subagents. In BOTH modes the
runner exits 0 and reports "complete" within seconds. Preflight: run ONE
cheap reviewer through `invoke-acpx.sh` and check its `<name>-exit.txt` is 0
with a non-stub `<name>-output.md`; on any failure go STRAIGHT to the
Workflow port. A full 7-lens attempt + a 900s background skeptic is the
observed cost of finding out the slow way.

## Usage

### Full multi-model debate (recommended)

```bash
/debate:all
```

- Runs all reviewers in `~/.claude/debate-acpx.json` in parallel
- Includes a parallel Claude Opus "claude-skeptic" subagent
- Synthesizes findings, runs a targeted debate phase on contradictions
- Up to 3 revision rounds + verification passes
- Final consensus verdict with SHA-verified plan

Options:
- `/debate:all codex,gemini` — run only specific reviewers
- `/debate:all skip-debate` — straight to final report, no debate round

### Lighter Claude-only reviews

- `/debate:claude-review` — single Opus skeptic (up to 5 rounds)
- `/debate:claude-double-review` — Skeptic + Architect in parallel
- `/debate:claude-custom-review` — interactive personality + model picker

### Setup & diagnostics

- `/debate:setup` — print permission allowlist for unattended use, verify symlinks
- `/debate:acpx-setup` — interactive config + connectivity probe (run this first)

## Unattended / No-prompt mode

After first use, add the printed Bash/Read/Write/Agent patterns to your `~/.claude/settings.json` `"permissions"."allow"` array so future debates never ask for approval.

`/debate:setup` prints the exact snippet with your real paths.

## When to reach for this

- Any plan > 1 page or touching > 2 subsystems
- Before a "wave" of implementation work
- After a major spec change
- When the cost of a bad assumption is high (auth, money, data loss, security)

## Notes

- The actual command implementations live in the `cc-debate` plugin (installed via `/plugin install debate@cc-debate`). This skill exists to surface the capability in every session's skill list.
- **Silent-success trap:** `run-parallel-acpx.sh` exits 0 even when EVERY reviewer errored — "review complete" in under ~10s means they all died instantly, not that they approved. Always check the per-reviewer `<name>-exit.txt` files (exit 1 + empty/stub `<name>-output.md` = dead reviewer), never infer success from the runner's exit code.
- A ready-to-use reviewer panel ships alongside this skill at `debate/debate-acpx.example.json` — a three-vendor default: **Claude/Opus** (Skeptic / Architect / Pragmatist), **Codex/ChatGPT** (Executor), and **Grok** (Bullshit Detector, Constraint Engineer, Pager Duty, Future Me). Copy it to `~/.claude/debate-acpx.json` to skip the interactive setup. Eight reviewers is a thorough panel; trim to a 2–4 reviewer subset (e.g. `/debate:all skeptic,executor,bullshit-detector`) for faster runs. The Codex/Grok legs need their CLIs installed and authed (`codex` + `OPENAI_API_KEY`; `grok` on PATH); Claude/Opus works out of the box.
- All reviewer output is read in full (no skimming). SHA checks prevent "I fixed it, trust me" bypasses.
- Work dirs are in `.tmp/ai-review-*` inside the project and cleaned up automatically (or via `safe-cleanup.sh`).
- Gemini requires a `GEMINI_API_KEY` in `~/.claude/settings.json` env (OAuth token does not work in acpx subprocess mode).

Run `/debate:acpx-setup` if you haven't configured reviewers yet.

---

**Claude Code Workflow users:** `SKILL.workflow.md` (this directory) runs the panel on Claude Code's Workflow tool. Same personas from `~/.claude/debate-acpx.json`. Claude Code only.

## Grok Build — panel

Skip every Claude section above. No acpx. No `/debate:*`. No `SKILL.workflow.md`.

Four personas, in parallel. Then synthesis. Then one debate exchange on real contradictions. Then a SHA gate. Max 3 revision rounds.

### Setup

```bash
REVIEW_ID=$(date +%s | shasum | cut -c1-8)
WORK_DIR="$PWD/.tmp/grok-debate-$REVIEW_ID"
mkdir -p "$WORK_DIR"
```

Write the plan verbatim to `$WORK_DIR/plan.md`. Show the first 20 lines and `wc -w`. Record the SHA:

```bash
shasum -a 256 "$WORK_DIR/plan.md" | cut -d' ' -f1 > "$WORK_DIR/round-0-plan.sha"
```

`todo_write` a board: capture, round 1, synthesis, debate, SHA, report.

### Round

One `spawn_subagent` per persona, same turn, `background: true`. Omit `subagent_type`. Do not pass `model`. The prompt tells the reviewer to read `$WORK_DIR/plan.md`. A subagent does not see this chat. Each prompt requires the reply to end with `VERDICT: APPROVED` or `VERDICT: REVISE`.

1. **Bullshit Detector.** Vague claims, unstated assumptions, "we'll figure it out later." Ask what the plan claims and why anyone should believe it.
2. **Constraint Engineer.** Physical, mathematical, and incentive limits. Ask what must be true, and whether it is true.
3. **Pager Duty Engineer.** Partial failure, config drift, 3am debug. No answer for "how do we debug this while it is on fire" means `REVISE`.
4. **Future Me.** Eighteen-month maintenance, one-person knowledge, decisions that look good in the PR and opaque later.

Then `get_command_or_subagent_output` with those task ids. Read each reply in full.

### Synthesis

List unanimous points, unique points, and contradictions. All `APPROVED`: go to the SHA gate. Any `REVISE`: debate the disagreeing pair, unless the user says to revise now.

### Debate

`spawn_subagent` with `resume_from` set to that reviewer's id. Quote the other side. Ask whether the verdict still holds. One exchange. Re-synthesize.

### SHA gate

Before any `APPROVED`, recompute `shasum -a 256` of `$WORK_DIR/plan.md`. Compare it to the SHA stored at the end of the last reviewer round. On a mismatch, re-review the diff, or tell the user the reviewers never saw these bytes and stop. Do not claim `APPROVED` on unseen bytes.

### Revise

Max 3 rounds. Write `$WORK_DIR/revisions-round-N.md`. Update `plan.md`. Store the new SHA. Re-run the reviewers who said `REVISE`, with the revision summary in the prompt.

### Report

Consensus, remaining concerns, each verdict, then `VERDICT: APPROVED` or `VERDICT: REVISE`. Leave `$WORK_DIR` unless the user says to delete it.

---

*Inspired by Sam Reed's ([STRML](https://github.com/STRML)) [`cc-debate`](https://github.com/STRML/cc-debate) plugin and [`cc-skills`](https://github.com/STRML/cc-skills). This is a personal adaptation; the upstream plugin remains the canonical implementation of the `/debate:*` commands.*
