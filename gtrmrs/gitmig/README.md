# gitmig

> Part of the [gtrmrs](../../README.md) unified CLI toolkit.

**gitmig** copies Git repositories without dependencies—no `node_modules`, `venv`, Android build output, or `.git`.

---

## Features

- ⚡ **Fast** — Skips heavy folders, copies only source code
- 🌲 **Git-Aware** — Respects `.gitignore` rules
- 🤖 **Android-Friendly** — Automatically skips Gradle and Android build caches
- 🔒 **Safe** — Never modifies source repos (copy only)
- 📦 **Zip Mode** — Create archives instead of folders
- 🔧 **Preserves Configs** — Always keeps `.env`, `.gitignore`
- 📊 **Stats** — File type breakdown after migration

---

## Usage

```bash
# Copy current repo to destination
gitmig ./backup

# Preview what would be copied
gitmig ./backup --dry-run

# Copy an Android app repo without Gradle/build output
gitmig ./backup --only "android-app"

# Copy all repos in a folder
gitmig C:\Projects D:\Backup
```

---

## Selection Modes

### Default — Respects .gitignore

```bash
gitmig ./backup
```
Copies all files except:
- Dependencies (`node_modules`, `venv`, etc.)
- Files ignored by `.gitignore`
- Binary/temp files (`.log`, `.pyc`, etc.)

### --env — Only .env Files

```bash
gitmig ./backup --env
```
Copies only environment files:
- `.env`
- `.env.local`
- `.env.example`
- `.env.production`

### --ext — By Extension

```bash
gitmig ./backup --ext md          # Only markdown
gitmig ./backup --ext "py,md"     # Python + markdown
gitmig ./backup --ext "ts,tsx,js" # TypeScript/JavaScript
```

### --raw — Include Gitignored

```bash
gitmig ./backup --raw
```
Copies **all files** including those in `.gitignore`, but still excludes:
- Dependencies (`node_modules`, `venv`)
- `.git` folder

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
| `--zip` | Create .zip archives |
| `--stats` | Show file type breakdown |
| `--env` | Copy only .env files |
| `--ext` | Copy by extension (comma-separated) |
| `--raw` | Include gitignored files |
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
| **Build** | `dist`, `build`, `target`, `bin`, `obj` |
| **Files** | `*.log`, `*.pyc`, `*.exe`, `*.dll`, `local.properties`, `*.apk`, `*.aab`, `*.dex` |

### Always Preserved

- `.env`, `.env.local`, `.env.*`
- `.gitignore`

---

## Examples

```bash
# Preview backup
gitmig D:\Backup --dry-run

# Android repo copy without build noise
gitmig ./backup --only "android-app"

# Zip archives with stats
gitmig ./backup --zip --stats

# Selective repos
gitmig ./backup --only "frontend,backend"

# Only markdown documentation
gitmig ./docs --ext md

# Extract all env files
gitmig ./configs --env

# Include everything (except deps)
gitmig ./backup --raw
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
gitmig ./backup     # Copies myproject only

# Parent folder
cd ~/Projects
gitmig ./backup     # Copies all repos in Projects
```

---

## Module Structure

```
gtrmrs/gitmig/
├── __init__.py
├── engine.py    # GitMigEngine class
├── config.py    # Preserve patterns
└── cli.py       # CLI entry point
```
