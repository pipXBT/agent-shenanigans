import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from doctor import cli
from doctor.hosts import HostState, PluginState, SkillEntry, UserEntry
from doctor.probes import ProbeResult, read_probes
from doctor.report import Finding, build_report, exit_code, render
from doctor.stack import load_stack

REPO = Path(__file__).resolve().parents[2]
HEAD = "a" * 40


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class ReportCase(unittest.TestCase):
    """A synthetic machine that matches stack.toml; each test bends one thing."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.stack = load_stack(REPO / "stack.toml", REPO, {"HOME": str(self.home)})
        self.head, self.verified, self.repo = HEAD, {}, REPO
        self.claude_skills, self.grok_skills, self.claude_users, self.grok_users = [], [], [], []
        self.claude_plugins, self.grok_plugins, self.loaded = {}, {}, {}
        for p in self.stack.plugins:
            sha = HEAD if p.name == "shenanigans" else f"sha-{p.name}"
            if "enabled" in (p.claude_state, p.grok_state):
                self.loaded[p.name] = sha
            if p.claude_state == "enabled":
                self.claude_plugins[p.claude_id] = PluginState("claude", p.claude_id, True, sha, None, False)
            if p.grok_state == "enabled":
                self.grok_plugins[p.grok_name] = PluginState("grok", p.grok_name, True, sha, None, False)
        now = time.time()
        self.probes = {
            name: ProbeResult(name, True, now, "shell" if name == "grok" else None, "", dict(self.loaded))
            for name in ("claude", "grok", "seats")
        }
        for link in self.stack.links:
            link.path.parent.mkdir(parents=True, exist_ok=True)
            link.path.symlink_to(link.target)
        for d in self.stack.settings:
            if d.format == "json":
                write(d.file, json.dumps({d.key: d.value}))
        write(self.home / ".grok/config.toml", '[models]\ndefault = "grok-4.7"\ndefault_reasoning_effort = "xhigh"\n')

    def report(self):
        claude = HostState("claude", self.claude_plugins, tuple(self.claude_skills), tuple(self.claude_users))
        grok = HostState("grok", self.grok_plugins, tuple(self.grok_skills), tuple(self.grok_users))
        return build_report(self.stack, claude, grok, self.probes, self.verified, self.head, self.home, self.repo)

    def kinds(self, findings=None):
        return sorted((f.host, f.kind, f.level) for f in (self.report() if findings is None else findings))


class Drift(ReportCase):
    def test_clean_machine_exits_0(self):
        findings = self.report()
        self.assertEqual(findings, [])
        self.assertEqual(exit_code(findings), 0)

    def test_each_drift_kind_is_drift(self):
        def missing():
            del self.claude_plugins["cc-codemaps@cc-codemaps"]

        def wrong_state():
            self.grok_plugins["caveman"] = PluginState("grok", "caveman", False, "sha-caveman", None, False)

        def host_sha_mismatch():
            self.grok_plugins["ponytail"] = PluginState("grok", "ponytail", True, "other", None, False)

        def updated_since_verified():
            self.verified = {"ponytail": "older"}

        def checkout_drift():
            self.head = "b" * 40

        def shadowed():
            self.grok_skills += [
                SkillEntry("writing-plans", "user", False, "/user:writing-plans"),
                SkillEntry("writing-plans", "plugin: superpowers", False, "/superpowers:writing-plans"),
            ]

        def retired_present():
            (self.home / ".grok/skills/compound").mkdir(parents=True)

        def dead_link():
            self.claude_users.append(UserEntry(self.home / ".claude/skills/handoff", "handoff", True))

        def setting_differs():
            write(self.home / ".grok/config.toml", '[models]\ndefault = "grok-4.6"\ndefault_reasoning_effort = "xhigh"\n')

        def link_missing():
            self.stack.links[0].path.unlink()

        def link_wrong():
            self.stack.links[0].path.unlink()
            self.stack.links[0].path.symlink_to(self.home)

        def grok_daemon_route():
            self.probes["grok"] = ProbeResult("grok", True, time.time(), "daemon", "", dict(self.loaded))

        def generated_js():
            write(self.home / ".grok/workflows/adversarial-verification.js", "x")

        def probe_missing():
            del self.probes["seats"]

        def probe_failing():
            self.probes["seats"] = ProbeResult("seats", False, time.time(), None, "seat wrote a file")

        def probe_stale():
            self.probes["claude"] = ProbeResult("claude", True, time.time(), None, "", {**self.loaded, "ponytail": "older"})

        cases = {
            "missing": missing, "wrong-state": wrong_state, "host-sha-mismatch": host_sha_mismatch,
            "updated-since-verified": updated_since_verified, "checkout-drift": checkout_drift,
            "shadowed": shadowed, "retired-present": retired_present, "dead-link": dead_link,
            "setting-differs": setting_differs, "link-missing": link_missing, "link-wrong": link_wrong,
            "grok-daemon-route": grok_daemon_route, "generated-js": generated_js,
            "probe-missing": probe_missing, "probe-failing": probe_failing, "probe-stale": probe_stale,
        }
        for kind, bend in cases.items():
            with self.subTest(kind):
                self.setUp()
                bend()
                findings = self.report()
                self.assertEqual({(f.kind, f.level) for f in findings}, {(kind, "drift")})
                self.assertEqual(exit_code(findings), 1)

    def test_checkout_drift_when_install_sha_differs_from_head(self):
        self.head = "b" * 40
        self.assertEqual(self.kinds(), [("claude", "checkout-drift", "drift"), ("grok", "checkout-drift", "drift")])

    def test_local_install_sha_matches_on_its_head_part(self):
        self.grok_plugins["shenanigans"] = PluginState("grok", "shenanigans", True, HEAD + "+0123456789ab", None, False)
        self.assertEqual(self.report(), [])

    def test_local_install_hash_suffix_is_not_a_host_mismatch(self):
        self.grok_plugins["ponytail"] = PluginState("grok", "ponytail", True, "sha-ponytail+0123456789ab", None, False)
        self.assertEqual(self.report(), [])

    def test_probe_is_stale_when_a_loaded_sha_changed_since_it_ran(self):
        self.claude_plugins["ponytail@ponytail"] = PluginState("claude", "ponytail@ponytail", True, "newer", None, False)
        self.grok_plugins["ponytail"] = PluginState("grok", "ponytail", True, "newer", None, False)
        self.assertEqual(self.kinds(), [("claude", "probe-stale", "drift"), ("grok", "probe-stale", "drift")])
        self.probes["claude"] = ProbeResult("claude", True, 0, None, "", {**self.loaded, "ponytail": "newer"})
        self.probes["grok"] = ProbeResult("grok", True, 0, "shell", "", {**self.loaded, "ponytail": "newer"})
        self.assertEqual(self.report(), [])  # age does not matter, only the SHAs

    def test_probe_without_recorded_shas_is_stale_but_the_seat_probe_never_is(self):
        self.probes["claude"] = ProbeResult("claude", True, time.time(), None, "")
        self.probes["seats"] = ProbeResult("seats", True, time.time(), None, "")
        self.assertEqual(self.kinds(), [("claude", "probe-stale", "drift")])

    def test_probe_naming_a_plugin_that_is_no_longer_loaded_is_stale(self):
        self.probes["grok"] = ProbeResult("grok", True, time.time(), "shell", "", {**self.loaded, "gone": "abc"})
        self.assertEqual(self.kinds(), [("grok", "probe-stale", "drift")])

    def test_verified_sha_ignores_a_grok_local_install_suffix(self):
        self.grok_plugins["ponytail"] = PluginState("grok", "ponytail", True, "sha-ponytail+0123456789ab", None, False)
        self.verified = {"ponytail": "sha-ponytail"}
        self.assertEqual(self.report(), [])

    def test_generated_js_is_drift(self):
        write(self.home / ".grok/workflows/adversarial-verification.js", "x")
        self.assertEqual(self.kinds(), [("grok", "generated-js", "drift")])

    def test_claude_loaded_grok_plugin_compares_claude_sha(self):
        self.grok_plugins["caveman"] = PluginState("grok", "caveman", True, "native-grok", None, False)
        self.assertEqual(self.kinds(), [("shared", "host-sha-mismatch", "drift")])
        self.grok_skills.append(SkillEntry("ultracave", "plugin: caveman", True, None))
        self.assertEqual(self.report(), [])
        self.verified = {"caveman": "sha-caveman"}
        self.assertEqual(self.report(), [])

    def test_absent_plugin_still_installed_is_wrong_state(self):
        self.claude_plugins["superpowers@superpowers-marketplace"] = PluginState(
            "claude", "superpowers@superpowers-marketplace", False, "x", None, False
        )
        (f,) = self.report()
        self.assertEqual((f.host, f.kind, f.name), ("claude", "wrong-state", "superpowers@superpowers-marketplace"))
        self.assertIn("claude plugin uninstall superpowers@superpowers-marketplace", f.detail)

    def test_retired_after_probe_waits_for_both_spawn_probes(self):
        (self.home / ".grok/skills/model-policy").mkdir(parents=True)
        self.probes["grok"] = ProbeResult("grok", False, time.time(), "shell", "")
        self.assertEqual(self.kinds(), [("grok", "pending-retirement", "info"), ("grok", "probe-failing", "drift")])
        self.probes["grok"] = ProbeResult("grok", True, time.time(), "shell", "", dict(self.loaded))
        self.assertEqual(self.kinds(), [("grok", "retired-present", "drift")])

    def test_gated_path_waits_for_marker_in_repo_skill(self):
        gated = self.home / ".claude/commands/code-cleanup.md"
        write(gated, "x")
        self.repo = self.home / "repo"
        write(self.repo / "skills/code-cleanup/SKILL.md", "# Code cleanup\n")
        self.assertEqual(self.kinds(), [("claude", "pending-retirement", "info")])
        write(self.repo / "skills/code-cleanup/SKILL.md", "# Code cleanup\n## Hard exclusions\n")
        self.assertEqual(self.kinds(), [("claude", "retired-present", "drift")])

    def test_setting_in_unparseable_file_is_could_not_check(self):
        write(self.home / ".grok/config.toml", "[models\n")
        (f,) = self.report()
        self.assertEqual((f.kind, f.level), ("could-not-check", "error"))
        self.assertEqual(exit_code([f]), 2)

    def test_host_that_could_not_be_read_is_skipped(self):
        findings = build_report(self.stack, None, None, self.probes, {}, self.head, self.home, REPO)
        self.assertEqual(findings, [])


class Info(ReportCase):
    def test_unmanaged_is_info(self):
        self.grok_users.append(UserEntry(self.home / ".grok/skills/brandkit", "brandkit", False))
        findings = self.report()
        self.assertEqual(self.kinds(findings), [("grok", "unmanaged", "info")])
        self.assertEqual(exit_code(findings), 0)

    def test_cc_debate_info_until_stamp_then_drift(self):
        self.claude_plugins["debate@cc-debate"] = PluginState("claude", "debate@cc-debate", True, "d", None, False)
        self.grok_plugins["debate"] = PluginState("grok", "debate", True, "d", None, True)
        findings = self.report()
        self.assertEqual(self.kinds(findings), [("claude", "pending-retirement", "info"), ("grok", "pending-retirement", "info")])
        self.assertEqual(exit_code(findings), 0)
        self.probes["seat-dry-run"] = ProbeResult("seat-dry-run", True, time.time(), None, "14/14")
        findings = self.report()
        self.assertEqual(self.kinds(findings), [("claude", "wrong-state", "drift"), ("grok", "wrong-state", "drift")])
        self.assertEqual(exit_code(findings), 1)

    def test_auto_installed_copy_same_sha_is_info(self):
        write(self.home / ".grok/config.toml",
              '[marketplace]\nofficial_marketplace_auto_installed = true\n'
              '[models]\ndefault = "grok-4.7"\ndefault_reasoning_effort = "xhigh"\n')
        write(self.home / ".grok/installed-plugins/registry.json", json.dumps({"repos": {"sp-1": {
            "plugins": {"superpowers": {}}, "marketplace": {"source_display_name": "xAI Official"},
        }}}))
        findings = self.report()
        self.assertEqual(self.kinds(findings), [("grok", "auto-installed", "info")])
        self.assertEqual(exit_code(findings), 0)
        self.grok_plugins["superpowers"] = PluginState("grok", "superpowers", True, "newer", None, False)
        self.assertEqual(self.kinds(), [("shared", "host-sha-mismatch", "drift")])

    def test_retired_dead_entry_is_reported_once(self):
        gone = self.home / ".grok/skills/code-cleanup"
        gone.parent.mkdir(parents=True)
        gone.symlink_to(self.home / "missing")
        self.grok_users.append(UserEntry(gone, "code-cleanup", True))
        self.assertEqual(self.kinds(), [("grok", "retired-present", "drift")])


class Render(unittest.TestCase):
    def test_exit_code_prefers_error_then_drift(self):
        info, drift, error = (Finding("grok", "k", "n", "d", lvl) for lvl in ("info", "drift", "error"))
        self.assertEqual([exit_code(x) for x in ([], [info], [info, drift], [drift, error])], [0, 0, 1, 2])

    def test_render_groups_by_host(self):
        out = render([
            Finding("grok", "missing", "ponytail", "not installed", "drift"),
            Finding("claude", "unmanaged", "foo", "user entry", "info"),
            Finding("grok", "could-not-check", "grok inspect", "boom", "error"),
        ])
        lines = out.splitlines()
        self.assertLess(lines.index("claude"), lines.index("grok"))
        grok = lines[lines.index("grok") + 1:]
        self.assertIn("could-not-check", grok[0])
        self.assertIn("missing", grok[1])
        self.assertIn("1 error, 1 drift, 1 info", out)
        self.assertEqual(render([]), "doctor: clean\n")

    def test_read_probes_reads_the_four_files(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write(d / "grok.json", json.dumps({"host": "grok", "passed": True, "written_at": 5, "route": "daemon", "token_seen": True}))
            write(d / "seat-dry-run.json", json.dumps({"host": "seat-dry-run", "passed": True, "written_at": 6, "detail": "14/14"}))
            got = read_probes(d)
        self.assertEqual(set(got), {"grok", "seat-dry-run"})
        self.assertEqual((got["grok"].route, got["grok"].written_at), ("daemon", 5.0))
        self.assertEqual(got["seat-dry-run"].detail, "14/14")


class Cli(unittest.TestCase):
    def run_cli(self, grok_script, extra_env=None):
        """Run the CLI on an empty home; `grok_script` None means no grok binary at all."""
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            grok = home / ".grok/bin/grok"
            if grok_script is not None:
                write(grok, grok_script)
                grok.chmod(0o755)
            out = io.StringIO()
            env = {"HOME": str(home), "AGENT_SHENANIGANS_HOME": str(home), "GROK_BIN": str(grok), "PATH": os.environ["PATH"],
                   **(extra_env or {})}
            with contextlib.redirect_stdout(out):
                code = cli.main([], env)
        return code, out.getvalue()

    def test_hung_grok_inspect_exits_2(self):
        start = time.monotonic()
        code, out = self.run_cli("#!/bin/sh\nexec sleep 5\n", {"DOCTOR_GROK_TIMEOUT": "0.5"})
        self.assertLess(time.monotonic() - start, 4)
        self.assertEqual(code, 2)
        self.assertIn("could-not-check", out)
        self.assertIn("TimeoutExpired", out)

    def test_inspect_failure_exits_2(self):
        code, out = self.run_cli("#!/bin/sh\necho garbage\n")
        self.assertEqual(code, 2)
        self.assertIn("could-not-check", out)
        self.assertIn("InspectFormatError", out)
        self.assertIn("probe-missing", out)  # the rest of the report still prints

    def test_inspect_nonzero_exit_is_exit_2(self):
        code, out = self.run_cli("#!/bin/sh\nexit 3\n")
        self.assertEqual(code, 2)
        self.assertIn("could-not-check", out)

    def test_missing_grok_binary_is_exit_2(self):
        code, out = self.run_cli(None)
        self.assertEqual(code, 2)
        self.assertIn("could-not-check", out)


if __name__ == "__main__":
    unittest.main()
