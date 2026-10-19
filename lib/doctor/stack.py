"""Load stack.toml: the plugins, links, retired paths, and settings each host must have."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

STATES = ("enabled", "absent")
FORMATS = ("json", "toml")


class StackError(Exception):
    pass


@dataclass(frozen=True)
class PluginDecl:
    name: str
    source: str
    claude_id: str | None
    grok_name: str | None
    claude_state: Literal["enabled", "absent"] | None
    grok_state: Literal["enabled", "absent"] | None
    pending_until: str | None


@dataclass(frozen=True)
class LinkDecl:
    path: Path
    target: Path


@dataclass(frozen=True)
class SettingDecl:
    file: Path
    format: Literal["json", "toml"]
    table: str | None
    key: str
    value: str


@dataclass(frozen=True)
class Stack:
    plugins: tuple[PluginDecl, ...]
    links: tuple[LinkDecl, ...]
    retire: tuple[Path, ...]
    retire_after_probe: tuple[Path, ...]
    gated: dict[Path, str]
    settings: tuple[SettingDecl, ...]


def _need(entry: dict, key: str, label: str):
    if key not in entry:
        raise StackError(f"{label}: missing {key!r}")
    return entry[key]


def _choice(entry: dict, key: str, allowed: tuple[str, ...], label: str, required: bool = False):
    value = _need(entry, key, label) if required else entry.get(key)
    if value is not None and value not in allowed:
        raise StackError(f"{label}: {key} {value!r} not one of {allowed}")
    return value


def load_stack(path: Path, repo_root: Path, env: Mapping[str, str]) -> Stack:
    """Parse `path`. `~` and `$XDG_CONFIG_HOME` expand from `env` only, never the real environment."""
    home = env["HOME"]
    xdg = env.get("XDG_CONFIG_HOME") or f"{home}/.config"

    def expand(s: str) -> Path:
        if s == "~" or s.startswith("~/"):
            s = home + s[1:]
        return Path(s.replace("$XDG_CONFIG_HOME", xdg))

    try:
        data = tomllib.loads(Path(path).read_text())
    except tomllib.TOMLDecodeError as e:
        raise StackError(f"{path}: {e}") from e

    plugins = []
    for p in data.get("plugin", []):
        label = f"plugin {p.get('name', '?')}"
        plugins.append(PluginDecl(
            name=_need(p, "name", label),
            source=_need(p, "source", label),
            claude_id=p.get("claude_id"),
            grok_name=p.get("grok_name"),
            claude_state=_choice(p, "claude_state", STATES, label),
            grok_state=_choice(p, "grok_state", STATES, label),
            pending_until=p.get("pending_until"),
        ))

    root = repo_root.resolve()
    links = []
    for entry in data.get("link", []):
        label = f"link {entry.get('path', '?')}"
        target = (root / _need(entry, "target", label)).resolve()
        if not target.is_relative_to(root):
            raise StackError(f"{label}: target {entry['target']!r} is outside the repo")
        links.append(LinkDecl(expand(_need(entry, "path", label)), target))

    retire = data.get("retire", {})
    gated = {expand(k): v for k, v in data.get("gated", {}).items()}

    settings = []
    for s in data.get("setting", []):
        label = f"setting {s.get('file', '?')} {s.get('key', '?')}"
        settings.append(SettingDecl(
            file=expand(_need(s, "file", label)),
            format=_choice(s, "format", FORMATS, label, required=True),
            table=s.get("table"),
            key=_need(s, "key", label),
            value=_need(s, "value", label),
        ))

    return Stack(
        plugins=tuple(plugins),
        links=tuple(links),
        retire=tuple(expand(p) for p in retire.get("paths", [])),
        retire_after_probe=tuple(expand(p) for p in retire.get("after_probe", [])),
        gated=gated,
        settings=tuple(settings),
    )
