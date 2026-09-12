"""Shared Java-properties and Gradle distribution reading for audits and edits."""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import unquote, urlsplit, urlunsplit


@dataclass
class Property:
    value: str
    spans: list[tuple[int, int]]
    continued: bool
    start: int


def _decode(value: str, offset: int) -> tuple[str, list[tuple[int, int]]]:
    decoded, spans = [], []
    index = 0
    while index < len(value):
        start = index
        char = value[index]
        index += 1
        if char == "\\":
            if index == len(value):
                raise ValueError("Dangling properties escape")
            char = value[index]
            index += 1
            if char == "u":
                digits = value[index:index + 4]
                if not re.fullmatch(r"[0-9a-fA-F]{4}", digits):
                    raise ValueError("Invalid Unicode escape in properties")
                char = chr(int(digits, 16))
                index += 4
            else:
                char = {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}.get(char, char)
        decoded.append(char)
        spans.append((offset + start, offset + index))
    return "".join(decoded), spans


def wrapper_properties(content: str) -> dict[str, Property]:
    """Read effective properties, including comments, escapes and continuations.

    Later definitions win, as with Java Properties. Edits to continued settings
    are deliberately refused; their offsets are for reading only.
    """
    properties = {}
    lines = re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", content)
    if lines and not lines[-1]:
        lines.pop()
    offset = 0
    index = 0
    while index < len(lines):
        first = lines[index]
        start = offset
        index += 1
        offset += len(first)
        line = first.rstrip("\r\n")
        if not line.lstrip(" \t\f") or line.lstrip(" \t\f").startswith(("#", "!")):
            continue
        continued = False
        while (len(line) - len(line.rstrip("\\"))) % 2:
            continued = True
            line = line[:-1]
            if index == len(lines):
                break
            following = lines[index]
            index += 1
            offset += len(following)
            line += following.rstrip("\r\n").lstrip(" \t\f")
        key_start = len(line) - len(line.lstrip(" \t\f"))
        end = key_start
        while end < len(line) and line[end] not in " \t\f=:":
            end += 2 if line[end] == "\\" else 1
        key, _ = _decode(line[key_start:end], start + key_start)
        position = end
        while position < len(line) and line[position] in " \t\f":
            position += 1
        if position < len(line) and line[position] in "=:":
            position += 1
        while position < len(line) and line[position] in " \t\f":
            position += 1
        value, spans = _decode(line[position:], start + position)
        properties[key] = Property(value, spans, continued, start + position)
    return properties


@dataclass
class Distribution:
    version: str
    kind: str
    # Encoded archive names can be read but have no safe literal edit span.
    span: tuple[int, int] | None


def distribution(value: str) -> Distribution | None:
    if any(char.isspace() or ord(char) < 32 for char in value):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    archive = parsed.path.rsplit("/", 1)[-1]
    name = unquote(archive)
    match = re.fullmatch(r"gradle-(\d+(?:\.\d+)*(?:-[A-Za-z0-9][A-Za-z0-9.+-]*)?)-(bin|all)\.zip", name)
    if not match:
        return None
    resource_end = min((value.find(char) for char in "?#" if char in value), default=len(value))
    base = resource_end - len(archive)
    span = (base + match.start(1), base + match.end(1)) if name == archive else None
    return Distribution(match.group(1), match.group(2), span)


def checksum_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in ("https", "http", "file"):
        raise ValueError("Checksum lookup requires an absolute distribution URL")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path + ".sha256", parsed.query, ""))
