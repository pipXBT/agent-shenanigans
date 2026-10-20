import contextlib
import dataclasses
import io
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from doctor import cli
from doctor.hosts import HostState, PluginState, loaded_shas
from doctor.probes import ProbeResult, accept, is_stale, read_probes, run_seat_probe
from doctor.stack import PluginDecl, Stack
from tests.doctor.test_hosts import git_repo

REPO = Path(__file__).resolve().parents[2]
FAKE_SEAT = REPO / "tests/debate/fake_seat"
HEAD = "a" * 40
SELF_ID = "shenanigans@agent-shenanigans"

STACK = Stack(
    plugins=(
        PluginDecl("shenanigans", "o/a", SELF_ID, "shenanigans", "enabled", "enabled", None),
        PluginDecl("ponytail", "o/p", "ponytail@ponytail", "ponytail", "enabled", "enabled", None),
        PluginDecl("old", "o/o", "old@old", None, "absent", None, None),
    ),
    links=(), retire=(), retire_after_probe=(), gated={}, settings=(),
)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def host(name, shas, enabled=True):
    """A host state loading each {plugin: sha}; Claude keys plugins by id, Grok by name."""
    key = {p.name: p.claude_id for p in STACK.plugins}.get if name == "claude" else (lambda n: n)
    plugins = {key(n): PluginState(name, key(n), enabled, sha, None, False) for n, sha in shas.items()}
    return HostState(name, plugins, (), ())


class Freshness(unittest.TestCase):
    def probe(self, shas):
        return ProbeResult("claude", True, 1.0, None, "", shas)

    def test_probe_stale_when_shas_differ(self):
        same = {"ponytail": "p1", "caveman": "c1"}
        self.assertFalse(is_stale(self.probe(same), dict(same)))
        self.assertFalse(is_stale(self.probe({}), {}))
        for label, (recorded, current) in {
            "a sha changed": ({"ponytail": "p1"}, {"ponytail": "p2"}),
            "a plugin was added": ({"ponytail": "p1"}, {"ponytail": "p1", "caveman": "c1"}),
            "a plugin went away": ({"ponytail": "p1", "caveman": "c1"}, {"ponytail": "p1"}),
            "no shas recorded": ({}, {"ponytail": "p1"}),
            "nothing loaded now": ({"ponytail": "p1"}, {}),
        }.items():
            with self.subTest(label):
                self.assertTrue(is_stale(self.probe(recorded), current))

    def test_age_does_not_matter(self):
        old = ProbeResult("claude", True, 0.0, None, "", {"ponytail": "p1"})
        self.assertFalse(is_stale(old, {"ponytail": "p1"}))

    def test_read_probes_reads_shas_and_defaults_to_none(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write(d / "claude.json", json.dumps({"host": "claude", "passed": True, "written_at": 1, "shas": {"ponytail": "p1"}}))
            write(d / "grok.json", json.dumps({"host": "grok", "passed": True, "written_at": 1}))
            got = read_probes(d)
        self.assertEqual(got["claude"].shas, {"ponytail": "p1"})
        self.assertEqual(got["grok"].shas, {})

    def test_loaded_shas_prefers_claude_and_drops_a_local_install_suffix(self):
        claude = host("claude", {"shenanigans": HEAD, "ponytail": "p1"})
        grok = host("grok", {"shenanigans": HEAD + "+0123456789ab", "ponytail": "p1"})
        self.assertEqual(loaded_shas(STACK, claude, grok), {"shenanigans": HEAD, "ponytail": "p1"})
        self.assertEqual(loaded_shas(STACK, claude, host("grok", {"ponytail": "p1"}, enabled=False)),
                         {"shenanigans": HEAD, "ponytail": "p1"})


class AcceptCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.claude_shas = {"shenanigans": HEAD, "ponytail": "p1"}
        self.grok_shas = dict(self.claude_shas)
        self.head = HEAD
        self.probes = {
            n: ProbeResult(n, True, time.time(), None, "", dict(self.claude_shas)) for n in ("claude", "grok", "seats")
        }
        self.probes["seats"] = ProbeResult("seats", True, time.time(), None, "")  # the seat probe records no shas

    def accept(self):
        return accept(self.repo, STACK, host("claude", self.claude_shas), host("grok", self.grok_shas), self.probes, self.head)

    def assert_refused(self, *fragments):
        why = self.accept()
        self.assertTrue(why)
        for f in fragments:
            self.assertTrue(any(f in w for w in why), f"{f!r} not in {why}")
        self.assertFalse((self.repo / "verified.json").exists())
        return why


class Accept(AcceptCase):
    def test_accept_writes_verified_json(self):
        self.grok_shas["shenanigans"] = HEAD + "+0123456789ab"  # a Local install: same commit, Grok-only hash
        self.assertEqual(self.accept(), [])
        text = (self.repo / "verified.json").read_text()
        self.assertEqual(json.loads(text), {"shenanigans": HEAD, "ponytail": "p1"})
        self.assertTrue(text.endswith("\n"))

    def test_accept_replaces_an_older_verified_json(self):
        write(self.repo / "verified.json", '{"ponytail": "old", "gone": "x"}')
        self.assertEqual(self.accept(), [])
        self.assertEqual(json.loads((self.repo / "verified.json").read_text()), {"shenanigans": HEAD, "ponytail": "p1"})

    def test_accept_refuses_when_hosts_differ(self):
        self.grok_shas["ponytail"] = "p2"
        (why,) = self.assert_refused("ponytail", "claude p1", "grok p2")
        self.assertIn("different SHAs", why)

    def test_accept_refuses_a_plugin_not_loaded_on_a_host(self):
        del self.grok_shas["ponytail"]
        self.assert_refused("ponytail is not loaded on grok")

    def test_accept_refuses_a_plugin_that_is_installed_but_disabled(self):
        why = accept(self.repo, STACK, host("claude", self.claude_shas), host("grok", self.grok_shas, enabled=False),
                     self.probes, self.head)
        self.assertEqual(why[:2], ["shenanigans is not loaded on grok", "ponytail is not loaded on grok"])

    def test_accept_refuses_a_sha_that_could_not_be_read(self):
        claude = host("claude", self.claude_shas)
        claude.plugins["ponytail@ponytail"] = dataclasses.replace(claude.plugins["ponytail@ponytail"], sha=None)
        why = accept(self.repo, STACK, claude, host("grok", self.grok_shas), self.probes, self.head)
        self.assertEqual(why, ["ponytail: no SHA could be read"])

    def test_accept_refuses_on_checkout_drift(self):
        self.head = "b" * 40
        why = self.assert_refused("shenanigans on claude", "shenanigans on grok")
        self.assertEqual(len(why), 2)
        self.head = None
        self.assert_refused("checkout HEAD is unknown")

    def test_checkout_drift_compares_a_local_install_on_its_commit_part(self):
        self.grok_shas["shenanigans"] = "b" * 40 + "+0123456789ab"
        self.assert_refused("hosts load different SHAs", "shenanigans on grok")

    def test_accept_refuses_missing_failing_or_stale_probe(self):
        def missing():
            del self.probes["grok"]

        def failing():
            self.probes["claude"] = ProbeResult("claude", False, time.time(), None, "no token", dict(self.claude_shas))

        def stale():
            self.probes["grok"] = ProbeResult("grok", True, time.time(), None, "", {"ponytail": "p0"})

        def no_shas():
            self.probes["claude"] = ProbeResult("claude", True, time.time(), None, "")

        def seats_missing():
            del self.probes["seats"]

        def seats_failing():
            self.probes["seats"] = ProbeResult("seats", False, time.time(), None, "opus lists Bash")

        cases = {
            "missing": (missing, "probe grok is missing"),
            "failing": (failing, "probe claude did not pass: no token"),
            "stale": (stale, "probe grok is stale"),
            "no recorded shas": (no_shas, "probe claude is stale"),
            "seats missing": (seats_missing, "probe seats is missing"),
            "seats failing": (seats_failing, "probe seats did not pass: opus lists Bash"),
        }
        for label, (bend, expect) in cases.items():
            with self.subTest(label):
                self.setUp()
                bend()
                self.assert_refused(expect)

    def test_a_refusal_lists_every_reason_and_leaves_verified_json_alone(self):
        write(self.repo / "verified.json", '{"ponytail": "old"}')
        self.grok_shas["ponytail"] = "p2"
        del self.probes["seats"]
        why = self.accept()
        self.assertEqual(len(why), 2)
        self.assertEqual((self.repo / "verified.json").read_text(), '{"ponytail": "old"}')


class SeatProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Run the fake once so any first-exec scan happens before a timed run.
        with tempfile.TemporaryDirectory() as d:
            write(Path(d) / "claude.body", "")
            subprocess.run([FAKE_SEAT, "-p"], input=b"", env=dict(os.environ, FAKE_DIR=d), check=True)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.probe_dir = self.tmp / "probe"

    def env(self, claude, grok):
        write(self.tmp / "claude.body", claude + "\n")
        write(self.tmp / "grok.body", grok + "\n")
        return {"SEATS_CLAUDE_BIN": str(FAKE_SEAT), "SEATS_GROK_BIN": str(FAKE_SEAT), "FAKE_DIR": str(self.tmp),
                "PATH": os.environ["PATH"], "HOME": str(self.tmp)}

    READ_ONLY = 'printf "Read\\nGrep\\n"; echo "I cannot write files."; echo "VERDICT: APPROVED"'

    def test_seat_probe_runs_runner(self):
        result = run_seat_probe(REPO, self.probe_dir, self.env(self.READ_ONLY, self.READ_ONLY))
        self.assertEqual((result.host, result.passed), ("seats", True))
        self.assertEqual(result.detail, "2/2 returned, read-only")
        self.assertEqual(read_probes(self.probe_dir)["seats"], result)
        self.assertLessEqual(abs(result.written_at - time.time()), 60)

    def test_seat_probe_reports_a_failing_seat(self):
        listing = 'printf "Read\\nBash\\n"; echo "VERDICT: APPROVED"'
        result = run_seat_probe(REPO, self.probe_dir, self.env(listing, self.READ_ONLY))
        self.assertFalse(result.passed)
        self.assertIn("Bash", result.detail)

    def test_runner_that_crashes_is_an_error_even_with_an_old_result_on_disk(self):
        write(self.probe_dir / "seats.json", json.dumps({"host": "seats", "passed": True, "written_at": 1, "detail": "old"}))
        broken = self.tmp / "repo"
        write(broken / "skills/debate/scripts/run_seats.py", "import sys\nprint('boom', file=sys.stderr)\nsys.exit(3)\n")
        write(broken / "skills/debate/panel.json", "{}")
        with self.assertRaisesRegex(RuntimeError, "boom"):
            run_seat_probe(broken, self.probe_dir, self.env("", ""))


class CliAccept(unittest.TestCase):
    """The CLI on a one-plugin stack in a temp repo, with a fake grok and a fake home."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.home, self.repo = root / "home", root / "repo"
        self.head = git_repo(self.repo)
        write(self.repo / "stack.toml", f'''
[[plugin]]
name = "shenanigans"
source = "o/a"
claude_id = "{SELF_ID}"
grok_name = "shenanigans"
claude_state = "enabled"
grok_state = "enabled"
''')
        write(self.home / ".claude/plugins/installed_plugins.json", json.dumps({"plugins": {SELF_ID: [
            {"scope": "user", "installPath": str(root / "cache"), "gitCommitSha": self.head}]}}))
        write(self.home / ".claude/settings.json", json.dumps({"enabledPlugins": {SELF_ID: True}}))
        self.grok = self.home / ".grok/bin/grok"
        write(self.grok, "#!/bin/sh\ncat <<'EOF'\n  Skills (0)\n\n  Plugins (1)\n  └ shenanigans (user, enabled)  0 skills\nEOF\n")
        self.grok.chmod(0o755)
        self.env = {"HOME": str(self.home), "AGENT_SHENANIGANS_HOME": str(self.home), "GROK_BIN": str(self.grok),
                    "PATH": os.environ["PATH"]}
        patch = mock.patch.object(cli, "REPO", self.repo)
        patch.start()
        self.addCleanup(patch.stop)

    def probes(self, shas):
        for name in ("claude", "grok", "seats"):
            write(self.home / f".agent-shenanigans-probe/{name}.json", json.dumps(
                {"host": name, "passed": True, "written_at": time.time(), "shas": {} if name == "seats" else shas}))

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(list(argv), self.env)
        return code, out.getvalue()

    def test_shas_prints_the_loaded_shas_as_json_and_changes_nothing(self):
        before = sorted(p for p in self.home.rglob("*"))
        code, out = self.run_cli("--shas")
        self.assertEqual((code, json.loads(out)), (0, {"shenanigans": self.head}))
        self.assertEqual(sorted(self.home.rglob("*")), before)
        self.assertFalse((self.repo / "verified.json").exists())

    def test_shas_exits_2_when_a_host_cannot_be_read(self):
        self.grok.write_text("#!/bin/sh\nexit 3\n")
        code, out = self.run_cli("--shas")
        self.assertEqual(code, 2)
        self.assertIn("could-not-check", out)

    def test_accept_refuses_until_probes_record_the_loaded_shas(self):
        self.probes({})
        code, out = self.run_cli("--accept")
        self.assertEqual(code, 1)
        self.assertIn("refused: probe claude is stale", out)
        self.assertIn("refused: probe grok is stale", out)
        self.assertFalse((self.repo / "verified.json").exists())

    def test_accept_then_a_plain_run_is_clean(self):
        self.probes({"shenanigans": self.head})
        code, out = self.run_cli("--accept")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads((self.repo / "verified.json").read_text()), {"shenanigans": self.head})
        self.assertEqual(self.run_cli(), (0, "doctor: clean\n"))

    def test_accept_ignores_a_malformed_verified_json_but_a_plain_run_does_not(self):
        self.probes({"shenanigans": self.head})
        write(self.repo / "verified.json", "{nope")
        self.assertEqual(self.run_cli()[0], 2)
        self.assertEqual(self.run_cli("--accept")[0], 0)
        self.assertEqual(self.run_cli(), (0, "doctor: clean\n"))

    def test_accept_exits_2_when_a_host_cannot_be_read(self):
        self.probes({"shenanigans": self.head})
        self.grok.write_text("#!/bin/sh\nexit 3\n")
        code, out = self.run_cli("--accept")
        self.assertEqual(code, 2)
        self.assertFalse((self.repo / "verified.json").exists())

    def test_an_update_after_accept_shows_as_updated_since_verified(self):
        self.probes({"shenanigans": self.head})
        self.run_cli("--accept")
        write(self.repo / "verified.json", json.dumps({"shenanigans": "c" * 40}))
        code, out = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn("updated-since-verified", out)

    def test_flags_are_mutually_exclusive(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.run_cli("--accept", "--shas")


class CliSeatProbe(unittest.TestCase):
    def test_seat_probe_through_the_cli(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            ok = 'printf "Read\\nGrep\\n"; echo "VERDICT: APPROVED"'
            write(home / "claude.body", ok + "\n")
            write(home / "grok.body", ok + "\n")
            env = {"HOME": str(home), "AGENT_SHENANIGANS_HOME": str(home), "SEATS_CLAUDE_BIN": str(FAKE_SEAT),
                   "SEATS_GROK_BIN": str(FAKE_SEAT), "FAKE_DIR": str(home), "PATH": os.environ["PATH"]}
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cli.main(["--seat-probe"], env)
            self.assertEqual(code, 0, out.getvalue())
            self.assertIn("seat probe passed", out.getvalue())
            self.assertTrue(json.loads((home / ".agent-shenanigans-probe/seats.json").read_text())["passed"])

            write(home / "claude.body", 'printf "Read\\nWrite\\n"; echo "VERDICT: APPROVED"\n')
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli.main(["--seat-probe"], env), 1)
            self.assertIn("seat probe failed", out.getvalue())


if __name__ == "__main__":
    unittest.main()
