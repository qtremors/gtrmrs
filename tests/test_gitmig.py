"""Migration regression tests using disposable repositories and destinations."""

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
import zipfile

from gtrmrs.core.git_utils import git_check_ignore
from gtrmrs.gitmig.cli import _configure_parser, run
from gtrmrs.gitmig.engine import GitMigEngine


@unittest.skipUnless(shutil.which("git"), "Git is required for migration integration tests")
class TestMigration(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.destination = self.root / "destination"
        self.source.mkdir()
        self.git("-c", "init.templateDir=", "init", "-q")
        self.git("config", "core.excludesFile", str(self.write(self.source / ".git/audit-excludes", "")))
        self.write(self.source / "source.py", "print('source')\n")
        self.stdout, self.stderr = io.StringIO(), io.StringIO()
        stdout_context = contextlib.redirect_stdout(self.stdout)
        stderr_context = contextlib.redirect_stderr(self.stderr)
        stdout_context.__enter__()
        stderr_context.__enter__()
        self.addCleanup(stdout_context.__exit__, None, None, None)
        self.addCleanup(stderr_context.__exit__, None, None, None)

    def git(self, *args):
        return subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-C", str(self.source), *args],
            capture_output=True, check=True,
        ).stdout

    @staticmethod
    def write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def engine(self, **options):
        return GitMigEngine(str(self.source), str(self.destination), quiet=True, **options)

    def command(self, *arguments):
        parser = argparse.ArgumentParser()
        _configure_parser(parser)
        run(parser.parse_args(list(map(str, arguments))))

    def link(self, target, link, directory=False):
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(str(target), str(link), target_is_directory=directory)
        except OSError:
            self.skipTest("Symlink creation unavailable")
        self.addCleanup(lambda: link.unlink() if link.is_symlink() else None)

    def test_copy_and_resume_count_only_completed_files(self):
        engine = self.engine()
        self.assertTrue(engine.run())
        self.assertEqual(engine.total_files_copied, 1)
        self.assertEqual((self.destination / "source/source.py").read_bytes(), (self.source / "source.py").read_bytes())
        resume = self.engine(skip_existing=True)
        self.assertTrue(resume.run())
        self.assertEqual(resume.total_files_copied, 0)
        self.assertEqual(resume.files_skipped_existing, 1)
        self.assertEqual(resume.total_bytes_copied, 0)

    def test_destination_file_symlink_is_refused(self):
        outside = self.write(self.root / "outside/file.py", "keep")
        self.link(outside, self.destination / "source/source.py")
        engine = self.engine()
        self.assertFalse(engine.run())
        self.assertEqual(outside.read_text(), "keep")
        self.assertEqual(engine.total_files_copied, 0)

    def test_destination_directory_symlink_is_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.link(outside, self.destination / "source", directory=True)
        engine = self.engine()
        self.assertFalse(engine.run())
        self.assertEqual(list(outside.iterdir()), [])

    def test_destination_junction_is_refused(self):
        if os.name != "nt":
            self.skipTest("Windows junction regression")
        outside = self.root / "outside"
        outside.mkdir()
        self.destination.mkdir()
        junction = self.destination / "source"
        command = "$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path $env:GTRMRS_TEST_LINK -Target $env:GTRMRS_TEST_TARGET | Out-Null"
        env = dict(os.environ, GTRMRS_TEST_LINK=str(junction), GTRMRS_TEST_TARGET=str(outside))
        subprocess.run(["powershell", "-NoProfile", "-Command", command], env=env, check=True, capture_output=True)
        self.addCleanup(os.rmdir, str(junction))
        engine = self.engine()
        self.assertFalse(engine.run())
        self.assertEqual(list(outside.iterdir()), [])

    def test_copy_failure_preserves_existing_file_and_removes_temporary(self):
        existing = self.write(self.destination / "source/source.py", "previous")
        with patch("gtrmrs.gitmig.engine.shutil.copy2", side_effect=OSError("disk full")):
            engine = self.engine()
            self.assertFalse(engine.run())
        self.assertEqual(existing.read_text(), "previous")
        self.assertEqual(engine.files_overwritten, 0)
        self.assertEqual(list(existing.parent.glob(".gitmig-*")), [])

    def test_copy_interrupt_preserves_existing_file(self):
        existing = self.write(self.destination / "source/source.py", "previous")
        with patch("gtrmrs.gitmig.engine.shutil.copy2", side_effect=KeyboardInterrupt):
            engine = self.engine()
            self.assertFalse(engine.run())
        self.assertTrue(engine.was_interrupted)
        self.assertEqual(existing.read_text(), "previous")
        self.assertEqual(list(existing.parent.glob(".gitmig-*")), [])

    def test_link_inserted_before_copy_commit_is_refused(self):
        outside = self.write(self.root / "outside.py", "keep")
        target = self.destination / "source/source.py"
        copy = shutil.copy2
        def changed_destination(source, destination):
            copy(source, destination)
            self.link(outside, target)
        with patch("gtrmrs.gitmig.engine.shutil.copy2", side_effect=changed_destination):
            engine = self.engine()
            self.assertFalse(engine.run())
        self.assertEqual(outside.read_text(), "keep")
        self.assertEqual(engine.total_files_copied, 0)

    def test_cli_interrupt_returns_nonzero(self):
        with patch("gtrmrs.gitmig.engine.shutil.copy2", side_effect=KeyboardInterrupt):
            with self.assertRaises(SystemExit) as raised:
                self.command(self.source, self.destination, "--quiet")
        self.assertEqual(raised.exception.code, 130)

    def test_dry_run_checks_resume_without_writing(self):
        existing = self.write(self.destination / "source/source.py", "previous")
        engine = self.engine(dry_run=True, skip_existing=True)
        self.assertTrue(engine.run())
        self.assertEqual(existing.read_text(), "previous")
        self.assertEqual(engine.total_files_copied, 0)
        self.assertEqual(list(existing.parent.glob(".gitmig-*")), [])

    def old_archive(self):
        self.destination.mkdir()
        path = self.destination / "source.zip"
        with zipfile.ZipFile(str(path), "w") as handle:
            handle.writestr("previous.txt", "backup")
        return path

    def test_zip_skip_existing_preserves_archive(self):
        archive = self.old_archive()
        previous = archive.read_bytes()
        engine = self.engine(use_zip=True, skip_existing=True)
        self.assertTrue(engine.run())
        self.assertEqual(archive.read_bytes(), previous)
        self.assertEqual(engine.total_files_copied, 0)
        self.assertEqual(engine.archives_skipped_existing, 1)

    def test_zip_failure_and_interrupt_preserve_archive(self):
        archive = self.old_archive()
        previous = archive.read_bytes()
        for failure in (OSError("read failure"), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                with patch("gtrmrs.gitmig.engine.zipfile.ZipFile.write", side_effect=failure):
                    engine = self.engine(use_zip=True)
                    self.assertFalse(engine.run())
                self.assertEqual(archive.read_bytes(), previous)
                self.assertEqual(engine.total_files_copied, 0)
                self.assertEqual(list(self.destination.glob(".gitmig-*")), [])

    def test_zip_success_atomically_replaces_archive(self):
        archive = self.old_archive()
        engine = self.engine(use_zip=True)
        self.assertTrue(engine.run())
        with zipfile.ZipFile(str(archive)) as handle:
            self.assertIsNone(handle.testzip())
            self.assertEqual(handle.namelist(), ["source/source.py"])
        self.assertEqual(engine.total_files_copied, 1)

    def test_zip_destination_symlink_preserves_external_file(self):
        outside = self.write(self.root / "outside.zip", "keep")
        self.link(outside, self.destination / "source.zip")
        self.assertFalse(self.engine(use_zip=True).run())
        self.assertEqual(outside.read_text(), "keep")

    def test_filters_respect_ignores_explicit_excludes_and_credentials(self):
        self.write(self.source / ".gitignore", "private.json\n")
        for name in ("private.json", "excluded.json", "keep.json", "release.jks", "release.keystore"):
            self.write(self.source / name, "data")
        engine = self.engine(ext_filter=["json", "jks", "keystore"], extra_excludes=["excluded.json"])
        self.assertTrue(engine.run())
        self.assertEqual([p.name for p in (self.destination / "source").iterdir()], ["keep.json"])

    def test_env_mode_preserves_ignored_configs_but_respects_explicit_exclusions(self):
        self.write(self.source / ".gitignore", ".env*\n")
        self.write(self.source / ".env", "KEEP=1")
        self.write(self.source / ".env.private", "SECRET=1")
        engine = self.engine(env_only=True, extra_excludes=[".env.private"])
        self.assertTrue(engine.run())
        self.assertTrue((self.destination / "source/.env").is_file())
        self.assertFalse((self.destination / "source/.env.private").exists())

    def test_raw_mode_includes_gitignored_files(self):
        self.write(self.source / ".gitignore", "private.json\n")
        self.write(self.source / "private.json", "{}")
        self.assertTrue(self.engine(raw_mode=True).run())
        self.assertTrue((self.destination / "source/private.json").exists())

    def test_excluded_directories_are_not_walked(self):
        self.write(self.source / "node_modules/package/index.js", "dependency")
        walk = os.walk
        visited = []
        def instrumented(path, *args, **kwargs):
            for entry in walk(path, *args, **kwargs):
                visited.append(Path(entry[0]))
                yield entry
        with patch("gtrmrs.gitmig.engine.os.walk", side_effect=instrumented):
            engine = self.engine(dry_run=True)
            self.assertTrue(engine.run())
        self.assertNotIn(self.source / "node_modules", visited)
        self.assertEqual(engine.total_dirs_skipped, 2)
        self.assertFalse(self.destination.exists())

    def test_git_verification_failure_does_not_replace_backup(self):
        archive = self.old_archive()
        previous = archive.read_bytes()
        with patch("gtrmrs.gitmig.engine.git_check_ignore", side_effect=RuntimeError("Git unavailable")):
            self.assertFalse(self.engine(use_zip=True).run())
        self.assertEqual(archive.read_bytes(), previous)

    def test_scan_error_does_not_replace_backup(self):
        archive = self.old_archive()
        previous = archive.read_bytes()
        def fail_walk(path, **options):
            options["onerror"](PermissionError("unreadable subtree"))
            return iter(())
        with patch("gtrmrs.gitmig.engine.os.walk", side_effect=fail_walk):
            self.assertFalse(self.engine(use_zip=True).run())
        self.assertEqual(archive.read_bytes(), previous)

    def test_strict_git_check_reports_missing_git_and_nonzero_failure(self):
        with patch("gtrmrs.core.git_utils.subprocess.run", side_effect=FileNotFoundError("Git missing")):
            with self.assertRaises(RuntimeError):
                git_check_ignore(str(self.source), ["source.py"], strict=True)
        failed = subprocess.CompletedProcess([], 128, stdout=b"", stderr=b"invalid repository")
        with patch("gtrmrs.core.git_utils.subprocess.run", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, "invalid repository"):
                git_check_ignore(str(self.source), ["source.py"], strict=True)

    def test_cli_failure_is_nonzero_and_errors_use_stderr(self):
        with patch("gtrmrs.gitmig.engine.shutil.copy2", side_effect=OSError("disk full")):
            with self.assertRaises(SystemExit) as raised:
                self.command(self.source, self.destination, "--quiet")
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("disk full", self.stderr.getvalue())
        self.assertEqual(self.stdout.getvalue(), "")

    def test_cli_rejects_effective_destination_equal_to_source(self):
        with self.assertRaises(SystemExit) as raised:
            self.command(self.source, self.root, "--quiet")
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual((self.source / "source.py").read_text(), "print('source')\n")

    def test_only_filter_applies_to_single_repository(self):
        engine = self.engine(only_repos=["missing"])
        self.assertFalse(engine.run())
        self.assertEqual(engine.total_files_copied, 0)
        self.assertFalse(self.destination.exists())

    def test_git_size_does_not_create_destination(self):
        self.command(self.source, self.destination, "--git-size", "--quiet")
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
