"""Gradle declaration reading without third-party packages or build execution."""

import argparse
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from gtrmrs.deps import cli
from gtrmrs.deps.engine import DepsEngine
from gtrmrs.deps.models import UpdateAction, UpstreamInfo
from gtrmrs.deps.report.html import HtmlReporter
from gtrmrs.deps.report.json_report import JsonReporter
from gtrmrs.deps.report.terminal import TerminalReporter
from gtrmrs.deps.scanners.android import AndroidScanner
from gtrmrs.deps.scanners.gradle import sdk_literals
from gtrmrs.deps.updater.toml_updater import CatalogUpdater


class TestGradleReading(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        self.scanner = AndroidScanner()

    def write(self, name, content, project=None):
        path = (project or self.project) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def catalog(self, text, project=None):
        return self.write("gradle/libs.versions.toml", text, project)

    def audit(self):
        return DepsEngine().run_audit(str(self.root), no_upstream=True)

    def command(self, *args):
        parser = argparse.ArgumentParser()
        cli._configure_parser(parser)
        output, errors = io.StringIO(), io.StringIO()
        status = 0
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            try:
                cli.run(parser.parse_args([str(self.root), "--no-upstream", *map(str, args)]))
            except SystemExit as exc:
                status = exc.code
        return status, output.getvalue(), errors.getvalue()

    def test_full_stdlib_parser_preserves_quoted_aliases_and_tables(self):
        self.catalog('''[versions] # comment
"shared.version" = '1.2'
[libraries."quoted.alias"]
group = "example"
name = "lib"
version.ref = "shared.version"
[plugins]
"android.library" = {id="com.android.library", version="8.1"}
''')
        parsed = self.scanner.parse_toml(str(self.project))
        self.assertEqual(parsed["libraries"]["quoted.alias"]["version"], "1.2")
        self.assertEqual(parsed["plugins"]["android.library"]["version"], "8.1")
        self.assertFalse(hasattr(self.scanner, "_parse_toml_basic"))

    def test_missing_catalog_is_distinct_from_invalid_catalog(self):
        self.assertEqual(self.scanner.parse_toml(str(self.project)), {"versions": {}, "libraries": {}, "plugins": {}})
        path = self.catalog('[libraries]\nlib = { broken\n')
        with self.assertRaisesRegex(ValueError, "Could not parse catalog") as raised:
            self.scanner.parse_toml(str(self.project))
        self.assertIn(str(path), str(raised.exception))
        self.assertIn("line 2", str(raised.exception))

    def test_invalid_utf8_catalog_reports_path(self):
        path = self.catalog('[libraries]\nlib="example:lib:1.0"\n')
        path.write_bytes(path.read_bytes() + b"# invalid \xff\n")
        with self.assertRaises(ValueError) as raised:
            self.audit()
        self.assertIn(str(path), str(raised.exception))

    def test_unreadable_catalog_is_not_reported_as_empty(self):
        self.catalog('[libraries]\nlib="example:lib:1.0"\n')
        with patch("gtrmrs.deps.scanners.android.open", side_effect=PermissionError("locked catalog")):
            with self.assertRaisesRegex(ValueError, "locked catalog"):
                self.scanner.parse_toml(str(self.project))

    def test_invalid_section_shapes_have_explicit_errors(self):
        for section in ("versions", "libraries", "plugins"):
            with self.subTest(section=section):
                self.catalog(section + " = []\n")
                with self.assertRaisesRegex(ValueError, "must be a table"):
                    self.audit()

    def test_invalid_coordinates_and_references_name_the_alias(self):
        for entry in ('{module="bad"}', '{module="example:lib", version.ref="absent"}', "42"):
            with self.subTest(entry=entry):
                self.catalog('[libraries]\nbroken = ' + entry + '\n')
                with self.assertRaises(ValueError) as raised:
                    self.audit()
                self.assertIn("[libraries].broken", str(raised.exception))

    def test_cli_parse_failure_preserves_reports_and_never_plans_updates(self):
        path = self.catalog('[libraries]\nbroken = {\n')
        original = path.read_bytes()
        report = self.root / "report.json"
        html = self.root / "report.html"
        report.write_text("previous JSON", encoding="utf-8")
        html.write_text("previous HTML", encoding="utf-8")
        with patch.object(DepsEngine, "plan_updates") as planner:
            status, output, errors = self.command("--json", "--out", report, "--html", html, "--update")
        self.assertEqual(status, 1)
        self.assertEqual(output, "")
        self.assertIn(str(path), errors)
        planner.assert_not_called()
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(report.read_text(encoding="utf-8"), "previous JSON")
        self.assertEqual(html.read_text(encoding="utf-8"), "previous HTML")

    def test_rich_reference_keeps_constraint_structure(self):
        self.catalog('''[versions]
v = {strictly="[1.0,2.0[", prefer="1.5", reject=["1.6"]}
[libraries]
lib = {module="example:lib", version.ref="v"}
''')
        parsed = self.scanner.parse_toml(str(self.project))
        entry = parsed["libraries"]["lib"]
        self.assertEqual(entry["version"], "[1.0,2.0[")
        self.assertEqual(entry["version_kind"], "constraint")
        self.assertEqual(entry["version_constraint"]["prefer"], "1.5")
        self.assertEqual(parsed["versions"]["v"]["reject"], ["1.6"])
        self.assertTrue(entry["is_ref"])

    def test_supported_rich_forms_are_never_compared_as_fixed_versions(self):
        declarations = ('{strictly="1.5"}', '{require="1.0", prefer="1.5"}',
                        '{prefer="1.5"}', '{reject=["1.5"]}', '{rejectAll=true}',
                        '"1.+"', '"latest.release"', '"[1,2)"', '"1.0!!"')
        for declaration in declarations:
            with self.subTest(declaration=declaration):
                self.catalog('[libraries]\nlib = {module="example:lib", version=' + declaration + '}\n')
                result = self.audit()
                component = result.components[0]
                self.assertEqual(component.repo_statuses["project"], "constraint")
                self.assertEqual(component.latest_in_repos, "N/A")
                self.assertEqual(DepsEngine().plan_updates(result), [])

    def test_unsupported_rich_shapes_remain_visible_and_not_updatable(self):
        for declaration in ('{future="1.0"}', '{reject="1.5"}', '{strictly=12}', '{rejectAll="yes"}', '{}', 'true'):
            with self.subTest(declaration=declaration):
                self.catalog('[libraries]\nlib = {module="example:lib", version=' + declaration + '}\n')
                result = self.audit()
                self.assertEqual(result.components[0].repo_statuses["project"], "unsupported")
                self.assertTrue(result.profiles["project"].metadata["declaration_notes"])
                self.assertEqual(DepsEngine().plan_updates(result), [])

    def test_versionless_and_unused_are_different_states(self):
        self.catalog('[libraries]\nmanaged={module="example:lib"}\n')
        self.catalog('[libraries]\nother="example:other:1.0"\n', self.root / "unused")
        component = next(c for c in self.audit().components if c.identifier == "example:lib")
        self.assertEqual(component.repo_statuses, {"project": "bom-managed", "unused": "unused"})
        self.assertIsNone(component.repo_versions["project"])
        self.assertEqual(component.repo_declarations["project"][0]["kind"], "managed")

    def test_managed_libraries_show_in_text_html_and_json_without_claiming_a_bom(self):
        self.catalog('[libraries]\nmanaged={module="example:lib"}\n')
        result = self.audit()
        text = TerminalReporter(False).generate(result)
        self.assertIn("Managed / versionless", text)
        self.assertIn("[libraries].managed", text)
        path = self.root / "report.html"
        HtmlReporter().generate(result, str(path))
        html = path.read_text(encoding="utf-8")
        self.assertIn("Managed / versionless", html)
        self.assertNotIn("Managed by BOM", html)
        encoded = json.loads(JsonReporter().generate(result))
        self.assertEqual(encoded["components"][0]["repo_statuses"]["project"], "bom-managed")
        self.assertEqual(encoded["components"][0]["repo_declarations"]["project"][0]["kind"], "managed")

    def test_constraints_are_escaped_and_preserved_in_reports(self):
        self.catalog('''[libraries]
lib={module="example:lib", version={prefer="<img src=x onerror=alert(1)>"}}
''')
        result = self.audit()
        path = self.root / "report.html"
        HtmlReporter().generate(result, str(path))
        html = path.read_text(encoding="utf-8")
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)
        self.assertIn("Constraint:", html)
        encoded = json.loads(JsonReporter().generate(result))
        self.assertIn("prefer", encoded["components"][0]["repo_declarations"]["project"][0]["constraint"])

    def test_upstream_metadata_does_not_turn_constraints_into_pins(self):
        self.catalog('''[libraries]
rich={module="example:rich", version={strictly="1.5"}}
managed={module="example:managed"}
fixed="example:fixed:1.0"
''')
        engine = DepsEngine()
        upstream = {"library:example:" + name: UpstreamInfo("fixture", "9.0", "9.0")
                    for name in ("rich", "managed", "fixed")}
        with patch.object(engine.resolver, "resolve_all", return_value=upstream):
            result = engine.run_audit(str(self.root))
        statuses = {c.identifier: c.upstream_status for c in result.components}
        self.assertEqual(statuses["example:rich"], "Constraints Not Evaluated")
        self.assertEqual(statuses["example:managed"], "Version Managed Externally")
        self.assertEqual([a.component_identifier for a in engine.plan_updates(result, mode="upstream")], ["example:fixed"])

    def test_mixed_aliases_retain_each_declaration(self):
        self.catalog('''[libraries]
fixed="example:lib:1.0"
rich={module="example:lib", version={prefer="2.0"}}
managed={module="example:lib"}
''')
        component = self.audit().components[0]
        self.assertEqual(component.latest_in_repos, "1.0")
        self.assertEqual(component.repo_statuses["project"], "constraint")
        self.assertEqual({d["kind"] for d in component.repo_declarations["project"]}, {"literal", "constraint", "managed"})

    def test_rich_alias_blocks_automatic_changes_to_the_same_coordinate_in_that_repo(self):
        self.catalog('''[libraries]
fixed="example:lib:1.0"
strict={module="example:lib",version={strictly="[1,2)"}}
''')
        self.catalog('[libraries]\nlib="example:lib:3.0"\n', self.root / "other")
        result = self.audit()
        self.assertEqual(DepsEngine().plan_updates(result), [])

    def test_rich_plugin_reference_is_preserved(self):
        self.catalog('''[versions]
v={strictly="8.1", reject=["8.2"]}
[plugins]
p={id="com.android.library",version.ref="v"}
''')
        component = self.audit().components[0]
        self.assertEqual(component.repo_statuses["project"], "constraint")
        self.assertEqual(component.repo_declarations["project"][0]["constraint"]["reject"], ["8.2"])

    def test_cli_json_with_update_keeps_rich_and_versionless_entries_unchanged(self):
        path = self.catalog('''[libraries]
rich={module="example:rich",version={prefer="1.0"}}
managed={module="example:managed"}
''')
        original = path.read_bytes()
        status, output, errors = self.command("--json", "--update", "--dry-run")
        self.assertEqual(status, 0, errors)
        encoded = json.loads(output)
        self.assertEqual(len(encoded["components"]), 2)
        self.assertTrue(encoded["profiles"]["project"]["declaration_notes"])
        self.assertEqual(path.read_bytes(), original)

    def test_constraint_only_repository_is_not_an_alignment_target(self):
        self.catalog('[libraries]\nlib={module="example:lib", version={strictly="99.0"}}\n')
        self.catalog('[libraries]\nlib="example:lib:1.0"\n', self.root / "fixed")
        result = self.audit()
        self.assertEqual(result.components[0].latest_in_repos, "1.0")
        self.assertEqual(DepsEngine().plan_updates(result), [])

    def test_unresolved_comparisons_do_not_claim_current_versions(self):
        self.catalog('[libraries]\nlib={module="example:lib",version={strictly="1.0"}}\n')
        engine = DepsEngine()
        upstream = {"library:example:lib": UpstreamInfo("fixture", "9.0", "9.0")}
        with patch.object(engine.resolver, "resolve_all", return_value=upstream):
            result = engine.run_audit(str(self.root))
        output = TerminalReporter(False).generate(result)
        self.assertNotIn("No newer upstream releases", output)
        self.assertIn("review unresolved declarations", output)
        self.assertEqual(result.up_to_date_count, 0)

    def test_versionless_alias_prevents_fully_current_claim(self):
        self.catalog('[libraries]\nfixed="example:lib:1.0"\nmanaged={module="example:lib"}\n')
        engine = DepsEngine()
        with patch.object(engine.resolver, "resolve_all", return_value={"library:example:lib": UpstreamInfo("fixture", "1.0", "1.0")}):
            result = engine.run_audit(str(self.root))
        self.assertEqual(result.up_to_date_count, 0)

    def test_manual_dynamic_or_rich_actions_are_refused(self):
        for version in ('"1.+"', '{strictly="1.0"}'):
            path = self.catalog('[libraries]\nlib={module="example:lib", version=' + version + '}\n')
            original = path.read_bytes()
            action = UpdateAction("project", str(path), "example:lib", "lib", "1.+" if version.startswith('"') else "1.0", "2.0", "upstream", component_type="library")
            updater = CatalogUpdater()
            self.assertFalse(updater.apply_action(action))
            self.assertEqual(path.read_bytes(), original)

    def test_missing_plugin_version_is_not_bom_managed(self):
        self.catalog('[plugins]\np={id="example.plugin"}\n')
        result = self.audit()
        self.assertEqual(result.components[0].repo_statuses["project"], "unsupported")
        self.assertEqual(DepsEngine().plan_updates(result), [])

    def test_agp_library_plugin_and_multiple_agp_aliases(self):
        self.catalog('''[plugins]
unusual={id="com.android.library",version="8.10"}
app={id="com.android.application",version="8.2"}
''')
        profile, _ = self.scanner.scan_project("library", str(self.project))
        self.assertEqual(profile.plugin_versions["agp"], "8.10")

    def test_similar_plugin_id_is_not_agp(self):
        self.catalog('[plugins]\nandroid-application={id="example.android.application",version="8.1"}\n')
        self.assertNotIn("agp", self.scanner.scan_project("other", str(self.project))[0].plugin_versions)

    def test_rich_agp_and_bom_do_not_break_profile_highlights(self):
        self.catalog('''[versions]
compose-bom={prefer="2026.01.00"}
[plugins]
agp={id="com.android.library",version={strictly="[8,9)"}}
[libraries]
bom={module="androidx.compose:compose-bom", version.ref="compose-bom"}
''')
        result = self.audit()
        self.assertEqual(result.profiles["project"].plugin_versions["agp"], "N/A")
        self.assertEqual(result.profiles["project"].plugin_versions["compose-bom"], "N/A")
        TerminalReporter(False).generate(result)

    def test_sdk_numeric_assignment_call_space_and_set_forms(self):
        forms = ("compileSdk = 35", "compileSdkVersion 35", "compileSdkVersion(35)",
                 "compileSdk.set(35)", "compileSdk . set ( 35 )", "compileSdkVersion = 35",
                 'compileSdkVersion "android-35"', "compileSdk = 3_5")
        for form in forms:
            with self.subTest(form=form):
                values, notes = sdk_literals("android { " + form + "; minSdkVersion 24; targetSdkVersion(35) }")
                self.assertEqual(values, {"compileSdk": {"35"}, "minSdk": {"24"}, "targetSdk": {"35"}})
                self.assertEqual(notes, [])

    def test_sdk_comments_nested_comments_and_string_examples_are_ignored(self):
        text = '''// android { compileSdk = 99 }
android {
 /* compileSdk = 98; /* minSdk = 97 */ targetSdk = 96 */
 println("compileSdk = 95 // not code")
 println('minSdk = 94')
 val example = """targetSdk = 93"""
 compileSdk = 35 // compileSdk = 92
 minSdk = 24
 targetSdk.set(35)
}
'''
        values, notes = sdk_literals(text)
        self.assertEqual(values, {"compileSdk": {"35"}, "minSdk": {"24"}, "targetSdk": {"35"}})
        self.assertEqual(notes, [])

    def test_sdk_expressions_and_partial_numeric_matches_remain_unknown(self):
        for expression in ("30 + 5", "35.toInt()", "35foo", "35.0", "Versions.sdk", 'providers.gradleProperty("sdk").get().toInt()'):
            with self.subTest(expression=expression):
                values, notes = sdk_literals("android { compileSdk = " + expression + " }")
                self.assertEqual(values["compileSdk"], set())
                self.assertEqual(notes, [(1, "compileSdk")])

    def test_sdk_reads_and_local_variables_are_not_settings(self):
        values, notes = sdk_literals('val compileSdk = 99\nandroid { val minSdk = 99; println(compileSdk); minSdk.get() }')
        self.assertEqual(values, {"compileSdk": set(), "targetSdk": set(), "minSdk": set()})
        self.assertEqual(notes, [])

    def test_sdk_scans_only_gradle_scripts_and_prunes_generated_folders(self):
        self.write("build.gradle", "android { compileSdkVersion 34 }")
        self.write("module/build.gradle.kts", "android { compileSdk.set(35) }")
        self.write("src/main/Example.kt", "android { compileSdk = 99 }")
        for folder in ("build", "node_modules", ".gradle", ".cxx", "venv"):
            self.write(folder + "/generated.gradle.kts", "android { compileSdk = 98 }")
        values = self.scanner.parse_sdk_and_build(str(self.project))
        self.assertEqual(values["compileSdk"], ["34", "35"])

    def test_sdk_unresolved_notes_appear_in_all_reports(self):
        self.catalog('[libraries]\nlib="example:lib:1.0"\n')
        self.write("build.gradle.kts", "android {\n compileSdk = Versions.sdk\n minSdk = 24\n}\n")
        result = self.audit()
        profile = result.profiles["project"]
        self.assertEqual(profile.sdk_info["compileSdk"], [])
        self.assertIn("build.gradle.kts:2: compileSdk expression not evaluated", profile.metadata["declaration_notes"])
        self.assertIn("Unknown", TerminalReporter(False).generate(result))
        self.assertIn("expression not evaluated", TerminalReporter(False).generate(result))
        path = self.root / "notes.html"
        HtmlReporter().generate(result, str(path))
        self.assertIn("expression not evaluated", path.read_text(encoding="utf-8"))
        self.assertIn("expression not evaluated", JsonReporter().generate(result))

    def test_unreadable_build_script_is_an_explicit_error(self):
        self.write("build.gradle.kts", "android { compileSdk = 35 }")
        with patch("gtrmrs.deps.scanners.android.open", side_effect=PermissionError("locked build script")):
            with self.assertRaisesRegex(ValueError, "locked build script"):
                self.scanner.parse_sdk_and_build(str(self.project))

    def test_python_floor_has_a_clear_runtime_error(self):
        source = Path(__file__).resolve().parents[1].joinpath("gtrmrs/__init__.py").read_text(encoding="utf-8")
        with patch.object(sys, "version_info", (3, 10, 0)):
            with self.assertRaisesRegex(RuntimeError, "requires Python 3.11"):
                exec(compile(source, "gtrmrs/__init__.py", "exec"), {})

    def test_audit_works_without_site_packages(self):
        self.catalog('[libraries]\nlib="example:lib:1.0"\n')
        script = "from gtrmrs.deps.engine import DepsEngine; import sys; print(DepsEngine().run_audit(sys.argv[1], no_upstream=True).total_components)"
        process = subprocess.run([sys.executable, "-S", "-c", script, str(self.root)],
                                 cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stdout.strip(), "1")


if __name__ == "__main__":
    unittest.main()
