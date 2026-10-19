"""Static checks on the Grok executor, workflows/adversarial-verification.rhai.

Grok runs the script itself; these tests read its source for the rules in
workflows/CONTRACT.md that a text check can prove.
"""

import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RHAI = REPO / "workflows/adversarial-verification.rhai"
CONTRACT = REPO / "workflows/CONTRACT.md"
HELPER = "call_agent"  # `call` is a reserved word in Rhai


def src():
    return RHAI.read_text()


def helper_body():
    m = re.search(rf"^fn {HELPER}\(.*?^\}}", src(), re.S | re.M)
    assert m, f"no fn {HELPER}"
    return m.group(0), m.start(), m.end()


def contract_labels():
    table = CONTRACT.read_text().split("### Labels", 1)[1].split("###", 1)[0]
    return set(re.findall(r"^\| `([a-z-]+)` \|", table, re.M))


class RhaiStaticTest(unittest.TestCase):
    def test_no_banned_constructs(self):
        text = src()
        for s in ["HEAD~1", "resume_from", "reset --hard", "git stash"]:
            self.assertFalse(s in text, s)

    def test_modes_say_ultracave(self):
        self.assertTrue("ultracave" in src())

    def test_modes_equal_rules_file(self):
        body = (REPO / "rules/modes.md").read_text().split("\n", 1)[1].strip()
        m = re.search(r'^const MODES = ("(?:\\.|[^"\\])*");$', src(), re.M)
        self.assertTrue(m, "no const MODES string")
        self.assertEqual(json.loads(m.group(1)), body)

    def test_agent_only_called_in_helper(self):
        calls = [m.start() for m in re.finditer(r"\bagent\(", src())]
        self.assertEqual(len(calls), 1, calls)
        _, start, end = helper_body()
        self.assertTrue(start < calls[0] < end)

    def test_helper_passes_grok_model(self):
        self.assertTrue(re.search(r'(?m)^const GROK_MODEL = "grok-4\.7";$', src()))
        body, _, _ = helper_body()
        self.assertIn("model: global::GROK_MODEL", body)

    def test_meta_is_first_statement_and_literal(self):
        lines = [l for l in src().splitlines() if l.strip() and not l.lstrip().startswith("//")]
        self.assertTrue(lines[0].startswith("let meta = #{"), lines[0])
        block = src().split("let meta = ", 1)[1].split("\n};", 1)[0] + "}"
        rest = re.sub(r'"(?:\\.|[^"\\])*"', "", block)
        rest = re.sub(r"\b[a-z_]+\s*:", "", rest)
        self.assertRegex(rest, r"^[#{}\[\],\s]*$")

    def test_labels_match_contract(self):
        labels = contract_labels()
        self.assertIn("implement", labels)
        used = set(re.findall(rf'\.{HELPER}\("([^"]+)"', src()))
        self.assertTrue(used)
        self.assertLessEqual(used, labels)


if __name__ == "__main__":
    unittest.main()
