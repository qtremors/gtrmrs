"""
resolver.py

Upstream dependency version resolver for Google Maven, Maven Central,
Gradle Plugin Portal, and services.gradle.org.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

from gtrmrs.deps.models import UpstreamInfo
from gtrmrs.deps.scanners.base import is_preview_version, parse_semver


class UpstreamResolver:
    """Resolves upstream version information concurrently with caching."""

    def __init__(self, timeout: int = 5, max_workers: int = 10):
        self.timeout = timeout
        self.max_workers = max_workers
        self._cache: Dict[str, UpstreamInfo] = {}

    def fetch_maven_metadata(self, base_url: str, group: str, artifact: str) -> Optional[Dict[str, Any]]:
        """Fetches and parses maven-metadata.xml from a Maven repository."""
        group_path = group.replace(".", "/")
        url = f"{base_url.rstrip('/')}/{group_path}/{artifact}/maven-metadata.xml"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "gtrmrs-deps-auditor/1.0 (Mozilla/5.0)"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = resp.read()
                root = ET.fromstring(data)
                latest_elem = root.find("./versioning/latest")
                release_elem = root.find("./versioning/release")
                versions_elems = root.findall("./versioning/versions/version")
                versions = [v.text.strip() for v in versions_elems if v.text]
                return {
                    "latest": latest_elem.text.strip() if latest_elem is not None and latest_elem.text else None,
                    "release": release_elem.text.strip() if release_elem is not None and release_elem.text else None,
                    "versions": versions,
                }
        except (urllib.error.URLError, OSError, ET.ParseError):
            return None

    def resolve_gradle_wrapper(self) -> UpstreamInfo:
        """Queries services.gradle.org for Gradle releases."""
        req = urllib.request.Request(
            "https://services.gradle.org/versions/all",
            headers={"User-Agent": "gtrmrs-deps-auditor/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode())
                current_stable = next(
                    (v["version"] for v in data if v.get("current") and not v.get("nightly") and not v.get("releaseCandidate")),
                    None,
                )
                latest_overall = data[0]["version"] if data else None
                return UpstreamInfo(
                    source="services.gradle.org",
                    latest_stable=current_stable or "9.7.1",
                    latest_overall=latest_overall or "9.7.1",
                )
        except Exception:
            return UpstreamInfo(source="services.gradle.org", latest_stable=None, latest_overall=None)

    def _extract_versions(self, meta: Dict[str, Any], source: str) -> UpstreamInfo:
        """Extracts stable and overall latest versions from maven metadata."""
        versions = meta.get("versions", [])
        if not versions:
            return UpstreamInfo(source=source)

        stable_versions = [v for v in versions if not is_preview_version(v)]
        rel = meta.get("release")

        if rel and rel in stable_versions:
            latest_stable = rel
        elif stable_versions:
            latest_stable = max(stable_versions, key=parse_semver)
        else:
            latest_stable = None

        raw_latest = meta.get("latest") or meta.get("release") or versions[-1]
        latest_overall = max(versions, key=parse_semver) if versions else raw_latest

        return UpstreamInfo(
            source=source,
            latest_stable=latest_stable,
            latest_overall=latest_overall,
        )

    def resolve_component(self, comp_type: str, identifier: str) -> UpstreamInfo:
        """Resolves upstream info for a library, plugin, or build tool."""
        cache_key = f"{comp_type}:{identifier}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if comp_type == "build_tool" and identifier.lower().startswith("gradle"):
            res = self.resolve_gradle_wrapper()
            self._cache[cache_key] = res
            return res

        group, artifact = None, None
        is_plugin = (comp_type == "plugin")

        if not is_plugin:
            parts = identifier.split(":")
            if len(parts) >= 2:
                group, artifact = parts[0], parts[1]
        else:
            # Map common Gradle plugin IDs to their maven publication coordinates
            if identifier in ["com.android.application", "com.android.library"]:
                group, artifact = "com.android.tools.build", "gradle"
            elif identifier.startswith("org.jetbrains.kotlin"):
                group, artifact = "org.jetbrains.kotlin", "kotlin-gradle-plugin"
            elif identifier == "com.google.devtools.ksp":
                group, artifact = "com.google.devtools.ksp", "symbol-processing-api"
            elif identifier in ["com.google.dagger.hilt.android", "dagger.hilt.android.plugin"]:
                group, artifact = "com.google.dagger", "hilt-android-gradle-plugin"
            else:
                # Standard Gradle plugin marker artifact: <plugin.id>:<plugin.id>.gradle.plugin
                group = identifier
                artifact = f"{identifier}.gradle.plugin"

        if not group or not artifact:
            res = UpstreamInfo(source="N/A")
            self._cache[cache_key] = res
            return res

        # 1. Check Google Maven if relevant
        if "android" in group or "google" in group:
            meta = self.fetch_maven_metadata("https://dl.google.com/android/maven2", group, artifact)
            if meta and meta.get("versions"):
                res = self._extract_versions(meta, "Google Maven")
                self._cache[cache_key] = res
                return res

        # 2. Check Maven Central
        meta = self.fetch_maven_metadata("https://repo1.maven.org/maven2", group, artifact)
        if meta and meta.get("versions"):
            res = self._extract_versions(meta, "Maven Central")
            self._cache[cache_key] = res
            return res

        # 3. Check Gradle Plugin Portal if plugin
        if is_plugin:
            meta = self.fetch_maven_metadata("https://plugins.gradle.org/m2", group, artifact)
            if meta and meta.get("versions"):
                res = self._extract_versions(meta, "Gradle Plugin Portal")
                self._cache[cache_key] = res
                return res

        res = UpstreamInfo(source="Not Found")
        self._cache[cache_key] = res
        return res

    def resolve_all(
        self, items: List[Tuple[str, str]]
    ) -> Dict[str, UpstreamInfo]:
        """Resolves a list of (comp_type, identifier) pairs in parallel."""
        results: Dict[str, UpstreamInfo] = {}
        to_query: List[Tuple[str, str]] = []

        for ctype, ident in items:
            key = f"{ctype}:{ident}"
            if key in self._cache:
                results[key] = self._cache[key]
            else:
                to_query.append((ctype, ident))

        if not to_query:
            return results

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_key = {
                executor.submit(self.resolve_component, ctype, ident): f"{ctype}:{ident}"
                for ctype, ident in to_query
            }
            for future in as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    results[key] = future.result()
                except Exception:
                    results[key] = UpstreamInfo(source="Error")

        return results
