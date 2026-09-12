"""
android.py

Android ecosystem scanner for Gradle version catalogs, wrapper, and SDK configurations.
"""

from __future__ import annotations

import os
import tomllib
from typing import Any, Dict, List, Optional, Set, Tuple

from gtrmrs.deps.models import ProjectProfile
from gtrmrs.deps.scanners.base import BaseScanner, parse_semver
from gtrmrs.deps.scanners.gradle import sdk_literals
from gtrmrs.deps.scanners.catalog import normalize_catalog
from gtrmrs.deps.scanners.wrapper import distribution, wrapper_properties


class AndroidScanner(BaseScanner):
    """Scanner for Android projects using Gradle and version catalogs."""

    @property
    def ecosystem_name(self) -> str:
        return "android"

    def can_scan_project(self, project_path: str) -> bool:
        """Returns True if the directory has Android / Gradle project markers."""
        if not os.path.isdir(project_path):
            return False
        return any(os.path.isfile(os.path.join(project_path, *marker.split("/"))) for marker in (
            "gradle/libs.versions.toml", "settings.gradle.kts", "settings.gradle",
            "build.gradle.kts", "build.gradle", "gradle/wrapper/gradle-wrapper.properties",
        ))

    def discover_projects(self, base_dir: str) -> Dict[str, str]:
        """Discover Gradle roots, stopping at the first project in each branch."""
        found: Dict[str, str] = {}
        abs_base = os.path.abspath(base_dir)

        if self.can_scan_project(abs_base):
            repo_name = os.path.basename(abs_base) or "root"
            found[repo_name] = abs_base
            return found

        # 2. Search direct subdirectories and nested folders
        entries = sorted(os.listdir(abs_base))

        skip_dirs = {
            ".git", ".gradle", "build", ".idea", "node_modules",
            "target", ".cxx", "captures", "bin", "obj", "dist"
        }

        for entry in entries:
            entry_path = os.path.join(abs_base, entry)
            if not os.path.isdir(entry_path) or entry in skip_dirs:
                continue

            # Check if entry is directly an Android project
            if self.can_scan_project(entry_path):
                found[entry] = entry_path
                continue

            # Search up to depth 3
            entry_projects: List[str] = []
            def failed(error: OSError) -> None:
                raise error

            for root, dirs, files in os.walk(entry_path, onerror=failed):
                dirs[:] = sorted(d for d in dirs if d not in skip_dirs)
                rel = os.path.relpath(root, entry_path)
                if rel.count(os.sep) >= 3:
                    dirs.clear()
                    continue

                if self.can_scan_project(root):
                    entry_projects.append(root)
                    dirs.clear()

            if len(entry_projects) == 1:
                found[entry] = entry_projects[0]
            elif len(entry_projects) > 1:
                for pr in entry_projects:
                    pname = os.path.relpath(pr, abs_base).replace("\\", "/")
                    found[pname] = pr

        return found

    def parse_gradle_wrapper(self, project_dir: str, notes: Optional[List[str]] = None) -> Optional[str]:
        """Extracts Gradle wrapper distribution version."""
        wrap = os.path.join(project_dir, "gradle", "wrapper", "gradle-wrapper.properties")
        if not os.path.exists(wrap):
            return None
        try:
            with open(wrap, encoding="utf-8", newline="") as handle:
                prop = wrapper_properties(handle.read()).get("distributionUrl")
            info = distribution(prop.value) if prop else None
            if info:
                return info.version
            if prop and notes is not None:
                notes.append("gradle/wrapper/gradle-wrapper.properties: active distribution filename not recognized")
        except (OSError, ValueError) as exc:
            raise ValueError("Could not read Gradle wrapper {}: {}".format(wrap, exc)) from exc
        return None

    def parse_sdk_and_build(self, project_dir: str, notes: Optional[List[str]] = None) -> Dict[str, List[str]]:
        """Read numeric SDK literals in Android Gradle script blocks."""
        info: Dict[str, Set[str]] = {"compileSdk": set(), "targetSdk": set(), "minSdk": set()}
        skip_dirs = {".git", ".gradle", "build", ".idea", "bin", "obj", "node_modules",
                     "venv", ".venv", "__pycache__", ".kotlin", ".cxx", "target", "dist"}

        def failed(error: OSError) -> None:
            raise error

        for root, dirs, files in os.walk(project_dir, onerror=failed):
            dirs[:] = [directory for directory in dirs if directory not in skip_dirs]
            relative = os.path.relpath(root, project_dir)
            if relative.count(os.sep) >= 4:
                dirs.clear()
                continue
            for name in sorted(files):
                if not name.endswith((".gradle.kts", ".gradle")):
                    continue
                path = os.path.join(root, name)
                try:
                    with open(path, encoding="utf-8") as handle:
                        content = handle.read()
                except (OSError, UnicodeError) as exc:
                    raise ValueError("Could not read Gradle script {}: {}".format(path, exc)) from exc
                values, unresolved = sdk_literals(content)
                for key, literals in values.items():
                    info[key].update(literals)
                if notes is not None:
                    label = os.path.relpath(path, project_dir).replace(os.sep, "/")
                    notes.extend("{}:{}: {} expression not evaluated".format(label, line, key)
                                 for line, key in unresolved)
        return {key: sorted(values, key=int) for key, values in info.items()}

    def parse_toml(self, project_dir: str) -> Dict[str, Any]:
        """Read the full catalog using the Python 3.11+ standard-library parser."""
        path = os.path.join(project_dir, "gradle", "libs.versions.toml")
        if not os.path.exists(path):
            return {"versions": {}, "libraries": {}, "plugins": {}}
        try:
            with open(path, "rb") as handle:
                data = tomllib.load(handle)
        except (OSError, ValueError) as exc:
            raise ValueError("Could not parse catalog {}: {}".format(path, exc)) from exc
        return normalize_catalog(data, path)

    def scan_project(self, name: str, path: str) -> Tuple[ProjectProfile, Dict[str, Any]]:
        """Scans an Android project for profile and components."""
        notes: List[str] = []
        gradle_ver = self.parse_gradle_wrapper(path, notes)
        sdk_info = self.parse_sdk_and_build(path, notes)
        toml_data = self.parse_toml(path)
        catalog = "gradle/libs.versions.toml"
        catalog_present = os.path.isfile(os.path.join(path, *catalog.split("/")))
        notes.append(
            "Dependency coverage: declarations from {} only; build-script dependencies, custom/imported catalogs and resolved versions are not evaluated.".format(catalog)
            if catalog_present else
            "Dependency coverage unknown: no gradle/libs.versions.toml; build-script dependencies and custom/imported catalogs are not evaluated."
        )

        plugs = toml_data.get("plugins", {})
        libs = toml_data.get("libraries", {})

        for section in ("libraries", "plugins"):
            for alias, entry in toml_data[section].items():
                kind = entry["version_kind"]
                if kind == "managed":
                    message = "Managed / versionless (external version not resolved)"
                elif kind == "constraint":
                    message = "Version constraint {} (not resolved or automatically edited)".format(entry["version_constraint"])
                elif kind == "unsupported":
                    message = entry["version_issue"] or "Unsupported version declaration"
                else:
                    continue
                notes.append("[{}].{}: {}".format(section, alias, message))

        # Extract notable plugin versions for profile summary
        plugin_versions: Dict[str, str] = {}
        for alias, pinfo in plugs.items():
            pid = pinfo.get("id", "")
            ver = pinfo.get("version") if pinfo.get("version_kind") == "literal" else None
            ver = ver or "N/A"
            if pid in ("com.android.application", "com.android.library"):
                previous = plugin_versions.get("agp", "N/A")
                plugin_versions["agp"] = max((previous, ver), key=parse_semver)
            elif "kotlin.compose" in pid or alias == "kotlin-compose":
                plugin_versions["kotlin-compose"] = ver
            elif "kotlin.android" in pid or alias == "kotlin-android":
                plugin_versions["kotlin-android"] = ver

        # Check compose BOM in libraries
        for alias, linfo in libs.items():
            coord = linfo.get("coord", "")
            if "compose-bom" in coord or "compose.bom" in alias or "compose-bom" in alias:
                plugin_versions["compose-bom"] = (linfo.get("version") if linfo.get("version_kind") == "literal" else None) or "N/A"
                break

        # If not found in libraries, check versions table directly
        if "compose-bom" not in plugin_versions:
            for vname, vval in toml_data.get("versions", {}).items():
                vname_norm = vname.lower().replace("_", "-").replace(".", "-")
                if "compose-bom" in vname_norm and isinstance(vval, str):
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
            metadata={"toml": toml_data, "declaration_notes": notes,
                      "dependency_coverage": {"catalog": catalog if catalog_present else None,
                                              "scope": "default-catalog-only", "complete": False}},
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
