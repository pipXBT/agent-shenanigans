import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MARKER = re.compile(r"^agent-shenanigans modes [0-9a-f]{16}$")


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    return [REPO / line for line in out.splitlines() if (REPO / line).exists()]


def first_line(path):
    return path.read_text().splitlines()[0]


class ModesFileTest(unittest.TestCase):
    def test_marker_line_format(self):
        self.assertRegex(first_line(REPO / "rules/modes.md"), MARKER)

    def test_token_unique_in_repo(self):
        token = first_line(REPO / "rules/modes.md").split()[-1]
        hits = [p for p in tracked_files() if token in p.read_text(errors="ignore")]
        self.assertEqual(hits, [REPO / "rules/modes.md"])

    def test_required_rules_present(self):
        body = (REPO / "rules/modes.md").read_text()
        for s in ["ultracave", "ponytail", "`full`", "xhigh", "Fable", "Opus 5.5",
                  "skills/ultracave/SKILL.md", "agents this repo starts"]:
            self.assertIn(s, body)
        self.assertTrue(body.rstrip().splitlines()[-1].startswith("- A headless run"))
