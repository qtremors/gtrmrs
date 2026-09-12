"""
base.py

Abstract base scanner for project dependencies across ecosystems.
"""

from __future__ import annotations

import abc
import re
from typing import Any, Dict, List, Optional, Tuple

from gtrmrs.deps.models import ProjectProfile


def parse_semver(v: Optional[str]) -> Tuple[int, ...]:
    """Parses a version string into a comparable tuple.
    
    Handles semver (1.2.3), date-based versions (2026.08.00),
    and pre-release tags (alpha, beta, rc, dev), ensuring
    stable releases compare higher than pre-releases of the same base.
    """
    if not v or v in ("None", "N/A"):
        return (-9999, 0, 0, 0, 0)

    v_clean = str(v).lstrip("v").strip()
    m = re.match(r"^(\d+(?:\.\d+)*)(?:[\.\-\+_](.+))?$", v_clean)
    if m:
        num_part = m.group(1)
        suffix = m.group(2) or ""
        nums = [int(p) for p in num_part.split(".")]
        while len(nums) < 3:
            nums.append(0)

        if not suffix:
            # Final/stable release: tag score 0
            return tuple(nums + [0, 0])

        s_lower = suffix.lower()
        sub_match = re.search(r"\d+", suffix)
        sub_num = int(sub_match.group(0)) if sub_match else 0

        if "alpha" in s_lower:
            tag_score = -30
        elif "beta" in s_lower:
            tag_score = -20
        elif "rc" in s_lower or "cr" in s_lower:
            tag_score = -10
        elif "m" in s_lower or "preview" in s_lower:
            tag_score = -25
        elif "dev" in s_lower or "snapshot" in s_lower or "ea" in s_lower:
            tag_score = -40
        else:
            tag_score = -5

        return tuple(nums + [tag_score, sub_num])

    # Fallback for non-standard version patterns
    parts = re.split(r"[\.\-\+_]", v_clean)
    nums = [int(p) if p.isdigit() else -1 for p in parts]
    return tuple(nums)


def is_preview_version(v: Optional[str]) -> bool:
    """Checks if a version represents a pre-release or preview build."""
    if not v:
        return False
    v_lower = str(v).lower()
    return any(x in v_lower for x in [
        "alpha", "beta", "rc", "m1", "m2", "m3", "preview", "dev", "snapshot", "ea", "cr"
    ])


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
