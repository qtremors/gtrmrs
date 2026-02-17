# gitmig

Copy repositories without common dependency and cache directories. Keep the
destination outside the source and preview selections before copying.

```sh
gitmig ../backup --dry-run
gitmig ../backup
gitmig ../backup --zip
gitmig ../backup --stats
gitmig --git-size
```

Environment files are preserved by default. Review copied files before sharing them.

[All commands](../../COMMANDS.md) | [Project](../../README.md)
