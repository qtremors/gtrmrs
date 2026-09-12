import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gtrmrs.storage.cli import main
from gtrmrs.storage.engine import StorageEngine


def write(root, name, content="generated"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def git(root, *args):
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(root), *args],
        check=True, capture_output=True,
    ).stdout


@unittest.skipUnless(shutil.which("git"), "Git is required for cleanup integration tests")
class TestStorage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.repo = self.workspace / "music"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        excludes = write(self.workspace, "empty-excludes", "")
        git(self.repo, "config", "core.excludesFile", str(excludes))
        write(self.repo, ".gitignore", "target/\nnode_modules/\n.next/\n.venv/\n.gradle/\nbuild/\n__pycache__/\n")
        write(self.repo, "Cargo.toml", "[package]\nname='music'\nversion='0.1.0'\n")
        self.target = self.repo / "target"
        self.build = self.target / "debug"
        write(self.repo, "target/debug/incremental/cache", "x" * 128)
        self.engine = StorageEngine()

    def target_candidate(self, audit):
        return next(c for c in audit.candidates if c.path == str(self.build))

    def command(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.argv", ["storage", *map(str, args)]), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            main()
        return stdout.getvalue(), stderr.getvalue()

    def link_directory(self, target, link):
        try:
            os.symlink(str(target), str(link), target_is_directory=True)
        except OSError:
            if os.name != "nt":
                self.skipTest("Directory links unavailable")
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
            if result.returncode:
                self.skipTest("Directory junctions unavailable")

    def test_read_only_sizes_and_rust_breakdown(self):
        audit = self.engine.audit(str(self.workspace))
        candidate = self.target_candidate(audit)
        self.assertTrue(candidate.eligible, candidate.blockers)
        self.assertEqual(candidate.bytes, 128)
        self.assertEqual(candidate.breakdown["incremental"], 128)
        self.assertGreater(audit.repositories[0].git_bytes, 0)
        self.assertEqual(audit.bytes, sum(r.bytes for r in audit.repositories))
        self.assertTrue(self.target.exists())

    def test_preview_then_apply_only_generated_directory(self):
        audit = self.engine.audit(str(self.repo))
        candidate = self.target_candidate(audit)
        preview = self.engine.clean(audit, [candidate])
        self.assertEqual(preview[0]["status"], "preview")
        self.assertTrue(self.target.exists())
        applied = self.engine.clean(audit, [candidate], apply=True)
        self.assertEqual(applied[0]["status"], "removed", applied)
        self.assertFalse(self.build.exists())
        self.assertTrue((self.repo / "Cargo.toml").is_file())
        self.assertTrue((self.repo / ".git").is_dir())

    def test_tracked_file_inside_ignored_output_is_kept(self):
        git(self.repo, "add", "-f", "target/debug/incremental/cache")
        candidate = self.target_candidate(self.engine.audit(str(self.repo)))
        self.assertIn("Contains tracked or unignored files", candidate.blockers)

    @unittest.skipUnless(os.name == "nt", "Windows case-insensitive path regression")
    def test_case_changed_directory_does_not_hide_tracked_files(self):
        write(self.repo, "module/Cargo.toml", "manifest")
        write(self.repo, "module/target/debug/output", "tracked")
        git(self.repo, "add", "-f", "module/target/debug/output")
        (self.repo / "module").rename(self.repo / "temporary-name")
        (self.repo / "temporary-name").rename(self.repo / "MODULE")
        audit = self.engine.audit(str(self.repo))
        candidate = next(c for c in audit.candidates if "MODULE" in Path(c.path).parts)
        self.assertIn("Contains tracked or unignored files", candidate.blockers)

    def test_unignored_output_is_kept(self):
        write(self.repo, ".gitignore", "")
        candidate = self.target_candidate(self.engine.audit(str(self.repo)))
        self.assertFalse(candidate.eligible)

    def test_unignored_exceptions_are_kept(self):
        write(self.repo, ".gitignore", "target/debug/*\n!target/debug/notes.txt\n")
        write(self.repo, "target/debug/notes.txt", "do not delete")
        candidate = self.target_candidate(self.engine.audit(str(self.repo)))
        self.assertIn("Contains tracked or unignored files", candidate.blockers)

    def test_cleanup_rechecks_newly_tracked_files(self):
        audit = self.engine.audit(str(self.repo))
        git(self.repo, "add", "-f", "target/debug/incremental/cache")
        result = self.engine.clean(audit, [self.target_candidate(audit)], apply=True)
        self.assertEqual(result[0]["status"], "refused")
        self.assertTrue(self.target.exists())

    def test_cleanup_rechecks_new_credentials(self):
        audit = self.engine.audit(str(self.repo))
        write(self.repo, "target/debug/.env", "SECRET=local")
        result = self.engine.clean(audit, [self.target_candidate(audit)], apply=True)
        self.assertEqual(result[0]["status"], "refused")
        self.assertTrue((self.build / ".env").exists())

    def test_database_sidecar_blocks_cleanup(self):
        write(self.repo, "target/debug/local.sqlite3-wal", "recoverable journal")
        candidate = self.target_candidate(self.engine.audit(str(self.repo)))
        self.assertFalse(candidate.eligible)

    def test_release_models_backups_and_patched_vendor_are_not_candidates(self):
        for parent in ("dist", "models", ".migration-backups", "vendor", ".git/recovery"):
            write(self.repo, parent + "/Cargo.toml", "manifest")
            write(self.repo, parent + "/target/debug/output", "keep")
        audit = self.engine.audit(str(self.repo))
        self.assertEqual([c.path for c in audit.candidates], [str(self.build)])

    def test_protected_subtree_blocks_parent_cleanup(self):
        write(self.repo, "target/debug/backup/data", "keep")
        candidate = self.target_candidate(self.engine.audit(str(self.repo)))
        self.assertFalse(candidate.eligible)

    def test_nested_repository_blocks_parent_cleanup(self):
        nested = self.build / "nested"
        nested.mkdir()
        git(nested, "init", "-q")
        candidate = self.target_candidate(self.engine.audit(str(self.repo)))
        self.assertIn("Contains a nested Git repository", candidate.blockers)

    def test_links_are_not_followed_and_cannot_be_cleaned(self):
        external = self.workspace / "external"
        write(external, "precious.txt", "keep")
        self.link_directory(external, self.build / "linked")
        audit = self.engine.audit(str(self.repo))
        self.assertEqual(self.target_candidate(audit).bytes, 128)
        self.assertFalse(self.target_candidate(audit).eligible)
        self.assertEqual(len(audit.skipped_links), 1)

    def test_replaced_target_junction_is_refused(self):
        audit = self.engine.audit(str(self.repo))
        self.target.rename(self.repo / "old-target")
        external = self.workspace / "external"
        precious = write(external, "precious.txt", "keep")
        self.link_directory(external, self.target)
        results = self.engine.clean(audit, [self.target_candidate(audit)], apply=True)
        self.assertEqual(results[0]["status"], "refused")
        self.assertEqual(precious.read_text(), "keep")

    def test_unreadable_subtree_is_kept(self):
        original = os.scandir

        def failing(path):
            if str(path) == str(self.target / "debug"):
                raise PermissionError("test permission failure")
            return original(path)

        with patch("gtrmrs.storage.engine.os.scandir", side_effect=failing):
            audit = self.engine.audit(str(self.repo))
        self.assertTrue(audit.errors)
        self.assertFalse(self.target_candidate(audit).eligible)

    def test_android_intermediates_can_be_removed_without_release_outputs(self):
        write(self.repo, "app/build.gradle.kts", "plugins {}")
        write(self.repo, "app/build/intermediates/file", "generated")
        apk = write(self.repo, "app/build/outputs/apk/release/app.apk", "release")
        mapping = write(self.repo, "app/build/outputs/mapping/release/mapping.txt", "mapping")
        audit = self.engine.audit(str(self.repo))
        android = [c for c in audit.candidates if "intermediates" in c.path]
        self.assertEqual(len(android), 1)
        self.assertTrue(android[0].eligible, android[0].blockers)
        self.assertEqual(self.engine.clean(audit, android, apply=True)[0]["status"], "removed")
        self.assertTrue(apk.exists())
        self.assertTrue(mapping.exists())

    def test_unknown_build_directory_is_not_selected(self):
        write(self.repo, "tools/build/source.py", "source")
        audit = self.engine.audit(str(self.repo))
        self.assertFalse(any("tools/build" in c.path.replace("\\", "/") for c in audit.candidates))

    def test_rust_cleanup_preserves_custom_target_tools_and_selects_triple_profiles(self):
        snapshot = write(self.repo, "target/recommit-tools/snapshots/source.rs", "recover")
        unknown = write(self.repo, "target/custom/debug/notes.txt", "keep")
        triple = write(self.repo, "target/x86_64-pc-windows-msvc/release/output", "compiled")
        audit = self.engine.audit(str(self.repo))
        self.assertEqual(len(audit.candidates), 2)
        results = self.engine.clean(audit, audit.candidates, apply=True)
        self.assertTrue(all(r["status"] == "removed" for r in results), results)
        self.assertTrue(snapshot.exists())
        self.assertTrue(unknown.exists())
        self.assertFalse(triple.exists())

    def test_scan_starting_inside_git_never_offers_cleanup(self):
        write(self.repo, ".git/recovery/Cargo.toml", "manifest")
        write(self.repo, ".git/recovery/target/debug/output", "recover")
        audit = self.engine.audit(str(self.repo / ".git"))
        self.assertEqual(audit.candidates, [])

    def test_nested_candidates_are_not_double_counted(self):
        write(self.repo, "target/debug/__pycache__/module.pyc", "data")
        audit = self.engine.audit(str(self.repo))
        self.assertEqual(len(audit.candidates), 1)
        self.assertEqual(audit.to_dict()["candidate_bytes"], 132)

    def test_nested_repositories_have_exclusive_sizes(self):
        nested = self.repo / "nested"
        nested.mkdir()
        git(nested, "init", "-q")
        write(nested, "source.txt", "nested")
        audit = self.engine.audit(str(self.repo))
        self.assertEqual(len(audit.repositories), 2)
        self.assertEqual(audit.bytes, sum(r.bytes for r in audit.repositories))

    def test_subdirectory_scan_discovers_owning_repo(self):
        audit = self.engine.audit(str(self.target.parent))
        self.assertEqual(audit.repositories[0].path, str(self.repo))
        subdir = self.repo / "subdir"
        write(subdir, "Cargo.toml", "manifest")
        write(subdir, "target/debug/output", "data")
        audit = self.engine.audit(str(subdir))
        self.assertEqual(audit.repositories[0].path, str(self.repo))
        self.assertTrue(audit.candidates[0].eligible)

    def test_linked_worktree_is_recognized(self):
        git(self.repo, "add", "Cargo.toml", ".gitignore")
        git(self.repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
        linked = self.workspace / "linked"
        git(self.repo, "worktree", "add", "--detach", "-q", str(linked))
        write(linked, "target/debug/output", "data")
        audit = self.engine.audit(str(linked))
        self.assertTrue(audit.candidates[0].eligible, audit.candidates[0].blockers)
        self.assertLess(audit.repositories[0].git_bytes, 1024)

    def test_git_failure_blocks_cleanup(self):
        with patch("gtrmrs.storage.engine._git", side_effect=FileNotFoundError("Git missing")):
            audit = self.engine.audit(str(self.repo))
        self.assertTrue(audit.errors)
        self.assertFalse(self.target_candidate(audit).eligible)

    def test_cli_json_and_cleanup_preview(self):
        stdout, stderr = self.command(self.workspace, "--json", "--clean")
        data = json.loads(stdout)
        self.assertEqual(data["cleanup"][0]["status"], "preview")
        self.assertFalse(stderr)
        self.assertTrue(self.target.exists())

    def test_cli_keeps_dependencies_unless_included(self):
        write(self.repo, "package.json", "{}")
        module = write(self.repo, "node_modules/module/dist/index.js", "dependency")
        write(self.repo, "node_modules/module/dist/query_compiler_bg.sqlite.wasm-base64.js", "code")
        write(self.repo, "node_modules/module/dist/startVitestModuleRunner.DB-7oCpn.js", "code")
        stdout, _ = self.command(self.repo, "--clean", "--apply", "--json")
        self.assertTrue(module.exists())
        self.assertEqual(len(json.loads(stdout)["cleanup"]), 1)
        stdout, _ = self.command(self.repo, "--clean", "--apply", "--include-deps", "--json")
        self.assertEqual(json.loads(stdout)["cleanup"][0]["status"], "removed")
        self.assertFalse(module.exists())

    def test_cli_apply_requires_clean(self):
        with self.assertRaises(SystemExit) as raised:
            self.command(self.repo, "--apply")
        self.assertEqual(raised.exception.code, 2)
        self.assertTrue(self.target.exists())

    def test_cli_unmatched_repo_never_deletes(self):
        with self.assertRaises(SystemExit) as raised:
            self.command(self.workspace, "--repo", "missing", "--clean", "--apply")
        self.assertEqual(raised.exception.code, 2)
        self.assertTrue(self.target.exists())

    def test_cli_report_path_inside_cleanup_target_is_refused(self):
        with self.assertRaises(SystemExit):
            self.command(self.repo, "--clean", "--apply", "--out", self.build / "report.json")
        self.assertTrue(self.target.exists())

    def test_cli_output_failure_exits_nonzero(self):
        with self.assertRaises(SystemExit) as raised:
            self.command(self.repo, "--out", self.workspace / "missing" / "report.json")
        self.assertEqual(raised.exception.code, 2)

    def test_umbrella_registers_storage(self):
        from gtrmrs.cli import main as umbrella
        output = io.StringIO()
        with patch("sys.argv", ["gtrmrs", "storage", str(self.repo), "--json"]), contextlib.redirect_stdout(output):
            umbrella()
        self.assertEqual(json.loads(output.getvalue())["root"], str(self.repo))

    def test_subtree_report_names_owner_and_explains_size_scope(self):
        write(self.repo, "subdir/file.txt", "data")
        stdout, _ = self.command(self.repo / "subdir")
        self.assertIn("music", stdout)
        self.assertIn("Scanned subtree: subdir", stdout)
        self.assertIn("file totals cover this subtree only", stdout)
        self.assertNotIn(".. ", stdout)
        audit = self.engine.audit(str(self.repo / "subdir"))
        self.assertEqual(audit.bytes, 4)
        self.assertEqual(audit.repositories[0].bytes, 4)
        self.assertEqual(audit.repositories[0].git_bytes, 0)

    def test_more_credential_names_and_formats_block_cleanup(self):
        for name in ("credentials.p8", "chain.p7b", "private.der", "client_secret_app.json",
                     "credentials.json", "project-service-account.json", "id_ed25519", ".netrc"):
            with self.subTest(name=name):
                path = write(self.repo, "target/debug/" + name, "keep")
                candidate = self.target_candidate(self.engine.audit(str(self.repo)))
                self.assertFalse(candidate.eligible)
                path.unlink()

    def test_keep_patterns_cover_files_directories_and_ancestors(self):
        write(self.repo, "target/debug/custom/data", "keep")
        for pattern in ("data", "target/debug/custom", "target/debug/", "target", "*/custom/*", "."):
            with self.subTest(pattern=pattern):
                audit = self.engine.audit(str(self.repo), keep_patterns=[pattern])
                candidate = self.target_candidate(audit)
                self.assertFalse(candidate.eligible)
                self.assertIn("Matches a user keep pattern", " ".join(candidate.blockers))
                self.assertEqual(audit.to_dict()["keep_patterns"], [pattern.rstrip("/")])

    def test_keep_pattern_paths_are_relative_to_scan_root(self):
        audit = self.engine.audit(str(self.workspace), keep_patterns=["music/target/debug"])
        self.assertFalse(self.target_candidate(audit).eligible)
        audit = self.engine.audit(str(self.workspace), keep_patterns=["target/debug"])
        self.assertTrue(self.target_candidate(audit).eligible)

    def test_invalid_keep_patterns_are_rejected(self):
        for pattern in ("", "../target", "/target", "C:/target", "target/../debug"):
            with self.assertRaises(ValueError):
                self.engine.audit(str(self.repo), keep_patterns=[pattern])

    def test_keep_rules_are_carried_into_cleanup_reinspection(self):
        audit = self.engine.audit(str(self.repo), keep_patterns=["important.bin"])
        candidate = self.target_candidate(audit)
        self.assertTrue(candidate.eligible)
        path = write(self.repo, "target/debug/important.bin", "keep")
        result = self.engine.clean(audit, [candidate], apply=True)
        self.assertEqual(result[0]["status"], "refused")
        self.assertIn("keep pattern", result[0]["error"])
        self.assertTrue(path.exists())

    def test_new_credential_format_is_rechecked_before_cleanup(self):
        audit = self.engine.audit(str(self.repo))
        path = write(self.repo, "target/debug/key.p8", "keep")
        result = self.engine.clean(audit, [self.target_candidate(audit)], apply=True)
        self.assertEqual(result[0]["status"], "refused")
        self.assertTrue(path.exists())

    def test_cli_keep_is_repeatable_and_excludes_selected_cleanup(self):
        write(self.repo, "__pycache__/module.pyc", "bytecode")
        stdout, _ = self.command(self.repo, "--clean", "--apply", "--json",
                                 "--keep", "target/debug", "--keep", "__pycache__")
        data = json.loads(stdout)
        self.assertEqual(data["selected_bytes"], 0)
        self.assertEqual(data["cleanup"], [])
        self.assertTrue(self.build.exists())
        self.assertTrue((self.repo / "__pycache__/module.pyc").exists())

    def test_dependency_credential_directory_is_retained(self):
        write(self.repo, "package.json", "{}")
        path = write(self.repo, "node_modules/package/.aws/custom", "keep")
        audit = self.engine.audit(str(self.repo))
        candidate = next(c for c in audit.candidates if c.kind == "dependencies")
        self.assertFalse(candidate.eligible)
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
