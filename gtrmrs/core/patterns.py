"""
patterns.py

Default exclusion and preservation patterns.
Combined best-of-all from rtree, locr, and gitmig.
"""

from typing import List

# =============================================================================
# Directories to Always Exclude (Eager Pruning)
# =============================================================================
EXCLUDE_DIRS: List[str] = [
    # Version Control
    ".git",
    ".svn",
    ".hg",
    # IDEs
    ".idea",
    ".vscode",
    # Python
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "venv",
    ".venv",
    "env",
    ".tox",
    ".nox",
    "*.egg-info",
    # Node / Web
    "node_modules",
    "bower_components",
    ".next",
    ".nuxt",
    ".output",
    ".cache",
    # Build Artifacts
    "dist",
    "build",
    "target",
    "bin",
    "obj",
    "out",
    ".parcel-cache",
    # Misc
    ".DS_Store",
    "Thumbs.db",
    ".turbo",
]

# =============================================================================
# File Patterns to Exclude
# =============================================================================
EXCLUDE_FILE_PATTERNS: List[str] = [
    "*.log",
    "*.tmp",
    "*.temp",
    "*.bak",
    "*.swp",
    "*.pyc",
    "*.pyo",
    "*.class",
    "*.dll",
    "*.exe",
    "*.o",
    "*.so",
    "*.dylib",
]

# =============================================================================
# Files/Patterns to Always Preserve (Override Exclusions)
# =============================================================================
PRESERVE_PATTERNS: List[str] = [
    ".env",
    ".env.*",  # Covers .env.local, .env.production, etc.
    ".gitignore",
]
