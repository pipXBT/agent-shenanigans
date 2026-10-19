"""Debate panel seats: load the panel, build each seat's read-only command, read its verdict."""
import collections
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

CLAUDE_READ_TOOLS = "Read,Grep,Glob"
GROK_READ_TOOLS = "read_file,grep,list_dir"
CAVEMAN_MODES = {"off", "caveman", "ultracave", "megacave"}
PONYTAIL_MODES = {"off", "lite", "full", "ultra"}
# The prompt is Grok's only delivery (no hooks), so both hosts get these same lines.
MODE_LINES = {
    ("caveman", "ultracave"): (
        "Style: caveman ultracave. Terse fragments; drop articles, filler, and connectives; state each "
        "fact once. Keep every technical fact, quote, path, number, and every not/never/no/only verbatim."),
    ("ponytail", "full"): (
        "Judgment: ponytail full. Recommend the smallest complete change; flag speculative abstraction, "
        "options, and scaffolding. Never cut validation, error handling that prevents data loss, or security."),
    ("ponytail", "ultra"): (
        "Judgment: ponytail ultra. Recommend the smallest complete change and challenge any requirement "
        "the plan does not justify; deletion beats addition. Never cut validation, error handling that "
        "prevents data loss, or security."),
}
VERDICT_INSTRUCTION = (
    "End your reply with one final line made of the word VERDICT in capitals, "
    "a colon, a space, and then either APPROVED or REVISE."
)

# A verdict line: optional markdown markers, VERDICT, a colon (markers may wrap it), then the word.
VERDICT_RE = re.compile(r"[\s*_`#>]*verdict[*_`]*:[*_`\s]*(approved|revise)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Seat:
    name: str
    persona: str
    host: Literal["opus", "grok"]
    model: str
    effort: str
    timeout: int
    system_prompt: str
    caveman: str = "off"
    ponytail: str = "off"


class PanelError(Exception):
    pass


def load_panel(path: Path) -> list[Seat]:
    seats = [Seat(name, **entry) for name, entry in json.loads(Path(path).read_text())["seats"].items()]
    hosts, modes = collections.defaultdict(set), collections.defaultdict(set)
    for s in seats:
        if "fable" in s.model.lower():
            raise PanelError(f"{s.name}: model id {s.model!r} is not allowed")
        if s.effort != "xhigh":
            raise PanelError(f"{s.name}: effort must be xhigh, got {s.effort!r}")
        for kind, allowed in (("caveman", CAVEMAN_MODES), ("ponytail", PONYTAIL_MODES)):
            if getattr(s, kind) not in allowed:
                raise PanelError(f"{s.name}: {kind} must be one of {sorted(allowed)}, got {getattr(s, kind)!r}")
        hosts[s.persona].add(s.host)
        modes[s.persona].add((s.caveman, s.ponytail))
    for persona, h in hosts.items():
        if h != {"opus", "grok"}:
            raise PanelError(f"{persona}: needs exactly one opus and one grok seat, got {sorted(h)}")
        # Both seats of a persona share modes, so a split comes from reasoning, not style.
        if len(modes[persona]) != 1:
            raise PanelError(f"{persona}: both seats need the same caveman and ponytail modes, got {sorted(modes[persona])}")
    return seats


def modes_lines(seat: Seat) -> str:
    lines = []
    for kind in ("caveman", "ponytail"):
        mode = getattr(seat, kind)
        if mode == "off":
            continue
        if (kind, mode) not in MODE_LINES:
            # No line would leave the Grok seat unstyled while the Opus hook styles its twin.
            raise PanelError(f"{seat.name}: no prompt line for {kind} {mode!r}")
        lines.append(MODE_LINES[kind, mode])
    return "\n".join(lines) or "Write plain prose."


def parse_verdict(text: str, timed_out: bool = False) -> Literal["APPROVED", "REVISE"] | None:
    lines = [line for line in text.splitlines() if line.strip()]
    for i in range(len(lines) - 1, -1, -1):
        m = VERDICT_RE.match(lines[i])
        if m:
            # A killed seat may have been mid-sentence; trust only a verdict it finished on.
            return None if timed_out and i != len(lines) - 1 else m.group(1).upper()
    return None


def seat_argv(seat: Seat, prompt_file: Path, claude_bin: str, grok_bin: str) -> list[str]:
    if seat.host == "opus":
        # The prompt goes on stdin.
        return [claude_bin, "-p", "--model", seat.model, "--effort", seat.effort,
                "--tools", CLAUDE_READ_TOOLS, "--strict-mcp-config",
                "--settings", '{"outputStyle":"default"}']
    return [grok_bin, "--prompt-file", str(prompt_file), "--output-format", "plain",
            "-m", seat.model, "--reasoning-effort", seat.effort, "--tools", GROK_READ_TOOLS,
            "--no-subagents", "--disable-web-search", "--no-memory"]


def seat_env(seat: Seat, base: dict[str, str]) -> dict[str, str]:
    env = dict(base, CAVEMAN_DEFAULT_MODE=seat.caveman, PONYTAIL_DEFAULT_MODE=seat.ponytail)
    if seat.host == "opus":
        # Unset so the child claude does not treat itself as nested in this session.
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    return env
