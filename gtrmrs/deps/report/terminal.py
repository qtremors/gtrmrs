"""
terminal.py

Dynamic ANSI Terminal UI for dependency audit results.
"""

from __future__ import annotations

from typing import List

from gtrmrs.core.colors import Colors
from gtrmrs.deps.models import AuditResult


class TerminalReporter:
    """Renders formatted terminal UI for dependency audit results."""

    def __init__(self, color_enabled: bool = True):
        self.color_enabled = color_enabled

    def _c(self, text: str, color_code: str) -> str:
        if not self.color_enabled:
            return text
        return f"{color_code}{text}{Colors.RESET}"

    def render(self, result: AuditResult) -> None:
        """Prints the complete terminal audit report."""
        repos = sorted(result.profiles.keys())
        c = self._c

        # Header banner
        banner_text = "  === ANDROID REPOSITORIES DEPENDENCY & UPGRADE AUDITOR ===  "
        print(f"\n{Colors.BOLD}\033[44m{Colors.WHITE}{banner_text}{Colors.RESET}\n")

        # 1. Repository Profiles
        print(f"{Colors.BOLD}{c('--- REPOSITORY PROFILES ---', Colors.CYAN)}")
        hdr = f"{'Repository':<18} {'Gradle':<10} {'AGP':<10} {'Kotlin':<10} {'BOM':<14} {'Min SDK':<10} {'Compile SDK':<12}"
        print(f"{Colors.BOLD}{hdr}{Colors.RESET}")
        print("-" * len(hdr))

        # Determine highest versions in profiles for relative coloring
        max_gradle = max((p.build_tool_version or "0" for p in result.profiles.values()), default="N/A")
        max_agp = max((p.plugin_versions.get("agp", "0") for p in result.profiles.values()), default="N/A")
        max_kot = max((p.plugin_versions.get("kotlin-compose") or p.plugin_versions.get("kotlin-android") or "0" for p in result.profiles.values()), default="N/A")
        max_bom = max((p.plugin_versions.get("compose-bom", "0") for p in result.profiles.values()), default="N/A")

        for r in repos:
            prof = result.profiles[r]
            g = prof.build_tool_version or "N/A"
            agp = prof.plugin_versions.get("agp") or "N/A"
            kotlin = prof.plugin_versions.get("kotlin-compose") or prof.plugin_versions.get("kotlin-android") or "N/A"
            bom = prof.plugin_versions.get("compose-bom") or "N/A"

            min_sdk_list = prof.sdk_info.get("minSdk", [])
            compile_sdk_list = prof.sdk_info.get("compileSdk", [])
            min_sdk = "/".join(min_sdk_list) if min_sdk_list else "N/A"
            compile_sdk = "/".join(compile_sdk_list) if compile_sdk_list else "N/A"

            g_col = Colors.GREEN if g == max_gradle and g != "N/A" else Colors.YELLOW
            agp_col = Colors.GREEN if agp == max_agp and agp != "N/A" else Colors.YELLOW
            kot_col = Colors.GREEN if kotlin == max_kot and kotlin != "N/A" else Colors.YELLOW
            bom_col = Colors.GREEN if bom == max_bom and bom != "N/A" else Colors.YELLOW

            print(
                f"{Colors.BOLD}{r:<18}{Colors.RESET} "
                f"{c(f'{g:<10}', g_col)} "
                f"{c(f'{agp:<10}', agp_col)} "
                f"{c(f'{kotlin:<10}', kot_col)} "
                f"{c(f'{bom:<14}', bom_col)} "
                f"{min_sdk:<10} "
                f"{compile_sdk:<12}"
            )

        # 2. Notable Discrepancies Across Repositories (Dynamically Computed)
        if result.discrepancies:
            print("\n" + f"{Colors.BOLD}{c('--- NOTABLE DISCREPANCIES ACROSS REPOSITORIES ---', Colors.YELLOW)}")
            for comp_name, latest_info, outdated_info in result.discrepancies:
                print(f"  * {Colors.BOLD}{comp_name}{Colors.RESET}:")
                print(f"    - {c('Latest in repos', Colors.GREEN)}: {latest_info}")
                print(f"    - {c('Outdated repos ', Colors.YELLOW)}: {outdated_info}")
        else:
            print("\n" + f"{Colors.BOLD}{c('--- NOTABLE DISCREPANCIES ACROSS REPOSITORIES ---', Colors.GREEN)}")
            print(f"  {c('No discrepancies detected across scanned repositories.', Colors.GREEN)}")

        # 3. Upstream Releases Available (Dynamically Computed)
        if result.upstream_updates:
            print("\n" + f"{Colors.BOLD}{c('--- UPSTREAM RELEASES AVAILABLE (NEWER THAN ANY REPO) ---', Colors.RED)}")
            for comp, current, up_ver, src in result.upstream_updates:
                print(
                    f"  * {Colors.BOLD}{comp:<45}{Colors.RESET} "
                    f"{c(f'Current: {current:<32}', Colors.YELLOW)} -> "
                    f"{Colors.BOLD}{c(f'Update: {up_ver:<24}', Colors.RED)} "
                    f"[{src}]"
                )
        else:
            print("\n" + f"{Colors.BOLD}{c('--- UPSTREAM RELEASES AVAILABLE (NEWER THAN ANY REPO) ---', Colors.GREEN)}")
            print(f"  {c('All components are aligned with upstream stable releases.', Colors.GREEN)}")

        # 4. Audit Statistics
        print("\n" + f"{Colors.BOLD}{c('--- AUDIT STATISTICS ---', Colors.GREEN)}")
        print(f"  Total Scanned Components : {result.total_components}")
        print(f"  Discrepancies in Repos   : {result.repo_discrepancies_count}")
        print(f"  Newer Upstream Available : {result.upstream_available_count}")
        print(f"  Fully Up-to-Date         : {result.up_to_date_count}\n")
