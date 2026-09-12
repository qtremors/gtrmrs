"""
base.py

Abstract base scanner for project dependencies across ecosystems.
"""

from __future__ import annotations

import abc
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from gtrmrs.deps.models import ProjectProfile


_QUALIFIERS = {
    "dev": -70, "ea": -60, "eap": -60, "alpha": -50, "a": -50,
    "beta": -40, "b": -40, "milestone": -30, "m": -30, "preview": -25,
    "rc": -20, "cr": -20, "snapshot": -10,
}
_FINAL = {"final", "ga", "release"}
VersionKey = Tuple[Tuple[int, ...], int, Tuple[Tuple[int, int, str], ...]]


def _known_qualifier(tokens: List[str], index: int) -> bool:
    token = tokens[index]
    return token in _QUALIFIERS and (token not in ("a", "b", "m")
                                     or index + 1 < len(tokens) and tokens[index + 1].isdigit())


@lru_cache(maxsize=4096)
def _version_parts(value: str) -> Tuple[Tuple[int, ...], str]:
    value = re.sub(r"^[vV](?=\d)", "", value.strip().split("+", 1)[0])
    match = re.fullmatch(r"(\d+(?:\.\d+)*)([._-]?[A-Za-z][A-Za-z0-9._-]*|[-_][0-9][A-Za-z0-9._-]*)?", value)
    if not match:
        return (-9999,), value
    numbers = [int(part) for part in match.group(1).split(".")]
    while len(numbers) < 3:
        numbers.append(0)
    while len(numbers) > 3 and numbers[-1] == 0:
        numbers.pop()
    return tuple(numbers), (match.group(2) or "").lstrip("._-").lower()


def parse_semver(v: Optional[str]) -> VersionKey:
    """Comparable key for common numeric, date, and qualified releases.

    Build metadata has no precedence. Qualifier counters compare numerically,
    common Maven/Android aliases share ranks, and finals follow prereleases.
    This is not a full implementation of every ecosystem's version scheme.
    """
    if not v or v in ("None", "N/A"):
        return (-9999,), 0, ()
    numbers, suffix = _version_parts(str(v))
    if numbers != (-9999,) and (not suffix or suffix in _FINAL):
        return numbers, 1, ()
    tokens = re.findall(r"[a-z]+|\d+", suffix)
    qualifiers = tuple((0, int(token), "") if token.isdigit()
                       else (1, _QUALIFIERS[token], "") if _known_qualifier(tokens, index)
                       else (1, 0, token) for index, token in enumerate(tokens))
    return numbers, 0, qualifiers


def is_preview_version(v: Optional[str]) -> bool:
    """Checks if a version represents a pre-release or preview build."""
    if not v:
        return False
    _, suffix = _version_parts(str(v))
    tokens = re.findall(r"[a-z]+|\d+", suffix)
    return any(_known_qualifier(tokens, index) for index in range(len(tokens)))


class BaseScanner(abc.ABC):
    """Abstract base class for ecosystem dependency scanners."""

    @property
    @abc.abstractmethod
    def ecosystem_name(self) -> str:
        """Name of the ecosystem, e.g., 'android', 'web', 'desktop'."""
        pass

    @abc.abstractmethod
    def can_scan_project(self, project_path: str) -> bool:
        """Determines if the directory is a project of this ecosystem."""
        pass

    @abc.abstractmethod
    def discover_projects(self, base_dir: str) -> Dict[str, str]:
        """Discovers projects of this ecosystem in base_dir.

        Returns a mapping of project name -> project root directory.
        """
        pass

    @abc.abstractmethod
    def scan_project(self, name: str, path: str) -> Tuple[ProjectProfile, Dict[str, Any]]:
        """Scans an individual project.

        Returns the project profile and a dict with keys:
          - 'libraries': Dict[alias, {group, name, coord, version, is_ref, ref_name}]
          - 'plugins': Dict[alias, {id, version, is_ref, ref_name}]
          - 'raw_versions': Dict[ref_name, version_str]
        """
        pass

    @abc.abstractmethod
    def categorize(self, identifier: str) -> str:
        """Returns a high-level category for a component identifier."""
        pass
