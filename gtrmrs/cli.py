"""
cli.py

Main entry point for gtrmrs unified CLI.
Routes to subcommands: rtree, locr, gitmig.
"""

from __future__ import annotations

import argparse
import sys

from gtrmrs import __version__


def main() -> None:
    """Main entry point for gtrmrs command."""
    parser = argparse.ArgumentParser(
        prog="gtrmrs",
        description="Unified CLI tools for Git repository management.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"gtrmrs {__version__}",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
        description="Available subcommands",
    )

    # Register subcommands
    from gtrmrs.rtree.cli import add_parser as add_rtree
    from gtrmrs.locr.cli import add_parser as add_locr
    from gtrmrs.gitmig.cli import add_parser as add_gitmig

    add_rtree(subparsers)
    add_locr(subparsers)
    add_gitmig(subparsers)

    # Parse arguments
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Execute subcommand
    args.func(args)


if __name__ == "__main__":
    main()
