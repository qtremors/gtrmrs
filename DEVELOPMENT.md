# gtrmrs — Development Guide

> **Version:** 0.1.0
> **Last Updated:** 21-10-2026

---

## Architecture Overview

gtrmrs provides five CLI tools. LOC, tree and migration share file-selection
utilities; dependency audits and storage inventory have their own readers.

```
gtrmrs/
├── cli.py                 # Main entry point (subcommand routing)
├── core/                  # Shared utilities
│   ├── colors.py          # ANSI terminal colors
│   ├── patterns.py        # Exclusion patterns (dirs, files, preserves)
│   ├── git_utils.py       # Git operations and shared file collection
│   └── scan_filter.py     # Tracked-source protection and scoped ignore rules
├── rtree/                 # Tree visualization subcommand
│   ├── engine.py          # RepoTreeVisualizer class
│   └── cli.py             # CLI and argument parsing
├── locr/                  # Lines of code subcommand
│   ├── engine.py          # LocrEngine class
│   ├── counter.py         # Physical-line classification
│   ├── languages.py       # Language definitions
│   └── cli.py             # CLI and argument parsing
├── gitmig/                # Repository migration subcommand
│   ├── engine.py          # GitMigEngine class
│   └── cli.py             # CLI and argument parsing
├── deps/                  # Static Gradle auditing and updates
│   ├── engine.py          # Discovery, comparison and update planning
│   ├── models.py          # Audit and update data
│   ├── scanners/          # Catalogs, wrapper properties and SDK literals
│   ├── upstream/          # Release metadata lookups
│   ├── updater/           # Validated per-file replacements
│   ├── report/            # Terminal, JSON and HTML output
│   └── cli.py             # CLI and argument parsing
└── storage/               # Inventory and opt-in cleanup
    ├── engine.py          # File-size accounting and cleanup eligibility
    └── cli.py             # Reports and explicit cleanup selection
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
| `EXCLUDE_DIRS` | Directory defaults for LOC/tree/migration, subject to tracked-source protection and explicit options |
| `EXCLUDE_FILE_PATTERNS` | File safeguards used by LOC/migration; tree output follows directory and Git rules |
| `PRESERVE_PATTERNS` | Migration configurations such as `.env` and `.gitignore`, unless explicitly excluded |

### git_utils.py

Key functions:

| Function | Purpose |
|----------|---------|
| `is_git_repo(path)` | Check if path is a Git repository |
| `git_check_ignore(root, paths)` | Use Git to filter ignored files; verification failures raise by default |
| `should_eager_prune(dirname)` | Check if directory should be skipped |
| `collect_files_with_pruning()` | 2-phase hybrid scanning |

---

## 2-Phase Hybrid Scanning

LOC and tree use the shared collector. Migration uses the same filtering policy
with its own copy-selection walk:

```
Phase 1: EAGER PRUNING
  - Skip known heavy folders (node_modules, venv, .git)
  - Don't even walk into them

Phase 2: GIT PRECISION
  - For remaining files, use `git check-ignore`
  - Preserve tracked source and use the owning repository's ignore decisions
```

Plain folders use bounded local ignore matching. Linked worktrees and submodules
are recognized. Migration visits ignored folders for preserved configuration
files while pruning default cache/dependency directories. Ambiguous names such
as `build`, `dist`, `bin`, `target`, and `schemas` follow project ignore rules.
See [file selection rules](COMMANDS.md#file-selection-rules).

Dependency scanning reads the default catalog, wrapper properties and supported
SDK literals without running Gradle. Extra scanners require corresponding
resolver, updater and report support; registration alone does not implement a
new ecosystem. Updates do not verify AGP/Gradle/JDK/Kotlin compatibility or build
the project. Storage sizes file lengths without following links and rechecks
cleanup candidates before explicit deletion.

---

## Adding a New Subcommand

1. Create a new directory: `gtrmrs/mycommand/`

2. Create required files:
   - `__init__.py`
   - `engine.py`: Core logic class
   - `cli.py`: CLI with `add_parser()` and `main()`

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

# Run a focused test suite
python -m unittest discover -s tests -p test_locr_accuracy.py -q

# Run the 57 offline regression probes using temporary fixtures
python -B tests/audit_regressions.py
```

---

## Code Style

- Pure Python 3.11+ standard library
- Type hints recommended
- Docstrings for public methods
- Follow existing patterns in codebase

---

## Installation (Local Only)

gtrmrs is a local tool suite and is not published on PyPI or package managers.

```bash
# Editable local install (recommended for development)
python -m pip install -e .

# Or standard local install
python -m pip install .

# Or run directly without installation
python -m gtrmrs.cli --help
```

Run module commands from the cloned source directory or an installed package.
Git-aware operations require the Git executable on PATH. Runtime packages use
only the standard library; local installation uses pip and setuptools as build
tooling. Online dependency lookups and pinned-wrapper checksum refreshes can
make network requests, including during update dry runs.
