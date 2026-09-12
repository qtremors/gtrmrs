"""File-selection regression tests using disposable folders and Git repositories."""

import argparse
import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from gtrmrs.core.git_utils import find_git_root, git_check_ignore
from gtrmrs.gitmig.engine import GitMigEngine
from gtrmrs.locr.engine import LocrEngine
from gtrmrs.rtree.engine import RepoTreeVisualizer
from gtrmrs.locr import cli as locr_cli
from gtrmrs.rtree import cli as tree_cli
from gtrmrs.gitmig import cli as migration_cli


class FolderFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "source"
        self.root.mkdir()

    def write(self, name, content="pass\n"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def loc(self, **options):
        return {item["path"] for item in LocrEngine(str(self.root), **options).scan()[1]}

    def tree(self, **options):
        return RepoTreeVisualizer(str(self.root), use_color=False, **options).visible_paths

    def migration(self, **options):
        engine = GitMigEngine(str(self.root), str(self.root.parent / "destination"), quiet=True, **options)
        paths, _ = engine._scan_repo("source", str(self.root))
        self.assertFalse(engine.errors, engine.errors)
        return {path.replace(os.sep, "/") for path, _ in paths}

    def invoke(self, module, *arguments):
        parser = argparse.ArgumentParser()
        module._configure_parser(parser)
        output, errors = io.StringIO(), io.StringIO()
        status = 0
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            try:
                module.run(parser.parse_args(list(map(str, arguments))))
            except SystemExit as exc:
                status = exc.code
        return status, output.getvalue(), errors.getvalue()


class TestPlainFolders(FolderFixture):
    def test_ambiguous_source_names_survive_in_all_tools(self):
        expected = {name + "/source.py" for name in ("schemas", "bin", "build", "dist", "target", "obj", "out")}
        for name in expected:
            self.write(name)
        self.assertEqual(self.loc(), expected)
        self.assertTrue(expected.issubset(self.tree()))
        self.assertEqual(self.migration(), expected)

    def test_root_only_pattern_does_not_hide_nested_name(self):
        self.write(".gitignore", "/private/\n")
        self.write("private/secret.py")
        self.write("src/private/keep.py")
        self.assertEqual(self.loc(), {"src/private/keep.py"})
        self.assertNotIn("private/", self.tree())
        self.assertIn("src/private/keep.py", self.tree())

    def test_ignored_directory_descendants_cannot_be_restored_alone(self):
        self.write(".gitignore", "private/\n!private/keep.py\n")
        self.write("private/keep.py")
        self.assertEqual(self.loc(), set())
        self.assertNotIn("private/keep.py", self.tree())

    def test_nested_rules_and_parent_restoration(self):
        self.write(".gitignore", "*.py\n/private/*\n!/private/open/\n")
        self.write("src/.gitignore", "!keep.py\n")
        self.write("src/keep.py")
        self.write("src/drop.py")
        self.write("private/open/.gitignore", "!keep.py\n")
        self.write("private/open/keep.py")
        self.write("private/closed/drop.py")
        expected = {"src/keep.py", "private/open/keep.py"}
        self.assertEqual(self.loc(), expected)
        self.assertTrue(expected.issubset(self.tree()))

    def test_double_star_and_single_star_have_different_directory_scope(self):
        self.write(".gitignore", "a/*.py\nb/**/drop.py\nc/**\n!c/keep.py\n")
        for name in ("a/drop.py", "a/sub/keep.py", "b/drop.py", "b/sub/drop.py", "c/keep.py", "c/sub/drop.py"):
            self.write(name)
        self.assertEqual(self.loc(), {"a/sub/keep.py", "c/keep.py"})

    def test_comments_escaped_names_and_whitespace(self):
        self.write(".gitignore", "# comment\n\\#drop.py\n\\!drop.py\n leading.py\ntrailing.py   \nliteral\\*.py\n")
        for name in ("#drop.py", "!drop.py", " leading.py", "leading.py", "trailing.py", "literalX.py"):
            self.write(name)
        self.assertEqual(self.loc(), {"leading.py", "literalX.py"})

    def test_case_sensitive_fallback(self):
        self.write(".gitignore", "DROP.py\n")
        self.write("drop.py")
        self.assertEqual(self.loc(), {"drop.py"})

    def test_directory_only_pattern_does_not_hide_same_named_file(self):
        self.write(".gitignore", "drop.py/\n")
        self.write("drop.py")
        self.assertEqual(self.loc(), {"drop.py"})

    def test_raw_test_filter_composes(self):
        self.write(".gitignore", "test_main.py\n")
        self.write("main.py")
        self.write("test_main.py")
        self.write("tests/fixture.py")
        self.assertEqual(self.loc(raw_mode=True, tests_only=True), {"test_main.py", "tests/fixture.py"})
        self.assertEqual(self.loc(tests_only=True), {"tests/fixture.py"})

    def test_override_only_disables_default_directories(self):
        self.write(".gitignore", "private.py\n")
        self.write("venv/source.py")
        self.write("private.py")
        self.assertEqual(self.loc(), set())
        self.assertEqual(self.loc(default_dir_excludes=False), {"venv/source.py"})
        self.assertIn("venv/source.py", self.tree(default_dir_excludes=False))
        self.assertEqual(self.migration(default_dir_excludes=False), {".gitignore", "venv/source.py"})

    def test_raw_migration_retains_directory_and_file_safeguards(self):
        self.write("venv/source.py")
        self.write("release.jks", "key")
        self.assertEqual(self.migration(raw_mode=True), set())
        self.assertEqual(self.migration(raw_mode=True, default_dir_excludes=False), {"venv/source.py"})

    def test_preserved_configs_inside_ignored_directories_are_still_copied(self):
        self.write(".gitignore", "private/\n")
        self.write("private/.env", "KEY=value\n")
        self.write("private/secret.py")
        self.assertEqual(self.migration(), {".gitignore", "private/.env"})

    def test_default_and_gitignored_directories_are_not_walked(self):
        self.write(".gitignore", "generated/\n")
        self.write("generated/large/tree/output.py")
        self.write("node_modules/package/file.py")
        visited = []
        walk = os.walk
        def instrumented(*args, **kwargs):
            for entry in walk(*args, **kwargs):
                visited.append(Path(entry[0]))
                yield entry
        with patch("gtrmrs.core.git_utils.os.walk", side_effect=instrumented):
            self.assertEqual(self.loc(), set())
        self.assertEqual(visited, [self.root])

    def test_depth_and_empty_directories_remain_visible(self):
        self.write("a/b/source.py")
        (self.root / "empty").mkdir()
        self.assertEqual(self.tree(max_depth=1), {"a/", "empty/"})
        self.assertEqual(self.tree(max_depth=0), set())

    def test_ascii_tree_keeps_unicode_connectors(self):
        self.write("a/source.py")
        self.write("last.py")
        tree = RepoTreeVisualizer(str(self.root), use_color=False).get_ascii_tree()
        self.assertEqual(tree, ["source/", "├── a/", "│   └── source.py", "└── last.py"])

    def test_migration_reports_unreadable_fallback_rules(self):
        self.write(".gitignore", "private.py\n")
        self.write("private.py")
        engine = GitMigEngine(str(self.root), str(self.root.parent / "destination"), quiet=True)
        with patch("gtrmrs.core.git_utils.open", side_effect=PermissionError("locked rules")):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(engine._scan_repo("source", str(self.root))[0], [])
        self.assertTrue(any("locked rules" in error for error in engine.errors))

    def test_raw_tree_includes_metadata_contents(self):
        self.write(".git/nested/config.py")
        self.assertIn(".git/nested/config.py", self.tree(raw_mode=True))

    def test_unreadable_plain_ignore_rules_raise_instead_of_widening_scan(self):
        self.write(".gitignore", "private.py\n")
        with patch("gtrmrs.core.git_utils.open", side_effect=PermissionError("locked rules")):
            with self.assertRaisesRegex(OSError, "locked rules"):
                self.loc()

    def test_cli_override_and_raw_tests_flags(self):
        self.write("venv/test_keep.py")
        self.write("main.py")
        status, output, errors = self.invoke(locr_cli, self.root, "--raw", "--tests", "--json", "--no-color")
        self.assertEqual(status, 0, errors)
        self.assertNotIn('"path": "main.py"', output)
        status, output, errors = self.invoke(tree_cli, "-r", self.root, "--flat", "--no-color", "--no-default-dir-excludes")
        self.assertEqual(status, 0, errors)
        self.assertIn("venv/test_keep.py", output)


@unittest.skipUnless(shutil.which("git"), "Git integration fixtures require Git")
class TestGitFolders(FolderFixture):
    def setUp(self):
        super().setUp()
        self.git("-c", "init.templateDir=", "init", "-q")
        self.git("config", "core.excludesFile", str(self.write(".git/fixture-excludes", "")))
        self.git("config", "core.ignoreCase", "false")

    def git(self, *args, root=None):
        return subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(root or self.root), *args],
                              capture_output=True, check=True).stdout

    def test_nested_unignore_and_tracked_files_override_root_rules(self):
        self.write(".gitignore", "*.py\n")
        self.write("src/.gitignore", "!keep.py\n")
        self.write("src/keep.py")
        self.write("tracked.py")
        self.write("drop.py")
        self.git("add", "-f", "tracked.py")
        expected = {"tracked.py", "src/keep.py"}
        self.assertEqual(self.loc(), expected)
        self.assertTrue(expected.issubset(self.tree()))
        self.assertTrue(expected.issubset(self.migration()))

    def test_tracked_descendants_protect_default_and_ignored_parents(self):
        self.write(".gitignore", "node_modules/\nbuild/\n")
        self.write("node_modules/package/source.py")
        self.write("node_modules/package/drop.py")
        self.write("build/keep.py")
        self.git("add", "-f", "node_modules/package/source.py", "build/keep.py")
        expected = {"node_modules/package/source.py", "build/keep.py"}
        self.assertEqual(self.loc(), expected)
        self.assertTrue(expected.issubset(self.tree()))
        self.assertTrue(expected.issubset(self.migration()))

    def test_explicit_migration_exclusions_still_override_tracked_source(self):
        self.write("build/source.py")
        self.git("add", "build/source.py")
        self.assertNotIn("build/source.py", self.migration(extra_excludes=["build/"]))

    def test_index_is_loaded_once_per_owner(self):
        self.write("src/a/keep.py")
        self.write("src/b/keep.py")
        original = subprocess.run
        with patch("gtrmrs.core.scan_filter.subprocess.run", wraps=original) as run:
            self.loc()
        self.assertEqual(sum("ls-files" in item.args[0] for item in run.call_args_list), 1)

    def test_info_exclude_is_authoritative(self):
        self.write(".git/info/exclude", "private/\n")
        self.write("private/secret.py")
        self.assertEqual(self.loc(), set())
        self.assertNotIn("private/", self.tree())

    def test_git_failure_is_strict_by_default_and_cli_uses_stderr(self):
        self.write("private.py")
        with patch("gtrmrs.core.git_utils.subprocess.run", side_effect=FileNotFoundError("Git missing")):
            with self.assertRaisesRegex(RuntimeError, "Git missing"):
                git_check_ignore(str(self.root), ["private.py"])
            for module, args in ((locr_cli, [self.root, "--json"]), (tree_cli, ["-r", self.root, "--flat"])):
                status, output, errors = self.invoke(module, *args)
                self.assertEqual(status, 1)
                self.assertIn("Git missing", errors)
                self.assertNotIn("private.py", output)

    def test_failed_ignore_check_and_timeout_do_not_widen_scan(self):
        self.write("private.py")
        for failure in (RuntimeError("invalid check"), subprocess.TimeoutExpired("git", 30)):
            if isinstance(failure, RuntimeError):
                with patch("gtrmrs.core.scan_filter.git_check_ignore", side_effect=failure):
                    with self.assertRaisesRegex(RuntimeError, "invalid check"):
                        self.loc()
            else:
                with patch("gtrmrs.core.git_utils.subprocess.run", side_effect=failure):
                    with self.assertRaises(RuntimeError):
                        self.tree()

    def test_nul_protocol_preserves_spaces_unicode_and_line_breaks(self):
        names = ["space name.py", "café.py", "tab\tname.py", "line\nname.py", "control\x01.py"]
        output = os.fsencode("\0".join(names) + "\0")
        completed = subprocess.CompletedProcess([], 0, stdout=output, stderr=b"")
        with patch("gtrmrs.core.git_utils.subprocess.run", return_value=completed) as run:
            self.assertEqual(git_check_ignore(str(self.root), names), set(names))
        self.assertEqual(run.call_args.kwargs["input"], output)
        with self.assertRaises(RuntimeError):
            git_check_ignore(str(self.root), ["bad\0name.py"])

    def test_linked_worktree_scan_and_metadata_copy_policy(self):
        self.write("source.py")
        self.git("add", "source.py")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
        linked = self.root.parent / "linked"
        self.git("worktree", "add", "--detach", "-q", str(linked))
        self.assertEqual(find_git_root(str(linked)), str(linked))
        self.assertEqual({r["path"] for r in LocrEngine(str(linked)).scan()[1]}, {"source.py"})
        self.assertNotIn(".git", RepoTreeVisualizer(str(linked), use_color=False).visible_paths)
        engine = GitMigEngine(str(linked), str(self.root.parent / "destination"), quiet=True)
        self.assertEqual(engine._find_repos(), ["linked"])
        self.assertEqual({p for p, _ in engine._scan_repo("linked", str(linked))[0]}, {"source.py"})
        with contextlib.redirect_stderr(io.StringIO()):
            external = GitMigEngine(str(linked), str(self.root.parent / "destination"), quiet=True, include_git=True)
            self.assertEqual(external._scan_repo("linked", str(linked))[0], [])
        self.assertTrue(external.errors)

    def test_submodule_uses_its_own_rules(self):
        child = self.root / "module"
        child.mkdir()
        self.git("-c", "init.templateDir=", "init", "-q", root=child)
        self.write("module/source.py")
        self.git("add", "source.py", root=child)
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "child", root=child)
        self.git("add", "module")
        self.git("config", "-f", ".gitmodules", "submodule.module.path", "module")
        self.git("config", "-f", ".gitmodules", "submodule.module.url", "../module-fixture")
        self.git("submodule", "absorbgitdirs", "module")
        self.assertTrue((child / ".git").is_file())
        self.write("module/.gitignore", "private.py\n")
        self.write("module/private.py")
        self.assertEqual(self.loc(), {"module/source.py"})
        self.assertIn("module/source.py", self.tree())
        self.assertIn("module/source.py", self.migration())
        self.assertNotIn("module/private.py", self.migration())

    def test_subdirectory_scans_use_owning_index_and_rules(self):
        self.write(".gitignore", "src/private.py\n")
        self.write("src/private.py")
        self.write("src/venv/keep.py")
        self.git("add", "src/venv/keep.py")
        found = LocrEngine(str(self.root / "src")).scan()[1]
        self.assertEqual({r["path"] for r in found}, {"venv/keep.py"})

    def test_raw_scan_does_not_require_git(self):
        self.write("test_keep.py")
        with patch("gtrmrs.core.git_utils.subprocess.run", side_effect=FileNotFoundError("Git missing")):
            self.assertEqual(self.loc(raw_mode=True, tests_only=True), {"test_keep.py"})

    def test_plain_fallback_agrees_with_git_for_supported_rules(self):
        paths = ("a.py", "b.py", "#drop.py", " leading.py", "src/a.py", "src/deep/a.py",
                 "private/a.py", "private/open/a.py", "private/closed/a.py", "cache/data.py")
        for name in paths:
            self.write(name)
        rules = (
            "*.py\n!a.py\n",
            "/a.py\n/private/\n",
            "src/*.py\ncache/\n",
            "src/**/a.py\n",
            "private/**\n!private/open/\n!private/open/a.py\n",
            "private/\n!private/open/a.py\n",
            "\\#drop.py\n leading.py\nb.py  \n",
        )
        for patterns in rules:
            with self.subTest(patterns=patterns):
                self.write(".gitignore", patterns)
                expected = self.loc()
                with patch("gtrmrs.core.scan_filter.find_git_root", return_value=None):
                    self.assertEqual(self.loc(), expected)

    def test_git_failure_preserves_existing_report(self):
        self.write("private.py")
        report = self.root.parent / "report.txt"
        report.write_text("previous report", encoding="utf-8")
        for module, args in ((locr_cli, [self.root, "--no-color"]),
                             (tree_cli, ["-r", self.root, "--no-color"])):
            with patch("gtrmrs.core.git_utils.subprocess.run", side_effect=FileNotFoundError("Git missing")):
                status, _, errors = self.invoke(module, *args, "--out", report)
            self.assertEqual(status, 1, errors)
            self.assertEqual(report.read_text(encoding="utf-8"), "previous report")

    def test_invalid_git_ignore_status_is_not_treated_as_empty(self):
        failed = subprocess.CompletedProcess([], 128, stdout=b"", stderr=b"invalid repository")
        with patch("gtrmrs.core.git_utils.subprocess.run", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, "invalid repository"):
                git_check_ignore(str(self.root), ["private.py"])

    def test_default_override_cli_migration_keeps_file_safeguards(self):
        self.write("venv/source.py")
        self.write("venv/key.jks", "key")
        destination = self.root.parent / "destination"
        status, _, errors = self.invoke(migration_cli, self.root, destination, "--quiet", "--no-default-dir-excludes")
        self.assertEqual(status, 0, errors)
        self.assertTrue((destination / "source/venv/source.py").is_file())
        self.assertFalse((destination / "source/venv/key.jks").exists())


if __name__ == "__main__":
    unittest.main()
