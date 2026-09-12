"""
cli.py

CLI interface for gtrmrs deps subcommand and standalone deps command.
Multi-repository and single-project dependency auditor and updater.
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path
from typing import Optional

from gtrmrs.core.colors import Colors
from gtrmrs.deps.engine import DepsEngine
from gtrmrs.deps.report.html import HtmlReporter
from gtrmrs.deps.report.json_report import JsonReporter
from gtrmrs.deps.report.terminal import TerminalReporter


def _configure_parser(parser: argparse.ArgumentParser) -> None:
    """Configures CLI options for deps command."""
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to project or directory of repositories (default: current directory)",
    )
    parser.add_argument(
        "--dir",
        dest="explicit_dir",
        help="Explicit directory containing projects (overrides positional path)",
    )
    parser.add_argument(
        "--no-upstream",
        action="store_true",
        help="Skip querying upstream Maven Central, Google Maven, and Gradle services",
    )
    parser.add_argument(
        "--html",
        nargs="?",
        const="android-dependency-report.html",
        default=None,
        help="Generate interactive HTML report (default filename: android-dependency-report.html)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the generated HTML report in the default browser",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )
    parser.add_argument(
        "--out",
        help="Write report output to specified file path",
    )
    parser.add_argument(
        "--repo",
        help="Filter audit or update to a specific repository",
    )
    parser.add_argument(
        "--align",
        action="store_true",
        help="Align outdated repositories to the highest version found across scanned repositories",
    )
    parser.add_argument(
        "--update",
        "-u",
        action="store_true",
        help="Upgrade outdated dependencies to the latest upstream stable release",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview planned in-place updates without modifying files",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color codes in terminal output",
    )


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register deps command with the umbrella gtrmrs CLI."""
    parser = subparsers.add_parser(
        "deps",
        help="Multi-repo dependency and upgrade auditor and updater",
        description="Scans repositories for dependency catalogs, discrepancies, and upstream updates.",
    )
    _configure_parser(parser)
    parser.set_defaults(func=run)


def _same_destination(first: str, second: str) -> bool:
    if os.path.normcase(os.path.realpath(first)) == os.path.normcase(os.path.realpath(second)):
        return True
    try:
        return os.path.samefile(first, second)
    except FileNotFoundError:
        return False


def _configure_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and (getattr(stream, "encoding", None) or "").lower() != "utf-8":
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def run(args: argparse.Namespace) -> None:
    """Executes the deps command workflow."""
    _configure_streams()
    target_dir = os.path.abspath(args.explicit_dir or args.path or ".")
    use_color = not args.no_color and not args.out and sys.stdout.isatty()
    notice_stream = sys.stderr if args.json else sys.stdout
    notice_color = not args.no_color and notice_stream.isatty()

    def notice(message: str) -> None:
        print(message, file=notice_stream)

    def style(message: str, color: str) -> str:
        return Colors.style(message, color, enabled=notice_color)

    if not os.path.exists(target_dir):
        print(f"Error: Target directory does not exist: {target_dir}", file=sys.stderr)
        sys.exit(1)

    engine = DepsEngine()

    if not args.json and not args.out:
        notice(f"Scanning repositories in: {target_dir}...")

    # Run audit
    try:
        result = engine.run_audit(
            base_dir=target_dir,
            no_upstream=args.no_upstream,
            target_repo=args.repo,
            comparison_scope=args.align or args.update,
        )
    except (OSError, ValueError) as exc:
        print("Unable to audit projects: " + str(exc), file=sys.stderr)
        sys.exit(1)

    if not result.profiles:
        print(
            f"No supported Gradle projects found in '{target_dir}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    planned_actions = []
    if args.align or args.update:
        try:
            planned_actions = engine.plan_updates(
                result, mode="upstream" if args.update else "align", target_repo=args.repo,
            )
        except ValueError as exc:
            print("Unable to plan updates: " + str(exc), file=sys.stderr)
            sys.exit(1)

    html_file = (args.html or "android-dependency-report.html") if args.html or args.open else None
    update_paths = {action.file_path for action in planned_actions}
    update_paths.update(path for profile in result.profiles.values() for path in profile.metadata.get("update_fingerprints", {}))
    try:
        for output in (args.out, html_file):
            if output and any(_same_destination(output, source) for source in update_paths):
                raise ValueError("Report output cannot overwrite an audited build file: " + output)
        if args.out and html_file and _same_destination(args.out, html_file):
            raise ValueError("Text/JSON and HTML reports must use different output files")
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    # Output Terminal Report or JSON
    content = JsonReporter().generate(result) if args.json else TerminalReporter(color_enabled=use_color).generate(result)
    if not content.endswith("\n"):
        content += "\n"
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(content)
            notice("{} report written to: {}".format("JSON" if args.json else "Text", args.out))
        except OSError as exc:
            print("Error writing report: " + str(exc), file=sys.stderr)
            sys.exit(1)
    else:
        print(content, end="")

    # Generate HTML report if requested
    if html_file:
        html_path = os.path.abspath(html_file)
        try:
            HtmlReporter().generate(result, html_path)
            notice(f"Interactive HTML Report generated at: {html_path}")
            if args.open and not webbrowser.open(Path(html_path).as_uri()):
                raise OSError("The browser could not open the report")
        except (OSError, webbrowser.Error) as exc:
            print("Error generating or opening HTML report: " + str(exc), file=sys.stderr)
            sys.exit(1)

    # Handle Updates (--align or --update)
    if args.align or args.update:
        mode = "update" if args.update else "align"
        notice("\n" + style('--- PLANNED UPDATES ---', Colors.BOLD))
        if not planned_actions:
            if args.update and result.upstream_checks["skipped"]:
                notice("No upstream updates planned: upstream checks were skipped (--no-upstream).")
            elif args.update and result.upstream_checks["unavailable"]:
                notice("No updates could be planned with the available upstream information.")
            else:
                notice(f"No pending updates found for mode '{mode}'.")
        else:
            status_tag = "[DRY-RUN]" if args.dry_run else "[APPLYING]"
            notice(f"Found {len(planned_actions)} update actions {status_tag}:")
            for act in planned_actions:
                target_rel = os.path.relpath(act.file_path, target_dir)
                ref_info = f" (ref: {act.ref_name})" if act.is_version_ref else ""
                notice(
                    f"  * {style(act.repo_name, Colors.BOLD)}: "
                    f"{act.component_identifier}{ref_info} "
                    f"in {target_rel} "
                    f"-> {style(act.old_version, Colors.YELLOW)} => {style(act.new_version, Colors.GREEN)}"
                )

            applied = engine.apply_actions(planned_actions, dry_run=args.dry_run)
            success_count = sum(1 for _, ok in applied if ok)
            if not args.dry_run:
                notice(f"\nSuccessfully applied {success_count}/{len(planned_actions)} updates.")
            else:
                notice(f"\nValidated {success_count}/{len(planned_actions)} updates. No files were modified on disk.")
            for action, success in applied:
                if not success:
                    reason = engine.updater.last_errors.get(action.file_path, "Update could not be applied")
                    print("Failed update for {} in {}: {}".format(action.component_identifier, action.file_path, reason), file=sys.stderr)
            if success_count != len(planned_actions):
                sys.exit(1)


def main() -> None:
    """Direct CLI entry point for deps command."""
    _configure_streams()
    parser = argparse.ArgumentParser(
        prog="deps",
        description="Multi-repository dependency and upgrade auditor and updater.",
    )
    _configure_parser(parser)
    args = parser.parse_args()
    try:
        run(args)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
