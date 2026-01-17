"""
engine.py

GitMigEngine - Repository copy/migration engine.
Refactored to use shared core module with .gitignore support.
"""

from __future__ import annotations

import fnmatch
import itertools
import os
import shutil
import subprocess
import sys
import time
import zipfile
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Set, Tuple

from gtrmrs.core.colors import Colors
from gtrmrs.core.patterns import EXCLUDE_DIRS, EXCLUDE_FILE_PATTERNS, PRESERVE_PATTERNS
from gtrmrs.core.git_utils import is_git_repo, git_check_ignore

# Env file patterns for --env mode
ENV_PATTERNS: List[str] = [
    ".env",
    ".env.*",
    "*.env",
]


class GitMigEngine:
    """Copy Git repositories without dependencies."""

    def __init__(
        self,
        source_dir: str,
        dest_dir: str,
        dry_run: bool = False,
        use_zip: bool = False,
        show_stats: bool = False,
        extra_excludes: Optional[List[str]] = None,
        include_git: bool = False,
        verbose: bool = False,
        quiet: bool = False,
        max_size: Optional[int] = None,
        only_repos: Optional[List[str]] = None,
        force: bool = False,
        stats_all: bool = False,
        skip_existing: bool = False,
        env_only: bool = False,
        ext_filter: Optional[List[str]] = None,
        raw_mode: bool = False,
    ):
        self.source_dir = os.path.abspath(source_dir)
        self.dest_dir = os.path.abspath(dest_dir)
        self.dry_run = dry_run
        self.use_zip = use_zip
        self.show_stats = show_stats
        self.include_git = include_git
        self.verbose = verbose
        self.quiet = quiet
        self.max_size = max_size
        self.only_repos = only_repos
        self.force = force
        self.stats_all = stats_all
        self.skip_existing = skip_existing
        self.env_only = env_only
        self.ext_filter = ext_filter  # List of extensions like ['md', 'py']
        self.raw_mode = raw_mode  # Include gitignored files but exclude dependencies

        # Merge excludes
        self.exclude_dirs = list(EXCLUDE_DIRS)
        self.exclude_files = list(EXCLUDE_FILE_PATTERNS)

        if extra_excludes:
            for pattern in extra_excludes:
                pattern = pattern.strip()
                if pattern.endswith("/"):
                    self.exclude_dirs.append(pattern.rstrip("/"))
                else:
                    self.exclude_files.append(pattern)

        # Remove .git from exclusions if --include-git
        if self.include_git and ".git" in self.exclude_dirs:
            self.exclude_dirs.remove(".git")

        # Stats
        self.repos_found: List[str] = []
        self.total_files_copied = 0
        self.total_files_skipped = 0
        self.total_bytes_copied = 0
        self.preserved_files: List[str] = []
        self.symlinks_skipped = 0
        self.large_files_skipped = 0
        self.files_overwritten = 0
        self.files_skipped_existing = 0
        self.start_time: float = 0
        self.was_interrupted = False

        # Stats per extension
        self.extension_stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"count": 0, "bytes": 0}
        )

        # Spinner
        self.spinner = itertools.cycle(["|", "/", "-", "\\"])
        self.last_spin_time = 0
        self.spinner_active = False

    def _print(self, message: str = "", style_color: str = None) -> None:
        """Print message unless in quiet mode."""
        if not self.quiet:
            if style_color:
                print(Colors.style(message, style_color))
            else:
                print(message)

    def _print_error(self, message: str) -> None:
        """Always print errors, even in quiet mode."""
        print(Colors.style(message, Colors.RED))

    def _update_spinner(self, msg: str = "") -> None:
        """Update spinner if active."""
        if not self.spinner_active:
            return
        now = time.time()
        if now - self.last_spin_time > 0.1:
            sys.stdout.write(f"\r{msg} {next(self.spinner)}")
            sys.stdout.flush()
            self.last_spin_time = now

    def _make_clickable(self, path: str) -> str:
        """Make a file path clickable in supported terminals using OSC 8."""
        file_url = f"file://{path.replace(os.sep, '/')}"
        return f"\033]8;;{file_url}\033\\{path}\033]8;;\033\\"

    def _is_git_repo(self, path: str) -> bool:
        """Check if path is a Git repository."""
        return is_git_repo(path)

    def _git_check_ignore(self, repo_path: str, relpaths: List[str]) -> Set[str]:
        """Use git check-ignore to determine ignored paths."""
        return git_check_ignore(repo_path, relpaths)

    def _find_repos(self) -> List[str]:
        """Find repos to process based on source directory."""
        # If source is itself a repo, return just its name
        if self._is_git_repo(self.source_dir):
            return [os.path.basename(self.source_dir)]

        # Otherwise, find all repos in the directory
        repos = []
        try:
            for entry in sorted(os.listdir(self.source_dir)):
                full_path = os.path.join(self.source_dir, entry)
                if os.path.isdir(full_path) and self._is_git_repo(full_path):
                    if self.only_repos and entry not in self.only_repos:
                        continue
                    repos.append(entry)
        except PermissionError:
            pass
        return repos

    def _should_exclude_dir(self, dirname: str) -> bool:
        """Check if a directory should be excluded."""
        for pattern in self.exclude_dirs:
            if fnmatch.fnmatch(dirname, pattern) or dirname == pattern:
                return True
        return False

    def _should_exclude_file(self, filename: str) -> bool:
        """Check if a file should be excluded."""
        for pattern in self.exclude_files:
            if fnmatch.fnmatch(filename, pattern):
                return True
        return False

    def _should_preserve(self, filename: str) -> bool:
        """Check if a file should be preserved (override exclusion)."""
        for pattern in PRESERVE_PATTERNS:
            if fnmatch.fnmatch(filename, pattern):
                return True
        return False

    def _matches_env_pattern(self, filename: str) -> bool:
        """Check if file matches env patterns."""
        for pattern in ENV_PATTERNS:
            if fnmatch.fnmatch(filename, pattern):
                return True
        return False

    def _matches_ext_filter(self, filename: str) -> bool:
        """Check if file matches extension filter."""
        if not self.ext_filter:
            return True
        ext = os.path.splitext(filename)[1].lower().lstrip(".")
        return ext in self.ext_filter

    def _scan_repo(
        self, repo_name: str, repo_path: str
    ) -> Tuple[List[Tuple[str, int]], Dict[str, int]]:
        """
        Scan a repository and return files to copy.
        Uses .gitignore for filtering when available.
        """
        files_to_copy: List[Tuple[str, int]] = []
        skipped_stats: Dict[str, int] = {}
        all_relpaths: List[str] = []

        # Phase 1: Walk and collect with eager pruning
        try:
            for dirpath, dirnames, filenames in os.walk(repo_path, topdown=True):
                self._update_spinner(f"Scanning {repo_name}")

                rel_dir = os.path.relpath(dirpath, repo_path)
                if rel_dir == ".":
                    rel_dir = ""

                # Eager prune excluded directories
                dirs_to_remove = []
                for d in dirnames:
                    if self._should_exclude_dir(d):
                        excluded_path = os.path.join(dirpath, d)
                        try:
                            count = sum(
                                len(files) for _, _, files in os.walk(excluded_path)
                            )
                            skipped_stats[d] = skipped_stats.get(d, 0) + count
                        except PermissionError:
                            skipped_stats[d] = skipped_stats.get(d, 0)
                        dirs_to_remove.append(d)

                for d in dirs_to_remove:
                    dirnames.remove(d)

                # Collect file paths
                for f in filenames:
                    rel_path = os.path.join(rel_dir, f) if rel_dir else f
                    all_relpaths.append(rel_path)

        except PermissionError as e:
            self._print(f"  {Colors.style('Warning:', Colors.YELLOW)} {e}")
            return files_to_copy, skipped_stats

        # Phase 2: Git filtering (skip if raw_mode)
        ignored_by_git: Set[str] = set()
        if not self.raw_mode and self._is_git_repo(repo_path):
            ignored_by_git = self._git_check_ignore(repo_path, all_relpaths)

        # Phase 3: Process files with all filters
        for rel_path in all_relpaths:
            filename = os.path.basename(rel_path)
            full_path = os.path.join(repo_path, rel_path)

            # Skip symlinks
            if os.path.islink(full_path):
                self.symlinks_skipped += 1
                continue

            try:
                file_size = os.path.getsize(full_path)
            except OSError:
                file_size = 0

            # Skip large files
            if self.max_size and file_size > self.max_size:
                self.large_files_skipped += 1
                if self.verbose:
                    size_mb = file_size / (1024 * 1024)
                    self._print(f"      Skipping large file ({size_mb:.1f} MB): {rel_path}")
                continue

            # Mode-specific filtering
            if self.env_only:
                # --env mode: only copy .env files
                if not self._matches_env_pattern(filename):
                    continue
            elif self.ext_filter:
                # --ext mode: only copy matching extensions
                if not self._matches_ext_filter(filename):
                    continue
            else:
                # Default mode: respect .gitignore but preserve special files
                if rel_path in ignored_by_git and not self._should_preserve(filename):
                    continue
                if self._should_exclude_file(filename) and not self._should_preserve(filename):
                    continue

            # Track preserved files
            if self._should_preserve(filename):
                self.preserved_files.append(f"{repo_name}/{rel_path}")

            files_to_copy.append((rel_path, file_size))

            # Track extension stats
            ext = os.path.splitext(filename)[1].lower() or "(no ext)"
            self.extension_stats[ext]["count"] += 1
            self.extension_stats[ext]["bytes"] += file_size

        return files_to_copy, skipped_stats

    def _on_walk_error(self, error: OSError) -> None:
        """Handle errors during os.walk."""
        if self.verbose:
            self._print(f"  {Colors.style('Warning:', Colors.YELLOW)} {error}")

    def _copy_repo(
        self, repo_name: str, repo_path: str, files_to_copy: List[Tuple[str, int]]
    ) -> int:
        """Copy files from repo to destination. Returns bytes copied."""
        dst_repo = os.path.join(self.dest_dir, repo_name)
        bytes_copied = 0

        for rel_path, file_size in files_to_copy:
            if self.was_interrupted:
                break

            src_file = os.path.join(repo_path, rel_path)
            dst_file = os.path.join(dst_repo, rel_path)

            try:
                dst_dir = os.path.dirname(dst_file)
                os.makedirs(dst_dir, exist_ok=True)

                if os.path.exists(dst_file):
                    if self.skip_existing:
                        self.files_skipped_existing += 1
                        if self.verbose:
                            self._print(
                                f"      {Colors.style('Skipped (exists):', Colors.GREY)} {rel_path}"
                            )
                        continue
                    self.files_overwritten += 1
                    if not self.force and not self.quiet:
                        self._print(
                            f"      {Colors.style('Overwriting:', Colors.YELLOW)} {rel_path}"
                        )

                shutil.copy2(src_file, dst_file)
                bytes_copied += file_size

                if self.verbose:
                    self._print(f"      {rel_path}")

            except (PermissionError, OSError) as e:
                self._print_error(f"  Warning: Could not copy {rel_path}: {e}")

        return bytes_copied

    def _zip_repo(
        self, repo_name: str, repo_path: str, files_to_copy: List[Tuple[str, int]]
    ) -> int:
        """Create a zip archive of the repo. Returns bytes of archive."""
        zip_path = os.path.join(self.dest_dir, f"{repo_name}.zip")

        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for rel_path, file_size in files_to_copy:
                    if self.was_interrupted:
                        break
                    # Normalize path and check for directory traversal attacks
                    normalized = os.path.normpath(rel_path)
                    if (
                        normalized.startswith("..")
                        or os.path.isabs(normalized)
                        or normalized.startswith(os.sep)
                    ):
                        self._print_error(f"  Skipping unsafe path: {rel_path}")
                        continue

                    src_file = os.path.join(repo_path, rel_path)
                    arc_name = os.path.join(repo_name, rel_path).replace("\\", "/")
                    zf.write(src_file, arc_name)

                    if self.verbose:
                        self._print(f"      {rel_path}")

            return os.path.getsize(zip_path)
        except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as e:
            self._print_error(f"  Warning: Could not create zip for {repo_name}: {e}")
            return 0

    def run(self) -> None:
        """Execute the migration."""
        self.start_time = time.time()
        self._print()

        # Determine if source is a single repo
        is_single_repo = self._is_git_repo(self.source_dir)

        # Find repos
        self.repos_found = self._find_repos()

        if not self.repos_found:
            self._print(f"No git repositories found in {self.source_dir}", Colors.YELLOW)
            return

        # Mode indicator
        mode_str = ""
        if self.env_only:
            mode_str = " (env files only)"
        elif self.ext_filter:
            mode_str = f" (*.{', *.'.join(self.ext_filter)} only)"
        elif self.raw_mode:
            mode_str = " (raw mode)"

        if is_single_repo:
            self._print(f"Copying repository{mode_str}")
        else:
            self._print(
                f"Detected {Colors.style(str(len(self.repos_found)), Colors.CYAN)} repositories{mode_str}"
            )
        self._print()

        # Setup spinner
        self.spinner_active = not self.quiet and sys.stdout.isatty()
        if self.spinner_active:
            sys.stdout.write(Colors.HIDE_CURSOR)

        try:
            for idx, repo_name in enumerate(self.repos_found, 1):
                if self.was_interrupted:
                    break

                self._print(
                    f"[{idx}/{len(self.repos_found)}] {Colors.style(repo_name + '/', Colors.BLUE)}"
                )

                # Get repo path (different for single vs multi repo mode)
                if is_single_repo:
                    repo_path = self.source_dir
                else:
                    repo_path = os.path.join(self.source_dir, repo_name)

                files_to_copy, skipped_stats = self._scan_repo(repo_name, repo_path)

                # Clear spinner line
                if self.spinner_active:
                    sys.stdout.write("\r" + " " * 50 + "\r")

                total_skipped = sum(skipped_stats.values())
                total_bytes = sum(size for _, size in files_to_copy)

                mode_label = "Zipping" if self.use_zip else "Copying"
                self._print(
                    f"      → {mode_label}: {Colors.style(str(len(files_to_copy)), Colors.GREEN)} files"
                )

                if skipped_stats and not self.env_only and not self.ext_filter:
                    skip_parts = [
                        f"{k}/ ({v:,})"
                        for k, v in sorted(skipped_stats.items(), key=lambda x: -x[1])[:5]
                    ]
                    self._print(
                        f"      → Skipping: {Colors.style(', '.join(skip_parts), Colors.GREY)}"
                    )

                if not self.dry_run:
                    if self.use_zip:
                        bytes_out = self._zip_repo(repo_name, repo_path, files_to_copy)
                    else:
                        bytes_out = self._copy_repo(repo_name, repo_path, files_to_copy)
                    self.total_bytes_copied += bytes_out
                else:
                    self.total_bytes_copied += total_bytes

                self.total_files_copied += len(files_to_copy)
                self.total_files_skipped += total_skipped
                self._print()

        except KeyboardInterrupt:
            self.was_interrupted = True
            self._print()
            self._print(Colors.style("⚠ Migration interrupted.", Colors.YELLOW))

        finally:
            if self.spinner_active:
                sys.stdout.write(Colors.SHOW_CURSOR)

        self._print_summary()

    def _print_summary(self) -> None:
        """Print final summary."""
        elapsed = time.time() - self.start_time
        sep = "─" * 50
        self._print(sep)

        if self.was_interrupted:
            self._print(Colors.style("INTERRUPTED", Colors.YELLOW) + " — partial results")
        elif self.dry_run:
            self._print(Colors.style("DRY RUN COMPLETE", Colors.YELLOW) + " (no files copied)")
            self._print(
                f"Would copy: {Colors.style(f'{self.total_files_copied:,}', Colors.GREEN)} files across {len(self.repos_found)} repos"
            )
            if self.total_files_skipped > 0:
                self._print(
                    f"Would skip: ~{Colors.style(f'{self.total_files_skipped:,}', Colors.GREY)} dependency/cache files"
                )
        else:
            mode = "ZIPPED" if self.use_zip else "COPIED"
            self._print(Colors.style(f"MIGRATION COMPLETE ({mode})", Colors.GREEN))
            self._print(
                f"Copied: {Colors.style(f'{self.total_files_copied:,}', Colors.GREEN)} files across {len(self.repos_found)} repos"
            )
            if self.total_files_skipped > 0:
                self._print(
                    f"Skipped: ~{Colors.style(f'{self.total_files_skipped:,}', Colors.GREY)} dependency/cache files"
                )

            if self.total_bytes_copied > 0:
                size_mb = self.total_bytes_copied / (1024 * 1024)
                self._print(f"Total size: {Colors.style(f'{size_mb:.2f} MB', Colors.CYAN)}")

            self._print(
                f"\nDestination: {Colors.style(self._make_clickable(self.dest_dir), Colors.BLUE)}"
            )

        # Show preserved files
        if self.preserved_files and not self.env_only:
            self._print(
                f"\nPreserved configs: {Colors.style(str(len(self.preserved_files)), Colors.GREEN)} files (.env, .gitignore)"
            )
            if self.verbose:
                for pf in self.preserved_files[:10]:
                    self._print(f"  • {pf}")
                if len(self.preserved_files) > 10:
                    self._print(f"  ... and {len(self.preserved_files) - 10} more")

        # Additional stats
        if self.symlinks_skipped > 0:
            self._print(f"Symlinks skipped: {Colors.style(str(self.symlinks_skipped), Colors.GREY)}")
        if self.large_files_skipped > 0:
            self._print(f"Large files skipped: {Colors.style(str(self.large_files_skipped), Colors.GREY)}")
        if self.files_overwritten > 0:
            self._print(f"Files overwritten: {Colors.style(str(self.files_overwritten), Colors.YELLOW)}")
        if self.files_skipped_existing > 0:
            self._print(f"Files skipped (existing): {Colors.style(str(self.files_skipped_existing), Colors.GREY)}")

        self._print(f"\nCompleted in {Colors.style(f'{elapsed:.2f}s', Colors.CYAN)}")

        if self.show_stats and self.extension_stats:
            self._print_stats()

        self._print()

    def _print_stats(self) -> None:
        """Print detailed file type breakdown."""
        self._print()
        self._print(Colors.style("─" * 50, Colors.WHITE))
        self._print(Colors.style("FILE TYPE BREAKDOWN", Colors.CYAN))
        self._print(Colors.style("─" * 50, Colors.WHITE))

        sorted_stats = sorted(
            self.extension_stats.items(), key=lambda x: x[1]["count"], reverse=True
        )

        if not self.stats_all:
            sorted_stats = sorted_stats[:15]

        self._print(f"{'Extension':<15} {'Files':>10} {'Size':>12}")
        self._print("-" * 40)

        for ext, stats in sorted_stats:
            size_kb = stats["bytes"] / 1024
            if size_kb > 1024:
                size_str = f"{size_kb / 1024:.1f} MB"
            else:
                size_str = f"{size_kb:.1f} KB"
            self._print(f"{ext:<15} {stats['count']:>10,} {size_str:>12}")
