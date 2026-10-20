import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STALE = ["cc-fork", "session-learnings", "skills/compound", "commands/init.md", "SKILL.workflow.md",
         "debate-acpx.example.json", "grok/install.sh", "grok/workflows/", "/debate:all",
         "run-plan", "agent-shenanigans:"]


class DocsRefsTest(unittest.TestCase):
    def test_no_stale_references(self):
        paths = [REPO / f for f in ["WORKFLOW.md", "README.md", "AGENTS.md"]] + list((REPO / "skills").rglob("*.md"))
        for p in paths:
            text = p.read_text()
            for s in STALE:
                self.assertNotIn(s, text, f"{p}: {s}")

    def test_manifests_version_and_description(self):
        for f in ["plugin.json", "marketplace.json"]:
            data = (REPO / ".claude-plugin" / f).read_text()
            self.assertIn('"version": "0.2.0"', data, f)
            self.assertIn("execute", data, f)
            self.assertNotIn("run-plan", data, f)
            self.assertNotIn("compound", data, f)

    def test_workflow_names_the_loop(self):
        w = (REPO / "WORKFLOW.md").read_text()
        for s in ["./doctor", "superpowers:brainstorming", "superpowers:writing-plans", "shenanigans:execute",
                  "/update-codemaps", "OWNER-ACCEPTED"]:
            self.assertIn(s, w)

    def test_execute_skill_is_named_execute(self):
        head = (REPO / "skills/execute/SKILL.md").read_text().split("\n---\n", 1)[0]
        self.assertIn("\nname: execute\n", head)
        for s in ["/shenanigans:execute", "/shenanigans:execute --full"]:
            self.assertIn(s, head)
        self.assertFalse((REPO / "skills/run-plan").exists())


if __name__ == "__main__":
    unittest.main()
