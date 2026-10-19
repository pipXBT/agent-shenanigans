"""Read the probe results other tools leave in ~/.agent-shenanigans-probe/."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from doctor.hosts import HostState
from doctor.stack import Stack

NAMES = ("claude", "grok", "seats", "seat-dry-run")


@dataclass(frozen=True)
class ProbeResult:
    host: str
    passed: bool
    written_at: float
    route: str | None
    detail: str


def read_probes(probe_dir: Path) -> dict[str, ProbeResult]:
    """Results keyed by file stem; a missing file is simply absent. A malformed file raises."""
    found = {}
    for name in NAMES:
        f = probe_dir / f"{name}.json"
        if f.exists():
            d = json.loads(f.read_text())
            found[name] = ProbeResult(
                d.get("host", name), bool(d["passed"]), float(d["written_at"]), d.get("route"), str(d.get("detail", ""))
            )
    return found


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def last_sha_change(home: Path, stack: Stack, grok: HostState | None) -> float:
    """Newest time a declared-enabled plugin changed: Claude's `lastUpdated`, or a loaded Grok directory's mtime."""
    wanted = {p.claude_id for p in stack.plugins if p.claude_state == "enabled"}
    f = home / ".claude/plugins/installed_plugins.json"
    installed = json.loads(f.read_text()).get("plugins", {}) if f.exists() else {}
    times = [
        datetime.fromisoformat(e["lastUpdated"]).timestamp()
        for pid, entries in installed.items() if pid in wanted
        for e in entries if "lastUpdated" in e
    ]
    if grok:
        for p in stack.plugins:
            have = grok.plugins.get(p.grok_name) if p.grok_state == "enabled" else None
            if have and have.path and not have.via_claude:
                times.append(_mtime(have.path))
    return max(times, default=0.0)


def is_stale(p: ProbeResult, last_sha_change: float) -> bool:
    return p.written_at < last_sha_change

