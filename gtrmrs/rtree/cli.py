"""
cli.py

CLI interface for rtree subcommand.
Generates plain-text directory trees for Git repositories.
"""

from __future__ import annotations

import argparse
import itertools
import os
import sys
import time
from typing import List, Optional

from gtrmrs.core.colors import Colors
from gtrmrs.rtree.engine import RepoTreeVisualizer

from gtrmrs import __version__


def auto_out_name(repo_name: str, flat_mode: bool, raw_mode: bool) -> str:
    """Generate automatic output filename."""
    base = os.path.basename(os.path.abspath(repo_name))
    suffix = "flat_tree" if flat_mode else "tree"
    if raw_mode:
        suffix += "_raw"
    return f"{base}_{suffix}.txt"


def add_parser(subparsers) -> None:
    """Add rtree subcommand to the argument parser."""
    parser = subparsers.add_parser(
        "rtree",
        help="Generate directory tree visualization",
        description="Generate plain-text folder/file trees for directories.",
    )
    _configure_parser(parser)
    parser.set_defaults(func=run)


def _configure_parser(parser: argparse.ArgumentParser) -> None:
    """Configure argument parser with rtree options."""
    parser.add_argument(
        "--repo", "-r",
        default=".",
        nargs="?",
        help="Target directory. Defaults to current directory.",
    )
    parser.add_argument(
        "--out", "-o",
        nargs="?",
        const=True,
        help="Write output to file. Auto-generates name if no value provided.",
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Output flat list of paths instead of tree.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Include everything (ignore .gitignore rules).",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=-1,
        help="Max recursion depth. Default: unlimited.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all git repositories in current directory.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"rtree {__version__}",
    )


def run(args: argparse.Namespace) -> None:
    """Execute rtree command."""
    cwd = os.getcwd()

    # Handle --list mode
    if args.list:
        try:
            repos = [
                n
                for n in sorted(os.listdir(cwd))
                if os.path.isdir(os.path.join(cwd, n, ".git"))
            ]
            for r in repos:
                print(Colors.style(r, Colors.BLUE, not args.no_color))
            if not repos:
                print("No git repos found.")
        except OSError:
            pass
        return

    # Resolve target path
    target_arg = args.repo if args.repo else "."
    repo_path = (
        target_arg if os.path.isabs(target_arg) else os.path.join(cwd, target_arg)
    )

    if not os.path.isdir(repo_path):
        print(f"Error: '{target_arg}' is not a valid directory.", file=sys.stderr)
        sys.exit(2)

    # Determine color usage
    out_arg = args.out
    writing_to_file = out_arg is not None
    use_color = not args.no_color and not writing_to_file

    # Spinner setup
    spinner_active = not writing_to_file and sys.stdout.isatty()
    msg = f"rtree: scanning {os.path.basename(repo_path)}..."
    spinner = itertools.cycle(["|", "/", "-", "\\"])
    last_spin = 0

    def update_spinner(*args):
        nonlocal last_spin
        if not spinner_active:
            return
        now = time.time()
        if now - last_spin > 0.1:
            sys.stdout.write(
                Colors.style(f"\r{msg} {next(spinner)}", Colors.CYAN, use_color)
            )
            sys.stdout.flush()
            last_spin = now

    if spinner_active:
        sys.stdout.write(Colors.HIDE_CURSOR)
        sys.stdout.write(Colors.style(msg, Colors.CYAN, use_color))
        sys.stdout.flush()

    try:
        visualizer = RepoTreeVisualizer(
            repo_path,
            raw_mode=bool(args.raw),
            max_depth=args.depth,
            use_color=use_color,
            callback=update_spinner,
        )

        output_lines = (
            visualizer.get_flat_list() if args.flat else visualizer.get_ascii_tree()
        )

        # Clear spinner
        if spinner_active:
            sys.stdout.write(f"\r{' ' * (len(msg) + 5)}\r")
            sys.stdout.flush()

        if writing_to_file:
            outname = (
                auto_out_name(repo_path, args.flat, args.raw)
                if out_arg is True
                else out_arg
            )
            try:
                with open(outname, "w", encoding="utf-8") as f:
                    f.write("\n".join(output_lines) + "\n")
                print(f"Output written to: {Colors.style(str(outname), Colors.GREEN)}")
            except OSError as e:
                print(f"Error writing to '{outname}': {e}", file=sys.stderr)
        else:
            print("\n".join(output_lines))

    finally:
        if spinner_active:
            sys.stdout.write(Colors.SHOW_CURSOR)


def main() -> None:
    """Direct entry point for rtree command."""
    parser = argparse.ArgumentParser(
        prog="rtree",
        description="Generate plain-text directory trees for Git repositories.",
    )
    _configure_parser(parser)
    args = parser.parse_args()
    
    try:
        run(args)
    except KeyboardInterrupt:
        print("\n" + Colors.style("⚠ Tree generation interrupted.", Colors.YELLOW))
        sys.exit(0)


if __name__ == "__main__":
    main()
