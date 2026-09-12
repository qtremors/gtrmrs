"""Gradle project discovery and explicit dependency coverage."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gtrmrs.deps import cli
from gtrmrs.deps.engine import DepsEngine
from gtrmrs.deps.report.html import HtmlReporter
from gtrmrs.deps.report.json_report import JsonReporter
from gtrmrs.deps.report.terminal import TerminalReporter
from gtrmrs.deps.scanners.android import AndroidScanner


class TestProjectDiscovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scanner = AndroidScanner()

    def write(self, name, text=""):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_recognition_and_discovery_agree_for_all_markers(self):
        for index, marker in enumerate(("settings.gradle", "settings.gradle.kts", "build.gradle",
                                       "build.gradle.kts", "gradle/libs.versions.toml",
                                       "gradle/wrapper/gradle-wrapper.properties")):
            name = "project" + str(index)
            self.write(name + "/" + marker)
            project = self.root / name
            self.assertTrue(self.scanner.can_scan_project(str(project)))
            self.assertEqual(self.scanner.discover_projects(str(project)), {name: str(project)})
        self.assertEqual(len(self.scanner.discover_projects(str(self.root))), 6)

    def test_settings_and_catalog_are_one_project_and_modules_are_not_roots(self):
        self.write("project/settings.gradle.kts")
        self.write("project/gradle/libs.versions.toml")
        self.write("project/app/build.gradle.kts")
        self.assertEqual(self.scanner.discover_projects(str(self.root)), {"project": str(self.root / "project")})

    def test_nested_projects_have_distinct_names(self):
        for branch in ("one", "two"):
            self.write("group/" + branch + "/project/settings.gradle.kts")
        self.assertEqual(set(self.scanner.discover_projects(str(self.root))), {"group/one/project", "group/two/project"})

    def test_single_nested_project_preserves_container_name(self):
        self.write("container/project/settings.gradle")
        self.assertEqual(self.scanner.discover_projects(str(self.root)), {"container": str(self.root / "container/project")})

    def test_generated_directories_are_pruned(self):
        for name in ("build", "node_modules", ".git", ".gradle", "target"):
            self.write(name + "/settings.gradle.kts")
            self.write("container/" + name + "/settings.gradle.kts")
        self.assertEqual(self.scanner.discover_projects(str(self.root)), {})

    def test_unreadable_discovery_is_not_a_successful_empty_scan(self):
        with patch("gtrmrs.deps.scanners.android.os.listdir", side_effect=PermissionError("fixture denied")):
            with self.assertRaisesRegex(PermissionError, "fixture denied"):
                self.scanner.discover_projects(str(self.root))

    def test_catalog_free_project_reports_wrapper_sdk_and_unknown_coverage(self):
        self.write("project/settings.gradle.kts", "rootProject.name = \"project\"\n")
        self.write("project/app/build.gradle.kts", "android { compileSdk = 35; defaultConfig { minSdk = 24 } }\n")
        self.write("project/gradle/wrapper/gradle-wrapper.properties", "distributionUrl=https\\://example.invalid/gradle-8.10-bin.zip\n")
        result = DepsEngine().run_audit(str(self.root), no_upstream=True)
        profile = result.profiles["project"]
        self.assertEqual(profile.build_tool_version, "8.10")
        self.assertEqual(profile.sdk_info["compileSdk"], ["35"])
        self.assertEqual(profile.libraries_count, 0)
        coverage = JsonReporter().to_dict(result)["profiles"]["project"]["dependency_coverage"]
        self.assertIsNone(coverage["catalog"])
        self.assertFalse(coverage["complete"])
        html_path = self.root / "report.html"
        HtmlReporter().generate(result, str(html_path))
        for report in (TerminalReporter(False).generate(result), html_path.read_text(encoding="utf-8")):
            self.assertIn("Dependency coverage unknown", report)
            self.assertIn("custom/imported catalogs", report)
        self.assertNotIn("No discrepancies detected across scanned repositories.", TerminalReporter(False).generate(result))
        self.assertEqual(DepsEngine().plan_updates(result), [])

    def test_default_catalog_coverage_is_also_scoped(self):
        self.write("project/gradle/libs.versions.toml", '[libraries]\nlib="example:lib:1.0"\n')
        result = DepsEngine().run_audit(str(self.root), no_upstream=True)
        profile = result.profiles["project"]
        self.assertEqual(profile.libraries_count, 1)
        self.assertEqual(profile.metadata["dependency_coverage"]["catalog"], "gradle/libs.versions.toml")
        self.assertIn("build-script dependencies", " ".join(profile.metadata["declaration_notes"]))

    def test_settings_only_cli_json_succeeds_with_explicit_coverage(self):
        self.write("project/settings.gradle")
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.argv", ["deps", str(self.root), "--no-upstream", "--json"]), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            cli.main()
        data = json.loads(stdout.getvalue())
        self.assertEqual(data["components"], [])
        self.assertFalse(data["profiles"]["project"]["dependency_coverage"]["complete"])


if __name__ == "__main__":
    unittest.main()
