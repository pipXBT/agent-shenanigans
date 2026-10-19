import collections
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PANEL = REPO / "skills/debate/panel.json"
sys.path.insert(0, str(REPO / "skills/debate/scripts"))

from seats import (  # noqa: E402
    CLAUDE_READ_TOOLS,
    GROK_READ_TOOLS,
    PLAIN_PROSE_LINE,
    VERDICT_INSTRUCTION,
    PanelError,
    Seat,
    load_panel,
    parse_verdict,
    seat_argv,
    seat_env,
)

opus_seat = Seat("skeptic-opus", "skeptic", "opus", "claude-opus-5-5", "xhigh", 1200, "Be skeptical.")
grok_seat = Seat("skeptic-grok", "skeptic", "grok", "grok-4.7", "xhigh", 1800, "Be skeptical.")


def seat_entry(host, model, effort="xhigh"):
    return {"persona": "skeptic", "host": host, "model": model, "effort": effort,
            "timeout": 60, "system_prompt": "Be skeptical."}


class PanelTest(unittest.TestCase):
    def test_panel_has_14_seats_7_personas_both_hosts(self):
        seats = load_panel(PANEL)
        self.assertEqual(len(seats), 14)
        by = collections.Counter(s.persona for s in seats)
        self.assertEqual(len(by), 7)
        self.assertEqual(set(by.values()), {2})
        self.assertEqual({s.model for s in seats}, {"claude-opus-5-5", "grok-4.7"})
        self.assertEqual({s.effort for s in seats}, {"xhigh"})
        for name, entry in json.loads(PANEL.read_text())["seats"].items():
            self.assertEqual(set(entry), {"persona", "host", "model", "effort", "timeout", "system_prompt"})
            self.assertEqual(name, f"{entry['persona']}-{entry['host']}")

    def test_load_panel_rejects_fable_and_non_xhigh(self):
        bad_panels = {
            "fable": {"skeptic-opus": seat_entry("opus", "claude-fable-1"),
                      "skeptic-grok": seat_entry("grok", "grok-4.7")},
            "effort": {"skeptic-opus": seat_entry("opus", "claude-opus-5-5", "high"),
                       "skeptic-grok": seat_entry("grok", "grok-4.7")},
            "one host": {"skeptic-opus": seat_entry("opus", "claude-opus-5-5")},
        }
        with tempfile.TemporaryDirectory() as d:
            for label, seats in bad_panels.items():
                with self.subTest(label):
                    path = Path(d) / "panel.json"
                    path.write_text(json.dumps({"seats": seats}))
                    with self.assertRaises(PanelError):
                        load_panel(path)


class VerdictTest(unittest.TestCase):
    def test_parse_verdict(self):
        self.assertEqual(parse_verdict("x\nVERDICT: APPROVED — Future Me can live with this"), "APPROVED")
        self.assertEqual(parse_verdict("**VERDICT:** REVISE"), "REVISE")
        self.assertEqual(parse_verdict("**VERDICT: APPROVED**"), "APPROVED")
        self.assertEqual(parse_verdict("> verdict: approved"), "APPROVED")
        self.assertEqual(parse_verdict("I would say VERDICT: APPROVED if fixed.\nVERDICT: REVISE"), "REVISE")
        self.assertEqual(parse_verdict("VERDICT: REVISE\nlater\nVERDICT: APPROVED"), "APPROVED")
        self.assertIsNone(parse_verdict("no verdict here"))
        self.assertIsNone(parse_verdict("VERDICT: APPROVED\ntrailing words", timed_out=True))
        self.assertEqual(parse_verdict("words\nVERDICT: REVISE\n\n", timed_out=True), "REVISE")

    def test_instruction_does_not_parse(self):
        self.assertIsNone(parse_verdict(VERDICT_INSTRUCTION))
        self.assertIsNone(parse_verdict(PLAIN_PROSE_LINE))


class ArgvTest(unittest.TestCase):
    def test_opus_argv_is_read_only_allowlist(self):
        a = seat_argv(opus_seat, Path("p.txt"), "claude", "/h/.grok/bin/grok")
        self.assertEqual(a[:2], ["claude", "-p"])
        self.assertEqual(a[a.index("--model"):a.index("--model") + 2], ["--model", "claude-opus-5-5"])
        for flag in ["--effort", "--tools", "--strict-mcp-config", "--settings"]:
            self.assertIn(flag, a)
        self.assertEqual(a[a.index("--effort") + 1], "xhigh")
        self.assertEqual(a[a.index("--tools") + 1], CLAUDE_READ_TOOLS)
        self.assertEqual(a[a.index("--tools") + 1], "Read,Grep,Glob")
        self.assertEqual(json.loads(a[a.index("--settings") + 1]), {"outputStyle": "default"})
        self.assertNotIn("--permission-mode", a)

    def test_grok_argv_is_read_only_allowlist(self):
        a = seat_argv(grok_seat, Path("p.txt"), "claude", "/h/.grok/bin/grok")
        self.assertEqual(a[0], "/h/.grok/bin/grok")
        self.assertEqual(a[a.index("--prompt-file") + 1], "p.txt")
        self.assertEqual(a[a.index("-m") + 1], "grok-4.7")
        self.assertEqual(a[a.index("--reasoning-effort") + 1], "xhigh")
        self.assertEqual(a[a.index("--tools") + 1], GROK_READ_TOOLS)
        self.assertEqual(a[a.index("--tools") + 1], "read_file,grep,list_dir")
        for flag in ["--prompt-file", "--no-subagents", "--disable-web-search", "--no-memory"]:
            self.assertIn(flag, a)
        self.assertFalse({"write", "search_replace", "run_terminal_cmd"} & set(",".join(a).split(",")))


class EnvTest(unittest.TestCase):
    def test_opus_env_modes_off_and_nested_unset(self):
        base = {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli", "PATH": "/b"}
        env = seat_env(opus_seat, base)
        self.assertEqual(env["CAVEMAN_DEFAULT_MODE"], "off")
        self.assertEqual(env["PONYTAIL_DEFAULT_MODE"], "off")
        self.assertNotIn("CLAUDECODE", env)
        self.assertNotIn("CLAUDE_CODE_ENTRYPOINT", env)
        self.assertEqual(env["PATH"], "/b")
        self.assertIn("CLAUDECODE", base)

    def test_grok_env_modes_off(self):
        env = seat_env(grok_seat, {"CLAUDECODE": "1", "PATH": "/b"})
        self.assertEqual(env["CAVEMAN_DEFAULT_MODE"], "off")
        self.assertEqual(env["PONYTAIL_DEFAULT_MODE"], "off")
        self.assertEqual(env["PATH"], "/b")


if __name__ == "__main__":
    unittest.main()
