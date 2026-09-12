# gtrmrs — Complete Command Reference

> **Version:** 0.1.0
> All commands can be called directly (`rtree`) or via umbrella (`gtrmrs rtree`).

Requires Python 3.11+ with no third-party runtime packages. Git is required for
Git-aware operations. Older Python versions are not supported.

---

## Table of Contents

- [File Selection Rules](#file-selection-rules)
- [rtree Commands](#rtree-commands)
- [locr Commands](#locr-commands)
- [gitmig Commands](#gitmig-commands)
- [deps Commands](#deps-commands)
- [storage Commands](#storage-commands)
- [gtrmrs Umbrella](#gtrmrs-umbrella)

---

## File Selection Rules

`rtree`, `locr`, and `gitmig` share directory filtering. Names such as `schemas`,
`bin`, `build`, `dist`, `target`, `obj`, and `out` are no longer blanket exclusions.
Put generated output paths in your project's `.gitignore` instead. Tracked
source and its parent directories override built-in directory defaults during
normal Git-aware scans. Language selection, file filters, explicit migration
exclusions, and migration safeguards still apply.

To include directories normally hidden by built-in cache/dependency defaults
while retaining Git rules:

```bash
rtree --no-default-dir-excludes
locr --no-default-dir-excludes
gitmig ../backup --no-default-dir-excludes
```

This switch does not reveal `.git` metadata or disable file safeguards. LOC
and tree `--raw` bypass ignore rules and directory defaults; `locr --raw --tests`
still selects only test files. `rtree --raw` includes Git metadata contents.
Migration `--raw` bypasses Git ignore rules but keeps directory defaults unless
the switch above is also supplied, and always retains its other file safeguards.

Normal Git-aware scans use the owning repository's index and ignore rules,
including nested rules, `.git/info/exclude`, and linked worktrees/submodules.
Git verification failures stop the scan with a nonzero status instead of
silently including unverified files. LOC/tree prune ignored directories before
walking their contents. Migration inspects ignored folders for preserved
configuration files; built-in cache/dependency exclusions still prune unless
tracked source or the explicit switch overrides them.

Plain folders use a case-sensitive fallback with common globs, `**`, root-only
patterns, directory rules, nested `.gitignore` files, and negation. Ignored
parents must be restored before their children can be restored. This fallback
does not emulate every Git pattern edge case or use Git's global/repository
excludes. Unreadable local ignore rules fail explicitly.

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
# Unicode text tree (default)
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

Colors are automatic for terminal output; redirected and saved trees are plain
text. With `-o` alone, the auto-named file is written to the current directory.
`--list` lists immediate child repositories with a `.git` directory, so it does
not list linked worktrees whose `.git` is a pointer file.

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
# Disable automatic terminal colors
locr --no-color

# Show percentage statistics
locr --stats
locr -s

# Show top 15 largest files
locr --top
locr -t

# Color + stats
locr --stats
locr -s
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

With `-o` alone, the auto-named report is written inside the target directory.
Report write failures return nonzero and go to stderr.

### Raw Mode

```bash
# Ignore .gitignore (count everything)
locr --raw

# Raw with stats
locr --raw --stats
```

### Counting and Read Failures

Lines containing code and comments count as code. Python strings, including
docstrings and multiline strings, count as code. Python uses the standard-library
tokenizer; incomplete syntax falls back to code for unclassified nonblank lines.
Other languages use a bounded comment/string reader. This is physical-line
counting, with limits for regex literals, shell heredocs and language-specific
string forms; it does not parse every language grammar.

Files must be UTF-8, optionally with a BOM. Unreadable files and decoding errors
are reported on stderr, excluded from successful file totals, and cause a nonzero
exit. JSON metadata includes `incomplete` and `errors`; saved text reports mark
incomplete totals. Interrupted scans exit 130. JSON stdout has no spinner output.

Recognition includes `.pyi`, `.sass`, `.swift`, `.ps1`, `.bat`, `.cmd`, `.bash`,
`.zsh`, and the exact filename `Dockerfile`, alongside existing extensions.
Arbitrary extensionless scripts are not detected by shebang.

### Test Files Only

```bash
# Count only test files
locr --tests

# Test files with stats
locr --tests --stats

# Test files even when ignored by Git
locr --raw --tests
```

### Full Examples

```bash
# Detailed stats with color
locr src --stats

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
gitmig ../backup
gitmig D:\Backup\CleanRepos

# Copy from specific source to destination
gitmig C:\Projects D:\Backup
```

The destination must be outside the source directory, including in dry runs.
Use a sibling such as `../backup` when copying the current directory.

### Preview Mode

```bash
# Dry run (show what would be copied)
gitmig ../backup --dry-run
```

### Selection Modes

```bash
# Default: respects .gitignore
gitmig ../backup

# Only .env files
gitmig ../backup --env

# Only specific extensions
gitmig ../backup --ext md
gitmig ../backup --ext "py,md,json"

# Include gitignored files (but still exclude deps)
gitmig ../backup --raw

# Check .git folder sizes (read-only)
gitmig --git-size
```

### Output Modes

```bash
# Create .zip archives instead of folders
gitmig ../backup --zip

# Show file type breakdown
gitmig ../backup --stats

# Full stats (all extensions)
gitmig ../backup --stats --stats-all
```

### Exclusion Control

```bash
# Add custom exclusions
gitmig ../backup --exclude "*.txt,temp/"

# Include .git folder (normally excluded)
gitmig ../backup --include-git

# Include built-in excluded directories while retaining Git rules
gitmig ../backup --no-default-dir-excludes
```

Worktrees and submodules can be copied as ordinary source snapshots. Their
`.git` files point to external metadata and are omitted. `--include-git`
refuses these pointer files rather than creating an incomplete Git backup.

### File Size Control

```bash
# Skip files larger than 10MB
gitmig ../backup --max-size 10M

# Skip files larger than 500KB
gitmig ../backup --max-size 500K
```

### Repo Filtering

```bash
# Only specific repos
gitmig ../backup --only "repo1,repo2"
```

### Overwrite Control

```bash
# Overwrite existing files without warning
gitmig ../backup --force

# Skip files that already exist (resume mode)
gitmig ../backup --skip-existing
```

### Verbosity

```bash
# Show every file being copied
gitmig ../backup --verbose
gitmig ../backup -v

# Suppress all output except errors
gitmig ../backup --quiet
gitmig ../backup -q
```

### Full Examples

```bash
# Preview what would be copied
gitmig D:\Backup --dry-run

# Create zip archives with stats
gitmig ../backup --zip --stats

# Only copy markdown files
gitmig ../docs-copy --ext md

# Extract all env files from repos
gitmig ../configs --env

# Include gitignored but not deps
gitmig ../backup --raw

# Selective backup of specific repos
gitmig ../backup --only "frontend,backend" --verbose

# Resume interrupted copy
gitmig ../backup --skip-existing

# Full backup with size limit
gitmig D:\Backup --max-size 50M --stats
```

Selected-file statistics and completed-copy totals describe different stages;
resume skips and failures do not count as completed copies. Environment files
are preserved by default, so copies can include secrets. Explicit exclusions
take priority. Migration disables colors and terminal hyperlinks when redirected;
`--no-color` disables them explicitly. `--quiet` suppresses routine output while
preserving errors.

---

## deps Commands

Multi-repository dependency and upgrade auditor and updater.

### Basic Usage

```bash
# Discover supported Gradle projects in the current directory
deps
gtrmrs deps

# Scan specific folder or workspace
deps /path/to/repositories
deps "X:/Github"
deps --dir "X:/Github"
```

### Offline and Fast Scanning

```bash
# Skip querying upstream registries (compare repos against each other only)
deps --no-upstream
```

### Filtering Repositories

```bash
# Filter scan or updates to a specific repository
deps --repo earnslate
```

### Generating Reports

```bash
# Generate standalone interactive HTML report
deps --html

# Specify custom HTML file path
deps --html audit-report.html

# Generate HTML report and open in default browser
deps --open

# Machine-readable JSON output
deps --json
deps --json --out report.json

# Save a plain-text report
deps --out report.txt

# Emit JSON while also saving an HTML report
deps --json --html audit-report.html
```

With `--json`, stdout contains only the audit JSON. Progress, saved-report
notifications, and update results go to stderr. Adding `--out` writes JSON to
that file and leaves stdout empty. Reports describe the audit before any
requested updates; update results and the exit status describe what happened
afterward.

Saved text reports contain no generated color codes, and `--no-color` disables
terminal styling, including update messages. Report paths must be different
from each other and from audited catalog or wrapper files. Report write and
browser-open failures return a nonzero exit status.

Upstream checks are reported as `checked`, `skipped`, or `unavailable`. JSON
includes an `upstream_checks` count summary and each component's
`upstream.check_status`. A checked result means release information was
available, not that every repository is current. Missing SDKs display as
`Unknown` in text/HTML; JSON retains the scanner's missing or empty SDK fields.

### Dependency Updating and Alignment

Discovery recognizes Gradle settings files, build scripts, the default version
catalog, or wrapper properties. Catalog-free projects still report readable
wrapper and SDK settings, with dependency coverage explicitly unknown. The
scanner reads dependency declarations only from `gradle/libs.versions.toml`;
custom/imported catalogs, build-script dependencies, and resolved versions are
not evaluated. JSON profiles include `dependency_coverage`, and all report
formats include coverage notes. Zero catalog declarations does not establish
that the project has no dependencies.

Scanning a project directly stops discovery at that root. Workspace discovery
stops at the first project in each branch, searches at most four levels below
the workspace, and prunes common generated directories. To inspect independent
nested builds, scan their roots directly.

Catalogs use Python's built-in TOML parser. Malformed or unreadable catalogs,
invalid section/coordinate shapes, and undefined version references stop the
audit with the affected path and a reason.

Rich versions (`strictly`, `require`, `prefer`, `reject`, `rejectAll`), ranges,
and dynamic selectors are retained as declarations. Their constraints are not
resolved, ranked as fixed versions, or automatically rewritten. Unsupported
constraint shapes are flagged in declaration notes. A constrained/unsupported
alias also prevents automatic edits to other aliases for the same coordinate
within that project.

Libraries with no declared version remain visible as `Managed / versionless`.
This means an external version is needed; it does not confirm that a BOM or
platform actually supplies one. The JSON status key `bom-managed` is retained
for compatibility and has this broader meaning.

JSON includes each component's `repo_declarations`, grouped by repository,
with alias, version, kind, constraint, issue, and reference details. Use
`repo_statuses` and `repo_declarations` to interpret a null `repo_versions`
value: it can describe a managed or constrained declaration, not only an
unused dependency. Profile `declaration_notes` also appear in text and HTML.

SDK reading supports numeric assignments, calls, Groovy space syntax, and
`.set(...)` for `compileSdk`, `targetSdk`, and `minSdk`, including their
traditional `...SdkVersion` names. It reads Android blocks in `.gradle` and
`.gradle.kts` scripts and explicitly qualified `android` SDK properties.
Comments and single/double/triple-quoted examples are ignored. Expressions, constants, provider
calls, and Kotlin convention-plugin source are not evaluated; encountered
unresolved settings include script/line notes. Missing numeric values remain
unknown. Script scanning retains its four-directory-level limit and skips
generated/dependency/cache folders. AGP profiles recognize both application
and library plugin IDs and show declared fixed versions.

```bash
# Preview aligning outdated repos to highest version across workspace (dry-run)
deps --align --dry-run

# Apply alignment across repositories
deps --align

# Preview upgrading dependencies to upstream latest stable releases (dry-run)
deps --update --dry-run

# Apply upstream upgrades
deps --update
```

With `--align` or `--update`, `--repo` limits which repositories may change while
the workspace remains available for comparison. Exact names, including matches
that differ only in case, take priority over partial names.

Conflicting targets for a shared version setting stop the plan before updates
are applied. Each catalog or wrapper file is prepared and checked before one
replacement; files changed since the audit are refused. Failures are reported
with a nonzero exit status. Replacement is atomic per file, so a run involving
multiple files can contain both completed and failed updates.

`--dry-run` validates the proposed edits without writing them. Catalog updates
use Python 3.11+'s standard-library TOML parser. Unsupported catalog layouts
are refused rather than rewritten.

### Version Selection and Wrapper Settings

Version comparisons ignore `+build` metadata and compare numeric qualifier
counters numerically, including multiple fields such as `alpha.2.10`.
Recognized preview tags include `dev`, `ea`/`eap`, `alpha`, `beta`, milestones
(`M4`, `M10`, `milestone-4`), `preview`, `rc`/`cr`, and `snapshot`. Abbreviated
`a`, `b`, and `m` tags require a following number. `Final`, `GA`, and `RELEASE`
are treated like unqualified final releases. Equal-precedence profile values
receive equal highlighting.

These rules cover common numeric/date and Maven/Android-style qualifiers;
they do not reproduce every Maven, Gradle, or strict SemVer ordering rule.
Unknown/vendor suffixes and plain numeric revisions are not automatically
classified as previews. Gradle stable recommendations require a current
release without preview/nightly/snapshot flags. Available releases are compared
by version instead of relying on registry response order.

Wrapper reading uses the active `distributionUrl`: `#`/`!` comments are ignored
and the last definition wins. Common property separators, Java escapes, and
continued lines are understood. Files are read as UTF-8; Java Unicode escapes
are supported. Versions come from recognized `gradle-VERSION-bin.zip` or
`gradle-VERSION-all.zip` path filenames, including RC/snapshot qualifiers;
query strings and fragments are not version fields. Unknown filenames produce
an unknown version and a note rather than exposing the URL as the version.

Updates preserve the archive type, surrounding URL options, inactive settings,
and line endings. Continued settings and percent-encoded archive filenames
are readable but refused for automatic editing. A pinned checksum is refreshed
from the updated distribution URL with `.sha256` appended to its path,
retaining host/query parameters. Fetch failures or invalid checksum content
leave the file unchanged. Relative distribution URLs can be edited without a
pinned checksum; checksum lookup requires an absolute HTTP(S) or file URL.
Wrapper scripts/JARs are not regenerated and project builds are not run.

`--no-upstream` skips registry release lookups. A read-only audit is then
offline, while updates and dry runs involving pinned wrappers can still fetch
the target distribution checksum. Updates do not verify AGP/Gradle/JDK/Kotlin
compatibility, resolve dependencies, migrate build scripts, or run project builds.

---

## storage Commands

Audit repository storage and preview generated-file cleanup. Read-only by default.

```powershell
# Rank repositories, identify build output and inspect Git storage
gtrmrs storage X:\Github

# Preview cleanup for one repository
gtrmrs storage X:\Github --repo tremors-music --clean

# After stopping builds/dev servers, explicitly apply cleanup
gtrmrs storage X:\Github --repo tremors-music --clean --apply

# Also preview removing installed dependencies for a dormant repository
gtrmrs storage X:\Github --repo algorithm-visualizer --clean --include-deps

# Preserve additional files or whole subtrees during cleanup
gtrmrs storage X:\Github --clean --keep "*.custom-key" --keep "my-project/target/debug/manual"

# Export a machine-readable report
gtrmrs storage X:\Github --json --out storage-report.json
```

The direct `storage` command is available after reinstalling the local package.
Git-tracked files, release outputs, recognized credential files, models, and recovery data are
protected. Cleanup rechecks eligibility before deletion; skipped links and
inspection errors prevent affected directories from being cleaned. See the
[storage guide](gtrmrs/storage/README.md) for recognition rules and limitations.

`--keep` is repeatable: names match at any depth; patterns containing `/` are
relative to the scan root. A matching file or directory keeps the containing
cleanup candidate, including during the final inspection. Sensitive-name
recognition is finite and does not inspect file contents. Subdirectory scans
show the owning repository name and label file totals as subtree-only.

---

## gtrmrs Umbrella

All subcommands accessible via `gtrmrs`:

### Version Info

```bash
gtrmrs --version      # gtrmrs 0.1.0
gtrmrs rtree --version
gtrmrs locr --version
gtrmrs gitmig --version
gtrmrs storage --version
```

### Help

```bash
gtrmrs --help
gtrmrs rtree --help
gtrmrs locr --help
gtrmrs gitmig --help
gtrmrs deps --help
gtrmrs storage --help
```

### Subcommand Examples

```bash
# rtree via umbrella
gtrmrs rtree -r src --depth 2

# locr via umbrella
gtrmrs locr --stats

# gitmig via umbrella
gtrmrs gitmig ../backup --dry-run
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Quick tree overview | `rtree --depth 1` |
| Flat file list | `rtree --flat` |
| Count lines of code | `locr` |
| LOC with percentages | `locr --stats` |
| Backup repos | `gitmig ../backup` |
| Preview backup | `gitmig ../backup --dry-run` |
| Zip repos | `gitmig ../backup --zip` |
| Audit dependencies | `deps` |
| Fast offline audit | `deps --no-upstream` |
| Generate HTML report | `deps --html --open` |
| Align workspace versions | `deps --align --dry-run` |
| Upgrade upstream deps | `deps --update --dry-run` |
| Audit repository storage | `gtrmrs storage` |
| Preview build/cache cleanup | `gtrmrs storage --clean` |
