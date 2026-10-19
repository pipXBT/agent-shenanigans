import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from doctor.hosts import (
    InspectFormatError,
    local_install_sha,
    parse_grok_inspect,
    read_claude,
    read_grok,
    run_grok_inspect,
    user_entries,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "grok_inspect.txt"

INSPECT = (
    "  Skills (1)\n"
    "  └ caveman      plugin: caveman [claude]\n"
    "\n"
    "  Plugins (3)\n"
    "  └ caveman (user, enabled)       1 skills\n"
    "  └ ponytail (user, enabled)      1 skills\n"
    "  └ cc-codemaps (user, disabled)  1 skills\n"
)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def git_repo(path):
    """Make a one-commit repo at `path` and return its HEAD."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-q", "--allow-empty", "-m", "x"],
        check=True,
    )
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


class FakeHome(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        env = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
        env.start()
        self.addCleanup(env.stop)

    def claude(self, shas, enabled):
        write_json(self.home / ".claude/plugins/installed_plugins.json", {"version": 2, "plugins": {
            pid: [{"scope": "user", "installPath": str(self.home / "cache" / pid), "gitCommitSha": sha}]
            for pid, sha in shas.items()
        }})
        write_json(self.home / ".claude/settings.json", {"enabledPlugins": enabled})


class ReadClaude(FakeHome):
    def test_read_claude_uses_gitCommitSha(self):
        self.claude({"caveman@caveman": "c0ffee"}, {"caveman@caveman": True})
        p = read_claude(self.home).plugins["caveman@caveman"]
        self.assertEqual((p.host, p.sha, p.path), ("claude", "c0ffee", self.home / "cache/caveman@caveman"))

    def test_claude_enabled_from_settings(self):
        self.claude({"on@m": "1", "off@m": "2", "unset@m": "3"}, {"on@m": True, "off@m": False})
        for pid in ("on@m", "off@m"):
            (self.home / "cache" / pid / "skills" / f"skill-{pid[:-2]}").mkdir(parents=True)
        (self.home / "cache/on@m/commands").mkdir()
        (self.home / "cache/on@m/commands/cmd.md").write_text("x")
        state = read_claude(self.home)
        self.assertEqual({k: p.enabled for k, p in state.plugins.items()},
                         {"on@m": True, "off@m": False, "unset@m": False})
        self.assertEqual({(s.name, s.source) for s in state.skills}, {("skill-on", "plugin: on"), ("cmd", "plugin: on")})


class ParseInspect(unittest.TestCase):
    def test_parse_grok_inspect_skills_and_collisions(self):
        skills, plugins = parse_grok_inspect(FIXTURE.read_text())
        wp = [s for s in skills if s.name == "writing-plans"]
        self.assertIn(("user", "/user:writing-plans"), {(s.source, s.collides_to) for s in wp})
        self.assertIn(("plugin: superpowers", "/superpowers:writing-plans"), {(s.source, s.collides_to) for s in wp})
        self.assertTrue(plugins["explanatory-output-style"])
        cave = next(s for s in skills if s.name == "ultracave")
        self.assertEqual((cave.source, cave.via_claude, cave.collides_to), ("plugin: caveman", True, None))
        self.assertEqual(len(skills), 18)
        self.assertEqual(len(plugins), 6)

    def test_parse_grok_inspect_rejects_unknown_layout(self):
        with self.assertRaises(InspectFormatError):
            parse_grok_inspect("Skills (2)\n  * foo  something new\n")
        with self.assertRaises(InspectFormatError):
            parse_grok_inspect("Skills (0)\n")


class ReadGrok(FakeHome):
    def grok(self):
        cave = self.home / ".grok/installed-plugins/caveman-1"
        copy = self.home / ".grok/installed-plugins/skills-1"
        src = self.home / ".grok/marketplace-cache/x"
        (copy / "ponytail").mkdir(parents=True)
        (copy / "ponytail/SKILL.md").write_text("lazy")
        heads = git_repo(cave), git_repo(src)
        (src / "skills").mkdir()
        write_json(self.home / ".grok/installed-plugins/registry.json", {"version": 1, "repos": {
            "caveman-1": {"kind": {"type": "Git", "url": "u", "commit": "0" * 40},
                          "path": str(cave), "plugins": {"caveman": {}}},
            "skills-1": {"kind": {"type": "Local", "source_path": str(src / "skills")},
                         "path": str(copy), "plugins": {"ponytail": {}}},
        }})
        self.claude({"caveman@caveman": "c1aude", "cc-codemaps@cc-codemaps": "c0de"}, {})
        return read_grok(self.home, INSPECT), heads, copy, src / "skills"

    def test_grok_git_install_sha_uses_rev_parse_not_registry(self):
        state, (head, _), _, _ = self.grok()
        p = state.plugins["caveman"]
        self.assertEqual((p.host, p.sha, p.enabled, p.via_claude), ("grok", head, True, False))

    def test_grok_local_install_sha(self):
        state, _, copy, src = self.grok()
        self.assertEqual(state.plugins["ponytail"].sha, local_install_sha(copy, src))

    def test_grok_claude_plugin_takes_claude_sha(self):
        state, _, _, _ = self.grok()
        p = state.plugins["cc-codemaps"]
        self.assertEqual((p.sha, p.enabled, p.via_claude), ("c0de", False, True))
        self.assertEqual(p.path, self.home / "cache/cc-codemaps@cc-codemaps")

    def test_local_install_sha_combines_source_head_and_content_hash(self):
        head = git_repo(self.home / "src")
        (self.home / "src/skills").mkdir()
        copy = self.home / "copy"
        (copy / "a").mkdir(parents=True)
        (copy / "a/SKILL.md").write_text("x")
        before = local_install_sha(copy, self.home / "src/skills")
        (copy / "a/SKILL.md").write_text("y")
        after = local_install_sha(copy, self.home / "src/skills")
        self.assertRegex(before, rf"^{head}\+[0-9a-f]{{12}}$")
        self.assertEqual(before.split("+")[0], after.split("+")[0])
        self.assertNotEqual(before, after)


class RunGrokInspect(FakeHome):
    def test_run_grok_inspect_times_out(self):
        grok = self.home / "grok"
        grok.write_text("#!/bin/bash\nexec sleep 5\n")
        grok.chmod(0o755)
        start = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            run_grok_inspect(grok, self.home, timeout=0.5)
        self.assertLess(time.monotonic() - start, 2)


class UserEntries(FakeHome):
    def test_user_entries_flags_dead_link(self):
        skills, grok = self.home / ".claude/skills", self.home / ".grok/skills"
        (skills / "good").mkdir(parents=True)
        (skills / "good/SKILL.md").write_text("x")
        (skills / ".trash").mkdir()
        (skills / "gone").symlink_to(self.home / "missing")
        (grok / "half").mkdir(parents=True)
        (grok / "half/SKILL.md").symlink_to(self.home / "missing.md")
        (self.home / ".claude/commands").mkdir()
        (self.home / ".claude/commands/init.md").write_text("x")
        self.assertEqual(
            {(e.name, e.dead) for e in user_entries(self.home)},
            {("good", False), ("gone", True), ("half", True), ("init", False)},
        )


if __name__ == "__main__":
    unittest.main()
