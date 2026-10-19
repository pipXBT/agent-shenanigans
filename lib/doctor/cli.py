"""`./doctor`: read the declared stack and both hosts, print the drift, exit 0 / 1 / 2. `--fix`, `--rollback`, `--seat-probe` and `--accept` write."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Mapping

from doctor.fix import LockHeld, RunFolder, apply_fix, make_resolves, rollback
from doctor.hosts import _rev_parse, loaded_shas, read_claude, read_grok, run_grok_inspect
from doctor.probes import accept, read_probes, run_seat_probe
from doctor.report import Finding, build_report, cannot, exit_code, render
from doctor.stack import load_stack

REPO = Path(__file__).resolve().parents[2]


def _rollback(backup: Path, run_id: str) -> int:
    try:
        skipped = rollback(backup, run_id)
    except (LockHeld, FileNotFoundError) as e:
        print(f"doctor: {e}")
        return 2
    for s in skipped:
        print(f"skipped {s}")
    print(f"doctor: rolled back {run_id}" + (f", {len(skipped)} skipped" if skipped else ""))
    return 1 if skipped else 0


def main(argv: list[str], env: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="doctor", description="Report drift from stack.toml; --fix repairs what doctor owns.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fix", action="store_true", help="patch settings, link, move retired and shadowing copies aside; print plugin commands")
    mode.add_argument("--rollback", metavar="RUN_ID", help="undo one --fix run from ~/.agent-shenanigans-backup/RUN_ID")
    mode.add_argument("--shas", action="store_true", help="print the loaded plugin SHAs as JSON {plugin: sha}")
    mode.add_argument("--seat-probe", action="store_true", help="run the debate seat runner's probe and write seats.json")
    mode.add_argument("--accept", action="store_true", help="record the loaded SHAs in verified.json, if the hosts and probes agree")
    args = parser.parse_args(argv)
    env = os.environ if env is None else env
    home = Path(env.get("AGENT_SHENANIGANS_HOME") or env["HOME"])
    grok_bin = Path(env.get("GROK_BIN") or home / ".grok/bin/grok")
    backup = home / ".agent-shenanigans-backup"
    probe_dir = home / ".agent-shenanigans-probe"

    if args.rollback:
        return _rollback(backup, args.rollback)
    if args.seat_probe:
        try:
            result = run_seat_probe(REPO, probe_dir, env)
        except Exception as e:
            print(render([cannot("shared", "seat probe", e)]), end="")
            return 2
        print(f"doctor: seat probe {'passed' if result.passed else 'failed'}: {result.detail}")
        return 0 if result.passed else 1

    errors: list[Finding] = []

    def attempt(host: str, what: str, read, default=None):
        try:
            return read()
        except Exception as e:  # any reader failure is one could-not-check, never a traceback
            errors.append(cannot(host, what, e))
            return default

    stack = attempt("shared", "stack.toml", lambda: load_stack(REPO / "stack.toml", REPO, {**env, "HOME": str(home)}))
    if stack is None:
        print(render(errors), end="")
        return exit_code(errors)

    claude = attempt("claude", "claude plugin state", lambda: read_claude(home))
    grok = attempt("grok", f"{grok_bin} inspect", lambda: read_grok(home, run_grok_inspect(grok_bin, home)))
    if args.shas:
        if errors:
            print(render(errors), end="")
            return 2
        print(json.dumps(loaded_shas(stack, claude, grok), indent=2, sort_keys=True))
        return 0

    probes = attempt("shared", "probe results", lambda: read_probes(probe_dir), {})
    verified_file = REPO / "verified.json"
    verified = attempt(  # --accept overwrites verified.json, so a bad one must not stop it
        "shared", "verified.json",
        lambda: json.loads(verified_file.read_text()) if verified_file.exists() and not args.accept else {}, {},
    )
    head = attempt("shared", "git rev-parse HEAD", lambda: _rev_parse(REPO))

    if args.accept:
        if errors:
            print(render(errors), end="")
            return 2
        refusals = accept(REPO, stack, claude, grok, probes, head)
        for why in refusals:
            print(f"refused: {why}")
        print(f"doctor: {'refused to accept' if refusals else 'accepted; loaded SHAs written to verified.json'}")
        return 1 if refusals else 0

    findings = errors + build_report(stack, claude, grok, probes, verified, head, home, REPO)
    if not args.fix:
        print(render(findings), end="")
        return exit_code(findings)

    if errors:
        print(render(errors), end="")
    run_id = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    try:
        with RunFolder(backup, run_id) as run:
            commands = apply_fix(stack, findings, home, REPO, run, make_resolves(stack, home, grok_bin))
    except LockHeld as e:
        print(f"doctor: {e}")
        return 2
    manifest = backup / run_id / "manifest.tsv"
    print(manifest.read_text() if manifest.exists() else "doctor: nothing to change\n", end="")
    print(f"doctor: run {run_id}; undo with ./doctor --rollback {run_id}")
    if commands:
        print("\nRun these yourself, in order:")
        print("\n".join(f"  {c}" for c in commands))
    return 0
