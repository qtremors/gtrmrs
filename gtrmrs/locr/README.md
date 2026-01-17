# locr

Count source files by language. Reports separate blank, comment and code lines.
Git-aware scans honor project ignore rules; `--raw` disables normal filtering.

```sh
locr
locr --stats
locr --raw
locr --json --out counts.json
locr --no-color
```

Output paths use the shell working directory. Counting is lexical, not a compiler.

[All commands](../../COMMANDS.md) | [Project](../../README.md)
