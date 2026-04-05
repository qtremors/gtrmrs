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

Android files include Gradle, Kotlin scripts, AIDL, ProGuard, properties and XML.

Mixed comments and code, Python strings and nested Kotlin, Rust and Swift block comments are recognized. Invalid UTF-8 and unreadable files are excluded from successful totals.

[All commands](../../COMMANDS.md) | [Project](../../README.md)
