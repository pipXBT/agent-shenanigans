"""Compare what stack.toml declares with what the hosts report, one Finding per deviation."""
from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from doctor.hosts import HostState, PluginState
from doctor.probes import ProbeResult, is_stale, last_sha_change
from doctor.stack import PluginDecl, SettingDecl, Stack

SELF = "agent-shenanigans"
HOSTS = ("claude", "grok", "shared")
LEVELS = ("error", "drift", "info")


@dataclass(frozen=True)
class Finding:
    host: str
    kind: str
    name: str
    detail: str
    level: Literal["drift", "info", "error"]


def drift(host: str, kind: str, name: str, detail: str) -> Finding:
    return Finding(host, kind, name, detail, "drift")


def info(host: str, kind: str, name: str, detail: str) -> Finding:
    return Finding(host, kind, name, detail, "info")


def cannot(host: str, name: str, e: Exception) -> Finding:
    return Finding(host, "could-not-check", name, f"{type(e).__name__}: {e}", "error")


def plugin_of(source: str) -> str | None:
    return source.removeprefix("plugin: ") if source.startswith("plugin: ") else None


def host_of(path: Path, home: Path) -> str:
    return next((h for h in ("claude", "grok") if path.is_relative_to(home / f".{h}")), "shared")


def _declared(state: HostState | None, key: str | None, want: str | None) -> PluginState | None:
    """The plugin on a host when stack.toml wants it enabled there and it is."""
    have = state.plugins.get(key) if state and key and want == "enabled" else None
    return have if have and have.enabled else None


def _plugin_states(stack: Stack, claude: HostState | None, grok: HostState | None, probes) -> list[Finding]:
    out = []
    for p in stack.plugins:
        binding = p.pending_until is None or (p.pending_until in probes and probes[p.pending_until].passed)
        for host, state, key, want in (
            ("claude", claude, p.claude_id, p.claude_state),
            ("grok", grok, p.grok_name, p.grok_state),
        ):
            if state is None or not key:
                continue
            have = state.plugins.get(key)
            if want == "enabled":
                if have is None:
                    out.append(drift(host, "missing", key, "not installed"))
                elif not have.enabled:
                    out.append(drift(host, "wrong-state", key, "installed but disabled"))
            elif want == "absent" and have is not None:
                if not binding:
                    out.append(info(host, "pending-retirement", key, f"installed until {p.pending_until} passes"))
                else:
                    how = "loaded from the Claude install" if have.via_claude else "installed"
                    fix = f"; run: claude plugin uninstall {key}" if host == "claude" else ""
                    out.append(drift(host, "wrong-state", key, f"{how}, declared absent{fix}"))
    return out


def _grok_sha(p: PluginDecl, claude_copy: PluginState | None, grok_copy: PluginState, grok: HostState) -> str | None:
    """Grok loads some plugins from Claude's copy (skill rows tagged [claude]); for those, Claude's SHA is the one loaded."""
    via_claude = grok_copy.via_claude or any(
        s.via_claude and s.source == f"plugin: {p.grok_name}" for s in grok.skills
    )
    return claude_copy.sha if via_claude and claude_copy else grok_copy.sha


def _shas(stack: Stack, claude: HostState | None, grok: HostState | None, verified, checkout_head, auto) -> list[Finding]:
    out = []
    for p in stack.plugins:
        c = _declared(claude, p.claude_id, p.claude_state)
        g = _declared(grok, p.grok_name, p.grok_state)
        shas = {}
        if c:
            shas["claude"] = (p.claude_id, c.sha)
        if g:
            shas["grok"] = (p.grok_name, _grok_sha(p, c, g, grok))
        for host, (key, sha) in shas.items():
            if sha is None:
                out.append(cannot(host, key, ValueError("no SHA could be read")))
                continue
            if p.name in verified and verified[p.name] != sha:
                out.append(drift(host, "updated-since-verified", key, f"loaded {sha[:12]}, verified {verified[p.name][:12]}"))
            if p.name == SELF and checkout_head and sha.split("+")[0] != checkout_head:
                out.append(drift(host, "checkout-drift", key, f"installed {sha[:12]}, checkout HEAD {checkout_head[:12]}"))
        if len(shas) == 2 and all(sha for _, sha in shas.values()):
            (_, cs), (_, gs) = shas["claude"], shas["grok"]
            if cs.split("+")[0] != gs.split("+")[0]:  # a Local install's "+hash" suffix is Grok-only
                out.append(drift("shared", "host-sha-mismatch", p.name, f"claude {cs[:12]}, grok {gs[:12]}"))
            elif p.grok_name in auto:
                out.append(info("grok", "auto-installed", p.grok_name, "xAI Official copy; same SHA as Claude"))
    return out


def _shadowed(stack: Stack, claude: HostState | None, grok: HostState | None) -> list[Finding]:
    out = []
    if grok:
        wanted = {p.grok_name for p in stack.plugins if p.grok_state == "enabled"}
        shipped = {s.name: plugin_of(s.source) for s in grok.skills if plugin_of(s.source) in wanted}
        for s in grok.skills:
            if s.source == "user" and s.collides_to and s.name in shipped:
                out.append(drift("grok", "shadowed", s.name, f"user-level copy wins bare /{s.name} over plugin {shipped[s.name]}"))
    if claude:
        wanted = {p.claude_id.split("@")[0] for p in stack.plugins if p.claude_state == "enabled"}
        shipped = {s.name: plugin_of(s.source) for s in claude.skills if plugin_of(s.source) in wanted}
        for e in claude.user_entries:
            if e.name in shipped and not e.dead:
                out.append(drift("claude", "shadowed", e.name, f"{e.path} wins bare /{e.name} over plugin {shipped[e.name]}"))
    return out


def _gate_open(spec: str, repo_root: Path) -> bool:
    file, _, heading = spec.partition(":")
    try:
        return heading in (repo_root / file).read_text()
    except OSError:
        return False


def _paths(stack: Stack, claude: HostState | None, grok: HostState | None, probes, shadowed, home: Path, repo_root: Path) -> list[Finding]:
    out = []
    for link in stack.links:
        host = host_of(link.path, home)
        if not os.path.lexists(link.path):
            out.append(drift(host, "link-missing", str(link.path), f"should link to {link.target}"))
        elif os.path.realpath(link.path) != str(link.target):
            now = f"points at {os.readlink(link.path)}" if link.path.is_symlink() else "is a regular file"
            out.append(drift(host, "link-wrong", str(link.path), f"{now}, should link to {link.target}"))

    spawn_ok = all(k in probes and probes[k].passed for k in ("claude", "grok"))
    due = [(p, True) for p in stack.retire]
    due += [(p, spawn_ok) for p in stack.retire_after_probe]
    due += [(p, _gate_open(spec, repo_root)) for p, spec in stack.gated.items()]
    for path, now in due:
        if os.path.lexists(path):
            host = host_of(path, home)
            if now:
                out.append(drift(host, "retired-present", str(path), "retired name still at user level"))
            else:
                out.append(info(host, "pending-retirement", str(path), "retires once its condition holds"))

    retired = {p for p, _ in due}
    claimed = {(f.host, f.name) for f in shadowed}
    for state in (claude, grok):
        for e in state.user_entries if state else ():
            if e.path in retired or (state.host, e.name) in claimed:
                continue
            if e.dead:
                out.append(drift(state.host, "dead-link", str(e.path), "symlink target is missing"))
            else:
                out.append(info(state.host, "unmanaged", e.name, str(e.path)))
    return out


def _live_setting(d: SettingDecl):
    if not d.file.exists():
        return None
    data = json.loads(d.file.read_text()) if d.format == "json" else tomllib.loads(d.file.read_text())
    return (data.get(d.table, {}) if d.table else data).get(d.key)


def _settings(stack: Stack, home: Path) -> list[Finding]:
    out, unreadable = [], set()
    for d in stack.settings:
        host, name = host_of(d.file, home), f"{d.file} {d.table + '.' if d.table else ''}{d.key}"
        if d.file in unreadable:
            continue
        try:
            live = _live_setting(d)
        except (OSError, ValueError) as e:
            unreadable.add(d.file)
            out.append(cannot(host, str(d.file), e))
            continue
        if live != d.value:
            out.append(drift(host, "setting-differs", name, f"is {live!r}, want {d.value!r}"))
    return out


def _probes(stack: Stack, claude: HostState | None, grok: HostState | None, probes, home: Path) -> list[Finding]:
    out = []
    try:
        changed = last_sha_change(home, stack, grok) if claude else 0.0
    except (OSError, ValueError) as e:
        changed = 0.0
        out.append(cannot("claude", "installed_plugins.json lastUpdated", e))
    for name, host in (("claude", "claude"), ("grok", "grok"), ("seats", "shared")):
        p = probes.get(name)
        if p is None:
            out.append(drift(host, "probe-missing", name, f"no ~/.agent-shenanigans-probe/{name}.json"))
        elif not p.passed:
            out.append(drift(host, "probe-failing", name, p.detail or "probe did not pass"))
        elif name != "seats" and is_stale(p, changed):
            out.append(drift(host, "probe-stale", name, "a plugin changed after this probe ran"))
    if probes.get("grok") and probes["grok"].route == "daemon":
        out.append(drift("grok", "grok-daemon-route", "grok", "Grok is on the daemon route, which does not run .rhai workflows"))
    return out


def _auto_installed(home: Path) -> set[str]:
    """Grok plugins its own `official_marketplace_auto_installed` step put in place (xAI Official copies)."""
    cfg, reg = home / ".grok/config.toml", home / ".grok/installed-plugins/registry.json"
    try:
        if not tomllib.loads(cfg.read_text()).get("marketplace", {}).get("official_marketplace_auto_installed"):
            return set()
        repos = json.loads(reg.read_text()).get("repos", {}).values()
    except (OSError, ValueError):  # an unreadable file is already a could-not-check from the settings check or read_grok
        return set()
    return {n for r in repos if r.get("marketplace", {}).get("source_display_name") == "xAI Official" for n in r.get("plugins", {})}


def build_report(
    stack: Stack,
    claude: HostState | None,
    grok: HostState | None,
    probes: dict[str, ProbeResult],
    verified: dict[str, str],
    checkout_head: str | None,
    home: Path,
    repo_root: Path,
) -> list[Finding]:
    """A host that could not be read arrives as None; its checks are skipped (the caller reports why)."""
    out = []
    auto = _auto_installed(home)
    shadowed = _shadowed(stack, claude, grok)
    out += _plugin_states(stack, claude, grok, probes)
    out += _shas(stack, claude, grok, verified, checkout_head, auto)
    out += shadowed
    out += _paths(stack, claude, grok, probes, shadowed, home, repo_root)
    out += _settings(stack, home)
    out += _probes(stack, claude, grok, probes, home)
    if os.path.lexists(js := home / ".grok/workflows/adversarial-verification.js"):
        out.append(drift("grok", "generated-js", str(js), "generated file; Grok should run the linked .rhai workflow"))
    return out


def exit_code(findings: list[Finding]) -> int:
    levels = {f.level for f in findings}
    return 2 if "error" in levels else 1 if "drift" in levels else 0


def render(findings: list[Finding]) -> str:
    if not findings:
        return "doctor: clean\n"
    lines = []
    for host in HOSTS:
        group = sorted((f for f in findings if f.host == host), key=lambda f: LEVELS.index(f.level))
        if group:
            lines.append(host)
            lines += [f"  {f.level:<5} {f.kind:<22} {f.name}  {f.detail}" for f in group]
    counts = [f"{n} {lvl}" for lvl in LEVELS if (n := sum(f.level == lvl for f in findings))]
    return "\n".join(lines + ["", "doctor: " + ", ".join(counts)]) + "\n"
