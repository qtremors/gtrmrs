"""
engine.py

Core coordinator for multi-ecosystem dependency audits and in-place updates.
"""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from gtrmrs.deps.models import (
    AuditResult,
    Component,
    ProjectProfile,
    UpdateAction,
    UpstreamInfo,
)
from gtrmrs.deps.scanners.android import AndroidScanner
from gtrmrs.deps.scanners.base import BaseScanner, parse_semver
from gtrmrs.deps.updater.toml_updater import CatalogUpdater
from gtrmrs.deps.upstream.resolver import UpstreamResolver


def get_highest_version(versions_list: List[Optional[str]]) -> str:
    """Finds the highest semver string in a list of versions."""
    valid = [str(v) for v in versions_list if v and str(v) not in ("None", "N/A")]
    if not valid:
        return "N/A"
    return max(valid, key=parse_semver)


def matching_repositories(names: List[str], target: Optional[str]) -> List[str]:
    """Use the same exact-name-first selection for audits and update plans."""
    if not target:
        return names
    if target in names:
        return [target]
    exact = [name for name in names if name.casefold() == target.casefold()]
    return exact or [name for name in names if target.casefold() in name.casefold()]


class DepsEngine:
    """Coordinates project discovery, catalog auditing, upstream resolution, and updates."""

    def __init__(self, upstream_timeout: int = 5):
        self.scanners: List[BaseScanner] = [AndroidScanner()]
        self.resolver = UpstreamResolver(timeout=upstream_timeout)
        self.updater = CatalogUpdater()

    def register_scanner(self, scanner: BaseScanner) -> None:
        """Registers an additional ecosystem scanner (e.g., Web, Desktop)."""
        self.scanners.append(scanner)

    def discover(self, base_dir: str) -> Dict[str, Tuple[str, BaseScanner]]:
        """Discovers all projects across registered scanners in base_dir.

        Returns mapping of repo_name -> (repo_root, scanner).
        """
        discovered: Dict[str, Tuple[str, BaseScanner]] = {}
        for scanner in self.scanners:
            found = scanner.discover_projects(base_dir)
            for name, path in found.items():
                if name not in discovered:
                    discovered[name] = (path, scanner)
        return discovered

    def run_audit(
        self,
        base_dir: str,
        no_upstream: bool = False,
        target_repo: Optional[str] = None,
        comparison_scope: bool = False,
    ) -> AuditResult:
        """Audit selected projects, retaining workspace context when comparison_scope is True."""
        all_discovered = self.discover(base_dir)
        if target_repo:
            selected = matching_repositories(list(all_discovered), target_repo)
            if not comparison_scope or not selected:
                all_discovered = {name: all_discovered[name] for name in selected}

        if not all_discovered:
            return AuditResult(
                base_dir=base_dir,
                profiles={},
                components=[],
                discrepancies=[],
                upstream_updates=[],
            )

        repos = sorted(all_discovered.keys())
        profiles: Dict[str, ProjectProfile] = {}
        raw_repo_data: Dict[str, Dict[str, Any]] = {}

        for r in repos:
            path, scanner = all_discovered[r]
            snapshots: Dict[str, Optional[str]] = {}
            for relative in ("gradle/libs.versions.toml", "gradle/wrapper/gradle-wrapper.properties"):
                source = os.path.join(path, *relative.split("/"))
                try:
                    with open(source, "rb") as handle:
                        snapshots[source] = hashlib.sha256(handle.read()).hexdigest()
                except OSError:
                    snapshots[source] = None
            prof, raw_data = scanner.scan_project(r, path)
            prof.metadata["update_fingerprints"] = snapshots
            profiles[r] = prof
            raw_repo_data[r] = raw_data

        # 1. Collect Gradle Wrapper / Build Tool Component
        gradle_versions = {r: profiles[r].build_tool_version for r in repos}
        has_gradle = any(v is not None for v in gradle_versions.values())
        components: List[Component] = []

        if has_gradle:
            highest_gradle = get_highest_version(list(gradle_versions.values()))
            components.append(
                Component(
                    identifier="Gradle Wrapper Distribution",
                    component_type="build_tool",
                    category="Build & Plugins",
                    repo_versions=gradle_versions,
                    latest_in_repos=highest_gradle,
                )
            )

        # 2. Collect Plugins
        all_plugins: Dict[str, Dict[str, Optional[str]]] = defaultdict(dict)
        declarations: Dict[Tuple[str, str], Dict[str, list]] = defaultdict(lambda: defaultdict(list))

        def declaration(kind: str, identifier: str, repo: str, alias: str, item: dict) -> None:
            declarations[(kind, identifier)][repo].append({
                "alias": alias, "version": item.get("version"),
                "kind": item.get("version_kind", "literal" if item.get("version") else "managed"),
                "constraint": item.get("version_constraint"), "issue": item.get("version_issue"),
                "ref_name": item.get("ref_name"),
            })
        for r in repos:
            plugs = raw_repo_data[r].get("plugins", {})
            for alias, pinfo in plugs.items():
                pid = pinfo.get("id")
                if pid:
                    declaration("plugin", pid, r, alias, pinfo)
                    version = pinfo.get("version") if pinfo.get("version_kind", "literal") == "literal" else None
                    previous = all_plugins[pid].get(r)
                    all_plugins[pid][r] = get_highest_version([previous, version]) if previous and version else previous or version

        for pid in sorted(all_plugins.keys()):
            vmap = all_plugins[pid]
            highest = get_highest_version([vmap.get(r) for r in repos])
            components.append(
                Component(
                    identifier=pid,
                    component_type="plugin",
                    category="Build & Plugins",
                    repo_versions={r: vmap.get(r) for r in repos},
                    latest_in_repos=highest,
                    repo_declarations=dict(declarations[("plugin", pid)]),
                )
            )

        # 3. Collect Libraries
        all_libs: Dict[str, Dict[str, Optional[str]]] = defaultdict(dict)
        library_categories: Dict[str, str] = {}

        for r in repos:
            libs = raw_repo_data[r].get("libraries", {})
            for alias, linfo in libs.items():
                coord = linfo.get("coord")
                if coord:
                    if coord not in library_categories:
                        library_categories[coord] = all_discovered[r][1].categorize(coord)
                    declaration("library", coord, r, alias, linfo)
                    version = linfo.get("version") if linfo.get("version_kind", "literal") == "literal" else None
                    previous = all_libs[coord].get(r)
                    all_libs[coord][r] = get_highest_version([previous, version]) if previous and version else previous or version

        for coord in sorted(all_libs.keys()):
            vmap = all_libs[coord]
            highest = get_highest_version([vmap.get(r) for r in repos])
            cat = library_categories[coord]
            components.append(
                Component(
                    identifier=coord,
                    component_type="library",
                    category=cat,
                    repo_versions={r: vmap.get(r) for r in repos},
                    latest_in_repos=highest,
                    repo_declarations=dict(declarations[("library", coord)]),
                )
            )

        # 4. Resolve Upstream Information
        if no_upstream:
            for c in components:
                c.upstream = UpstreamInfo(source="Skipped")
        else:
            query_items = [(c.component_type, c.identifier) for c in components]
            upstream_results = self.resolver.resolve_all(query_items)
            for c in components:
                key = f"{c.component_type}:{c.identifier}"
                if key in upstream_results:
                    c.upstream = upstream_results[key]

        # 5. Evaluate Statuses & Discrepancies
        discrepancies: List[Tuple[str, str, str]] = []
        upstream_updates: List[Tuple[str, str, str, str]] = []

        for c in components:
            max_in_repos = c.latest_in_repos
            up_stable = c.upstream.latest_stable
            up_overall = c.upstream.latest_overall

            # Determine statuses for each repository
            repo_statuses: Dict[str, str] = {}
            version_to_repos: Dict[str, List[str]] = defaultdict(list)

            for r in repos:
                v = c.repo_versions.get(r)
                kinds = {entry["kind"] for entry in c.repo_declarations.get(r, [])}
                if "unsupported" in kinds:
                    repo_statuses[r] = "unsupported"
                elif "constraint" in kinds:
                    repo_statuses[r] = "constraint"
                elif kinds == {"managed"}:
                    repo_statuses[r] = "bom-managed"
                elif not v:
                    repo_statuses[r] = "unused"
                elif v in ("None", "N/A"):
                    repo_statuses[r] = "bom-managed"
                elif max_in_repos != "N/A" and parse_semver(v) < parse_semver(max_in_repos):
                    repo_statuses[r] = "repo-outdated"
                    version_to_repos[v].append(r)
                else:
                    repo_statuses[r] = "repo-latest"
                    version_to_repos[v].append(r)

            c.repo_statuses = repo_statuses

            # Check for cross-repo discrepancies
            outdated_repos = [r for r, st in repo_statuses.items() if st == "repo-outdated"]
            if outdated_repos:
                latest_repos = [r for r, st in repo_statuses.items() if st == "repo-latest"]
                latest_summary = f"{', '.join(latest_repos)} ({max_in_repos})"

                # Group outdated by version: "acqua (1.8.0) | arcile, filion (1.9.0)"
                outdated_groups = []
                # Sort versions ascending
                sorted_out_vers = sorted(
                    [ver for ver in version_to_repos.keys() if ver != max_in_repos and ver not in ("None", "N/A")],
                    key=parse_semver,
                )
                for over in sorted_out_vers:
                    orepos = [r for r in version_to_repos[over] if r in outdated_repos]
                    if orepos:
                        outdated_groups.append(f"{', '.join(orepos)} ({over})")

                outdated_summary = " | ".join(outdated_groups) if outdated_groups else ", ".join(outdated_repos)
                discrepancies.append((c.identifier, latest_summary, outdated_summary))

            # Upstream status
            if c.upstream.check_status == "skipped":
                c.upstream_status = "Check Skipped"
            elif c.upstream.check_status == "unavailable":
                c.upstream_status = "Unavailable"
            elif "unsupported" in repo_statuses.values():
                c.upstream_status = "Unsupported Declaration"
            elif "constraint" in repo_statuses.values():
                c.upstream_status = "Constraints Not Evaluated"
            elif max_in_repos == "N/A":
                c.upstream_status = "Version Managed Externally"
            elif up_stable and parse_semver(max_in_repos) < parse_semver(up_stable):
                c.upstream_status = "Newer Stable Available"
                # Record upstream update recommendation
                used_in = [f"{r} ({v})" for r, v in c.repo_versions.items() if v and v not in ("None", "N/A")]
                current_summary = ", ".join(used_in) if len(used_in) <= 3 else f"{max_in_repos} ({len(used_in)} repos)"
                upstream_updates.append((c.identifier, current_summary, f"{up_stable} (Stable)", c.upstream.source))
            elif up_overall and parse_semver(max_in_repos) < parse_semver(up_overall):
                c.upstream_status = "Newer Preview Available"
                used_in = [f"{r} ({v})" for r, v in c.repo_versions.items() if v and v not in ("None", "N/A")]
                current_summary = ", ".join(used_in) if len(used_in) <= 3 else f"{max_in_repos} ({len(used_in)} repos)"
                upstream_updates.append((c.identifier, current_summary, f"{up_overall} (Preview)", c.upstream.source))
            elif not up_stable:
                c.upstream_status = "Stable Release Unknown"
            else:
                c.upstream_status = "Up to Date"

        # Calculate summary statistics
        total_comps = len(components)
        discrepant_count = len(discrepancies)
        newer_upstream_count = sum(
            1 for c in components if c.upstream_status in ("Newer Stable Available", "Newer Preview Available")
        )
        up_to_date_count = sum(
            1 for c in components if c.upstream_status == "Up to Date"
            and all(status in ("repo-latest", "unused") for status in c.repo_statuses.values())
            and all(entry["kind"] == "literal" for entries in c.repo_declarations.values() for entry in entries)
        )

        return AuditResult(
            base_dir=base_dir,
            profiles=profiles,
            components=components,
            discrepancies=discrepancies,
            upstream_updates=upstream_updates,
            total_components=total_comps,
            repo_discrepancies_count=discrepant_count,
            upstream_available_count=newer_upstream_count,
            up_to_date_count=up_to_date_count,
        )

    def plan_updates(
        self,
        result: AuditResult,
        mode: str = "align",
        target_repo: Optional[str] = None,
    ) -> List[UpdateAction]:
        """Plans in-place updates for catalog files.

        mode:
          - 'align': Align outdated repos to highest version found among scanned repos.
          - 'upstream': Upgrade all repos to latest upstream stable version.
        """
        if mode not in ("align", "upstream"):
            raise ValueError("Unknown update mode: " + mode)
        repos = matching_repositories(sorted(result.profiles), target_repo)
        if target_repo and not repos:
            raise ValueError("No repositories match: " + target_repo)
        components = {(c.component_type, c.identifier): c for c in result.components}
        actions: List[UpdateAction] = []

        def target_version(comp: Component, current: Optional[str]) -> Optional[str]:
            if not current or current in ("None", "N/A"):
                return None
            candidate = comp.latest_in_repos if mode == "align" else comp.upstream.latest_stable
            if candidate and candidate != "N/A" and parse_semver(current) < parse_semver(candidate):
                return candidate
            return current

        for repo in repos:
            profile = result.profiles[repo]
            for comp in result.components:
                if comp.component_type != "build_tool" or not comp.identifier.startswith("Gradle Wrapper"):
                    continue
                current = comp.repo_versions.get(repo)
                target = target_version(comp, current)
                if target and target != current:
                    actions.append(UpdateAction(
                        repo, os.path.join(profile.path, "gradle", "wrapper", "gradle-wrapper.properties"),
                        comp.identifier, "distributionUrl", current, target, mode, component_type="build_tool",
                    ))

            catalog_path = os.path.join(profile.path, "gradle", "libs.versions.toml")
            shared: Dict[str, List[Tuple[str, Optional[str]]]] = defaultdict(list)
            pending_refs: Dict[str, UpdateAction] = {}
            for section, kind, coordinate_key in (("libraries", "library", "coord"), ("plugins", "plugin", "id")):
                for alias, item in profile.metadata.get("toml", {}).get(section, {}).items():
                    identifier = item.get(coordinate_key, "")
                    current = item.get("version")
                    component = components.get((kind, identifier))
                    constrained = component and any(
                        entry["kind"] in ("constraint", "unsupported")
                        for entry in component.repo_declarations.get(repo, [])
                    )
                    target = (target_version(component, current)
                              if component and not constrained and item.get("version_kind", "literal") == "literal" else current)
                    reference = item.get("ref_name") if item.get("is_ref") else None
                    if reference:
                        # Include unchanged/unknown consumers so their settings are not silently moved.
                        shared[reference].append((section + "." + alias, target))
                    if not target or target == current:
                        continue
                    action = UpdateAction(
                        repo, catalog_path, identifier, alias, current, target, mode,
                        is_version_ref=bool(reference), ref_name=reference, component_type=kind,
                    )
                    if reference:
                        pending_refs.setdefault(reference, action)
                    else:
                        actions.append(action)

            for reference, action in pending_refs.items():
                consumers = shared[reference]
                if any(target != action.new_version for _, target in consumers):
                    details = ", ".join("{} -> {}".format(alias, target or "unknown") for alias, target in consumers)
                    raise ValueError("Conflicting updates for {} [versions].{}: {}".format(repo, reference, details))
                actions.append(action)

        # One fingerprint per file protects both versions and unrelated edits made after planning.
        fingerprints: Dict[str, str] = {}
        for action in actions:
            if action.file_path not in fingerprints:
                snapshot = result.profiles[action.repo_name].metadata.get("update_fingerprints", {})
                if action.file_path in snapshot:
                    if snapshot[action.file_path] is None:
                        raise ValueError("Could not read update target during audit: " + action.file_path)
                    fingerprints[action.file_path] = snapshot[action.file_path]
                else:
                    try:
                        with open(action.file_path, "rb") as handle:
                            fingerprints[action.file_path] = hashlib.sha256(handle.read()).hexdigest()
                    except OSError as exc:
                        raise ValueError("Could not read update target {}: {}".format(action.file_path, exc)) from exc
            action.expected_sha256 = fingerprints[action.file_path]
        return actions

    def apply_actions(
        self, actions: List[UpdateAction], dry_run: bool = False
    ) -> List[Tuple[UpdateAction, bool]]:
        """Applies update actions using CatalogUpdater."""
        return self.updater.apply_actions(actions, dry_run=dry_run)
