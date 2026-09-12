"""
engine.py

Core coordinator for multi-ecosystem dependency audits and in-place updates.
"""

from __future__ import annotations

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
    ) -> AuditResult:
        """Performs a complete audit scan across repositories."""
        all_discovered = self.discover(base_dir)
        if target_repo:
            if target_repo in all_discovered:
                all_discovered = {target_repo: all_discovered[target_repo]}
            else:
                matching = {k: v for k, v in all_discovered.items() if target_repo.lower() in k.lower()}
                if matching:
                    all_discovered = matching

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
            prof, raw_data = scanner.scan_project(r, path)
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
        for r in repos:
            plugs = raw_repo_data[r].get("plugins", {})
            for alias, pinfo in plugs.items():
                pid = pinfo.get("id")
                if pid:
                    all_plugins[pid][r] = pinfo.get("version")

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
                )
            )

        # 3. Collect Libraries
        all_libs: Dict[str, Dict[str, Optional[str]]] = defaultdict(dict)
        android_scanner = self.scanners[0]

        for r in repos:
            libs = raw_repo_data[r].get("libraries", {})
            for alias, linfo in libs.items():
                coord = linfo.get("coord")
                if coord:
                    all_libs[coord][r] = linfo.get("version")

        for coord in sorted(all_libs.keys()):
            vmap = all_libs[coord]
            highest = get_highest_version([vmap.get(r) for r in repos])
            cat = android_scanner.categorize(coord)
            components.append(
                Component(
                    identifier=coord,
                    component_type="library",
                    category=cat,
                    repo_versions={r: vmap.get(r) for r in repos},
                    latest_in_repos=highest,
                )
            )

        # 4. Resolve Upstream Information
        if not no_upstream:
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
                if not v:
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
            if not up_stable and not up_overall:
                c.upstream_status = "Internal / N/A"
            elif max_in_repos == "N/A":
                c.upstream_status = "BOM Managed"
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
            else:
                c.upstream_status = "Up to Date"

        # Calculate summary statistics
        total_comps = len(components)
        discrepant_count = len(discrepancies)
        newer_upstream_count = sum(
            1 for c in components if c.upstream_status in ("Newer Stable Available", "Newer Preview Available")
        )
        up_to_date_count = sum(1 for c in components if c.upstream_status == "Up to Date")

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
        actions: List[UpdateAction] = []
        repos = sorted(result.profiles.keys())
        if target_repo:
            repos = [r for r in repos if r == target_repo]

        for comp in result.components:
            if comp.component_type == "build_tool" and comp.identifier.startswith("Gradle Wrapper"):
                # Gradle wrapper update
                for r in repos:
                    current_v = comp.repo_versions.get(r)
                    if not current_v or current_v in ("None", "N/A"):
                        continue
                    target_v = None
                    if mode == "align" and comp.repo_statuses.get(r) == "repo-outdated":
                        target_v = comp.latest_in_repos
                    elif mode == "upstream" and comp.upstream.latest_stable:
                        if parse_semver(current_v) < parse_semver(comp.upstream.latest_stable):
                            target_v = comp.upstream.latest_stable

                    if target_v and target_v != current_v:
                        prof = result.profiles[r]
                        prop_path = os.path.join(prof.path, "gradle", "wrapper", "gradle-wrapper.properties")
                        actions.append(
                            UpdateAction(
                                repo_name=r,
                                file_path=prop_path,
                                component_identifier=comp.identifier,
                                key_or_alias="distributionUrl",
                                old_version=current_v,
                                new_version=target_v,
                                update_type=mode,
                            )
                        )
                continue

            # Library or Plugin update
            for r in repos:
                current_v = comp.repo_versions.get(r)
                if not current_v or current_v in ("None", "N/A"):
                    continue

                target_v = None
                if mode == "align" and comp.repo_statuses.get(r) == "repo-outdated":
                    target_v = comp.latest_in_repos
                elif mode == "upstream" and comp.upstream.latest_stable:
                    if parse_semver(current_v) < parse_semver(comp.upstream.latest_stable):
                        target_v = comp.upstream.latest_stable

                if not target_v or target_v == current_v:
                    continue

                prof = result.profiles[r]
                toml_path = os.path.join(prof.path, "gradle", "libs.versions.toml")
                toml_meta = prof.metadata.get("toml", {})
                raw_versions = toml_meta.get("versions", {})

                # Find which item in toml corresponds to this component
                found_alias = None
                is_ref = False
                ref_name = None

                items_dict = (
                    toml_meta.get("plugins", {})
                    if comp.component_type == "plugin"
                    else toml_meta.get("libraries", {})
                )

                for alias, item_data in items_dict.items():
                    coord = item_data.get("id") if comp.component_type == "plugin" else item_data.get("coord")
                    if coord == comp.identifier:
                        found_alias = alias
                        is_ref = item_data.get("is_ref", False)
                        ref_name = item_data.get("ref_name")
                        break

                if not found_alias:
                    continue

                actions.append(
                    UpdateAction(
                        repo_name=r,
                        file_path=toml_path,
                        component_identifier=comp.identifier,
                        key_or_alias=found_alias,
                        old_version=current_v,
                        new_version=target_v,
                        update_type=mode,
                        is_version_ref=is_ref,
                        ref_name=ref_name,
                    )
                )

        # De-duplicate actions if multiple libraries share the same version.ref
        deduped_actions: List[UpdateAction] = []
        seen_keys = set()
        for act in actions:
            dedup_key = (
                act.file_path,
                "ref:" + str(act.ref_name) if act.is_version_ref else "alias:" + str(act.key_or_alias),
            )
            if dedup_key not in seen_keys:
                seen_keys.add(dedup_key)
                deduped_actions.append(act)

        return deduped_actions

    def apply_actions(
        self, actions: List[UpdateAction], dry_run: bool = False
    ) -> List[Tuple[UpdateAction, bool]]:
        """Applies update actions using CatalogUpdater."""
        results: List[Tuple[UpdateAction, bool]] = []
        for act in actions:
            success = self.updater.apply_action(act, dry_run=dry_run)
            results.append((act, success))
        return results
