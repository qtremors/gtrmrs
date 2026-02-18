"""
engine.py

RepoTreeVisualizer - Directory tree visualization engine.
Refactored to use shared core module and single-pass scanning.
"""

from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Set

from gtrmrs.core.colors import Colors
from gtrmrs.core.git_utils import collect_files_with_pruning


class RepoTreeVisualizer:
    """Generates visual directory trees for Git repositories."""

    def __init__(
        self,
        repo_path: str,
        raw_mode: bool = False,
        max_depth: int = -1,
        use_color: bool = True,
        callback: Optional[Callable[..., None]] = None,
        default_dir_excludes: bool = True,
    ):
        self.repo_path = os.path.abspath(repo_path)
        self.raw_mode = raw_mode
        self.max_depth = max_depth
        self.use_color = use_color
        self.callback = callback
        self.default_dir_excludes = default_dir_excludes

        # Single pass scan
        self.visible_paths = self._scan_repo()

    def _scan_repo(self) -> Set[str]:
        """Use shared filtering and retain empty visible directories."""
        paths, ignored = collect_files_with_pruning(
            self.repo_path, raw_mode=self.raw_mode, max_depth=self.max_depth,
            callback=self.callback, default_dir_excludes=self.default_dir_excludes,
        )
        return {path.replace(os.sep, "/") for path in paths if path not in ignored}

    def get_ascii_tree(self) -> List[str]:
        """Generate ASCII tree from cached visible paths."""

        # Build dict
        tree: Dict[str, Dict] = {}

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
        return sorted(list(self.visible_paths))
