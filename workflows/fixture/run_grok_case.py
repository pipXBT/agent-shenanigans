#!/usr/bin/env python3
"""Run one fixture case through the Grok executor (workflows/CONTRACT.md section 8).

Usage: run_grok_case.py CASE.json [--rhai PATH]

Headless ~/.grok/bin/grok calls its `workflow` tool once with validate_only: true,
which runs the script without spawning agents. The tool cuts a finished result
short, so the runner writes a temporary copy of the script with the case's args
(plus fixture) embedded and the final `complete(result);` turned into a throw;
the thrown JSON comes back whole in the error text. The tool call and its result
are read from Grok's session log, not from the model's reply.

Prints the result JSON, then PASS or FAIL against the case's expect: ok, stage,
task and level (when given), each outcome, and summary as a substring (when given).
Exit status: 0 PASS, 1 FAIL, 2 no result.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

GROK = Path.home() / ".grok/bin/grok"
SESSIONS = Path.home() / ".grok/sessions"
RHAI = Path(__file__).resolve().parents[1] / "adversarial-verification.rhai"
END = "complete(result);"


def embed(src, args):
    """The script with `args` set after the meta literal and the result thrown."""
    head, tail = src.split("\n};\n", 1)
    tail = tail.rstrip()
    if not tail.endswith(END):
        sys.exit(f"script does not end with {END}")
    lit = json.dumps(json.dumps(args, separators=(",", ":")))
    return f"{head}\n}};\n\nlet args = parse_json({lit});\n{tail[:-len(END)]}throw json_encode(result);\n"


def tool_call(sid):
    """The workflow tool's raw input and result message from the session log."""
    logs = list(SESSIONS.glob(f"*/{sid}/updates.jsonl"))
    call_in = text = None
    for line in logs[0].read_text().splitlines() if logs else []:
        u = json.loads(line).get("params", {}).get("update", {})
        if u.get("sessionUpdate") == "tool_call" and "rawInput" in u:
            call_in = u["rawInput"]
        if u.get("sessionUpdate") == "tool_call_update" and u.get("status") in ("completed", "failed"):
            text = (u.get("rawOutput") or {}).get("message")
    return call_in, text


def mismatches(r, exp):
    bad = [f"{k}={r.get(k)!r}, want {exp[k]!r}" for k in ("ok", "stage", "task", "level") if k in exp and r.get(k) != exp[k]]
    got = {t.get("id"): t.get("outcome") for t in r.get("tasks", [])}
    bad += [f"outcome[{i}]={got.get(i)!r}, want {o!r}" for i, o in exp.get("outcomes", {}).items() if got.get(i) != o]
    if "summary" in exp and exp["summary"] not in r.get("summary", ""):
        bad.append(f"summary lacks {exp['summary']!r}")
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("case", type=Path)
    ap.add_argument("--rhai", type=Path, default=RHAI)
    a = ap.parse_args()
    case = json.loads(a.case.read_text())
    args = dict(case["args"], fixture=case["fixture"])
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp).resolve()  # the script must sit inside the session's project
        script = work / "adversarial-verification.rhai"
        script.write_text(embed(a.rhai.read_text(), args))
        prompt = work / "prompt.txt"
        prompt.write_text(
            "Call your `workflow` tool exactly once with these parameters and nothing else: "
            f'validate_only: true, script_path: "{script}", and args set to {{}}. '
            "Do not edit any file and do not run any other tool. Then reply with the complete raw "
            "tool result verbatim (every field, including any error text), with no commentary.")
        sid = str(uuid.uuid4())
        p = subprocess.run([str(GROK), "-m", "grok-4.7", "--max-turns", "4", "--cwd", str(work), "-s", sid,
                            "--prompt-file", str(prompt)], capture_output=True, text=True, timeout=900)
        call_in, text = tool_call(sid)
    if call_in is None or text is None:
        print(f"NO TOOL CALL: {(p.stdout + p.stderr)[-500:]}")
        return 2
    if call_in.get("validate_only") is not True or call_in.get("source", {}).get("script_path") != str(script):
        print(f"WRONG TOOL CALL: {json.dumps(call_in)[:500]}")
        return 2
    m = re.search(r"Runtime error: (\{.*\}) \(line \d+", text, re.S)
    if not m:
        print(f"NO RESULT: {text[-500:]}")
        return 2
    r = json.loads(m.group(1))
    print(json.dumps(r, indent=1))
    bad = mismatches(r, case["expect"])
    print("PASS" if not bad else "FAIL: " + "; ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
