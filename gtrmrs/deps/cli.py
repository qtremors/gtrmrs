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


def run(args: argparse.Namespace) -> None:
    """Executes the deps command workflow."""
    target_dir = os.path.abspath(args.explicit_dir or args.path or ".")
    use_color = not args.no_color and sys.stdout.isatty()

    if not os.path.exists(target_dir):
        print(f"Error: Target directory does not exist: {target_dir}", file=sys.stderr)
        sys.exit(1)

    engine = DepsEngine()

    if not args.json and not args.out:
        print(f"Scanning repositories in: {target_dir}...")

    # Run audit
    result = engine.run_audit(
        base_dir=target_dir,
        no_upstream=args.no_upstream,
        target_repo=args.repo,
    )

    if not result.profiles:
        print(
            f"No supported projects found with dependency catalogs in '{target_dir}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Output Terminal Report or JSON
    if args.json:
        json_content = JsonReporter().generate(result)
        if args.out:
            try:
                with open(args.out, "w", encoding="utf-8") as f:
                    f.write(json_content + "\n")
                print(f"JSON report written to: {args.out}")
            except OSError as e:
                print(f"Error writing to file: {e}", file=sys.stderr)
        else:
            print(json_content)
    else:
        reporter = TerminalReporter(color_enabled=use_color)
        reporter.render(result)

    # Generate HTML report if requested
    html_target = args.html
    if html_target or args.open:
        html_file = html_target or "android-dependency-report.html"
        html_path = os.path.abspath(html_file)
        HtmlReporter().generate(result, html_path)
        print(f"Interactive HTML Report generated at: {html_path}")

        if args.open:
            webbrowser.open(f"file://{html_path}")

    # Handle Updates (--align or --update)
    if args.align or args.update:
        mode = "update" if args.update else "align"
        planned_actions = engine.plan_updates(
            result, mode="upstream" if args.update else "align", target_repo=args.repo
        )

        print("\n" + f"{Colors.BOLD}{'--- PLANNED UPDATES ---'}{Colors.RESET}")
        if not planned_actions:
            print(f"No pending updates found for mode '{mode}'. Everything is already aligned/up-to-date.")
        else:
            status_tag = "[DRY-RUN]" if args.dry_run else "[APPLYING]"
            print(f"Found {len(planned_actions)} update actions {status_tag}:")
            for act in planned_actions:
                target_rel = os.path.relpath(act.file_path, target_dir)
                ref_info = f" (ref: {act.ref_name})" if act.is_version_ref else ""
                print(
                    f"  * {Colors.BOLD}{act.repo_name}{Colors.RESET}: "
                    f"{act.component_identifier}{ref_info} "
                    f"in {target_rel} "
                    f"-> {Colors.YELLOW}{act.old_version}{Colors.RESET} => {Colors.GREEN}{act.new_version}{Colors.RESET}"
                )

            if not args.dry_run:
                applied = engine.apply_actions(planned_actions, dry_run=False)
                success_count = sum(1 for _, ok in applied if ok)
                print(f"\nSuccessfully applied {success_count}/{len(planned_actions)} updates.")
            else:
                print("\nDry-run complete. No files were modified on disk.")


def main() -> None:
    """Direct CLI entry point for deps command."""
    parser = argparse.ArgumentParser(
        prog="deps",
        description="Multi-repository dependency and upgrade auditor and updater.",
    )
    _configure_parser(parser)
    args = parser.parse_args()
    try:
        run(args)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
