"""Physical-line classification without interpreting or executing source code."""

import tokenize
from collections import Counter


def _python_lines(lines):
    source = iter(lines)
    pending = {}
    row = 0
    first = 1

    def readline():
        nonlocal row
        line = next(source, "")
        if line:
            row += 1
            pending[row] = [bool(line.strip()), None]
        return line

    def completed(before):
        nonlocal first
        while pending and first < before:
            nonblank, kind = pending.pop(first)
            first += 1
            yield kind or ("code" if nonblank else "blank")

    ignored = {tokenize.ENCODING, tokenize.ENDMARKER, tokenize.INDENT,
               tokenize.DEDENT, tokenize.NEWLINE, tokenize.NL}
    try:
        for token in tokenize.generate_tokens(readline):
            yield from completed(token.start[0])
            if token.type in ignored:
                continue
            kind = "comment" if token.type == tokenize.COMMENT else "code"
            last = token.end[0] - (token.end[1] == 0)
            for number in range(token.start[0], last + 1):
                if number in pending and pending[number][1] != "code":
                    pending[number][1] = kind
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # Incomplete source is still countable. Unclassified nonblank lines are code.
        pass
    yield from completed(row + 1)
    # A tokenizer error may leave physical lines unread.
    for line in source:
        yield "code" if line.strip() else "blank"


def count_lines(lines, language):
    """Code wins over comments on mixed lines; Python strings count as code."""
    if language["name"] == "Python":
        kinds = _python_lines(lines)
    else:
        kinds = _generic_lines(lines, language)
    totals = Counter(kinds)
    return tuple(totals[kind] for kind in ("blank", "comment", "code"))


def _generic_lines(lines, language):
    single = language.get("single")
    start, end = language.get("multi") or (None, None)
    if not single and not start and language["name"] != "Batch":
        for line in lines:
            yield "code" if line.strip() else "blank"
        return
    nested = language["name"] in {"Kotlin", "Kotlin Script", "Rust", "Swift"}
    block_depth = 0
    quote = None
    for line in lines:
        has_code = bool(quote)
        has_comment = bool(block_depth)
        index = 0
        if language["name"] == "Batch":
            stripped = line.lstrip().lower()
            yield ("blank" if not stripped.strip() else "comment" if
                   stripped.startswith("::") or stripped.rstrip() == "rem" or
                   stripped.startswith(("rem ", "rem\t")) else "code")
            continue
        while index < len(line):
            if block_depth:
                has_comment = True
                if line.startswith(end, index):
                    block_depth -= 1
                    index += len(end)
                elif nested and line.startswith(start, index):
                    block_depth += 1
                    index += len(start)
                else:
                    index += 1
            elif quote:
                has_code = True
                if line[index] == "\\":
                    index += 2
                elif line.startswith(quote, index):
                    index += len(quote)
                    quote = None
                else:
                    index += 1
            elif start and line.startswith(start, index):
                has_comment = True
                block_depth = 1
                index += len(start)
            elif single and line.startswith(single, index):
                has_comment = True
                break
            elif line[index] in "\"'`":
                has_code = True
                quote = line[index]
                if language["name"] in {"Kotlin", "Kotlin Script", "Gradle", "Swift", "TOML"} and line.startswith(quote * 3, index):
                    quote *= 3
                index += len(quote)
            else:
                has_code |= not line[index].isspace()
                index += 1
        # Ordinary quotes do not persist across physical lines in C-family code.
        if quote and len(quote) == 1 and quote != "`" and language["name"] not in {"Shell", "PowerShell"}:
            if not line.rstrip("\r\n").endswith("\\"):
                quote = None
        yield "code" if has_code else "blank" if not line.strip() else "comment" if has_comment else "code"
