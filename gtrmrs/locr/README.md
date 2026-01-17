# locr

> Part of the [gtrmrs](../../README.md) unified CLI toolkit.

**locr** is a blazing fast, dependency-free lines of code counter.

---

## Features

- 📊 **Language Detection** — Recognizes 20+ programming languages
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
