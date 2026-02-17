# gitmig

> Part of the [gtrmrs](../../README.md) unified CLI toolkit.

**gitmig** copies Git repositories using Git ignore rules and built-in cache/dependency filters. Generated output folders follow the project's ignore rules; `.git` metadata is omitted by default.

---

## Features

- ⚡ **Fast** — Skips heavy folders, copies only source code
- 🌲 **Git-Aware** — Respects `.gitignore` rules
- 🤖 **Android-Friendly**: Skips Gradle/Android caches and honors project rules for build output
- 🔒 **Safe** — Never modifies source repos (copy only)
- 📦 **Zip Mode** — Create archives instead of folders
- 🔧 **Preserves Configs**: Keeps `.env`, `.gitignore` unless explicitly excluded
- 📊 **Stats** — File type breakdown after migration

---

## Usage

```bash
# Copy current repo to destination
gitmig ../backup

# Preview what would be copied
gitmig ../backup --dry-run

# Copy an Android app repo without Gradle/build output
gitmig ../backup --only "android-app"

# Copy all repos in a folder
gitmig C:\Projects D:\Backup
```

---

## Selection Modes

### Default — Respects .gitignore

```bash
gitmig ../backup
```
Copies all files except:
- Dependencies (`node_modules`, `venv`, etc.)
- Files ignored by `.gitignore`
- Binary/temp files (`.log`, `.pyc`, etc.)

### --env — Only .env Files

```bash
gitmig ../backup --env
```
Copies only environment files:
- `.env`
- `.env.local`
- `.env.example`
- `.env.production`

### --ext — By Extension

```bash
gitmig ../backup --ext md          # Only markdown
gitmig ../backup --ext "py,md"     # Python + markdown
gitmig ../backup --ext "ts,tsx,js" # TypeScript/JavaScript
```

### --raw — Include Gitignored

```bash
gitmig ../backup --raw
```
Includes files ignored by Git, but still applies these defaults:
- Dependencies (`node_modules`, `venv`)
- `.git` folder
- Binary/temp and signing-file safeguards

Use `--no-default-dir-excludes` to disable directory defaults while retaining
file safeguards and explicit exclusions. Without `--raw`, Git ignore rules
still apply.

### --git-size — Check .git Folder Size

```bash
gitmig --git-size
```
Calculates and displays the size of the `.git` folder for all found repositories.
- **Read-only**: Does not copy or migrate any files.
- **Table Output**: Shows results in a sorted table (largest first).


---

## Arguments

| Argument | Description |
|----------|-------------|
| `paths` | `[destination]` or `[source] [destination]` |
| `--dry-run` | Preview without copying |
| `--no-color` | Disable terminal colors and hyperlinks |
| `--zip` | Create .zip archives |
| `--stats` | Show file type breakdown |
| `--stats-all` | With `--stats`, show all selected extensions |
| `--env` | Copy only .env files |
| `--ext` | Copy by extension (comma-separated) |
| `--raw` | Include gitignored files |
| `--no-default-dir-excludes` | Disable built-in directory exclusions; retain Git rules and file safeguards |
| `--exclude` | Additional patterns (comma-separated) |
| `--include-git` | Include .git folder |
| `--git-size` | Calculate .git folder size (no copy) |
| `--max-size` | Skip files larger than limit (e.g., `10M`) |
| `--only` | Only specific repos (comma-separated) |
| `--force` | Overwrite without warning |
| `--skip-existing` | Skip existing files (resume mode) |
| `--verbose`, `-v` | Show every file |
| `--quiet`, `-q` | Suppress output |
| `--version` | Show version |

---

## What Gets Excluded

| Category | Excluded |
|----------|----------|
| **Version Control** | `.git`, `.svn`, `.hg` |
| **IDEs** | `.idea`, `.vscode` |
| **Python** | `__pycache__`, `venv`, `.venv`, `*.egg-info` |
| **Node** | `node_modules`, `.next`, `.nuxt` |
| **Android** | `.gradle`, `.kotlin`, `.cxx`, `captures`, `externalNativeBuild` |
| **Project Output** | `build`, `dist`, `target`, `bin`, `obj`, `out`, and `schemas` follow project ignore rules; they are not built-in exclusions |
| **Files** | `*.log`, `*.pyc`, `*.exe`, `*.dll`, `local.properties`, `*.apk`, `*.aab`, `*.dex` |

### Preserved Configurations

- `.env`, `.env.local`, `.env.*`
- `.gitignore`

Explicit `--exclude` patterns take priority in every selection mode, including
`--env` and `--ext`. Extension selection respects `.gitignore`; use `--raw` to
include ignored files. Signing keys (`*.jks`, `*.keystore`) are excluded by default.

Tracked source and its parent directories override built-in directory defaults
in normal Git-aware mode. Preserved configurations are found in visited
folders, including ignored folders; explicitly excluded directories and
untracked cache/dependency directories are not searched unless directory
defaults are disabled. See [file selection rules](../../COMMANDS.md#file-selection-rules).

Linked worktrees and submodules are supported as source snapshots. Their `.git`
pointer files are omitted, and `--include-git` refuses external metadata rather
than creating an incomplete Git backup.

Existing destination links and junctions are refused. Copies and ZIP archives
are staged before replacement so failed or interrupted writes preserve the
previous file or archive. `--skip-existing` also preserves existing ZIP archives.
Errors exit nonzero, and copied-file totals count completed writes. Excluded
directory totals count directories without walking their contents.

Destinations must be outside the source directory. A sibling such as
`../backup` works when scanning the current directory. Migration preserves
environment configurations by default, so copied snapshots can contain secrets;
use explicit exclusions for files you do not want copied. These filename
filters do not inspect file contents.

`--stats` describes selected files; completed-copy totals exclude resume skips
and failures. Colors and terminal hyperlinks are enabled only on terminals;
`--no-color` disables them explicitly. Use `--quiet` to suppress routine output.

---

## Examples

```bash
# Preview backup
gitmig D:\Backup --dry-run

# Android repo copy without build noise
gitmig ../backup --only "android-app"

# Zip archives with stats
gitmig ../backup --zip --stats

# Selective repos
gitmig ../backup --only "frontend,backend"

# Only markdown documentation
gitmig ../docs-copy --ext md

# Extract all env files
gitmig ../configs --env

# Include everything (except deps)
gitmig ../backup --raw
```

---

## Smart Detection

| Location | Behavior |
|----------|----------|
| Inside a repo | Copy **this repo** only |
| Folder with multiple repos | Copy **all repos** found |

```bash
# Inside a repo
cd myproject
gitmig ../backup     # Copies myproject only

# Parent folder
cd ~/Projects
gitmig ../backup     # Copies all repos in Projects
```

---

## Module Structure

```
gtrmrs/gitmig/
├── __init__.py
├── engine.py    # GitMigEngine class
└── cli.py       # CLI entry point
```

Directory, file and preserved-configuration patterns live in
[`core/patterns.py`](../core/patterns.py); migration adds signing-key safeguards.
