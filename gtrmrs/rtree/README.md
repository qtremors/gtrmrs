# rtree

> Part of the [gtrmrs](../../README.md) unified CLI toolkit.

**rtree** generates plain-text directory tree visualizations for Git repositories.

---

## Features

- 🌲 **Git-Aware** — Automatically respects `.gitignore` rules
- 🎨 **Smart Colors** — Blue for directories, Green for files, Yellow for configs
- 📏 **Depth Control** — Limit recursion depth for large projects
- 🔄 **Multiple Modes** — ASCII tree, flat list, or raw (unfiltered)
- 📁 **File Output** — Save to file with auto-generated names

---

## Usage

```bash
# Scan current directory
rtree

# Scan specific folder
rtree -r src

# Limit depth
rtree --depth 2

# Flat list
rtree --flat

# Save to file
rtree -o
```

---

## Arguments

| Argument | Short | Description |
|----------|-------|-------------|
| `--repo` | `-r` | Target directory (defaults to current) |
| `--depth` | | Max recursion depth |
| `--flat` | | Output flat list instead of tree |
| `--raw` | | Ignore .gitignore rules |
| `--out` | `-o` | Save to file |
| `--no-color` | | Disable colored output |
| `--list` | | List git repos in current directory |
| `--version` | | Show version |

---

## Examples

```bash
# Quick project overview
rtree --depth 1

# Save tree to file
rtree -r my-project -o project_tree.txt

# Flat list of all files
rtree --flat

# Raw mode (show everything)
rtree --raw --depth 2
```

---

## How It Works

1. **Initialization** — Reads `.gitignore` from target directory
2. **Eager Pruning** — Skips heavy folders (`node_modules`, `venv`) immediately
3. **Git Precision** — Uses `git check-ignore` for remaining files
4. **Rendering** — Generates ASCII tree with proper indentation

---

## Module Structure

```
gtrmrs/rtree/
├── __init__.py
├── engine.py    # RepoTreeVisualizer class
└── cli.py       # CLI entry point
```
