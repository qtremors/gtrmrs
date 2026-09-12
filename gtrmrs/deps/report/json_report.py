"""
json_report.py

Machine-readable JSON report generator for dependency audits.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from gtrmrs.deps.models import AuditResult


class JsonReporter:
    """Generates a structured JSON representation of an audit result."""

    def to_dict(self, result: AuditResult) -> Dict[str, Any]:
        return {
            "base_dir": result.base_dir,
            "statistics": {
                "total_components": result.total_components,
                "repo_discrepancies": result.repo_discrepancies_count,
                "newer_upstream_available": result.upstream_available_count,
                "up_to_date": result.up_to_date_count,
            },
            "profiles": {
                name: {
                    "path": p.path,
                    "project_type": p.project_type,
                    "build_tool_version": p.build_tool_version,
                    "plugin_versions": p.plugin_versions,
                    "sdk_info": p.sdk_info,
                    "libraries_count": p.libraries_count,
                    "plugins_count": p.plugins_count,
                }
                for name, p in result.profiles.items()
            },
            "discrepancies": [
                {
                    "component": comp,
                    "latest_in_repos": latest,
                    "outdated_repos": outdated,
                }
                for comp, latest, outdated in result.discrepancies
            ],
            "upstream_updates": [
                {
                    "component": comp,
                    "current_version": cur,
                    "upstream_version": up,
                    "source": src,
                }
                for comp, cur, up, src in result.upstream_updates
            ],
            "components": [
                {
                    "identifier": c.identifier,
                    "type": c.component_type,
                    "category": c.category,
                    "repo_versions": c.repo_versions,
                    "latest_in_repos": c.latest_in_repos,
                    "upstream": {
                        "source": c.upstream.source,
                        "latest_stable": c.upstream.latest_stable,
                        "latest_overall": c.upstream.latest_overall,
                    },
                    "repo_statuses": c.repo_statuses,
                    "upstream_status": c.upstream_status,
                }
                for c in result.components
            ],
        }

    def generate(self, result: AuditResult, indent: int = 2) -> str:
        """Serializes the audit result into a formatted JSON string."""
        return json.dumps(self.to_dict(result), indent=indent)
