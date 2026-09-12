"""LOC accuracy and report failures using temporary source fixtures."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gtrmrs.locr import cli as locr
from gtrmrs.locr.counter import count_lines
from gtrmrs.locr.engine import LocrEngine
from gtrmrs.locr.languages import language_for
from gtrmrs.rtree import cli as rtree


def count(source, filename):
    return count_lines(source.splitlines(keepends=True), language_for(filename))


class TestLineCounting(unittest.TestCase):
    def test_inline_block_comment_and_code_in_either_order(self):
        for source in ("/* note */ int main() {}\n", "int main() {} /* note */\n",
                       "/* one */ /* two */ call(); /* three */\n"):
            self.assertEqual(count(source, "main.c"), (0, 0, 1))

    def test_code_after_multiline_comment_end(self):
        self.assertEqual(count("/* begin\ncomment\n*/ call();\n// end\n", "main.cpp"), (0, 3, 1))

    def test_comment_markers_inside_strings_are_code(self):
        self.assertEqual(count('const char *s = "/* // */";\n/* comment */\ncall();\n', "main.c"), (0, 1, 2))
        self.assertEqual(count('print("# text")  # comment\n', "main.py"), (0, 0, 1))

    def test_escaped_quotes_do_not_open_comments(self):
        self.assertEqual(count('const char *s = "\\\" /*"; /* real\ncomment */\ncall();\n', "main.c"), (0, 1, 2))

    def test_nested_block_comments(self):
        for filename in ("main.kt", "build.gradle.kts", "main.rs", "main.swift"):
            self.assertEqual(count("/* outer /* inner */\nstill outer */ call();\n", filename), (0, 1, 1))

    def test_python_multiline_strings_both_quotes(self):
        for quote in ('"""', "'''"):
            for prefix in ("", "r", "f", "b"):
                source = 'value = ' + prefix + quote + '\n# string contents\n' + quote + '\nprint(value)\n'
                self.assertEqual(count(source, "main.py"), (0, 0, 4))

    def test_python_docstrings_and_blank_string_lines_are_code(self):
        self.assertEqual(count('"""docs\n\n# text\n"""\n\n# comment\npass\n', "stub.pyi"), (1, 1, 5))

    def test_python_comment_containing_triple_quotes(self):
        self.assertEqual(count('# """ example\npass\n# end\n', "main.py"), (0, 2, 1))

    def test_incomplete_python_is_still_counted(self):
        self.assertEqual(count('# comment\nx = (\n  1\n', "main.py"), (0, 1, 2))
        self.assertEqual(count('value = """unfinished\ntext\n', "main.py"), (0, 0, 2))

    def test_powershell_and_batch_comments(self):
        self.assertEqual(count('<# comment\nend #> Write-Host "# text"\n# note\n', "main.ps1"), (0, 2, 1))
        for filename in ("script.bat", "script.cmd"):
            self.assertEqual(count('REM note\nrem\n:: note\necho rem text\nremember\n\n', filename), (1, 3, 2))

    def test_xml_comment_and_following_element(self):
        self.assertEqual(count('<!-- note --> <root/>\n<!-- note\nend -->\n', "main.xml"), (0, 2, 1))

    def test_markdown_fences_do_not_turn_blank_lines_into_code(self):
        self.assertEqual(count('```text\nexample\n\n```\n', "README.md"), (1, 0, 3))


class TestScanReporting(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def invoke(self, cli, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        status = 0
        with patch("sys.argv", ["command", *map(str, args)]), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                cli.main()
            except SystemExit as exc:
                status = exc.code
        return status, stdout.getvalue(), stderr.getvalue()

    def test_advertised_language_files_are_all_included(self):
        files = ("stub.pyi", "style.sass", "main.swift", "script.ps1", "script.bat",
                 "script.cmd", "script.bash", "script.zsh", "Dockerfile")
        for name in files:
            (self.root / name).write_text("example\n", encoding="utf-8")
        result, details = LocrEngine(str(self.root), raw_mode=True).scan()
        self.assertEqual({entry["path"] for entry in details}, set(files))
        self.assertEqual(sum(item["files"] for item in result.values()), len(files))

    def test_failed_read_is_excluded_without_losing_other_files(self):
        good = self.root / "good.py"
        bad = self.root / "bad.py"
        good.write_text("pass\n", encoding="utf-8")
        bad.write_text("pass\n", encoding="utf-8")
        original = open

        def read(path, *args, **kwargs):
            if Path(path) == bad:
                raise PermissionError("locked fixture")
            return original(path, *args, **kwargs)

        engine = LocrEngine(str(self.root), raw_mode=True)
        with patch("gtrmrs.locr.engine.open", side_effect=read):
            result, details = engine.scan()
        self.assertEqual(result["Python"]["files"], 1)
        self.assertEqual([item["path"] for item in details], ["good.py"])
        self.assertIn("bad.py", engine.errors[0])
        engine.scan()
        self.assertEqual(engine.errors, [])

    def test_invalid_utf8_is_a_visible_failure(self):
        (self.root / "bad.py").write_bytes(b"# text\xff\n")
        status, output, errors = self.invoke(locr, self.root, "--json", "--raw")
        data = json.loads(output)
        self.assertEqual(status, 1)
        self.assertEqual(data["totals"]["files"], 0)
        self.assertTrue(data["metadata"]["incomplete"])
        self.assertIn("bad.py", data["metadata"]["errors"][0])
        self.assertIn("Scan incomplete", errors)

    def test_utf8_bom_is_accepted(self):
        (self.root / "main.py").write_text("# note\npass\n", encoding="utf-8-sig")
        result, _ = LocrEngine(str(self.root), raw_mode=True).scan()
        self.assertEqual(result["Python"]["comment"], 1)
        self.assertEqual(result["Python"]["code"], 1)

    def test_incomplete_text_report_is_marked_in_saved_file(self):
        (self.root / "bad.py").write_bytes(b"\xff")
        destination = self.root / "report.txt"
        status, _, errors = self.invoke(locr, self.root, "--raw", "--out", destination)
        self.assertEqual(status, 1)
        self.assertIn("Scan incomplete", destination.read_text(encoding="utf-8"))
        self.assertIn("bad.py", errors)

    def test_write_failures_exit_nonzero_with_stderr(self):
        (self.root / "main.py").write_text("pass\n", encoding="utf-8")
        for cli, args in ((locr, [self.root]), (rtree, ["--repo", self.root])):
            status, output, errors = self.invoke(cli, *args, "--raw", "--out", self.root / "missing" / "report.txt")
            self.assertNotEqual(status, 0)
            self.assertNotIn("Output written", output)
            self.assertIn("Error writing", errors)

    def test_redirected_tree_and_saved_confirmation_have_no_ansi(self):
        (self.root / "main.py").write_text("pass\n", encoding="utf-8")
        for extra in ([], ["--flat"], ["--out", self.root / "report.txt"]):
            status, output, errors = self.invoke(rtree, "--repo", self.root, "--raw", *extra)
            self.assertEqual(status, 0, errors)
            self.assertNotIn("\x1b[", output)

    def test_redirected_list_has_no_ansi(self):
        (self.root / "repo" / ".git").mkdir(parents=True)
        with patch("gtrmrs.rtree.cli.os.getcwd", return_value=str(self.root)):
            status, output, _ = self.invoke(rtree, "--list")
        self.assertEqual(status, 0)
        self.assertEqual(output.strip(), "repo")

    def test_interactive_json_does_not_include_spinner_output(self):
        (self.root / "main.py").write_text("pass\n", encoding="utf-8")
        class TerminalBuffer(io.StringIO):
            def isatty(self):
                return True

        with patch("io.StringIO", TerminalBuffer):
            status, output, errors = self.invoke(locr, self.root, "--raw", "--json")
        self.assertEqual(status, 0, errors)
        self.assertEqual(json.loads(output)["totals"]["files"], 1)

    def test_interruption_marks_json_incomplete_and_exits_130(self):
        with patch.object(LocrEngine, "_collect_and_filter_files", side_effect=KeyboardInterrupt):
            status, output, errors = self.invoke(locr, self.root, "--raw", "--json")
        self.assertEqual(status, 130)
        self.assertTrue(json.loads(output)["metadata"]["incomplete"])
        self.assertIn("Scan interrupted", errors)


if __name__ == "__main__":
    unittest.main()
