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
from typing import Callable, List, Optional, Set, Tuple

from gtrmrs.core.patterns import EXCLUDE_DIRS


def is_git_repo(path: str) -> bool:
    """Check if the given path is inside a Git repository."""
    git_dir = os.path.join(path, ".git")
    return os.path.isdir(git_dir)


def git_check_ignore(repo_path: str, relpaths: List[str]) -> Set[str]:
    """
    Use `git check-ignore` to determine which paths are ignored.
    
    Args:
        repo_path: Root of the Git repository
        relpaths: List of relative paths to check
    
    Returns:
        Set of relative paths that are ignored by Git
    """
    if not relpaths:
        return set()
    
    # Sanitize paths: filter out any with null bytes or control characters
    safe_paths = [
        p for p in relpaths
        if "\0" not in p and all(ord(c) >= 32 or c in "\t\n" for c in p)
    ]
    
    if not safe_paths:
        return set()
    
    try:
        # Use null-delimited protocol (-z) for safer parsing
        input_bytes = "\0".join(safe_paths).encode("utf-8")
        proc = subprocess.run(
            ["git", "check-ignore", "--stdin", "-z"],
            input=input_bytes,
            capture_output=True,
            cwd=repo_path,
            timeout=30,
        )
        if proc.returncode not in (0, 1) or not proc.stdout:
            return set()
        parts = [p.decode("utf-8") for p in proc.stdout.split(b"\0") if p]
        return set(parts)
    except (subprocess.SubprocessError, FileNotFoundError):
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
        with open(gitignore_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                
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
    except (IOError, UnicodeDecodeError):
        pass
    
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
    ignored = False
    
    for pattern, is_negation, is_dir_only in patterns:
        # Skip dir-only patterns for files
        if is_dir_only and not is_dir:
            continue
        
        # Match against basename or full path
        basename = os.path.basename(relpath)
        matches = fnmatch.fnmatch(basename, pattern) or fnmatch.fnmatch(relpath, pattern)
        
        if matches:
            ignored = not is_negation
    
    return ignored


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
) -> Tuple[List[str], Set[str]]:
    """
    Collect all files using the 2-phase hybrid scanning strategy.
    
    Phase 1: Eagerly prune heavy folders during os.walk
    Phase 2: Use git check-ignore for remaining files (if in a Git repo)
    
    Args:
        root: Root directory to scan
        raw_mode: If True, skip all filtering
        extra_excludes: Additional patterns to exclude
        max_depth: Maximum depth to scan (-1 for unlimited)
        callback: Optional callback for progress updates
    
    Returns:
        Tuple of (list of relative paths, set of ignored paths)
    """
    root = os.path.abspath(root)
    all_relpaths: List[str] = []
    
    # Phase 1: Walk and collect with eager pruning
    for dirpath, dirnames, filenames in os.walk(root):
        # Calculate current depth
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            current_depth = 0
        else:
            current_depth = rel_dir.count(os.sep) + 1
        
        # Depth limiting
        if max_depth >= 0 and current_depth >= max_depth:
            dirnames.clear()
            continue
        
        # Eager pruning (unless raw mode)
        if not raw_mode:
            dirnames[:] = [
                d for d in dirnames
                if not should_eager_prune(d, extra_excludes)
            ]
        
        # Collect files
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            relpath = os.path.relpath(full_path, root)
            all_relpaths.append(relpath)
            
            if callback:
                callback(relpath)
        
        # Collect directories (for tree visualization)
        for dirname in dirnames:
            full_path = os.path.join(dirpath, dirname)
            relpath = os.path.relpath(full_path, root) + os.sep
            all_relpaths.append(relpath)
    
    # Phase 2: Git filtering (unless raw mode)
    ignored_set: Set[str] = set()
    
    if not raw_mode and is_git_repo(root):
        # Filter only files (not directories) through git check-ignore
        file_relpaths = [p for p in all_relpaths if not p.endswith(os.sep)]
        ignored_set = git_check_ignore(root, file_relpaths)
    elif not raw_mode:
        # Fallback to .gitignore parsing
        gitignore_path = os.path.join(root, ".gitignore")
        patterns = compile_gitignore_patterns(gitignore_path)
        
        if patterns:
            for relpath in all_relpaths:
                is_dir = relpath.endswith(os.sep)
                if simple_gitignore_match(relpath.rstrip(os.sep), patterns, is_dir):
                    ignored_set.add(relpath)
    
    return all_relpaths, ignored_set
