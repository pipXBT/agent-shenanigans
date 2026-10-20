import contextlib
import dataclasses
import hashlib
import io
import json
import os
import tempfile
import tomllib
import unittest
from pathlib import Path

from doctor import cli
from doctor.fix import LockHeld, RunFolder, apply_fix, rollback
from doctor.hosts import HostState, PluginState
from doctor.report import Finding, build_report
from doctor.stack import LinkDecl, PluginDecl, SettingDecl, Stack, load_stack

REPO = Path(__file__).resolve().parents[2]

# Shaped like the owner's ~/.grok/config.toml; both [models] keys are off so each
# patch has to pass the config check with the other still pending.
GROK_CFG = """\
# Grok CLI configuration
[models]
default = "grok-4.6"  # main model
default_reasoning_effort = "high"

[model."grok-4.7"]
context_window = 500000

[ui]
fork_secondary_model = "grok-build"
"""


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plugin(name, claude_id=None, grok_name=None, claude_state=None, grok_state=None, claude_install=None, grok_install=None):
    return PluginDecl(name, f"owner/{name}", claude_id, grok_name, claude_state, grok_state, None, claude_install, grok_install)


def tree(root: Path) -> dict[Path, tuple]:
    """Every regular file and symlink under `root`: ("file", bytes) or ("link", target)."""
    found = {}
    for d, dirs, names in os.walk(root):
        for n in dirs + names:
            p = Path(d) / n
            if p.is_symlink():
                found[p] = ("link", os.readlink(p))
            elif p.is_file():
                found[p] = ("file", p.read_bytes())
    return found


class FixCase(unittest.TestCase):
    """A fake home and a fake repo; nothing outside the temp dir is touched."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.home, self.repo = root / "home", root / "repo"
        h = self.home
        self.backup = h / ".agent-shenanigans-backup"
        write(self.repo / "rules/modes.md", "agent-shenanigans modes 0123abcd\n")
        write(self.repo / "skills/code-cleanup/SKILL.md", "# code-cleanup\n")
        self.cfg = h / ".grok/config.toml"
        write(self.cfg, GROK_CFG)
        write(h / ".claude/settings.json", '{"effortLevel": "high", "outputStyle": "Terse"}\n')
        self.link = h / ".claude/rules/agent-shenanigans.md"
        self.rhai = h / ".grok/workflows/adversarial-verification.rhai"
        self.stack = Stack(
            plugins=(
                plugin(
                    "shenanigans", "shenanigans@agent-shenanigans", "shenanigans", "enabled", "enabled",
                    "claude plugin marketplace remove agent-shenanigans; claude plugin marketplace add {repo} && claude plugin install shenanigans@agent-shenanigans",
                    "~/.grok/bin/grok plugin install {repo}",
                ),
                plugin("ponytail", "ponytail@ponytail", "ponytail", "enabled", "enabled",
                       "claude plugin install ponytail@ponytail", "~/.grok/bin/grok plugin install DietrichGebert/ponytail"),
                plugin("caveman", "caveman@caveman", "caveman", "enabled", "enabled",
                       "claude plugin install caveman@caveman", "~/.grok/bin/grok plugin install JuliusBrussee/caveman"),
                plugin("cc-codemaps", "cc-codemaps@cc-codemaps", "cc-codemaps", "enabled", "enabled"),
                plugin("explanatory", "explanatory-output-style@claude-code-plugins", "explanatory-output-style", "absent", "absent"),
                plugin("native-old", None, "native-old", None, "absent"),
            ),
            links=(
                LinkDecl(self.link, self.repo / "rules/modes.md"),
                LinkDecl(self.rhai, self.repo / "workflows/adversarial-verification.rhai"),
            ),
            retire=(h / ".grok/skills/compound", h / ".claude/commands/init.md"),
            retire_after_probe=(h / ".grok/skills/model-policy",),
            gated={h / ".claude/commands/code-cleanup.md": "skills/code-cleanup/SKILL.md:## Hard exclusions"},
            settings=(
                SettingDecl(h / ".config/caveman/config.json", "json", None, "defaultMode", "ultracave"),
                SettingDecl(h / ".config/ponytail/config.json", "json", None, "defaultMode", "full"),
                SettingDecl(self.cfg, "toml", "models", "default", "grok-4.7"),
                SettingDecl(self.cfg, "toml", "models", "default_reasoning_effort", "xhigh"),
                SettingDecl(h / ".claude/settings.json", "json", None, "effortLevel", "xhigh"),
            ),
        )
        self.calls, self.losers = [], set()

    def resolves(self, host, name):
        self.calls.append((host, name))
        return name not in self.losers

    def fix(self, findings=(), run_id="r1"):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), RunFolder(self.backup, run_id) as run:
            commands = apply_fix(self.stack, list(findings), self.home, self.repo, run, self.resolves)
        return commands, out.getvalue()

    def manifest(self, run_id="r1"):
        f = self.backup / run_id / "manifest.tsv"
        return [line.split("\t") for line in f.read_text().splitlines()] if f.exists() else []

    def actions(self, run_id="r1"):
        return [(a, Path(live)) for a, live, _, _ in self.manifest(run_id)]

    def probe(self, name, **fields):
        write(self.home / f".agent-shenanigans-probe/{name}.json", json.dumps({"host": name, "written_at": 1, **fields}))

    def skill(self, rel, text=None):
        write(self.home / rel / "SKILL.md", text or f"user copy of {rel}\n")
        return self.home / rel


class RunFolderTest(FixCase):
    def test_run_folder_records_preimage_and_manifest(self):
        f = self.home / ".claude/settings.json"
        with RunFolder(self.backup, "a") as run:
            stored = run.preimage(f)
            self.assertEqual(stored, self.backup / "a/.claude/settings.json")
            self.assertEqual(stored.read_text(), f.read_text())
            f.write_text("after\n")
            run.record("patched", f, stored)
            again = run.preimage(f)  # a second change in the same run gets its own pre-image
            self.assertEqual(again, self.backup / "a/.claude/settings.json~1")
            self.assertEqual(again.read_text(), "after\n")
            gone = self.skill(".grok/skills/compound")
            moved = run.move_aside(gone)
            run.record("moved", gone, moved)
        self.assertEqual(moved, self.backup / "a/.grok/skills/compound")
        self.assertFalse(gone.exists())
        self.assertEqual(self.manifest("a"), [
            ["patched", str(f), str(stored), sha(b"after\n")],
            ["moved", str(gone), str(moved), "-"],
        ])

    def test_second_fix_while_locked(self):
        with RunFolder(self.backup, "a"):
            with self.assertRaises(LockHeld):
                RunFolder(self.backup, "b").__enter__()
        with RunFolder(self.backup, "b"):  # released on exit
            pass


class Fix(FixCase):
    def test_link_created_and_real_file_moved_first(self):
        write(self.link, "my own rules\n")
        self.fix()
        self.assertTrue(self.link.is_symlink())
        self.assertEqual(os.readlink(self.link), str(self.repo / "rules/modes.md"))
        self.assertEqual((self.backup / "r1/.claude/rules/agent-shenanigans.md").read_text(), "my own rules\n")
        mine = [a for a in self.actions() if a[1] == self.link]
        self.assertEqual(mine, [("moved", self.link), ("linked", self.link)])

    def test_link_skipped_when_target_missing(self):
        write(self.rhai, "generated\n")
        _, out = self.fix()
        self.assertFalse(self.rhai.is_symlink())
        self.assertEqual(self.rhai.read_text(), "generated\n")
        self.assertNotIn(self.rhai, [live for _, live in self.actions()])
        self.assertIn(str(self.rhai), out)

    def test_retire_moves_with_relative_path(self):
        compound = self.skill(".grok/skills/compound", "old compound\n")
        init = self.home / ".claude/commands/init.md"
        init.parent.mkdir(parents=True)
        init.symlink_to(self.home / "cc-skills/commands/init.md")  # dead link into a clone: moved, never followed
        self.fix()
        self.assertFalse(os.path.lexists(compound))
        self.assertEqual((self.backup / "r1/.grok/skills/compound/SKILL.md").read_text(), "old compound\n")
        self.assertFalse(os.path.lexists(init))
        self.assertTrue((self.backup / "r1/.claude/commands/init.md").is_symlink())
        self.assertIn(("moved", compound), self.actions())

    def test_after_probe_retire_waits_for_both_spawn_probes(self):
        policy = self.skill(".grok/skills/model-policy")
        self.probe("claude", passed=True)
        _, out = self.fix(run_id="r1")
        self.assertTrue(policy.exists())
        self.assertIn(str(policy), out)
        self.probe("grok", passed=True)
        self.losers = {"debate"}
        self.fix(run_id="r2")
        self.assertTrue(policy.exists())
        self.assertIn(("grok", "debate"), self.calls)
        self.losers = set()
        self.fix(run_id="r3")
        self.assertFalse(policy.exists())
        self.assertIn(("moved", policy), self.actions("r3"))

    def test_gated_collision_waits_for_marker_in_repo_skill(self):
        cmd = self.home / ".claude/commands/code-cleanup.md"
        write(cmd, "old command\n")
        shadow = [Finding("claude", "shadowed", "code-cleanup", f"{cmd} wins", "drift")]
        _, out = self.fix(shadow, run_id="r1")
        self.assertEqual(cmd.read_text(), "old command\n")
        self.assertIn(str(cmd), out)
        write(self.repo / "skills/code-cleanup/SKILL.md", "# code-cleanup\n\n## Hard exclusions\n")
        self.fix(shadow, run_id="r2")
        self.assertFalse(cmd.exists())
        self.assertEqual(sorted(self.calls), [("claude", "code-cleanup"), ("grok", "code-cleanup")])

    def test_collision_moved_back_when_source_does_not_win(self):
        wp = self.skill(".grok/skills/writing-plans", "mine\n")
        self.losers = {"writing-plans"}
        self.fix([Finding("grok", "shadowed", "writing-plans", "user copy wins", "drift")])
        self.assertEqual((wp / "SKILL.md").read_text(), "mine\n")
        self.assertEqual([a for a in self.actions() if a[1] == wp], [("moved", wp), ("moved-back", wp)])
        self.assertEqual(self.calls, [("grok", "writing-plans")])

    def test_collision_stays_moved_when_source_wins(self):
        wp = self.skill(".grok/skills/writing-plans")
        brain = self.skill(".claude/skills/brainstorming")
        self.fix([
            Finding("grok", "shadowed", "writing-plans", "user copy wins", "drift"),
            Finding("claude", "shadowed", "brainstorming", "user copy wins", "drift"),
        ])
        self.assertFalse(wp.exists())
        self.assertFalse(brain.exists())
        self.assertTrue((self.backup / "r1/.grok/skills/writing-plans/SKILL.md").exists())
        # Grok reads ~/.claude too, so a ~/.claude move must resolve on both hosts.
        self.assertEqual(sorted(self.calls), [("claude", "brainstorming"), ("grok", "brainstorming"), ("grok", "writing-plans")])

    def test_mode_config_created_when_absent(self):
        ponytail = self.home / ".config/ponytail/config.json"
        write(ponytail, '{"defaultMode": "lite", "other": 1}')
        self.fix()
        caveman = self.home / ".config/caveman/config.json"
        self.assertEqual(json.loads(caveman.read_text()), {"defaultMode": "ultracave"})
        self.assertEqual(json.loads(ponytail.read_text()), {"defaultMode": "full", "other": 1})
        rows = {(a, Path(live)): stored for a, live, stored, _ in self.manifest()}
        self.assertEqual(rows[("created", caveman)], "-")
        self.assertEqual(Path(rows[("patched", ponytail)]).read_text(), '{"defaultMode": "lite", "other": 1}')

    def test_grok_config_patched_one_key_at_a_time(self):
        self.fix()
        cfg = tomllib.loads(self.cfg.read_text())
        self.assertEqual(cfg["models"], {"default": "grok-4.7", "default_reasoning_effort": "xhigh"})
        self.assertIn('default = "grok-4.7"  # main model', self.cfg.read_text())
        self.assertNotIn("paths", cfg)
        self.assertNotIn("features", cfg)
        self.assertEqual([a for a in self.actions() if a[1] == self.cfg], [("patched", self.cfg)] * 2)

    def test_missing_grok_config_is_reported_and_fix_moves_on(self):
        self.cfg.rename(self.home / "elsewhere.toml")
        _, out = self.fix()
        self.assertFalse(self.cfg.exists())
        self.assertIn(str(self.cfg), out)
        self.assertIn(("patched", self.home / ".claude/settings.json"), self.actions())

    def test_extra_rule_dirs_set_when_grok_probe_lacks_token(self):
        self.probe("grok", passed=False, token_seen=False)
        self.fix()
        cfg = tomllib.loads(self.cfg.read_text())
        self.assertEqual(cfg["paths"], {"extra_rule_dirs": [str(self.repo / "rules")]})
        self.assertEqual(cfg["model"]["grok-4.7"]["context_window"], 500000)

    def test_subagent_inheritance_off_when_probe_reports_model_rejected(self):
        self.cfg.write_text(GROK_CFG + "\n[features]\nfoo = true\n")
        self.probe("grok", passed=True, token_seen=True, model_param_rejected=True)
        self.fix()
        cfg = tomllib.loads(self.cfg.read_text())
        self.assertEqual(cfg["features"], {"foo": True, "subagent_model_inheritance": False})
        self.assertNotIn("paths", cfg)

    def test_features_table_is_created_when_probe_reports_model_rejected(self):
        self.probe("grok", passed=True, model_param_rejected=True)
        _, out = self.fix()
        cfg = tomllib.loads(self.cfg.read_text())
        self.assertEqual(cfg["features"], {"subagent_model_inheritance": False})
        self.assertNotIn("paths", cfg)
        self.assertNotIn("features", out)
        self.assertEqual(rollback(self.backup, "r1"), [])  # the created table goes with the rollback
        self.assertEqual(self.cfg.read_text(), GROK_CFG)

    def test_other_missing_tables_are_still_not_created(self):
        stack = dataclasses.replace(self.stack, settings=(SettingDecl(self.cfg, "toml", "telemetry", "enabled", False),))
        with contextlib.redirect_stdout(io.StringIO()) as out, RunFolder(self.backup, "r1") as run:
            apply_fix(stack, [], self.home, self.repo, run, self.resolves)
        self.assertNotIn("telemetry", tomllib.loads(self.cfg.read_text()))
        self.assertIn("no [telemetry] table", out.getvalue())

    def test_plugin_commands_printed_in_order(self):
        grok = self.home / ".grok/bin/grok"
        commands, out = self.fix([
            Finding("grok", "wrong-state", "caveman", "installed but disabled", "drift"),
            Finding("claude", "missing", "shenanigans@agent-shenanigans", "not installed", "drift"),
            Finding("grok", "missing", "ponytail", "not installed", "drift"),
            Finding("claude", "wrong-state", "explanatory-output-style@claude-code-plugins", "installed, declared absent", "drift"),
            Finding("grok", "wrong-state", "explanatory-output-style", "loaded from the Claude install, declared absent", "drift"),
            Finding("grok", "wrong-state", "native-old", "installed, declared absent", "drift"),
            Finding("claude", "wrong-state", "cc-codemaps@cc-codemaps", "installed but disabled", "drift"),
            Finding("grok", "checkout-drift", "shenanigans", "installed a2b97fa, checkout HEAD a1d50e4", "drift"),
            Finding("claude", "missing", "caveman@caveman", "not installed", "drift"),
        ])
        self.assertEqual(commands, [
            "claude plugin uninstall explanatory-output-style@claude-code-plugins",
            f"{grok} plugin uninstall native-old",
            f"{grok} plugin uninstall shenanigans",
            f"claude plugin marketplace remove agent-shenanigans; claude plugin marketplace add {self.repo} && "
            "claude plugin install shenanigans@agent-shenanigans",
            "~/.grok/bin/grok plugin install DietrichGebert/ponytail",
            f"~/.grok/bin/grok plugin install {self.repo}",
            "claude plugin install caveman@caveman",
            f"{grok} plugin enable caveman",
            "claude plugin enable cc-codemaps@cc-codemaps",
            "re-run ./doctor --fix",
        ])
        self.assertNotIn("_install", out)

    def test_repo_stack_moves_an_install_off_the_old_plugin_name(self):
        self.stack = load_stack(REPO / "stack.toml", REPO, {"HOME": str(self.home)})
        old_id, old_name = "agent-shenanigans@agent-shenanigans", "agent-shenanigans"
        claude = HostState("claude", {old_id: PluginState("claude", old_id, True, "s", None, False)}, (), ())
        grok = HostState("grok", {old_name: PluginState("grok", old_name, True, "s", None, False)}, (), ())
        commands, _ = self.fix(build_report(self.stack, claude, grok, {}, {}, None, self.home, self.repo))
        self.assertEqual([c for c in commands if "shenanigans" in c or str(self.repo) in c], [
            "claude plugin uninstall agent-shenanigans@agent-shenanigans",
            f"{self.home / '.grok/bin/grok'} plugin uninstall agent-shenanigans",
            f"claude plugin marketplace remove agent-shenanigans; claude plugin marketplace add {self.repo} && "
            "claude plugin install shenanigans@agent-shenanigans",
            f"~/.grok/bin/grok plugin install {self.repo} --trust",
        ])

    def test_install_command_is_the_declared_text_not_derived_from_source(self):
        commands, _ = self.fix([Finding("claude", "missing", "ponytail@ponytail", "not installed", "drift")])
        self.assertEqual(commands, ["claude plugin install ponytail@ponytail", "re-run ./doctor --fix"])
        self.assertNotIn("owner/ponytail", " ".join(commands))

    def test_repo_path_with_a_space_is_quoted(self):
        spaced = self.home / "my repo"
        out = io.StringIO()
        with contextlib.redirect_stdout(out), RunFolder(self.backup, "r1") as run:
            commands = apply_fix(
                self.stack, [Finding("grok", "missing", "shenanigans", "not installed", "drift")],
                self.home, spaced, run, self.resolves,
            )
        self.assertEqual(commands[0], f"~/.grok/bin/grok plugin install '{spaced}'")

    def test_missing_plugin_with_no_declared_install_is_reported_not_guessed(self):
        commands, out = self.fix([Finding("grok", "missing", "cc-codemaps", "not installed", "drift")])
        self.assertEqual(commands, [])
        self.assertIn("cc-codemaps: no grok_install command in stack.toml", out)

    def test_no_commands_when_plugins_match(self):
        commands, _ = self.fix([Finding("grok", "unmanaged", "foo", "x", "info")])
        self.assertEqual(commands, [])


class Rollback(FixCase):
    def test_rollback_restores_patched_and_moves_created_aside(self):
        settings = self.home / ".claude/settings.json"
        before_settings, before_cfg = settings.read_bytes(), self.cfg.read_bytes()
        compound = self.skill(".grok/skills/compound", "old compound\n")
        self.fix()
        self.assertEqual(rollback(self.backup, "r1"), [])
        self.assertEqual(settings.read_bytes(), before_settings)
        self.assertEqual(self.cfg.read_bytes(), before_cfg)  # two patches undone in reverse
        self.assertEqual((compound / "SKILL.md").read_text(), "old compound\n")
        caveman = self.home / ".config/caveman/config.json"
        self.assertFalse(os.path.lexists(caveman))
        self.assertEqual(json.loads((self.backup / "r1/.config/caveman/config.json").read_text()), {"defaultMode": "ultracave"})
        self.assertFalse(os.path.lexists(self.link))
        self.assertTrue((self.backup / "r1/.claude/rules/agent-shenanigans.md").is_symlink())

    def test_rollback_of_earlier_run_after_later_one(self):
        settings = self.home / ".claude/settings.json"
        original = settings.read_bytes()
        self.fix(run_id="r1")
        after_r1 = settings.read_bytes()
        extra = SettingDecl(settings, "json", None, "outputStyle", "Plain")
        self.stack = dataclasses.replace(self.stack, settings=self.stack.settings + (extra,))
        self.fix(run_id="r2")
        self.assertEqual(self.actions("r2"), [("patched", settings)])
        self.assertEqual(rollback(self.backup, "r2"), [])
        self.assertEqual(settings.read_bytes(), after_r1)
        self.assertEqual(rollback(self.backup, "r1"), [])
        self.assertEqual(settings.read_bytes(), original)

    def test_rollback_never_writes_through_symlink(self):
        settings = self.home / ".claude/settings.json"
        before = settings.read_bytes()
        self.fix()
        other = self.home / "dotfiles/settings.json"
        write(other, settings.read_text())
        written = other.read_bytes()
        settings.rename(self.home / "fixed-copy.json")
        settings.symlink_to(other)
        self.assertEqual(rollback(self.backup, "r1"), [])
        self.assertEqual(other.read_bytes(), written)
        self.assertFalse(settings.is_symlink())
        self.assertEqual(settings.read_bytes(), before)
        kept = [p for p in self.backup.rglob("settings.json*") if p.is_symlink()]
        self.assertEqual([os.readlink(p) for p in kept], [str(other)])

    def test_rollback_skips_changed_file_and_continues(self):
        settings = self.home / ".claude/settings.json"
        compound = self.skill(".grok/skills/compound")
        self.fix()
        settings.write_text('{"effortLevel": "max"}\n')
        skipped = rollback(self.backup, "r1")
        self.assertEqual(len(skipped), 1)
        self.assertIn(str(settings), skipped[0])
        self.assertEqual(settings.read_text(), '{"effortLevel": "max"}\n')
        self.assertTrue(compound.exists())
        self.assertEqual(self.cfg.read_text(), GROK_CFG)

    def test_rollback_unknown_run(self):
        with self.assertRaises(FileNotFoundError):
            rollback(self.backup, "nope")
        with self.assertRaises(FileNotFoundError):
            rollback(self.backup, "..")

    def test_nothing_is_ever_deleted(self):
        write(self.link, "my rules\n")
        self.skill(".grok/skills/compound")
        self.skill(".grok/skills/model-policy")
        self.skill(".grok/skills/writing-plans")
        self.skill(".grok/skills/skill-postmortem")
        self.skill(".claude/skills/brainstorming")
        write(self.home / ".claude/commands/code-cleanup.md", "old command\n")
        write(self.repo / "skills/code-cleanup/SKILL.md", "## Hard exclusions\n")
        write(self.home / ".config/ponytail/config.json", '{"defaultMode": "lite"}')
        self.probe("claude", passed=True)
        self.probe("grok", passed=True, token_seen=False)
        self.losers = {"writing-plans"}
        shadow = [Finding("grok", "shadowed", n, "x", "drift") for n in ("writing-plans", "skill-postmortem")]
        shadow.append(Finding("claude", "shadowed", "brainstorming", "x", "drift"))
        before = tree(self.home)

        def all_kept(stage):
            after = set(tree(self.home).values())
            for p, item in before.items():
                self.assertIn(item, after, f"{stage}: {p}")

        self.fix(shadow)
        self.assertIn(("moved-back", self.home / ".grok/skills/writing-plans"), self.actions())
        all_kept("after fix")
        self.assertEqual(rollback(self.backup, "r1"), [])
        all_kept("after rollback")
        src = (REPO / "lib/doctor/fix.py").read_text()
        self.assertNotRegex(src, r"unlink|rmtree|rmdir|os\.remove")


class Cli(unittest.TestCase):
    def test_fix_and_rollback_through_the_cli(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            grok = home / ".grok/bin/grok"
            write(grok, "#!/bin/sh\nprintf '  Skills (0)\\n\\n  Plugins (0)\\n'\n")
            grok.chmod(0o755)
            write(home / ".grok/config.toml", GROK_CFG)
            env = {"HOME": str(home), "AGENT_SHENANIGANS_HOME": str(home), "GROK_BIN": str(grok), "PATH": os.environ["PATH"]}
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cli.main(["--fix"], env)
            self.assertEqual(code, 0, out.getvalue())
            caveman = home / ".config/caveman/config.json"
            self.assertTrue(caveman.exists())
            self.assertIn("re-run ./doctor --fix", out.getvalue())
            (run_id,) = [p.name for p in (home / ".agent-shenanigans-backup").iterdir() if not p.name.startswith(".")]
            self.assertRegex(run_id, r"^\d{4}-\d{2}-\d{2}T\d{6}$")
            with contextlib.redirect_stdout(io.StringIO()):
                with RunFolder(home / ".agent-shenanigans-backup", "held"):
                    self.assertEqual(cli.main(["--fix"], env), 2)
                    self.assertEqual(cli.main(["--rollback", run_id], env), 2)
                self.assertEqual(cli.main(["--rollback", run_id], env), 0)
                self.assertEqual(cli.main(["--rollback", "no-such-run"], env), 2)
            self.assertFalse(caveman.exists())


if __name__ == "__main__":
    unittest.main()
