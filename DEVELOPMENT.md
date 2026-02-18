# Development

> **Version:** 0.0.4
>
> **Last Updated:** 2026-02-18

Use Python 3.11+ and Git. Runtime code uses the standard library. Installation
uses pip and setuptools as build tooling.

```sh
python -m pip install -e .
python -B -m unittest discover -s tests -q
python -m gtrmrs.cli --help
```

`gtrmrs/cli.py` registers the three commands. Each tool has its own CLI and
engine. Shared colors, Git helpers and selection patterns live in `gtrmrs/core/`.
Keep tests offline and place mutations in temporary directories.

Use command-specific `--help` output and [COMMANDS.md](COMMANDS.md) for usage.
