# rtree

> Part of the [gtrmrs](../../README.md) unified CLI toolkit.

**rtree** generates plain-text directory tree visualizations for Git repositories.

---

## Features

- 🌲 **Git-Aware** — Automatically respects `.gitignore` rules
- 🤖 **Android-Friendly**: Hides Gradle caches and honors project ignore rules for build output
- 🎨 **Smart Colors** — Blue for directories, Green for files, Yellow for configs
- 📏 **Depth Control** — Limit recursion depth for large projects
- 🔄 **Multiple Modes**: Unicode tree, flat list, or raw (ignore rules bypassed)
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
| `--no-default-dir-excludes` | | Disable built-in directory exclusions; retain Git rules |
| `--out` | `-o` | Save to file |
| `--no-color` | | Disable colored output |
| `--list` | | List git repos in current directory |
| `--version` | | Show version |

Colors are automatic on terminals and disabled for redirected or saved reports.
Report write failures go to stderr and return a nonzero exit status.
With `-o` alone, the generated report is saved in the current directory.
`--list` lists direct child repositories with a `.git` directory; linked worktree
pointer files are recognized by scanning but are not included in this listing.

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

1. **Initialization**: Finds the owning Git repository and reads its tracked-file index; plain folders use scoped local ignore rules.
2. **Eager Pruning**: Skips ignored and default cache/dependency folders before walking their contents, while preserving tracked source.
3. **Git Precision**: Uses Git ignore decisions for untracked paths, including nested rules. Git failures stop the scan explicitly.
4. **Rendering**: Generates a Unicode text tree with indentation.

---

## Module Structure

```
gtrmrs/rtree/
├── __init__.py
├── engine.py    # RepoTreeVisualizer class
└── cli.py       # CLI entry point
```
