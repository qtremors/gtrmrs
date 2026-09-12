"""Offline regression probes. All mutations use temporary fixtures, never real projects.

Run: python -B tests/audit_regressions.py
Exit 1 means a probe found a behavior gap; exit 2 means a probe could not run.
These checks supplement the unittest suite without retaining generated reports.
"""

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gtrmrs.core.git_utils import find_git_root, git_check_ignore
from gtrmrs.deps.engine import DepsEngine
from gtrmrs.deps.models import UpdateAction, UpstreamInfo
from gtrmrs.deps.report.html import HtmlReporter
from gtrmrs.deps.report.terminal import TerminalReporter
from gtrmrs.deps.scanners.android import AndroidScanner
from gtrmrs.deps.scanners.base import is_preview_version, parse_semver
from gtrmrs.deps.updater.toml_updater import CatalogUpdater
from gtrmrs.deps.upstream.resolver import UpstreamResolver
from gtrmrs.gitmig.engine import GitMigEngine
from gtrmrs.locr.engine import LocrEngine
from gtrmrs.rtree.engine import RepoTreeVisualizer
from gtrmrs.storage.engine import StorageEngine


PROBES = []


def probe(identifier):
    def decorate(function):
        PROBES.append((identifier, function))
        return function
    return decorate


def write(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def git(root, *args):
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(root), *args],
        check=True, capture_output=True,
    ).stdout


def init(root):
    root.mkdir(parents=True, exist_ok=True)
    git(root, "-c", "init.templateDir=", "init", "-q")
    git(root, "config", "core.excludesFile", str(write(root / ".git", "audit-excludes", "")))
    return root


def catalog(root, text):
    return write(root, "gradle/libs.versions.toml", text)


def one_library(version="1.0"):
    return '[libraries]\nlib = "example:lib:' + version + '"\n'


def migrated(root, **options):
    engine = GitMigEngine(str(root), str(root.parent / "destination"), quiet=True, **options)
    return {p.replace("\\", "/") for p, _ in engine._scan_repo(root.name, str(root))[0]}


def invoke(module, arguments):
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


@probe("C01")
def global_source_exclusions(root):
    for name in ("schemas", "bin", "build"):
        write(root, name + "/source.py", "print('source')\n")
    files = [item["path"] for item in LocrEngine(str(root)).scan()[1]]
    return sorted(files), ["bin/source.py", "build/source.py", "schemas/source.py"]


@probe("C02")
def git_failure_opens_filter(root):
    with patch("gtrmrs.core.git_utils.subprocess.run", side_effect=FileNotFoundError("git missing")):
        try:
            git_check_ignore(str(root), ["private.txt"])
            signaled = False
        except (OSError, RuntimeError):
            signaled = True
    return signaled, True


@probe("C03")
def linked_worktree_detection(root):
    repo = init(root / "repo")
    write(repo, "source.py", "pass\n")
    git(repo, "add", "source.py")
    git(repo, "-c", "user.name=Audit", "-c", "user.email=audit@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
    linked = root / "linked"
    git(repo, "worktree", "add", "--detach", "-q", str(linked))
    return find_git_root(str(linked)) is not None, True


@probe("C04")
def plain_directory_ignore_descendants(root):
    write(root, ".gitignore", "private/\n")
    write(root, "private/secret.py", "secret = 1\n")
    return "private/secret.py" in RepoTreeVisualizer(str(root), use_color=False).visible_paths, False


@probe("C05")
def plain_directory_anchored_ignore(root):
    write(root, ".gitignore", "/private/\n")
    write(root, "private/secret.py", "secret = 1\n")
    return "private/secret.py" in [f["path"] for f in LocrEngine(str(root)).scan()[1]], False


@probe("L01")
def raw_tests_flag(root):
    write(root, "main.py", "pass\n")
    write(root, "test_main.py", "pass\n")
    return sorted(f["path"] for f in LocrEngine(str(root), raw_mode=True, tests_only=True).scan()[1]), ["test_main.py"]


@probe("L02")
def nested_ignore_override(root):
    init(root)
    write(root, ".gitignore", "*.py\n")
    write(root, "src/.gitignore", "!keep.py\n")
    write(root, "src/keep.py", "pass\n")
    return [f["path"] for f in LocrEngine(str(root)).scan()[1]], ["src/keep.py"]


@probe("L03")
def tracked_file_override(root):
    init(root)
    write(root, ".gitignore", "*.py\n")
    write(root, "keep.py", "pass\n")
    git(root, "add", "-f", "keep.py")
    return [f["path"] for f in LocrEngine(str(root)).scan()[1]], ["keep.py"]


@probe("L04")
def inline_comment_then_code(root):
    file = write(root, "main.c", "/* explanation */ int main(void) { return 0; }\n")
    from gtrmrs.locr.languages import LANGUAGES
    return LocrEngine(str(root))._analyze_file(str(file), LANGUAGES[".c"]), (0, 0, 1)


@probe("L05")
def multiline_string(root):
    file = write(root, "main.py", 'value = """\n# string contents\n"""\nprint(value)\n')
    from gtrmrs.locr.languages import LANGUAGES
    return LocrEngine(str(root))._analyze_file(str(file), LANGUAGES[".py"]), (0, 0, 4)


@probe("L06")
def advertised_language_extensions(root):
    names = ["stub.pyi", "style.sass", "main.swift", "script.ps1", "script.bat",
             "script.cmd", "script.bash", "script.zsh", "Dockerfile"]
    for name in names:
        write(root, name, "example\n")
    return sorted(f["path"] for f in LocrEngine(str(root), raw_mode=True).scan()[1]), sorted(names)


@probe("L07")
def unreadable_source_is_reported(root):
    write(root, "main.py", "pass\n")
    with patch("builtins.open", side_effect=PermissionError("fixture read failure")):
        result = LocrEngine(str(root)).scan()[0]
    return result["Python"]["files"], 0


@probe("M01")
def extension_filter_respects_ignore(root):
    init(root)
    write(root, ".gitignore", "private.json\n")
    write(root, "private.json", '{"secret": true}\n')
    return "private.json" in migrated(root, ext_filter=["json"]), False


@probe("M02")
def extension_filter_respects_exclude(root):
    write(root, "private.json", "{}\n")
    return "private.json" in migrated(root, ext_filter=["json"], extra_excludes=["private.json"]), False


@probe("M03")
def existing_zip_is_preserved(root):
    repo, destination = init(root / "repo"), root / "destination"
    destination.mkdir()
    write(repo, "new.txt", "new\n")
    archive = destination / "repo.zip"
    with zipfile.ZipFile(str(archive), "w") as handle:
        handle.writestr("old.txt", "previous backup")
    engine = GitMigEngine(str(repo), str(destination), use_zip=True, skip_existing=True, quiet=True)
    engine.run()
    with zipfile.ZipFile(str(archive)) as handle:
        return "old.txt" in handle.namelist(), True


@probe("M04")
def destination_link_escape(root):
    repo, destination = init(root / "repo"), root / "destination"
    source = write(repo, "source.py", "new\n")
    external = write(root, "outside/source.py", "original\n")
    (destination / "repo").mkdir(parents=True)
    link = destination / "repo/source.py"
    try:
        os.symlink(str(external), str(link))
    except OSError as exc:
        raise unittest_skip("File symlinks unavailable: " + str(exc))
    try:
        GitMigEngine(str(repo), str(destination), quiet=True)._copy_repo("repo", str(repo), [(source.name, source.stat().st_size)])
        return external.read_text(encoding="utf-8"), "original\n"
    finally:
        link.unlink()


class unittest_skip(Exception):
    pass


@probe("M05")
def same_source_destination_reports_failure(root):
    from gtrmrs.gitmig import cli
    repo = init(root / "repo")
    write(repo, "source.py", "pass\n")
    status, _, _ = invoke(cli, [repo, root, "--quiet"])
    return status != 0, True


@probe("M06")
def single_repo_filter(root):
    init(root)
    engine = GitMigEngine(str(root), str(root.parent / "destination"), only_repos=["unmatched"], quiet=True)
    return engine._find_repos(), []


@probe("M07")
def credential_exclusion_claim(root):
    write(root, "release.jks", "private key")
    write(root, "release.keystore", "private key")
    return sorted(p for p in migrated(root) if p.endswith((".jks", ".keystore"))), []


@probe("M08")
def skipped_existing_counts_as_copied(root):
    repo, destination = init(root / "repo"), root / "destination"
    write(repo, "file.txt", "new")
    write(destination, "repo/file.txt", "old")
    engine = GitMigEngine(str(repo), str(destination), skip_existing=True, quiet=True)
    engine.run()
    return engine.total_files_copied, 0


@probe("M09")
def excluded_subtree_is_walked(root):
    write(root, "node_modules/package/index.js", "dependency")
    original = os.walk
    visits = []
    def spy(path, *args, **kwargs):
        visits.append(Path(path).name)
        return original(path, *args, **kwargs)
    with patch("gtrmrs.gitmig.engine.os.walk", side_effect=spy):
        migrated(root)
    return "node_modules" in visits, False


@probe("M10")
def non_git_source_is_not_migrated(root):
    write(root, "source.py", "pass\n")
    engine = GitMigEngine(str(root), str(root.parent / "destination"), quiet=True)
    return engine._find_repos(), []


@probe("D01")
def filtered_alignment_loses_reference(root):
    from gtrmrs.deps import cli
    catalog(root / "old", one_library("1.0"))
    catalog(root / "new", one_library("2.0"))
    status, _, _ = invoke(cli, [root, "--no-upstream", "--repo", "old", "--align"])
    version = AndroidScanner().parse_toml(str(root / "old"))["libraries"]["lib"]["version"]
    return [status, version], [0, "2.0"]


@probe("D02")
def partial_update_repo_filter(root):
    catalog(root / "my-old", one_library("1.0"))
    catalog(root / "new", one_library("2.0"))
    engine = DepsEngine()
    result = engine.run_audit(str(root), no_upstream=True)
    return len(engine.plan_updates(result, target_repo="my-o")), 1


@probe("D03")
def shared_ref_conflicting_targets(root):
    catalog(root / "old", '[versions]\nshared = "1.0"\n[libraries]\na = {module="example:a", version.ref="shared"}\nb = {module="example:b", version.ref="shared"}\n')
    catalog(root / "new", '[libraries]\na = "example:a:2.0"\nb = "example:b:3.0"\n')
    engine = DepsEngine()
    result = engine.run_audit(str(root), no_upstream=True)
    try:
        actions = engine.plan_updates(result)
    except ValueError as exc:
        if "Conflicting updates" not in str(exc):
            raise
        versions = AndroidScanner().parse_toml(str(root / "old"))["versions"]
        return versions["shared"] == "1.0", True
    engine.apply_actions(actions)
    return False, True


@probe("D04")
def inline_plugin_action(root):
    path = catalog(root, '[plugins]\nandroid = {id="com.android.application", version="8.0"}\n')
    action = UpdateAction("repo", str(path), "com.android.application", "android", "8.0", "8.1", "align")
    return CatalogUpdater().apply_action(action), True


@probe("D05")
def commented_section_header(root):
    path = catalog(root, '[versions] # shared versions\nlib = "1.0"\n')
    return CatalogUpdater().update_version_ref(str(path), "lib", "2.0")[0], True


@probe("D06")
def stale_action_overwrites_edit(root):
    path = catalog(root, '[versions]\nlib = "3.0"\n')
    action = UpdateAction("repo", str(path), "example:lib", "lib", "1.0", "2.0", "align", True, "lib")
    CatalogUpdater().apply_action(action)
    return AndroidScanner().parse_toml(str(root))["versions"]["lib"], "3.0"


@probe("D07")
def fallback_parser_parity(root):
    catalog(root, '[versions]\nv = "1.0"\n[libraries]\nlib = {group="example", name="lib", version.ref="v"}\n[plugins]\nandroid = {id="com.android.application", version="8.0"}\n')
    scanner = AndroidScanner()
    result = scanner.parse_toml(str(root))
    # Python 3.11+ is now required; the incomplete older-Python fallback is retired.
    return [len(result["libraries"]), len(result["plugins"]), hasattr(scanner, "_parse_toml_basic")], [1, 1, False]


@probe("D08")
def rich_version_constraints(root):
    catalog(root, '[versions]\nv = {strictly="[1.0,2.0[", prefer="1.5"}\n[libraries]\nlib = {module="example:lib", version.ref="v"}\n')
    value = AndroidScanner().parse_toml(str(root))["libraries"]["lib"]["version"]
    return value.startswith("{"), False


@probe("D09")
def sdk_syntax(root):
    write(root, "build.gradle", "android { compileSdkVersion 34; defaultConfig { minSdkVersion 24; targetSdkVersion 34 } }\n")
    write(root, "module/build.gradle.kts", "android { compileSdk.set(35) }\n")
    info = AndroidScanner().parse_sdk_and_build(str(root))
    return info, {"compileSdk": ["34", "35"], "targetSdk": ["34"], "minSdk": ["24"]}


@probe("D10")
def commented_sdk_values(root):
    write(root, "build.gradle.kts", "// compileSdk = 99\nandroid { compileSdk = 35 }\n")
    return AndroidScanner().parse_sdk_and_build(str(root))["compileSdk"], ["35"]


@probe("D11")
def gradle_release_candidate(root):
    write(root, "gradle/wrapper/gradle-wrapper.properties", "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.7-rc-1-bin.zip\n")
    return AndroidScanner().parse_gradle_wrapper(str(root)), "8.7-rc-1"


@probe("D12")
def missing_bom_dependency(root):
    catalog(root, '[libraries]\nmanaged = {module="example:managed"}\n')
    result = DepsEngine().run_audit(str(root), no_upstream=True)
    return result.components[0].repo_statuses[root.name], "bom-managed"


@probe("D13")
def duplicate_coordinate_aliases(root):
    catalog(root / "old", '[libraries]\nfirst = "example:lib:1.0"\nsecond = "example:lib:1.5"\n')
    catalog(root / "new", one_library("2.0"))
    engine = DepsEngine()
    result = engine.run_audit(str(root), no_upstream=True)
    actions = engine.plan_updates(result)
    engine.apply_actions(actions)
    values = AndroidScanner().parse_toml(str(root / "old"))["libraries"]
    return [value["version"] for value in values.values()], ["2.0", "2.0"]


@probe("D14")
def semver_build_metadata(root):
    return parse_semver("1.2.3+build.5") == parse_semver("1.2.3"), True


@probe("D15")
def maven_milestone_as_stable(root):
    result = UpstreamResolver()._extract_versions({"versions": ["1.0", "2.0-M4"]}, "fixture")
    return result.latest_stable, "1.0"


@probe("D16")
def preview_misclassification(root):
    return is_preview_version("1.0.0.Final"), False


@probe("D17")
def no_upstream_terminal_claim(root):
    catalog(root, one_library())
    result = DepsEngine().run_audit(str(root), no_upstream=True)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        TerminalReporter(color_enabled=False).render(result)
    return "All components are aligned with upstream stable releases." in output.getvalue(), False


@probe("D18")
def json_update_stdout(root):
    from gtrmrs.deps import cli
    catalog(root, one_library())
    _, output, _ = invoke(cli, [root, "--no-upstream", "--json", "--align", "--dry-run"])
    try:
        json.loads(output)
        valid = True
    except ValueError:
        valid = False
    return valid, True


@probe("D19")
def malformed_catalog_is_silent(root):
    catalog(root, '[libraries]\nlib = { broken\n')
    try:
        result = DepsEngine().run_audit(str(root), no_upstream=True)
        detected = not result.profiles
    except (ValueError, RuntimeError):
        detected = True
    return detected, True


@probe("D20")
def agp_library_profile(root):
    catalog(root, '[plugins]\nandroid-library = {id="com.android.library", version="8.1"}\n')
    profile, _ = AndroidScanner().scan_project("library", str(root))
    return profile.plugin_versions.get("agp"), "8.1"


@probe("D21")
def failed_apply_exit_status(root):
    from gtrmrs.deps import cli
    catalog(root / "old", one_library("1.0"))
    catalog(root / "new", one_library("2.0"))
    with patch("gtrmrs.deps.updater.toml_updater.os.replace", side_effect=OSError("fixture replacement failure")):
        status, _, _ = invoke(cli, [root, "--align", "--no-upstream"])
    return status != 0, True


@probe("D22")
def text_output_file_ignored(root):
    from gtrmrs.deps import cli
    catalog(root, one_library())
    destination = root / "audit.txt"
    invoke(cli, [root, "--no-upstream", "--out", destination])
    return destination.exists(), True


@probe("D23")
def no_catalog_discovery(root):
    write(root, "settings.gradle.kts", 'rootProject.name = "fixture"\n')
    scanner = AndroidScanner()
    return scanner.can_scan_project(str(root)) == bool(scanner.discover_projects(str(root))), True


@probe("D24")
def commented_wrapper_url(root):
    write(root, "gradle/wrapper/gradle-wrapper.properties",
          "# distributionUrl=https\\://services.gradle.org/distributions/gradle-7.0-bin.zip\n"
          "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.0-bin.zip\n")
    return AndroidScanner().parse_gradle_wrapper(str(root)), "8.0"


@probe("R01")
def html_escaping(root):
    catalog(root, one_library())
    result = DepsEngine().run_audit(str(root), no_upstream=True)
    result.components[0].identifier = '<img src=x onerror="alert(1)">'
    output = root / "report.html"
    HtmlReporter().generate(result, str(output))
    return '<img src=x onerror="alert(1)">' in output.read_text(encoding="utf-8"), False


@probe("R02")
def unknown_sdk_html(root):
    catalog(root, one_library())
    result = DepsEngine().run_audit(str(root), no_upstream=True)
    output = root / "report.html"
    HtmlReporter().generate(result, str(output))
    text = output.read_text(encoding="utf-8")
    return "<strong> / </strong>" in text, False


@probe("R03")
def terminal_no_color(root):
    catalog(root, one_library())
    result = DepsEngine().run_audit(str(root), no_upstream=True)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        TerminalReporter(color_enabled=False).render(result)
    return "\x1b[" in output.getvalue(), False


@probe("R04")
def output_failure_status(root):
    from gtrmrs.deps import cli as deps_cli
    from gtrmrs.locr import cli as locr_cli
    from gtrmrs.rtree import cli as rtree_cli
    catalog(root, one_library())
    missing = root / "missing/report.txt"
    statuses = [
        invoke(deps_cli, [root, "--json", "--no-upstream", "--out", missing])[0],
        invoke(locr_cli, [root, "--out", missing])[0],
        invoke(rtree_cli, ["--repo", root, "--out", missing])[0],
    ]
    return [status != 0 for status in statuses], [True, True, True]


@probe("R05")
def raw_tree_git_contents(root):
    init(root)
    return ".git/config" in RepoTreeVisualizer(str(root), raw_mode=True, use_color=False).visible_paths, True


@probe("R06")
def rtree_redirected_ansi(root):
    from gtrmrs.rtree import cli
    write(root, "source.py", "pass\n")
    return "\x1b[" in invoke(cli, ["--repo", root])[1], False


@probe("S01")
def subdirectory_repository_label(root):
    from gtrmrs.storage.cli import _render
    repo = init(root / "repo")
    write(repo, "subdir/file.txt", "data")
    audit = StorageEngine().audit(str(repo / "subdir"))
    return ".. " in _render(audit, audit.candidates, None, False), False


@probe("S02")
def storage_secret_extension_gap(root):
    repo = init(root / "repo")
    write(repo, ".gitignore", "__pycache__/\n")
    write(repo, "__pycache__/credentials.p8", "private key")
    audit = StorageEngine().audit(str(repo))
    return audit.candidates[0].eligible, False


@probe("V01")
def git_directory_ignore_works(root):
    init(root)
    write(root, ".gitignore", "private/\n")
    write(root, "private/secret.py", "pass\n")
    return "private/secret.py" in RepoTreeVisualizer(str(root), use_color=False).visible_paths, False


@probe("V02")
def source_symlinks_are_skipped(root):
    source = write(root, "main.py", "pass\n")
    link = root / "linked.py"
    try:
        os.symlink(str(source), str(link))
    except OSError as exc:
        raise unittest_skip("File symlinks unavailable: " + str(exc))
    try:
        return "linked.py" in migrated(root), False
    finally:
        link.unlink()


@probe("V03")
def tracked_storage_is_protected(root):
    repo = init(root / "repo")
    write(repo, ".gitignore", "__pycache__/\n")
    write(repo, "__pycache__/source.py", "pass\n")
    git(repo, "add", "-f", "__pycache__/source.py")
    audit = StorageEngine().audit(str(repo))
    return audit.candidates[0].eligible, False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    results = []
    # Probes must remain offline. Specific upstream probes use in-memory metadata.
    with patch("urllib.request.urlopen", side_effect=RuntimeError("Audit probes cannot access the network")):
        for identifier, function in PROBES:
            with tempfile.TemporaryDirectory(prefix="gtrmrs-audit-") as directory:
                try:
                    observed, expected = function(Path(directory))
                    result = {"id": identifier, "probe": function.__name__,
                              "status": "PASS" if observed == expected else "GAP",
                              "observed": observed, "expected": expected}
                except unittest_skip as exc:
                    result = {"id": identifier, "probe": function.__name__, "status": "SKIP", "error": str(exc)}
                except Exception as exc:
                    result = {"id": identifier, "probe": function.__name__, "status": "ERROR",
                              "error": type(exc).__name__ + ": " + str(exc)}
                results.append(result)
                print("{id}: {status} ({probe})".format(**result))
    data = {"python": sys.version.split()[0], "platform": sys.platform, "results": results}
    if args.out:
        args.out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print("{} probes: {} gaps, {} passes, {} skips, {} errors".format(
        len(results), *(sum(r["status"] == status for r in results) for status in ("GAP", "PASS", "SKIP", "ERROR"))))
    return 2 if any(r["status"] == "ERROR" for r in results) else int(any(r["status"] == "GAP" for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
