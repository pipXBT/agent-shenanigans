"""Change exactly one settings key in a JSON or TOML file, leaving everything else alone."""
from __future__ import annotations

import contextlib
import copy
import json
import os
import re
import stat
import tempfile
import tomllib
from pathlib import Path
from typing import Callable


class PatchRefused(Exception):
    pass


def atomic_write(path: Path, text: str) -> None:
    """Write `text` to a temp file beside `path`, then rename it over `path`, keeping its mode."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def real_target(path: Path) -> Path:
    return path.resolve() if path.is_symlink() else path


def patch_json_key(path: Path, key: str, value: str) -> bool:
    target = real_target(path)
    try:
        if target.exists():
            data = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise PatchRefused(f"{target}: top level is not an object")
            if data.get(key) == value:
                return False
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            data = {}
        data[key] = value
        # Re-serialising normalises the file's whitespace; key order and values are kept.
        atomic_write(target, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        return True
    except PatchRefused:
        raise
    except Exception as e:
        raise PatchRefused(f"{target}: {e}") from e


def _parses(text: str) -> bool:
    try:
        tomllib.loads(text)
        return True
    except tomllib.TOMLDecodeError:
        return False


def _is_header(line: str, header: str) -> bool:
    s = line.strip()
    return s == header or (s.startswith(header) and s[len(header):].lstrip().startswith("#"))


def _replace_value(lines: list[str], k: int, end: int, new: str) -> None:
    """Replace the key/value starting at line `k` (possibly multi-line) with `new`, keeping a trailing comment."""
    j = k + 1
    while j < end and not _parses("".join(lines[k:j])):
        j += 1
    old = "".join(lines[k:j])
    body = old.rstrip("\r\n")
    rest = body.split("=", 1)[1]
    comment = next(
        (rest[len(rest[:p].rstrip()):] for p, c in enumerate(rest) if c == "#" and _parses("k =" + rest[:p])),
        "",
    )
    indent = old[: len(old) - len(old.lstrip())]
    lines[k:j] = [indent + new + comment + old[len(body):]]


def patch_toml_key(
    path: Path,
    table: str,
    key: str,
    value: str | list[str],
    create_table: bool = False,
    check: Callable[[dict], None] | None = None,
) -> bool:
    target = real_target(path)
    try:
        text = target.read_bytes().decode("utf-8")
        before = tomllib.loads(text)
        expected = copy.deepcopy(before)
        node, keys = expected, tomllib.loads(f"[{table}]")
        while keys:
            ((k, keys),) = keys.items()
            node = node.setdefault(k, {})
        if not isinstance(node, dict):
            raise PatchRefused(f"{target}: [{table}] is not a table")
        if key in node and node[key] == value:
            return False
        node[key] = value

        new = f"{key} = {json.dumps(value, ensure_ascii=False)}"
        header = f"[{table}]"
        lines = text.splitlines(keepends=True)
        h = next((i for i, line in enumerate(lines) if _is_header(line, header)), None)
        if h is None:
            if not create_table:
                raise PatchRefused(f"{target}: no {header} table")
            if text and not text.endswith("\n"):
                lines.append("\n")
            lines.append(("\n" if text else "") + f"{header}\n{new}\n")
        else:
            # ponytail: a line starting with "[" inside a multi-line value ends the span early;
            # the re-parse comparison below refuses any edit that goes wrong because of it.
            end = next((i for i in range(h + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
            kv = re.compile(rf"\s*{re.escape(key)}\s*=")
            k = next((i for i in range(h + 1, end) if kv.match(lines[i])), None)
            if k is not None:
                _replace_value(lines, k, end, new)
            else:
                last = max(i for i in range(h, end) if i == h or lines[i].strip() and not lines[i].lstrip().startswith("#"))
                if not lines[last].endswith("\n"):
                    lines[last] += "\n"
                lines.insert(last + 1, new + "\n")

        out = "".join(lines)
        after = tomllib.loads(out)
        if after != expected:
            raise PatchRefused(f"{target}: edit would change more than [{table}] {key}")
        if check:
            check(after)
        atomic_write(target, out)
        return True
    except PatchRefused:
        raise
    except Exception as e:
        raise PatchRefused(f"{target}: {e}") from e


def grok_config_check(before: dict) -> Callable[[dict], None]:
    fork = before.get("ui", {}).get("fork_secondary_model")

    def check(after: dict) -> None:
        got = (
            after.get("models", {}).get("default"),
            after.get("models", {}).get("default_reasoning_effort"),
            after.get("model", {}).get("grok-4.7", {}).get("context_window"),
            after.get("ui", {}).get("fork_secondary_model"),
        )
        want = ("grok-4.7", "xhigh", 500000, fork)
        if got != want:
            raise PatchRefused(f"grok config check failed: got {got}, want {want}")

    return check
