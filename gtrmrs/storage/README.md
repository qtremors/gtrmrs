# storage

Audit repository storage and preview removal of generated files. Uses Python's
standard library and local Git commands; no network requests or build tools run.

```powershell
# Rank repositories and explain generated storage
gtrmrs storage X:\Github

# Preview cleanup for one repository
gtrmrs storage X:\Github --repo tremors-music --clean

# Stop builds and dev servers first, then explicitly apply cleanup
gtrmrs storage X:\Github --repo tremors-music --clean --apply

# Include installed dependencies for dormant projects
gtrmrs storage X:\Github --repo algorithm-visualizer --clean --include-deps

# Export the inventory and cleanup eligibility
gtrmrs storage X:\Github --json --out storage-report.json

# Keep custom files or a complete subtree during cleanup
gtrmrs storage X:\Github --clean --keep "*.custom-key" --keep "my-project/target/debug/manual"
```

After reinstalling the local package, `storage` also works directly. Without
reinstalling, run `python -m gtrmrs.storage.cli` from the project directory.

## Options

| Argument | Description |
|----------|-------------|
| `path` | Repository or workspace, defaulting to the current directory |
| `--repo` | Exact repository name or path relative to the scan root |
| `--json` | Machine-readable inventory and cleanup results |
| `--out` | Write the report to a file with an existing parent directory |
| `--clean` | Preview eligible build/cache cleanup |
| `--include-deps` | Also select eligible installed dependencies |
| `--apply` | With `--clean`, delete selected eligible directories |
| `--keep PATTERN` | Preserve matching names or scan-root-relative paths; repeatable |
| `--version` | Show the installed version |

## What is recognized

- Rust: default `target/debug` and `target/release`, plus equivalent profiles
  under explicit target triples beside a `Cargo.toml`. Reports compiled
  dependencies, incremental caches, build outputs, and duplicated target modes.
  Custom files and tools elsewhere in `target` are retained.
- Web: `node_modules` and Next.js/Nuxt/bundler caches beside `package.json`.
- Python: virtual environments containing `pyvenv.cfg`, bytecode, and known
  Python tool caches.
- Android: local Gradle/Kotlin/native caches beside Gradle project files and
  recognized generated subdirectories of module `build` directories.
  `build/outputs` is retained, including release APKs and matching R8 mappings.
- Git: directory size and inexpensive object statistics. Large loose-object
  stores get a maintenance hint. Loose objects are not automatically classified
  as unreachable, and this tool never prunes Git data.

Unknown directories are counted but never automatically selected for deletion.
Dependencies require `--include-deps`; build output and caches are the default
cleanup selection. `--repo` accepts an exact name or a relative repository path
and fails if unmatched or ambiguous. Workspace inventory totals remain visible
when filtering cleanup to one repository.

When scanning a repository subdirectory, the report names the owning repository
and labels file totals as covering only the scanned subtree. Git object
statistics describe the owning repository; Git file bytes count only metadata
inside the scanned subtree.

## Cleanup boundaries

An audit and `--clean` are read-only. Deletion requires both `--clean` and
`--apply`. Every selected directory must be ignored by Git, have no tracked or
unignored contents, and be within the scanned directory. Linked Git worktrees
are recognized, but shared object stores outside the scan are not sized.

Git metadata, backups, snapshots, release distributions, model directories, and
patched vendored code are retained. A candidate containing recognized credentials, local
configuration, databases, nested repositories, protected subdirectories, links,
or unreadable files is kept. Git verification failure also prevents cleanup.
Each selected subtree is inspected again immediately before removal, including
its Git status, directory identity, and resolved path.

Sensitive filename checks are conservative. For example, a bundled `.pem`
certificate can keep an otherwise disposable virtual environment in place.
Checks include common key/certificate formats (`.p8`, `.p7b`, `.der`), credential
JSON names, extensionless SSH keys, and credential directories such as `.ssh`
and `.aws`. Recognition is finite and does not inspect file contents.

Use repeatable `--keep PATTERN` options for additional files or directories.
Patterns without `/` match names at any depth; patterns with `/` match paths
relative to the scan root. Use forward slashes for paths. `*`, `?`, and bracket
patterns follow Python `fnmatch` rules, with `*` also able to cross `/`; these
are not Git-ignore rules and do not support negation. Matching is case-insensitive
on Windows and case-sensitive elsewhere. A directory match protects its subtree;
a match anywhere inside a candidate keeps the entire candidate. Keep patterns
are included in JSON and carried into the final pre-deletion inspection.

Stop builds, dev servers, and other writers before applying cleanup. Process
activity is not detected automatically; checks cannot make concurrent writes
safe. Deletion is permanent. Locked files or filesystem errors can leave a
partially removed directory; the command reports failure and exits nonzero.
Rebuilds and dependency reinstalls will recreate generated files.

Sizes are file lengths, not allocated disk usage or guaranteed free space.
Links and Windows junctions are skipped, and their targets are not counted.
Scan/Git errors are included in JSON and terminal reports and cause a nonzero
exit status. Rust custom target directories and profiles beyond debug/release
are not automatically cleaned.
