"""Probe results in ~/.agent-shenanigans-probe/: read them, run the seat probe, and gate `--accept` on them."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from doctor.hosts import HostState, loaded, loaded_shas
from doctor.patch import atomic_write
from doctor.stack import SELF, Stack

NAMES = ("claude", "grok", "seats", "seat-dry-run")


@dataclass(frozen=True)
class ProbeResult:
    host: str
    passed: bool
    written_at: float
    route: str | None
    detail: str
    shas: dict[str, str] = field(default_factory=dict)  # {plugin name: sha} loaded when the probe ran


def _load(f: Path) -> ProbeResult:
    d = json.loads(f.read_text())
    return ProbeResult(
        d.get("host", f.stem), bool(d["passed"]), float(d["written_at"]), d.get("route"), str(d.get("detail", "")),
        dict(d.get("shas", {})),
    )


def read_probes(probe_dir: Path) -> dict[str, ProbeResult]:
    """Results keyed by file stem; a missing file is simply absent. A malformed file raises."""
    return {n: _load(f) for n in NAMES if (f := probe_dir / f"{n}.json").exists()}


def is_stale(p: ProbeResult, current_shas: dict[str, str]) -> bool:
    """True when the probe ran against different SHAs: any plugin either side names that the other lacks or has differently."""
    return p.shas != current_shas


def run_seat_probe(repo_root: Path, probe_dir: Path, env: Mapping[str, str] | None = None) -> ProbeResult:
    """Run the seat runner's probe in a scratch directory and read back <probe_dir>/seats.json. Raises if it wrote nothing new."""
    out, started = probe_dir / "seats.json", time.time()
    script = repo_root / "skills/debate/scripts/run_seats.py"
    with tempfile.TemporaryDirectory() as work:
        done = subprocess.run(
            [sys.executable, str(script), "probe", "--panel", str(repo_root / "skills/debate/panel.json"),
             "--work-dir", work, "--out", str(out)],
            env=None if env is None else dict(env), capture_output=True, text=True,
        )
    # The runner exits 1 both for a failed probe and for a crash, so only a fresh result file counts.
    if not out.exists() or (result := _load(out)).written_at < started:
        raise RuntimeError(f"seat runner wrote no result (exit {done.returncode}): {done.stderr.strip()[-300:]}")
    return result


def accept(
    repo_root: Path,
    stack: Stack,
    claude: HostState,
    grok: HostState,
    probes: dict[str, ProbeResult],
    checkout_head: str | None,
) -> list[str]:
    """Reasons to refuse recording the loaded SHAs as verified. With none, writes them to <repo>/verified.json."""
    why = []
    for p, shas in loaded(stack, claude, grok):
        for host, state in (("claude", p.claude_state), ("grok", p.grok_state)):
            if state == "enabled" and host not in shas:
                why.append(f"{p.name} is not loaded on {host}")
        found = {host: sha for host, (_, sha) in shas.items()}
        if None in found.values():
            why.append(f"{p.name}: no SHA could be read")
            continue
        found = {host: sha.split("+")[0] for host, sha in found.items()}  # a Grok Local install's "+hash" is Grok-only
        if len(set(found.values())) > 1:
            why.append(f"{p.name}: hosts load different SHAs ({', '.join(f'{h} {s[:12]}' for h, s in found.items())})")
        if p.name == SELF:
            for host, sha in found.items():
                if sha != checkout_head:
                    why.append(f"{p.name} on {host} is {sha[:12]}, checkout HEAD is {(checkout_head or 'unknown')[:12]}")

    current = loaded_shas(stack, claude, grok)
    for name in ("claude", "grok", "seats"):
        probe = probes.get(name)
        if probe is None:
            why.append(f"probe {name} is missing")
        elif not probe.passed:
            why.append(f"probe {name} did not pass: {probe.detail or 'no detail'}")
        elif name != "seats" and is_stale(probe, current):  # the seat probe does not depend on plugin SHAs
            why.append(f"probe {name} is stale: it ran against different plugin SHAs")

    if not why:
        atomic_write(repo_root / "verified.json", json.dumps(current, indent=2, sort_keys=True) + "\n")
    return why
