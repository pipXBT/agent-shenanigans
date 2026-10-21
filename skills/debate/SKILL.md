---
name: debate
description: "Use to review a design spec or implementation plan with the owner's 14-seat panel (seven personas, each on Opus 5.5 and Grok 4.7 at xhigh). Triggers: 'debate the spec', 'debate the plan', 'panel review', '/shenanigans:debate'."
---

# Debate: 14-seat panel review

Send a spec or plan to seven personas, each run twice (once on `claude-opus-5-5`, once on
`grok-4.7`, both `xhigh`), before any code is written. One mechanical round rule decides the
verdict. The same procedure and the same script run on Claude Code and Grok Build.

Seats are read-only by allowlist (Opus: `Read,Grep,Glob`; Grok: read tools only, no subagents,
no web search, no memory, no MCP). They can read files; they cannot change anything.

Needs `claude` on PATH and `~/.grok/bin/grok` installed and logged in. First time on a machine,
or after a CLI upgrade, run the probe once and fix anything it reports:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-<plugin dir>}/skills/debate/scripts/run_seats.py" probe \
  --panel "${CLAUDE_PLUGIN_ROOT:-<plugin dir>}/skills/debate/panel.json" \
  --work-dir .tmp/debate-probe --out ~/.agent-shenanigans-probe/seats.json
```

`<plugin dir>` is the plugin root: two directories above this `SKILL.md`. Claude sets
`CLAUDE_PLUGIN_ROOT`; on Grok use the directory this file was loaded from.

## 1. Set up

Make one folder per debate and one subfolder per round. Put the exact plan bytes in
`plan.md`; edit it only between rounds.

```bash
ID=$(date +%s | shasum | cut -c1-8)
DEBATE="$PWD/.tmp/debate-$ID"
mkdir -p "$DEBATE/round-1"
cp <spec-or-plan-file> "$DEBATE/plan.md"
```

Show the user the first 20 lines and `wc -w`.

## 2. Run the round

A round can take 30 minutes or more, past the foreground shell limit.

**Claude Code:** start one background job per seat yourself, from the main session: one Bash tool
call per seat with `run_in_background: true`, each in its own sub-run `<work_dir>/<seat>/`. Each
job notifies you when its seat finishes; do not poll. Do not hand seats to subagents or a
workflow: a subagent's background job is killed when the subagent ends its turn, long before a
seat finishes. The seat names are the keys of `panel.json`:

```bash
python3 -c 'import json, sys; print(" ".join(json.load(open(sys.argv[1]))["seats"]))' "${CLAUDE_PLUGIN_ROOT}/skills/debate/panel.json"
```

For each seat `<s>`, one call:

```bash
mkdir -p "$DEBATE/round-1/<s>" && python3 "${CLAUDE_PLUGIN_ROOT}/skills/debate/scripts/run_seats.py" run \
  --panel "${CLAUDE_PLUGIN_ROOT}/skills/debate/panel.json" --work-dir "$DEBATE/round-1/<s>" \
  --plan "$DEBATE/plan.md" --seats <s>
```

When every job has finished, merge the sub-runs into the round folder:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/debate/scripts/run_seats.py" collect \
  --work-dir "$DEBATE/round-1" --stamp ~/.agent-shenanigans-probe/seat-dry-run.json
```

The round rule reads the `summary.json` that `collect` writes. When the sub-runs saw different
plan bytes, `collect` sets `plan_hash_mismatch` and the round is not approved. To re-run a dead
seat, `rm -rf` its sub-run folder and start its job again on the same `plan.md`.

**Grok Build:** run the runner directly in a background terminal and wait for it to exit:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-<plugin dir>}/skills/debate/scripts/run_seats.py" run \
  --panel "${CLAUDE_PLUGIN_ROOT:-<plugin dir>}/skills/debate/panel.json" \
  --work-dir "$DEBATE/round-1" --plan "$DEBATE/plan.md" \
  --stamp ~/.agent-shenanigans-probe/seat-dry-run.json
```

To stop a round early, find the runner's `python3` processes (one per seat on Claude Code;
`ps -eo pid,args | grep '[r]un_seats.py'`, not the wrapping shell) and `kill <pid>` each. On
SIGINT or SIGTERM a runner kills every live seat's process group before it exits. Do not use
`kill -9` on a runner: it cannot clean up.

`--seats a,b` runs a subset (seat names such as `skeptic-opus,skeptic-grok`); on Claude Code,
start jobs for only those seats. A subset names whole personas, reports `N/<requested>`, and
never produces the final APPROVED. `--stamp` only writes when all 14 seats return, so it is safe
to pass every time.

Each seat runs in the caveman and ponytail modes `panel.json` gives its persona. Both seats of a
persona always share modes, so a split comes from reasoning, not style (`load_panel` rejects a
panel where they differ). The modes reach Opus through `CAVEMAN_DEFAULT_MODE` and
`PONYTAIL_DEFAULT_MODE`, and both models through lines in the prompt (Grok has no hooks):

| Persona | caveman | ponytail |
|---------|---------|----------|
| skeptic | ultracave | off |
| architect | ultracave | full |
| pragmatist | ultracave | ultra |
| bullshit-detector | ultracave | off |
| constraint-engineer | ultracave | off |
| pager-duty | ultracave | off |
| future-me | ultracave | ultra |

The runner appends those mode lines (or "Write plain prose." when a persona has both off) and a
final-`VERDICT:`-line instruction to every seat's prompt, re-runs seats that returned no verdict
once, and writes into the round folder. On Claude Code each seat's files are in its sub-run,
`<seat>/`, next to that sub-run's own `plan.sha256` and `summary.json`; `collect` writes the
round's `plan.sha256` and `summary.json`.

| File | Meaning |
|------|---------|
| `<seat>-output.md` | the seat's review |
| `<seat>-exit.txt` | exit code; `124` timed out, `127` binary not found |
| `<seat>-stderr.txt`, `<seat>-argv.json`, `<seat>-input.txt` | diagnostics |
| `plan.sha256` | sha256 of the exact plan bytes sent to the seats |
| `summary.json` | `requested`, `returned`, `verdicts` (per seat, `null` if not returned), `plan_sha256`, `approved` |

## 3. Read every review

Read every seat's output in full: `<seat>/<seat>-output.md` on Claude Code, `<seat>-output.md`
on Grok Build. No skimming, no sampling. A seat with exit code other than
`0` and no verdict is dead; read its `-stderr.txt` and say so rather than treating silence as consent.

## 4. Synthesize

Write three lists: unanimous points, unique points (one seat only), and contradictions. Then
this table with seven rows (Skeptic, Architect, Pragmatist, Bullshit Detector, Constraint
Engineer, Pager Duty, Future Me), taking verdicts from `summary.json`. Example row:

| Persona | Opus | Grok | Agree/split |
|---------|------|------|-------------|
| Skeptic | APPROVED | REVISE | split |

### Targeted exchange (optional)

For a contradiction that the plan text cannot settle, ask the two seats involved to answer each
other. Use a separate folder so the round record stays intact: `$DEBATE/round-1/exchange/`.
`mkdir -p` it and write `<seat>-prompt.txt` for each seat (`<seat>/<seat>-prompt.txt` on Claude
Code, where each sub-run reads its own). That file replaces the seat's whole
prompt (persona text and plan), so make it self-contained: the seat's `system_prompt` copied from
`panel.json`, the other seat's finding quoted, the plan path, and the question "does your
verdict still hold, and what exact text in the plan would change it?". Run the round as in
step 2 with that folder as the work dir, the same plan, and only the two seats (on Grok Build,
`run_seats.py run --seats <seat-a>,<seat-b>`).

The exchange only supplies text for the next revision; it never changes a seat's or the round's verdict.
Ignore the `VERDICT:` lines and the exchange's `summary.json`.

## 5. Apply the round rule

Read `round-N/summary.json`, and compute `shasum -a 256 "$DEBATE/plan.md" | cut -d' ' -f1` now.
The round is APPROVED only if all of these hold:

1. `returned` equals `requested`, and `requested` is all 14 seats (`approved` is `false` for any
   subset).
2. Every verdict is `APPROVED`.
3. The fresh hash equals the contents of `plan.sha256` (and `summary.json`'s `plan_sha256`).

Otherwise the round is REVISE:

- A persona whose Opus and Grok runs disagree makes the round REVISE; the REVISE side's
  findings go into the revision.
- A seat still missing after the runner's one re-run makes the round REVISE, reported as
  `N/<requested> returned` (for example `13/14 returned`).
- A hash mismatch, or `plan_hash_mismatch` in `summary.json`, means the seats never saw these
  bytes: say so and re-review. Never record
  APPROVED on unseen bytes.

## 6. Revise and repeat

Maximum 3 rounds. After a REVISE round:

1. Write `$DEBATE/revisions-round-N.md`: each finding addressed, and the plan edit that answers it.
2. Edit `plan.md` and make a new folder `$DEBATE/round-N+1`.
3. Run the whole panel again (a partial re-run cannot approve a round). For every seat that said
   REVISE, write `<seat>-prompt.txt` in the new folder (`<seat>/<seat>-prompt.txt` on Claude
   Code): its `system_prompt` from `panel.json`,
   its previous findings, the revision summary, and the revised plan pasted verbatim from
   `plan.md` (so the hash still matches what the seat saw). Other seats use the default prompt.

At the cap with any seat still REVISE, stop. Report the open items per seat, and offer the owner
`OWNER-ACCEPTED`: an explicit sign-off recorded with the open items listed. It is never
APPROVED, and it lets the next workflow step proceed. Do not record it without the owner's say-so.

## Cost and time

Tell the owner before starting. A full round is 14 xhigh reviews. Wall clock is bounded by the
slowest seat's timeout (Grok 1800 s, Opus 1200 s); a seat that has to be re-run can add up to
one more timeout. Three rounds is up to 42 reviews plus any targeted exchanges. Leave the
`.tmp/debate-<id>/` folder in place unless the owner says to delete it.

---

*Adapted from Sam Reed's ([STRML](https://github.com/STRML)) [`cc-debate`](https://github.com/STRML/cc-debate) plugin. This skill uses its own seat runner and panel file; upstream stays the canonical multi-vendor implementation.*
