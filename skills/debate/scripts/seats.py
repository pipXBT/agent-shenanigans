"""Debate panel seats: load the panel, build each seat's read-only command, read its verdict."""
import collections
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

CLAUDE_READ_TOOLS = "Read,Grep,Glob"
GROK_READ_TOOLS = "read_file,grep,list_dir"
PLAIN_PROSE_LINE = "Write plain prose. Do not use caveman or ponytail styles."
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


class PanelError(Exception):
    pass


def load_panel(path: Path) -> list[Seat]:
    seats = [Seat(name, **entry) for name, entry in json.loads(Path(path).read_text())["seats"].items()]
    hosts = collections.defaultdict(set)
    for s in seats:
        if "fable" in s.model.lower():
            raise PanelError(f"{s.name}: model id {s.model!r} is not allowed")
        if s.effort != "xhigh":
            raise PanelError(f"{s.name}: effort must be xhigh, got {s.effort!r}")
        hosts[s.persona].add(s.host)
    for persona, h in hosts.items():
        if h != {"opus", "grok"}:
            raise PanelError(f"{persona}: needs exactly one opus and one grok seat, got {sorted(h)}")
    return seats


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
    env = dict(base, CAVEMAN_DEFAULT_MODE="off", PONYTAIL_DEFAULT_MODE="off")
    if seat.host == "opus":
        # Unset so the child claude does not treat itself as nested in this session.
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    return env
