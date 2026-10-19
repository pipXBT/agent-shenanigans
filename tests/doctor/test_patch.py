import json
import os
import tempfile
import tomllib
import unittest
from pathlib import Path

from doctor.patch import PatchRefused, grok_config_check, patch_json_key, patch_toml_key

# Shaped like the owner's ~/.grok/config.toml (written here, never read from home).
OWNER = """\
# Grok CLI configuration
# Edited by hand; keep the comments.

[models]
default = "grok-4.6"  # main model
default_reasoning_effort = "xhigh"

[model."grok-4.7"]
# Load-bearing: the larger window.
context_window = 500000

[ui]
fork_secondary_model = "grok-build"
permission_mode = "always-approve"

[profiles.fast]
default = "grok-4.6"
"""


class PatchTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def write(self, name, text):
        path = self.tmp / name
        path.write_text(text)
        return path


class JsonPatch(PatchTest):
    def test_json_patch_keeps_other_keys(self):
        path = self.write("settings.json", '{"b": [1, 2], "effortLevel": "high", "nested": {"x": "é"}}')
        path.chmod(0o640)
        self.assertTrue(patch_json_key(path, "effortLevel", "xhigh"))
        data = json.loads(path.read_text())
        self.assertEqual(data, {"b": [1, 2], "effortLevel": "xhigh", "nested": {"x": "é"}})
        self.assertEqual(list(data), ["b", "effortLevel", "nested"])
        self.assertTrue(path.read_text().endswith("}\n"))
        self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        self.assertEqual(os.listdir(self.tmp), ["settings.json"])
        before = path.read_bytes()
        self.assertFalse(patch_json_key(path, "effortLevel", "xhigh"))
        self.assertEqual(path.read_bytes(), before)

    def test_json_patch_creates_missing_file_and_parents(self):
        path = self.tmp / "config" / "caveman" / "config.json"
        self.assertTrue(patch_json_key(path, "defaultMode", "ultracave"))
        self.assertEqual(path.read_text(), '{\n  "defaultMode": "ultracave"\n}\n')

    def test_json_patch_follows_symlink(self):
        real = self.tmp / "dotfiles/settings.json"
        real.parent.mkdir()
        real.write_text('{"a": 1}')
        link = self.tmp / "settings.json"
        link.symlink_to(real)
        self.assertTrue(patch_json_key(link, "effortLevel", "xhigh"))
        self.assertTrue(link.is_symlink())
        self.assertEqual(json.loads(real.read_text()), {"a": 1, "effortLevel": "xhigh"})


class TomlPatch(PatchTest):
    def test_toml_patch_only_touches_target_table(self):
        path = self.write("c.toml", '[other]\ndefault = "keep"\n\n[models]\ndefault = "old"\n')
        self.assertTrue(patch_toml_key(path, "models", "default", "new"))
        self.assertEqual(path.read_text(), '[other]\ndefault = "keep"\n\n[models]\ndefault = "new"\n')

    def test_toml_patch_inserts_missing_key(self):
        path = self.write("c.toml", '[models]\ndefault = "grok-4.7"\n# about ui\n\n[ui]\nx = "y"\n')
        self.assertTrue(patch_toml_key(path, "models", "default_reasoning_effort", "xhigh"))
        self.assertEqual(
            path.read_text(),
            '[models]\ndefault = "grok-4.7"\ndefault_reasoning_effort = "xhigh"\n# about ui\n\n[ui]\nx = "y"\n',
        )
        eof = self.write("eof.toml", '[models]\ndefault = "a"')
        self.assertTrue(patch_toml_key(eof, "models", "b", "c"))
        self.assertEqual(eof.read_text(), '[models]\ndefault = "a"\nb = "c"\n')

    def test_toml_patch_keeps_comments_and_500k_window(self):
        path = self.write("config.toml", OWNER)
        check = grok_config_check(tomllib.loads(OWNER))
        self.assertTrue(patch_toml_key(path, "models", "default", "grok-4.7", check=check))
        self.assertEqual(
            path.read_text(),
            OWNER.replace('default = "grok-4.6"  # main model', 'default = "grok-4.7"  # main model'),
        )
        after = tomllib.loads(path.read_text())
        self.assertEqual(after["model"]["grok-4.7"]["context_window"], 500000)
        self.assertEqual(after["profiles"]["fast"]["default"], "grok-4.6")
        self.assertFalse(patch_toml_key(path, "models", "default", "grok-4.7", check=check))

    def test_toml_patch_create_table_paths(self):
        path = self.write("config.toml", OWNER)
        with self.assertRaises(PatchRefused):
            patch_toml_key(path, "paths", "extra_rule_dirs", ["/r/rules"])
        self.assertEqual(path.read_text(), OWNER)
        self.assertTrue(patch_toml_key(path, "paths", "extra_rule_dirs", ["/r/rules"], create_table=True))
        self.assertEqual(path.read_text(), OWNER + '\n[paths]\nextra_rule_dirs = ["/r/rules"]\n')
        self.assertFalse(patch_toml_key(path, "paths", "extra_rule_dirs", ["/r/rules"], create_table=True))

    def test_toml_patch_replaces_multiline_value(self):
        path = self.write("c.toml", '[paths]\nextra_rule_dirs = [\n  "/old/a",\n  "/old/b",\n]  # rules\nother = "keep"\n')
        self.assertTrue(patch_toml_key(path, "paths", "extra_rule_dirs", ["/r/rules"]))
        self.assertEqual(path.read_text(), '[paths]\nextra_rule_dirs = ["/r/rules"]  # rules\nother = "keep"\n')

    def test_toml_patch_refuses_when_check_fails(self):
        text = OWNER.replace('default_reasoning_effort = "xhigh"', 'default_reasoning_effort = "high"')
        path = self.write("config.toml", text)
        before = path.read_bytes()
        with self.assertRaises(PatchRefused):
            patch_toml_key(path, "models", "default", "grok-4.7", check=grok_config_check(tomllib.loads(text)))
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(os.listdir(self.tmp), ["config.toml"])

    def test_unparseable_file_raises_and_is_untouched(self):
        for name, text, patch in [
            ("s.json", '{"a": 1,', lambda p: patch_json_key(p, "a", "b")),
            ("c.toml", '[models\ndefault = "x"\n', lambda p: patch_toml_key(p, "models", "default", "y")),
        ]:
            path = self.write(name, text)
            with self.assertRaises(PatchRefused):
                patch(path)
            self.assertEqual(path.read_text(), text)
        with self.assertRaises(PatchRefused):
            patch_toml_key(self.tmp / "missing.toml", "models", "default", "y", create_table=True)
        self.assertFalse((self.tmp / "missing.toml").exists())


if __name__ == "__main__":
    unittest.main()
