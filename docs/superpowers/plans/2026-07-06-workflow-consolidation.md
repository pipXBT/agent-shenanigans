# Workflow Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `agent-shenanigans` the single home + documented pipeline for the author's non-superpowers Claude Code workflow.

**Architecture:** Vendor three Sam-authored pieces verbatim (session-learnings, compound, init) with attribution; reference the cc-codemaps plugin; teach `install.sh` to link commands; add `WORKFLOW.md` as the shareable pipeline doc; update README/AGENTS.

**Tech Stack:** Markdown skills/commands, POSIX bash (`install.sh`), symlink-based install.

## Global Constraints

- Attribution required on every vendored file: STRML / `cc-skills` / MIT, "vendored verbatim, unmodified."
- Vendored pieces are **Claude-only** — no `SKILL.grok.md`.
- No secrets or personal absolute paths introduced.
- **No `git push`** — author pushes when ready.
- Upstream sources live in the local clone at `~/cc-skills` (skills at `skills/<name>/SKILL.md`, init at `commands/init.md`); the fresh reference clone is also in the session scratchpad.
- Commit after each task (direct to `main`, matching repo convention). Do **not** stage the pre-existing unstaged `debate/` edits — they are a separate concern.

---

### Task 1: Vendor `session-learnings` and `compound`

**Files:**
- Create: `session-learnings/SKILL.md`
- Create: `compound/SKILL.md`
- Source: `~/cc-skills/skills/<name>/SKILL.md` (single file each, no scripts/refs)

**Interfaces:**
- Produces: two new skill dirs discoverable by `install.sh`'s skill loop (each has a `SKILL.md`).

- [ ] **Step 1:** Copy `~/cc-skills/skills/session-learnings/SKILL.md` → `session-learnings/SKILL.md`, and `~/cc-skills/skills/compound/SKILL.md` → `compound/SKILL.md`, byte-for-byte.

- [ ] **Step 2:** In each new file, insert this attribution blockquote on the line immediately after the closing `---` of the YAML frontmatter:

```markdown

> Vendored verbatim from Samuel Reed's ([STRML](https://github.com/STRML))
> [`cc-skills`](https://github.com/STRML/cc-skills) (MIT). Unmodified; upstream
> remains canonical. Claude Code only.
```

- [ ] **Step 3: Verify** the files exist, carry the credit, and differ from upstream by exactly the attribution block:

```bash
for s in session-learnings compound; do
  grep -q 'Vendored verbatim from Samuel Reed' "$s/SKILL.md" && echo "$s: credited"
  diff <(grep -v 'STRML\|Vendored verbatim\|upstream remains canonical\|Claude Code only' "$s/SKILL.md") \
       ~/cc-skills/skills/$s/SKILL.md && echo "$s: body matches upstream"
done
```
Expected: both print "credited" and "body matches upstream".

- [ ] **Step 4: Commit**

```bash
git add session-learnings/SKILL.md compound/SKILL.md
git commit -m "feat(vendor): session-learnings + compound from STRML/cc-skills (MIT, credited)"
```

---

### Task 2: Vendor `init` as the repo's first command

**Files:**
- Create: `commands/init.md`
- Source: `~/cc-skills/commands/init.md`

**Interfaces:**
- Produces: a top-level `commands/` dir (new convention) holding Claude slash-commands.

- [ ] **Step 1:** Copy `~/cc-skills/commands/init.md` → `commands/init.md` byte-for-byte.

- [ ] **Step 2:** Insert, on the line immediately after the frontmatter closing `---`:

```markdown

> Vendored verbatim from Samuel Reed's ([STRML](https://github.com/STRML))
> [`cc-skills`](https://github.com/STRML/cc-skills) (MIT). Unmodified; upstream
> remains canonical. Claude Code slash-command.
```

- [ ] **Step 3: Verify**

```bash
test -f commands/init.md && grep -q 'Vendored verbatim' commands/init.md && echo "init: vendored + credited"
```
Expected: "init: vendored + credited".

- [ ] **Step 4: Commit**

```bash
git add commands/init.md
git commit -m "feat(vendor): /init command from STRML/cc-skills (MIT, credited)"
```

---

### Task 3: Extend `install.sh` to link commands

**Files:**
- Modify: `install.sh`

**Interfaces:**
- Consumes: existing `link()`, `run()`, `REPO_ROOT`, `TARGET`, `ARGS`, `DRY_RUN`.
- Produces: `commands/*.md` symlinked into `~/.claude/commands/` on full Claude installs.

- [ ] **Step 1:** After the `GROK_SKILLS_DIR` definition, add:

```bash
CLAUDE_COMMANDS_DIR="${CLAUDE_COMMANDS_DIR:-$HOME/.claude/commands}"
```

- [ ] **Step 2:** After the `install_grok()` function, add:

```bash
install_commands() {
  local src="$REPO_ROOT/commands"
  [[ -d "$src" ]] || return 0
  run mkdir -p "$CLAUDE_COMMANDS_DIR"
  while IFS= read -r f; do
    local base; base="$(basename "$f")"
    link "$f" "$CLAUDE_COMMANDS_DIR/$base" "commands/$base [claude]"
  done < <(find "$src" -maxdepth 1 -type f -name '*.md')
}
```

- [ ] **Step 3:** After the `for name in "${SKILLS[@]}"; do ... done` loop, before the final `echo`, add (commands are repo-global, Claude-only, full-install-only):

```bash
# Slash commands (Claude only, on a full install — not when specific skills are named)
if [[ "$TARGET" == "claude" || "$TARGET" == "both" ]] && [[ ${#ARGS[@]} -eq 0 ]]; then
  echo "commands:"
  install_commands
fi
```

- [ ] **Step 4:** Update the help header comment block (lines ~15-22) to mention that a full install also links `commands/*.md` into `~/.claude/commands/` (Claude only), so `--help` documents it.

- [ ] **Step 5: Verify** dry-run shows the command and grok skips it:

```bash
./install.sh --dry-run 2>&1 | grep -E 'init|commands' && echo "--- grok target ---"
./install.sh --dry-run --target grok 2>&1 | grep -c 'commands/init.md'
```
Expected: full dry-run lists `commands/init.md [claude]`; grok target prints `0`.

- [ ] **Step 6: Commit**

```bash
git add install.sh
git commit -m "feat(install): link commands/*.md into ~/.claude/commands (Claude, full install)"
```

---

### Task 4: Write `WORKFLOW.md`

**Files:**
- Create: `WORKFLOW.md`

- [ ] **Step 1:** Write `WORKFLOW.md` with exactly these sections: thesis (superpowers thinks, this repo wraps it); a pipeline table with a row per stage (0 bootstrap `/init`, 1 think superpowers, 2 debate `/debate:all`, 3 execute superpowers/ultracode/`parallel-orchestrate`, 4 clean `/code-cleanup`, 5 map `/update-codemaps` cc-codemaps plugin, 6 capture skill-postmortem/session-learnings/compound, ✓ gate `goal-check`); a one-paragraph detail per stage; a "Mine vs borrowed" table; an Install section with `git clone` + `./install.sh` + the two `/plugin` commands (`/plugin marketplace add STRML/cc-codemaps`, `/plugin install cc-codemaps@cc-codemaps`).

- [ ] **Step 2: Verify** all pipeline tools and the plugin commands are named:

```bash
for t in /init /debate:all parallel-orchestrate /code-cleanup /update-codemaps skill-postmortem session-learnings compound goal-check 'cc-codemaps@cc-codemaps'; do
  grep -qF "$t" WORKFLOW.md && echo "ok: $t" || echo "MISSING: $t"
done
```
Expected: every line prints `ok:`.

- [ ] **Step 3: Commit**

```bash
git add WORKFLOW.md
git commit -m "docs: add WORKFLOW.md — the end-to-end non-superpowers pipeline"
```

---

### Task 5: Update `README.md` and `AGENTS.md`

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1:** README — add `session-learnings` and `compound` rows to the skills table (CLIs column: "Claude"; note "vendored from STRML"); add a **Commands** subsection documenting `/init`; add a **Referenced plugins** note with the two codemaps `/plugin` commands; add a **See also** line pointing to `STRML/cc-skills` for `recall` / `scan-diff` / `commit-and-verify` / `coderabbit-new`; add a prominent link to `WORKFLOW.md` near the top; extend **Credits** to list the three vendored pieces + the referenced plugin.

- [ ] **Step 2:** AGENTS.md — under "Adding or editing a skill" (or a new "Commands" note), document that top-level `commands/*.md` are Claude-only slash-commands linked by `install.sh` on a full install; add a one-line pointer to `WORKFLOW.md`.

- [ ] **Step 3: Verify**

```bash
grep -q 'WORKFLOW.md' README.md && grep -q 'session-learnings' README.md && grep -q 'cc-codemaps@cc-codemaps' README.md && echo "README ok"
grep -q 'commands/' AGENTS.md && echo "AGENTS ok"
```
Expected: "README ok" and "AGENTS ok".

- [ ] **Step 4: Commit**

```bash
git add README.md AGENTS.md
git commit -m "docs: README/AGENTS — vendored skills, /init command, codemaps plugin, WORKFLOW link"
```

---

### Task 6: Full-install smoke check (no push)

- [ ] **Step 1:** Confirm the full dry-run reflects the consolidated repo:

```bash
./install.sh --dry-run 2>&1 | grep -E '\[claude\]|\[grok|commands/' 
```
Expected: 7 skills (debate, code-cleanup, parallel-orchestrate, skill-postmortem, goal-check, session-learnings, compound) + `commands/init.md [claude]`.

- [ ] **Step 2:** Confirm nothing was pushed and the tree is clean except the intended commits + the pre-existing debate edits:

```bash
git log --oneline origin/main..main
git status --short
```
Expected: the task commits ahead of origin; `debate/` edits still unstaged; no other surprises.

## Self-Review

- **Spec coverage:** C1→Task 1, C2→Task 2, C3→Task 3, C4→Task 4, C5→Task 5, acceptance criteria→Task 6. All covered.
- **Placeholders:** none — attribution blocks and install.sh code are shown verbatim; WORKFLOW/README content is specified by exact required tokens with grep verification.
- **Consistency:** `CLAUDE_COMMANDS_DIR`, `install_commands`, and the full-install guard names match across Task 3 steps and Task 6 checks.
