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
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from gtrmrs.core.colors import Colors
from gtrmrs.core.patterns import EXCLUDE_DIRS, EXCLUDE_FILE_PATTERNS, PRESERVE_PATTERNS
from gtrmrs.core.git_utils import is_git_repo, git_check_ignore
from gtrmrs.core.scan_filter import ScanFilter

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
        check_git_size: bool = False,
        default_dir_excludes: bool = True,
        use_color: Optional[bool] = None,
    ):
        self.source_dir = os.path.realpath(os.path.abspath(source_dir))
        self.dest_dir = os.path.realpath(os.path.abspath(dest_dir))
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
        self.check_git_size = check_git_size
        self.default_dir_excludes = default_dir_excludes
        self.use_color = sys.stdout.isatty() if use_color is None else use_color

        # Merge excludes
        self.exclude_dirs = list(EXCLUDE_DIRS)
        self.exclude_files = list(EXCLUDE_FILE_PATTERNS)
        self.exclude_files.extend(["*.jks", "*.keystore"])
        self.explicit_file_excludes: List[str] = []
        self.explicit_dir_excludes: List[str] = []

        if extra_excludes:
            for pattern in extra_excludes:
                pattern = pattern.strip()
                if pattern.endswith("/"):
                    self.exclude_dirs.append(pattern.rstrip("/"))
                    self.explicit_dir_excludes.append(pattern.rstrip("/"))
                else:
                    self.exclude_files.append(pattern)
                    self.explicit_file_excludes.append(pattern)

        # Remove .git from exclusions if --include-git
        if self.include_git and ".git" in self.exclude_dirs:
            self.exclude_dirs.remove(".git")

        # Stats
        self.repos_found: List[str] = []
        self.total_files_copied = 0
        self.total_dirs_skipped = 0
        self.total_bytes_copied = 0
        self.preserved_files: List[str] = []
        self.symlinks_skipped = 0
        self.large_files_skipped = 0
        self.files_overwritten = 0
        self.files_skipped_existing = 0
        self.archives_skipped_existing = 0
        self.errors: List[str] = []
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

    def _style(self, text: str, color: str, enabled: bool = True) -> str:
        return Colors.style(text, color, enabled and self.use_color)

    def _print(self, message: str = "", style_color: str = None) -> None:
        """Print message unless in quiet mode."""
        if not self.quiet:
            if style_color:
                print(self._style(message, style_color))
            else:
                print(message)

    def _print_error(self, message: str) -> None:
        """Always print errors, even in quiet mode."""
        self.errors.append(message)
        print(self._style(message, Colors.RED, sys.stderr.isatty()), file=sys.stderr)

    @staticmethod
    def _is_link(path: str) -> bool:
        info = os.lstat(path)
        return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)

    @staticmethod
    def _within(path: str, root: str) -> bool:
        try:
            return os.path.commonpath([os.path.normcase(path), os.path.normcase(root)]) == os.path.normcase(root)
        except ValueError:
            return False

    def _safe_destination(self, *parts: str) -> str:
        """Check the resolved boundary and reject links below the chosen destination."""
        path = os.path.abspath(os.path.join(self.dest_dir, *parts))
        if not self._within(path, self.dest_dir):
            raise OSError("Destination escaped the selected directory")
        current = self.dest_dir
        paths = [current]
        for part in os.path.relpath(path, self.dest_dir).split(os.sep):
            current = os.path.join(current, part)
            paths.append(current)
        for current in paths:
            if os.path.lexists(current) and self._is_link(current):
                raise OSError("Destination contains a link or junction: " + current)
        resolved = os.path.realpath(path)
        if not self._within(resolved, self.dest_dir) or os.path.normcase(os.path.realpath(self.dest_dir)) != os.path.normcase(self.dest_dir):
            raise OSError("Destination directory changed or escaped its boundary")
        if self._within(resolved, self.source_dir):
            raise OSError("Destination cannot overlap the source directory")
        return path

    def _source_file(self, repo_path: str, rel_path: str) -> str:
        path = os.path.abspath(os.path.join(repo_path, rel_path))
        if not self._within(path, repo_path) or not self._within(os.path.realpath(path), os.path.realpath(repo_path)):
            raise OSError("Source file escaped the repository: " + rel_path)
        if self._is_link(path) or not stat.S_ISREG(os.lstat(path).st_mode):
            raise OSError("Source is not a regular file: " + rel_path)
        return path

    def _update_spinner(self, msg: str = "") -> None:
        """Update spinner if active."""
        if not self.spinner_active:
            return
        now = time.time()
        if now - self.last_spin_time > 0.1:
            sys.stdout.write(f"\r{msg} {next(self.spinner)}")
            sys.stdout.flush()
            self.last_spin_time = now

    def _get_dir_size(self, path: str) -> int:
        """Calculate total size of a directory."""
        total = 0
        try:
            for dirpath, _, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    try:
                        total += os.path.getsize(fp)
                    except OSError:
                        pass
        except OSError:
            pass
        return total

    def _make_clickable(self, path: str) -> str:
        """Make a file path clickable in supported terminals using OSC 8."""
        if not self.use_color:
            return path
        file_url = Path(os.path.abspath(path)).as_uri()
        return f"\033]8;;{file_url}\033\\{path}\033]8;;\033\\"

    def _is_git_repo(self, path: str) -> bool:
        """Check if path is a Git repository."""
        return is_git_repo(path)

    def _git_check_ignore(self, repo_path: str, relpaths: List[str]) -> Set[str]:
        """Use git check-ignore to determine ignored paths."""
        return git_check_ignore(repo_path, relpaths, strict=True)

    def _find_repos(self) -> List[str]:
        """Find repos to process based on source directory."""
        # If source is itself a repo, return just its name
        if self._is_git_repo(self.source_dir):
            name = os.path.basename(self.source_dir)
            return [name] if not self.only_repos or name in self.only_repos else []

        # Otherwise, find all repos in the directory
        repos = []
        try:
            for entry in sorted(os.listdir(self.source_dir)):
                full_path = os.path.join(self.source_dir, entry)
                if self._is_link(full_path):
                    self.symlinks_skipped += 1
                    continue
                if os.path.isdir(full_path) and self._is_git_repo(full_path):
                    if self.only_repos and entry not in self.only_repos:
                        continue
                    repos.append(entry)
        except OSError as exc:
            self._on_walk_error(exc)
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
        policy = ScanFilter(
            repo_path, raw_mode=self.raw_mode, default_dir_excludes=self.default_dir_excludes,
            extra_excludes=self.explicit_dir_excludes, include_git=self.include_git, defaults_in_raw=True,
        )
        policy.check_ignore = self._git_check_ignore

        # Phase 1: Walk and collect with eager pruning
        try:
            for dirpath, dirnames, filenames in os.walk(repo_path, topdown=True, onerror=self._on_walk_error):
                self._update_spinner(f"Scanning {repo_name}")

                rel_dir = os.path.relpath(dirpath, repo_path)
                if rel_dir == ".":
                    rel_dir = ""

                # Eager prune excluded directories
                active_dirs = []
                candidates = [os.path.join(rel_dir, d) + os.sep for d in dirnames
                              if not self._is_link(os.path.join(dirpath, d))]
                # Preserve the ability to find .env configs inside ignored folders.
                # Default cache/dependency directories are still pruned eagerly.
                excluded = policy.ignored(candidates, apply_ignore_rules=False)
                for d in dirnames:
                    directory = os.path.join(dirpath, d)
                    if self._is_link(directory):
                        self.symlinks_skipped += 1
                        continue
                    if os.path.join(rel_dir, d) + os.sep in excluded:
                        skipped_stats[d] = skipped_stats.get(d, 0) + 1
                    else:
                        active_dirs.append(d)
                dirnames[:] = active_dirs

                # Collect file paths
                for f in filenames:
                    if f == ".git" and self.include_git:
                        self._print_error("Cannot include external Git metadata from a worktree/submodule .git file; omit --include-git")
                        return [], skipped_stats
                    rel_path = os.path.join(rel_dir, f) if rel_dir else f
                    all_relpaths.append(rel_path)

        except (OSError, RuntimeError) as e:
            self._on_walk_error(e)
            return files_to_copy, skipped_stats

        # Phase 2: Git filtering (skip if raw_mode)
        ignored_by_git: Set[str] = set()
        try:
            ignored_by_git = policy.ignored(all_relpaths)
        except (RuntimeError, OSError) as exc:
            self._print_error("Could not verify ignored files in {}: {}".format(repo_name, exc))
            return [], skipped_stats

        # Phase 3: Process files with all filters
        for rel_path in all_relpaths:
            filename = os.path.basename(rel_path)
            full_path = os.path.join(repo_path, rel_path)

            try:
                if self._is_link(full_path):
                    self.symlinks_skipped += 1
                    continue
                full_path = self._source_file(repo_path, rel_path)
                file_size = os.path.getsize(full_path)
            except OSError as exc:
                self._print_error("Could not inspect {}: {}".format(rel_path, exc))
                continue

            # Skip large files
            if self.max_size and file_size > self.max_size:
                self.large_files_skipped += 1
                if self.verbose:
                    size_mb = file_size / (1024 * 1024)
                    self._print(f"      Skipping large file ({size_mb:.1f} MB): {rel_path}")
                continue

            # Explicit exclusions always win, including over preserved configurations.
            if any(fnmatch.fnmatch(filename, pattern) for pattern in self.explicit_file_excludes):
                continue
            if self._should_exclude_file(filename) and not self._should_preserve(filename):
                continue
            if rel_path in ignored_by_git and not self._should_preserve(filename) and not self.env_only:
                continue

            # Selection narrows the safely filtered file list.
            if self.env_only:
                # --env mode: only copy .env files
                if not self._matches_env_pattern(filename):
                    continue
            elif self.ext_filter:
                # --ext mode: only copy matching extensions
                if not self._matches_ext_filter(filename):
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
        self._print_error("Could not scan source directory: {}".format(error))

    def _copy_repo(
        self, repo_name: str, repo_path: str, files_to_copy: List[Tuple[str, int]]
    ) -> int:
        """Copy files from repo to destination. Returns bytes copied."""
        bytes_copied = 0

        for rel_path, file_size in files_to_copy:
            if self.was_interrupted:
                break

            temporary = None
            try:
                src_file = self._source_file(repo_path, rel_path)
                dst_file = self._safe_destination(repo_name, rel_path)
                dst_dir = os.path.dirname(dst_file)
                existed = os.path.exists(dst_file)
                if os.path.exists(dst_file):
                    if not os.path.isfile(dst_file) or os.path.samefile(src_file, dst_file):
                        raise OSError("Destination is not a distinct regular file")
                    if self.skip_existing:
                        self.files_skipped_existing += 1
                        if self.verbose:
                            self._print(
                                f"      {self._style('Skipped (exists):', Colors.GREY)} {rel_path}"
                            )
                        continue
                    if not self.force and not self.quiet:
                        self._print(
                            f"      {self._style('Overwriting:', Colors.YELLOW)} {rel_path}"
                        )

                if not self.dry_run:
                    os.makedirs(dst_dir, exist_ok=True)
                    self._safe_destination(repo_name, rel_path)
                    descriptor, temporary = tempfile.mkstemp(prefix=".gitmig-", dir=dst_dir)
                    os.close(descriptor)
                    shutil.copy2(src_file, temporary)
                    self._safe_destination(repo_name, rel_path)
                    os.replace(temporary, dst_file)
                    temporary = None
                self.total_files_copied += 1
                if existed:
                    self.files_overwritten += 1
                bytes_copied += file_size

                if self.verbose:
                    self._print(f"      {rel_path}")

            except (PermissionError, OSError) as e:
                self._print_error(f"  Warning: Could not copy {rel_path}: {e}")
            finally:
                if temporary is not None:
                    self._discard_temporary(temporary)

        return bytes_copied

    def _zip_repo(
        self, repo_name: str, repo_path: str, files_to_copy: List[Tuple[str, int]]
    ) -> int:
        """Create a zip archive of the repo. Returns bytes of archive."""
        temporary = None
        try:
            zip_path = self._safe_destination(f"{repo_name}.zip")
            existed = os.path.exists(zip_path)
            if existed and not os.path.isfile(zip_path):
                raise OSError("Archive destination is not a regular file")
            if existed and self.skip_existing:
                self.archives_skipped_existing += 1
                return 0
            if existed and not self.force:
                self._print("      Overwriting archive: " + zip_path)
            if self.dry_run:
                for rel_path, _ in files_to_copy:
                    self._source_file(repo_path, rel_path)
                self.total_files_copied += len(files_to_copy)
                return sum(size for _, size in files_to_copy)
            os.makedirs(self.dest_dir, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".gitmig-", suffix=".zip", dir=self.dest_dir)
            os.close(descriptor)
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as zf:
                for rel_path, file_size in files_to_copy:
                    if self.was_interrupted:
                        raise OSError("Archive creation was interrupted")
                    # Normalize path and check for directory traversal attacks
                    normalized = os.path.normpath(rel_path)
                    if (
                        ".." in normalized.split(os.sep)
                        or os.path.isabs(normalized)
                        or normalized.startswith(os.sep)
                    ):
                        raise OSError("Unsafe archive path: " + rel_path)

                    src_file = self._source_file(repo_path, rel_path)
                    arc_name = os.path.join(repo_name, rel_path).replace("\\", "/")
                    zf.write(src_file, arc_name)

                    if self.verbose:
                        self._print(f"      {rel_path}")

            self._safe_destination(f"{repo_name}.zip")
            size = os.path.getsize(temporary)
            os.replace(temporary, zip_path)
            temporary = None
            self.total_files_copied += len(files_to_copy)
            if existed:
                self.files_overwritten += 1
            return size
        except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as e:
            self._print_error(f"  Warning: Could not create zip for {repo_name}: {e}")
            return 0
        finally:
            if temporary is not None:
                self._discard_temporary(temporary)

    def _discard_temporary(self, path: str) -> None:
        try:
            os.unlink(path)
        except OSError as exc:
            self._print_error("Could not remove temporary file {}: {}".format(path, exc))

    def run(self) -> bool:
        """Execute the migration."""
        self.start_time = time.time()
        self._print()

        # Determine if source is a single repo
        is_single_repo = self._is_git_repo(self.source_dir)

        # Find repos
        self.repos_found = self._find_repos()

        if not self.repos_found:
            self._print_error(f"No matching git repositories found in {self.source_dir}")
            return False

        # Mode indicator
        mode_str = ""
        if self.env_only:
            mode_str = " (env files only)"
        elif self.ext_filter:
            mode_str = f" (*.{', *.'.join(self.ext_filter)} only)"
        elif self.raw_mode:
            mode_str = " (raw mode)"

        # Special mode: check .git size
        if self.check_git_size:
            self._print("Calculating .git folder sizes...")
            self._print()

            git_sizes = []
            total_git_size = 0

            for _, repo_name in enumerate(self.repos_found, 1):
                if is_single_repo:
                    repo_path = self.source_dir
                else:
                    repo_path = os.path.join(self.source_dir, repo_name)

                git_dir = os.path.join(repo_path, ".git")
                if os.path.isdir(git_dir):
                    size = self._get_dir_size(git_dir)
                    git_sizes.append((repo_name, size))
                    total_git_size += size
                else:
                    git_sizes.append((repo_name, 0)) # Should not happen if _is_git_repo checked out

            # Sort by size descending
            git_sizes.sort(key=lambda x: x[1], reverse=True)

            # Print Table
            # Dynamic width calculation
            max_name_len = len("Repository")
            for name, _ in git_sizes:
                max_name_len = max(max_name_len, len(name))

            # Cap at reasonable limits
            col1_width = max(30, min(max_name_len + 2, 60))
            col2_width = 15
            total_width = col1_width + col2_width + 1 # +1 for space

            fmt = f"{{:<{col1_width}}} {{:>{col2_width}}}"
            sep = "=" * total_width
            thin_sep = "-" * total_width

            self._print()
            self._print(sep)
            self._print(self._style(fmt.format("Repository", "Size"), Colors.BOLD))
            self._print(thin_sep)

            for name, size in git_sizes:
                size_mb = size / (1024 * 1024)
                if size_mb >= 1024:
                    size_str = f"{size_mb / 1024:.2f} GB"
                elif size_mb >= 1:
                    size_str = f"{size_mb:.2f} MB"
                else:
                    size_str = f"{size / 1024:.2f} KB"

                # Colorize logic based on size
                # > 1024 MB (1 GiB): Red + Bold (Critical)
                # > 500 MB: Red
                # > 200 MB: Magenta
                # > 100 MB: Yellow
                # > 50 MB: Cyan
                # > 10 MB: Blue
                # <= 10 MB: White (default)

                col = Colors.WHITE
                if size_mb > 1024:
                    col = Colors.RED + Colors.BOLD
                elif size_mb > 500:
                    col = Colors.RED
                elif size_mb > 200:
                    col = Colors.MAGENTA
                elif size_mb > 100:
                    col = Colors.YELLOW
                elif size_mb > 50:
                    col = Colors.CYAN
                elif size_mb > 10:
                    col = Colors.BLUE

                # Apply color to the Size column only, or the whole line?
                # Let's color the Size column specifically to make it pop,
                # but we need to format the string carefully.
                # Actually, let's color the whole line for better visibility in the table.

                line_content = fmt.format(name, size_str)
                self._print(self._style(line_content, col))

            self._print(thin_sep)

            total_mb = total_git_size / (1024 * 1024)
            if total_mb >= 1024:
                total_str = f"{total_mb / 1024:.2f} GB"
            elif total_mb >= 1:
                total_str = f"{total_mb:.2f} MB"
            else:
                total_str = f"{total_git_size / 1024:.2f} KB"

            self._print(self._style(fmt.format("TOTAL", total_str), Colors.BOLD))
            self._print(sep)
            self._print(f"Processed {len(git_sizes)} repositories.")
            self._print()

            return not self.errors

        if is_single_repo:
            self._print(f"Copying repository{mode_str}")
        else:
            self._print(
                f"Detected {self._style(str(len(self.repos_found)), Colors.CYAN)} repositories{mode_str}"
            )
        self._print()

        # Setup spinner
        self.spinner_active = not self.quiet and self.use_color and sys.stdout.isatty()
        if self.spinner_active:
            sys.stdout.write(Colors.HIDE_CURSOR)

        try:
            for idx, repo_name in enumerate(self.repos_found, 1):
                if self.was_interrupted:
                    break

                self._print(
                    f"[{idx}/{len(self.repos_found)}] {self._style(repo_name + '/', Colors.BLUE)}"
                )

                # Get repo path (different for single vs multi repo mode)
                if is_single_repo:
                    repo_path = self.source_dir
                else:
                    repo_path = os.path.join(self.source_dir, repo_name)

                errors_before_scan = len(self.errors)
                files_to_copy, skipped_stats = self._scan_repo(repo_name, repo_path)
                if len(self.errors) != errors_before_scan:
                    continue

                # Clear spinner line
                if self.spinner_active:
                    sys.stdout.write("\r" + " " * 50 + "\r")

                total_skipped = sum(skipped_stats.values())

                mode_label = "Zipping" if self.use_zip else "Copying"
                self._print(
                    f"      → {mode_label}: {self._style(str(len(files_to_copy)), Colors.GREEN)} files"
                )

                if skipped_stats and not self.env_only and not self.ext_filter:
                    skip_parts = [
                        f"{k}/ ({v:,} dirs)"
                        for k, v in sorted(skipped_stats.items(), key=lambda x: -x[1])[:5]
                    ]
                    self._print(
                        f"      → Skipping: {self._style(', '.join(skip_parts), Colors.GREY)}"
                    )

                if self.use_zip:
                    bytes_out = self._zip_repo(repo_name, repo_path, files_to_copy)
                else:
                    bytes_out = self._copy_repo(repo_name, repo_path, files_to_copy)
                self.total_bytes_copied += bytes_out

                self.total_dirs_skipped += total_skipped
                self._print()

        except KeyboardInterrupt:
            self.was_interrupted = True
            self._print()
            self._print(self._style("⚠ Migration interrupted.", Colors.YELLOW))

        finally:
            if self.spinner_active:
                sys.stdout.write(Colors.SHOW_CURSOR)

        self._print_summary()
        return not self.errors and not self.was_interrupted

    def _print_summary(self) -> None:
        """Print final summary."""
        elapsed = time.time() - self.start_time
        sep = "─" * 50
        self._print(sep)

        if self.was_interrupted:
            self._print(self._style("INTERRUPTED", Colors.YELLOW) + " - partial results")
        elif self.errors:
            self._print(self._style("MIGRATION INCOMPLETE", Colors.RED))
            self._print("Copied: {:,} files; {} errors.".format(self.total_files_copied, len(self.errors)))
        elif self.dry_run:
            self._print(self._style("DRY RUN COMPLETE", Colors.YELLOW) + " (no files copied)")
            self._print(
                f"Would copy: {self._style(f'{self.total_files_copied:,}', Colors.GREEN)} files across {len(self.repos_found)} repos"
            )
            if self.total_dirs_skipped > 0:
                self._print(
                    f"Would skip: {self._style(f'{self.total_dirs_skipped:,}', Colors.GREY)} dependency/cache directories"
                )
        else:
            mode = "ZIPPED" if self.use_zip else "COPIED"
            self._print(self._style(f"MIGRATION COMPLETE ({mode})", Colors.GREEN))
            self._print(
                f"Copied: {self._style(f'{self.total_files_copied:,}', Colors.GREEN)} files across {len(self.repos_found)} repos"
            )
            if self.total_dirs_skipped > 0:
                self._print(
                    f"Skipped: {self._style(f'{self.total_dirs_skipped:,}', Colors.GREY)} dependency/cache directories"
                )

            if self.total_bytes_copied > 0:
                size_mb = self.total_bytes_copied / (1024 * 1024)
                self._print(f"Total size: {self._style(f'{size_mb:.2f} MB', Colors.CYAN)}")

            self._print(
                f"\nDestination: {self._style(self._make_clickable(self.dest_dir), Colors.BLUE)}"
            )

        # Show preserved files
        if self.preserved_files and not self.env_only:
            self._print(
                f"\nPreserved configs: {self._style(str(len(self.preserved_files)), Colors.GREEN)} files (.env, .gitignore)"
            )
            if self.verbose:
                for pf in self.preserved_files[:10]:
                    self._print(f"  • {pf}")
                if len(self.preserved_files) > 10:
                    self._print(f"  ... and {len(self.preserved_files) - 10} more")

        # Additional stats
        if self.symlinks_skipped > 0:
            self._print(f"Symlinks skipped: {self._style(str(self.symlinks_skipped), Colors.GREY)}")
        if self.large_files_skipped > 0:
            self._print(f"Large files skipped: {self._style(str(self.large_files_skipped), Colors.GREY)}")
        if self.files_overwritten > 0:
            self._print(f"Files overwritten: {self._style(str(self.files_overwritten), Colors.YELLOW)}")
        if self.files_skipped_existing > 0:
            self._print(f"Files skipped (existing): {self._style(str(self.files_skipped_existing), Colors.GREY)}")
        if self.archives_skipped_existing > 0:
            self._print("Archives skipped (existing): {}".format(self.archives_skipped_existing))

        self._print(f"\nCompleted in {self._style(f'{elapsed:.2f}s', Colors.CYAN)}")

        if self.show_stats and self.extension_stats:
            self._print_stats()

        self._print()

    def _print_stats(self) -> None:
        """Print detailed file type breakdown."""
        self._print()
        self._print(self._style("─" * 50, Colors.WHITE))
        self._print(self._style("SELECTED FILE TYPE BREAKDOWN", Colors.CYAN))
        self._print(self._style("─" * 50, Colors.WHITE))

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
