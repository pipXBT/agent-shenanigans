"""Read the live state of each host: installed plugins, their SHAs, skills, and user-level entries."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from doctor.stack import PluginDecl, Stack

HEADER = re.compile(r" {0,2}([A-Z][A-Za-z ]*?)(?: \(.*\))?")
SKILL_ROW = re.compile(r"  └ (\S+) +(user|bundled|plugin: \S+)( \[claude\])?(?: \[collides with /\S+ → (\S+)\])?")
PLUGIN_ROW = re.compile(r"  └ (\S+) \(\w+, (enabled|disabled)\)(?: .*)?")


class InspectFormatError(Exception):
    pass


@dataclass(frozen=True)
class PluginState:
    host: str
    key: str
    enabled: bool
    sha: str | None
    path: Path | None
    via_claude: bool


@dataclass(frozen=True)
class SkillEntry:
    name: str
    source: str
    via_claude: bool
    collides_to: str | None


@dataclass(frozen=True)
class UserEntry:
    path: Path
    name: str
    dead: bool


@dataclass(frozen=True)
class HostState:
    host: Literal["claude", "grok"]
    plugins: dict[str, PluginState]
    skills: tuple[SkillEntry, ...]
    user_entries: tuple[UserEntry, ...]


def _json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _rev_parse(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def _dead(p: Path) -> bool:
    return p.is_symlink() and not p.exists()


def user_entries(home: Path) -> list[UserEntry]:
    found = []
    for pattern in (".claude/skills/*", ".claude/commands/*.md", ".grok/skills/*"):
        found += sorted(p for p in home.glob(pattern) if not p.name.startswith("."))
    return [
        UserEntry(p, p.stem if p.suffix == ".md" else p.name, _dead(p) or _dead(p / "SKILL.md"))
        for p in found
    ]


def _own(home: Path, host: str) -> tuple[UserEntry, ...]:
    return tuple(e for e in user_entries(home) if e.path.is_relative_to(home / f".{host}"))


def read_claude(home: Path) -> HostState:
    installed = _json(home / ".claude/plugins/installed_plugins.json").get("plugins", {})
    enabled = _json(home / ".claude/settings.json").get("enabledPlugins", {})
    plugins, skills = {}, []
    for pid, entries in installed.items():
        entry = next((e for e in entries if e.get("scope") == "user"), entries[0])
        path, on = Path(entry["installPath"]), bool(enabled.get(pid))
        plugins[pid] = PluginState("claude", pid, on, entry.get("gitCommitSha"), path, False)
        if on:
            names = [p.name for p in sorted(path.glob("skills/*")) if p.is_dir()]
            names += [p.stem for p in sorted(path.glob("commands/*.md"))]
            skills += [SkillEntry(n, f"plugin: {pid.split('@')[0]}", False, None) for n in names]
    return HostState("claude", plugins, tuple(skills), _own(home, "claude"))


def parse_grok_inspect(text: str) -> tuple[list[SkillEntry], dict[str, bool]]:
    skills, plugins, section, seen = [], {}, None, set()
    for line in text.splitlines():
        if not line.strip():
            continue
        if header := HEADER.fullmatch(line):
            section = header[1]
            seen.add(section)
        elif section == "Skills":
            if not (m := SKILL_ROW.fullmatch(line)):
                raise InspectFormatError(f"unrecognised Skills row: {line!r}")
            skills.append(SkillEntry(m[1], m[2], bool(m[3]), m[4]))
        elif section == "Plugins":
            if not (m := PLUGIN_ROW.fullmatch(line)):
                raise InspectFormatError(f"unrecognised Plugins row: {line!r}")
            plugins[m[1]] = m[2] == "enabled"
    if missing := {"Skills", "Plugins"} - seen:
        raise InspectFormatError(f"grok inspect printed no {' or '.join(sorted(missing))} section")
    return skills, plugins


def local_install_sha(copy_dir: Path, source_dir: Path) -> str:
    digest = hashlib.sha256()
    for rel, f in sorted((f.relative_to(copy_dir).as_posix(), f) for f in copy_dir.rglob("*") if f.is_file()):
        digest.update(rel.encode() + b"\0" + f.read_bytes() + b"\0")
    return f"{_rev_parse(source_dir)}+{digest.hexdigest()[:12]}"


def read_grok(home: Path, inspect_text: str) -> HostState:
    skills, enabled = parse_grok_inspect(inspect_text)
    repos = _json(home / ".grok/installed-plugins/registry.json").get("repos", {}).values()
    native = {name: repo for repo in repos for name in repo.get("plugins", {})}
    claude = read_claude(home).plugins
    plugins = {}
    for name, on in enabled.items():
        if repo := native.get(name):
            kind, path = repo["kind"], Path(repo["path"])
            try:  # never registry `commit`: it goes stale
                sha = _rev_parse(path) if kind["type"] == "Git" else local_install_sha(path, Path(kind["source_path"]))
            except (subprocess.CalledProcessError, OSError):
                sha = None
            plugins[name] = PluginState("grok", name, on, sha, path, False)
            continue
        # ponytail: one name installed from two Claude marketplaces is resolved by Claude's
        # enabled flag, then install order; read Grok's own choice if it ever exposes one.
        twins = [p for pid, p in claude.items() if pid.split("@")[0] == name]
        src = min(twins, key=lambda p: not p.enabled, default=None)
        plugins[name] = PluginState(
            "grok", name, on, src.sha if src else None, src.path if src else None, src is not None
        )
    return HostState("grok", plugins, tuple(skills), _own(home, "grok"))


def run_grok_inspect(grok_bin: Path, cwd: Path) -> str:
    return subprocess.run([str(grok_bin), "inspect"], cwd=cwd, capture_output=True, text=True, check=True).stdout


def _declared(state: HostState | None, key: str | None, want: str | None) -> PluginState | None:
    """The plugin on a host when stack.toml wants it enabled there and it is."""
    have = state.plugins.get(key) if state and key and want == "enabled" else None
    return have if have and have.enabled else None


def _grok_sha(p: PluginDecl, claude_copy: PluginState | None, grok_copy: PluginState, grok: HostState) -> str | None:
    """Grok loads some plugins from Claude's copy (skill rows tagged [claude]); for those, Claude's SHA is the one loaded."""
    via_claude = grok_copy.via_claude or any(
        s.via_claude and s.source == f"plugin: {p.grok_name}" for s in grok.skills
    )
    return claude_copy.sha if via_claude and claude_copy else grok_copy.sha


def loaded(stack: Stack, claude: HostState | None, grok: HostState | None):
    """Yield (plugin, {host: (key, sha)}) for each declared plugin, with the hosts that want it enabled and have it so."""
    for p in stack.plugins:
        c = _declared(claude, p.claude_id, p.claude_state)
        g = _declared(grok, p.grok_name, p.grok_state)
        shas = {}
        if c:
            shas["claude"] = (p.claude_id, c.sha)
        if g:
            shas["grok"] = (p.grok_name, _grok_sha(p, c, g, grok))
        yield p, shas


def loaded_shas(stack: Stack, claude: HostState | None, grok: HostState | None) -> dict[str, str]:
    """{plugin name: sha} of what is loaded now: Claude's when both hosts load it, minus a Grok Local install's "+hash"."""
    out = {}
    for p, shas in loaded(stack, claude, grok):
        if sha := next((s for _, s in shas.values() if s), None):
            out[p.name] = sha.split("+")[0]
    return out
