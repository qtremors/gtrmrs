"""
engine.py

LocrEngine - Lines of code counting engine.
Refactored to use shared core module.
"""

from __future__ import annotations

import fnmatch
import os
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Tuple

from gtrmrs.core.colors import Colors
from gtrmrs.core.patterns import EXCLUDE_FILE_PATTERNS
from gtrmrs.core.git_utils import collect_files_with_pruning
from gtrmrs.locr.languages import language_for
from gtrmrs.locr.counter import count_lines


class LocrEngine:
    """Lines of code counter with Git-aware scanning."""

    def __init__(self, repo_path: str, raw_mode: bool = False, tests_only: bool = False,
                 default_dir_excludes: bool = True):
        self.repo_path = os.path.abspath(repo_path)
        self.raw_mode = raw_mode
        self.tests_only = tests_only
        self.default_dir_excludes = default_dir_excludes
        self.was_interrupted = False
        self.errors: List[str] = []

    def _is_test_file(self, rel_path: str) -> bool:
        """Determine if a file is a test file based on its path or name."""
        parts = rel_path.replace('\\', '/').split('/')
        dir_parts = [p.lower() for p in parts[:-1]]
        test_dirs = {'test', 'tests', '__tests__', 'spec', 'specs', 'androidtest', 'testlib', 'testing'}
        if any(d in test_dirs for d in dir_parts):
            return True

        filename = parts[-1]
        name_without_ext = os.path.splitext(filename)[0]
        lower_name = name_without_ext.lower()

        if lower_name.startswith('test_') or lower_name.startswith('test-'):
            return True

        for suffix in ('_test', '-test', '.test', '_spec', '-spec', '.spec'):
            if lower_name.endswith(suffix):
                return True

        if name_without_ext.endswith('Test') or name_without_ext.endswith('Tests') or name_without_ext.endswith('Spec'):
            return True

        return False

    def _collect_and_filter_files(
        self, callback: Optional[Callable[[], None]] = None
    ) -> List[str]:
        """Collect source files with shared Git-aware filtering."""
        try:
            paths, ignored = collect_files_with_pruning(
                self.repo_path, raw_mode=self.raw_mode,
                default_dir_excludes=self.default_dir_excludes,
                callback=(lambda _: callback()) if callback else None,
            )
        except KeyboardInterrupt:
            self.was_interrupted = True
            return []
        return [path.replace(os.sep, "/") for path in paths
                if path not in ignored and not path.endswith(os.sep)
                and language_for(path) is not None
                and (self.raw_mode or not any(
                    fnmatch.fnmatchcase(os.path.basename(path), pattern)
                    for pattern in EXCLUDE_FILE_PATTERNS))
                and (not self.tests_only or self._is_test_file(path))]

    def scan(self, callback: Optional[Callable[[], None]] = None) -> Tuple[Dict, List[Dict]]:
        """Scan repository and count lines of code."""
        results = defaultdict(
            lambda: {
                "files": 0,
                "blank": 0,
                "comment": 0,
                "code": 0,
                "color": Colors.WHITE,
            }
        )
        file_results = []
        self.was_interrupted = False
        self.errors = []

        try:
            valid_files = self._collect_and_filter_files(callback)

            for rel_path in valid_files:
                if self.was_interrupted:
                    break
                if callback:
                    callback()

                full_path = os.path.join(self.repo_path, rel_path)
                lang_def = language_for(rel_path)

                if lang_def:
                    try:
                        b, c, k = self._analyze_file(full_path, lang_def)
                    except (OSError, UnicodeError) as exc:
                        self.errors.append("{}: {}".format(rel_path, exc))
                        continue

                    name = lang_def["name"]
                    results[name]["files"] += 1
                    results[name]["blank"] += b
                    results[name]["comment"] += c
                    results[name]["code"] += k
                    results[name]["color"] = lang_def.get("color", Colors.WHITE)

                    file_results.append({
                        "path": rel_path,
                        "blank": b,
                        "comment": c,
                        "code": k
                    })

        except KeyboardInterrupt:
            self.was_interrupted = True

        return results, file_results

    def _analyze_file(
        self, filepath: str, lang_def: dict
    ) -> Tuple[int, int, int]:
        """Analyze a single file for blank/comment/code lines."""
        with open(filepath, "r", encoding="utf-8-sig") as source:
            return count_lines(source, lang_def)
