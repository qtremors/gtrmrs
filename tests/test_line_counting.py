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
