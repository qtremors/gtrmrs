"""
test_deps.py

Unit tests for deps subcommand: scanning, parsing, discrepancy detection,
and in-place TOML catalog updating.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from gtrmrs.deps.engine import DepsEngine
from gtrmrs.deps.models import Component, UpdateAction
from gtrmrs.deps.report.html import HtmlReporter
from gtrmrs.deps.report.json_report import JsonReporter
from gtrmrs.deps.scanners.android import AndroidScanner
from gtrmrs.deps.scanners.base import is_preview_version, parse_semver
from gtrmrs.deps.updater.toml_updater import CatalogUpdater


def write_file(root: str, relative_path: str, content: str) -> str:
    path = os.path.join(root, *relative_path.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


SAMPLE_TOML = """# Version Catalog
[versions]
agp = "8.4.0"
kotlin = "1.9.22"
appcompat = "1.6.1"
compose-bom = "2024.02.00"

[libraries]
androidx-appcompat = { group = "androidx.appcompat", name = "appcompat", version.ref = "appcompat" }
# OkHttp inline string
okhttp = "com.squareup.okhttp3:okhttp:4.12.0"
retrofit = { module = "com.squareup.retrofit2:retrofit", version = "2.9.0" }

[plugins]
android-application = { id = "com.android.application", version.ref = "agp" }
kotlin-android = { id = "org.jetbrains.kotlin.android", version.ref = "kotlin" }
"""


class TestDepsSemver(unittest.TestCase):
    def test_semver_comparisons(self) -> None:
        self.assertGreater(parse_semver("1.2.3"), parse_semver("1.2.0"))
        self.assertGreater(parse_semver("2.4.20"), parse_semver("2.4.10"))
        self.assertGreater(parse_semver("2026.09.00"), parse_semver("2026.08.00"))
        # Stable is greater than alpha/beta/rc
        self.assertGreater(parse_semver("1.5.0"), parse_semver("1.5.0-alpha26"))
        self.assertGreater(parse_semver("1.5.0-beta01"), parse_semver("1.5.0-alpha01"))
        self.assertGreater(parse_semver("1.5.0-rc01"), parse_semver("1.5.0-beta01"))

    def test_preview_detection(self) -> None:
        self.assertTrue(is_preview_version("1.5.0-alpha28"))
        self.assertTrue(is_preview_version("2.0.0-rc.1"))
        self.assertTrue(is_preview_version("1.0.0-beta02"))
        self.assertFalse(is_preview_version("1.5.0"))
        self.assertFalse(is_preview_version("2026.09.00"))


class TestAndroidScanner(unittest.TestCase):
    def test_scan_single_repo(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            write_file(repo, "gradle/libs.versions.toml", SAMPLE_TOML)
            write_file(
                repo,
                "gradle/wrapper/gradle-wrapper.properties",
                "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.6-bin.zip\n",
            )
            write_file(
                repo,
                "app/build.gradle.kts",
                "android {\n    compileSdk = 34\n    defaultConfig {\n        minSdk = 24\n        targetSdk = 34\n    }\n}\n",
            )

            scanner = AndroidScanner()
            self.assertTrue(scanner.can_scan_project(repo))

            profile, toml_data = scanner.scan_project("test-repo", repo)
            self.assertEqual(profile.build_tool_version, "8.6")
            self.assertEqual(profile.plugin_versions.get("agp"), "8.4.0")
            self.assertEqual(profile.plugin_versions.get("compose-bom"), "2024.02.00")
            self.assertIn("34", profile.sdk_info.get("compileSdk", []))
            self.assertIn("24", profile.sdk_info.get("minSdk", []))
            self.assertEqual(len(toml_data["libraries"]), 3)
            self.assertEqual(len(toml_data["plugins"]), 2)

    def test_discover_multi_repo(self) -> None:
        with tempfile.TemporaryDirectory() as base_dir:
            repo1 = os.path.join(base_dir, "repo1")
            repo2 = os.path.join(base_dir, "repo2")
            write_file(repo1, "gradle/libs.versions.toml", SAMPLE_TOML)
            write_file(repo2, "gradle/libs.versions.toml", SAMPLE_TOML)

            scanner = AndroidScanner()
            discovered = scanner.discover_projects(base_dir)
            self.assertIn("repo1", discovered)
            self.assertIn("repo2", discovered)


class TestCatalogUpdater(unittest.TestCase):
    def test_update_version_ref(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            toml_path = write_file(repo, "gradle/libs.versions.toml", SAMPLE_TOML)
            updater = CatalogUpdater()

            success, old_v, content = updater.update_version_ref(toml_path, "appcompat", "1.7.0")
            self.assertTrue(success)
            self.assertEqual(old_v, "1.6.1")
            self.assertIn('appcompat = "1.7.0"', content)
            self.assertIn('# Version Catalog', content)
            self.assertIn('agp = "8.4.0"', content)

    def test_update_inline_library(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            toml_path = write_file(repo, "gradle/libs.versions.toml", SAMPLE_TOML)
            updater = CatalogUpdater()

            # Update string coordinate
            success, old_v, content = updater.update_inline_library_or_plugin(
                toml_path, "libraries", "okhttp", "5.0.0"
            )
            self.assertTrue(success)
            self.assertEqual(old_v, "4.12.0")
            self.assertIn('okhttp = "com.squareup.okhttp3:okhttp:5.0.0"', content)

    def test_update_gradle_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            write_file(
                repo,
                "gradle/wrapper/gradle-wrapper.properties",
                "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.6-bin.zip\n",
            )
            updater = CatalogUpdater()

            success, old_v, content = updater.update_gradle_wrapper(repo, "8.7.0")
            self.assertTrue(success)
            self.assertEqual(old_v, "8.6")
            self.assertIn("gradle-8.7.0-bin.zip", content)


class TestAuditAndPlanning(unittest.TestCase):
    def test_audit_detects_discrepancy(self) -> None:
        with tempfile.TemporaryDirectory() as base_dir:
            repo1_toml = SAMPLE_TOML  # has appcompat 1.6.1
            repo2_toml = SAMPLE_TOML.replace('appcompat = "1.6.1"', 'appcompat = "1.7.0"')

            write_file(base_dir, "repo1/gradle/libs.versions.toml", repo1_toml)
            write_file(base_dir, "repo2/gradle/libs.versions.toml", repo2_toml)

            engine = DepsEngine()
            result = engine.run_audit(base_dir, no_upstream=True)

            self.assertEqual(len(result.profiles), 2)
            self.assertGreater(result.repo_discrepancies_count, 0)

            # Plan alignment updates
            actions = engine.plan_updates(result, mode="align")
            self.assertTrue(any(a.repo_name == "repo1" and a.ref_name == "appcompat" for a in actions))

            # Apply actions (dry-run)
            results = engine.apply_actions(actions, dry_run=True)
            self.assertTrue(all(ok for _, ok in results))

            # Verify file was NOT modified in dry-run
            with open(os.path.join(base_dir, "repo1/gradle/libs.versions.toml")) as f:
                self.assertIn('appcompat = "1.6.1"', f.read())

            # Apply actions (real)
            results = engine.apply_actions(actions, dry_run=False)
            self.assertTrue(all(ok for _, ok in results))

            # Verify file WAS modified
            with open(os.path.join(base_dir, "repo1/gradle/libs.versions.toml")) as f:
                self.assertIn('appcompat = "1.7.0"', f.read())

    def test_reporters_generate_without_em_dashes(self) -> None:
        with tempfile.TemporaryDirectory() as base_dir:
            write_file(base_dir, "repo1/gradle/libs.versions.toml", SAMPLE_TOML)
            engine = DepsEngine()
            result = engine.run_audit(base_dir, no_upstream=True)

            # JSON test
            json_out = JsonReporter().generate(result)
            self.assertIn('"total_components"', json_out)

            # HTML test
            html_path = os.path.join(base_dir, "report.html")
            HtmlReporter().generate(result, html_path)
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertIn("Android Repositories Dependency & Upgrade Audit", content)
                # Confirm no em dashes
                self.assertNotIn("\u2014", content)


if __name__ == "__main__":
    unittest.main()
