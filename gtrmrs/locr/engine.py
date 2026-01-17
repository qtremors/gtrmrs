"""
engine.py

LocrEngine - Lines of code counting engine.
Refactored to use shared core module.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Set, Tuple

from gtrmrs.core.colors import Colors

from gtrmrs.core.patterns import EXCLUDE_DIRS
from gtrmrs.core.git_utils import (
    is_git_repo,
    git_check_ignore,
    simple_gitignore_match,
)
from gtrmrs.locr.languages import LANGUAGES


class LocrEngine:
    """Lines of code counter with Git-aware scanning."""

    def __init__(self, repo_path: str, raw_mode: bool = False):
        self.repo_path = os.path.abspath(repo_path)
        self.raw_mode = raw_mode
        self.was_interrupted = False

        # Load patterns for eager pruning
        self.simple_patterns: List[Tuple[str, bool, bool]] = []
        if not self.raw_mode:
            self.simple_patterns = self._load_default_patterns()

    def _load_default_patterns(self) -> List[Tuple[str, bool, bool]]:
        """Load default patterns plus .gitignore for fast pruning."""
        patterns = list(EXCLUDE_DIRS)
        gitignore_path = os.path.join(self.repo_path, ".gitignore")
        
        if os.path.exists(gitignore_path):
            try:
                with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            patterns.append(line)
            except PermissionError:
                pass

        # Compile for fnmatch
        compiled = []
        for raw in patterns:
            p = raw.strip()
            is_dir = p.endswith("/")
            if is_dir:
                p = p[:-1]
            anchored = p.startswith("/")
            if anchored:
                p = p[1:]
            p = p.replace("\\", "/")
            compiled.append((p, is_dir, anchored))
        return compiled

    def _simple_gitignore_match(
        self, relpath: str, patterns: List[Tuple[str, bool, bool]]
    ) -> bool:
        """Simple pattern matching for eager pruning."""
        is_dir = relpath.endswith("/")
        clean_path = relpath.rstrip("/")
        return simple_gitignore_match(clean_path, patterns, is_dir)

    def _is_git_repo(self) -> bool:
        """Check if this is a Git repository."""
        return is_git_repo(self.repo_path)

    def _git_check_ignore(self, relpaths: List[str]) -> Set[str]:
        """Use git check-ignore for accurate filtering."""
        return git_check_ignore(self.repo_path, relpaths)

    def _collect_and_filter_files(
        self, callback: Optional[Callable[[], None]] = None
    ) -> List[str]:
        """
        Collect files using 2-phase hybrid scanning:
        Phase 1: Walk & prune heavy folders
        Phase 2: Use Git for precision filtering
        """
        all_rel_paths = []

        # Phase 1: Walk & Prune
        try:
            for dirpath, dirnames, filenames in os.walk(self.repo_path, topdown=True):
                if callback:
                    callback()

                rel_dir = os.path.relpath(dirpath, self.repo_path)
                if rel_dir == ".":
                    rel_dir = ""
                else:
                    rel_dir = rel_dir.replace(os.sep, "/")

                if not self.raw_mode:
                    # Eager pruning
                    active_dirs = []
                    for d in dirnames:
                        if d == ".git":
                            continue
                        path_to_check = (rel_dir + "/" + d) if rel_dir else d
                        if not self._simple_gitignore_match(
                            path_to_check, self.simple_patterns
                        ):
                            active_dirs.append(d)
                    dirnames[:] = active_dirs

                for f in filenames:
                    # Only track files with known extensions
                    ext = os.path.splitext(f)[1].lower()
                    if ext not in LANGUAGES:
                        continue

                    rel_path = (rel_dir + "/" + f if rel_dir else f).replace(
                        os.sep, "/"
                    )

                    if not self.raw_mode and self._simple_gitignore_match(
                        rel_path, self.simple_patterns
                    ):
                        continue

                    all_rel_paths.append(rel_path)

        except KeyboardInterrupt:
            self.was_interrupted = True
            return []

        if self.raw_mode or not all_rel_paths:
            return all_rel_paths

        # Phase 2: Git Accuracy
        final_list = []
        ignored_by_git = set()

        if self._is_git_repo():
            ignored_by_git = self._git_check_ignore(all_rel_paths)

        for p in all_rel_paths:
            if p not in ignored_by_git:
                final_list.append(p)

        return final_list

    def scan(self, callback: Optional[Callable[[], None]] = None) -> Dict:
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
        self.was_interrupted = False

        try:
            valid_files = self._collect_and_filter_files(callback)

            for rel_path in valid_files:
                if self.was_interrupted:
                    break
                if callback:
                    callback()

                full_path = os.path.join(self.repo_path, rel_path)
                ext = os.path.splitext(rel_path)[1].lower()

                if ext in LANGUAGES:
                    lang_def = LANGUAGES[ext]
                    b, c, k = self._analyze_file(full_path, lang_def)

                    name = lang_def["name"]
                    results[name]["files"] += 1
                    results[name]["blank"] += b
                    results[name]["comment"] += c
                    results[name]["code"] += k
                    results[name]["color"] = lang_def.get("color", Colors.WHITE)

        except KeyboardInterrupt:
            self.was_interrupted = True

        return results

    def _analyze_file(
        self, filepath: str, lang_def: dict
    ) -> Tuple[int, int, int]:
        """Analyze a single file for blank/comment/code lines."""
        blank = 0
        comment = 0
        code = 0
        in_block = False
        single = lang_def.get("single")
        m_start, m_end = lang_def.get("multi") or (None, None)

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        blank += 1
                        continue
                    if in_block:
                        comment += 1
                        if m_end and m_end in line:
                            in_block = False
                        continue
                    if m_start and stripped.startswith(m_start):
                        comment += 1
                        if m_end and m_end not in stripped[len(m_start) :]:
                            in_block = True
                        continue
                    if single and stripped.startswith(single):
                        comment += 1
                        continue
                    code += 1
        except OSError:
            return 0, 0, 0

        return blank, comment, code
