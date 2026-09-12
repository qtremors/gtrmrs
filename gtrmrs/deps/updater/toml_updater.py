"""
toml_updater.py

Safe in-place updater for gradle/libs.versions.toml and gradle-wrapper.properties.
Preserves existing comments, whitespace, and formatting.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from gtrmrs.deps.models import UpdateAction


class CatalogUpdater:
    """Safely updates version catalog TOML files and Gradle wrappers in-place."""

    def update_version_ref(
        self, toml_path: str, ref_name: str, new_version: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Updates a version definition in the [versions] section of a TOML file.
        
        Returns (success, old_version, new_content).
        """
        if not os.path.exists(toml_path):
            return False, None, None

        try:
            with open(toml_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except OSError:
            return False, None, None

        in_versions_section = False
        pattern = re.compile(rf"^(\s*{re.escape(ref_name)}\s*=\s*[\"'])([^\"']+)([\"'].*)$")
        old_version = None
        updated = False
        new_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                sec = stripped[1:-1].strip()
                in_versions_section = (sec == "versions")
                new_lines.append(line)
                continue

            if in_versions_section and not updated:
                m = pattern.match(line)
                if m:
                    prefix, old_version, suffix = m.group(1), m.group(2), m.group(3)
                    new_lines.append(f"{prefix}{new_version}{suffix}\n" if not suffix.endswith("\n") else f"{prefix}{new_version}{suffix}")
                    updated = True
                    continue

            new_lines.append(line)

        if updated:
            return True, old_version, "".join(new_lines)
        return False, None, None

    def update_inline_library_or_plugin(
        self, toml_path: str, section: str, alias: str, new_version: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Updates an inline version in [libraries] or [plugins] section."""
        if not os.path.exists(toml_path):
            return False, None, None

        try:
            with open(toml_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except OSError:
            return False, None, None

        in_target_section = False
        alias_pattern = re.compile(rf"^(\s*{re.escape(alias)}\s*=)(.*)$")
        old_version = None
        updated = False
        new_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                sec = stripped[1:-1].strip()
                in_target_section = (sec == section)
                new_lines.append(line)
                continue

            if in_target_section and not updated:
                m = alias_pattern.match(line)
                if m:
                    prefix, rest = m.group(1), m.group(2)
                    # Check if string coordinate: "group:artifact:1.2.3"
                    m_str = re.search(r"([\"'][^\"']+:[^\"']+:)([^\"']+)([\"'])", rest)
                    if m_str:
                        old_version = m_str.group(2)
                        new_rest = rest[:m_str.start(2)] + new_version + rest[m_str.end(2):]
                        new_lines.append(f"{prefix}{new_rest}")
                        updated = True
                        continue
                    # Check version = "1.2.3"
                    m_ver = re.search(r"(version\s*=\s*[\"'])([^\"']+)([\"'])", rest)
                    if m_ver:
                        old_version = m_ver.group(2)
                        new_rest = rest[:m_ver.start(2)] + new_version + rest[m_ver.end(2):]
                        new_lines.append(f"{prefix}{new_rest}")
                        updated = True
                        continue

            new_lines.append(line)

        if updated:
            return True, old_version, "".join(new_lines)
        return False, None, None

    def update_gradle_wrapper(
        self, project_path: str, new_version: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Updates distributionUrl in gradle-wrapper.properties."""
        prop_path = os.path.join(project_path, "gradle", "wrapper", "gradle-wrapper.properties")
        if not os.path.exists(prop_path):
            return False, None, None

        try:
            with open(prop_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except OSError:
            return False, None, None

        old_version = None
        updated = False
        new_lines: List[str] = []

        for line in lines:
            if "distributionUrl" in line and not updated:
                m = re.search(r"gradle-([\d\.]+)-(?:bin|all)\.zip", line)
                if m:
                    old_version = m.group(1)
                    new_line = line[:m.start(1)] + new_version + line[m.end(1):]
                    new_lines.append(new_line)
                    updated = True
                    continue
            new_lines.append(line)

        if updated:
            return True, old_version, "".join(new_lines)
        return False, None, None

    def apply_action(self, action: UpdateAction, dry_run: bool = False) -> bool:
        """Applies a single planned update action. Returns True on success."""
        if action.component_identifier.startswith("Gradle Wrapper"):
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(action.file_path)))
            success, old_v, content = self.update_gradle_wrapper(project_dir, action.new_version)
        elif action.is_version_ref and action.ref_name:
            success, old_v, content = self.update_version_ref(
                action.file_path, action.ref_name, action.new_version
            )
        else:
            # Inline alias
            section = "plugins" if "plugin" in action.component_identifier.lower() else "libraries"
            success, old_v, content = self.update_inline_library_or_plugin(
                action.file_path, section, action.key_or_alias, action.new_version
            )

        if success and content is not None and not dry_run:
            try:
                target_path = action.file_path
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return True
            except OSError:
                return False
        return success
