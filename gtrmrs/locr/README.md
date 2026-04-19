# locr

> Part of the [gtrmrs](../../README.md) unified CLI toolkit.

**locr** is a blazing fast, dependency-free lines of code counter.

---

## Features

- 📊 **Language Detection** — Recognizes 20+ programming languages
- 🤖 **Android-Aware** — Counts Kotlin, Gradle, AIDL, ProGuard, and Android XML files automatically
- 🎯 **Accurate Counting** — Separates code, comments, and blank lines
- 🎨 **Smart Colors** — Language-specific syntax highlighting
- 📈 **Statistics** — Percentage breakdowns for file share and comment density
- 📁 **Multiple Outputs** — Terminal, text file, or JSON

---

## Usage

```bash
# Scan current directory
locr

# Scan specific folder
locr src

# Analyze an Android project
locr app --stats

# With color and stats
locr --color --stats

# JSON output
locr --json

# Save report
locr -o
```

---

## Arguments

| Argument | Short | Description |
|----------|-------|-------------|
| `path` | | Target directory (defaults to current) |
| `--color` | `-c` | Enable colored output |
| `--stats` | `-s` | Show percentage statistics |
| `--top` | `-t` | Show top 15 largest files |
| `--json` | | Output as JSON |
| `--raw` | | Ignore .gitignore rules |
| `--out` | `-o` | Save to file |
| `--version` | | Show version |

---

## Supported Languages

| Extension | Language | Comment Style |
|-----------|----------|---------------|
| `.py` | Python | `#`, `"""` |
| `.js`, `.jsx` | JavaScript | `//`, `/* */` |
| `.ts`, `.tsx` | TypeScript | `//`, `/* */` |
| `.html` | HTML | `<!-- -->` |
| `.css` | CSS | `/* */` |
| `.java` | Java | `//`, `/* */` |
| `.kt` | Kotlin | `//`, `/* */` |
| `.kts` | Kotlin Script | `//`, `/* */` |
| `.gradle` | Gradle | `//`, `/* */` |
| `.aidl` | AIDL | `//`, `/* */` |
| `.pro` | ProGuard | `#` |
| `.properties` | Properties | `#` |
| `.go` | Go | `//`, `/* */` |
| `.rs` | Rust | `//`, `/* */` |
| `.md` | Markdown | None |
| `.json` | JSON | None |
| And more... | | |

---

## Examples

```bash
# Detailed stats with color
locr src --color --stats

# Show largest files
locr --top

# Android app module + Gradle files
locr app --stats

# JSON for CI/CD pipelines
locr --json -o report.json

# Count everything (ignore .gitignore)
locr --raw

# Quick count
locr
```

---

## Sample Output

```
========================================================================
Language                    Files        Blank      Comment         Code
------------------------------------------------------------------------
Python                         15          120          240          840
TypeScript TSX                 21          257           19         2256
JavaScript                      7           36           14          239
------------------------------------------------------------------------
TOTAL                          43          413          273         3335
========================================================================
Processed 43 files in 0.032 seconds.
```

---

## Module Structure

```
gtrmrs/locr/
├── __init__.py
├── engine.py      # LocrEngine class
├── languages.py   # Language definitions
└── cli.py         # CLI entry point
```
