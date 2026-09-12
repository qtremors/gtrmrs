"""Dependency report content, output formats, and CLI regressions."""

import argparse
import contextlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from gtrmrs.core.colors import Colors
from gtrmrs.deps import cli
from gtrmrs.deps.engine import DepsEngine
from gtrmrs.deps.models import AuditResult, Component, ProjectProfile, UpstreamInfo
from gtrmrs.deps.report.html import HtmlReporter
from gtrmrs.deps.report.json_report import JsonReporter
from gtrmrs.deps.report.terminal import TerminalReporter


class Markup(HTMLParser):
    def __init__(self, content):
        super().__init__(convert_charrefs=True)
        self.elements = []
        self.text = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


class Terminal(io.StringIO):
    def isatty(self):
        return True


class TestDependencyReports(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def catalog(self, name="repo", version="1.0"):
        path = self.root / name / "gradle/libs.versions.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('[libraries]\nlib="example:lib:' + version + '"\n', encoding="utf-8")
        return path

    def command(self, *arguments, tty=False, offline=True):
        parser = argparse.ArgumentParser()
        cli._configure_parser(parser)
        stdout = Terminal() if tty else io.StringIO()
        stderr = Terminal() if tty else io.StringIO()
        status = 0
        options = [str(self.root), *(["--no-upstream"] if offline else []), *map(str, arguments)]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                cli.run(parser.parse_args(options))
            except SystemExit as exc:
                status = exc.code
        return status, stdout.getvalue(), stderr.getvalue()

    def result(self):
        profile = ProjectProfile("repo", str(self.root), "android")
        component = Component("example:lib", "library", "Other", {"repo": "1.0"}, "1.0")
        return AuditResult(str(self.root), {"repo": profile}, [component], [], [], total_components=1)

    def html(self, result):
        path = self.root / "report.html"
        HtmlReporter().generate(result, str(path))
        return path.read_text(encoding="utf-8")

    def test_html_escapes_every_dynamic_text_and_attribute_context(self):
        payload = '\"><img src=x onerror="alert(1)"><script>alert(2)</script>&'
        result = self.result()
        profile = result.profiles.pop("repo")
        result.profiles[payload] = profile
        profile.build_tool_version = payload
        profile.plugin_versions = {"agp": payload, "kotlin-android": payload}
        profile.sdk_info = {"minSdk": [payload], "compileSdk": [payload]}
        profile.libraries_count = payload
        result.total_components = payload
        result.repo_discrepancies_count = payload
        result.upstream_available_count = payload
        result.up_to_date_count = payload
        component = result.components[0]
        component.identifier = payload
        component.component_type = payload
        component.category = payload
        component.latest_in_repos = payload
        component.repo_versions = {payload: payload}
        component.repo_statuses = {payload: "repo-outdated"}
        component.upstream = UpstreamInfo(payload, payload, payload)
        for status in (payload, "Newer Stable Available", "Newer Preview Available"):
            with self.subTest(status=status):
                component.upstream_status = status
                content = self.html(result)
                parsed = Markup(content)
                self.assertNotIn(payload, content)
                self.assertFalse(any(tag == "img" for tag, _ in parsed.elements))
                self.assertEqual(sum(tag == "script" for tag, _ in parsed.elements), 1)
                self.assertTrue(any(attrs.get("data-category") == payload for _, attrs in parsed.elements))
                self.assertIn(payload, "".join(parsed.text))
                self.assertFalse(any("onerror" in attrs for _, attrs in parsed.elements))

    def test_html_search_has_an_accessible_name(self):
        parsed = Markup(self.html(self.result()))
        search = next(attrs for _, attrs in parsed.elements if attrs.get("id") == "searchInput")
        self.assertEqual(search["aria-label"], "Search dependencies")

    def test_missing_sdk_values_are_unknown_in_text_and_html(self):
        result = self.result()
        for sdk in ({}, {"minSdk": [], "compileSdk": []}, {"minSdk": None, "compileSdk": None}):
            with self.subTest(sdk=sdk):
                result.profiles["repo"].sdk_info = sdk
                self.assertIn("<strong>Unknown / Unknown</strong>", self.html(result))
                text = TerminalReporter(False).generate(result)
                self.assertGreaterEqual(text.count("Unknown"), 2)
                self.assertEqual(JsonReporter().to_dict(result)["profiles"]["repo"]["sdk_info"], sdk)

    def test_real_sdk_values_are_retained(self):
        result = self.result()
        result.profiles["repo"].sdk_info = {"minSdk": ["21", "24"], "compileSdk": ["35"]}
        self.assertIn("<strong>21, 24 / 35</strong>", self.html(result))
        self.assertIn("21/24", TerminalReporter(False).generate(result))

    def test_offline_checks_are_marked_skipped_in_every_format(self):
        self.catalog()
        engine = DepsEngine()
        with patch.object(engine.resolver, "resolve_all") as resolve:
            result = engine.run_audit(str(self.root), no_upstream=True)
        resolve.assert_not_called()
        self.assertEqual(result.upstream_checks, {"checked": 0, "skipped": 1, "unavailable": 0})
        self.assertEqual(result.components[0].upstream_status, "Check Skipped")
        self.assertEqual(result.up_to_date_count, 0)
        text = TerminalReporter(False).generate(result)
        self.assertIn("checks were skipped", text)
        self.assertNotIn("All components are aligned", text)
        self.assertIn("0 checked, 1 skipped, 0 unavailable", self.html(result))
        data = JsonReporter().to_dict(result)
        self.assertEqual(data["components"][0]["upstream"]["check_status"], "skipped")
        self.assertEqual(data["upstream_checks"], result.upstream_checks)

    def test_failed_network_requests_are_unavailable(self):
        self.catalog()
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            result = DepsEngine().run_audit(str(self.root))
        self.assertEqual(result.components[0].upstream_status, "Unavailable")
        self.assertEqual(result.up_to_date_count, 0)
        self.assertEqual(result.upstream_checks["unavailable"], 1)
        self.assertIn("update status is unknown", TerminalReporter(False).generate(result))

    def test_missing_resolver_result_does_not_claim_success(self):
        self.catalog()
        engine = DepsEngine()
        with patch.object(engine.resolver, "resolve_all", return_value={}):
            result = engine.run_audit(str(self.root))
        self.assertEqual(result.upstream_checks["unavailable"], 1)
        self.assertEqual(result.up_to_date_count, 0)

    def test_mixed_success_and_failure_keep_separate_counts(self):
        path = self.catalog()
        path.write_text('[libraries]\na="example:a:1.0"\nb="example:b:1.0"\n', encoding="utf-8")
        engine = DepsEngine()
        releases = {"library:example:a": UpstreamInfo("fixture", "1.0", "1.0"), "library:example:b": UpstreamInfo("Error")}
        with patch.object(engine.resolver, "resolve_all", return_value=releases):
            result = engine.run_audit(str(self.root))
        self.assertEqual(result.upstream_checks, {"checked": 1, "skipped": 0, "unavailable": 1})
        self.assertEqual(result.up_to_date_count, 1)
        text = TerminalReporter(False).generate(result)
        self.assertIn("1 checked, 0 skipped, 1 unavailable", text)
        self.assertIn("among checked components", text)
        self.assertNotIn("All components are aligned", text)

    def test_older_repository_prevents_fully_up_to_date_count(self):
        self.catalog("old", "1.0")
        self.catalog("new", "2.0")
        engine = DepsEngine()
        with patch.object(engine.resolver, "resolve_all", return_value={"library:example:lib": UpstreamInfo("fixture", "2.0", "2.0")}):
            result = engine.run_audit(str(self.root))
        self.assertEqual(result.components[0].upstream_status, "Up to Date")
        self.assertEqual(result.up_to_date_count, 0)
        self.assertEqual(result.repo_discrepancies_count, 1)

    def test_preview_only_metadata_does_not_verify_stable_alignment(self):
        self.catalog(version="2.0-rc1")
        engine = DepsEngine()
        with patch.object(engine.resolver, "resolve_all", return_value={"library:example:lib": UpstreamInfo("fixture", latest_overall="2.0-rc1")}):
            result = engine.run_audit(str(self.root))
        self.assertEqual(result.components[0].upstream_status, "Stable Release Unknown")
        self.assertEqual(result.up_to_date_count, 0)
        self.assertEqual(result.upstream_checks["checked"], 1)
        self.assertIn("Stable release information is unknown", TerminalReporter(False).generate(result))

    def test_empty_report_does_not_claim_alignment(self):
        result = self.result()
        result.components = []
        result.total_components = 0
        self.assertIn("No components to check", TerminalReporter(False).generate(result))

    def test_no_color_applies_to_every_report_section(self):
        result = self.result()
        result.discrepancies = [("example:lib", "new (2.0)", "old (1.0)")]
        result.upstream_updates = [("example:lib", "1.0", "2.0 (Stable)", "fixture")]
        self.assertNotIn("\x1b", TerminalReporter(False).generate(result))
        self.assertIn("\x1b", TerminalReporter(True).generate(result))

    def test_profile_colors_use_version_order_for_all_fields(self):
        for field in ("gradle", "agp", "kotlin-android", "compose-bom"):
            with self.subTest(field=field):
                result = self.result()
                result.profiles = {}
                for name, version in (("old", "8.2"), ("new", "8.10")):
                    profile = ProjectProfile(name, str(self.root / name), "android")
                    if field == "gradle":
                        profile.build_tool_version = version
                    else:
                        profile.plugin_versions[field] = version
                    result.profiles[name] = profile
                width = 14 if field == "compose-bom" else 10
                output = TerminalReporter(True).generate(result)
                self.assertIn(Colors.GREEN + "8.10".ljust(width), output)
                self.assertIn(Colors.YELLOW + "8.2".ljust(width), output)

    def test_json_with_alignment_and_dry_run_remains_one_object(self):
        old = self.catalog("old", "1.0")
        self.catalog("new", "2.0")
        original = old.read_bytes()
        code, output, errors = self.command("--json", "--align", "--dry-run", "--no-color", tty=True)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["statistics"]["total_components"], 1)
        self.assertIn("Validated 1/1", errors)
        self.assertNotIn("\x1b", output + errors)
        self.assertEqual(old.read_bytes(), original)

    def test_json_remains_valid_after_a_failed_update(self):
        self.catalog("old", "1.0")
        self.catalog("new", "2.0")
        with patch("gtrmrs.deps.updater.toml_updater.os.replace", side_effect=OSError("locked")):
            code, output, errors = self.command("--json", "--align", "--no-color")
        self.assertEqual(code, 1)
        self.assertIn("statistics", json.loads(output))
        self.assertIn("Failed update", errors)

    def test_json_file_uses_stderr_for_notifications(self):
        self.catalog()
        path = self.root / "report.json"
        code, output, errors = self.command("--json", "--out", path)
        self.assertEqual((code, output), (0, ""))
        self.assertIn("JSON report written", errors)
        self.assertIn("statistics", json.loads(path.read_text(encoding="utf-8")))

    def test_json_html_and_browser_can_be_combined(self):
        self.catalog("alpha β")
        path = self.root / "report # β.html"
        with patch("gtrmrs.deps.cli.webbrowser.open", return_value=True) as browser:
            code, output, errors = self.command("--json", "--html", path, "--open")
        self.assertEqual(code, 0)
        self.assertIn("alpha β", json.loads(output)["profiles"])
        browser.assert_called_once_with(path.as_uri())
        self.assertIn("%20%23%20", browser.call_args.args[0])
        self.assertIn("%CE%B2", browser.call_args.args[0])
        self.assertIn("Interactive HTML Report generated", errors)
        self.assertTrue(path.is_file())

    def test_text_out_writes_plain_report_even_on_a_tty(self):
        self.catalog()
        path = self.root / "report.txt"
        code, output, errors = self.command("--out", path, tty=True)
        self.assertEqual((code, errors), (0, ""))
        content = path.read_text(encoding="utf-8")
        self.assertIn("REPOSITORY PROFILES", content)
        self.assertIn("Unknown", content)
        self.assertNotIn("\x1b", content)
        self.assertIn("Text report written", output)

    def test_redirected_terminal_output_has_no_generated_escape_codes(self):
        self.catalog()
        code, output, errors = self.command()
        self.assertEqual((code, errors), (0, ""))
        self.assertNotIn("\x1b", output)

    def test_no_color_covers_update_progress_on_a_tty(self):
        self.catalog("old", "1.0")
        self.catalog("new", "2.0")
        code, output, errors = self.command("--align", "--dry-run", "--no-color", tty=True)
        self.assertEqual(code, 0)
        self.assertIn("PLANNED UPDATES", output)
        self.assertNotIn("\x1b", output + errors)

    def test_report_write_failure_stops_updates(self):
        old = self.catalog("old", "1.0")
        self.catalog("new", "2.0")
        original = old.read_bytes()
        code, _, errors = self.command("--align", "--out", self.root / "missing/report.txt")
        self.assertEqual(code, 1)
        self.assertIn("Error writing report", errors)
        self.assertEqual(old.read_bytes(), original)

    def test_html_failure_has_a_clear_error_and_keeps_json_valid(self):
        self.catalog()
        with patch.object(HtmlReporter, "generate", side_effect=OSError("no space")):
            code, output, errors = self.command("--json", "--html", self.root / "report.html")
        self.assertEqual(code, 1)
        self.assertIn("statistics", json.loads(output))
        self.assertIn("no space", errors)

    def test_browser_failure_is_reported(self):
        self.catalog()
        path = self.root / "report.html"
        with patch("gtrmrs.deps.cli.webbrowser.open", return_value=False):
            code, output, errors = self.command("--json", "--html", path, "--open")
        self.assertEqual(code, 1)
        self.assertIn("browser could not open", errors)
        self.assertIn("statistics", json.loads(output))
        self.assertTrue(path.is_file())

    def test_report_formats_cannot_overwrite_each_other(self):
        self.catalog()
        path = self.root / "report.json"
        code, _, errors = self.command("--json", "--out", path, "--html", path)
        self.assertEqual(code, 1)
        self.assertIn("different output files", errors)
        self.assertFalse(path.exists())

    def test_audit_only_report_cannot_overwrite_source_catalog(self):
        path = self.catalog()
        original = path.read_bytes()
        code, _, errors = self.command("--json", "--out", path)
        self.assertEqual(code, 1)
        self.assertIn("cannot overwrite", errors)
        self.assertEqual(path.read_bytes(), original)

    def test_update_without_upstream_does_not_claim_up_to_date(self):
        self.catalog()
        code, output, errors = self.command("--json", "--update", "--no-color")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["upstream_checks"]["skipped"], 1)
        self.assertIn("checks were skipped", errors)
        self.assertNotIn("Everything is already", errors)

    def test_standalone_entry_point_normalizes_legacy_console_streams(self):
        self.catalog("alpha β")
        stdout_bytes, stderr_bytes = io.BytesIO(), io.BytesIO()
        stdout = io.TextIOWrapper(stdout_bytes, encoding="cp1252")
        stderr = io.TextIOWrapper(stderr_bytes, encoding="cp1252")
        with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", stderr), patch.object(sys, "argv", ["deps", str(self.root), "--no-upstream", "--no-color"]):
            cli.main()
            stdout.flush()
            stderr.flush()
        self.assertIn("alpha β", stdout_bytes.getvalue().decode("utf-8"))
        self.assertEqual(stdout.encoding, "utf-8")
        self.assertEqual(stderr.encoding, "utf-8")
        stdout.close()
        stderr.close()

    def test_run_normalizes_stderr_for_unicode_json_update_messages(self):
        self.catalog("old β", "1.0")
        self.catalog("new", "2.0")
        parser = argparse.ArgumentParser()
        cli._configure_parser(parser)
        args = parser.parse_args([str(self.root), "--no-upstream", "--json", "--align", "--dry-run", "--no-color"])
        stdout_bytes, stderr_bytes = io.BytesIO(), io.BytesIO()
        stdout = io.TextIOWrapper(stdout_bytes, encoding="utf-8")
        stderr = io.TextIOWrapper(stderr_bytes, encoding="cp1252")
        with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", stderr):
            cli.run(args)
            stdout.flush()
            stderr.flush()
        self.assertIn("statistics", json.loads(stdout_bytes.getvalue().decode("utf-8")))
        self.assertIn("old β", stderr_bytes.getvalue().decode("utf-8"))
        stdout.close()
        stderr.close()


if __name__ == "__main__":
    unittest.main()
