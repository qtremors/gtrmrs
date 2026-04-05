# Command Guide

> **Version:** 0.0.6
>
> **Last Updated:** 2026-04-05

Commands operate on the current directory unless a path is supplied. Output
filenames are relative to the shell's working directory. Use sibling destinations
for repository copies and inspect `--dry-run` output before copying.

## Directory trees

```sh
rtree
rtree --depth 2
rtree --flat
rtree --raw --no-color
rtree --out tree.txt
```

[Tree guide](gtrmrs/rtree/README.md)

## Lines of code

```sh
locr
locr --stats
locr --json
locr --out counts.txt
locr --no-color
```

[LOC guide](gtrmrs/locr/README.md)

## Repository copies

```sh
gitmig ../backup --dry-run
gitmig ../backup
gitmig ../backup --zip
gitmig ../backup --stats
gitmig --git-size
gitmig ../backup --dry-run --no-color
```

[Migration guide](gtrmrs/gitmig/README.md)
