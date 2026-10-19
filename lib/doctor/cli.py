"""`./doctor`: read the declared stack and both hosts, print the drift, exit 0 / 1 / 2."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Mapping

from doctor.hosts import _rev_parse, read_claude, read_grok, run_grok_inspect
from doctor.probes import read_probes
from doctor.report import Finding, build_report, cannot, exit_code, render
from doctor.stack import load_stack

REPO = Path(__file__).resolve().parents[2]


def main(argv: list[str], env: Mapping[str, str] | None = None) -> int:
    argparse.ArgumentParser(prog="doctor", description="Read-only report of drift from stack.toml.").parse_args(argv)
    env = os.environ if env is None else env
    home = Path(env.get("AGENT_SHENANIGANS_HOME") or env["HOME"])
    grok_bin = Path(env.get("GROK_BIN") or home / ".grok/bin/grok")

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
    probes = attempt("shared", "probe results", lambda: read_probes(home / ".agent-shenanigans-probe"), {})
    verified_file = REPO / "verified.json"
    verified = attempt(
        "shared", "verified.json", lambda: json.loads(verified_file.read_text()) if verified_file.exists() else {}, {}
    )
    head = attempt("shared", "git rev-parse HEAD", lambda: _rev_parse(REPO))

    findings = errors + build_report(stack, claude, grok, probes, verified, head, home, REPO)
    print(render(findings), end="")
    return exit_code(findings)
