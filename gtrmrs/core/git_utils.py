"""
git_utils.py

Git-aware scanning utilities.
Provides the 2-phase hybrid scanning logic shared by rtree, locr, and gitmig:
  Phase 1: Eager pruning of heavy folders (node_modules, venv, etc.)
  Phase 2: Git check-ignore for precision filtering
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
from functools import lru_cache
from typing import Callable, List, Optional, Set, Tuple

from gtrmrs.core.patterns import EXCLUDE_DIRS


def find_git_root(path: str) -> Optional[str]:
    """Find the root of the Git repository containing path, or None."""
    curr = os.path.abspath(path)
    while True:
        marker = os.path.join(curr, ".git")
        if os.path.isdir(marker):
            return curr
        if os.path.isfile(marker):
            try:
                with open(marker, encoding="utf-8") as handle:
                    value = handle.readline().strip()
                if value.startswith("gitdir: ") and os.path.isdir(os.path.join(curr, value[8:])):
                    return curr
            except (OSError, UnicodeError):
                pass
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent
    return None


def is_git_repo(path: str) -> bool:
    """Check if the given path is inside a Git repository."""
    return find_git_root(path) is not None


def git_check_ignore(repo_path: str, relpaths: List[str], strict: bool = True) -> Set[str]:
    """
    Use `git check-ignore` to determine which paths are ignored.

    Args:
        repo_path: Root of the Git repository
        relpaths: List of relative paths to check
        strict: Raise RuntimeError if Git cannot verify every supplied path

    Returns:
        Set of relative paths that are ignored by Git
    """
    if not relpaths:
        return set()

    # NUL is the only unsupported character in the NUL-delimited protocol.
    safe_paths = [p for p in relpaths if "\0" not in p]

    if strict and len(safe_paths) != len(relpaths):
        raise RuntimeError("Git ignore check received an unsupported path")

    if not safe_paths:
        return set()

    try:
        # Use null-delimited protocol (-z) for safer parsing
        input_bytes = os.fsencode("\0".join(safe_paths) + "\0")
        proc = subprocess.run(
            ["git", "check-ignore", "--stdin", "-z"],
            input=input_bytes,
            capture_output=True,
            cwd=repo_path,
            timeout=30,
        )
        if proc.returncode not in (0, 1):
            if strict:
                raise RuntimeError(proc.stderr.decode("utf-8", errors="replace").strip() or "Git ignore check failed")
            return set()
        if not proc.stdout:
            return set()
        parts = [os.fsdecode(p) for p in proc.stdout.split(b"\0") if p]
        return set(parts)
    except (subprocess.SubprocessError, OSError, UnicodeError) as exc:
        if strict:
            raise RuntimeError("Git ignore check failed: {}".format(exc)) from exc
        # Git not available or error occurred
        return set()


def compile_gitignore_patterns(gitignore_path: str) -> List[Tuple[str, bool, bool]]:
    """
    Parse a .gitignore file and compile patterns.

    Returns:
        List of tuples: (pattern, is_negation, is_dir_only)
    """
    patterns = []

    if not os.path.isfile(gitignore_path):
        return patterns

    try:
        with open(gitignore_path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.rstrip("\r\n")
                # Git discards unescaped trailing spaces, not leading spaces.
                while line.endswith(" "):
                    escapes = len(line[:-1]) - len(line[:-1].rstrip("\\"))
                    if escapes % 2:
                        break
                    line = line[:-1]

                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                is_negation = line.startswith("!")
                if is_negation:
                    line = line[1:]

                is_dir_only = line.endswith("/")
                if is_dir_only:
                    line = line[:-1]

                patterns.append((line, is_negation, is_dir_only))
    except (OSError, UnicodeError) as exc:
        raise OSError("Could not read ignore rules from {}: {}".format(gitignore_path, exc)) from exc

    return patterns


def simple_gitignore_match(
    relpath: str,
    patterns: List[Tuple[str, bool, bool]],
    is_dir: bool = False
) -> bool:
    """
    Simple gitignore pattern matching (fallback when Git is not available).

    Args:
        relpath: Relative path to check
        patterns: Compiled gitignore patterns
        is_dir: Whether the path is a directory

    Returns:
        True if the path should be ignored
    """
    parts = relpath.replace(os.sep, "/").strip("/").split("/")
    for end in range(1, len(parts) + 1):
        path = "/".join(parts[:end])
        directory = end < len(parts) or is_dir
        ignored = False
        for pattern, negated, dir_only in patterns:
            if (not dir_only or directory) and _match_ignore_pattern(path, pattern):
                ignored = not negated
        # A child cannot be restored while its parent remains excluded.
        if ignored:
            return True
    return False


def _match_ignore_pattern(path: str, pattern: str) -> bool:
    """Match a scope-relative Git-style glob without OS case folding."""
    anchored = pattern.startswith("/")
    pattern = pattern.lstrip("/")

    def segment_matches(value: str, glob: str) -> bool:
        escaped = []
        index = 0
        while index < len(glob):
            char = glob[index]
            if char == "\\" and index + 1 < len(glob):
                index += 1
                char = glob[index]
                escaped.append({"*": "[*]", "?": "[?]", "[": "[[]", "]": "[]]"}.get(char, char))
            else:
                escaped.append(char)
            index += 1
        return fnmatch.fnmatchcase(value, "".join(escaped))

    if not anchored and "/" not in pattern:
        return segment_matches(path.rsplit("/", 1)[-1], pattern)
    values, globs = path.split("/"), pattern.split("/")

    @lru_cache(maxsize=None)
    def matches(i: int, j: int) -> bool:
        if j == len(globs):
            return i == len(values)
        if globs[j] == "**":
            if j == len(globs) - 1 and j > 0:
                return i < len(values)
            return matches(i, j + 1) or (i < len(values) and matches(i + 1, j))
        return i < len(values) and segment_matches(values[i], globs[j]) and matches(i + 1, j + 1)

    return matches(0, 0)


def should_eager_prune(dirname: str, extra_excludes: Optional[List[str]] = None) -> bool:
    """
    Check if a directory should be eagerly pruned (skipped before Git check).

    Args:
        dirname: Name of the directory (not full path)
        extra_excludes: Additional patterns to exclude

    Returns:
        True if the directory should be skipped entirely
    """
    # Check against default exclude patterns
    for pattern in EXCLUDE_DIRS:
        if fnmatch.fnmatch(dirname, pattern):
            return True

    # Check against extra excludes
    if extra_excludes:
        for pattern in extra_excludes:
            # Handle both "dir/" and "dir" patterns
            clean_pattern = pattern.rstrip("/")
            if fnmatch.fnmatch(dirname, clean_pattern):
                return True

    return False


def collect_files_with_pruning(
    root: str,
    raw_mode: bool = False,
    extra_excludes: Optional[List[str]] = None,
    max_depth: int = -1,
    callback: Optional[Callable[[str], None]] = None,
    default_dir_excludes: bool = True,
) -> Tuple[List[str], Set[str]]:
    """Collect paths, pruning ignored directories before visiting their contents.

    Git repositories use Git for ignore rules and tracked-source protection.
    Plain folders use scoped basic Git-style rules. Raw mode bypasses both
    ignore rules and defaults; explicit extra exclusions still apply.
    """
    from gtrmrs.core.scan_filter import ScanFilter

    root = os.path.abspath(root)
    policy = ScanFilter(root, raw_mode, default_dir_excludes, extra_excludes)
    paths: List[str] = []
    files: List[str] = []

    def failed(error: OSError) -> None:
        raise error

    for directory, dirs, names in os.walk(root, topdown=True, onerror=failed):
        if callback:
            callback(directory)
        relative = os.path.relpath(directory, root)
        depth = 0 if relative == "." else relative.count(os.sep) + 1
        if max_depth >= 0 and depth >= max_depth:
            dirs.clear()
            continue
        relative = "" if relative == "." else relative
        candidates = [os.path.join(relative, name) + os.sep for name in dirs]
        ignored = policy.ignored(candidates)
        dirs[:] = [name for name, path in zip(dirs, candidates) if path not in ignored]
        paths.extend(path for path in candidates if path not in ignored)
        files.extend(os.path.join(relative, name) for name in names)
    ignored = policy.ignored(files)
    paths.extend(files)
    return paths, ignored
