"""Shared scan filtering with Git authority and scoped plain-folder rules."""

from __future__ import annotations

import fnmatch
import os
import subprocess
from typing import Dict, List, Optional, Set

from gtrmrs.core.git_utils import (
    _match_ignore_pattern, compile_gitignore_patterns, find_git_root, git_check_ignore,
)
from gtrmrs.core.patterns import EXCLUDE_DIRS


class ScanFilter:
    """Filter paths in batches while protecting indexed source from defaults.

    Explicit exclusions and metadata hiding take precedence over tracked paths.
    Raw mode can optionally retain directory defaults for migration.
    """

    def __init__(self, root: str, raw_mode: bool = False,
                 default_dir_excludes: bool = True, extra_excludes: Optional[List[str]] = None,
                 include_git: bool = False, defaults_in_raw: bool = False):
        self.root = os.path.abspath(root)
        self.raw_mode = raw_mode
        self.default_dir_excludes = default_dir_excludes
        self.extra_excludes = extra_excludes or []
        self.include_git = include_git
        self.defaults_in_raw = defaults_in_raw
        self._indexes: Dict[str, Set[str]] = {}
        self._tracked_dirs: Dict[str, Set[str]] = {}
        self._patterns: Dict[str, list] = {}
        self._repos: Dict[str, Optional[str]] = {}
        self.check_ignore = git_check_ignore

    def _load_index(self, repo: str) -> None:
        if repo in self._indexes:
            return
        try:
            process = subprocess.run(
                ["git", "-c", "core.fsmonitor=false", "ls-files", "--cached", "-z"],
                cwd=repo, capture_output=True, timeout=30,
            )
            if process.returncode:
                raise RuntimeError(process.stderr.decode("utf-8", errors="replace").strip() or "Git index check failed")
            files = {os.fsdecode(value) for value in process.stdout.split(b"\0") if value}
        except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
            raise RuntimeError("Could not read tracked files: {}".format(exc)) from exc
        directories = set()
        for path in files:
            parts = path.split("/")
            directories.update("/".join(parts[:end]) for end in range(1, len(parts)))
        self._indexes[repo], self._tracked_dirs[repo] = files, directories

    def _plain_ignored(self, relative: str, is_dir: bool) -> bool:
        parts = relative.split("/")
        # Evaluate ancestors first: ignored parents cannot be restored by a child.
        for end in range(1, len(parts) + 1):
            ignored = False
            directory = end < len(parts) or is_dir
            for start in range(end):
                scope = os.path.join(self.root, *parts[:start])
                if scope not in self._patterns:
                    self._patterns[scope] = compile_gitignore_patterns(os.path.join(scope, ".gitignore"))
                value = "/".join(parts[start:end])
                for pattern, negated, dir_only in self._patterns[scope]:
                    if (not dir_only or directory) and _match_ignore_pattern(value, pattern):
                        ignored = not negated
            if ignored:
                return True
        return False

    def ignored(self, paths: List[str], apply_ignore_rules: bool = True) -> Set[str]:
        """Return excluded paths, preserving the caller's separators and dir suffixes."""
        excluded: Set[str] = set()
        groups: Dict[str, list] = {}
        for original in paths:
            relative = original.replace(os.sep, "/").rstrip("/")
            is_dir = original.endswith(("/", os.sep))
            name = relative.rsplit("/", 1)[-1]
            metadata = ".git" in relative.split("/")
            if metadata:
                if not (self.include_git or (self.raw_mode and not self.defaults_in_raw)):
                    excluded.add(original)
                continue
            if any(fnmatch.fnmatchcase(name, pattern.rstrip("/")) for pattern in self.extra_excludes):
                excluded.add(original)
                continue
            parent = os.path.dirname(os.path.join(self.root, relative))
            if not self.raw_mode and parent not in self._repos:
                self._repos[parent] = find_git_root(parent)
            repo = None if self.raw_mode else self._repos[parent]
            tracked = False
            if repo:
                self._load_index(repo)
                value = os.path.relpath(os.path.join(self.root, relative), repo).replace(os.sep, "/")
                tracked = value in self._indexes[repo] or (is_dir and value in self._tracked_dirs[repo])
            if (is_dir and self.default_dir_excludes and (not self.raw_mode or self.defaults_in_raw)
                    and not tracked and any(fnmatch.fnmatchcase(name, pattern) for pattern in EXCLUDE_DIRS)):
                excluded.add(original)
                continue
            if self.raw_mode or not apply_ignore_rules:
                continue
            if repo:
                if not tracked:
                    # Git determines directory type from the filesystem. An
                    # appended slash can make "dir/**" match the parent itself.
                    groups.setdefault(repo, []).append((original, value))
            elif self._plain_ignored(relative, is_dir):
                excluded.add(original)
        for repo, entries in groups.items():
            ignored = self.check_ignore(repo, [value for _, value in entries])
            excluded.update(original for original, value in entries if value in ignored)
        return excluded
