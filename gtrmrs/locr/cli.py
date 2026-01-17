"""
cli.py

CLI interface for locr subcommand.
Lines of code counter with language-specific breakdown.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import shutil
import sys
import time
from typing import Dict

from gtrmrs.core.colors import Colors
from gtrmrs.locr.engine import LocrEngine

from gtrmrs import __version__



# Constants
WIDTH_STATS = 78
WIDTH_SIMPLE = 72
FMT_STATS = "{:<20} {:>12} {:>14} {:>14} {:>14}"
FMT_SIMPLE = "{:<22} {:>10} {:>12} {:>12} {:>12}"


def generate_report(
    results: Dict,
    elapsed_time: float,
    use_color: bool,
    interrupted: bool,
    show_stats: bool,
) -> List[str]:
    """Generate text report from scan results."""
    lines = []

    if not results:
        return lines + ["No code files found."]

    # Calculate totals
    total_files = sum(s["files"] for s in results.values())
    total_blank = sum(s["blank"] for s in results.values())
    total_comment = sum(s["comment"] for s in results.values())
    total_code = sum(s["code"] for s in results.values())
    
    grand_total_lines = total_blank + total_comment + total_code
    safe_total_files = total_files if total_files > 0 else 1

    sorted_stats = sorted(results.items(), key=lambda x: x[1]["code"], reverse=True)

    # Determine widths
    if show_stats:
        content_width = WIDTH_STATS
        header_fmt = FMT_STATS
        row_fmt = FMT_STATS
    else:
        content_width = WIDTH_SIMPLE
        header_fmt = FMT_SIMPLE
        row_fmt = FMT_SIMPLE

    sep = "=" * content_width
    thin_sep = "-" * content_width

    lines.append("")
    lines.append(Colors.style(sep, Colors.WHITE, use_color))

    if show_stats:
        # Detailed view with percentages
        lines.append(
            Colors.style(
                header_fmt.format("Language", "Files", "Blank", "Comment", "Code"),
                Colors.BOLD,
                use_color,
            )
        )
        lines.append(Colors.style(thin_sep, Colors.WHITE, use_color))

        for lang, s in sorted_stats:
            l_lines = s["blank"] + s["comment"] + s["code"]
            safe_lines = l_lines if l_lines > 0 else 1

            f_pct = (s["files"] / safe_total_files) * 100
            b_pct = (s["blank"] / safe_lines) * 100
            c_pct = (s["comment"] / safe_lines) * 100
            k_pct = (s["code"] / safe_lines) * 100

            lines.append(
                Colors.style(
                    row_fmt.format(
                        lang,
                        f"{s['files']} ({f_pct:.0f}%)",
                        f"{s['blank']} ({b_pct:.0f}%)",
                        f"{s['comment']} ({c_pct:.0f}%)",
                        f"{s['code']} ({k_pct:.0f}%)",
                    ),
                    s["color"],
                    use_color,
                )
            )

        # Totals
        safe_global = grand_total_lines if grand_total_lines > 0 else 1
        gt_b_pct = (total_blank / safe_global) * 100
        gt_c_pct = (total_comment / safe_global) * 100
        gt_k_pct = (total_code / safe_global) * 100

        lines.append(Colors.style(thin_sep, Colors.WHITE, use_color))
        lines.append(
            Colors.style(
                row_fmt.format(
                    "TOTAL",
                    f"{total_files} (100%)",
                    f"{total_blank} ({gt_b_pct:.0f}%)",
                    f"{total_comment} ({gt_c_pct:.0f}%)",
                    f"{total_code} ({gt_k_pct:.0f}%)",
                ),
                Colors.BOLD,
                use_color,
            )
        )
    else:
        # Simple view
        lines.append(
            Colors.style(
                header_fmt.format("Language", "Files", "Blank", "Comment", "Code"),
                Colors.BOLD,
                use_color,
            )
        )
        lines.append(Colors.style(thin_sep, Colors.WHITE, use_color))

        for lang, s in sorted_stats:
            lines.append(
                Colors.style(
                    header_fmt.format(
                        lang, s["files"], s["blank"], s["comment"], s["code"]
                    ),
                    s["color"],
                    use_color,
                )
            )

        lines.append(Colors.style(thin_sep, Colors.WHITE, use_color))
        lines.append(
            Colors.style(
                header_fmt.format(
                    "TOTAL", total_files, total_blank, total_comment, total_code
                ),
                Colors.BOLD,
                use_color,
            )
        )

    lines.append(Colors.style(sep, Colors.WHITE, use_color))
    time_str = f"Processed {total_files} files in {elapsed_time:.3f} seconds."
    lines.append(Colors.style(time_str, Colors.CYAN, use_color))
    lines.append("")

    return lines


def generate_json_report(
    results: Dict, elapsed_time: float, interrupted: bool
) -> str:
    """Generate JSON report from scan results."""
    total_files = sum(s["files"] for s in results.values())
    total_blank = sum(s["blank"] for s in results.values())
    total_comment = sum(s["comment"] for s in results.values())
    total_code = sum(s["code"] for s in results.values())

    output = {
        "metadata": {
            "version": __version__,
            "elapsed_seconds": round(elapsed_time, 3),
            "interrupted": interrupted,
            "timestamp": time.time(),
        },
        "totals": {
            "files": total_files,
            "blank": total_blank,
            "comment": total_comment,
            "code": total_code,
            "lines": total_blank + total_comment + total_code,
        },
        "languages": {},
    }

    for lang, s in results.items():
        output["languages"][lang] = {
            "files": s["files"],
            "blank": s["blank"],
            "comment": s["comment"],
            "code": s["code"],
        }

    return json.dumps(output, indent=2)


def auto_out_name(target_path: str, is_json: bool = False) -> str:
    """Generate automatic output filename."""
    abs_target = os.path.abspath(target_path)
    folder_name = os.path.basename(os.path.normpath(abs_target))
    if not folder_name:
        folder_name = "root"
    ext = ".json" if is_json else ".txt"
    suffix = "_locr"
    return os.path.join(abs_target, f"{folder_name}{suffix}{ext}")


def add_parser(subparsers) -> None:
    """Add locr subcommand to the argument parser."""
    parser = subparsers.add_parser(
        "locr",
        help="Count lines of code",
        description="Lines of code counter with language breakdown.",
    )
    _configure_parser(parser)
    parser.set_defaults(func=run)


def _configure_parser(parser: argparse.ArgumentParser) -> None:
    """Configure argument parser with locr options."""
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Target directory. Defaults to current directory.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Ignore .gitignore rules.",
    )
    parser.add_argument(
        "--out", "-o",
        nargs="?",
        const=True,
        help="Write output to file.",
    )
    parser.add_argument(
        "--stats", "-s",
        action="store_true",
        help="Show percentage statistics.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"locr {__version__}",
    )


def run(args: argparse.Namespace) -> None:
    """Execute locr command."""
    target_path = os.path.abspath(args.path)

    is_writing_file = args.out is not None
    use_color = not args.no_color and not is_writing_file and sys.stdout.isatty()

    if not os.path.isdir(target_path):
        print(f"Error: {args.path} is not a directory.")
        sys.exit(1)

    spinner_active = not is_writing_file and sys.stdout.isatty()
    msg = f"locr: scanning {os.path.basename(target_path)}..."

    if spinner_active:
        sys.stdout.write(Colors.style(msg, Colors.CYAN, use_color))
        sys.stdout.flush()

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

    start_time = time.time()

    if spinner_active:
        sys.stdout.write(Colors.HIDE_CURSOR)

    try:
        engine = LocrEngine(target_path, raw_mode=args.raw)
        results = engine.scan(callback=update_spinner)

        if spinner_active:
            w = shutil.get_terminal_size().columns
            sys.stdout.write(f"\r{' ' * (w - 1)}\r")
            sys.stdout.flush()

    except OSError as e:
        if spinner_active:
            w = shutil.get_terminal_size().columns
            sys.stdout.write(f"\r{' ' * (w - 1)}\r")
            sys.stdout.flush()
        print(f"\nError: {e}")
        sys.exit(1)
    finally:
        if spinner_active:
            sys.stdout.write(Colors.SHOW_CURSOR)

    end_time = time.time()

    report_lines = []
    if not args.json:
        report_lines = generate_report(
            results,
            end_time - start_time,
            use_color,
            engine.was_interrupted,
            show_stats=args.stats,
        )

    if is_writing_file:
        filename = (
            auto_out_name(target_path, is_json=args.json)
            if args.out is True
            else args.out
        )
        try:
            if args.json:
                content = generate_json_report(
                    results, end_time - start_time, engine.was_interrupted
                )
            else:
                clean_lines = generate_report(
                    results,
                    end_time - start_time,
                    False,
                    engine.was_interrupted,
                    show_stats=args.stats,
                )
                content = "\n".join(clean_lines) + "\n"

            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Output written to: {filename}")
        except OSError as e:
            print(f"Error writing to file: {e}")
    else:
        if args.json:
            print(
                generate_json_report(
                    results, end_time - start_time, engine.was_interrupted
                )
            )
        else:
            print("\n".join(report_lines))


def main() -> None:
    """Direct entry point for locr command."""
    parser = argparse.ArgumentParser(
        prog="locr",
        description="Lines of code counter with language breakdown.",
    )
    _configure_parser(parser)
    args = parser.parse_args()
    try:
        run(args)
    except KeyboardInterrupt:
        print("\n" + Colors.style("⚠ Scan interrupted.", Colors.YELLOW))
        sys.exit(0)


if __name__ == "__main__":
    main()
