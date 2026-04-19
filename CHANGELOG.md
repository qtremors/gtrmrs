# gtrmrs — Changelog

> **Project:** gtrmrs (unified CLI)
> **Version:** 1.3.0
> **Last Updated:** 19-04-2026

---

## [1.3.0] — 19-04-2026

### Added

- **locr**: New `--top` / `-t` flag
  - Displays a table of the top 15 largest files (by total line count)
  - Features smart path truncation and column alignment
  - Includes `top_files` section in JSON output when requested

### Fixed

- **locr**: Resolved several missing typing and standard library imports in `cli.py`
- **locr**: Corrected output table formatting issues with long file paths

---

## [1.2.0] — 05-04-2026

### Added

- **Android / Gradle Repo Support**
  - Added automatic Android-friendly handling across `rtree`, `locr`, and `gitmig`
  - Added Kotlin, Kotlin Script, Gradle, AIDL, ProGuard, and Properties support to `locr`
  - Added focused regression tests for Android-shaped repositories

### Changed

- **Shared Exclusion Rules**
  - Exclude Android/Gradle cache and generated directories such as `.gradle`, `.kotlin`, `.cxx`, `captures`, and `externalNativeBuild`
  - Exclude Android build artifacts and machine-local files such as `local.properties`, `*.apk`, `*.aab`, and `*.dex`

### Documentation

- Updated README and tool docs with Android project examples
- Synced project documentation to version `1.2.0`

---

## [1.1.0] — 17-02-2026

### Added

- **gitmig**: New `--git-size` flag
  - Calculates and displays the size of `.git` folders
  - Outputs a sorted table (largest to smallest)
  - Read-only mode (skips migration)
  - Supports `gitmig --git-size` to scan current directory

---

## [1.0.0] — 17-01-2026

### Added

- **Unified CLI Architecture**
  - Combined `rtree`, `locr`, and `gitmig` into single `gtrmrs` package
  - Shared core module (`gtrmrs/core/`) with Colors, patterns, and git utilities
  - Both direct access (`rtree`, `locr`, `gitmig`) and umbrella (`gtrmrs <cmd>`) commands

- **Shared Components**
  - `colors.py` — Unified ANSI color class
  - `patterns.py` — Combined exclusion patterns from all tools
  - `git_utils.py` — Git-aware scanning utilities

- **Subcommands**
  - `rtree` — Directory tree visualization with Git awareness
  - `locr` — Lines of code counter with language detection
  - `gitmig` — Repository copy/migration without dependencies

- **Documentation**
  - Unified README.md with overview
  - COMMANDS.md with complete reference
  - DEVELOPMENT.md with architecture guide
  - Individual READMEs for each subcommand

### Changed

- All tools now share common exclusion patterns
- Unified versioning (1.0.0) across all subcommands
- Default to current directory (no `.` needed)

### gitmig Enhancements

- Added `.gitignore` respect (uses `git check-ignore`)
- Added `--env` flag: copy only .env files
- Added `--ext` flag: copy by extension
- Added `--raw` flag: include gitignored but exclude deps
- Added spinner feedback during scan
- Added graceful `Ctrl+C` handling
- Added smart single/multi repo detection

### Notes

- Original standalone folders preserved (`rtree/`, `locr/`, `gitmig/`)
- Zero dependencies maintained
