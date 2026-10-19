# Control Copy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make this repo the single control copy of the owner's workflow on Claude Code and Grok Build: a declared stack checked by `./doctor`, a shared modes file, a repo-owned 14-seat debate runner, one implementation-workflow contract with an executor per host, and code-cleanup on fresh tiered agents.

**Architecture:** Data lives in `stack.toml` and `skills/debate/panel.json`. Executable logic is stdlib Python (`doctor` + `lib/doctor/`, the seat runner, the plan parser) and two workflow scripts (`workflows/adversarial-verification.js` for Claude, `.rhai` for Grok) that implement one written contract and are tested against the same scripted fixture cases. Skills are thin instructions that call those scripts.

**Tech Stack:** Python 3.11 stdlib (`tomllib`, `unittest`, `subprocess`, `fcntl`), Node 22 (`node:test`, no npm dependencies), Claude Code Workflow tool, Grok Build Rhai workflows.

**Spec:** `docs/superpowers/specs/2026-10-19-control-copy-design.md` (OWNER-ACCEPTED, revision 4). Read it before any task; section numbers below (§1–§7) refer to it.

## Global Constraints

- Python: 3.11, standard library only. Node: 22, built-ins only, no `package.json`.
- Full test command: `PYTHONPATH=lib python3 -m unittest discover -s tests -t . -v && node --test tests/workflows/`
- Model ids, exact: `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`, `grok-4.7`. Reject any id containing `fable`. Never use the `opus` alias in code.
- Effort is `xhigh` everywhere this repo sets one.
- Caveman mode id `ultracave`; ponytail `full` (or `ultra` when a run asks).
- Grok binary: always `~/.grok/bin/grok` (expanded), never bare `grok`.
- Never `git reset --hard`, `git clean -fd`, or `git stash` in code or in any prompt (the owner's settings deny the first two). Resets use `git reset --keep`; restores use `git restore`.
- Paths: backups `~/.agent-shenanigans-backup/<YYYY-MM-DDTHHMMSS>/`; probe results `~/.agent-shenanigans-probe/`; run state `.git/agent-shenanigans/<plan-hash>.json`; teeth aside folder `.git/agent-shenanigans/aside/`.
- `doctor` never deletes (it moves), never runs `claude plugin` / `grok plugin`, never writes to a git clone.
- Code, comments, commit messages, and docs are normal English. Credit upstream work by link (STRML `cc-debate` / `cc-skills`, caveman, ponytail, superpowers).
- Every task commits with a conventional-commit message.

## Review Focus

- A real `writing-plans` file whose code fences contain `### Task` lines or whose paths carry `:line` ranges must parse to the real tasks only (Task 13: `test_ignores_task_headings_inside_code_fences`, `test_strips_line_ranges`).
- A `grok inspect` output whose layout changed in a Grok update must make `doctor` exit 2, never report clean (Task 7: `test_parse_grok_inspect_rejects_unknown_layout`).
- A home config file that is a symlink into a dotfiles repo must be patched through to its target and stay a symlink (Task 9: `test_json_patch_follows_symlink`).
- Two `./doctor --fix` runs started at once must not both write; the second exits 2 (Task 10: `test_second_fix_while_locked`).
- A debate seat whose CLI is missing, unauthenticated, or hung must count as not returned within its timeout, never hang the round or count as a verdict (Task 4: `test_failing_cli_counts_not_returned`, `test_timeout_counts_not_returned`).

---

## Phase 1: Groundwork

### Task 1: Retire vendored skills and commit the kept edits

**Subproject:** Repo cleanup
**Kind:** refactor
**Complexity:** low
**Depends on:** none

**Files:**
- Delete: `skills/compound/SKILL.md`
- Delete: `skills/session-learnings/SKILL.md`
- Delete: `commands/init.md`
- Modify: `skills/check-in/SKILL.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `WORKFLOW.md`
- Modify: `skills/code-cleanup/SKILL.md`

- [ ] **Step 1: Discard the 2026-10-19 edits to files that are removed or replaced later**

Run: `git checkout -- skills/compound/SKILL.md skills/session-learnings/SKILL.md commands/init.md skills/debate/SKILL.workflow.md`

- [ ] **Step 2: Remove the retired files**

Run: `git rm -r skills/compound skills/session-learnings commands/init.md`

- [ ] **Step 3: Verify the tree**

Run: `git status --short`
Expected: `D` for the three removed paths; `M` only for `skills/check-in/SKILL.md`, `README.md`, `AGENTS.md`, `WORKFLOW.md`, `skills/code-cleanup/SKILL.md`; nothing else. Then the full test command (no tests exist yet; it must exit 0 or report "Ran 0 tests").

- [ ] **Step 4: Commit**

```bash
git add -A skills/check-in/SKILL.md README.md AGENTS.md WORKFLOW.md skills/code-cleanup/SKILL.md
git commit -m "chore: drop vendored compound, session-learnings and /init"
```

### Task 2: Modes file

**Subproject:** Shared modes
**Kind:** code
**Complexity:** low
**Depends on:** none

**Files:**
- Create: `rules/modes.md`
- Create: `tests/__init__.py` (empty)
- Test: `tests/test_modes_file.py`

**Interfaces:**
- Produces: `rules/modes.md`, first line `agent-shenanigans modes <16 lowercase hex>`; the token is read by Task 19's probe and by nothing else.

- [ ] **Step 1: Write the failing tests**

```python
MARKER = re.compile(r"^agent-shenanigans modes [0-9a-f]{16}$")

def test_marker_line_format():
    assert MARKER.match(first_line(REPO / "rules/modes.md"))

def test_token_unique_in_repo():
    token = first_line(REPO / "rules/modes.md").split()[-1]
    hits = [p for p in tracked_files() if token in p.read_text(errors="ignore")]
    assert hits == [REPO / "rules/modes.md"]

def test_required_rules_present():
    body = (REPO / "rules/modes.md").read_text()
    for s in ["ultracave", "ponytail", "`full`", "xhigh", "Fable", "Opus 5.5",
              "skills/ultracave/SKILL.md", "agents this repo starts"]:
        assert s in body
    assert body.rstrip().splitlines()[-1].startswith("- A headless run")
```

(`tracked_files()` = `git ls-files` under the repo root, as `Path`s; `first_line` reads line 1.)

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=lib python3 -m unittest tests.test_modes_file -v`
Expected: FAIL / ERROR, `rules/modes.md` missing.

- [ ] **Step 3: Create `rules/modes.md`**

Generate the token once with `python3 -c 'import secrets; print(secrets.token_hex(8))'`. Body, in this order (spec §3, exact rules):

```markdown
agent-shenanigans modes <token>

- In interactive sessions and in agents this repo starts: caveman at `ultracave` and ponytail at `full`, unless the user or the task prompt sets another level. Code, comments, commits, and docs stay normal English.
- On Grok, where these plugins' hooks do not run, an interactive session reads the caveman plugin's `skills/ultracave/SKILL.md` and the ponytail skill at `full` at session start (the path is in `grok inspect`).
- Effort `xhigh` for every agent this repo starts unless the user says a task is simple. Never use Fable. "Opus 5" means Opus 5.5.
- For agents this repo starts, if another skill or prompt names a weaker model or lower effort, this file wins unless the user says otherwise. It does not change the models other tools choose for their own agents.
- A headless run whose output a program parses (`claude -p`, `grok --prompt-file`, Plamen workers, debate seats) writes normal prose in its required format. This rule wins over every line above for those runs.
```

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=lib python3 -m unittest tests.test_modes_file -v`
Expected: 3 tests OK.

- [ ] **Step 5: Commit**

```bash
git add rules/modes.md tests/__init__.py tests/test_modes_file.py
git commit -m "feat: add shared modes file for both hosts"
```

---

## Phase 2: Debate panel

### Task 3: Panel file and seat primitives

**Subproject:** Seat runner
**Kind:** code
**Complexity:** high
**Depends on:** none

**Files:**
- Create: `skills/debate/panel.json`
- Create: `skills/debate/scripts/seats.py`
- Create: `tests/debate/__init__.py` (empty)
- Test: `tests/debate/test_seats.py`

**Interfaces:**
- Produces (`skills/debate/scripts/seats.py`; tests add that dir to `sys.path`):
  - `@dataclass(frozen=True) class Seat: name: str; persona: str; host: Literal["opus","grok"]; model: str; effort: str; timeout: int; system_prompt: str`
  - `class PanelError(Exception)`
  - `load_panel(path: Path) -> list[Seat]` — raises `PanelError` on a `fable` id, an effort other than `xhigh`, or a persona without both hosts.
  - `parse_verdict(text: str, timed_out: bool = False) -> Literal["APPROVED","REVISE"] | None`
  - `seat_argv(seat: Seat, prompt_file: Path, claude_bin: str, grok_bin: str) -> list[str]`
  - `seat_env(seat: Seat, base: dict[str, str]) -> dict[str, str]`
  - Constants `VERDICT_INSTRUCTION: str`, `PLAIN_PROSE_LINE: str`, `GROK_READ_TOOLS = "read_file,grep,list_dir"`, `CLAUDE_READ_TOOLS = "Read,Grep,Glob"`.
- `panel.json` shape: `{"seats": {"<persona>-<host>": {"persona", "host", "model", "effort", "timeout", "system_prompt"}}}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_panel_has_14_seats_7_personas_both_hosts():
    seats = load_panel(PANEL)
    assert len(seats) == 14
    by = collections.Counter(s.persona for s in seats)
    assert len(by) == 7 and set(by.values()) == {2}
    assert {s.model for s in seats} == {"claude-opus-5-5", "grok-4.7"}

def test_load_panel_rejects_fable_and_non_xhigh(): ...  # temp panel files -> PanelError each

def test_parse_verdict():
    assert parse_verdict("x\nVERDICT: APPROVED — Future Me can live with this") == "APPROVED"
    assert parse_verdict("**VERDICT:** REVISE") == "REVISE"
    assert parse_verdict("> verdict: approved") == "APPROVED"
    assert parse_verdict("I would say VERDICT: APPROVED if fixed.\nVERDICT: REVISE") == "REVISE"
    assert parse_verdict("VERDICT: REVISE\nlater\nVERDICT: APPROVED") == "APPROVED"
    assert parse_verdict("no verdict here") is None
    assert parse_verdict("VERDICT: APPROVED\ntrailing words", timed_out=True) is None

def test_instruction_does_not_parse():
    assert parse_verdict(VERDICT_INSTRUCTION) is None

def test_opus_argv_is_read_only_allowlist():
    a = seat_argv(opus_seat, Path("p.txt"), "claude", "/h/.grok/bin/grok")
    assert a[:2] == ["claude", "-p"]
    assert ["--model", "claude-opus-5-5"] == a[a.index("--model"):a.index("--model") + 2]
    for flag in ["--effort", "--tools", "--strict-mcp-config", "--settings"]:
        assert flag in a
    assert a[a.index("--tools") + 1] == "Read,Grep,Glob"
    assert json.loads(a[a.index("--settings") + 1]) == {"outputStyle": "default"}
    assert "--permission-mode" not in a

def test_grok_argv_is_read_only_allowlist():
    a = seat_argv(grok_seat, Path("p.txt"), "claude", "/h/.grok/bin/grok")
    assert a[0] == "/h/.grok/bin/grok"
    assert a[a.index("--tools") + 1] == "read_file,grep,list_dir"
    for flag in ["--prompt-file", "--no-subagents", "--disable-web-search", "--no-memory"]:
        assert flag in a
    assert not {"write", "search_replace", "run_terminal_cmd"} & set(",".join(a).split(","))

def test_opus_env_modes_off_and_nested_unset():
    env = seat_env(opus_seat, {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli", "PATH": "/b"})
    assert env["CAVEMAN_DEFAULT_MODE"] == "off" and env["PONYTAIL_DEFAULT_MODE"] == "off"
    assert "CLAUDECODE" not in env and "CLAUDE_CODE_ENTRYPOINT" not in env and env["PATH"] == "/b"
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=lib python3 -m unittest tests.debate.test_seats -v`
Expected: ERROR, `No module named 'seats'`.

- [ ] **Step 3: Create `panel.json` from the live config**

Run:
```bash
jq '{seats: (.reviewers | with_entries(.value = {persona: (.key | sub("-(opus|grok)$"; "")), host: .value.agent, model: .value.model, effort: .value.effort, timeout: .value.timeout, system_prompt: .value.system_prompt}))}' ~/.claude/debate-acpx.json > skills/debate/panel.json
```
Check: 14 seats; no key other than the six listed.

- [ ] **Step 4: Implement `seats.py`**

- `parse_verdict`: for each line, strip leading `*`, `_`, backticks, `#`, `>`, and spaces; also strip `*`/`_`/backticks around the colon; a line counts when it starts with `VERDICT:` (case-insensitive) and the next word is `APPROVED` or `REVISE`. Return the last counting line's word. With `timed_out=True`, return it only if that line is the last non-empty line.
- `VERDICT_INSTRUCTION`: "End your reply with one final line made of the word VERDICT in capitals, a colon, a space, and then either APPROVED or REVISE." (It must not itself parse.)
- `PLAIN_PROSE_LINE`: "Write plain prose. Do not use caveman or ponytail styles."
- Opus argv: `[claude_bin, "-p", "--model", m, "--effort", e, "--tools", CLAUDE_READ_TOOLS, "--strict-mcp-config", "--settings", '{"outputStyle":"default"}']`; the prompt goes on stdin (the runner handles that).
- Grok argv: `[grok_bin, "--prompt-file", str(prompt_file), "--output-format", "plain", "-m", m, "--reasoning-effort", e, "--tools", GROK_READ_TOOLS, "--no-subagents", "--disable-web-search", "--no-memory"]`.
- `seat_env`: copy `base`; for opus drop `CLAUDECODE` and `CLAUDE_CODE_ENTRYPOINT`; for both set `CAVEMAN_DEFAULT_MODE=off` and `PONYTAIL_DEFAULT_MODE=off`.

- [ ] **Step 5: Run to verify they pass**

Run: `PYTHONPATH=lib python3 -m unittest tests.debate.test_seats -v`
Expected: all OK.

- [ ] **Step 6: Commit**

```bash
git add skills/debate/panel.json skills/debate/scripts/seats.py tests/debate
git commit -m "feat(debate): add 14-seat panel and read-only seat commands"
```

### Task 4: Seat runner

**Subproject:** Seat runner
**Kind:** code
**Complexity:** high
**Depends on:** Task 3

**Files:**
- Create: `skills/debate/scripts/run_seats.py`
- Test: `tests/debate/test_run_seats.py`

**Interfaces:**
- Consumes: everything in Task 3.
- Produces, CLI:
  - `run_seats.py run --panel PANEL --work-dir W --plan PLAN [--seats a,b] [--stamp PATH]` — exit 0 when every requested seat returned, else 1. `--stamp` writes `{"host": "seat-dry-run", "passed": true, "written_at": <epoch>, "detail": "14/14"}` only when all 14 seats were requested and returned.
  - `run_seats.py probe --panel PANEL --work-dir W --out PATH` — writes the seat-probe result JSON, exit 0 on pass.
- Produces, files in `W`: `<seat>-output.md`, `<seat>-exit.txt`, `<seat>-argv.json`, `plan.sha256` (sha256 hex of the exact plan bytes), `summary.json` = `{"requested": int, "returned": int, "verdicts": {seat: "APPROVED"|"REVISE"|null}, "plan_sha256": str, "approved": bool}`.
- Produces: `run_seats.main(argv: list[str]) -> int`. Binaries come from `SEATS_CLAUDE_BIN` (default `claude`) and `SEATS_GROK_BIN` (default `~/.grok/bin/grok`, expanded).

- [ ] **Step 1: Write the failing tests**

Each test builds fake `claude`/`grok` scripts in a temp dir (bash, printing a canned reply chosen by an env var or a counter file) and points `SEATS_*_BIN` at them. Use a two-seat temp panel with `timeout: 2` unless the test needs 14.

```python
def test_run_writes_outputs_exit_argv_summary(): ...      # every file listed above exists; summary.approved is True when both reply APPROVED
def test_prompt_has_plain_prose_and_verdict_instruction(): ...  # fake bins echo their prompt; both lines present once
def test_uses_seat_prompt_file_when_present(): ...        # W/<seat>-prompt.txt replaces system_prompt+plan
def test_missing_seat_rerun_once(): ...                   # fake fails first call, succeeds second -> returned
def test_failing_cli_counts_not_returned(): ...           # fake exits 1 both times -> verdict null, returned 1/2, exit 1
def test_timeout_counts_not_returned(): ...               # fake sleeps 5 with timeout 2 -> killed, null
def test_timed_out_seat_with_final_verdict_counts(): ...  # fake prints verdict line then sleeps -> counted
def test_plan_hash_matches_bytes_sent(): ...
def test_subset_reports_requested_count(): ...            # --seats skeptic-opus -> requested 1
def test_stamp_only_on_full_return(): ...                 # --stamp written iff returned == requested == 14
def test_probe_passes_with_read_only_seats(): ...
def test_probe_fails_when_seat_lists_write_tool_or_writes(): ...
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=lib python3 -m unittest tests.debate.test_run_seats -v`
Expected: ERROR, no `run_seats`.

- [ ] **Step 3: Implement `run_seats.py`**

- One `subprocess.Popen` per seat (opus: prompt on stdin; grok: prompt file), `start_new_session=True`, cwd = `W`, env from `seat_env`; wait with the seat's timeout; on timeout kill the process group and mark `timed_out`. Exit file holds the return code, or `124` on timeout.
- Prompt = (`W/<seat>-prompt.txt` if present, else `system_prompt + "\n\n" + plan text`) + `"\n\n" + PLAIN_PROSE_LINE + "\n" + VERDICT_INSTRUCTION`.
- A seat is returned when `parse_verdict(output, timed_out)` is not None. Re-run each not-returned seat once, then write `summary.json`.
- `probe`: run one opus and one grok seat with the prompt "List the tools you can call, one per line. Then try to create a file named PROBE_WRITE in your working directory. Then end with the verdict line." Pass when both return, `W/PROBE_WRITE` does not exist, and no listed tool name contains `write`, `edit`, `replace`, `bash`, `terminal`, or `mcp` (case-insensitive). Write `{"host": "seats", "passed", "written_at", "detail"}` to `--out`.

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=lib python3 -m unittest tests.debate -v`
Expected: all OK.

- [ ] **Step 5: Commit**

```bash
git add skills/debate/scripts/run_seats.py tests/debate/test_run_seats.py
git commit -m "feat(debate): add parallel seat runner with plan hash and probe"
```

### Task 5: Debate skill for both hosts

**Subproject:** Debate skill
**Kind:** code
**Complexity:** medium
**Depends on:** Task 4

**Files:**
- Modify: `skills/debate/SKILL.md`
- Delete: `skills/debate/SKILL.workflow.md`
- Delete: `skills/debate/debate-acpx.example.json`
- Test: `tests/test_debate_skill.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_description_triggers():
    fm = frontmatter(SKILL)
    assert "/debate:all" not in fm["description"] and "run debate" not in fm["description"].lower()
    assert "debate the spec" in fm["description"]

def test_body_carries_the_round_rule():
    body = SKILL.read_text()
    for s in ["run_seats.py", "summary.json", "plan.sha256", "OWNER-ACCEPTED", "N/<requested>",
              "never changes a seat's or the round's verdict", "| Persona | Opus | Grok | Agree/split |",
              "run_in_background", "STRML", "cc-debate"]:
        assert s in body

def test_retired_files_gone():
    assert not (REPO / "skills/debate/SKILL.workflow.md").exists()
    assert not (REPO / "skills/debate/debate-acpx.example.json").exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=lib python3 -m unittest tests.test_debate_skill -v`
Expected: FAIL on the description and missing strings.

- [ ] **Step 3: Rewrite `SKILL.md` and remove the two files**

Description: "Use to review a design spec or implementation plan with the owner's 14-seat panel (seven personas, each on Opus 5.5 and Grok 4.7 at xhigh). Triggers: 'debate the spec', 'debate the plan', 'panel review', '/agent-shenanigans:debate'." Body sections, one host-neutral procedure (spec §6): setup a work dir under `.tmp/debate-<id>/` and write the plan; run `python3 "${CLAUDE_PLUGIN_ROOT:-<plugin dir>}/skills/debate/scripts/run_seats.py" run ... --stamp ~/.agent-shenanigans-probe/seat-dry-run.json` in the background (Claude: Bash `run_in_background`; Grok: background terminal) and wait for it; read every `<seat>-output.md` in full; synthesis lists plus the 7-row table; targeted exchange through `<seat>-prompt.txt` files (exchange never changes a seat's or the round's verdict); round rule from `summary.json` and `plan.sha256`; revision prompts; max 3 rounds; at the cap stop, report, and offer `OWNER-ACCEPTED`; cost and time line. Keep the credit line to STRML `cc-debate`. Then `git rm skills/debate/SKILL.workflow.md skills/debate/debate-acpx.example.json`.

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=lib python3 -m unittest tests.test_debate_skill -v`
Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add -A skills/debate tests/test_debate_skill.py
git commit -m "feat(debate): run the panel from the repo seat runner on both hosts"
```

---

## Phase 3: doctor

### Task 6: `stack.toml` and its loader

**Subproject:** Declaration
**Kind:** code
**Complexity:** medium
**Depends on:** none

**Files:**
- Create: `stack.toml`
- Create: `lib/doctor/__init__.py` (empty)
- Create: `lib/doctor/stack.py`
- Create: `tests/doctor/__init__.py` (empty)
- Test: `tests/doctor/test_stack.py`

**Interfaces:**
- Produces (`lib/doctor/stack.py`):
  - `class StackError(Exception)`
  - `@dataclass(frozen=True) class PluginDecl: name: str; source: str; claude_id: str | None; grok_name: str | None; claude_state: Literal["enabled","absent"] | None; grok_state: Literal["enabled","absent"] | None; pending_until: str | None`
  - `@dataclass(frozen=True) class LinkDecl: path: Path; target: Path` (path `~`-expanded; target absolute under the repo)
  - `@dataclass(frozen=True) class SettingDecl: file: Path; format: Literal["json","toml"]; table: str | None; key: str; value: str`
  - `@dataclass(frozen=True) class Stack: plugins: tuple[PluginDecl, ...]; links: tuple[LinkDecl, ...]; retire: tuple[Path, ...]; retire_after_probe: tuple[Path, ...]; gated: dict[Path, str]; settings: tuple[SettingDecl, ...]`
  - `load_stack(path: Path, repo_root: Path, env: Mapping[str, str]) -> Stack` — expands `~` and `$XDG_CONFIG_HOME` (default `~/.config`).

- [ ] **Step 1: Write the failing tests**

```python
def test_loads_repo_stack():
    s = load_stack(REPO / "stack.toml", REPO, {"HOME": "/h"})
    assert len(s.plugins) == 9 and len(s.links) == 2 and len(s.settings) == 5
    assert Path("/h/.grok/skills/model-policy") in s.retire_after_probe
    assert s.gated == {Path("/h/.claude/commands/code-cleanup.md"): "skills/code-cleanup/SKILL.md:## Hard exclusions"}

def test_xdg_config_home_respected():
    s = load_stack(REPO / "stack.toml", REPO, {"HOME": "/h", "XDG_CONFIG_HOME": "/x"})
    assert Path("/x/caveman/config.json") in {d.file for d in s.settings}

def test_rejects_unknown_state(): ...      # temp toml with claude_state = "disabled" -> StackError
def test_rejects_link_target_outside_repo(): ...
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=lib python3 -m unittest tests.doctor.test_stack -v`
Expected: ERROR, no module `doctor.stack`.

- [ ] **Step 3: Write `stack.toml`**

Exact entries (spec §1); `grok_name` is the plugin name `grok inspect` prints:

| name | claude_id | grok_name | claude_state | grok_state | pending_until |
|---|---|---|---|---|---|
| caveman | `caveman@caveman` | `caveman` | enabled | enabled | |
| ponytail | `ponytail@ponytail` | `ponytail` | enabled | enabled | |
| superpowers | `superpowers@claude-plugins-official` | `superpowers` | enabled | enabled | |
| superpowers-duplicate | `superpowers@superpowers-marketplace` | | absent | | |
| cc-codemaps | `cc-codemaps@cc-codemaps` | `cc-codemaps` | enabled | enabled | |
| agent-shenanigans | `agent-shenanigans@agent-shenanigans` | `agent-shenanigans` | enabled | enabled | |
| explanatory-output-style | `explanatory-output-style@claude-code-plugins` | `explanatory-output-style` | absent | absent | |
| explanatory-output-style-official | `explanatory-output-style@claude-plugins-official` | | absent | | |
| cc-debate | `debate@cc-debate` | `debate` | absent | absent | `seat-dry-run` |

Links: `~/.grok/workflows/adversarial-verification.rhai` → `workflows/adversarial-verification.rhai`; `~/.claude/rules/agent-shenanigans.md` → `rules/modes.md`.
Retire: `~/.grok/skills/` + `compound`, `session-learnings`, `parallel-orchestrate`, `code-cleanup.pre-fork-backup.md`, `code-cleanup`, `debate`; `~/.claude/skills/compound`, `~/.claude/skills/session-learnings`, `~/.claude/commands/init.md`. Retire after probe: `~/.grok/skills/model-policy`, `~/.grok/skills/debate-panel`. Gated: `~/.claude/commands/code-cleanup.md` = `"skills/code-cleanup/SKILL.md:## Hard exclusions"`.
Settings: caveman `defaultMode = "ultracave"` and ponytail `defaultMode = "full"` (json, `$XDG_CONFIG_HOME/<name>/config.json`); `~/.grok/config.toml` `[models] default = "grok-4.7"` and `[models] default_reasoning_effort = "xhigh"`; `~/.claude/settings.json` `effortLevel = "xhigh"`.
Use `[[plugin]]`, `[[link]]`, `[retire] paths / after_probe`, `[gated]`, `[[setting]]` tables.

- [ ] **Step 4: Implement `load_stack`**

`tomllib` parse; validate every state value and every link target resolves inside `repo_root`; raise `StackError` with the offending entry name.

- [ ] **Step 5: Run to verify they pass**

Run: `PYTHONPATH=lib python3 -m unittest tests.doctor.test_stack -v`
Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add stack.toml lib/doctor tests/doctor
git commit -m "feat(doctor): declare the stack and load it"
```

### Task 7: Host state readers

**Subproject:** Inspection
**Kind:** code
**Complexity:** high
**Depends on:** Task 6

**Files:**
- Create: `lib/doctor/hosts.py`
- Create: `tests/doctor/fixtures/grok_inspect.txt` (trimmed copy of a real `~/.grok/bin/grok inspect` run: the Skills, Agents and Plugins sections, 20–40 lines including `[claude]` and `[collides with …]` rows)
- Test: `tests/doctor/test_hosts.py`

**Interfaces:**
- Produces (`lib/doctor/hosts.py`):
  - `class InspectFormatError(Exception)`
  - `@dataclass(frozen=True) class PluginState: host: str; key: str; enabled: bool; sha: str | None; path: Path | None; via_claude: bool`
  - `@dataclass(frozen=True) class SkillEntry: name: str; source: str; via_claude: bool; collides_to: str | None` (`source` is `"user"`, `"bundled"`, or `"plugin: <name>"`)
  - `@dataclass(frozen=True) class UserEntry: path: Path; name: str; dead: bool`
  - `@dataclass(frozen=True) class HostState: host: Literal["claude","grok"]; plugins: dict[str, PluginState]; skills: tuple[SkillEntry, ...]; user_entries: tuple[UserEntry, ...]`
  - `read_claude(home: Path) -> HostState` — plugins keyed by install id; `sha` = `gitCommitSha` of the `installed_plugins.json` entry; `enabled` from `enabledPlugins` in `~/.claude/settings.json`; skills = names under each enabled plugin's `skills/` and `commands/`.
  - `parse_grok_inspect(text: str) -> tuple[list[SkillEntry], dict[str, bool]]` — skill rows, and plugin name → enabled.
  - `read_grok(home: Path, inspect_text: str) -> HostState` — plugins keyed by inspect name; `sha`: Git installs `git -C <path> rev-parse HEAD` (never `registry.json` `commit`); Local installs `local_install_sha(path, source_path)`; `[claude]` plugins take the Claude SHA from `installed_plugins.json`.
  - `local_install_sha(copy_dir: Path, source_dir: Path) -> str` — `"<source git HEAD>+<first 12 hex of sha256 over sorted relative paths and bytes of copy_dir>"`.
  - `user_entries(home: Path) -> list[UserEntry]` — `~/.claude/skills/*`, `~/.claude/commands/*.md`, `~/.grok/skills/*`; `dead` when the entry or its `SKILL.md` is a symlink to a missing path.
  - `run_grok_inspect(grok_bin: Path, cwd: Path) -> str` — runs `grok inspect` from `cwd` (the home dir, so project files don't leak in).

- [ ] **Step 1: Write the failing tests**

```python
def test_read_claude_uses_gitCommitSha(): ...             # temp home: installed_plugins.json entry -> sha matches field
def test_claude_enabled_from_settings(): ...
def test_parse_grok_inspect_skills_and_collisions():
    skills, plugins = parse_grok_inspect(FIXTURE.read_text())
    wp = [s for s in skills if s.name == "writing-plans"]
    assert ("user", "/user:writing-plans") in {(s.source, s.collides_to) for s in wp}
    assert plugins["explanatory-output-style"] is True
def test_parse_grok_inspect_rejects_unknown_layout():
    with self.assertRaises(InspectFormatError):
        parse_grok_inspect("Skills (2)\n  * foo  something new\n")
def test_grok_git_install_sha_uses_rev_parse_not_registry(): ...  # git init a temp repo; registry says another commit
def test_local_install_sha_combines_source_head_and_content_hash(): ...  # changing one byte in the copy changes the suffix
def test_user_entries_flags_dead_link(): ...
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=lib python3 -m unittest tests.doctor.test_hosts -v`
Expected: ERROR, no module `doctor.hosts`.

- [ ] **Step 3: Implement `hosts.py`**

Parse inspect by section header (`Skills (N)`, `Plugins (N)`); a row inside a known section that does not match `└ <name> <source> [tags]` raises `InspectFormatError`, and so does a missing `Skills` or `Plugins` section.

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=lib python3 -m unittest tests.doctor.test_hosts -v`
Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add lib/doctor/hosts.py tests/doctor/fixtures tests/doctor/test_hosts.py
git commit -m "feat(doctor): read plugin, skill and SHA state on both hosts"
```

### Task 8: Report, exit codes, read-only CLI

**Subproject:** Report
**Kind:** code
**Complexity:** medium
**Depends on:** Task 6, Task 7

**Files:**
- Create: `lib/doctor/probes.py`
- Create: `lib/doctor/report.py`
- Create: `lib/doctor/cli.py`
- Create: `doctor` (executable; inserts `<repo>/lib` into `sys.path`, `raise SystemExit(cli.main(sys.argv[1:]))`)
- Test: `tests/doctor/test_report.py`

**Interfaces:**
- Consumes: `Stack` (Task 6), `HostState`, `run_grok_inspect` (Task 7).
- Produces:
  - `probes.py`: `@dataclass(frozen=True) class ProbeResult: host: str; passed: bool; written_at: float; route: str | None; detail: str`; `read_probes(probe_dir: Path) -> dict[str, ProbeResult]` (files `claude.json`, `grok.json`, `seats.json`, `seat-dry-run.json`).
  - `report.py`: `@dataclass(frozen=True) class Finding: host: str; kind: str; name: str; detail: str; level: Literal["drift","info","error"]`; `build_report(stack, claude: HostState, grok: HostState, probes: dict[str, ProbeResult], verified: dict[str, str], checkout_head: str, home: Path, repo_root: Path) -> list[Finding]`; `exit_code(findings) -> int` (2 if any `error`, else 1 if any `drift`, else 0); `render(findings) -> str` grouped by host.
  - `cli.py`: `main(argv: list[str]) -> int` — no flags: build and print the report. Later tasks add `--fix`, `--rollback`, `--accept`, `--seat-probe`.
- Finding kinds (drift unless noted): `missing`, `wrong-state`, `host-sha-mismatch`, `updated-since-verified`, `checkout-drift`, `shadowed`, `retired-present`, `dead-link`, `setting-differs`, `link-missing`, `link-wrong`, `grok-daemon-route`, `generated-js`, `probe-missing`, `probe-failing`, `probe-stale`; info: `unmanaged`, `pending-retirement`, `auto-installed`; error: `could-not-check`.

- [ ] **Step 1: Write the failing tests**

```python
def test_clean_machine_exits_0(): ...            # synthetic states matching stack.toml, fresh passing probes -> []
def test_each_drift_kind_is_drift(): ...         # one synthetic deviation per kind -> that kind, level drift, exit 1
def test_unmanaged_is_info(): ...                # extra ~/.grok/skills/brandkit -> info, exit 0
def test_cc_debate_info_until_stamp_then_drift(): ...
def test_auto_installed_copy_same_sha_is_info(): ...
def test_checkout_drift_when_install_sha_differs_from_head(): ...
def test_generated_js_is_drift(): ...            # ~/.grok/workflows/adversarial-verification.js exists
def test_inspect_failure_exits_2(): ...          # cli with a fake grok bin printing garbage -> 2
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=lib python3 -m unittest tests.doctor.test_report -v`
Expected: ERROR.

- [ ] **Step 3: Implement `probes.py`, `report.py`, `cli.py`, `doctor`**

Shadowed = a Grok skill row with source `user` whose `collides_to` names a declared plugin's skill, or a Claude user entry named like a skill an enabled declared plugin ships. A setting's live value is read with `json`/`tomllib`. `verified` comes from `<repo>/verified.json` (`{}` when absent). `checkout_head` = `git -C <repo> rev-parse HEAD`. `doctor` reads `GROK_BIN` (default `~/.grok/bin/grok`) and `AGENT_SHENANIGANS_HOME` (default `$HOME`) so tests can redirect both.

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=lib python3 -m unittest tests.doctor -v` and `./doctor; echo $?`
Expected: tests OK; the live run prints a grouped report and exits 1.

- [ ] **Step 5: Commit**

```bash
git add doctor lib/doctor/probes.py lib/doctor/report.py lib/doctor/cli.py tests/doctor/test_report.py
git commit -m "feat(doctor): report drift with 0/1/2 exit codes"
```

### Task 9: In-place settings patches

**Subproject:** Fix
**Kind:** code
**Complexity:** high
**Depends on:** none

**Files:**
- Create: `lib/doctor/patch.py`
- Test: `tests/doctor/test_patch.py`

**Interfaces:**
- Produces (`lib/doctor/patch.py`):
  - `class PatchRefused(Exception)`
  - `atomic_write(path: Path, text: str) -> None` — temp file in the same directory, then `os.replace`.
  - `real_target(path: Path) -> Path` — the file a symlink points at (or `path`).
  - `patch_json_key(path: Path, key: str, value: str) -> bool` — True when changed; creates the file and parents with only `{key: value}` when absent; writes to `real_target(path)`.
  - `patch_toml_key(path: Path, table: str, key: str, value: str | list[str], create_table: bool = False, check: Callable[[dict], None] | None = None) -> bool` — line edit inside `[table]` only; inserts the key at the table's end when missing; `create_table` appends `[table]` when absent; re-parses with `tomllib` and calls `check`; on any failure raises `PatchRefused` and leaves the file unchanged.
  - `grok_config_check(before: dict) -> Callable[[dict], None]` — after-state must have `models.default == "grok-4.7"`, `models.default_reasoning_effort == "xhigh"`, `model["grok-4.7"].context_window == 500000`, and `ui.fork_secondary_model` equal to `before`'s.

- [ ] **Step 1: Write the failing tests**

```python
def test_json_patch_keeps_other_keys(): ...
def test_json_patch_creates_missing_file_and_parents(): ...
def test_json_patch_follows_symlink():
    real = tmp / "dotfiles/settings.json"; real.parent.mkdir(); real.write_text('{"a": 1}')
    link = tmp / "settings.json"; link.symlink_to(real)
    assert patch_json_key(link, "effortLevel", "xhigh")
    assert link.is_symlink() and json.loads(real.read_text()) == {"a": 1, "effortLevel": "xhigh"}
def test_toml_patch_only_touches_target_table(): ...   # same key under [other] unchanged
def test_toml_patch_inserts_missing_key(): ...
def test_toml_patch_keeps_comments_and_500k_window(): ...  # copy of a config.toml shaped like the owner's
def test_toml_patch_create_table_paths(): ...          # extra_rule_dirs = ["/r/rules"] appended under new [paths]
def test_toml_patch_refuses_when_check_fails(): ...    # bytes identical afterwards
def test_unparseable_file_raises_and_is_untouched(): ...
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=lib python3 -m unittest tests.doctor.test_patch -v`
Expected: ERROR.

- [ ] **Step 3: Implement `patch.py`**

TOML values render with `json.dumps` (strings and string arrays only). A table's span runs from its header to the next `[` header line.

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=lib python3 -m unittest tests.doctor.test_patch -v`
Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add lib/doctor/patch.py tests/doctor/test_patch.py
git commit -m "feat(doctor): patch single settings keys in place"
```

### Task 10: `--fix` and `--rollback`

**Subproject:** Fix
**Kind:** code
**Complexity:** high
**Depends on:** Task 8, Task 9

**Files:**
- Create: `lib/doctor/fix.py`
- Modify: `lib/doctor/cli.py`
- Delete: `grok/install.sh`
- Test: `tests/doctor/test_fix.py`

**Interfaces:**
- Consumes: `Stack`, `Finding`, `build_report` (Tasks 6, 8); `patch_json_key`, `patch_toml_key`, `grok_config_check` (Task 9); `read_probes` (Task 8).
- Produces (`lib/doctor/fix.py`):
  - `class LockHeld(Exception)`
  - `class RunFolder` — context manager `RunFolder(backup_root: Path, run_id: str)`; takes a non-blocking `fcntl.flock` on `backup_root/.lock` (raises `LockHeld`); `preimage(live: Path) -> Path`; `move_aside(live: Path) -> Path` (keeps the path relative to home); `record(action: str, live: Path, stored: Path | None) -> None` appends `action\tlive\tstored\tsha256-after` to `manifest.tsv`. Actions: `patched`, `created`, `linked`, `moved`, `moved-back`.
  - `apply_fix(stack, findings, home: Path, repo_root: Path, run: RunFolder, resolves: Callable[[str, str], bool]) -> list[str]` — performs §2's owned writes and returns the printed plugin commands in order: every `claude plugin uninstall <id>`, then installs, then enables, then `re-run ./doctor --fix`.
  - `resolves(host: str, name: str) -> bool` default: Grok re-runs `grok inspect` and checks the first row for `name` is not `user`; Claude checks no user skill or command named `name` remains and the declared plugin is enabled.
  - `rollback(backup_root: Path, run_id: str) -> list[str]` — returns skipped items.
- `cli.py`: `--fix` (run id = local time `%Y-%m-%dT%H%M%S`; `LockHeld` → exit 2), `--rollback RUN_ID`.

- [ ] **Step 1: Write the failing tests**

```python
def test_run_folder_records_preimage_and_manifest(): ...
def test_second_fix_while_locked():
    with RunFolder(root, "a"):
        with self.assertRaises(LockHeld):
            RunFolder(root, "b").__enter__()
def test_link_created_and_real_file_moved_first(): ...
def test_link_skipped_when_target_missing(): ...
def test_retire_moves_with_relative_path(): ...
def test_after_probe_retire_waits_for_both_spawn_probes(): ...
def test_gated_collision_waits_for_marker_in_repo_skill(): ...
def test_collision_moved_back_when_source_does_not_win(): ...
def test_collision_stays_moved_when_source_wins(): ...
def test_mode_config_created_when_absent(): ...
def test_extra_rule_dirs_set_when_grok_probe_lacks_token(): ...   # grok.json token_seen false -> [paths] extra_rule_dirs = ["<repo>/rules"], table created
def test_subagent_inheritance_off_when_probe_reports_model_rejected(): ...  # grok.json model_param_rejected true -> [features] subagent_model_inheritance = false
def test_plugin_commands_printed_in_order(): ...
def test_rollback_restores_patched_and_moves_created_aside(): ...
def test_rollback_never_writes_through_symlink(): ...
def test_rollback_skips_changed_file_and_continues(): ...
def test_nothing_is_ever_deleted(): ...   # every file present before fix+rollback exists afterwards, live or in the run folder
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=lib python3 -m unittest tests.doctor.test_fix -v`
Expected: ERROR.

- [ ] **Step 3: Implement `fix.py`, wire the CLI, remove `grok/install.sh`**

Gated entry: move only when the repo file named before `:` contains the text after it. Probe-driven settings (spec §1, §3): when `grok.json` has `token_seen: false`, patch `[paths] extra_rule_dirs = ["<repo>/rules"]` with `create_table=True`; when it has `model_param_rejected: true`, patch `[features] subagent_model_inheritance = false`. Before wiring the printed install commands, check their syntax with `claude plugin --help` and `~/.grok/bin/grok plugin --help`; agent-shenanigans installs from this checkout's path on both hosts. `after_probe` entries: move only when `claude.json` and `grok.json` probes both passed and `resolves("grok", "debate")` is true. Run `git rm grok/install.sh`.

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=lib python3 -m unittest tests.doctor -v`
Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add -A lib/doctor/fix.py lib/doctor/cli.py tests/doctor/test_fix.py grok/install.sh
git commit -m "feat(doctor): add --fix with run folders and --rollback"
```

### Task 11: Probe freshness, seat probe, `--accept`

**Subproject:** Probe
**Kind:** code
**Complexity:** medium
**Depends on:** Task 4, Task 8, Task 9

**Files:**
- Modify: `lib/doctor/probes.py`
- Modify: `lib/doctor/cli.py`
- Test: `tests/doctor/test_accept.py`

**Interfaces:**
- Consumes: `run_seats.py probe` (Task 4); `ProbeResult`, `read_probes` (Task 8); `HostState` (Task 7).
- Produces:
  - `probes.py`: `run_seat_probe(repo_root: Path, probe_dir: Path) -> ProbeResult` (runs `python3 skills/debate/scripts/run_seats.py probe --panel skills/debate/panel.json --work-dir <tmp> --out <probe_dir>/seats.json`); `is_stale(p: ProbeResult, last_sha_change: float) -> bool`; `accept(repo_root: Path, claude: HostState, grok: HostState, probes: dict[str, ProbeResult], checkout_head: str) -> list[str]` — returns refusal reasons; when empty, writes `verified.json` = `{plugin name: sha}`.
  - `cli.py`: `--seat-probe`, `--accept`.
- Last SHA change time = newest `lastUpdated` in `installed_plugins.json` and newest mtime of a loaded Grok plugin directory.

- [ ] **Step 1: Write the failing tests**

```python
def test_probe_stale_when_older_than_sha_change(): ...
def test_accept_refuses_when_hosts_differ(): ...
def test_accept_refuses_on_checkout_drift(): ...
def test_accept_refuses_missing_failing_or_stale_probe(): ...
def test_accept_writes_verified_json(): ...
def test_seat_probe_runs_runner(): ...      # SEATS_*_BIN fakes from Task 4 tests
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=lib python3 -m unittest tests.doctor.test_accept -v`
Expected: ERROR.

- [ ] **Step 3: Implement**

- [ ] **Step 4: Run to verify they pass**

Run: the full test command.
Expected: all OK.

- [ ] **Step 5: Commit**

```bash
git add lib/doctor/probes.py lib/doctor/cli.py tests/doctor/test_accept.py
git commit -m "feat(doctor): add seat probe and --accept"
```

---

## Phase 4: Implementation workflow

### Task 12: Workflow contract

**Subproject:** Contract
**Kind:** refactor
**Complexity:** high
**Depends on:** Task 1

**Files:**
- Create: `workflows/CONTRACT.md`
- Modify: `grok/workflows/adversarial-verification.rhai` → moved to `workflows/adversarial-verification.rhai` (content unchanged in this task)

**Interfaces:**
- Produces the agent port both executors implement and Tasks 14–18 rely on:
  - Executor args: `repo`, `test_cmd`, `lint_cmd?`, `plan_path`, `plan_hash`, `branch?`, `rules: {high_risk: [glob], test_globs: [glob]}`, `forbid: [glob]`, `review: bool`, `ponytail: "full"|"ultra"`, `run_nonce`, `tasks: [{id, title, files, tests, kind, kind_source, complexity}]` (from Task 13), `fixture?`.
  - Labels and outputs:
    - `plan` (read-only) → `{phases: [{name, subprojects: [{name, tasks: [{id, depends_on: [str], complexity, brief}]}]}]}`
    - `git` (execute) — prompt names one action and its parameters; output `GitReport` = `{ok: bool, error: str, head: str, tree: str, branch: str, default_branch: str, porcelain: str, untracked: [str], name_status: str, diff: str, last_message: str, base_is_ancestor: bool, state_json: str}`. `diff` is `git diff --no-renames <base>..HEAD`; over 200 000 characters the report sets `ok: false` with error `diff too large` (fails closed). Read-only agents get the diff in their prompt and have no shell. Actions: `snapshot(base)`, `checkout_branch(name)`, `read_state(plan_hash)`, `write_state(plan_hash, json)`, `teeth_revert(base, paths)`, `teeth_restore()`, `reset_keep(sha)`, `move_untracked_aside(since)`, `amend_trailer(trailer)`.
    - `test` (execute) → `{test_exit: int, lint_exit: int | null, tail: str}`
    - `implement` (all) → `{summary: str, issues: [str]}`
    - `skeptic` (read-only) → `{verdict: "pass"|"fail", evidence: str}`
    - `review` (read-only) → `{findings: [{file, issue, severity}]}`; `verify-finding` (read-only) → `{real: bool, evidence: str}`; `fix-review` (all) → `{summary: str}`
  - Fixture: `args.fixture = {outputs: {<label>: [output, ...]}, kill_after: <task id> | null}`. With a fixture present the executor never spawns: each `call(label, …)` returns that label's next output, and records `{label, model, effort}`.
  - Result: `{ok: bool, stage: "plan"|"preflight"|"task"|"review"|"done", task: str | null, summary: str, tasks: [{id, outcome: "pass"|"fail"|"done-before", attempts: int, teeth: "ran"|"skipped:<kind>", model: str}]}`.
  - Fixture case file (`workflows/fixture/cases/<name>.json`): `{name, args, fixture, expect: {ok, stage, task?, outcomes: {id: outcome}}}`.

- [ ] **Step 1: Move the Grok workflow**

Run: `mkdir -p workflows && git mv grok/workflows/adversarial-verification.rhai workflows/adversarial-verification.rhai`

- [ ] **Step 2: Write `workflows/CONTRACT.md`**

Sections, in order: inputs (above); plan input (spec §4 "Plan input", with the marker syntax `**Kind:**` / `**Complexity:**` and `Delete:` lines counting as `files`); run state and branch (spec §4, file `.git/agent-shenanigans/<plan-hash>.json` = `{plan_hash, run_start, tasks: {id: {pre: sha, receipt: sha | null}}}`); the agent port (labels, schemas, actions above, each action's exact git commands: `teeth_revert` uses `git diff --no-renames --name-status <base> HEAD`, checks out M/D paths from base, moves A paths to `.git/agent-shenanigans/aside/`; `teeth_restore` is `git restore --source=HEAD --staged --worktree -- :/` then empties the aside folder; `reset_keep` is `git reset --keep <sha>`); the per-step predicates (spec §4 steps 1–6 and Failures, written as checks on `GitReport` fields); models and modes (the full model ids; Grok effort set at launch); review stage; fixture format; the result object. Every predicate names the field it reads.

- [ ] **Step 3: Verify**

Run: `grep -c -E 'HEAD~1|reset --hard|git stash|resume_from' workflows/CONTRACT.md` → `0`, and the full test command → OK.

- [ ] **Step 4: Commit**

```bash
git add -A workflows grok
git commit -m "docs(workflows): write the shared executor contract"
```

### Task 13: Plan-file parser

**Subproject:** Entry
**Kind:** code
**Complexity:** medium
**Depends on:** Task 12

**Files:**
- Create: `skills/run-plan/scripts/parse_plan.py`
- Create: `tests/run_plan/__init__.py` (empty)
- Test: `tests/run_plan/test_parse_plan.py`

**Interfaces:**
- Produces (`skills/run-plan/scripts/parse_plan.py`):
  - `@dataclass(frozen=True) class PlanTask: id: str; title: str; files: tuple[str, ...]; tests: tuple[str, ...]; kind: Literal["code","refactor","docs","test"]; kind_source: Literal["marker","derived"]; complexity: Literal["low","medium","high"] | None`
  - `parse_plan(text: str) -> list[PlanTask]` — one task per `### Task N: <title>` outside code fences; `id = "N"`. Every backticked token on a `Create:`, `Modify:`, `Delete:`, or `Test:` line is a path; a token without `/` takes the directory of the line's first token.
  - `validate(tasks: list[PlanTask]) -> list[str]` — errors: duplicate id; `code` task with empty `files` or empty `tests`.
  - `plan_hash(data: bytes) -> str` — sha256 hex.
  - CLI: `parse_plan.py PLAN` prints `{"plan_hash", "tasks": [...], "errors": [...]}`; exit 1 when `errors` is non-empty.
- Docs path: ends in `.md`, `.rst`, `.txt`, `.adoc`, or starts with `docs/`.

- [ ] **Step 1: Write the failing tests**

```python
def test_strips_line_ranges():
    t = parse_plan("### Task 1: A\n**Files:**\n- Modify: `a.py:123-145`\n- Test: `t.py`\n")[0]
    assert t.files == ("a.py",) and t.tests == ("t.py",)
def test_delete_lines_count_as_files(): ...
def test_multiple_paths_on_one_line_inherit_directory():
    t = parse_plan("### Task 1: A\n- Create: `w/c/a.json`, `b.json`\n- Test: `t.py`\n")[0]
    assert t.files == ("w/c/a.json", "w/c/b.json")
def test_kind_marker_wins(): ...
def test_derived_docs_when_all_docs_paths(): ...
def test_derived_test_when_only_tests(): ...
def test_refactor_only_from_marker(): ...
def test_complexity_marker(): ...
def test_ignores_task_headings_inside_code_fences():
    text = "### Task 1: A\n**Files:**\n- Create: `a.py`\n- Test: `t.py`\n```markdown\n### Task 9: fake\n```\n"
    assert [t.id for t in parse_plan(text)] == ["1"]
def test_validate_rejects_code_without_tests_or_files(): ...
def test_parses_this_repo_plan():
    tasks = parse_plan((REPO / "docs/superpowers/plans/2026-10-19-control-copy.md").read_text())
    assert len(tasks) == 21 and validate(tasks) == []
    assert tasks[0].kind == "refactor" and tasks[0].kind_source == "marker"
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=lib python3 -m unittest tests.run_plan -v`
Expected: ERROR.

- [ ] **Step 3: Implement `parse_plan.py`**

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=lib python3 -m unittest tests.run_plan -v`
Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add skills/run-plan/scripts/parse_plan.py tests/run_plan
git commit -m "feat(run-plan): parse writing-plans files into executor tasks"
```

### Task 14: Claude executor — preflight, plan stage, run state

**Subproject:** Claude executor
**Kind:** code
**Complexity:** high
**Depends on:** Task 12

**Files:**
- Create: `workflows/adversarial-verification.js`
- Create: `workflows/fixture/harness.mjs`
- Create: `agents/reader.md` (Claude agent type for the `plan`, `skeptic`, `review`, and `verify-finding` labels: tools `Read, Grep, Glob` only)
- Create: `workflows/fixture/cases/cycle-rejected.json`, `default-branch-refused.json`, `explicit-default-branch-refused.json`, `complexity-floor.json`, `restart-no-receipt.json`, `restart-after-receipt.json`, `forged-trailer-not-done.json`
- Test: `tests/workflows/executor.test.mjs`

**Interfaces:**
- Consumes: the contract (Task 12).
- Produces:
  - `harness.mjs`: `export async function runCase(scriptPath: string, casePath: string): Promise<{result, calls: [{label, model, effort}]}>` — reads the script, replaces `export const meta` with `const meta`, runs the body as an async function with globals `agent`, `parallel`, `phase`, `log`, `args` (case `args` + `fixture`), `budget`; `agent` throws if called (fixture mode must not spawn).
  - In the script: `CLAUDE_MODELS = {low: "claude-haiku-5-5", medium: "claude-sonnet-5-5", high: "claude-opus-5-5"}`, `OTHER_MODEL = "claude-opus-5-5"`, `call(label, prompt, opts)` (the only place `agent()` is called; adds `model`, `effort: "xhigh"`, and `agentType: "agent-shenanigans:reader"` for read-only labels; rejects any model containing `fable`).
- Script meta: `name: "adversarial-verification"`, phases `Preflight`, `Plan`, `Tasks`, `Review`.

- [ ] **Step 1: Write the failing test runner and the seven cases**

```js
for (const file of readdirSync(CASES)) {
  test(file, async () => {
    const c = JSON.parse(readFileSync(join(CASES, file)));
    const { result, calls } = await runCase(SCRIPT, join(CASES, file));
    assert.equal(result.ok, c.expect.ok);
    assert.equal(result.stage, c.expect.stage);
    for (const [id, outcome] of Object.entries(c.expect.outcomes ?? {}))
      assert.equal(result.tasks.find(t => t.id === id)?.outcome, outcome);
    for (const k of calls) {
      assert.ok(/^claude-(haiku|sonnet|opus)-5-5$/.test(k.model), k.label);
      assert.equal(k.effort, "xhigh");
    }
  });
}
```

Cases: a fixed cyclic `plan` output → `stage: "plan"`, no `git` call after the snapshot; current branch = default and no `branch` → `stage: "preflight"`; `branch` equal to the default → `preflight`; a 4-file task rated `low` by the agent → its `implement` call uses `claude-sonnet-5-5`; restart with state lacking receipts → `reset_keep(run_start)`; restart with one receipt → that task `done-before`, `reset_keep(receipt)`; a commit with a `Task-Id` trailer but no receipt → not done.

- [ ] **Step 2: Run to verify they fail**

Run: `node --test tests/workflows/`
Expected: FAIL, script missing.

- [ ] **Step 3: Implement preflight, plan, and run-state handling**

Graph validation (unique ids, deps known, Kahn's order or a cycle error) and the complexity order (agent value, plan override, floor) are plain JS in the script. Tasks run in topological order; log parallel-eligible ids per wave. The task loop body is a stub that returns `fail` until Task 15.

- [ ] **Step 4: Run to verify they pass**

Run: `node --test tests/workflows/`
Expected: 7 cases pass.

- [ ] **Step 5: Commit**

```bash
git add workflows/adversarial-verification.js workflows/fixture tests/workflows
git commit -m "feat(workflows): add Claude executor preflight, plan and restart"
```

### Task 15: Claude executor — task loop

**Subproject:** Claude executor
**Kind:** code
**Complexity:** high
**Depends on:** Task 14

**Files:**
- Modify: `workflows/adversarial-verification.js`
- Create: `workflows/fixture/cases/add-file.json`, `delete-and-rename.json`, `docs-pass.json`, `docs-empty-commit-fails.json`, `test-kind.json`, `refactor-test-confirmed.json`, `refactor-test-weakened-fails.json`, `retry-passes.json`, `failed-restore-stops.json`, `forbid-path-fails.json`, `uncommitted-implement-fails.json`
- Test: `tests/workflows/executor.test.mjs` (runs the new cases unchanged)

**Interfaces:**
- Consumes: `call`, `CLAUDE_MODELS` (Task 14); contract steps 1–6 and Failures.

- [ ] **Step 1: Write the eleven failing cases**

Expected outcomes, one per case: added production file → pass, teeth `ran`; deletion plus rename → pass, `teeth_revert` receives both old paths; `docs` → pass, teeth `skipped:docs`; `docs` whose implementer leaves `head` equal to the pre-task SHA → fail at step 2; `test` → pass, `skipped:test`; `refactor` editing a test with skeptic `pass` → pass; same with skeptic `fail` → fail after retries; first gate `test_exit: 1` then `0` → pass, `attempts: 2`, second `implement` uses the next tier; `teeth_restore` report with `ok: false` → `ok: false`, `stage: "task"`, and no `reset_keep` call afterwards; diff naming a `forbid` path → fail; dirty `porcelain` after `implement` → attempt fails.

- [ ] **Step 2: Run to verify they fail**

Run: `node --test tests/workflows/`
Expected: the eleven new cases FAIL.

- [ ] **Step 3: Implement steps 1–6, failures, and the tier ladder**

Each step reads only `GitReport` / `test` fields and checks the predicate the contract names; a missing field fails closed. Retries: new `implement` call one tier up, prompt states the branch is back at the pre-task SHA; at most two retries; Opus retries at Opus.

- [ ] **Step 4: Run to verify they pass**

Run: `node --test tests/workflows/`
Expected: all 18 cases pass.

- [ ] **Step 5: Commit**

```bash
git add workflows tests/workflows
git commit -m "feat(workflows): add Claude executor task loop with teeth and retries"
```

### Task 16: Claude executor — review stage

**Subproject:** Claude executor
**Kind:** code
**Complexity:** medium
**Depends on:** Task 15

**Files:**
- Modify: `workflows/adversarial-verification.js`
- Create: `workflows/fixture/cases/review-clean.json`, `review-fix-test-path.json`, `review-fix-fails-stops.json`
- Test: `tests/workflows/executor.test.mjs`

- [ ] **Step 1: Write the three failing cases**

No confirmed finding → `stage: "done"`; a confirmed finding in a test path matching `rules.test_globs` → the fix task's `teeth_revert` call excludes that path; fix gate fails → `ok: false`, `stage: "review"`, `reset_keep(pre-fix SHA)` called.

- [ ] **Step 2: Run to verify they fail**

Run: `node --test tests/workflows/`
Expected: the three new cases FAIL.

- [ ] **Step 3: Implement the review stage**

Three `review` calls in one `parallel`, one `verify-finding` per finding (`real` with non-empty `evidence` confirms), fix scope derived in code from confirmed findings' paths split by `rules.test_globs`, then steps 1–6 as task `review-fix` outside the tier ladder.

- [ ] **Step 4: Run to verify they pass**

Run: `node --test tests/workflows/`
Expected: all 21 cases pass.

- [ ] **Step 5: Commit**

```bash
git add workflows tests/workflows
git commit -m "feat(workflows): add Claude executor review stage"
```

### Task 17: Grok executor — preflight, plan, task loop

**Subproject:** Grok executor
**Kind:** code
**Complexity:** high
**Depends on:** Task 12, Task 15

**Files:**
- Modify: `workflows/adversarial-verification.rhai`
- Test: `tests/workflows/test_rhai_static.py`

**Interfaces:**
- Consumes: the contract and the fixture cases from Tasks 14–15.
- Produces: `GROK_MODEL = "grok-4.7"`; a single call helper invoked method-style on a state map (`state.call(label, prompt, opts)`) so the fixture counter can advance; every `agent()` call goes through it.

- [ ] **Step 1: Write the failing static tests**

```python
def test_no_banned_constructs():
    src = RHAI.read_text()
    for s in ["HEAD~1", "resume_from", "reset --hard", "git stash"]:
        assert s not in src
def test_modes_say_ultracave(): assert "ultracave" in RHAI.read_text()
def test_agent_only_called_in_helper(): ...   # exactly one "agent(" occurrence, inside the helper
def test_helper_passes_grok_model(): ...       # the helper's opts map sets model: GROK_MODEL
def test_meta_is_first_statement_and_literal(): ...
def test_labels_match_contract(): ...          # every label string used is one of the contract's labels
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=lib python3 -m unittest tests.workflows.test_rhai_static -v` (add `tests/workflows/__init__.py`)
Expected: FAIL (`HEAD~1`, `resume_from` present).

- [ ] **Step 3: Rewrite the preflight, plan, run-state, and task loop to the contract**

Keep today's prompt texts where the contract agrees with them; replace teeth, gate, fix, and the `modes()` text. The Grok retry is one new `implement` call on the same model.

- [ ] **Step 4: Static tests pass, then the fixture on Grok**

Run: `PYTHONPATH=lib python3 -m unittest tests.workflows.test_rhai_static -v` → OK. Then in a Grok session, for each case in `workflows/fixture/cases/` from Tasks 14–15, call the `workflow` tool with `script_path` = the repo `.rhai`, `args` = the case's `args` plus `fixture`, `validate_only: true`. Expected: every result matches the case's `expect`.

- [ ] **Step 5: Commit**

```bash
git add workflows/adversarial-verification.rhai tests/workflows
git commit -m "feat(workflows): rewrite Grok executor task loop to the contract"
```

### Task 18: Grok executor — review stage and full fixture

**Subproject:** Grok executor
**Kind:** code
**Complexity:** high
**Depends on:** Task 16, Task 17

**Files:**
- Modify: `workflows/adversarial-verification.rhai`
- Test: `tests/workflows/test_rhai_static.py`

- [ ] **Step 1: Add the failing static test**

```python
def test_review_fix_goes_through_gate(): ...  # the review-fix path calls the same step function as tasks
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=lib python3 -m unittest tests.workflows.test_rhai_static -v`
Expected: FAIL.

- [ ] **Step 3: Implement the review stage to the contract**

- [ ] **Step 4: Verify**

Static tests OK; then in a Grok session run all 21 fixture cases with `validate_only: true` as in Task 17. Expected: every result matches `expect`, the same outcomes as `node --test tests/workflows/`.

- [ ] **Step 5: Commit**

```bash
git add workflows/adversarial-verification.rhai tests/workflows/test_rhai_static.py
git commit -m "feat(workflows): add Grok executor review stage"
```

### Task 19: `run-plan` entry skill and probe agent

**Subproject:** Entry
**Kind:** docs
**Complexity:** medium
**Depends on:** Task 2, Task 13, Task 16, Task 18

**Files:**
- Create: `skills/run-plan/SKILL.md`
- Create: `agents/probe.md`

**Interfaces:**
- Consumes: `parse_plan.py` CLI (Task 13); both executors; `rules/modes.md` token (Task 2).
- Produces: probe result file `~/.agent-shenanigans-probe/<claude|grok>.json` = `{host, passed, token_seen: bool, activation: str, requested: {model, effort}, recorded: {model, effort} | null, route: "shell"|"daemon"|null, model_param_rejected: bool, cwd, tool_calls: int, written_at}` (read by Tasks 8 and 10).

- [ ] **Step 1: Write `skills/run-plan/SKILL.md`**

Description triggers: "run the plan", "execute the implementation plan", "/agent-shenanigans:run-plan". Procedure (spec §4 "Entry point"): run `parse_plan.py` and stop on errors; show a table of task, kind, kind source, complexity; refuse a Fable session; Grok: refuse unless session effort is `xhigh` and the route is the shell route; state the expected agent count (about seven per task plus three reviewers and one verifier per finding); generate `run_nonce`; Claude: `Workflow({scriptPath: "<plugin root>/workflows/adversarial-verification.js", args})`; Grok: run the named workflow `adversarial-verification` with the same args and effort `xhigh`. Never resume a run; a restart is a new run. `--probe` mode: from a fresh temp directory outside the repo, spawn one agent of type `agent-shenanigans:probe` (Claude, Workflow `agent()` with `claude-opus-5-5`, `xhigh`) or a no-tools capability agent on `grok-4.7` (Grok) with a prompt that has no modes paste, token, path, or repo name, asking it to quote any line starting `agent-shenanigans modes` and any mode-activation text it received; the session reads the token from `rules/modes.md` itself and writes the probe JSON.

- [ ] **Step 2: Write `agents/probe.md`**

Frontmatter `name: probe`, a description saying it is for the run-plan probe only, and the narrowest tool setting the host accepts (no file, shell, search, or web tool). Body: "Answer from what is already in your context. Do not call any tool."

- [ ] **Step 3: Verify**

Run: `PYTHONPATH=lib python3 -m unittest tests.run_plan -v` → OK. In a Claude session in another repo: `/agent-shenanigans:run-plan --probe`; expected: `~/.agent-shenanigans-probe/claude.json` with `tool_calls: 0`. If the agent shows any tool, tighten `agents/probe.md` and repeat. In the same session spawn one Workflow `agent()` with `model: "claude-haiku-5-5", effort: "xhigh"`; if the host rejects that effort, change `CLAUDE_MODELS.low` in `workflows/adversarial-verification.js` to `claude-sonnet-5-5` and say so in the skill.

- [ ] **Step 4: Commit**

```bash
git add skills/run-plan/SKILL.md agents/probe.md
git commit -m "feat(run-plan): add entry skill and probe agent"
```

---

## Phase 5: code-cleanup

### Task 20: Port the safety rules and switch to tiered agents

**Subproject:** code-cleanup
**Kind:** code
**Complexity:** medium
**Depends on:** Task 19

**Files:**
- Modify: `skills/code-cleanup/SKILL.md`
- Modify: `skills/code-cleanup/references/cleanup-rules.md`
- Delete: `skills/code-cleanup/scripts/cc-fork`
- Test: `tests/test_code_cleanup_skill.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_safety_rules_ported():
    body = SKILL.read_text()
    for s in ["## Hard exclusions", "vendor/ third_party/", "**_pb2.py", "Never start on the default branch",
              "The boundary outranks the mandate", "Never weaken a guard", "Recovery is not a judgement call",
              "git submodule status --recursive"]:
        assert s in body
def test_no_cc_fork():
    assert "cc-fork" not in SKILL.read_text()
    assert not (REPO / "skills/code-cleanup/scripts/cc-fork").exists()
def test_spawn_rule():
    body = SKILL.read_text()
    for s in ["ultracave", "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "grok-4.7", 'effort: "xhigh"']:
        assert s in body
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=lib python3 -m unittest tests.test_code_cleanup_skill -v`
Expected: FAIL.

- [ ] **Step 3: Edit the skill**

- Port the owner's 49-line delta from `git -C ~/cc-skills diff commands/code-cleanup.md` (read-only): the "Hard exclusions" section (adapted to nine mandates), Phase 1 step 8's concrete path list and the new step 9 pre-flight, reconcile step's invariant scripts plus the `git status --short <excluded paths>` and submodule checks, and the three rules. Keep the repo override note.
- Replace the `cc-fork` fan-out with one Workflow `agent()` per mandate on Claude (explicit model per mandate, `effort: "xhigh"`, the recon and exclusion list pasted, the modes block first) and `spawn_subagent` on Grok (`model: "grok-4.7"` when the tool accepts it; check its schema in a Grok session and say so in the skill). Mandate tiers *(my call)*: autofix and ai-slop `claude-haiku-5-5`; cycles `claude-opus-5-5`; the rest `claude-sonnet-5-5`.
- Update **Modes** to `ultracave` and the full model ids; drop the Dependency block and the cc-fork fallback; keep dry-run default, worktrees, and Phase 3.
- Update the attribution note: adapted from STRML `cc-skills`; `cc-fork` is no longer used.
- `git rm skills/code-cleanup/scripts/cc-fork`.

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=lib python3 -m unittest tests.test_code_cleanup_skill -v`
Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add -A skills/code-cleanup tests/test_code_cleanup_skill.py
git commit -m "feat(code-cleanup): port safety rules and spawn tiered agents"
```

---

## Phase 6: Docs and release

### Task 21: Docs, manifests, stale references

**Subproject:** Docs
**Kind:** code
**Complexity:** medium
**Depends on:** Task 5, Task 11, Task 19, Task 20

**Files:**
- Modify: `WORKFLOW.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Test: `tests/test_docs_refs.py`

- [ ] **Step 1: Write the failing tests**

```python
STALE = ["cc-fork", "session-learnings", "skills/compound", "commands/init.md", "SKILL.workflow.md",
         "debate-acpx.example.json", "grok/install.sh", "grok/workflows/", "/debate:all"]
def test_no_stale_references():
    for p in [REPO / f for f in ["WORKFLOW.md", "README.md", "AGENTS.md"]] + list((REPO / "skills").rglob("*.md")):
        text = p.read_text()
        for s in STALE:
            assert s not in text, f"{p}: {s}"
def test_manifests_version_and_description():
    for f in ["plugin.json", "marketplace.json"]:
        data = (REPO / ".claude-plugin" / f).read_text()
        assert '"version": "0.2.0"' in data and "run-plan" in data and "compound" not in data
def test_workflow_names_the_loop():
    w = (REPO / "WORKFLOW.md").read_text()
    for s in ["./doctor", "superpowers:brainstorming", "superpowers:writing-plans", "run-plan", "/update-codemaps", "OWNER-ACCEPTED"]:
        assert s in w
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=lib python3 -m unittest tests.test_docs_refs -v`
Expected: FAIL.

- [ ] **Step 3: Rewrite the docs**

- `WORKFLOW.md`: install step `./doctor` then `./doctor --fix` for both hosts; the loop brainstorm → debate (repo skill, round rule, `OWNER-ACCEPTED`) → writing-plans → run-plan (phases, tiers, teeth) → `/code-cleanup` → `/update-codemaps`; check-in as the gate.
- `README.md`: skills table (check-in, code-cleanup, debate, run-plan, skill-postmortem); the `doctor` commands; credits by link only.
- `AGENTS.md`: layout gains `workflows/`, `rules/`, `lib/doctor/`, `agents/`, `stack.toml`, `doctor`, `verified.json`; drop the vendored paragraph; the bundled-script example names `skills/debate/scripts/run_seats.py`.
- Manifests: version `0.2.0`; descriptions list debate, run-plan, code-cleanup, check-in, skill-postmortem.

- [ ] **Step 4: Run to verify they pass**

Run: the full test command.
Expected: all OK.

- [ ] **Step 5: Commit**

```bash
git add WORKFLOW.md README.md AGENTS.md .claude-plugin tests/test_docs_refs.py
git commit -m "docs: describe the control-copy workflow and bump to 0.2.0"
```

---

## After the plan: day-one apply (owner runs these)

1. `./doctor` — expect exit 1 and the drift list.
2. `./doctor --fix` — patches settings, creates mode configs and links, retires names; run the printed `claude plugin` / `grok plugin` commands (uninstall the explanatory and duplicate superpowers installs; install agent-shenanigans from this checkout on both hosts).
3. `./doctor --fix` again (collision moves now pass their probes).
4. Probes: `/agent-shenanigans:run-plan --probe` in a Claude session and `/run-plan --probe` in a Grok session, each from a directory outside this repo; `./doctor --seat-probe`.
5. One full debate on any spec with the repo debate skill (writes the seat dry-run stamp); `./doctor --fix` (retires `model-policy` and `debate-panel`; prints the cc-debate uninstall).
6. `./doctor --accept`, then `./doctor` — expect exit 0.
