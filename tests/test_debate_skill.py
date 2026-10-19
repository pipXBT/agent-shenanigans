import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills/debate/SKILL.md"


def frontmatter(path):
    block = re.match(r"---\n(.*?)\n---\n", path.read_text(), re.S).group(1)
    return {k: v.strip().strip('"') for k, v in re.findall(r"^(\w+):\s*(.*)$", block, re.M)}


class DebateSkillTest(unittest.TestCase):
    def test_description_triggers(self):
        fm = frontmatter(SKILL)
        self.assertEqual(fm["name"], "debate")
        self.assertNotIn("/debate:all", fm["description"])
        self.assertNotIn("run debate", fm["description"].lower())
        self.assertIn("debate the spec", fm["description"])

    def test_body_carries_the_round_rule(self):
        body = SKILL.read_text()
        for s in ["run_seats.py", "summary.json", "plan.sha256", "OWNER-ACCEPTED", "N/<requested>",
                  "never changes a seat's or the round's verdict", "| Persona | Opus | Grok | Agree/split |",
                  "run_in_background", "STRML", "cc-debate"]:
            self.assertIn(s, body)

    def test_no_stale_cc_debate_command_reference(self):
        # A later task scans every skill .md for stale command names.
        self.assertNotIn("/debate:all", SKILL.read_text())

    def test_retired_files_gone(self):
        self.assertFalse((REPO / "skills/debate/SKILL.workflow.md").exists())
        self.assertFalse((REPO / "skills/debate/debate-acpx.example.json").exists())


if __name__ == "__main__":
    unittest.main()
