import tempfile
import unittest
from pathlib import Path

from doctor.stack import StackError, load_stack

REPO = Path(__file__).resolve().parents[2]


class LoadRepoStack(unittest.TestCase):
    def test_loads_repo_stack(self):
        s = load_stack(REPO / "stack.toml", REPO, {"HOME": "/h"})
        self.assertEqual((len(s.plugins), len(s.links), len(s.settings)), (9, 2, 5))
        self.assertIn(Path("/h/.grok/skills/model-policy"), s.retire_after_probe)
        self.assertEqual(
            s.gated,
            {Path("/h/.claude/commands/code-cleanup.md"): "skills/code-cleanup/SKILL.md:## Hard exclusions"},
        )

    def test_plugin_without_grok_side(self):
        s = load_stack(REPO / "stack.toml", REPO, {"HOME": "/h"})
        dup = next(p for p in s.plugins if p.name == "superpowers-duplicate")
        self.assertEqual((dup.grok_name, dup.grok_state, dup.claude_state), (None, None, "absent"))

    def test_every_enabled_plugin_declares_its_install_commands(self):
        s = load_stack(REPO / "stack.toml", REPO, {"HOME": "/h"})
        for p in s.plugins:
            with self.subTest(p.name):
                self.assertEqual(bool(p.claude_install), p.claude_state == "enabled")
                self.assertEqual(bool(p.grok_install), p.grok_state == "enabled")
        mine = next(p for p in s.plugins if p.name == "agent-shenanigans")
        self.assertIn("{repo}", mine.claude_install)
        self.assertEqual(mine.grok_install, "~/.grok/bin/grok plugin install {repo}")
        self.assertIn("plugin marketplace remove agent-shenanigans", mine.claude_install)

    def test_install_commands_are_optional(self):
        s = load_stack(REPO / "stack.toml", REPO, {"HOME": "/h"})
        dup = next(p for p in s.plugins if p.name == "superpowers-duplicate")
        self.assertEqual((dup.claude_install, dup.grok_install), (None, None))

    def test_links_target_inside_repo(self):
        s = load_stack(REPO / "stack.toml", REPO, {"HOME": "/h"})
        self.assertIn(
            (Path("/h/.claude/rules/agent-shenanigans.md"), REPO / "rules/modes.md"),
            {(link.path, link.target) for link in s.links},
        )

    def test_xdg_config_home_respected(self):
        s = load_stack(REPO / "stack.toml", REPO, {"HOME": "/h", "XDG_CONFIG_HOME": "/x"})
        self.assertIn(Path("/x/caveman/config.json"), {d.file for d in s.settings})

    def test_xdg_config_home_defaults_under_home(self):
        s = load_stack(REPO / "stack.toml", REPO, {"HOME": "/h"})
        self.assertIn(Path("/h/.config/ponytail/config.json"), {d.file for d in s.settings})


class RejectBadStack(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "stack.toml"
            f.write_text(text)
            return load_stack(f, Path(tmp), {"HOME": "/h"})

    def test_rejects_unknown_state(self):
        with self.assertRaisesRegex(StackError, "bad-plugin"):
            self.load('[[plugin]]\nname = "bad-plugin"\nsource = "o/r"\nclaude_id = "a@b"\nclaude_state = "disabled"\n')

    def test_rejects_link_target_outside_repo(self):
        with self.assertRaisesRegex(StackError, "x.md"):
            self.load('[[link]]\npath = "~/x.md"\ntarget = "../outside.md"\n')

    def test_rejects_unknown_setting_format(self):
        with self.assertRaisesRegex(StackError, "mode"):
            self.load('[[setting]]\nfile = "~/s.yaml"\nformat = "yaml"\nkey = "mode"\nvalue = "v"\n')


if __name__ == "__main__":
    unittest.main()
