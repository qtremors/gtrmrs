# gtrmrs — Complete Command Reference

> **Version:** 1.0.0  
> All commands can be called directly (`rtree`) or via umbrella (`gtrmrs rtree`).

---

## Table of Contents

- [rtree Commands](#rtree-commands)
- [locr Commands](#locr-commands)
- [gitmig Commands](#gitmig-commands)
- [gtrmrs Umbrella](#gtrmrs-umbrella)

---

## rtree Commands

Generate directory tree visualizations.

### Basic Usage

```bash
# Scan current directory
rtree

# Scan specific folder
rtree -r src
rtree -r "C:/Projects/MyApp"
rtree --repo my-project
```

### Depth Control

```bash
# Limit to 1 level deep
rtree --depth 1

# Limit to 2 levels
rtree --depth 2

# Combine with target
rtree -r src --depth 3
```

### Output Modes

```bash
# ASCII tree (default)
rtree

# Flat list of paths
rtree --flat

# Flat list with depth limit
rtree --flat --depth 2
```

### File Output

```bash
# Auto-generate filename (folder_tree.txt)
rtree -o

# Specific filename
rtree -o structure.txt

# Combine with target
rtree -r src -o src_tree.txt
```

### Raw Mode

```bash
# Ignore .gitignore (show everything)
rtree --raw

# Raw with depth limit
rtree --raw --depth 1

# Raw flat list
rtree --raw --flat
```

### Display Options

```bash
# Disable colored output
rtree --no-color

# List all git repos in current directory
rtree --list
```

### Full Examples

```bash
# Tree of src folder, 2 levels, save to file
rtree -r src --depth 2 -o src_tree.txt

# Flat list of everything (raw mode)
rtree --raw --flat -o all_files.txt

# Quick overview of project structure
rtree --depth 1 --no-color
```

---

## locr Commands

Count lines of code with language breakdown.

### Basic Usage

```bash
# Scan current directory
locr

# Scan specific folder
locr src
locr "C:/Projects/MyApp"
```

### Display Options

```bash
# Enable colored output
locr --color
locr -c

# Show percentage statistics
locr --stats
locr -s

# Color + stats
locr --color --stats
locr -c -s
```

### Output Formats

```bash
# JSON output to stdout
locr --json

# Save to file (auto-generate name)
locr -o

# Save to specific file
locr -o report.txt

# JSON to file
locr --json -o stats.json
```

### Raw Mode

```bash
# Ignore .gitignore (count everything)
locr --raw

# Raw with stats
locr --raw --stats
```

### Full Examples

```bash
# Detailed stats with color
locr src --color --stats

# JSON report for CI/CD
locr --json -o locr_report.json

# Quick count of everything
locr --raw
```

---

## gitmig Commands

Copy repositories without dependencies.

### Basic Usage

```bash
# Copy from current dir to destination
gitmig ./backup
gitmig D:\Backup\CleanRepos

# Copy from specific source to destination
gitmig C:\Projects D:\Backup
```

### Preview Mode

```bash
# Dry run (show what would be copied)
gitmig ./backup --dry-run
```

### Selection Modes

```bash
# Default: respects .gitignore
gitmig ./backup

# Only .env files
gitmig ./backup --env

# Only specific extensions
gitmig ./backup --ext md
gitmig ./backup --ext "py,md,json"

# Include gitignored files (but still exclude deps)
gitmig ./backup --raw

# Check .git folder sizes (read-only)
gitmig --git-size
```

### Output Modes

```bash
# Create .zip archives instead of folders
gitmig ./backup --zip

# Show file type breakdown
gitmig ./backup --stats

# Full stats (all extensions)
gitmig ./backup --stats --stats-all
```

### Exclusion Control

```bash
# Add custom exclusions
gitmig ./backup --exclude "*.txt,temp/"

# Include .git folder (normally excluded)
gitmig ./backup --include-git
```

### File Size Control

```bash
# Skip files larger than 10MB
gitmig ./backup --max-size 10M

# Skip files larger than 500KB
gitmig ./backup --max-size 500K
```

### Repo Filtering

```bash
# Only specific repos
gitmig ./backup --only "repo1,repo2"
```

### Overwrite Control

```bash
# Overwrite existing files without warning
gitmig ./backup --force

# Skip files that already exist (resume mode)
gitmig ./backup --skip-existing
```

### Verbosity

```bash
# Show every file being copied
gitmig ./backup --verbose
gitmig ./backup -v

# Suppress all output except errors
gitmig ./backup --quiet
gitmig ./backup -q
```

### Full Examples

```bash
# Preview what would be copied
gitmig D:\Backup --dry-run

# Create zip archives with stats
gitmig ./backup --zip --stats

# Only copy markdown files
gitmig ./docs --ext md

# Extract all env files from repos
gitmig ./configs --env

# Include gitignored but not deps
gitmig ./backup --raw

# Selective backup of specific repos
gitmig ./backup --only "frontend,backend" --verbose

# Resume interrupted copy
gitmig ./backup --skip-existing

# Full backup with size limit
gitmig D:\Backup --max-size 50M --stats
```

---

## gtrmrs Umbrella

All subcommands accessible via `gtrmrs`:

### Version Info

```bash
gtrmrs --version      # gtrmrs 1.0.0
gtrmrs rtree --version
gtrmrs locr --version
gtrmrs gitmig --version
```

### Help

```bash
gtrmrs --help
gtrmrs rtree --help
gtrmrs locr --help
gtrmrs gitmig --help
```

### Subcommand Examples

```bash
# rtree via umbrella
gtrmrs rtree -r src --depth 2

# locr via umbrella
gtrmrs locr --color --stats

# gitmig via umbrella
gtrmrs gitmig ./backup --dry-run
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Quick tree overview | `rtree --depth 1` |
| Flat file list | `rtree --flat` |
| Count lines of code | `locr` |
| LOC with percentages | `locr --stats` |
| Backup repos | `gitmig ./backup` |
| Preview backup | `gitmig ./backup --dry-run` |
| Zip repos | `gitmig ./backup --zip` |
