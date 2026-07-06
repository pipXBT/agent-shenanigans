# Plugin Conversion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Convert `agent-shenanigans` into an installable Claude Code plugin so a teammate can `/plugin install` it and replicate the workflow.

**Architecture:** Add `.claude-plugin/` manifests; move the 7 skill dirs into `skills/`; make bundled-script paths plugin-relative; delete `install.sh`; rewrite install docs to `/plugin`. Claude-only.

**Tech Stack:** Claude Code plugin format (`plugin.json` + `marketplace.json`, `skills/`, `commands/`), markdown, git.

## Global Constraints

- No skill behavior changes — only relocation + path plumbing + docs.
- Vendored attribution headers must survive the move.
- `SKILL.grok.md` files kept (dormant), not deleted.
- Work on a branch; commit per task; merge to main + push at the end (a plugin must be on GitHub to install via `pipXBT/agent-shenanigans`).
- `/plugin install` itself is the user's action (slash-command, not shell).

---

### Task 1: Add plugin manifests

**Files:** Create `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`

- [ ] **Step 1:** Write `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` with the exact content from the spec (§C1).
- [ ] **Step 2: Verify** both are valid JSON and marketplace lists one plugin with `source: "./"`:
```bash
python3 -c "import json; p=json.load(open('.claude-plugin/plugin.json')); m=json.load(open('.claude-plugin/marketplace.json')); assert p['name']=='agent-shenanigans'; assert m['plugins'][0]['source']=='./'; print('manifests OK:', p['name'], p['version'])"
```
- [ ] **Step 3: Commit** `git add .claude-plugin && git commit -m "feat(plugin): add .claude-plugin manifests (plugin.json + marketplace.json)"`

---

### Task 2: Relocate skills into skills/ and remove install.sh

**Files:** `git mv` 7 dirs → `skills/`; `git rm install.sh`

- [ ] **Step 1:** `mkdir -p skills` then `git mv <name> skills/<name>` for: debate, code-cleanup, parallel-orchestrate, skill-postmortem, goal-check, session-learnings, compound.
- [ ] **Step 2:** `git rm install.sh`.
- [ ] **Step 3: Verify** layout — 7 dirs under skills/ each with SKILL.md, none at root, install.sh gone, commands/init.md intact, attribution preserved:
```bash
ls skills/ | wc -l   # 7
for d in debate code-cleanup parallel-orchestrate skill-postmortem goal-check session-learnings compound; do test -f "skills/$d/SKILL.md" || echo "MISSING skills/$d/SKILL.md"; done
test ! -e install.sh && echo "install.sh gone"
test -f commands/init.md && echo "init present"
grep -q 'Vendored verbatim' skills/session-learnings/SKILL.md skills/compound/SKILL.md commands/init.md && echo "attribution intact"
```
- [ ] **Step 4: Commit** `git add -A && git commit -m "refactor(plugin): move skills into skills/, remove install.sh"`

---

### Task 3: Make bundled-script paths plugin-relative

**Files:** Modify `skills/parallel-orchestrate/SKILL.md`, `skills/code-cleanup/SKILL.md`

- [ ] **Step 1:** In `skills/parallel-orchestrate/SKILL.md`, at the start of Phase 4 (Fanout), insert the `$PO_SCRIPT` resolution block from spec §C3, then replace every `python3 ~/.claude/skills/parallel-orchestrate/scripts/spawn-parallel.py` with `python3 "$PO_SCRIPT"`.
- [ ] **Step 2:** In `skills/code-cleanup/SKILL.md`, update the `cc-fork` dependency line's symlink source to `${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/skills/code-cleanup}/scripts/cc-fork`.
- [ ] **Step 3: Verify** no bare hardcoded python-on-skills-path remains in the runtime skill:
```bash
grep -n 'python3 ~/.claude/skills/parallel-orchestrate' skills/parallel-orchestrate/SKILL.md && echo "STILL HARDCODED" || echo "parallel-orchestrate: clean"
grep -q 'PO_SCRIPT' skills/parallel-orchestrate/SKILL.md && echo "PO_SCRIPT present"
```
- [ ] **Step 4: Commit** `git add skills/parallel-orchestrate/SKILL.md skills/code-cleanup/SKILL.md && git commit -m "fix(plugin): resolve bundled scripts via CLAUDE_PLUGIN_ROOT with fallback"`

---

### Task 4: Rewrite install docs (README, WORKFLOW, AGENTS)

**Files:** Modify `README.md`, `WORKFLOW.md`, `AGENTS.md`

- [ ] **Step 1:** README — replace `## Install` / `## Updating` / `## Removing a skill` / `## Two CLIs, one repo` / manual-symlink block with one **Install (plugin)** section: `/plugin marketplace add pipXBT/agent-shenanigans` + `/plugin install agent-shenanigans@agent-shenanigans` + restart. Drop "and Grok Build" from the top blurb. Keep skills table, Commands, Referenced plugins, See also, Credits.
- [ ] **Step 2:** WORKFLOW.md — replace the `git clone + ./install.sh` install step with the three `/plugin` installs (agent-shenanigans, cc-codemaps, cc-debate).
- [ ] **Step 3:** AGENTS.md — replace the two-CLI/symlink model + install.sh refs with the plugin layout (`.claude-plugin/`, `skills/`, `commands/`, `${CLAUDE_PLUGIN_ROOT}` for scripts); keep vendored-attribution rule.
- [ ] **Step 4: Verify**:
```bash
grep -q 'plugin marketplace add pipXBT/agent-shenanigans' README.md && echo "README plugin-install ok"
! grep -q './install.sh' README.md && echo "README: no install.sh"
grep -q 'agent-shenanigans@agent-shenanigans' WORKFLOW.md && echo "WORKFLOW ok"
grep -q '.claude-plugin' AGENTS.md && echo "AGENTS ok"
```
- [ ] **Step 5: Commit** `git add README.md WORKFLOW.md AGENTS.md && git commit -m "docs(plugin): rewrite install to /plugin; drop symlink/two-CLI model"`

---

### Task 5: Rollout (post-merge)

> Runs after finishing-a-development-branch merges to main + pushes.

- [ ] **Step 1:** Remove superseded local symlinks (only those resolving into agent-shenanigans or the plugin-superseded cc-skills targets):
```bash
for s in debate code-cleanup goal-check parallel-orchestrate skill-postmortem session-learnings compound; do
  l="$HOME/.claude/skills/$s"; t=$(readlink "$l" 2>/dev/null) || continue
  case "$t" in *agent-shenanigans*|*cc-skills/skills/session-learnings|*cc-skills/skills/compound) rm "$l"; echo "removed $s -> $t";; esac
done
il="$HOME/.claude/commands/init.md"; t=$(readlink "$il" 2>/dev/null); case "$t" in *cc-skills/commands/init.md) rm "$il"; echo "removed init.md -> $t";; esac
```
- [ ] **Step 2:** Hand the user the install commands (I cannot run `/plugin`):
  `/plugin marketplace add pipXBT/agent-shenanigans` then `/plugin install agent-shenanigans@agent-shenanigans`, then restart Claude Code.
- [ ] **Step 3: Verify** (structural, since I can't run /plugin): manifests valid, plugin layout matches Sam's working plugins, GitHub has the converted tree.

## Self-Review

- Spec coverage: C1→T1, C2+C4→T2, C3→T3, C5→T4, C6→T5. Covered.
- No placeholders: manifest content + path-fix block are in the spec, referenced exactly.
- Consistency: `$PO_SCRIPT` defined in T3 and checked in T3 verify; plugin name `agent-shenanigans@agent-shenanigans` consistent across T1/T4/T5.
