<p align="center">
  <img src="gtrmrs.svg" alt="gtrmrs Logo" width="120" style="border-radius: 20px;"/>
</p>

<h1 align="center"><a href="https://github.com/qtremors/gtrmrs">gtrmrs</a></h1>

<p align="center">
  A unified suite of dependency-free, Git-aware CLI tools for developers.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Version-0.1.0-green" alt="Version">
  <img src="https://img.shields.io/badge/License-TSL-red" alt="License">
</p>

> [!NOTE]
> **Personal Project** 🎯 Five tools for directory trees, lines of code, repository migration, Gradle dependency audits, and storage inspection.

---

## ✨ Tools Included

| Tool | Command | Description |
|------|---------|-------------|
| **rtree** | `rtree` | Generate plain-text directory trees |
| **locr** | `locr` | Count lines of code with language breakdown |
| **gitmig** | `gitmig` | Copy repos without `node_modules`, `venv`, `.git` |
| **deps** | `deps` | Audit Gradle catalogs, wrapper versions and SDK settings |
| **storage** | `storage` | Inspect repository sizes and preview generated-file cleanup |

Requires **Python 3.11+**, with no third-party Python runtime packages. Git must
be on PATH for Git-aware scans, migration and storage cleanup verification.
LOC/tree scans also work on plain folders using local ignore rules.

`locr`, `rtree`, and `gitmig` share Git-aware directory filtering and cache
pruning. Generated folders such as `build`, `target`, and `schemas` follow
project ignore rules. Dependency audits read static Gradle declarations;
storage inspection uses separate inventory and cleanup eligibility rules.

---

## 🚀 Quick Start

> **Note:** `gtrmrs` is a local tool suite and is not published on PyPI or package managers. Install directly from local source.

```sh
# Clone and install locally
git clone https://github.com/qtremors/gtrmrs.git
cd gtrmrs
python -m pip install -e .

# Now use directly
rtree
locr
deps
storage
gitmig ../backup --dry-run

# Or via umbrella command
gtrmrs rtree
gtrmrs locr
gtrmrs deps
gtrmrs storage
gtrmrs gitmig ../backup --dry-run
```

For direct execution from the cloned source without installation, run
`python -m gtrmrs.cli --help`. See [installation details](DEVELOPMENT.md#installation-local-only).

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
locr src --no-color      # Disable automatic terminal colors
locr --stats             # Show percentages
locr app --stats         # Analyze an Android app module
locr --json              # Output as JSON
locr -o report.txt       # Save report
```

### gitmig — Repository Copy

```bash
gitmig ../backup          # Copy current repo or discovered repos
gitmig ../backup --dry-run # Preview what would be copied
gitmig ../backup --only "android-app" # Select a repository by name
gitmig ../backup --zip    # Create .zip archives
gitmig ../backup --stats  # Show selected file type breakdown
gitmig --git-size        # Show .git folder sizes
```

Choose a destination outside the source directory. Environment files can be
included in migrations; use explicit exclusions when needed.

### deps - Gradle Dependency Audit

```bash
deps --no-upstream          # Read-only audit without release lookups
deps --align --dry-run      # Validate a workspace alignment plan
deps --json --out deps.json # Save a machine-readable audit
```

Dependency declarations come from `gradle/libs.versions.toml`. Custom catalogs,
resolved versions and toolchain compatibility are not evaluated. See the
[dependency guide](gtrmrs/deps/README.md) before applying updates.

### storage - Storage Inspection

```bash
storage                    # Read-only inventory
storage --clean            # Preview eligible cleanup
storage --clean --keep "*.custom-key" # Preserve additional matching data
```

Deletion requires `--clean --apply`. Read the [cleanup boundaries](gtrmrs/storage/README.md#cleanup-boundaries)
before applying a cleanup.

---

## 📁 Project Structure

```
gtrmrs/
├── gtrmrs/              # Unified package
│   ├── cli.py           # Main entry point
│   ├── core/            # Shared utilities
│   ├── rtree/           # Tree visualization
│   ├── locr/            # LOC counter
│   ├── gitmig/          # Repo migration
│   ├── deps/            # Gradle dependency audit and updates
│   └── storage/         # Storage inventory and opt-in cleanup
├── tests/               # Unit tests
└── setup.py
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Language** | Python 3.11+ |
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
| deps | [gtrmrs/deps/README.md](gtrmrs/deps/README.md) |
| storage | [gtrmrs/storage/README.md](gtrmrs/storage/README.md) |

---

## 📄 License

**Tremors Source License (TSL)** — Source-available license allowing viewing, forking, and derivative works with **mandatory attribution**. Commercial use requires permission.

See [LICENSE.md](LICENSE.md) for full terms.

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/qtremors">Tremors</a>
</p>
