"""
toml_updater.py

Safe in-place updater for gradle/libs.versions.toml and gradle-wrapper.properties.
Preserves existing comments, whitespace, and formatting.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from gtrmrs.deps.models import UpdateAction
from gtrmrs.deps.scanners import android
from gtrmrs.deps.scanners.wrapper import checksum_url, distribution, wrapper_properties


_SECTION_HEADER = re.compile(r"^\s*\[([A-Za-z0-9_-]+)\]\s*(?:#.*)?$")


class CatalogUpdater:
    """Safely updates version catalog TOML files and Gradle wrappers in-place."""

    def __init__(self):
        self.last_errors: Dict[str, str] = {}

    @staticmethod
    def _read_lines(path: str, content: Optional[str]) -> List[str]:
        if content is None:
            with open(path, "r", encoding="utf-8", newline="") as handle:
                content = handle.read()
        return content.splitlines(keepends=True)

    def update_version_ref(
        self, toml_path: str, ref_name: str, new_version: str, content: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Updates a version definition in the [versions] section of a TOML file.

        Returns (success, old_version, new_content).
        """
        if not os.path.exists(toml_path):
            return False, None, None

        try:
            lines = self._read_lines(toml_path, content)
        except (OSError, UnicodeError):
            return False, None, None

        in_versions_section = False
        pattern = re.compile(rf"^(\s*{re.escape(ref_name)}\s*=\s*[\"'])([^\"']+)([\"'].*)$")
        old_version = None
        updated = False
        new_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("["):
                header = _SECTION_HEADER.match(stripped)
                in_versions_section = bool(header and header.group(1) == "versions")
                new_lines.append(line)
                continue

            if in_versions_section and not updated:
                m = pattern.match(line)
                if m:
                    old_version = m.group(2)
                    new_lines.append(line[:m.start(2)] + new_version + line[m.end(2):])
                    updated = True
                    continue

            new_lines.append(line)

        if updated:
            return True, old_version, "".join(new_lines)
        return False, None, None

    def update_inline_library_or_plugin(
        self, toml_path: str, section: str, alias: str, new_version: str, content: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Updates an inline version in [libraries] or [plugins] section."""
        if not os.path.exists(toml_path):
            return False, None, None

        try:
            lines = self._read_lines(toml_path, content)
        except (OSError, UnicodeError):
            return False, None, None

        in_target_section = False
        alias_pattern = re.compile(rf"^(\s*{re.escape(alias)}\s*=)(.*)$", re.DOTALL)
        old_version = None
        updated = False
        new_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("["):
                header = _SECTION_HEADER.match(stripped)
                in_target_section = bool(header and header.group(1) == section)
                new_lines.append(line)
                continue

            if in_target_section and not updated:
                m = alias_pattern.match(line)
                if m:
                    prefix, rest = m.group(1), m.group(2)
                    # Check if string coordinate: "group:artifact:1.2.3"
                    coordinate = r"([\"'][^\"']+:[^\"']+:)([^\"']+)([\"'])" if section == "libraries" else r"([\"'][^\"']+:)([^\"']+)([\"'])"
                    m_str = re.match(r"\s*" + coordinate, rest)
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
        self, project_path: str, new_version: str, content: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Updates distributionUrl in gradle-wrapper.properties."""
        prop_path = os.path.join(project_path, "gradle", "wrapper", "gradle-wrapper.properties")
        if not os.path.exists(prop_path):
            return False, None, None

        try:
            lines = self._read_lines(prop_path, content)
        except (OSError, UnicodeError):
            return False, None, None

        source = "".join(lines)
        try:
            properties = wrapper_properties(source)
            prop = properties.get("distributionUrl")
            info = distribution(prop.value) if prop else None
            if not info or info.span is None or prop.continued:
                return False, info.version if info else None, None
            if not re.fullmatch(r"\d+(?:\.\d+)*(?:[-+][A-Za-z0-9][A-Za-z0-9._+-]*)?", new_version):
                return False, info.version, None
            first, end = info.span
            updated_url = prop.value[:first] + new_version + prop.value[end:]
            changes = [(prop.spans[first][0], prop.spans[end - 1][1], new_version)]
            pinned = properties.get("distributionSha256Sum")
            if pinned:
                if pinned.continued:
                    return False, info.version, None
                # Fetch the checksum beside the exact updated distribution,
                # preserving its host, archive type and query parameters.
                with urllib.request.urlopen(checksum_url(updated_url), timeout=10) as response:
                    checksum = response.read().decode("ascii").strip()
                if not re.fullmatch(r"[0-9a-fA-F]{64}", checksum):
                    return False, info.version, None
                if pinned.spans:
                    changes.append((pinned.spans[0][0], pinned.spans[-1][1], checksum))
                else:
                    changes.append((pinned.start, pinned.start, checksum))
            for start, stop, replacement in sorted(changes, reverse=True):
                source = source[:start] + replacement + source[stop:]
            prepared = wrapper_properties(source)
            result = distribution(prepared["distributionUrl"].value)
            if not result or result.version != new_version or result.kind != info.kind:
                return False, info.version, None
            if pinned and prepared["distributionSha256Sum"].value != checksum:
                return False, info.version, None
            return True, info.version, source
        except (OSError, ValueError, UnicodeError):
            return False, None, None

    def apply_action(self, action: UpdateAction, dry_run: bool = False) -> bool:
        """Applies a single planned update action. Returns True on success."""
        return self.apply_actions([action], dry_run=dry_run)[0][1]

    @staticmethod
    def _catalog_data(content: str) -> Dict[str, Any]:
        if android.tomllib is None:
            raise ValueError("Safe catalog updates require the Python 3.11+ standard-library TOML parser")
        return android.tomllib.loads(content)

    @staticmethod
    def _entry(data: Dict[str, Any], section: str, action: UpdateAction) -> Tuple[Optional[str], Any]:
        table = data.get(section, {})
        if not isinstance(table, dict):
            raise ValueError("Unsupported catalog section: " + section)
        entry = table.get(action.key_or_alias)
        if isinstance(entry, str):
            parts = entry.split(":")
            width = 2 if section == "libraries" else 1
            return ":".join(parts[:width]), parts[width] if len(parts) == width + 1 else None
        if isinstance(entry, dict):
            identifier = entry.get("id") if section == "plugins" else entry.get("module") or "{}:{}".format(entry.get("group", ""), entry.get("name", ""))
            return identifier, entry.get("version")
        return None, None

    def _section(self, data: Dict[str, Any], action: UpdateAction) -> str:
        if action.component_type in ("library", "plugin"):
            return "plugins" if action.component_type == "plugin" else "libraries"
        if action.component_type is not None:
            raise ValueError("Unsupported component type: " + action.component_type)
        # Legacy callers without a type are matched to actual catalog coordinates.
        matches = [section for section in ("libraries", "plugins") if self._entry(data, section, action)[0] == action.component_identifier]
        if len(matches) != 1:
            raise ValueError("Cannot identify a unique catalog entry for " + action.key_or_alias)
        return matches[0]

    def _version(self, data: Dict[str, Any], action: UpdateAction) -> str:
        if action.is_version_ref:
            versions = data.get("versions", {})
            if not isinstance(versions, dict):
                raise ValueError("Unsupported versions section")
            value = versions.get(action.ref_name)
        else:
            section = self._section(data, action)
            identifier, value = self._entry(data, section, action)
            if identifier != action.component_identifier:
                raise ValueError("Catalog entry no longer matches " + action.component_identifier)
        if not isinstance(value, str):
            raise ValueError("Missing or unsupported version for " + (action.ref_name or action.key_or_alias))
        from gtrmrs.deps.scanners.catalog import _version
        if _version(value, {}, True)["version_kind"] != "literal":
            raise ValueError("Only fixed version declarations can be updated")
        return value

    def _prepare(self, actions: List[UpdateAction], original: str) -> str:
        wrappers = [action.component_type == "build_tool" or (action.component_type is None and action.component_identifier.startswith("Gradle Wrapper")) for action in actions]
        if any(wrappers) and not all(wrappers):
            raise ValueError("Cannot mix wrapper and catalog actions in one file")
        data = {} if all(wrappers) else self._catalog_data(original)
        content = original
        for action in actions:
            if all(wrappers) and not re.fullmatch(r"\d+(?:\.\d+)*(?:[-+][A-Za-z0-9][A-Za-z0-9._+-]*)?", action.new_version):
                raise ValueError("Invalid Gradle distribution version: " + action.new_version)
            if not all(wrappers) and self._version(data, action) != action.old_version:
                raise ValueError("Version changed since planning: " + (action.ref_name or action.key_or_alias))
            if all(wrappers):
                project = os.path.dirname(os.path.dirname(os.path.dirname(action.file_path)))
                success, old, updated = self.update_gradle_wrapper(project, action.new_version, content=content)
            elif action.is_version_ref and action.ref_name:
                success, old, updated = self.update_version_ref(action.file_path, action.ref_name, action.new_version, content=content)
            else:
                success, old, updated = self.update_inline_library_or_plugin(
                    action.file_path, self._section(data, action), action.key_or_alias, action.new_version, content=content,
                )
            if not success or updated is None:
                raise ValueError("Could not prepare update for " + (action.ref_name or action.key_or_alias))
            if old != action.old_version:
                raise ValueError("Version changed since planning: " + (action.ref_name or action.key_or_alias))
            content = updated
        if not all(wrappers):
            updated_data = self._catalog_data(content)
            for action in actions:
                if self._version(updated_data, action) != action.new_version:
                    raise ValueError("Prepared catalog does not contain the requested version for " + action.key_or_alias)
        return content

    @staticmethod
    def _read_state(path: str) -> Tuple[bytes, os.stat_result]:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Update target must be a regular file, not a link")
        if not info.st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            raise ValueError("Update target is read-only: " + path)
        with open(path, "rb") as handle:
            return handle.read(), info

    def _unchanged(self, path: str, original: bytes, identity: os.stat_result) -> None:
        current, info = self._read_state(path)
        if current != original or (info.st_dev, info.st_ino) != (identity.st_dev, identity.st_ino):
            raise ValueError("File changed while preparing updates: " + path)

    def _commit(self, path: str, original: bytes, identity: os.stat_result, content: str) -> None:
        descriptor, temporary = tempfile.mkstemp(prefix=".gtrmrs-update-", dir=os.path.dirname(os.path.abspath(path)))
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content.encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, stat.S_IMODE(identity.st_mode))
            self._unchanged(path, original, identity)
            os.replace(temporary, path)
            temporary = ""
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except PermissionError:
                    os.chmod(temporary, stat.S_IWRITE | stat.S_IREAD)
                    os.unlink(temporary)

    def apply_actions(self, actions: List[UpdateAction], dry_run: bool = False) -> List[Tuple[UpdateAction, bool]]:
        """Prepare and validate every edit to a file before one atomic replacement."""
        self.last_errors = {}
        groups: Dict[str, List[Tuple[int, UpdateAction]]] = {}
        successes = [False] * len(actions)
        for index, action in enumerate(actions):
            groups.setdefault(os.path.normcase(os.path.abspath(action.file_path)), []).append((index, action))
        for entries in groups.values():
            file_actions = [action for _, action in entries]
            path = file_actions[0].file_path
            try:
                original, identity = self._read_state(path)
                digest = hashlib.sha256(original).hexdigest()
                if any(action.expected_sha256 and action.expected_sha256 != digest for action in file_actions):
                    raise ValueError("File changed since planning: " + path)
                content = self._prepare(file_actions, original.decode("utf-8"))
                if dry_run:
                    self._unchanged(path, original, identity)
                else:
                    self._commit(path, original, identity, content)
                for index, _ in entries:
                    successes[index] = True
            except (OSError, UnicodeError, ValueError) as exc:
                for action in file_actions:
                    self.last_errors[action.file_path] = str(exc)
        return [(action, successes[index]) for index, action in enumerate(actions)]
