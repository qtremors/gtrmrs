<p align="center">
  <img src="gtrmrs.png" alt="gtrmrs Logo" width="120" style="border-radius: 20px;"/>
</p>

<h1 align="center"><a href="https://github.com/qtremors/gtrmrs">gtrmrs</a></h1>

<p align="center">
  A unified suite of dependency-free, Git-aware CLI tools for developers.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Version-1.2.0-green" alt="Version">
  <img src="https://img.shields.io/badge/License-TSL-red" alt="License">
</p>

> [!NOTE]
> **Personal Project** 🎯 A unified CLI combining three tools I built for my workflow: directory tree visualization, lines of code counting, and clean repository migration.

---

## ✨ Tools Included

| Tool | Command | Description |
|------|---------|-------------|
| **rtree** | `rtree` | Generate plain-text directory trees |
| **locr** | `locr` | Count lines of code with language breakdown |
| **gitmig** | `gitmig` | Copy repos without `node_modules`, `venv`, `.git` |

All tools share:
- 🔒 **Zero Dependencies** — Pure Python standard library
- 🌲 **Git-Aware** — Respects `.gitignore` automatically
- ⚡ **Eager Pruning** — Skips heavy folders before scanning
- 🤖 **Android-Friendly** — Handles Android/Gradle repos without extra flags

---

## 🚀 Quick Start

```bash
# Clone and install
git clone https://github.com/qtremors/gtrmrs.git
cd gtrmrs
pip install -e .

# Now use directly
rtree
locr
gitmig ./backup --dry-run

# Or via umbrella command
gtrmrs rtree
gtrmrs locr
gtrmrs gitmig ./backup
```

---

## 🎮 Usage Examples

### rtree — Directory Tree

```bash
rtree                    # Tree of current directory
rtree -r src             # Tree of 'src' folder
rtree --depth 2          # Limit to 2 levels
rtree --flat             # Flat list instead of tree
rtree -o                 # Save to file
```

### locr — Lines of Code

```bash
locr                     # Count current directory
locr src --color         # With syntax highlighting
locr --stats             # Show percentages
locr app --stats         # Analyze an Android app module
locr --json              # Output as JSON
locr -o report.txt       # Save report
```

### gitmig — Repository Copy

```bash
gitmig ./backup          # Copy all repos to backup
gitmig --dry-run         # Preview what would be copied
gitmig ./backup --only "android-app"  # Copy an Android repo without build artifacts
gitmig --zip             # Create .zip archives
gitmig --stats           # Show file type breakdown
gitmig --git-size        # Show .git folder sizes
```

---

## 📁 Project Structure

```
gtrmrs/
├── gtrmrs/              # Unified package
│   ├── cli.py           # Main entry point
│   ├── core/            # Shared utilities
│   ├── rtree/           # Tree visualization
│   ├── locr/            # LOC counter
│   └── gitmig/          # Repo migration
├── tests/               # Unit tests
└── setup.py
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Language** | Python 3.8+ |
| **Dependencies** | None (stdlib only) |
| **Logic** | `argparse`, `subprocess`, `os`, `fnmatch` |
| **Testing** | `unittest` |

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [COMMANDS.md](COMMANDS.md) | Complete command reference |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Architecture and contribution guide |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [LICENSE.md](LICENSE.md) | License terms |

### Individual Tool Docs

| Tool | README |
|------|--------|
| rtree | [gtrmrs/rtree/README.md](gtrmrs/rtree/README.md) |
| locr | [gtrmrs/locr/README.md](gtrmrs/locr/README.md) |
| gitmig | [gtrmrs/gitmig/README.md](gtrmrs/gitmig/README.md) |

---

## 📄 License

**Tremors Source License (TSL)** — Source-available license allowing viewing, forking, and derivative works with **mandatory attribution**. Commercial use requires permission.

See [LICENSE.md](LICENSE.md) for full terms.

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/qtremors">Tremors</a>
</p>
