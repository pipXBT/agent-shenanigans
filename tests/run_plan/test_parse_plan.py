import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "skills" / "run-plan" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from parse_plan import parse_plan, plan_hash, validate  # noqa: E402

PLAN = REPO / "docs/superpowers/plans/2026-10-19-control-copy.md"


def one(body):
    return parse_plan("### Task 1: A\n" + body)[0]


class ParsePlanTests(unittest.TestCase):
    def test_strips_line_ranges(self):
        t = one("**Files:**\n- Modify: `a.py:123-145`\n- Test: `t.py`\n")
        self.assertEqual(t.files, ("a.py",))
        self.assertEqual(t.tests, ("t.py",))
        self.assertEqual((t.id, t.title), ("1", "A"))

    def test_a_bare_second_range_is_not_a_directory(self):
        t = one("- Modify: `src/shield.rs:1000-1030` and `:1105-1120`\n- Test: `t.rs`\n")
        self.assertEqual(t.files, ("src/shield.rs",))

    def test_delete_lines_count_as_files(self):
        t = one("- Delete: `old/x.py`\n- Modify: `a.py:7`\n- Test: `t.py`\n")
        self.assertEqual(t.files, ("old/x.py", "a.py"))

    def test_multiple_paths_on_one_line_inherit_directory(self):
        t = one("- Create: `w/c/a.json`, `b.json`\n- Test: `t.py`\n")
        self.assertEqual(t.files, ("w/c/a.json", "w/c/b.json"))

    def test_first_token_without_slash_stays_put(self):
        t = one("- Create: `stack.toml`\n- Test: `t.py`\n")
        self.assertEqual(t.files, ("stack.toml",))

    def test_ignores_parenthetical_notes(self):
        t = one("- Create: `agents/reader.md` (tools `Read, Grep, Glob` only)\n- Test: `t.py`\n")
        self.assertEqual(t.files, ("agents/reader.md",))

    def test_kind_marker_wins(self):
        t = one("**Kind:** docs\n- Create: `a.py`\n- Test: `t.py`\n")
        self.assertEqual((t.kind, t.kind_source), ("docs", "marker"))

    def test_derived_code(self):
        t = one("- Create: `a.py`\n- Test: `t.py`\n")
        self.assertEqual((t.kind, t.kind_source), ("code", "derived"))

    def test_derived_docs_when_all_docs_paths(self):
        for path in ("README.md", "docs/x.png", "n.rst", "n.txt", "n.adoc"):
            with self.subTest(path=path):
                t = one(f"- Modify: `{path}`\n")
                self.assertEqual((t.kind, t.kind_source), ("docs", "derived"))

    def test_derived_test_when_only_tests(self):
        t = one("- Test: `tests/t.py`\n")
        self.assertEqual((t.kind, t.kind_source), ("test", "derived"))

    def test_refactor_only_from_marker(self):
        self.assertEqual(one("- Modify: `a.py`\n- Test: `t.py`\n").kind, "code")
        t = one("**Kind:** refactor\n- Modify: `a.py`\n")
        self.assertEqual((t.kind, t.kind_source), ("refactor", "marker"))

    def test_complexity_marker(self):
        self.assertEqual(one("**Complexity:** high\n- Modify: `a.py`\n").complexity, "high")
        self.assertIsNone(one("- Modify: `a.py`\n").complexity)

    def test_ignores_task_headings_inside_code_fences(self):
        text = (
            "### Task 1: A\n**Files:**\n- Create: `a.py`\n- Test: `t.py`\n"
            "```markdown\n### Task 9: fake\n- Create: `fake.py`\n```\n"
        )
        tasks = parse_plan(text)
        self.assertEqual([t.id for t in tasks], ["1"])
        self.assertEqual(tasks[0].files, ("a.py",))

    def test_longer_fence_is_not_closed_by_shorter_one(self):
        text = "### Task 1: A\n- Create: `a.py`\n- Test: `t.py`\n````md\n```\n### Task 9: fake\n```\n````\n"
        self.assertEqual([t.id for t in parse_plan(text)], ["1"])

    def test_other_heading_ends_a_task(self):
        text = "### Task 1: A\n- Create: `a.py`\n- Test: `t.py`\n## Notes\n- Create: `stray.py`\n"
        self.assertEqual(parse_plan(text)[0].files, ("a.py",))

    def test_validate_rejects_code_without_tests_or_files(self):
        ok, no_tests, no_files = parse_plan(
            "### Task 1: A\n- Create: `a.py`\n- Test: `t.py`\n"
            "### Task 2: B\n- Create: `a.py`\n"
            "### Task 3: C\n**Kind:** code\n- Test: `t.py`\n"
        )
        self.assertEqual(validate([ok]), [])
        errs = validate([no_tests, no_files])
        self.assertEqual(len(errs), 2)
        self.assertIn("Task 2", errs[0])
        self.assertIn("no tests", errs[0])
        self.assertIn("Task 3", errs[1])
        self.assertIn("no files", errs[1])

    def test_validate_allows_refactor_without_tests(self):
        self.assertEqual(validate([one("**Kind:** refactor\n- Modify: `a.py`\n")]), [])

    def test_validate_rejects_duplicate_ids(self):
        text = "### Task 1: A\n- Create: `a.py`\n- Test: `t.py`\n### Task 1: B\n- Create: `b.py`\n- Test: `u.py`\n"
        errs = validate(parse_plan(text))
        self.assertEqual(len(errs), 1)
        self.assertIn("duplicate", errs[0])

    def test_validate_flags_a_new_test_on_a_create_line(self):
        t = one("- Create: `pkg/__tests__/x.test.ts`\n- Modify: `pkg/src/x.ts`\n- Test: `pkg/__tests__/y.test.ts`\n")
        errs = validate([t], ("**/__tests__/**",))
        self.assertEqual(len(errs), 1)
        self.assertIn("pkg/__tests__/x.test.ts", errs[0])
        self.assertIn("Test: line", errs[0])
        self.assertEqual(validate([t]), [])  # no globs given: no check
        self.assertEqual(validate([t], ("scripts/test-*.sh",)), [])

    def test_validate_leaves_create_lines_outside_the_test_globs(self):
        t = one("- Create: `pkg/src/new.ts`\n- Test: `pkg/__tests__/new.test.ts`\n")
        self.assertEqual(validate([t], ("**/__tests__/**", "**/tests/**")), [])

    def test_plan_hash_is_sha256_hex(self):
        self.assertEqual(
            plan_hash(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )

    def test_parses_this_repo_plan(self):
        tasks = parse_plan(PLAN.read_text())
        self.assertEqual(len(tasks), 21)
        self.assertEqual(validate(tasks), [])
        self.assertEqual((tasks[0].kind, tasks[0].kind_source), ("refactor", "marker"))
        by_id = {t.id: t for t in tasks}
        self.assertNotIn("Read, Grep, Glob", by_id["14"].files)
        self.assertIn("agents/reader.md", by_id["14"].files)
        self.assertIn(
            "workflows/fixture/cases/default-branch-refused.json", by_id["14"].files
        )


class CliTests(unittest.TestCase):
    def run_cli(self, text, *extra):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "plan.md"
            p.write_text(text)
            r = subprocess.run(
                [sys.executable, str(SCRIPTS / "parse_plan.py"), str(p), *extra],
                capture_output=True, text=True,
            )
        return r.returncode, json.loads(r.stdout)

    def test_test_glob_reaches_validate_and_created_stays_out_of_tasks(self):
        text = "### Task 1: A\n- Create: `tests/t_new.py`\n- Modify: `a.py`\n- Test: `tests/t.py`\n"
        code, out = self.run_cli(text, "--test-glob", "tests/**")
        self.assertEqual(code, 1)
        self.assertIn("tests/t_new.py", out["errors"][0])
        self.assertNotIn("created", out["tasks"][0])
        self.assertEqual(self.run_cli(text)[0], 0)

    def test_ok_plan_exits_zero(self):
        text = "### Task 1: A\n- Create: `a.py`\n- Test: `t.py`\n"
        code, out = self.run_cli(text)
        self.assertEqual(code, 0)
        self.assertEqual(out["errors"], [])
        self.assertEqual(out["plan_hash"], plan_hash(text.encode()))
        self.assertEqual(out["tasks"][0]["files"], ["a.py"])

    def test_invalid_plan_exits_one(self):
        code, out = self.run_cli("### Task 1: A\n- Create: `a.py`\n")
        self.assertEqual(code, 1)
        self.assertEqual(len(out["errors"]), 1)


if __name__ == "__main__":
    unittest.main()
