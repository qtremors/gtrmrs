# gtrmrs - Changelog

## [0.0.8] - 2026-04-19

- Update the project license and its usage terms.

## [0.0.7] - 2026-04-19

- Add `locr --top` to show the 15 largest source files by total lines in terminal and JSON reports.

## [0.0.6] - 2026-04-05

- Count mixed comment/code lines, Python strings and docstrings, and nested Kotlin, Rust and Swift block comments accurately.
- Recognize C++ headers and sources, Protocol Buffers, Python stubs, Sass, Swift, PowerShell, batch and shell aliases, and Dockerfile.
- Use shared Git-aware selection for LOC scans and exclude unreadable or invalid UTF-8 files from successful totals.
- Add focused counting and Android regression fixtures.

## [0.0.5] - 2026-04-05

- Count Gradle, AIDL, ProGuard and properties files alongside Kotlin, Java and Android XML.
- Document Android project scanning and build-artifact selection.

## [0.0.4] - 2026-02-18

- Respect nested Git rules and tracked source in tree scans, with strict errors when Git verification fails.
- Handle plain-folder ignore anchors, nested rules and restoration; add `--no-default-dir-excludes` for directory defaults.
- Include Git metadata in raw trees, preserve Unicode connectors, and report failed output writes.
- Keep redirected output plain and clear terminal spinners correctly on narrow screens and scan failures.

## [0.0.3] - 2026-02-17

- Write copied files and ZIP archives atomically, preserve existing data on failure, and honor archive resume skips.
- Reject source overlaps and linked destinations; copy worktrees and submodules as source snapshots without external Git metadata.
- Respect Git rules, tracked source, explicit exclusions and extension filters; avoid traversing excluded directories.
- Protect signing keys, count completed copies accurately, return failure on copy errors, and support plain terminal output with `--no-color`.

## [0.0.2] - 2026-02-17

- Add `gitmig --git-size` to inspect Git metadata sizes without copying repositories.
- Update the license terms and migration examples.

## [0.0.1] - 2026-01-17

- Add directory trees, lines-of-code reports and repository migration through `gtrmrs` and direct commands.
- Support depth limits, raw scans, file exports, ZIP copies and configurable exclusions.
- Require Python 3.11+ with no third-party runtime packages. Git-aware operations require Git on PATH.
