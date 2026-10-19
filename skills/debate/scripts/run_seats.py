"""Run debate seats in parallel, record each seat's output, and summarise the round.

    run_seats.py run --panel PANEL --work-dir W --plan PLAN [--seats a,b] [--stamp PATH]
    run_seats.py probe --panel PANEL --work-dir W --out PATH
"""
import argparse
import contextlib
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from seats import PLAIN_PROSE_LINE, VERDICT_INSTRUCTION, Seat, load_panel, parse_verdict, seat_argv, seat_env

PROBE_PROMPT = ("List the tools you can call, one per line. Then try to create a file named PROBE_WRITE "
                "in your working directory. Then end with the verdict line.")
BANNED_TOOL_WORDS = ("write", "edit", "replace", "bash", "terminal", "mcp")
# A tool line: optional list marker, one name, then end of line or a description separator.
# ponytail: reads only the first name on a line (the probe asks for one per line).
TOOL_LINE_RE = re.compile(r"[\s>*•\d.)-]*[`*_]*([A-Za-z][\w.-]*)[`*_]*\s*(?:$|[:,(—–]|-\s)")
FULL_PANEL = 14
LIVE: list[subprocess.Popen] = []  # seats currently running, so an interrupt can stop them


def finish(head: str) -> str:
    return head + "\n\n" + PLAIN_PROSE_LINE + "\n" + VERDICT_INSTRUCTION


def kill_group(p: subprocess.Popen) -> None:
    # Kill the whole group so a hung CLI's children die with it.
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(p.pid, signal.SIGKILL)


def stop_seats(signum, frame) -> None:
    for p in LIVE:
        kill_group(p)
    sys.exit(128 + signum)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def run_once(seats: list[Seat], w: Path, prompts: dict[str, str]) -> dict[str, str | None]:
    claude_bin = os.environ.get("SEATS_CLAUDE_BIN", "claude")
    grok_bin = os.path.expanduser(os.environ.get("SEATS_GROK_BIN", "~/.grok/bin/grok"))
    procs, start = {}, time.monotonic()
    for s in seats:
        # Not <seat>-prompt.txt: that name is the caller's prompt override.
        prompt_file = w / f"{s.name}-input.txt"
        prompt_file.write_bytes(prompts[s.name].encode())
        argv = seat_argv(s, prompt_file, claude_bin, grok_bin)
        (w / f"{s.name}-argv.json").write_text(json.dumps(argv))
        with open(prompt_file, "rb") as stdin, open(w / f"{s.name}-output.md", "wb") as out, \
                open(w / f"{s.name}-stderr.txt", "wb") as err:
            try:
                # Opus takes the prompt on stdin: --tools is variadic, so no prompt argument may follow it.
                procs[s] = subprocess.Popen(argv, cwd=w, env=seat_env(s, os.environ), stdout=out, stderr=err,
                                            stdin=stdin if s.host == "opus" else subprocess.DEVNULL,
                                            start_new_session=True)
                LIVE.append(procs[s])
            except OSError as e:
                err.write(f"{e}\n".encode())
                procs[s] = None
    verdicts = {}
    for s, p in procs.items():
        timed_out, code = False, 127
        if p is not None:
            try:
                code = p.wait(max(0, start + s.timeout - time.monotonic()))
            except subprocess.TimeoutExpired:
                kill_group(p)
                p.wait()
                timed_out, code = True, 124
            LIVE.remove(p)
        (w / f"{s.name}-exit.txt").write_text(str(code))
        output = (w / f"{s.name}-output.md").read_bytes().decode(errors="replace")
        verdicts[s.name] = parse_verdict(output, timed_out)
    return verdicts


def run_with_retry(seats: list[Seat], w: Path, prompts: dict[str, str]) -> dict[str, str | None]:
    verdicts = run_once(seats, w, prompts)
    verdicts.update(run_once([s for s in seats if verdicts[s.name] is None], w, prompts))
    return verdicts


def run(panel: list[Seat], seats: list[Seat], w: Path, plan: Path, stamp: Path | None) -> int:
    plan_bytes = plan.read_bytes()
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    (w / "plan.sha256").write_text(plan_sha)
    prompts = {}
    for s in seats:
        custom = w / f"{s.name}-prompt.txt"
        head = custom.read_text(encoding="utf-8") if custom.exists() else s.system_prompt + "\n\n" + plan_bytes.decode()
        prompts[s.name] = finish(head)
    verdicts = run_with_retry(seats, w, prompts)
    returned = sum(v is not None for v in verdicts.values())
    write_json(w / "summary.json", {
        "requested": len(seats), "returned": returned, "verdicts": verdicts, "plan_sha256": plan_sha,
        # A subset never approves the round.
        "approved": returned == len(seats) == len(panel) and all(v == "APPROVED" for v in verdicts.values())})
    if stamp and returned == len(seats) == FULL_PANEL:
        write_json(stamp, {"host": "seat-dry-run", "passed": True, "written_at": time.time(),
                           "detail": f"{FULL_PANEL}/{FULL_PANEL}"})
    return 0 if returned == len(seats) else 1


def probe(panel: list[Seat], w: Path, out: Path) -> int:
    seats = [next(s for s in panel if s.host == host) for host in ("opus", "grok")]
    verdicts = run_with_retry(seats, w, {s.name: finish(PROBE_PROMPT) for s in seats})
    problems = [f"{name} did not return" for name, v in verdicts.items() if v is None]
    for s in seats:
        output = (w / f"{s.name}-output.md").read_bytes().decode(errors="replace")
        text = re.sub("probe_write", "", output, flags=re.I)  # the file name itself is not a tool
        for m in filter(None, map(TOOL_LINE_RE.match, text.splitlines())):
            if any(word in m.group(1).lower() for word in BANNED_TOOL_WORDS):
                problems.append(f"{s.name} lists {m.group(1)}")
    if (w / "PROBE_WRITE").exists():
        problems.append("PROBE_WRITE was created")
    write_json(out, {"host": "seats", "passed": not problems, "written_at": time.time(),
                     "detail": "; ".join(problems) or "2/2 returned, read-only"})
    return 1 if problems else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="run_seats.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run_ap, probe_ap = sub.add_parser("run"), sub.add_parser("probe")
    path = lambda s: Path(s).expanduser()  # noqa: E731
    for p in (run_ap, probe_ap):
        p.add_argument("--panel", required=True, type=path)
        p.add_argument("--work-dir", required=True, type=path)
    run_ap.add_argument("--plan", required=True, type=path)
    run_ap.add_argument("--seats", help="comma-separated seat names (default: the whole panel)")
    run_ap.add_argument("--stamp", type=path)
    probe_ap.add_argument("--out", required=True, type=path)
    args = ap.parse_args(argv)

    panel = load_panel(args.panel)
    w = args.work_dir.resolve()
    w.mkdir(parents=True, exist_ok=True)
    if args.cmd == "probe":
        return probe(panel, w, args.out)
    seats = panel
    if args.seats:
        names = args.seats.split(",")
        unknown = set(names) - {s.name for s in panel}
        if unknown:
            ap.error(f"unknown seat(s): {', '.join(sorted(unknown))}")
        seats = [s for s in panel if s.name in names]
    return run(panel, seats, w, args.plan, args.stamp)


if __name__ == "__main__":
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop_seats)
    sys.exit(main(sys.argv[1:]))
