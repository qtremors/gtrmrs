"""Read literal SDK settings without executing Gradle or evaluating expressions."""

from __future__ import annotations

import re


def _code_and_strings(text: str) -> tuple[str, dict[int, str]]:
    """Mask comments/quoted strings while retaining offsets and line breaks."""
    code = list(text)
    strings = {}
    index = 0
    while index < len(text):
        start = index
        if text.startswith("//", index):
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
        elif text.startswith("/*", index):
            index += 2
            depth = 1
            while index < len(text) and depth:
                if text.startswith("/*", index):
                    depth += 1
                    index += 2
                elif text.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
        elif text[index] in "\"'":
            quote = text[index]
            delimiter = quote * 3 if text.startswith(quote * 3, index) else quote
            index += len(delimiter)
            value_start = index
            while index < len(text):
                if text.startswith(delimiter, index):
                    strings[start] = text[value_start:index]
                    index += len(delimiter)
                    break
                if text[index] == "\\" and len(delimiter) == 1:
                    index += 2
                else:
                    index += 1
        else:
            index += 1
            continue
        for position in range(start, min(index, len(text))):
            if text[position] not in "\r\n":
                code[position] = " "
        if start in strings:
            code[start] = "@"
    return "".join(code), strings


def sdk_literals(text: str) -> tuple[dict[str, set[str]], list[tuple[int, str]]]:
    """Return numeric Android SDK literals and locations of unresolved settings.

    Supports Kotlin/Groovy assignments, calls, Groovy space syntax, and .set().
    Only Android blocks or explicit android.SDK properties are considered.
    """
    code, strings = _code_and_strings(text)
    result = {key: set() for key in ("compileSdk", "targetSdk", "minSdk")}
    unresolved = []
    android_braces = {match.end() - 1 for match in re.finditer(r"\bandroid\s*\{", code)}
    scopes = []
    tokens = re.finditer(r"[{}]|\b(?:compileSdk|targetSdk|minSdk)(?:Version)?\b", code)
    for token in tokens:
        value = token.group()
        if value == "{":
            scopes.append(token.start() in android_braces or bool(scopes and scopes[-1]))
            continue
        if value == "}":
            if scopes:
                scopes.pop()
            continue
        prefix = code[:token.start()]
        if not (scopes and scopes[-1]) and not re.search(r"\bandroid\s*\.\s*$", prefix):
            continue
        if re.search(r"\b(?:val|var|def)\s*$", prefix):
            continue
        after = code[token.end():]
        form = re.match(r"\s*(?:\.\s*set\s*\(\s*|\(\s*|=\s*)", after)
        called = form is not None and "(" in form.group()
        if form:
            position = token.end() + form.end()
        else:
            # Groovy: minSdkVersion 24. Reads/calls such as minSdk.get() are not settings.
            space = re.match(r"[ \t]+(?=[\w@])", after)
            if not space:
                continue
            position = token.end() + space.end()
        key = value.removesuffix("Version")
        number = re.match(r"[0-9]+(?:_[0-9]+)*", code[position:])
        if number:
            literal = number.group().replace("_", "")
            end = position + number.end()
        elif position in strings and re.fullmatch(r"(?:android-)?[0-9]+", strings[position]):
            literal = strings[position].removeprefix("android-")
            end = position + 1
        else:
            literal, end = None, position
        remainder = code[end:]
        close = re.match(r"\s*\)", remainder) if called else None
        if called and close:
            remainder = remainder[close.end():]
        complete = re.match(r"[ \t\r]*(?:[;}]|\n|$)", remainder) is not None
        if literal is not None and complete and (not called or close):
            result[key].add(str(int(literal)))
        else:
            unresolved.append((text.count("\n", 0, token.start()) + 1, key))
    return result, unresolved
