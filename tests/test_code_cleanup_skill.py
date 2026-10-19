import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills/code-cleanup/SKILL.md"
SLUGS = ["dedup", "types", "dead-code", "cycles", "weak-types", "dead-paths", "autofix",
         "test-hygiene", "ai-slop"]
TIERS = {"autofix": "claude-haiku-5-5", "ai-slop": "claude-haiku-5-5", "cycles": "claude-opus-5-5"}


class CodeCleanupSkillTest(unittest.TestCase):
    def test_safety_rules_ported(self):
        body = SKILL.read_text()
        for s in ["## Hard exclusions", "vendor/ third_party/", "**_pb2.py", "Never start on the default branch",
                  "The boundary outranks the mandate", "Never weaken a guard", "Recovery is not a judgement call",
                  "git submodule status --recursive", "git status --short <every excluded path>",
                  ".claude/commands/code-cleanup.md"]:
            self.assertIn(s, body)

    def test_no_cc_fork(self):
        self.assertNotIn("cc-fork", SKILL.read_text())
        self.assertFalse((REPO / "skills/code-cleanup/scripts/cc-fork").exists())

    def test_spawn_rule(self):
        body = SKILL.read_text()
        for s in ["ultracave", "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "grok-4.7",
                  'effort: "xhigh"', "spawn_subagent"]:
            self.assertIn(s, body)

    def test_every_mandate_has_a_tier(self):
        body = SKILL.read_text()
        for slug in SLUGS:
            model = TIERS.get(slug, "claude-sonnet-5-5")
            self.assertRegex(body, rf"\|\s*`{slug}`\s*\|[^|]*\|\s*`{model}`\s*\|")

    def test_attribution_names_command_only(self):
        body = SKILL.read_text()
        self.assertIn("STRML", body)
        self.assertIn("cc-skills", body)
        self.assertNotRegex(body, r"(?i)vendored verbatim")


if __name__ == "__main__":
    unittest.main()
