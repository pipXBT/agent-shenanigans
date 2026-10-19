#!/usr/bin/env python3
"""Parse a superpowers:writing-plans file into executor tasks.

Usage: parse_plan.py PLAN   (prints JSON; exit 1 when "errors" is non-empty)
"""
import hashlib
import json
import posixpath
import re
import sys
from dataclasses import asdict, dataclass
from typing import Literal, Optional

KINDS = ("code", "refactor", "docs", "test")
COMPLEXITIES = ("low", "medium", "high")

HEADING = re.compile(r"^(#{1,3})\s")
TASK = re.compile(r"^### Task (\w+):\s*(.*\S)\s*$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
PATH_LINE = re.compile(r"^\s*[-*]\s+(Create|Modify|Delete|Test):(.*)$")
TICKED = re.compile(r"`([^`]+)`")
RANGE = re.compile(r":\d+(?:-\d+)?$")
KIND = re.compile(r"^\s*\*\*Kind:\*\*\s*(\w+)\s*$", re.I)
COMPLEXITY = re.compile(r"^\s*\*\*Complexity:\*\*\s*(\w+)\s*$", re.I)
DOCS_SUFFIXES = (".md", ".rst", ".txt", ".adoc")


@dataclass(frozen=True)
class PlanTask:
    id: str
    title: str
    files: tuple[str, ...]
    tests: tuple[str, ...]
    kind: Literal["code", "refactor", "docs", "test"]
    kind_source: Literal["marker", "derived"]
    complexity: Optional[Literal["low", "medium", "high"]]


def is_docs(path: str) -> bool:
    return path.endswith(DOCS_SUFFIXES) or path.startswith("docs/")


def derive_kind(files: tuple[str, ...], tests: tuple[str, ...]) -> str:
    if any(not is_docs(f) for f in files):
        return "code"
    paths = files + tests
    if paths and all(map(is_docs, paths)):
        return "docs"
    return "test" if tests else "code"


def line_paths(rest: str) -> list[str]:
    # The plan's own "(notes ...)" after the paths hold backticked non-paths.
    tokens = [RANGE.sub("", t.strip()) for t in TICKED.findall(rest.split(" (")[0])]
    if not tokens:
        return []
    base = posixpath.dirname(tokens[0])
    return [t if "/" in t or not base else f"{base}/{t}" for t in tokens]


def build(num: str, title: str, body: list[str]) -> PlanTask:
    files: list[str] = []
    tests: list[str] = []
    marked = complexity = None
    for line in body:
        m = PATH_LINE.match(line)
        if m:
            (tests if m[1] == "Test" else files).extend(line_paths(m[2]))
        elif (m := KIND.match(line)) and m[1].lower() in KINDS:
            marked = marked or m[1].lower()
        elif (m := COMPLEXITY.match(line)) and m[1].lower() in COMPLEXITIES:
            complexity = complexity or m[1].lower()
    f, t = tuple(dict.fromkeys(files)), tuple(dict.fromkeys(tests))
    return PlanTask(
        num, title, f, t, marked or derive_kind(f, t),
        "marker" if marked else "derived", complexity,
    )


def parse_plan(text: str) -> list[PlanTask]:
    tasks: list[PlanTask] = []
    current: Optional[tuple[str, str, list[str]]] = None
    fence = None  # (char, length) of the open code fence

    def close() -> None:
        if current:
            tasks.append(build(*current))

    for line in text.splitlines():
        f = FENCE.match(line)
        if fence:
            if f and f[1][0] == fence[0] and len(f[1]) >= fence[1] and not f[2].strip():
                fence = None
            continue
        if f:
            fence = (f[1][0], len(f[1]))
            continue
        if m := TASK.match(line):
            close()
            current = (m[1], m[2], [])
        elif HEADING.match(line):
            close()
            current = None
        elif current:
            current[2].append(line)
    close()
    return tasks


def validate(tasks: list[PlanTask]) -> list[str]:
    errors, seen = [], set()
    for t in tasks:
        if t.id in seen:
            errors.append(f"Task {t.id} ({t.title}): duplicate id")
        seen.add(t.id)
        if t.kind == "code":
            for name, paths in (("files", t.files), ("tests", t.tests)):
                if not paths:
                    errors.append(
                        f"Task {t.id} ({t.title}): code task has no {name}; "
                        "add them or mark the task with **Kind:**"
                    )
    return errors


def plan_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    data = open(argv[0], "rb").read()
    tasks = parse_plan(data.decode("utf-8"))
    errors = validate(tasks)
    print(json.dumps(
        {"plan_hash": plan_hash(data), "tasks": [asdict(t) for t in tasks], "errors": errors},
        indent=2,
    ))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
