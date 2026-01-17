# gtrmrs — Development Guide

> **Version:** 1.0.0  
> **Last Updated:** 17-01-2026

---

## Architecture Overview

gtrmrs is a unified CLI package combining three Git-aware tools that share a common core.

```
gtrmrs/
├── cli.py                 # Main entry point (subcommand routing)
├── core/                  # Shared utilities
│   ├── colors.py          # ANSI terminal colors
│   ├── patterns.py        # Exclusion patterns (dirs, files, preserves)
│   └── git_utils.py       # Git-aware scanning logic
├── rtree/                 # Tree visualization subcommand
│   ├── engine.py          # RepoTreeVisualizer class
│   └── cli.py             # CLI and argument parsing
├── locr/                  # Lines of code subcommand
│   ├── engine.py          # LocrEngine class
│   ├── languages.py       # Language definitions
│   └── cli.py             # CLI and argument parsing
└── gitmig/                # Repository migration subcommand
    ├── engine.py          # GitMigEngine class
    ├── config.py          # Preserve patterns (.env)
    └── cli.py             # CLI and argument parsing
```

---

## Core Module

### colors.py

Unified ANSI color class:

```python
from gtrmrs.core.colors import Colors

# Usage
print(Colors.style("Hello", Colors.GREEN))
print(Colors.style("Warning", Colors.YELLOW, enabled=True))
```

### patterns.py

Three types of patterns:

| Pattern Type | Purpose |
|-------------|---------|
| `EXCLUDE_DIRS` | Directories to skip (node_modules, venv, .git) |
| `EXCLUDE_FILE_PATTERNS` | File patterns to skip (*.log, *.pyc) |
| `PRESERVE_PATTERNS` | Files to always include (.env, .env.*) |

### git_utils.py

Key functions:

| Function | Purpose |
|----------|---------|
| `is_git_repo(path)` | Check if path is a Git repository |
| `git_check_ignore(root, paths)` | Use Git to filter ignored files |
| `should_eager_prune(dirname)` | Check if directory should be skipped |
| `collect_files_with_pruning()` | 2-phase hybrid scanning |

---

## 2-Phase Hybrid Scanning

All three tools use the same scanning strategy:

```
Phase 1: EAGER PRUNING
  - Skip known heavy folders (node_modules, venv, .git)
  - Don't even walk into them
  
Phase 2: GIT PRECISION
  - For remaining files, use `git check-ignore`
  - Ensures 100% accuracy with .gitignore rules
```

This provides both speed (skip millions of files) and accuracy (respect complex .gitignore).

---

## Adding a New Subcommand

1. Create a new directory: `gtrmrs/mycommand/`

2. Create required files:
   - `__init__.py`
   - `engine.py` — Core logic class
   - `cli.py` — CLI with `add_parser()` and `main()`

3. Register in `gtrmrs/cli.py`:
   ```python
   from gtrmrs.mycommand.cli import add_parser as add_mycommand
   add_mycommand(subparsers)
   ```

4. Add entry point in `setup.py`:
   ```python
   'mycommand=gtrmrs.mycommand.cli:main',
   ```

---

## Testing

```bash
# Run all tests
python -m unittest discover tests -v

# Run specific test suite
python -m unittest tests.test_rtree -v
```

---

## Code Style

- Pure Python 3.8+ standard library
- Type hints recommended
- Docstrings for public methods
- Follow existing patterns in codebase

---

## Building

```bash
# Editable install (development)
pip install -e .

# Build distribution
python -m build

# Upload to PyPI (requires credentials)
twine upload dist/*
```
