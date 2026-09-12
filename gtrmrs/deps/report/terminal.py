"""
terminal.py

Dynamic ANSI Terminal UI for dependency audit results.
"""

from __future__ import annotations

import io
import sys
from typing import Iterable, Optional, TextIO

from gtrmrs.core.colors import Colors
from gtrmrs.deps.models import AuditResult
from gtrmrs.deps.scanners.base import parse_semver


def _highest(versions: Iterable[Optional[str]]) -> str:
    return max((value for value in versions if value and value not in ("None", "N/A")), key=parse_semver, default="N/A")


class TerminalReporter:
    """Renders formatted terminal UI for dependency audit results."""

    def __init__(self, color_enabled: bool = True):
        self.color_enabled = color_enabled

    def _c(self, text: str, color_code: str) -> str:
        if not self.color_enabled:
            return text
        return f"{color_code}{text}{Colors.RESET}"

    def generate(self, result: AuditResult) -> str:
        buffer = io.StringIO()
        self.render(result, stream=buffer)
        return buffer.getvalue()

    def render(self, result: AuditResult, stream: Optional[TextIO] = None) -> None:
        """Prints the complete terminal audit report."""
        repos = sorted(result.profiles.keys())
        c = self._c

        def emit(message: str = "") -> None:
            print(message, file=stream if stream is not None else sys.stdout)

        # Header banner
        banner_text = "  === ANDROID REPOSITORIES DEPENDENCY & UPGRADE AUDITOR ===  "
        emit("\n" + c(banner_text, Colors.BOLD + "\033[44m" + Colors.WHITE) + "\n")

        # 1. Repository Profiles
        emit(c('--- REPOSITORY PROFILES ---', Colors.BOLD + Colors.CYAN))
        hdr = f"{'Repository':<18} {'Gradle':<10} {'AGP':<10} {'Kotlin':<10} {'BOM':<14} {'Min SDK':<10} {'Compile SDK':<12}"
        emit(c(hdr, Colors.BOLD))
        emit("-" * len(hdr))

        # Determine highest versions in profiles for relative coloring
        max_gradle = _highest(p.build_tool_version for p in result.profiles.values())
        max_agp = _highest(p.plugin_versions.get("agp") for p in result.profiles.values())
        max_kot = _highest(p.plugin_versions.get("kotlin-compose") or p.plugin_versions.get("kotlin-android") for p in result.profiles.values())
        max_bom = _highest(p.plugin_versions.get("compose-bom") for p in result.profiles.values())

        for r in repos:
            prof = result.profiles[r]
            g = prof.build_tool_version or "N/A"
            agp = prof.plugin_versions.get("agp") or "N/A"
            kotlin = prof.plugin_versions.get("kotlin-compose") or prof.plugin_versions.get("kotlin-android") or "N/A"
            bom = prof.plugin_versions.get("compose-bom") or "N/A"

            min_sdk_list = prof.sdk_info.get("minSdk", [])
            compile_sdk_list = prof.sdk_info.get("compileSdk", [])
            min_sdk = "/".join(min_sdk_list or []) or "Unknown"
            compile_sdk = "/".join(compile_sdk_list or []) or "Unknown"

            g_col = Colors.GREEN if g != "N/A" and parse_semver(g) == parse_semver(max_gradle) else Colors.YELLOW
            agp_col = Colors.GREEN if agp != "N/A" and parse_semver(agp) == parse_semver(max_agp) else Colors.YELLOW
            kot_col = Colors.GREEN if kotlin != "N/A" and parse_semver(kotlin) == parse_semver(max_kot) else Colors.YELLOW
            bom_col = Colors.GREEN if bom != "N/A" and parse_semver(bom) == parse_semver(max_bom) else Colors.YELLOW

            emit(
                c(f"{r:<18}", Colors.BOLD) + " "
                f"{c(f'{g:<10}', g_col)} "
                f"{c(f'{agp:<10}', agp_col)} "
                f"{c(f'{kotlin:<10}', kot_col)} "
                f"{c(f'{bom:<14}', bom_col)} "
                f"{min_sdk:<10} "
                f"{compile_sdk:<12}"
            )

        notes = [(repo, note) for repo in repos
                 for note in result.profiles[repo].metadata.get("declaration_notes", [])]
        unresolved = any(entry["kind"] != "literal" for component in result.components
                         for entries in component.repo_declarations.values() for entry in entries)
        coverage_limited = any(p.metadata.get("dependency_coverage", {}).get("complete") is False
                               for p in result.profiles.values())
        if notes:
            emit("\n" + c("--- DECLARATION NOTES ---", Colors.BOLD))
            for repo, note in notes:
                emit("  {}: {}".format(repo, note))

        # 2. Notable Discrepancies Across Repositories (Dynamically Computed)
        if result.discrepancies:
            emit("\n" + c('--- NOTABLE DISCREPANCIES ACROSS REPOSITORIES ---', Colors.BOLD + Colors.YELLOW))
            for comp_name, latest_info, outdated_info in result.discrepancies:
                emit(f"  * {c(comp_name, Colors.BOLD)}:")
                emit(f"    - {c('Latest in repos', Colors.GREEN)}: {latest_info}")
                emit(f"    - {c('Outdated repos ', Colors.YELLOW)}: {outdated_info}")
        else:
            emit("\n" + c('--- NOTABLE DISCREPANCIES ACROSS REPOSITORIES ---', Colors.BOLD + Colors.GREEN))
            message = ("No fixed-version discrepancies detected; review declaration and coverage notes."
                       if unresolved or coverage_limited else "No discrepancies detected across scanned repositories.")
            emit("  " + c(message, Colors.GREEN))

        # 3. Upstream Releases Available (Dynamically Computed)
        checks = result.upstream_checks
        emit("\n" + c('--- UPSTREAM RELEASES AVAILABLE (NEWER THAN ANY REPO) ---', Colors.BOLD + Colors.CYAN))
        emit("  Upstream checks: {checked} checked, {skipped} skipped, {unavailable} unavailable.".format(**checks))
        if result.upstream_updates:
            for comp, current, up_ver, src in result.upstream_updates:
                emit(
                    f"  * {c(f'{comp:<45}', Colors.BOLD)} "
                    f"{c(f'Current: {current:<32}', Colors.YELLOW)} -> "
                    f"{c(f'Update: {up_ver:<24}', Colors.BOLD + Colors.RED)} "
                    f"[{src}]"
                )
        elif checks["checked"]:
            emit("  No fixed-version update recommendations; review unresolved declarations." if unresolved
                 else "  No newer upstream releases found among checked components.")
        elif checks["skipped"] and not checks["unavailable"]:
            emit("  Upstream checks were skipped (--no-upstream).")
        elif checks["unavailable"]:
            emit("  Upstream information is unavailable; update status is unknown.")
        else:
            emit("  No components to check.")
        unknown_stable = sum(component.upstream_status == "Stable Release Unknown" for component in result.components)
        if unknown_stable:
            emit("  Stable release information is unknown for {} components.".format(unknown_stable))

        # 4. Audit Statistics
        emit("\n" + c('--- AUDIT STATISTICS ---', Colors.BOLD + Colors.GREEN))
        emit(f"  Total Scanned Components : {result.total_components}")
        emit(f"  Discrepancies in Repos   : {result.repo_discrepancies_count}")
        emit(f"  Newer Upstream Available : {result.upstream_available_count}")
        emit(f"  Fully Up-to-Date         : {result.up_to_date_count}\n")
