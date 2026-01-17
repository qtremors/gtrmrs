"""
engine.py

RepoTreeVisualizer - Directory tree visualization engine.
Refactored to use shared core module and single-pass scanning.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
from typing import Callable, Dict, List, Optional, Set, Tuple

from gtrmrs.core.colors import Colors


from gtrmrs.core.patterns import EXCLUDE_DIRS
from gtrmrs.core.git_utils import (
    is_git_repo,
    git_check_ignore,
    simple_gitignore_match,
)


class RepoTreeVisualizer:
    """Generates visual directory trees for Git repositories."""

    def __init__(
        self,
        repo_path: str,
        raw_mode: bool = False,
        max_depth: int = -1,
        use_color: bool = True,
        callback: Optional[Callable[..., None]] = None,
    ):
        self.repo_path = os.path.abspath(repo_path)
        self.raw_mode = raw_mode
        self.max_depth = max_depth
        self.use_color = use_color
        self.callback = callback
        
        # Single pass scan
        self.visible_paths = self._scan_repo()

    def _scan_repo(self) -> Set[str]:
        """Perform a single pass scan to identify all visible files."""
        # 1. Collect all candidates (respecting eager pruning)
        all_rel = self._collect_candidates()
        
        if self.raw_mode:
            return set(all_rel)
            
        # 2. Filter using Git or simple patterns
        candidates = set(all_rel)
        ignored = set()
        
        # Always keep .gitignore if present (and usually .git if raw, but here we handled .git)
        # Note: .git dir itself is usually excluded by logic unless handled specifically
        
        if is_git_repo(self.repo_path):
            # Batch check ignore
            # We must pass ALL paths to check-ignore to be safe
            ignored = git_check_ignore(self.repo_path, list(candidates))
        else:
            # Fallback simple matching
            ignore_patterns = self._read_and_compile_gitignore()
            for path in candidates:
                # directory check logic
                is_dir = path.endswith("/") # Our collect adds trailing slash to dirs? 
                # wait, collect logic needs to be consistent
                # let's assume collect returns "foo/bar" for file and "foo/" for dir?
                
                # Using simple_gitignore_match
                if simple_gitignore_match(path.rstrip("/"), ignore_patterns, path.endswith("/")):
                     ignored.add(path)

        # 3. Apply filter
        visible = candidates - ignored
        
        # Ensure .gitignore is visible if it exists (standard practice)
        if os.path.isfile(os.path.join(self.repo_path, ".gitignore")):
            visible.add(".gitignore")
            
        return visible

    def _collect_candidates(self) -> List[str]:
        """Walk file system and collect candidates (eager pruning)."""
        candidates = []
        try:
            for dirpath, dirnames, filenames in os.walk(self.repo_path, topdown=True):
                # Callback
                if self.callback:
                    # Provide feedback on progress
                    self.callback(dirpath)
                
                rel_dir = os.path.relpath(dirpath, self.repo_path)
                if rel_dir == ".":
                    rel_dir = ""
                else:
                    rel_dir = rel_dir.replace(os.sep, "/")
                
                # Check depth
                depth = 0 if not rel_dir else rel_dir.count("/") + 1
                if self.max_depth > -1 and depth >= self.max_depth:
                    dirnames[:] = []
                    filenames[:] = []
                    continue

                # Eager Pruning
                active_dirs = []
                for d in dirnames:
                    if d == ".git":
                        # We generally hide .git content unless raw mode? 
                        # Actually standard rtree shows .git/ folder but not contents usually
                        # Logic: if raw_mode, show .git. If not, hide it.
                        if self.raw_mode:
                            candidates.append((rel_dir + "/" + d + "/") if rel_dir else d + "/")
                        continue
                        
                    if not self.raw_mode:
                        # Check EXCLUDE_DIRS
                        if any(fnmatch.fnmatch(d, p) for p in EXCLUDE_DIRS):
                            continue
                    
                    active_dirs.append(d)
                    path_str = (rel_dir + "/" + d + "/") if rel_dir else d + "/"
                    candidates.append(path_str)
                
                dirnames[:] = active_dirs
                
                for f in filenames:
                    path_str = (rel_dir + "/" + f) if rel_dir else f
                    candidates.append(path_str)
                    
        except OSError:
            pass
            
        return candidates

    def _read_and_compile_gitignore(self) -> List[Tuple[str, bool, bool]]:
        """Read .gitignore and return compiled patterns."""
        path = os.path.join(self.repo_path, ".gitignore")
        if not os.path.isfile(path):
            return []
            
        patterns = []
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    
                    # Compile simple logic (same as engine logic)
                    is_dir = line.endswith("/")
                    if is_dir: line = line[:-1]
                    anchored = line.startswith("/")
                    if anchored: line = line[1:]
                    line = line.replace("\\", "/")
                    patterns.append((line, is_dir, anchored))
        except OSError:
            pass
        return patterns

    def get_ascii_tree(self) -> List[str]:
        """Generate ASCII tree from cached visible paths."""
        
        # Build dict
        tree: Dict[str, Dict] = {}
        
        # Sort paths to ensure parents process before children? 
        # Actually dict update works fine regardless of order if we use setdefault
        
        for path in sorted(self.visible_paths):
            path = path.rstrip("/")
            parts = path.split("/")
            node = tree
            for p in parts:
                node = node.setdefault(p, {})
        
        def _render_ascii(node: Dict, prefix: str = "", current_path: str = "") -> List[str]:
            items = sorted(node.items(), key=lambda x: (len(x[1]) == 0, x[0].lower()))
            lines = []
            for idx, (name, child) in enumerate(items):
                is_last = idx == len(items) - 1
                connector = "└── " if is_last else "├── "
                
                # Determine type
                rel_path = (current_path + "/" + name) if current_path else name
                # It is a directory if it has children OR if explicitly in our set as a dir
                is_dir = len(child) > 0 or (rel_path + "/") in self.visible_paths
                
                if name == ".git" or is_dir:
                    colored_name = Colors.style(name + "/", Colors.BLUE, self.use_color)
                elif name == ".gitignore":
                     colored_name = Colors.style(name, Colors.YELLOW, self.use_color)
                else:
                     colored_name = Colors.style(name, Colors.GREEN, self.use_color)

                lines.append(prefix + connector + colored_name)
                
                if child:
                    extension = "    " if is_last else "│   "
                    lines.extend(_render_ascii(child, prefix + extension, rel_path))
            return lines

        header = Colors.style(
            os.path.basename(self.repo_path) + "/",
            Colors.BLUE + Colors.BOLD,
            self.use_color,
        )
        return [header] + _render_ascii(tree)

    def get_flat_list(self) -> List[str]:
        """Generate sorted flat list."""
        # Just sort the cache!
        # Files first or dirs first? 
        # The previous implementation mixed them but generally breadth-first or directory order?
        # Actually standard simple sort is fine for a flat list usually.
        # But let's try to match: dirs have trailing slash.
        return sorted(list(self.visible_paths))
