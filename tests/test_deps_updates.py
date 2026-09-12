"""Safe dependency plans and per-file atomic update regressions."""

import argparse
import contextlib
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from gtrmrs.deps import cli
from gtrmrs.deps.engine import DepsEngine
from gtrmrs.deps.models import UpdateAction, UpstreamInfo
from gtrmrs.deps.scanners import android
from gtrmrs.deps.updater.toml_updater import CatalogUpdater


def library(version):
    return '[libraries]\nlib = "example:lib:' + version + '"\n'


class TestSafeDependencyUpdates(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.engine = DepsEngine()

    def catalog(self, name, content):
        path = self.root / name / "gradle/libs.versions.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
        return path

    def audit(self, **options):
        return self.engine.run_audit(str(self.root), no_upstream=True, **options)

    def command(self, *arguments):
        parser = argparse.ArgumentParser()
        cli._configure_parser(parser)
        stdout, stderr = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                cli.run(parser.parse_args([str(self.root), "--no-upstream", "--no-color", *map(str, arguments)]))
            except SystemExit as exc:
                code = exc.code
        return code, stdout.getvalue(), stderr.getvalue()

    def pair(self):
        old = self.catalog("my-old", library("1.0"))
        new = self.catalog("new", library("2.0"))
        return old, new

    def shared(self):
        return self.catalog("old", '[versions]\nshared = "1.0"\n[libraries]\na = {module="example:a", version.ref="shared"}\nb = {module="example:b", version.ref="shared"}\n')

    def test_conflicting_shared_reference_refuses_the_plan(self):
        old = self.shared()
        self.catalog("new", '[libraries]\na = "example:a:2.0"\nb = "example:b:3.0"\n')
        original = old.read_bytes()
        with self.assertRaisesRegex(ValueError, r"Conflicting updates.*shared.*libraries.a.*2.0.*libraries.b.*3.0"):
            self.engine.plan_updates(self.audit())
        code, _, errors = self.command("--align")
        self.assertEqual(code, 1)
        self.assertIn("Conflicting updates", errors)
        self.assertEqual(old.read_bytes(), original)

    def test_unchanged_shared_consumer_is_not_silently_updated(self):
        old = self.shared()
        self.catalog("new", '[libraries]\na = "example:a:2.0"\nb = "example:b:1.0"\n')
        with self.assertRaisesRegex(ValueError, "Conflicting updates"):
            self.engine.plan_updates(self.audit())
        self.assertIn(b'shared = "1.0"', old.read_bytes())

    def test_unknown_upstream_consumer_blocks_shared_update(self):
        self.shared()
        result = self.audit()
        for component in result.components:
            if component.identifier == "example:a":
                component.upstream = UpstreamInfo("fixture", latest_stable="2.0")
        with self.assertRaisesRegex(ValueError, "Conflicting updates"):
            self.engine.plan_updates(result, mode="upstream")

    def test_agreeing_shared_reference_is_written_once(self):
        old = self.shared()
        self.catalog("new", '[libraries]\na = "example:a:2.0"\nb = "example:b:2.0"\n')
        actions = self.engine.plan_updates(self.audit())
        self.assertEqual(len(actions), 1)
        with patch("gtrmrs.deps.updater.toml_updater.os.replace", wraps=os.replace) as replace:
            self.assertTrue(all(success for _, success in self.engine.apply_actions(actions)))
        self.assertEqual(replace.call_count, 1)
        self.assertEqual(android.AndroidScanner().parse_toml(str(old.parents[1]))["versions"]["shared"], "2.0")

    def test_shared_reference_checks_plugins_and_libraries_together(self):
        self.catalog("old", '[versions]\nshared="1.0"\n[libraries]\na={module="example:a", version.ref="shared"}\n[plugins]\np={id="example.plugin", version.ref="shared"}\n')
        self.catalog("new", '[libraries]\na="example:a:2.0"\n[plugins]\np={id="example.plugin", version="3.0"}\n')
        with self.assertRaisesRegex(ValueError, "plugins.p"):
            self.engine.plan_updates(self.audit())

    def test_duplicate_aliases_use_their_own_old_versions(self):
        old = self.catalog("old", '[libraries]\nfirst="example:lib:1.0"\nsecond="example:lib:1.5"\n')
        self.catalog("new", library("2.0"))
        actions = self.engine.plan_updates(self.audit())
        self.assertEqual({action.old_version for action in actions}, {"1.0", "1.5"})
        with patch("gtrmrs.deps.updater.toml_updater.os.replace", wraps=os.replace) as replace:
            self.assertTrue(all(success for _, success in self.engine.apply_actions(actions)))
        self.assertEqual(replace.call_count, 1)
        parsed = android.AndroidScanner().parse_toml(str(old.parents[1]))["libraries"]
        self.assertEqual([item["version"] for item in parsed.values()], ["2.0", "2.0"])

    def test_duplicate_aliases_do_not_hide_the_highest_version(self):
        self.catalog("only", '[libraries]\nfirst="example:lib:2.0"\nsecond="example:lib:1.0"\n')
        result = self.audit()
        self.assertEqual(result.components[0].latest_in_repos, "2.0")
        actions = self.engine.plan_updates(result)
        self.assertEqual([(action.key_or_alias, action.new_version) for action in actions], [("second", "2.0")])

    def test_library_and_plugin_aliases_are_separate(self):
        old = self.catalog("old", '[libraries]\nsame={module="example:gradle-plugin", version="1.0"}\n[plugins]\nsame={id="com.android.application", version="8.0"}\n')
        self.catalog("new", '[libraries]\nsame={module="example:gradle-plugin", version="2.0"}\n[plugins]\nsame={id="com.android.application", version="8.1"}\n')
        actions = self.engine.plan_updates(self.audit())
        self.assertEqual({action.component_type for action in actions}, {"library", "plugin"})
        self.assertTrue(all(success for _, success in self.engine.apply_actions(actions)))
        parsed = android.AndroidScanner().parse_toml(str(old.parents[1]))
        self.assertEqual(parsed["libraries"]["same"]["version"], "2.0")
        self.assertEqual(parsed["plugins"]["same"]["version"], "8.1")

    def test_legacy_plugin_action_uses_catalog_identity(self):
        path = self.catalog("only", '[plugins]\nandroid={id="com.android.application", version="8.0"}\n')
        action = UpdateAction("only", str(path), "com.android.application", "android", "8.0", "8.1", "align")
        self.assertTrue(CatalogUpdater().apply_action(action))
        self.assertIn(b'version="8.1"', path.read_bytes())

    def test_plugin_shorthand_is_updated(self):
        path = self.catalog("only", '[plugins]\np="example.plugin:1.0"\n')
        action = UpdateAction("only", str(path), "example.plugin", "p", "1.0", "2.0", "upstream", component_type="plugin")
        self.assertTrue(CatalogUpdater().apply_action(action))
        self.assertIn(b'example.plugin:2.0', path.read_bytes())

    def test_selected_repository_retains_comparison_context(self):
        old, new = self.pair()
        reference = new.read_bytes()
        self.assertEqual(list(self.audit(target_repo="my-old").profiles), ["my-old"])
        code, _, errors = self.command("--repo", "my-o", "--align")
        self.assertEqual((code, errors), (0, ""))
        self.assertIn(b'example:lib:2.0', old.read_bytes())
        self.assertEqual(new.read_bytes(), reference)

    def test_comparison_scope_still_refuses_unmatched_repository(self):
        old, new = self.pair()
        originals = [path.read_bytes() for path in (old, new)]
        self.assertFalse(self.audit(target_repo="missing", comparison_scope=True).profiles)
        self.assertEqual(self.command("--repo", "missing", "--align")[0], 1)
        self.assertEqual([path.read_bytes() for path in (old, new)], originals)

    def test_planning_filter_matches_the_audit_filter(self):
        self.pair()
        self.catalog("my-other", library("1.5"))
        result = self.audit(target_repo="MY-", comparison_scope=True)
        actions = self.engine.plan_updates(result, target_repo="MY-")
        self.assertEqual({action.repo_name for action in actions}, {"my-old", "my-other"})

    def test_case_insensitive_exact_match_precedes_partial_matches(self):
        self.catalog("old", library("1.0"))
        other = self.catalog("my-old", library("1.5"))
        self.catalog("new", library("2.0"))
        original = other.read_bytes()
        result = self.audit(target_repo="OLD", comparison_scope=True)
        actions = self.engine.plan_updates(result, target_repo="OLD")
        self.assertEqual({action.repo_name for action in actions}, {"old"})
        self.assertTrue(all(success for _, success in self.engine.apply_actions(actions)))
        self.assertEqual(other.read_bytes(), original)

    def test_version_edit_between_audit_and_plan_is_preserved(self):
        old, _ = self.pair()
        result = self.audit()
        old.write_bytes(library("3.0").encode())
        actions = self.engine.plan_updates(result)
        self.assertFalse(any(success for _, success in self.engine.apply_actions(actions)))
        self.assertEqual(old.read_bytes(), library("3.0").encode())

    def test_comment_edit_after_planning_is_preserved(self):
        old, _ = self.pair()
        actions = self.engine.plan_updates(self.audit())
        edited = b"# user edit\n" + old.read_bytes()
        old.write_bytes(edited)
        self.assertFalse(any(success for _, success in self.engine.apply_actions(actions)))
        self.assertEqual(old.read_bytes(), edited)
        self.assertIn("changed since planning", self.engine.updater.last_errors[str(old)])

    def test_manual_stale_action_checks_old_version(self):
        path = self.catalog("only", '[versions]\nv="3.0"\n')
        action = UpdateAction("only", str(path), "example:lib", "lib", "1.0", "2.0", "align", True, "v")
        updater = CatalogUpdater()
        self.assertFalse(updater.apply_action(action))
        self.assertIn(b'v="3.0"', path.read_bytes())

    def test_one_bad_action_preserves_the_entire_file(self):
        path = self.catalog("only", '[libraries]\na="example:a:1.0"\nb="example:b:1.0"\n')
        original = path.read_bytes()
        actions = [UpdateAction("only", str(path), "example:" + alias, alias, old, "2.0", "align", component_type="library") for alias, old in (("a", "1.0"), ("b", "wrong"))]
        updater = CatalogUpdater()
        with patch("gtrmrs.deps.updater.toml_updater.os.replace") as replace:
            self.assertFalse(any(success for _, success in updater.apply_actions(actions)))
        replace.assert_not_called()
        self.assertEqual(path.read_bytes(), original)

    def test_replacement_failure_preserves_original_and_reports_failure(self):
        old, _ = self.pair()
        original = old.read_bytes()
        with patch("gtrmrs.deps.updater.toml_updater.os.replace", side_effect=OSError("disk failure")):
            code, _, errors = self.command("--align")
        self.assertEqual(code, 1)
        self.assertIn("Failed update", errors)
        self.assertIn("disk failure", errors)
        self.assertEqual(old.read_bytes(), original)
        self.assertEqual(list(old.parent.glob(".gtrmrs-update-*")), [])

    def test_flush_failure_preserves_original(self):
        old, _ = self.pair()
        original = old.read_bytes()
        actions = self.engine.plan_updates(self.audit())
        with patch("gtrmrs.deps.updater.toml_updater.os.fsync", side_effect=OSError("disk full")):
            self.assertFalse(any(success for _, success in self.engine.apply_actions(actions)))
        self.assertEqual(old.read_bytes(), original)
        self.assertEqual(list(old.parent.glob(".gtrmrs-update-*")), [])

    def test_edit_during_preparation_is_detected(self):
        old, _ = self.pair()
        actions = self.engine.plan_updates(self.audit())
        sync = os.fsync
        edited = b"# edited during write\n" + old.read_bytes()
        def changed(descriptor):
            sync(descriptor)
            old.write_bytes(edited)
        with patch("gtrmrs.deps.updater.toml_updater.os.fsync", side_effect=changed):
            self.assertFalse(any(success for _, success in self.engine.apply_actions(actions)))
        self.assertEqual(old.read_bytes(), edited)

    def test_dry_run_validates_without_writing(self):
        old, _ = self.pair()
        original = old.read_bytes()
        with patch("gtrmrs.deps.updater.toml_updater.os.replace") as replace:
            self.assertEqual(self.command("--align", "--dry-run")[0], 0)
        replace.assert_not_called()
        self.assertEqual(old.read_bytes(), original)
        self.assertEqual(list(old.parent.glob(".gtrmrs-update-*")), [])

    def test_dry_run_refuses_unsupported_catalog_edit(self):
        old = self.catalog("old", '[libraries]\n"quoted-alias"="example:lib:1.0"\n')
        self.catalog("new", library("2.0"))
        original = old.read_bytes()
        code, _, errors = self.command("--align", "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("Could not prepare update", errors)
        self.assertEqual(old.read_bytes(), original)

    def test_newlines_and_missing_final_newline_are_preserved(self):
        for ending in ("\n", "\r\n", ""):
            with self.subTest(ending=repr(ending)):
                content = '[versions]' + (ending or "\n") + 'v="1.0"' + ending
                path = self.catalog("only", content)
                action = UpdateAction("only", str(path), "example:lib", "lib", "1.0", "2.0", "align", True, "v")
                self.assertTrue(CatalogUpdater().apply_action(action))
                self.assertEqual(path.read_bytes(), content.replace('v="1.0"', 'v="2.0"').encode())

    def test_commented_section_header_and_file_mode_are_preserved(self):
        path = self.catalog("only", '[versions] # keep comment\nv="1.0"\n')
        initial_mode = stat.S_IMODE(path.stat().st_mode)
        action = UpdateAction("only", str(path), "example:lib", "lib", "1.0", "2.0", "align", True, "v")
        self.assertTrue(CatalogUpdater().apply_action(action))
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), initial_mode)
        self.assertIn(b"# keep comment", path.read_bytes())

    def test_invalid_generated_toml_is_refused(self):
        path = self.catalog("only", library("1.0"))
        original = path.read_bytes()
        action = UpdateAction("only", str(path), "example:lib", "lib", "1.0", '2.0"broken', "align")
        self.assertFalse(CatalogUpdater().apply_action(action))
        self.assertEqual(path.read_bytes(), original)

    def test_invalid_utf8_is_not_silently_discarded(self):
        path = self.catalog("only", library("1.0"))
        original = path.read_bytes() + b"# invalid byte \xff\n"
        path.write_bytes(original)
        action = UpdateAction("only", str(path), "example:lib", "lib", "1.0", "2.0", "align")
        self.assertFalse(CatalogUpdater().apply_action(action))
        self.assertEqual(path.read_bytes(), original)

    def test_no_full_toml_parser_refuses_writes(self):
        path = self.catalog("only", library("1.0"))
        original = path.read_bytes()
        updater = CatalogUpdater()
        action = UpdateAction("only", str(path), "example:lib", "lib", "1.0", "2.0", "align")
        with patch.object(android, "tomllib", None):
            self.assertFalse(updater.apply_action(action))
        self.assertIn("Python 3.11+ standard-library TOML parser", updater.last_errors[str(path)])
        self.assertEqual(path.read_bytes(), original)

    def test_report_cannot_overwrite_planned_catalog(self):
        old, _ = self.pair()
        original = old.read_bytes()
        code, _, errors = self.command("--json", "--out", old, "--align")
        self.assertEqual(code, 1)
        self.assertIn("cannot overwrite", errors)
        self.assertEqual(old.read_bytes(), original)

    def test_wrapper_failure_preserves_original(self):
        project = self.root / "only"
        path = project / "gradle/wrapper/gradle-wrapper.properties"
        path.parent.mkdir(parents=True)
        original = b"distributionUrl=https\\://services.gradle.org/distributions/gradle-8.0-bin.zip\r\n"
        path.write_bytes(original)
        action = UpdateAction("only", str(path), "Gradle Wrapper Distribution", "distributionUrl", "8.0", "8.1", "align", component_type="build_tool")
        updater = CatalogUpdater()
        with patch("gtrmrs.deps.updater.toml_updater.os.replace", side_effect=OSError("locked file")):
            self.assertFalse(updater.apply_action(action))
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(path.parent.glob(".gtrmrs-update-*")), [])
        self.assertTrue(updater.apply_action(action))
        self.assertEqual(path.read_bytes(), original.replace(b"8.0", b"8.1"))

    def test_invalid_wrapper_version_is_refused(self):
        path = self.root / "only/gradle/wrapper/gradle-wrapper.properties"
        path.parent.mkdir(parents=True)
        original = b"distributionUrl=https\\://services.gradle.org/distributions/gradle-8.0-bin.zip\n"
        path.write_bytes(original)
        action = UpdateAction("only", str(path), "Gradle Wrapper Distribution", "distributionUrl", "8.0", "8.1\ninjected=true", "align", component_type="build_tool")
        self.assertFalse(CatalogUpdater().apply_action(action))
        self.assertEqual(path.read_bytes(), original)

    def test_catalog_symlink_is_not_replaced_or_followed_for_writing(self):
        target = self.catalog("outside", library("1.0"))
        link = self.root / "catalog.toml"
        try:
            os.symlink(str(target), str(link))
        except OSError:
            self.skipTest("File symlinks unavailable")
        self.addCleanup(link.unlink)
        original = target.read_bytes()
        action = UpdateAction("only", str(link), "example:lib", "lib", "1.0", "2.0", "align")
        self.assertFalse(CatalogUpdater().apply_action(action))
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_bytes(), original)

    def test_report_cannot_overwrite_a_build_file_when_nothing_is_pending(self):
        path = self.catalog("only", library("1.0"))
        original = path.read_bytes()
        self.assertEqual(self.command("--align", "--json", "--out", path)[0], 1)
        self.assertEqual(path.read_bytes(), original)

    def test_read_only_catalog_is_not_replaced(self):
        path = self.catalog("only", library("1.0"))
        original = path.read_bytes()
        initial_mode = stat.S_IMODE(path.stat().st_mode)
        action = UpdateAction("only", str(path), "example:lib", "lib", "1.0", "2.0", "align")
        try:
            path.chmod(stat.S_IREAD)
            self.assertFalse(CatalogUpdater().apply_action(action))
        finally:
            path.chmod(initial_mode)
        self.assertEqual(path.read_bytes(), original)

    def test_hardlinked_report_cannot_overwrite_a_catalog(self):
        old, _ = self.pair()
        original = old.read_bytes()
        report = self.root / "report.json"
        try:
            os.link(str(old), str(report))
        except OSError:
            self.skipTest("Hard links unavailable")
        code, _, errors = self.command("--align", "--json", "--out", report)
        self.assertEqual(code, 1)
        self.assertIn("cannot overwrite", errors)
        self.assertEqual(old.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
