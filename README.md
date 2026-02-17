# gtrmrs

Version 0.0.2. Small, Git-aware tools for everyday repository work.

Requires Python 3.11+. Git-aware operations need Git on PATH. The tools use
Python's standard library and have no third-party runtime dependencies.

## Install

```sh
git clone https://github.com/qtremors/gtrmrs.git
cd gtrmrs
python -m pip install -e .
```

## Use

```sh
rtree --depth 2          # Show a directory tree
locr --stats            # Count source by language
gitmig ../backup --dry-run  # Preview a repository copy
```

Run each command directly or through `gtrmrs`, for example `gtrmrs locr`.
Use `--help` on a command to see its available options.

```sh
gitmig --git-size       # Inspect Git metadata sizes
```

## Guides

- [Commands](COMMANDS.md)
- [Development](DEVELOPMENT.md)
- [Directory trees](gtrmrs/rtree/README.md)
- [Code counts](gtrmrs/locr/README.md)
- [Repository copies](gtrmrs/gitmig/README.md)
- [Changelog](CHANGELOG.md)
- [License](LICENSE.md)
