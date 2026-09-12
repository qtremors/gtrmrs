"""Storage reports and opt-in cleanup for one repository or a workspace."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from gtrmrs import __version__
from gtrmrs.storage.engine import REASONS, StorageEngine


def _configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("path", nargs="?", default=".", help="Repository or workspace to scan")
    parser.add_argument("--repo", help="Exact repository name or path relative to the scan root")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--out", help="Write the report to a file")
    parser.add_argument("--clean", action="store_true", help="Preview eligible build/cache cleanup")
    parser.add_argument("--include-deps", action="store_true", help="Also select installed dependencies for cleanup")
    parser.add_argument("--apply", action="store_true", help="With --clean, delete the selected directories")
    parser.add_argument("--keep", action="append", default=[], metavar="PATTERN",
                        help="Keep cleanup candidates containing matching names or scan-root-relative paths; repeatable")
    parser.add_argument("--version", action="version", version="storage " + __version__)


def add_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "storage", help="Audit repository space and preview generated-file cleanup",
        description="Rank repository sizes and identify generated files. Read-only by default.",
    )
    _configure_parser(parser)
    parser.set_defaults(func=run)


def _size(value: int) -> str:
    number = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if number < 1024 or unit == "TiB":
            return "{:.2f} {}".format(number, unit)
        number /= 1024
    return ""


def _render(audit, candidates, cleanup, include_deps: bool) -> str:
    lines = ["Repository storage: " + audit.root, "Total: {} across {:,} files".format(_size(audit.bytes), audit.files)]
    lines.append("Sizes are file lengths, not guaranteed freed disk space; links are not followed.")
    lines += ["", "Repository                         Total          Git     Eligible cleanup"]
    for repo in audit.repositories:
        repository = Path(repo.path)
        scan_root = Path(audit.root)
        subtree = repository in scan_root.parents
        label = repository.name if repo.path == audit.root or subtree else os.path.relpath(repo.path, audit.root)
        eligible = sum(c.bytes for c in candidates if c.repo == repo.path and c.eligible and (
            c.kind != "dependencies" or include_deps
        ))
        lines.append("{:<30} {:>12} {:>12} {:>18}".format(
            label,
            _size(repo.bytes), _size(repo.git_bytes), _size(eligible),
        ))
        if subtree:
            lines.append("  Scanned subtree: {} (file totals cover this subtree only)".format(scan_root.relative_to(repository).as_posix()))
        if repo.git_objects.get("size", 0) >= 100 * 1024:
            lines.append("  Git has {} of loose objects; review recovery needs before Git-managed GC.".format(
                _size(repo.git_objects["size"] * 1024),
            ))
    outside = audit.bytes - sum(repo.bytes for repo in audit.repositories)
    if outside:
        lines.append("Outside repositories: " + _size(outside))
    lines += ["", "Generated directories (largest first):"]
    for candidate in candidates:
        action = "REMOVE" if candidate.eligible else "KEEP"
        if candidate.kind == "dependencies" and not include_deps and candidate.eligible:
            action = "OPTIONAL"
        lines.append("{} {:>12}  {}".format(action, _size(candidate.bytes), os.path.relpath(candidate.path, audit.root)))
        lines.append("  " + candidate.reason)
        for blocker in candidate.blockers:
            lines.append("  Keep: " + blocker)
        if candidate.reason == REASONS["rust"]:
            for name, size in candidate.breakdown.items():
                if "/" not in name or name.endswith("/incremental"):
                    lines.append("  {}: {}".format(name, _size(size)))
    rust_targets = {}
    for candidate in candidates:
        if candidate.reason == REASONS["rust"]:
            path = Path(candidate.path)
            root = path.parent if path.parent.name == "target" else path.parent.parent
            rust_targets.setdefault(str(root), set()).add("default" if path.parent == root else path.parent.name)
    for root, targets in rust_targets.items():
        if "default" in targets and len(targets) > 1:
            lines.append("Rust builds in {} use default and explicit targets; use a consistent build target.".format(root))
    if not candidates:
        lines.append("No recognized generated directories found.")
    total = sum(c.bytes for c in candidates if c.eligible and (c.kind != "dependencies" or include_deps))
    lines += ["", "Eligible cleanup: " + _size(total)]
    if cleanup is not None:
        for result in cleanup:
            lines.append("{} {}{}".format(
                result["status"].upper(), result["path"],
                ": " + result["error"] if "error" in result else "",
            ))
        if not any(result["status"] == "removed" for result in cleanup):
            lines.append("Nothing deleted. Stop builds/dev servers before running --clean --apply.")
        else:
            lines.append("Removed {} of file data; future builds/installs will recreate outputs.".format(
                _size(sum(r["bytes"] for r in cleanup if r["status"] == "removed")),
            ))
    else:
        lines.append("Read-only audit. Use --clean to preview; add --apply to delete.")
    lines.append("Dependencies require --include-deps. Git data and retained artifacts are never cleanup targets.")
    if audit.skipped_links:
        lines.append("Skipped {} links/junctions; affected cleanup candidates are kept.".format(len(audit.skipped_links)))
    for error in audit.errors:
        lines.append("Warning: " + error)
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> None:
    if args.apply and not args.clean:
        print("Error: --apply requires --clean.", file=sys.stderr)
        raise SystemExit(2)
    try:
        engine = StorageEngine()
        audit = engine.audit(args.path, keep_patterns=args.keep)
        if args.repo:
            matches = [repo for repo in audit.repositories if args.repo in (
                Path(repo.path).name, os.path.relpath(repo.path, audit.root),
            )]
            if len(matches) != 1:
                raise ValueError("--repo must match exactly one repository name or relative path")
            audit.candidates = [c for c in audit.candidates if c.repo == matches[0].path]
        selected = [c for c in audit.candidates if c.eligible and (
            c.kind != "dependencies" or args.include_deps
        )]
        if args.out:
            destination = Path(os.path.realpath(os.path.abspath(args.out)))
            if args.clean and any(Path(c.path) == destination or Path(c.path) in destination.parents for c in selected):
                raise ValueError("Report output must be outside selected cleanup directories")
            # Verify the destination before any deletion is attempted.
            if not destination.parent.is_dir() or destination.is_dir():
                raise ValueError("Report output must have an existing parent directory and be a file")
        cleanup = engine.clean(audit, selected, apply=args.apply) if args.clean else None
        if args.json:
            report = audit.to_dict()
            report["cleanup"] = cleanup
            report["repository_filter"] = args.repo
            report["selected_bytes"] = sum(c.bytes for c in selected)
            output = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
        else:
            output = _render(audit, audit.candidates, cleanup, args.include_deps)
            if args.repo:
                output = "Repository filter: " + args.repo + " (workspace totals retained)\n" + output
        if args.out:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(output)
        else:
            print(output, end="")
        if audit.errors or (cleanup is not None and any(r["status"] == "refused" for r in cleanup)):
            raise SystemExit(1)
    except (OSError, ValueError) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        raise SystemExit(2)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Repository storage audit and explicit cleanup")
    _configure_parser(parser)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
