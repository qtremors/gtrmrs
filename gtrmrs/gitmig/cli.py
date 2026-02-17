"""
cli.py

CLI interface for gitmig subcommand.
Copy Git repositories without dependencies.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from gtrmrs.core.colors import Colors
from gtrmrs.gitmig.engine import GitMigEngine

from gtrmrs import __version__


def add_parser(subparsers) -> None:
    """Add gitmig subcommand to the argument parser."""
    parser = subparsers.add_parser(
        "gitmig",
        help="Copy repos without dependencies",
        description="Copy Git repositories without node_modules, venv, .git, etc.",
    )
    _configure_parser(parser)
    parser.set_defaults(func=run)


def _configure_parser(parser: argparse.ArgumentParser) -> None:
    """Configure argument parser with gitmig options."""
    parser.add_argument(
        "paths",
        nargs="*",
        help="Destination, or [source] [destination]",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be copied without copying.",
    )
    parser.add_argument(
        "--zip",
        action="store_true",
        help="Compress each repo as a .zip archive.",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show detailed file type breakdown.",
    )
    parser.add_argument(
        "--exclude",
        type=str,
        default="",
        help="Additional patterns to exclude (comma-separated).",
    )
    parser.add_argument(
        "--include-git",
        action="store_true",
        help="Include .git folder in the copy.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Include gitignored files but still exclude dependencies.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show every file being copied.",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress all output except errors.",
    )
    parser.add_argument(
        "--max-size",
        type=str,
        default=None,
        help="Skip files larger than this (e.g., '10M', '500K').",
    )
    parser.add_argument(
        "--only",
        type=str,
        default="",
        help="Only migrate specific repos (comma-separated).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files without warning.",
    )
    parser.add_argument(
        "--stats-all",
        action="store_true",
        help="Show all file extensions in stats.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip files that already exist (resume mode).",
    )
    parser.add_argument(
        "--env",
        action="store_true",
        help="Copy only .env files (.env, .env.local, .env.example, etc.).",
    )
    parser.add_argument(
        "--ext",
        type=str,
        default="",
        help="Copy only files with given extension(s) (comma-separated, e.g., 'md,py').",
    )
    parser.add_argument(
        "--git-size",
        action="store_true",
        help="Calculate and show size of .git folder (skips migration).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"gitmig {__version__}",
    )


def _parse_size(size_str: str) -> Optional[int]:
    """Parse size string like '10M', '500K', '1G' to bytes."""
    if not size_str:
        return None

    size_str = size_str.upper().strip()
    try:
        if size_str.endswith("G"):
            return int(float(size_str[:-1]) * 1024 * 1024 * 1024)
        elif size_str.endswith("M"):
            return int(float(size_str[:-1]) * 1024 * 1024)
        elif size_str.endswith("K"):
            return int(float(size_str[:-1]) * 1024)
        else:
            return int(size_str)
    except ValueError:
        return None


def run(args: argparse.Namespace) -> None:
    """Execute gitmig command."""
    # Parse positional arguments
    source_dir = os.getcwd()
    dest_dir = None

    if len(args.paths) == 0:
        if not args.git_size:
            print("Error: Destination argument is required.")
            print("Usage: gitmig [source] destination")
            sys.exit(1)
        # For --git-size, default source is current dir, no dest needed
    elif len(args.paths) == 1:
        if args.git_size:
            source_dir = args.paths[0]
        else:
            dest_dir = args.paths[0]
    elif len(args.paths) == 2:
        source_dir = args.paths[0]
        dest_dir = args.paths[1]
    else:
        print(f"Error: Expected [destination] or [source] [destination]")
        sys.exit(1)

    # Parse extra excludes
    extra_excludes: List[str] = []
    if args.exclude:
        extra_excludes = [e.strip() for e in args.exclude.split(",") if e.strip()]

    # Parse --only repos
    only_repos: Optional[List[str]] = None
    if args.only:
        only_repos = [r.strip() for r in args.only.split(",") if r.strip()]

    # Parse --ext filter
    ext_filter: Optional[List[str]] = None
    if args.ext:
        ext_filter = [e.strip().lstrip(".").lower() for e in args.ext.split(",") if e.strip()]

    # Parse --max-size
    max_size = None
    if args.max_size:
        max_size = _parse_size(args.max_size)
        if max_size is None:
            print(
                f"Error: Invalid size format '{args.max_size}'. Use format like '10M', '500K', or '1G'."
            )
            sys.exit(1)

    # Validate source
    if not os.path.isdir(source_dir):
        print(f"Error: Source '{source_dir}' is not a valid directory.")
        sys.exit(1)
    source_dir = os.path.abspath(source_dir)

    # Validate destination
    if dest_dir and os.path.exists(dest_dir) and not os.path.isdir(dest_dir):
        print(f"Error: Destination '{dest_dir}' exists but is not a directory.")
        sys.exit(1)

    # Prevent copying into source
    if dest_dir:
        abs_dest = os.path.abspath(dest_dir)
        # Skip this check if using --git-size (read-only mode)
        if not args.git_size:
            if abs_dest.startswith(source_dir + os.sep) or abs_dest == source_dir:
                print("Error: Destination cannot be inside the source directory.")
                sys.exit(1)

    # Create destination if needed
    if dest_dir and not args.dry_run and not os.path.exists(dest_dir):
        try:
            os.makedirs(dest_dir)
        except OSError as e:
            print(f"Error: Could not create destination directory: {e}")
            sys.exit(1)

    # Run migration
    engine = GitMigEngine(
        source_dir,
        dest_dir if dest_dir else "",
        dry_run=args.dry_run,
        use_zip=args.zip,
        show_stats=args.stats,
        extra_excludes=extra_excludes,
        include_git=args.include_git,
        verbose=args.verbose,
        quiet=args.quiet,
        max_size=max_size,
        only_repos=only_repos,
        force=args.force,
        stats_all=args.stats_all,
        skip_existing=args.skip_existing,
        env_only=args.env,
        ext_filter=ext_filter,
        raw_mode=args.raw,
        check_git_size=args.git_size,
    )

    try:
        engine.run()
    except KeyboardInterrupt:
        print(f"\n{Colors.style('Migration interrupted.', Colors.YELLOW)}")
        sys.exit(1)


def main() -> None:
    """Direct entry point for gitmig command."""
    parser = argparse.ArgumentParser(
        prog="gitmig",
        description="Copy Git repositories without dependencies.",
    )
    _configure_parser(parser)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
