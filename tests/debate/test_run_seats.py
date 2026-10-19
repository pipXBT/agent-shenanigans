import contextlib
import hashlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
PANEL = REPO / "skills/debate/panel.json"
sys.path.insert(0, str(REPO / "skills/debate/scripts"))

import run_seats  # noqa: E402
from seats import VERDICT_INSTRUCTION, load_panel, modes_lines  # noqa: E402

# One committed fake serves both hosts (see its header). A stable file matters: macOS can take
# many seconds to scan a newly written executable, which would trip the 1-2 s seat timeouts.
FAKE_BIN = REPO / "tests/debate/fake_seat"
APPROVE = 'echo "VERDICT: APPROVED"'
ECHO = 'printf "%s\\n" "$PROMPT"; echo "VERDICT: APPROVED"'
CALLS = 'echo call >> "$me.calls"; '
FAIL_FIRST = CALLS + '[ "$(wc -l < "$me.calls")" -eq 1 ] && exit 1; ' + APPROVE
HANG = 'sleep 30 & echo $! > "$me.pid"; wait'
HANG_PIDS = 'sleep 30 & echo $! > "$me.pid"; echo $$ > "$me.seat"; wait'
PLAN = "Ship the widget.\n"


PLAIN = "Write plain prose."  # both modes off: what a panel entry with no mode keys gets


def panel_json(timeout=2, persona="skeptic", **modes):
    return {"seats": {f"{persona}-{h}": {
        "persona": persona, "host": h, "model": "claude-opus-5-5" if h == "opus" else "grok-4.7",
        "effort": "xhigh", "timeout": timeout, "system_prompt": f"You are the {h} {persona}.", **modes}
        for h in ("opus", "grok")}}


class RunSeatsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Run the fake once, untimed, so any first-exec scan happens here.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "claude.body").write_text("")
            subprocess.run([FAKE_BIN, "-p"], input=b"", env=dict(os.environ, FAKE_DIR=d), check=True)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.w = self.tmp / "w"
        self.plan = self.tmp / "plan.md"
        self.plan.write_text(PLAN)
        self.panel = self.tmp / "panel.json"
        self.write_panel(panel_json())

    def write_panel(self, data):
        self.panel.write_text(json.dumps(data))

    def fakes(self, claude=APPROVE, grok=APPROVE):
        for name, body in [("claude", claude), ("grok", grok)]:
            (self.tmp / f"{name}.body").write_text(body + "\n")
        grok_bin = self.tmp / "grok"  # a symlink, so the argv shows which binary each host got
        if not grok_bin.exists():
            grok_bin.symlink_to(FAKE_BIN)
        env = {"SEATS_CLAUDE_BIN": str(FAKE_BIN), "SEATS_GROK_BIN": str(grok_bin), "FAKE_DIR": str(self.tmp)}
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)

    def run_cmd(self, *extra, w=None):
        return run_seats.main(["run", "--panel", str(self.panel), "--work-dir", str(w or self.w),
                               "--plan", str(self.plan), *extra])

    def probe(self):
        out = self.tmp / "probe" / "seats.json"
        rc = run_seats.main(["probe", "--panel", str(self.panel), "--work-dir", str(self.w), "--out", str(out)])
        return rc, json.loads(out.read_text())

    def summary(self, w=None):
        return json.loads(((w or self.w) / "summary.json").read_text())

    def read(self, name):
        return (self.w / name).read_text()

    def assert_gone(self, pid, within=3):
        deadline = time.monotonic() + within
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
        self.fail(f"process {pid} still alive after {within}s")

    def interrupt_runner(self, sig):
        self.write_panel(panel_json(timeout=60))
        self.fakes(claude=HANG_PIDS)
        runner = subprocess.Popen([sys.executable, str(REPO / "skills/debate/scripts/run_seats.py"), "run",
                                   "--panel", str(self.panel), "--work-dir", str(self.w),
                                   "--plan", str(self.plan), "--seats", "skeptic-opus"])
        self.addCleanup(runner.kill)
        seat_file = self.tmp / "claude.seat"
        deadline = time.monotonic() + 10
        while not (seat_file.exists() and seat_file.read_text().strip()):
            self.assertLess(time.monotonic(), deadline, "seat never started")
            time.sleep(0.05)
        pids = [int((self.tmp / f"claude.{k}").read_text()) for k in ("seat", "pid")]
        runner.send_signal(sig)
        runner.wait(timeout=5)
        for pid in pids:
            self.assert_gone(pid)

    def test_run_writes_outputs_exit_argv_summary(self):
        self.fakes()
        self.assertEqual(self.run_cmd(), 0)
        for seat in ["skeptic-opus", "skeptic-grok"]:
            self.assertTrue((self.w / f"{seat}-output.md").exists())
            self.assertEqual(self.read(f"{seat}-exit.txt"), "0")
        self.assertEqual(json.loads(self.read("skeptic-opus-argv.json"))[0], str(FAKE_BIN))
        self.assertEqual(json.loads(self.read("skeptic-grok-argv.json"))[0], str(self.tmp / "grok"))
        sha = hashlib.sha256(PLAN.encode()).hexdigest()
        self.assertEqual(self.read("plan.sha256"), sha)
        self.assertEqual(self.summary(), {
            "requested": 2, "returned": 2, "plan_sha256": sha, "approved": True,
            "verdicts": {"skeptic-opus": "APPROVED", "skeptic-grok": "APPROVED"}})

    def test_one_revise_is_not_approved(self):
        self.fakes(grok='echo "VERDICT: REVISE"')
        self.assertEqual(self.run_cmd(), 0)
        self.assertEqual(self.summary()["verdicts"], {"skeptic-opus": "APPROVED", "skeptic-grok": "REVISE"})
        self.assertFalse(self.summary()["approved"])

    def test_prompt_has_plain_prose_when_modes_are_off(self):
        self.fakes(ECHO, ECHO)
        self.assertEqual(self.run_cmd(), 0)
        for host in ["opus", "grok"]:
            out = self.read(f"skeptic-{host}-output.md")
            self.assertEqual(out.count(PLAIN), 1)
            self.assertEqual(out.count(VERDICT_INSTRUCTION), 1)
            self.assertIn(f"You are the {host} skeptic.\n\n{PLAN}\n\n{PLAIN}\n{VERDICT_INSTRUCTION}", out)
            # The prompt never rides on argv (claude's --tools is variadic).
            self.assertNotIn("Ship the widget", self.read(f"skeptic-{host}-argv.json"))

    def test_future_me_seats_get_ultracave_and_ponytail_ultra_lines(self):
        self.write_panel(panel_json(persona="future-me", caveman="ultracave", ponytail="ultra"))
        self.fakes(ECHO, ECHO)
        self.assertEqual(self.run_cmd(), 0)
        seats = {s.name: s for s in load_panel(self.panel)}
        for name, seat in seats.items():
            out = self.read(f"{name}-output.md")
            lines = modes_lines(seat)
            self.assertEqual(lines.count("\n"), 1)
            self.assertIn("Style: caveman ultracave.", lines)
            self.assertIn("Judgment: ponytail ultra.", lines)
            self.assertNotIn(PLAIN, out)
            self.assertIn(f"{PLAN}\n\n{lines}\n{VERDICT_INSTRUCTION}", out)
        self.assertIn("future-me-grok", seats)  # the Grok seat has no hooks: its prompt is the only delivery

    def test_uses_seat_prompt_file_when_present(self):
        self.w.mkdir()
        (self.w / "skeptic-opus-prompt.txt").write_text("Answer the grok skeptic's point.")
        self.fakes(ECHO, ECHO)
        self.assertEqual(self.run_cmd(), 0)
        opus = self.read("skeptic-opus-output.md")
        self.assertIn(f"Answer the grok skeptic's point.\n\n{PLAIN}\n{VERDICT_INSTRUCTION}", opus)
        self.assertNotIn("Ship the widget", opus)
        self.assertNotIn("You are the opus skeptic.", opus)
        self.assertIn("Ship the widget", self.read("skeptic-grok-output.md"))

    def test_missing_seat_rerun_once(self):
        self.fakes(claude=FAIL_FIRST)
        self.assertEqual(self.run_cmd(), 0)
        self.assertEqual((self.tmp / "claude.calls").read_text().count("call"), 2)
        self.assertEqual(self.summary()["returned"], 2)
        self.assertEqual(self.read("skeptic-opus-exit.txt"), "0")

    def test_failing_cli_counts_not_returned(self):
        self.fakes(grok=CALLS + "echo boom >&2; exit 1")
        self.assertEqual(self.run_cmd(), 1)
        self.assertEqual((self.tmp / "grok.calls").read_text().count("call"), 2)
        s = self.summary()
        self.assertEqual((s["requested"], s["returned"]), (2, 1))
        self.assertIsNone(s["verdicts"]["skeptic-grok"])
        self.assertFalse(s["approved"])
        self.assertEqual(self.read("skeptic-grok-exit.txt"), "1")

    def test_missing_binary_counts_not_returned(self):
        self.fakes()
        os.environ["SEATS_GROK_BIN"] = str(self.tmp / "no-such-grok")
        self.assertEqual(self.run_cmd(), 1)
        self.assertIsNone(self.summary()["verdicts"]["skeptic-grok"])
        self.assertEqual(self.read("skeptic-grok-exit.txt"), "127")

    def test_timeout_counts_not_returned(self):
        self.write_panel(panel_json(timeout=1))
        self.fakes(claude=HANG)
        start = time.monotonic()
        self.assertEqual(self.run_cmd(), 1)
        self.assertLess(time.monotonic() - start, 5)  # two 1 s attempts, not two 30 s sleeps
        self.assertEqual(self.read("skeptic-opus-exit.txt"), "124")
        self.assertIsNone(self.summary()["verdicts"]["skeptic-opus"])
        # The fake's child sleep died with its process group.
        self.assert_gone(int((self.tmp / "claude.pid").read_text()))

    def test_sigterm_to_runner_kills_live_seats(self):
        self.interrupt_runner(signal.SIGTERM)

    def test_sigint_to_runner_kills_live_seats(self):
        self.interrupt_runner(signal.SIGINT)

    def test_timed_out_seat_with_final_verdict_counts(self):
        self.write_panel(panel_json(timeout=1))
        self.fakes(claude='echo "Looks risky."; echo "VERDICT: REVISE"; sleep 30')
        self.assertEqual(self.run_cmd(), 0)
        self.assertEqual(self.read("skeptic-opus-exit.txt"), "124")
        self.assertEqual(self.summary()["verdicts"]["skeptic-opus"], "REVISE")
        self.assertEqual(self.summary()["returned"], 2)

    def test_plan_hash_matches_bytes_sent(self):
        plan = "Plan: café — naïve\r\nline two\n".encode()
        self.plan.write_bytes(plan)
        self.fakes(ECHO, ECHO)
        self.assertEqual(self.run_cmd(), 0)
        sha = hashlib.sha256(plan).hexdigest()
        self.assertEqual(self.read("plan.sha256"), sha)
        self.assertEqual(self.summary()["plan_sha256"], sha)
        for host in ["opus", "grok"]:
            self.assertIn(plan, (self.w / f"skeptic-{host}-output.md").read_bytes())

    def test_subset_reports_requested_count(self):
        self.fakes()
        self.assertEqual(self.run_cmd("--seats", "skeptic-opus"), 0)
        s = self.summary()
        self.assertEqual((s["requested"], s["returned"]), (1, 1))
        self.assertEqual(s["verdicts"], {"skeptic-opus": "APPROVED"})
        self.assertFalse(s["approved"])  # a subset never approves the round
        self.assertFalse((self.w / "skeptic-grok-output.md").exists())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.run_cmd("--seats", "skeptic-opus,nobody")

    def test_stamp_only_on_full_return(self):
        full = json.loads(PANEL.read_text())
        for entry in full["seats"].values():
            entry["timeout"] = 2
        names = list(full["seats"])
        stamp = self.tmp / "probe" / "seat-dry-run.json"
        self.fakes()
        with self.subTest("two-seat panel"):
            self.assertEqual(self.run_cmd("--stamp", str(stamp), w=self.tmp / "w2"), 0)
            self.assertFalse(stamp.exists())
        self.write_panel(full)
        with self.subTest("13 of 14"):
            self.assertEqual(self.run_cmd("--seats", ",".join(names[:13]), "--stamp", str(stamp),
                                          w=self.tmp / "w13"), 0)
            self.assertFalse(stamp.exists())
        with self.subTest("14 requested, grok seats fail"):
            self.fakes(grok="exit 1")
            self.assertEqual(self.run_cmd("--stamp", str(stamp), w=self.tmp / "wfail"), 1)
            self.assertFalse(stamp.exists())
        with self.subTest("14 of 14"):
            self.fakes()
            self.assertEqual(self.run_cmd("--stamp", str(stamp), w=self.tmp / "w14"), 0)
            self.assertEqual(self.summary(self.tmp / "w14")["returned"], 14)
            data = json.loads(stamp.read_text())
            self.assertEqual(set(data), {"host", "passed", "written_at", "detail"})
            self.assertEqual((data["host"], data["passed"], data["detail"]), ("seat-dry-run", True, "14/14"))
            self.assertLessEqual(abs(data["written_at"] - time.time()), 60)

    def test_probe_prompt_carries_the_seat_modes(self):
        self.write_panel(panel_json(caveman="ultracave", ponytail="off"))
        self.fakes()
        rc, data = self.probe()
        self.assertEqual(rc, 0, data["detail"])
        for seat in ["skeptic-opus", "skeptic-grok"]:
            self.assertIn("Style: caveman ultracave.", self.read(f"{seat}-input.txt"))
            self.assertNotIn("Judgment: ponytail", self.read(f"{seat}-input.txt"))

    def test_probe_passes_with_read_only_seats(self):
        self.fakes(claude='printf -- "- **Read** - read files\\n- Grep\\n- `Glob`\\n"; '
                          'echo "PROBE_WRITE: not created, I have no tool that can write or edit."; ' + APPROVE,
                   grok='printf "read_file\\ngrep\\nlist_dir\\n"; echo "I cannot write files."; '
                        'echo "VERDICT: REVISE"')
        rc, data = self.probe()
        self.assertEqual(rc, 0, data["detail"])
        self.assertEqual(set(data), {"host", "passed", "written_at", "detail"})
        self.assertEqual((data["host"], data["passed"]), ("seats", True))
        for seat in ["skeptic-opus", "skeptic-grok"]:
            self.assertIn("try to create a file named PROBE_WRITE", self.read(f"{seat}-input.txt"))
            self.assertTrue(self.read(f"{seat}-input.txt").endswith(VERDICT_INSTRUCTION))

    def test_probe_fails_when_seat_lists_write_tool_or_writes(self):
        cases = {
            "grok lists search_replace": (APPROVE, 'printf "read_file\\nsearch_replace\\n"; ' + APPROVE,
                                          "search_replace"),
            "opus lists an mcp tool": ('printf -- "- Read\\n- mcp__github__create_issue: file issues\\n"; '
                                       + APPROVE, APPROVE, "mcp__github__create_issue"),
            "opus lists Bash": ('printf "1. Read\\n2. **Bash** (shell)\\n"; ' + APPROVE, APPROVE, "Bash"),
            "opus writes": ("touch PROBE_WRITE; " + APPROVE, APPROVE, "PROBE_WRITE"),
            "grok does not return": (APPROVE, "exit 1", "skeptic-grok"),
        }
        for label, (claude, grok, detail) in cases.items():
            with self.subTest(label):
                self.w = self.tmp / label.replace(" ", "-")
                self.fakes(claude, grok)
                rc, data = self.probe()
                self.assertEqual(rc, 1)
                self.assertFalse(data["passed"])
                self.assertIn(detail, data["detail"])


if __name__ == "__main__":
    unittest.main()
