"""
android.py

Android ecosystem scanner for Gradle version catalogs, wrapper, and SDK configurations.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # Handled gracefully if missing

from gtrmrs.deps.models import ProjectProfile
from gtrmrs.deps.scanners.base import BaseScanner


class AndroidScanner(BaseScanner):
    """Scanner for Android projects using Gradle and version catalogs."""

    @property
    def ecosystem_name(self) -> str:
        return "android"

    def can_scan_project(self, project_path: str) -> bool:
        """Returns True if the directory has Android / Gradle project markers."""
        if not os.path.isdir(project_path):
            return False
        toml_path = os.path.join(project_path, "gradle", "libs.versions.toml")
        if os.path.exists(toml_path):
            return True
        settings_kts = os.path.join(project_path, "settings.gradle.kts")
        settings_groovy = os.path.join(project_path, "settings.gradle")
        return os.path.exists(settings_kts) or os.path.exists(settings_groovy)

    def discover_projects(self, base_dir: str) -> Dict[str, str]:
        """Discovers Android projects with version catalogs in base_dir."""
        found: Dict[str, str] = {}
        abs_base = os.path.abspath(base_dir)

        # 1. Check if base_dir itself is an Android project with a catalog
        direct_catalog = os.path.join(abs_base, "gradle", "libs.versions.toml")
        if os.path.exists(direct_catalog):
            repo_name = os.path.basename(abs_base) or "root"
            found[repo_name] = abs_base
            return found

        # 2. Search direct subdirectories and nested folders
        try:
            entries = sorted(os.listdir(abs_base))
        except OSError:
            return found

        skip_dirs = {
            ".git", ".gradle", "build", ".idea", "node_modules",
            "target", ".cxx", "captures", "bin", "obj", "dist"
        }

        for entry in entries:
            entry_path = os.path.join(abs_base, entry)
            if not os.path.isdir(entry_path) or entry in skip_dirs:
                continue

            # Check if entry is directly an Android project
            if os.path.exists(os.path.join(entry_path, "gradle", "libs.versions.toml")):
                found[entry] = entry_path
                continue

            # Search up to depth 3
            entry_projects: List[str] = []
            for root, dirs, files in os.walk(entry_path):
                dirs[:] = [d for d in dirs if d not in skip_dirs]
                rel = os.path.relpath(root, entry_path)
                if rel.count(os.sep) >= 3:
                    dirs.clear()
                    continue

                if "libs.versions.toml" in files and os.path.basename(root) == "gradle":
                    project_root = os.path.dirname(root)
                    entry_projects.append(project_root)
                    dirs.clear()

            if len(entry_projects) == 1:
                found[entry] = entry_projects[0]
            elif len(entry_projects) > 1:
                for pr in entry_projects:
                    pname = os.path.relpath(pr, abs_base).replace("\\", "/")
                    found[pname] = pr

        return found

    def parse_gradle_wrapper(self, project_dir: str) -> Optional[str]:
        """Extracts Gradle wrapper distribution version."""
        wrap = os.path.join(project_dir, "gradle", "wrapper", "gradle-wrapper.properties")
        if not os.path.exists(wrap):
            return None
        try:
            with open(wrap, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "distributionUrl" in line:
                        m = re.search(r"gradle-([\d\.]+)-(?:bin|all)\.zip", line)
                        if m:
                            return m.group(1)
                        parts = line.strip().split("=")
                        if len(parts) > 1:
                            return parts[-1]
        except OSError:
            pass
        return None

    def parse_sdk_and_build(self, project_dir: str) -> Dict[str, List[str]]:
        """Extracts compileSdk, targetSdk, and minSdk from build files."""
        info: Dict[str, Set[str]] = {"compileSdk": set(), "targetSdk": set(), "minSdk": set()}
        skip_dirs = {".git", ".gradle", "build", ".idea", "bin", "obj"}

        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            rel = os.path.relpath(root, project_dir)
            if rel.count(os.sep) >= 4:
                dirs.clear()
                continue

            for f in files:
                if f.endswith(".gradle.kts") or f.endswith(".gradle") or f.endswith(".kt"):
                    fp = os.path.join(root, f)
                    try:
                        with open(fp, "r", encoding="utf-8", errors="ignore") as file:
                            content = file.read()
                            for m in re.finditer(r"compileSdk(?:\.set\()?[\s=]+(\d+)\)?", content):
                                info["compileSdk"].add(m.group(1))
                            for m in re.finditer(r"targetSdk(?:\.set\()?[\s=]+(\d+)\)?", content):
                                info["targetSdk"].add(m.group(1))
                            for m in re.finditer(r"minSdk(?:\.set\()?[\s=]+(\d+)\)?", content):
                                info["minSdk"].add(m.group(1))
                    except OSError:
                        pass

        return {k: sorted(list(v), key=lambda x: int(x) if x.isdigit() else x) for k, v in info.items()}

    def parse_toml(self, project_dir: str) -> Dict[str, Any]:
        """Parses gradle/libs.versions.toml into libraries, plugins, and raw versions."""
        toml_path = os.path.join(project_dir, "gradle", "libs.versions.toml")
        empty_result: Dict[str, Any] = {"versions": {}, "libraries": {}, "plugins": {}}
        if not os.path.exists(toml_path):
            return empty_result

        if tomllib is None:
            # Fallback simple parser if tomllib is missing
            return self._parse_toml_basic(toml_path)

        try:
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            return empty_result

        versions = data.get("versions", {})
        raw_libs = data.get("libraries", {})
        raw_plugins = data.get("plugins", {})

        libraries: Dict[str, Any] = {}
        for alias, lib_data in raw_libs.items():
            is_ref = False
            ref_name = None
            if isinstance(lib_data, str):
                parts = lib_data.split(":")
                group = parts[0]
                name = parts[1] if len(parts) > 1 else ""
                version = parts[2] if len(parts) > 2 else None
            elif isinstance(lib_data, dict):
                if "module" in lib_data:
                    parts = lib_data["module"].split(":")
                    group = parts[0]
                    name = parts[1] if len(parts) > 1 else ""
                else:
                    group = str(lib_data.get("group", ""))
                    name = str(lib_data.get("name", ""))

                if "version.ref" in lib_data:
                    ref_name = str(lib_data["version.ref"])
                    is_ref = True
                    version = str(versions.get(ref_name, f"ref:{ref_name}"))
                elif "version" in lib_data:
                    v = lib_data["version"]
                    if isinstance(v, dict) and "ref" in v:
                        ref_name = str(v["ref"])
                        is_ref = True
                        version = str(versions.get(ref_name, f"ref:{ref_name}"))
                    else:
                        version = str(v)
                else:
                    version = None
            else:
                continue

            libraries[alias] = {
                "group": group,
                "name": name,
                "coord": f"{group}:{name}" if group and name else alias,
                "version": version,
                "is_ref": is_ref,
                "ref_name": ref_name,
            }

        plugins: Dict[str, Any] = {}
        for alias, plug_data in raw_plugins.items():
            is_ref = False
            ref_name = None
            if isinstance(plug_data, str):
                parts = plug_data.split(":")
                plugin_id = parts[0]
                version = parts[1] if len(parts) > 1 else None
            elif isinstance(plug_data, dict):
                plugin_id = str(plug_data.get("id", ""))
                if "version.ref" in plug_data:
                    ref_name = str(plug_data["version.ref"])
                    is_ref = True
                    version = str(versions.get(ref_name, f"ref:{ref_name}"))
                elif "version" in plug_data:
                    v = plug_data["version"]
                    if isinstance(v, dict) and "ref" in v:
                        ref_name = str(v["ref"])
                        is_ref = True
                        version = str(versions.get(ref_name, f"ref:{ref_name}"))
                    else:
                        version = str(v)
                else:
                    version = None
            else:
                continue

            plugins[alias] = {
                "id": plugin_id,
                "version": version,
                "is_ref": is_ref,
                "ref_name": ref_name,
            }

        return {
            "versions": {str(k): str(v) for k, v in versions.items()},
            "libraries": libraries,
            "plugins": plugins,
        }

    def _parse_toml_basic(self, toml_path: str) -> Dict[str, Any]:
        """Regex-based fallback parser for basic libs.versions.toml files."""
        versions: Dict[str, str] = {}
        libraries: Dict[str, Any] = {}
        plugins: Dict[str, Any] = {}
        current_section = ""

        try:
            with open(toml_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("[") and line.endswith("]"):
                        current_section = line[1:-1].strip()
                        continue

                    if current_section == "versions":
                        m = re.match(r"^([A-Za-z0-9_\-]+)\s*=\s*[\"']([^\"']+)[\"']", line)
                        if m:
                            versions[m.group(1)] = m.group(2)
                    elif current_section == "libraries":
                        m_str = re.match(r"^([A-Za-z0-9_\-]+)\s*=\s*[\"']([^\"']+)[\"']", line)
                        if m_str:
                            alias, full = m_str.group(1), m_str.group(2)
                            pts = full.split(":")
                            libraries[alias] = {
                                "group": pts[0],
                                "name": pts[1] if len(pts) > 1 else "",
                                "coord": f"{pts[0]}:{pts[1]}" if len(pts) > 1 else alias,
                                "version": pts[2] if len(pts) > 2 else None,
                                "is_ref": False,
                                "ref_name": None,
                            }
                        else:
                            m_mod = re.search(r"module\s*=\s*[\"']([^\"']+)[\"']", line)
                            m_ref = re.search(r"version\.ref\s*=\s*[\"']([^\"']+)[\"']", line)
                            m_alias = re.match(r"^([A-Za-z0-9_\-]+)\s*=", line)
                            if m_alias and m_mod:
                                alias = m_alias.group(1)
                                pts = m_mod.group(1).split(":")
                                ref = m_ref.group(1) if m_ref else None
                                libraries[alias] = {
                                    "group": pts[0],
                                    "name": pts[1] if len(pts) > 1 else "",
                                    "coord": m_mod.group(1),
                                    "version": versions.get(ref) if ref else None,
                                    "is_ref": bool(ref),
                                    "ref_name": ref,
                                }
        except OSError:
            pass

        return {"versions": versions, "libraries": libraries, "plugins": plugins}

    def scan_project(self, name: str, path: str) -> Tuple[ProjectProfile, Dict[str, Any]]:
        """Scans an Android project for profile and components."""
        gradle_ver = self.parse_gradle_wrapper(path)
        sdk_info = self.parse_sdk_and_build(path)
        toml_data = self.parse_toml(path)

        plugs = toml_data.get("plugins", {})
        libs = toml_data.get("libraries", {})

        # Extract notable plugin versions for profile summary
        plugin_versions: Dict[str, str] = {}
        for alias, pinfo in plugs.items():
            pid = pinfo.get("id", "")
            ver = pinfo.get("version") or "N/A"
            if "android.application" in pid or alias == "android-application":
                plugin_versions["agp"] = ver
            elif "kotlin.compose" in pid or alias == "kotlin-compose":
                plugin_versions["kotlin-compose"] = ver
            elif "kotlin.android" in pid or alias == "kotlin-android":
                plugin_versions["kotlin-android"] = ver

        # Check compose BOM in libraries
        for alias, linfo in libs.items():
            coord = linfo.get("coord", "")
            if "compose-bom" in coord or "compose.bom" in alias or "compose-bom" in alias:
                plugin_versions["compose-bom"] = linfo.get("version") or "N/A"
                break

        # If not found in libraries, check versions table directly
        if "compose-bom" not in plugin_versions:
            for vname, vval in toml_data.get("versions", {}).items():
                vname_norm = vname.lower().replace("_", "-").replace(".", "-")
                if "compose-bom" in vname_norm:
                    plugin_versions["compose-bom"] = vval
                    break

        profile = ProjectProfile(
            name=name,
            path=path,
            project_type="android",
            build_tool_version=gradle_ver,
            plugin_versions=plugin_versions,
            sdk_info=sdk_info,
            libraries_count=len(libs),
            plugins_count=len(plugs),
            metadata={"toml": toml_data},
        )

        return profile, toml_data

    def categorize(self, identifier: str) -> str:
        """Assigns a clean functional category to an Android component."""
        n = identifier.lower()
        if any(x in n for x in ["plugin", "gradle", "ksp", "detekt", "spotless"]):
            return "Build & Plugins"
        if any(x in n for x in ["compose", "material", "adaptive", "ui", "shape", "icon", "animation"]):
            return "UI & Compose"
        if any(x in n for x in ["lifecycle", "activity", "navigation", "appcompat", "core", "splashscreen", "fragment"]):
            return "AndroidX & Architecture"
        if any(x in n for x in ["hilt", "dagger", "inject", "koin"]):
            return "Dependency Injection"
        if any(x in n for x in ["room", "datastore", "sql", "sqlite", "preference"]):
            return "Database & Storage"
        if any(x in n for x in ["okhttp", "retrofit", "ktor", "webkit", "apollo"]):
            return "Networking & Web"
        if any(x in n for x in ["media3", "sceneview", "filament", "coil", "glide", "exoplayer", "jaudiotagger", "youtubedl"]):
            return "Media & Graphics"
        if any(x in n for x in ["test", "junit", "espresso", "mockk", "mockito", "turbine", "robolectric", "archunit", "truth"]):
            return "Testing"
        if any(x in n for x in ["coroutine", "serialization", "immutable", "compress", "zip", "xz", "desugar", "arrow"]):
            return "Kotlin & Utilities"
        if any(x in n for x in ["bouncy", "crypto", "security", "tink", "biometric"]):
            return "Security & Crypto"
        return "Other"
