"""`./doctor --fix` and `--rollback`: write only what doctor owns, keep a pre-image of every change, never delete."""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import shutil
import tempfile
import tomllib
from pathlib import Path
from typing import Callable

from doctor.hosts import parse_grok_inspect, read_claude, run_grok_inspect, user_entries
from doctor.patch import PatchRefused, grok_config_check, patch_json_key, patch_toml_key, real_target
from doctor.probes import read_probes
from doctor.report import SELF, Finding, _gate_open, _live_setting, plugin_of
from doctor.stack import PluginDecl, SettingDecl, Stack

class LockHeld(Exception):
    pass


def _sha(p: Path, action: str) -> str:
    """What the run left at `p`: a link's target text for `linked`, else the file's bytes (through links); "-" for none."""
    if action == "linked":
        data = os.readlink(p).encode() if p.is_symlink() else None
    else:
        data = p.read_bytes() if p.is_file() else None
    return "-" if data is None else hashlib.sha256(data).hexdigest()


class RunFolder:
    """One --fix (or --rollback) run: holds the lock and stores pre-images and moved-aside files under its folder."""

    def __init__(self, backup_root: Path, run_id: str):
        self.root, self.dir = backup_root, backup_root / run_id
        self.home = backup_root.parent  # backups live at ~/.agent-shenanigans-backup

    def __enter__(self) -> RunFolder:
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = open(self.root / ".lock", "a")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._lock.close()
            raise LockHeld(f"{self.root / '.lock'} is held by another doctor run") from None
        self.dir.mkdir(exist_ok=True)
        return self

    def __exit__(self, *exc) -> None:
        self._lock.close()  # closing releases the flock

    def _slot(self, live: Path) -> Path:
        """A free path in the run folder for `live`, relative to home; repeats get `~1`, `~2`, ..."""
        rel = live.relative_to(self.home) if live.is_relative_to(self.home) else Path(*live.parts[1:])
        dest, n = self.dir / rel, 0
        while os.path.lexists(dest):
            n += 1
            dest = self.dir / f"{rel}~{n}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        return dest

    def preimage(self, live: Path) -> Path:
        dest = self._slot(live)
        shutil.copy2(live, dest)
        return dest

    def move_aside(self, live: Path) -> Path:
        dest = self._slot(live)
        os.rename(live, dest)  # renames a link itself, never what it points at
        return dest

    def record(self, action: str, live: Path, stored: Path | None) -> None:
        line = f"{action}\t{live}\t{stored or '-'}\t{_sha(live, action)}\n"
        with open(self.dir / "manifest.tsv", "a") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())


def _skip(path, why) -> None:
    print(f"skipped {path}: {why}")


def _move(run: RunFolder, path: Path) -> Path:
    stored = run.move_aside(path)
    run.record("moved", path, stored)
    return stored


def _grok_check(cfg: Path, pending: list[SettingDecl]) -> Callable[[dict], None]:
    """grok_config_check on the state this run ends in: the edited file plus the [table] keys still to come."""
    base = grok_config_check(tomllib.loads(cfg.read_text()))

    def check(after: dict) -> None:
        final = copy.deepcopy(after)
        for d in pending:  # ponytail: single-level tables only; dotted ones would need tomllib's table path
            final.setdefault(d.table, {})[d.key] = d.value
        base(final)

    return check


def _settings(stack: Stack, home: Path, repo_root: Path, run: RunFolder) -> None:
    cfg = home / ".grok/config.toml"
    try:
        probe = json.loads((home / ".agent-shenanigans-probe/grok.json").read_text())
    except (OSError, ValueError):
        probe = {}
    todo = list(stack.settings)
    if probe.get("token_seen") is False:  # Grok did not load the modes link: point it at the repo's rules/
        todo.append(SettingDecl(cfg, "toml", "paths", "extra_rule_dirs", [str(repo_root / "rules")]))
    if probe.get("model_param_rejected") is True:
        todo.append(SettingDecl(cfg, "toml", "features", "subagent_model_inheritance", False))
    for i, d in enumerate(todo):
        try:
            if _live_setting(d) == d.value:
                continue
            target = real_target(d.file)
            existed = target.exists()
            if d.format == "toml":
                check = _grok_check(d.file, [e for e in todo[i + 1:] if e.file == d.file]) if d.file == cfg else None
                stored = run.preimage(target) if existed else None
                changed = patch_toml_key(d.file, d.table, d.key, d.value, create_table=d.table == "paths", check=check)
            else:
                stored = run.preimage(target) if existed else None
                changed = patch_json_key(d.file, d.key, d.value)
            if changed:
                run.record("patched" if existed else "created", target, stored)
        except (PatchRefused, OSError, ValueError) as e:
            _skip(d.file, e)


def _links(stack: Stack, run: RunFolder) -> None:
    for link in stack.links:
        if os.path.realpath(link.path) == os.path.realpath(link.target):
            continue
        if not link.target.exists():
            _skip(link.path, f"link target {link.target} does not exist")
            continue
        if os.path.lexists(link.path):
            _move(run, link.path)
        link.path.parent.mkdir(parents=True, exist_ok=True)
        link.path.symlink_to(link.target)
        run.record("linked", link.path, None)


def _collide(run: RunFolder, paths: list[Path], name: str, hosts: list[str], resolves) -> None:
    """Move user copies aside; if the declared source does not then win bare /name on every host, move them back."""
    moved = [(p, _move(run, p)) for p in paths]
    if all(resolves(h, name) for h in hosts):
        return
    for p, stored in reversed(moved):
        if os.path.lexists(p):
            _skip(p, f"not moved back from {stored}: something new is there")
            continue
        os.rename(stored, p)
        run.record("moved-back", p, stored)
    _skip(", ".join(map(str, paths)), f"declared source does not win /{name} on {', '.join(hosts)}; moved back")


def _moves(stack: Stack, findings: list[Finding], home: Path, repo_root: Path, run: RunFolder, resolves) -> None:
    for p in stack.retire:
        if os.path.lexists(p):
            _move(run, p)

    waiting = [p for p in stack.retire_after_probe if os.path.lexists(p)]
    if waiting:
        try:
            probes = read_probes(home / ".agent-shenanigans-probe")
        except (OSError, ValueError, KeyError):
            probes = {}
        spawn_ok = all(k in probes and probes[k].passed for k in ("claude", "grok"))
        if spawn_ok and resolves("grok", "debate"):
            for p in waiting:
                _move(run, p)
        else:
            for p in waiting:
                _skip(p, "waits for passing claude and grok spawn probes and bare /debate resolving to the repo skill")

    for p, spec in stack.gated.items():
        if not os.path.lexists(p):
            continue
        if _gate_open(spec, repo_root):
            _collide(run, [p], p.stem if p.suffix == ".md" else p.name, ["claude", "grok"], resolves)
        else:
            _skip(p, f"waits for {spec}")

    managed = {*stack.retire, *stack.retire_after_probe, *stack.gated}
    shadowed: dict[str, set[str]] = {}
    for f in findings:
        if f.kind == "shadowed":
            shadowed.setdefault(f.name, set()).add(f.host)
    for name, hosts in shadowed.items():
        # Grok reads ~/.claude too; Claude never reads ~/.grok.
        paths = [
            e.path for e in user_entries(home)
            if e.name == name and e.path not in managed and ("grok" in hosts or e.path.is_relative_to(home / ".claude"))
        ]
        if not paths:
            continue
        if any(p.is_relative_to(home / ".claude") for p in paths):
            hosts = {"claude", "grok"}
        _collide(run, paths, name, sorted(hosts), resolves)


def _plugin_commands(stack: Stack, findings: list[Finding], home: Path, repo_root: Path) -> list[str]:
    grok = home / ".grok/bin/grok"
    decls: dict[tuple[str, str], PluginDecl] = {}
    for p in stack.plugins:
        if p.claude_id:
            decls["claude", p.claude_id] = p
        if p.grok_name:
            decls["grok", p.grok_name] = p
    uninstall, install, enable = [], [], []

    def install_cmd(host: str, p: PluginDecl) -> str:
        if host == "claude":
            return f"claude plugin install {p.name} --marketplace {repo_root}" if p.name == SELF else f"claude plugin install {p.claude_id}"
        return f"{grok} plugin install {repo_root if p.name == SELF else p.source}"

    for f in findings:
        p = decls.get((f.host, f.name))
        if p is None:
            continue
        want = p.claude_state if f.host == "claude" else p.grok_state
        if f.kind == "missing":
            install.append(install_cmd(f.host, p))
        elif f.kind == "wrong-state" and want == "enabled":
            enable.append(f"claude plugin enable {f.name}" if f.host == "claude" else f"{grok} plugin enable {f.name}")
        elif f.kind == "wrong-state" and want == "absent":
            if f.host == "claude" or (p.claude_id and "Claude install" in f.detail):  # Grok loads it from Claude's copy
                uninstall.append(f"claude plugin uninstall {p.claude_id}")
            else:
                uninstall.append(f"{grok} plugin uninstall {f.name}")
        elif f.kind == "checkout-drift" and p.name == SELF:  # reinstall from this checkout
            uninstall.append(f"claude plugin uninstall {f.name}" if f.host == "claude" else f"{grok} plugin uninstall {f.name}")
            install.append(install_cmd(f.host, p))
    commands = list(dict.fromkeys(uninstall + install + enable))
    return commands + ["re-run ./doctor --fix"] if commands else []


def apply_fix(
    stack: Stack,
    findings: list[Finding],
    home: Path,
    repo_root: Path,
    run: RunFolder,
    resolves: Callable[[str, str], bool],
) -> list[str]:
    """Do the writes doctor owns (each one a manifest line) and return the plugin commands for the owner to run."""
    _settings(stack, home, repo_root, run)
    _links(stack, run)
    _moves(stack, findings, home, repo_root, run, resolves)
    return _plugin_commands(stack, findings, home, repo_root)


def make_resolves(stack: Stack, home: Path, grok_bin: Path) -> Callable[[str, str], bool]:
    """Whether bare /name now resolves to a declared plugin. Any failure to tell counts as no."""
    wanted = {p.claude_id.split("@")[0] for p in stack.plugins if p.claude_id and p.claude_state == "enabled"}

    def resolves(host: str, name: str) -> bool:
        try:
            if host == "grok":
                skills, _ = parse_grok_inspect(run_grok_inspect(grok_bin, home))
                rows = [s for s in skills if s.name == name]
                return bool(rows) and rows[0].source != "user"
            claude = read_claude(home)
            return not any(e.name == name for e in claude.user_entries) and any(
                s.name == name and plugin_of(s.source) in wanted for s in claude.skills
            )
        except Exception:
            return False

    return resolves


def _restore(stored: Path, live: Path) -> None:
    fd, tmp = tempfile.mkstemp(dir=live.parent, prefix=f".{live.name}.")
    os.close(fd)
    shutil.copy2(stored, tmp)
    os.replace(tmp, live)


def _undo(run: RunFolder, action: str, live: Path, stored: Path | None, sha: str) -> str | None:
    """Undo one manifest line; return why it was skipped, or None."""
    if action == "moved":
        if os.path.lexists(live):
            return "something is at this path now"
        if stored is None or not os.path.lexists(stored):
            return f"{stored} is no longer in the run folder"
        live.parent.mkdir(parents=True, exist_ok=True)
        os.rename(stored, live)
        return None
    if _sha(live, action) != sha:
        return "changed since the run"
    if action == "patched":
        if live.is_symlink():  # never write through a link: set it aside, then restore the file
            run.move_aside(live)
        _restore(stored, live)
    else:  # created, linked
        run.move_aside(live)
    return None


def rollback(backup_root: Path, run_id: str) -> list[str]:
    """Undo a run's manifest in reverse. Returns the lines it skipped; the rest still proceed."""
    manifest = backup_root / run_id / "manifest.tsv"
    if "/" in run_id or run_id.startswith(".") or not manifest.is_file():
        raise FileNotFoundError(f"no run {run_id!r} under {backup_root}")
    skipped, moved_back = [], set()
    with RunFolder(backup_root, run_id) as run:
        for line in reversed(manifest.read_text().splitlines()):
            action, live, stored, sha = line.split("\t")
            live, stored = Path(live), None if stored == "-" else Path(stored)
            if action == "moved-back":  # cancels the move it reversed
                moved_back.add(live)
                continue
            if action == "moved" and live in moved_back:
                moved_back.discard(live)
                continue
            try:
                why = _undo(run, action, live, stored, sha)
            except OSError as e:
                why = str(e)
            if why:
                skipped.append(f"{action} {live}: {why}")
    return skipped
