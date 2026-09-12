"""Version precedence and wrapper settings using local, offline fixtures."""

import argparse
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from gtrmrs.core.colors import Colors
from gtrmrs.deps import cli
from gtrmrs.deps.engine import DepsEngine
from gtrmrs.deps.models import AuditResult, ProjectProfile, UpdateAction, UpstreamInfo
from gtrmrs.deps.report.terminal import TerminalReporter
from gtrmrs.deps.scanners.android import AndroidScanner
from gtrmrs.deps.scanners.base import is_preview_version, parse_semver
from gtrmrs.deps.scanners.wrapper import distribution, wrapper_properties
from gtrmrs.deps.updater.toml_updater import CatalogUpdater
from gtrmrs.deps.upstream.resolver import UpstreamResolver


class TestVersionPrecedence(unittest.TestCase):
    def test_build_metadata_does_not_change_precedence_or_preview_class(self):
        for value in ("1.2.3", "1.2.3-rc.2", "1.2.3-alpha10", "2026.01.02"):
            for metadata in ("build.5", "dev.999", "snapshot.m4", "rc.beta"):
                with self.subTest(value=value, metadata=metadata):
                    self.assertEqual(parse_semver(value), parse_semver(value + "+" + metadata))
                    self.assertEqual(is_preview_version(value), is_preview_version(value + "+" + metadata))

    def test_dotted_numeric_prerelease_fields(self):
        ordered = ("1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta",
                   "1.0.0-beta", "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0")
        self.assertEqual(sorted(reversed(ordered), key=parse_semver), list(ordered))
        self.assertGreater(parse_semver("1.0.0-alpha.2.10"), parse_semver("1.0.0-alpha.2.2"))

    def test_common_compact_qualifier_counters_are_numeric(self):
        for tag in ("alpha", "beta", "M", "milestone-", "rc-", "cr", "preview", "dev", "ea", "EAP"):
            with self.subTest(tag=tag):
                self.assertGreater(parse_semver("2.0-" + tag + "10"), parse_semver("2.0-" + tag + "2"))
                self.assertTrue(is_preview_version("2.0-" + tag + "10"))

    def test_qualifier_stage_order_and_aliases(self):
        ordered = ["2.0-dev1", "2.0-ea1", "2.0-alpha1", "2.0-beta1",
                   "2.0-M1", "2.0-preview1", "2.0-rc1", "2.0-SNAPSHOT", "2.0"]
        self.assertEqual(sorted(reversed(ordered), key=parse_semver), ordered)
        for left, right in (("a2", "alpha-2"), ("b2", "beta.2"), ("M4", "milestone-4"), ("cr1", "RC.1")):
            self.assertEqual(parse_semver("1.0-" + left), parse_semver("1.0-" + right))

    def test_every_milestone_counter_is_preview(self):
        for tag in ("M", "m", "milestone-", "Milestone."):
            for number in (1, 4, 10, 99):
                self.assertTrue(is_preview_version("2.0-" + tag + str(number)))

    def test_final_aliases_and_ordinary_suffixes_do_not_match_substrings(self):
        for suffix in ("Final", "GA", "RELEASE"):
            self.assertFalse(is_preview_version("1.0.0." + suffix))
            self.assertEqual(parse_semver("1.0.0." + suffix), parse_semver("1.0.0"))
        for suffix in ("jre", "android", "team1", "cream", "developer", "source", "grade-a", "1"):
            self.assertFalse(is_preview_version("1.0.0-" + suffix), suffix)

    def test_extra_core_components_are_separate_from_qualifier_ranks(self):
        self.assertEqual(parse_semver("1.2.3.0"), parse_semver("1.2.3"))
        self.assertGreater(parse_semver("1.2.3.4-alpha1"), parse_semver("1.2.3"))
        self.assertGreater(parse_semver("1.2.3.4"), parse_semver("1.2.3.4-rc10"))
        self.assertGreater(parse_semver("2026.10.01"), parse_semver("2026.9.30"))

    def test_unavailable_and_non_numeric_values_have_comparable_keys(self):
        values = [None, "", "N/A", "None", "invalid", "https://example.invalid/8.0", "1.0"]
        self.assertEqual(max(values, key=parse_semver), "1.0")
        self.assertEqual(parse_semver(" v1.2.3 "), parse_semver("V1.2.3"))

    def test_maven_stable_selection_excludes_all_known_previews(self):
        releases = ["1.0", "2.0-M4", "2.0-M10", "2.0-rc1", "2.0-dev1", "2.0-EAP2"]
        info = UpstreamResolver()._extract_versions({"release": "2.0-M10", "versions": releases}, "fixture")
        self.assertEqual(info.latest_stable, "1.0")
        self.assertEqual(info.latest_overall, "2.0-rc1")

    def test_invalid_registry_values_do_not_become_stable_recommendations(self):
        info = UpstreamResolver()._extract_versions({"versions": [None, 42, "bad", "1.0", "2.0-M4"]}, "fixture")
        self.assertEqual(info.latest_stable, "1.0")
        missing = UpstreamResolver()._extract_versions({"versions": ["bad", None]}, "fixture")
        self.assertEqual(missing.check_status, "unavailable")

    def test_gradle_feed_order_does_not_choose_the_latest(self):
        payload = [{"version": "8.9", "current": True},
                   {"version": "9.0-M4", "current": True},
                   {"version": "9.0-rc-10", "releaseCandidate": True},
                   {"version": "99.0", "broken": True}]
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        with patch("urllib.request.urlopen", return_value=response):
            info = UpstreamResolver().resolve_gradle_wrapper()
        self.assertEqual(info.latest_stable, "8.9")
        self.assertEqual(info.latest_overall, "9.0-rc-10")

    def test_gradle_without_a_verified_current_stable_does_not_guess(self):
        payload = [{"version": "9.0-M4", "current": True},
                   {"version": "8.9", "nightly": True, "current": True},
                   {"version": "8.8", "snapshot": True, "current": True}]
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        with patch("urllib.request.urlopen", return_value=response):
            self.assertIsNone(UpstreamResolver().resolve_gradle_wrapper().latest_stable)

    def test_equivalent_metadata_profiles_receive_equal_highlights(self):
        profiles = {name: ProjectProfile(name, name, "android", build_tool_version=version,
                                        plugin_versions={"agp": version, "kotlin-android": version, "compose-bom": version})
                    for name, version in (("one", "8.0"), ("two", "8.0+ci.7"))}
        report = TerminalReporter(True).generate(AuditResult(".", profiles, [], [], []))
        for version in ("8.0", "8.0+ci.7"):
            self.assertIn(Colors.GREEN + f"{version:<10}" + Colors.RESET, report)
            self.assertIn(Colors.GREEN + f"{version:<14}" + Colors.RESET, report)


class TestWrapperSelection(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        self.path = self.project / "gradle/wrapper/gradle-wrapper.properties"
        self.path.parent.mkdir(parents=True)
        catalog = self.project / "gradle/libs.versions.toml"
        catalog.write_text('[libraries]\nlib="example:lib:1.0"\n', encoding="utf-8")

    def write(self, content):
        self.path.write_bytes(content.encode("utf-8"))
        return self.path

    def version(self):
        return AndroidScanner().parse_gradle_wrapper(str(self.project))

    def action(self, old="8.7-rc-1", new="8.7"):
        return UpdateAction("project", str(self.path), "Gradle Wrapper Distribution",
                            "distributionUrl", old, new, "upstream", component_type="build_tool")

    def test_rc_milestone_snapshot_and_timestamp_versions_are_extracted(self):
        for version in ("8.7", "8.7-rc-1", "8.7-milestone-4", "8.7-SNAPSHOT", "8.7-20240101000000+0000"):
            for kind in ("bin", "all"):
                self.write("distributionUrl=https\\://services.gradle.org/distributions/gradle-" + version + "-" + kind + ".zip\n")
                self.assertEqual(self.version(), version)

    def test_commented_and_differently_named_settings_do_not_override_active_url(self):
        self.write("# distributionUrl=https\\://example.invalid/gradle-7.0-bin.zip\n"
                   " ! distributionUrl=https\\://example.invalid/gradle-7.1-bin.zip\n"
                   "otherDistributionUrl=https\\://example.invalid/gradle-7.2-bin.zip\n"
                   "note=distributionUrl=https\\://example.invalid/gradle-7.3-bin.zip\n"
                   "distributionUrl=https\\://example.invalid/gradle-8.7-rc-1-all.zip\n")
        self.assertEqual(self.version(), "8.7-rc-1")

    def test_last_active_setting_is_read_and_updated(self):
        source = ("distributionUrl=https\\://example.invalid/gradle-7.0-bin.zip\r\n"
                  "# distributionUrl=https\\://example.invalid/gradle-9.0-all.zip\r\n"
                  "distributionUrl=https\\://example.invalid/gradle-8.7-rc-1-all.zip\r\n")
        self.write(source)
        self.assertEqual(self.version(), "8.7-rc-1")
        self.assertTrue(CatalogUpdater().apply_action(self.action()))
        self.assertEqual(self.path.read_bytes(), source.replace("8.7-rc-1", "8.7").encode())

    def test_property_delimiters_and_unicode_key_escapes(self):
        for prefix in ("distributionUrl: ", "distributionUrl ", "\fdistributionUrl = ", r"distribution\u0055rl="):
            source = prefix + "https\\://example.invalid/gradle-8.7-rc-1-bin.zip\n"
            self.write(source)
            self.assertEqual(self.version(), "8.7-rc-1")
            self.assertTrue(CatalogUpdater().apply_action(self.action()))
            self.assertEqual(self.path.read_bytes(), source.replace("8.7-rc-1", "8.7").encode())

    def test_unicode_escaped_version_digits_are_edited_by_decoded_position(self):
        source = r"distributionUrl=https\://example.invalid/gradle-\u0038.7-rc-1-all.zip" + "\n"
        self.write(source)
        self.assertEqual(self.version(), "8.7-rc-1")
        self.assertTrue(CatalogUpdater().apply_action(self.action()))
        self.assertIn(b"gradle-8.7-all.zip", self.path.read_bytes())

    def test_url_parameters_and_fragments_do_not_become_versions(self):
        self.write("distributionUrl=https\\://mirror.invalid/files/gradle-8.7-rc-1-all.zip?token\\=fixture#fragment\n")
        self.assertEqual(self.version(), "8.7-rc-1")
        self.assertTrue(CatalogUpdater().apply_action(self.action()))
        prop = wrapper_properties(self.path.read_text(encoding="utf-8"))["distributionUrl"]
        self.assertEqual(prop.value, "https://mirror.invalid/files/gradle-8.7-all.zip?token=fixture#fragment")

    def test_host_and_query_occurrences_are_not_edited_instead_of_archive(self):
        source = "distributionUrl=https\\://gradle-8.7-rc-1-bin.zip/gradle-8.7-rc-1-bin.zip?backup=/gradle-99.0-bin.zip\n"
        self.write(source)
        self.assertTrue(CatalogUpdater().apply_action(self.action()))
        self.assertEqual(self.path.read_bytes(), source.replace("/gradle-8.7-rc-1-bin.zip?", "/gradle-8.7-bin.zip?").encode())

    def test_unknown_archive_names_are_unknown_without_exposing_url(self):
        self.write("distributionUrl=https\\://user:secret@mirror.invalid/custom.zip?token=private\n")
        self.assertIsNone(self.version())
        result = DepsEngine().run_audit(str(self.root), no_upstream=True)
        report = TerminalReporter(False).generate(result)
        self.assertIn("filename not recognized", report)
        self.assertNotIn("secret", report)
        self.assertNotIn("private", report)

    def test_url_like_text_in_query_is_not_treated_as_the_archive(self):
        self.write("distributionUrl=https\\://example.invalid/custom.zip?fallback=/gradle-8.7-bin.zip\n")
        self.assertIsNone(self.version())

    def test_missing_active_url_or_wrapper_is_unknown(self):
        self.write("# distributionUrl=https\\://example.invalid/gradle-8.0-bin.zip\n")
        self.assertIsNone(self.version())
        self.path.unlink()
        self.assertIsNone(self.version())

    def test_continuations_are_read_but_automatic_edits_are_refused(self):
        source = "distributionUrl=https\\://example.invalid/\\\r\n  gradle-8.7-rc-1-bin.zip\r\n"
        self.write(source)
        self.assertEqual(self.version(), "8.7-rc-1")
        self.assertFalse(CatalogUpdater().apply_action(self.action()))
        self.assertEqual(self.path.read_bytes(), source.encode())

    def test_percent_encoded_archive_is_read_but_not_rewritten(self):
        source = "distributionUrl=https\\://example.invalid/gradle-%38.7-rc-1-bin.zip\n"
        self.write(source)
        self.assertEqual(self.version(), "8.7-rc-1")
        self.assertFalse(CatalogUpdater().apply_action(self.action()))
        self.assertEqual(self.path.read_bytes(), source.encode())

    def test_invalid_properties_or_encoding_are_explicit_read_errors(self):
        self.write(r"distributionUrl=https\://example.invalid/gradle-\uBAD-bin.zip" + "\n")
        with self.assertRaisesRegex(ValueError, "Invalid Unicode escape"):
            self.version()
        self.path.write_bytes(b"distributionUrl=\xff\n")
        with self.assertRaisesRegex(ValueError, "Could not read Gradle wrapper"):
            self.version()

    def test_checksum_comes_from_exact_updated_url_and_keeps_query(self):
        source = ("distributionUrl=https\\://mirror.invalid/files/gradle-8.7-rc-1-all.zip?token\\=fixture#fragment\r\n"
                  "distributionSha256Sum=" + "a" * 64 + "\r\n")
        self.write(source)
        response = MagicMock()
        response.__enter__.return_value.read.return_value = ("b" * 64).encode()
        with patch("urllib.request.urlopen", return_value=response) as fetch:
            self.assertTrue(CatalogUpdater().apply_action(self.action()))
        self.assertEqual(fetch.call_args.args[0], "https://mirror.invalid/files/gradle-8.7-all.zip.sha256?token=fixture")
        self.assertEqual(self.path.read_bytes(), source.replace("8.7-rc-1", "8.7").replace("a" * 64, "b" * 64).encode())

    def test_only_effective_pinned_checksum_changes(self):
        source = ("distributionUrl=https\\://services.gradle.org/distributions/gradle-8.7-rc-1-bin.zip\n"
                  "distributionSha256Sum=" + "a" * 64 + "\n"
                  "! distributionSha256Sum=comment\n"
                  "distributionSha256Sum: " + "c" * 64 + "\n")
        self.write(source)
        response = MagicMock()
        response.__enter__.return_value.read.return_value = ("b" * 64).encode()
        with patch("urllib.request.urlopen", return_value=response):
            self.assertTrue(CatalogUpdater().apply_action(self.action()))
        self.assertEqual(self.path.read_bytes(), source.replace("8.7-rc-1", "8.7").replace("c" * 64, "b" * 64).encode())

    def test_checksum_failure_and_invalid_body_preserve_original(self):
        source = ("distributionUrl=https\\://services.gradle.org/distributions/gradle-8.7-rc-1-bin.zip\n"
                  "distributionSha256Sum=" + "a" * 64 + "\n")
        self.write(source)
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            self.assertFalse(CatalogUpdater().apply_action(self.action()))
        self.assertEqual(self.path.read_bytes(), source.encode())
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"invalid checksum"
        with patch("urllib.request.urlopen", return_value=response):
            self.assertFalse(CatalogUpdater().apply_action(self.action()))
        self.assertEqual(self.path.read_bytes(), source.encode())
        self.assertEqual(list(self.path.parent.glob(".gtrmrs-update-*")), [])

    def test_empty_pinned_checksum_is_filled_without_dropping_verification(self):
        self.write("distributionUrl=https\\://services.gradle.org/distributions/gradle-8.7-rc-1-bin.zip\n"
                   "distributionSha256Sum=\n")
        response = MagicMock()
        response.__enter__.return_value.read.return_value = ("b" * 64).encode()
        with patch("urllib.request.urlopen", return_value=response):
            self.assertTrue(CatalogUpdater().apply_action(self.action()))
        self.assertEqual(wrapper_properties(self.path.read_text(encoding="utf-8"))["distributionSha256Sum"].value, "b" * 64)

    def test_continued_pinned_checksum_is_refused_before_fetching(self):
        source = ("distributionUrl=https\\://services.gradle.org/distributions/gradle-8.7-rc-1-bin.zip\n"
                  "distributionSha256Sum=" + "a" * 32 + "\\\n" + "a" * 32 + "\n")
        self.write(source)
        with patch("urllib.request.urlopen") as fetch:
            self.assertFalse(CatalogUpdater().apply_action(self.action()))
        fetch.assert_not_called()
        self.assertEqual(self.path.read_bytes(), source.encode())

    def test_unpinned_wrapper_does_not_fetch_checksums(self):
        self.write("distributionUrl=https\\://services.gradle.org/distributions/gradle-8.7-rc-1-bin.zip\n")
        with patch("urllib.request.urlopen") as fetch:
            self.assertTrue(CatalogUpdater().apply_action(self.action()))
        fetch.assert_not_called()

    def test_file_distribution_fetches_its_adjacent_checksum(self):
        local = self.root / "local releases #safe"
        local.mkdir()
        archive = local / "gradle-8.7-rc-1-bin.zip"
        checksum = local / "gradle-8.7-bin.zip.sha256"
        checksum.write_text("b" * 64, encoding="ascii")
        self.write("distributionSha256Sum=" + "a" * 64 + "\n"
                   "distributionUrl=" + archive.as_uri() + "\n")
        self.assertTrue(CatalogUpdater().apply_action(self.action()))
        prepared = wrapper_properties(self.path.read_text(encoding="utf-8"))
        self.assertEqual(prepared["distributionSha256Sum"].value, "b" * 64)
        self.assertEqual(distribution(prepared["distributionUrl"].value).version, "8.7")

    def test_relative_distribution_without_checksum_is_updated_locally(self):
        source = "distributionUrl=../../releases/gradle-8.7-rc-1-bin.zip\n"
        self.write(source)
        self.assertEqual(self.version(), "8.7-rc-1")
        with patch("urllib.request.urlopen") as fetch:
            self.assertTrue(CatalogUpdater().apply_action(self.action()))
        fetch.assert_not_called()
        self.assertEqual(self.path.read_bytes(), source.replace("8.7-rc-1", "8.7").encode())

    def test_stale_rc_action_preserves_wrapper(self):
        source = "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.7-rc-2-bin.zip\n"
        self.write(source)
        self.assertFalse(CatalogUpdater().apply_action(self.action()))
        self.assertEqual(self.path.read_bytes(), source.encode())

    def test_end_to_end_preview_wrapper_can_update_to_stable(self):
        self.write("distributionUrl=https\\://services.gradle.org/distributions/gradle-8.7-rc-1-bin.zip\n")
        engine = DepsEngine()
        upstream = {"build_tool:Gradle Wrapper Distribution": UpstreamInfo("fixture", "8.7", "8.8-rc-1")}
        with patch.object(engine.resolver, "resolve_all", return_value=upstream):
            result = engine.run_audit(str(self.root))
        actions = engine.plan_updates(result, mode="upstream")
        self.assertEqual([(a.old_version, a.new_version) for a in actions], [("8.7-rc-1", "8.7")])
        self.assertTrue(engine.apply_actions(actions)[0][1])
        self.assertEqual(self.version(), "8.7")

    def test_build_metadata_differences_do_not_plan_catalog_updates(self):
        catalog = self.project / "gradle/libs.versions.toml"
        catalog.write_text('[libraries]\nlib="example:lib:1.2.3+build.5"\n', encoding="utf-8")
        engine = DepsEngine()
        with patch.object(engine.resolver, "resolve_all", return_value={"library:example:lib": UpstreamInfo("fixture", "1.2.3", "1.2.3")}):
            result = engine.run_audit(str(self.root))
        self.assertEqual(result.repo_discrepancies_count, 0)
        self.assertEqual(engine.plan_updates(result, mode="upstream"), [])

    def test_cli_ignores_commented_version_and_applies_only_stable_target(self):
        source = "# distributionUrl=https\\://example.invalid/gradle-7.0-bin.zip\n" \
                 "distributionUrl=https\\://example.invalid/gradle-8.7-rc-1-bin.zip\n"
        self.write(source)
        parser = argparse.ArgumentParser()
        cli._configure_parser(parser)
        arguments = parser.parse_args([str(self.root), "--json", "--update"])
        output, errors = io.StringIO(), io.StringIO()
        upstream = {"build_tool:Gradle Wrapper Distribution": UpstreamInfo("fixture", "8.7", "8.8-rc-1")}
        with patch.object(UpstreamResolver, "resolve_all", return_value=upstream):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                cli.run(arguments)
        self.assertEqual(json.loads(output.getvalue())["profiles"]["project"]["build_tool_version"], "8.7-rc-1")
        self.assertEqual(self.path.read_bytes(), source.replace("8.7-rc-1", "8.7").encode())


if __name__ == "__main__":
    unittest.main()
