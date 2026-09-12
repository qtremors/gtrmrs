# deps

Audit Gradle declarations in one project or a workspace and preview version
updates. Requires Python 3.11+ with standard-library `tomllib`.

```bash
# Offline, read-only audit
deps --no-upstream

# Compare a workspace and preview alignment for one project
deps /path/to/projects --repo my-project --align --dry-run

# Preview upgrades using available upstream stable versions
deps --update --dry-run

# Save JSON or interactive HTML reports
deps --json --out deps.json
deps --html --open
```

Use `gtrmrs deps` after a local source installation, or
`python -m gtrmrs.deps.cli` from the cloned source directory. See the
[command reference](../../COMMANDS.md#deps-commands) for every option.

## Reading and Discovery

Gradle settings, build scripts, the default catalog and wrapper properties can
identify a project. Catalog-free projects still report readable wrapper/SDK
settings with dependency coverage marked unknown. Direct scans stop discovery
at the project root; workspace discovery stops at the first project in each
branch and searches at most four levels below the workspace. Scan independent
nested builds directly.

Dependency declarations come only from `gradle/libs.versions.toml`. Custom or
imported catalogs, build-script dependencies, resolved versions and arbitrary
convention-plugin source are not evaluated. Reports include coverage and
unresolved-declaration notes; no catalog entries does not imply no dependencies.
SDK reading is static and limited to supported numeric Kotlin/Groovy forms.

Malformed/unreadable catalogs fail explicitly. Rich constraints and managed or
versionless declarations remain visible and are not automatically converted to
fixed versions. Version ordering targets common numeric/date and Maven/Android
forms; see [version selection](../../COMMANDS.md#version-selection-and-wrapper-settings)
for limitations.

## Updates and Reports

`--align` uses the highest comparable declared version in the scanned workspace;
`--update` uses available upstream stable versions. `--repo` selects update
targets while retaining comparison context. Neither checks complete toolchain
compatibility, dependency resolution or whether the result builds.

Use `--dry-run` to validate edits without writing. Conflicting shared settings,
stale files and unsupported edit layouts are refused. Validated replacements
are atomic per file; a multi-file update can contain successes and failures.
Failures return nonzero. Wrapper scripts and JARs are not regenerated.

`--no-upstream` skips registry release lookups. Audits without updates are then
offline. Updating or dry-running a pinned wrapper can still fetch its SHA-256
from beside the target distribution, retaining the configured mirror and query.

With `--json`, stdout contains JSON only; progress and update results use stderr.
`--out` saves JSON or plain text. HTML uses `--html`, with `--open` to launch it.
Reports describe the audit before updates; update results describe applied edits.
Checked, skipped and unavailable upstream states remain distinct. Missing SDKs
and unreadable/unsupported declarations are never replaced with guessed values.
