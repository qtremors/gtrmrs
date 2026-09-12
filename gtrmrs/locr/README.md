# locr

> Part of the [gtrmrs](../../README.md) unified CLI toolkit.

**locr** is a blazing fast, dependency-free lines of code counter.

---

## Features

- 📊 **Language Detection** — Recognizes 20+ programming languages
- 🤖 **Android-Aware** — Counts Kotlin, Gradle, AIDL, ProGuard, and Android XML files automatically
- 🎯 **Accurate Counting** — Separates code, comments, and blank lines
- 🎨 **Smart Colors**: Language-specific report row colors
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
locr --stats

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
| `--no-color` | | Disable automatic terminal colors |
| `--stats` | `-s` | Show percentage statistics |
| `--top` | `-t` | Show top 15 largest files |
| `--json` | | Output as JSON |
| `--raw` | | Ignore .gitignore rules |
| `--no-default-dir-excludes` | | Disable built-in directory exclusions; retain Git rules and file filters |
| `--tests` | | Count only lines of code in test files |
| `--out` | `-o` | Save to file |
| `--version` | | Show version |

---

## Supported Languages

| Extension | Language | Comment Style |
|-----------|----------|---------------|
| `.py`, `.pyi` | Python | `#`; strings and docstrings count as code |
| `.scss`, `.sass` | Sass | `//`, `/* */` |
| `.swift` | Swift | `//`, `/* */` |
| `.ps1` | PowerShell | `#`, `<# #>` |
| `.bat`, `.cmd` | Batch | `REM`, `::` |
| `.sh`, `.bash`, `.zsh` | Shell | `#` |
| `Dockerfile` (exact filename) | Dockerfile | `#` |
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
| `.c`, `.h` | C / C Header | `//`, `/* */` |
| `.cpp`, `.cc`, `.cxx` | C++ | `//`, `/* */` |
| `.hpp`, `.hh`, `.hxx` | C++ Header | `//`, `/* */` |
| `.proto` | Protocol Buffers | `//`, `/* */` |
| `.cs` | C# | `//`, `/* */` |
| `.php` | PHP | `//`, `/* */` |
| `.yaml`, `.yml` | YAML | `#` |
| `.toml` | TOML | `#` |
| `.xml` | XML | `<!-- -->` |
| `.sql` | SQL | `--`, `/* */` |
| `.lua` | Lua | `--`, `--[[ ]]` |

Mixed code/comment lines count as code. Python uses its standard-library
tokenizer; other languages use a bounded comment/string reader, including
nested Kotlin/Rust/Swift block comments. Regex literals, shell heredocs,
arbitrary extensionless scripts, and some specialized string syntax remain
outside coverage. Incomplete Python syntax treats unclassified nonblank lines
as code. Files must be UTF-8, optionally with a BOM.

Unreadable/invalid-encoding files are reported on stderr and excluded from
successful file totals; the command exits nonzero. JSON metadata contains
`incomplete` and `errors`, and saved text reports label incomplete totals.
Interrupted scans exit 130. Colors are automatic on terminals; redirected
output and JSON have no generated styling or spinner output.
With `-o` alone, the generated report is saved inside the scanned directory.
`--tests` uses directory and filename heuristics, including `test`, `tests`,
`spec`, `androidTest`, `test_...` and `...Test` forms. It does not isolate embedded
test blocks or identify every framework/source-set convention.

---

## Examples

```bash
# Detailed stats with color
locr src --stats

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
├── counter.py     # Physical-line classification
├── languages.py   # Language definitions
└── cli.py         # CLI entry point
```
