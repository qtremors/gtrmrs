# gtrmrs — Tasks

> **Project:** gtrmrs
> **Version:** 1.1.0
> **Last Updated:** 18-02-2026

---

## Bugs

- [ ] **`locr/cli.py` missing `List` import**
  - `generate_report()` return type annotation uses `List[str]` (line 39), but `List` is not imported from `typing` — only `Dict` is imported
  - Will crash at runtime if type checking is enforced, and is a static analysis error

- [ ] **`locr/cli.py` color flag inconsistency with actual code**
  - README and COMMANDS.md document `--color` / `-c` as the flag to enable color
  - Actual CLI code only has `--no-color` (opt-out), there is no `--color` / `-c` flag
  - locr README arguments table lists `--color | -c | Enable colored output` — these flags don't exist

- [ ] **`locr/engine.py` callback signature mismatch**
  - `scan()` declares `callback: Optional[Callable[[], None]]` (no args)
  - `_collect_and_filter_files()` also declares `callback: Optional[Callable[[], None]]`
  - But `locr/cli.py` defines `update_spinner(*args)` and passes it as callback
  - The callback is called with `callback()` in engine (no args) but with `callback(relpath)` in `core/git_utils.py` `collect_files_with_pruning()`
  - Inconsistent contract: engine calls `callback()`, core calls `callback(relpath)`

- [ ] **`rtree/cli.py` spinner not using terminal width for clearing**
  - Uses `f"\\r{' ' * (len(msg) + 5)}\\r"` which may not fully clear the spinner line
  - `locr/cli.py` uses `shutil.get_terminal_size().columns` which is the correct approach

- [ ] **`rtree/engine.py` passes both dirs and files to `git_check_ignore`**
  - Passes ALL candidates (including directory paths ending in `/`) to `git_check_ignore`
  - `git check-ignore` may not correctly handle paths with trailing slash
  - `locr/engine.py` correctly filters to files only before calling `git_check_ignore`

- [ ] **`gitmig/engine.py` skipped dir counting walks entire excluded subtree**
  - Lines 244-249: When a directory is excluded, it walks the entire excluded tree just to count files
  - This defeats the purpose of eager pruning and causes a performance hit on large `node_modules`

- [ ] **`gitmig/engine.py` missing newline at end of `_print_stats` method**
  - The `_print_stats` method (line 667-690) is missing the final newline, file ends abruptly after the last print statement

- [ ] **`gitmig/cli.py` missing KeyboardInterrupt handler in `main()`**
  - `locr` and `rtree` both wrap `run(args)` in try/except KeyboardInterrupt in their `main()`
  - `gitmig/cli.py` `main()` calls `run(args)` directly without a KeyboardInterrupt handler
  - The handler is inside `run()` but it re-raises via `sys.exit(1)`, so traceback is still possible

- [ ] **`core/git_utils.py` `simple_gitignore_match` doesn't handle negation correctly**
  - The function iterates all patterns and sets `ignored = not is_negation`
  - A negation pattern (`!pattern`) should un-ignore a previously matched path
  - But the current logic lets any subsequent non-negation pattern re-ignore it, which is correct per gitignore spec
  - However, the anchored flag from `compile_gitignore_patterns` is never used — anchored patterns (`/foo`) should only match at root level but are treated as unanchored

- [ ] **`rtree/engine.py` `_read_and_compile_gitignore` returns incompatible tuples**
  - Returns `(pattern, is_dir, anchored)` tuples
  - But `simple_gitignore_match` from core expects `(pattern, is_negation, is_dir_only)` tuples
  - The third field is `anchored` vs `is_dir_only` — completely different semantics
  - This means fallback gitignore matching (when not in a git repo) is broken for rtree

---

## Inconsistencies

- [ ] **Version mismatch in `COMMANDS.md`**
  - `COMMANDS.md` header says `Version: 1.0.0`
  - All other docs (README, CHANGELOG, DEVELOPMENT, TASKS, `__init__.py`) say `1.1.0`

- [ ] **`locr` color behavior is inverted vs doc**
  - COMMANDS.md, locr README, and main README document `locr --color` to enable color
  - Code has `--no-color` flag (opt-out) and colors are auto-enabled when not writing to file and stdout is a tty
  - So color is effectively **on by default** in terminal, but docs suggest it needs to be enabled

- [ ] **`--raw` flag has different semantics across tools**
  - `rtree --raw`: Include everything, ignore .gitignore rules (shows all files including `.git` contents)
  - `locr --raw`: Ignore .gitignore rules (counts all code files)
  - `gitmig --raw`: Include gitignored files **but still exclude dependency dirs** — different behavior!
  - COMMANDS.md documents gitmig `--raw` correctly, but the inconsistency should be acknowledged

- [ ] **Target path argument naming is inconsistent**
  - `rtree`: uses `--repo` / `-r` for target
  - `locr`: uses positional `path`
  - `gitmig`: uses positional `paths` (supports 0-2 args)
  - None of them use the same convention

- [ ] **`--out` / `-o` behavior differs**
  - `rtree -o`: writes to auto-named file in **current directory** (not target dir)
  - `locr -o`: writes to auto-named file in **target directory**
  - Different output locations for the same flag convention

- [ ] **`DEVELOPMENT.md` references non-existent `config.py` in gitmig**
  - Architecture diagram shows `gitmig/config.py` — this file doesn't exist
  - `gitmig/README.md` also references `config.py` in its module structure
  - Preserve patterns are actually in `core/patterns.py`

- [ ] **`locr/engine.py` has its own scanning logic instead of using `core/git_utils.collect_files_with_pruning`**
  - Despite the refactoring to a shared core, locr reimplements file collection with its own `_collect_and_filter_files` method
  - Same for rtree (`_collect_candidates` + `_scan_repo`)
  - Same for gitmig (`_scan_repo`)
  - The shared `collect_files_with_pruning` in `core/git_utils.py` is defined but **never used** by any tool

- [ ] **`locr/engine.py` has redundant `_simple_gitignore_match` wrapper**
  - Wraps `core.git_utils.simple_gitignore_match`; but its internal `_load_default_patterns` returns tuples with `(pattern, is_dir, anchored)` — which is a different format than what `simple_gitignore_match` expects `(pattern, is_negation, is_dir_only)`
  - This means locr's eager pruning with gitignore patterns may produce incorrect results

- [ ] **Unused imports in `locr/engine.py`**
  - `subprocess` is imported but never used (git subprocess calls go through `core/git_utils`)

- [ ] **`EXCLUDE_FILE_PATTERNS` from core only used by gitmig**
  - `core/patterns.py` defines `EXCLUDE_FILE_PATTERNS` for file-level exclusions
  - Only `gitmig/engine.py` uses it; `locr` and `rtree` never check file patterns
  - This means `*.log`, `*.pyc`, etc. would still appear in rtree output and be counted by locr

- [ ] **`PRESERVE_PATTERNS` from core only used by gitmig**
  - `core/patterns.py` defines `PRESERVE_PATTERNS` for `.env`, `.gitignore` preservation
  - Only relevant to gitmig's copy logic; not used by locr or rtree (which makes sense)
  - But it's in core as if it were shared

- [ ] **`rtree/engine.py` `.git` handling is inconsistent with core**
  - Core's `EXCLUDE_DIRS` includes `.git`
  - But `rtree/engine.py` handles `.git` as a special case (line 113) separately from `EXCLUDE_DIRS` check
  - If `.git` is in `EXCLUDE_DIRS`, the fnmatch check would also catch it, making the special-case redundant yet inconsistent

---

## Code Quality

- [ ] **`rtree/engine.py` contains leftover review comments in production code**
  - Line 70: `# directory check logic`
  - Line 71-72: `# wait, collect logic needs to be consistent` / `# let's assume collect returns "foo/bar" for file...`
  - Line 172: `# Sort paths to ensure parents process before children?`
  - Line 218-220: `# Files first or dirs first?` / `# The previous implementation mixed them...`
  - These read like dev notes/thinking-out-loud, not documentation

- [ ] **`rtree/engine.py` line 157 multi-statement on one line**
  - `if is_dir: line = line[:-1]` and `if anchored: line = line[1:]` on single lines
  - Inconsistent with the rest of the codebase style

- [ ] **`gitmig/engine.py` has inconsistent dir removal approach**
  - Uses `dirnames.remove(d)` in a separate loop (lines 252-253)
  - Other tools use `dirnames[:] = active_dirs` (slice assignment) which is the idiomatic pattern
  - The `remove()` approach is O(n²) and can fail with duplicates

- [ ] **`gitmig/engine.py` uses `os.path.getsize` for skipped dir counting**
  - Lines 244-246: Walks excluded dirs with `os.walk` just to count files
  - This is expensive for large directories like `node_modules` (walks millions of entries)

- [ ] **No `.env.example` file**
  - GEMINI.md rules require `.env.example` with placeholder values if `.env` is mentioned
  - The project references `.env` files extensively in code and docs

---

## Documentation

- [ ] **COMMANDS.md `gtrmrs --version` shows `1.0.0`**
  - Example output `gtrmrs 1.0.0` should be `gtrmrs 1.1.0`

- [ ] **`locr/README.md` documents `--color` / `-c` flag that doesn't exist**
  - Arguments table lists `--color | -c | Enable colored output`
  - Main README also shows `locr src --color`
  - COMMANDS.md shows `locr --color` and `locr -c`
  - Actual code: only `--no-color` exists

- [ ] **`gitmig/README.md` references non-existent `config.py`**
  - Module structure lists `config.py — Preserve patterns`
  - File doesn't exist; patterns are in `core/patterns.py`

- [ ] **`DEVELOPMENT.md` references non-existent `config.py`**
  - Architecture shows `config.py` in gitmig tree — doesn't exist

- [ ] **`--stats-all` flag not documented in gitmig README**
  - `gitmig/cli.py` has `--stats-all` flag
  - COMMANDS.md documents it but `gitmig/README.md` arguments table omits it

- [ ] **`gitmig` `--no-color` flag not available**
  - `rtree` has `--no-color`, `locr` has `--no-color`
  - `gitmig` has no color control flag — always uses color

---

## Future

- [ ] **Testing**
  - [ ] Create unified `tests/` directory
  - [ ] Port existing tests from old projects
  - [ ] Add tests for shared core module
  - [ ] Add tests for gitmig new features

- [ ] **Performance**
  - [ ] Add parallel processing to locr
  - [ ] Benchmark improvements

- [ ] **CI/CD**
  - [ ] GitHub Actions workflow
  - [ ] Test matrix: Python 3.8, 3.10, 3.12
  - [ ] Lint/format checks

- [ ] **Long-term**
  - [ ] Plugin system for custom language definitions
  - [ ] Plugin system for custom exclusion patterns
