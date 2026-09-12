"""
models.py

Data structures for the dependency auditor and updater.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ProjectProfile:
    """Represents a scanned project and its build configuration."""
    name: str
    path: str
    project_type: str  # e.g., 'android', 'web', 'desktop'
    build_tool_version: Optional[str] = None  # e.g., Gradle wrapper version
    plugin_versions: Dict[str, str] = field(default_factory=dict)
    sdk_info: Dict[str, List[str]] = field(default_factory=dict)
    libraries_count: int = 0
    plugins_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UpstreamInfo:
    """Represents upstream release information for a component."""
    source: str
    latest_stable: Optional[str] = None
    latest_overall: Optional[str] = None


@dataclass
class Component:
    """Represents a library, plugin, or build tool across projects."""
    identifier: str  # e.g., 'androidx.appcompat:appcompat' or 'com.android.application'
    component_type: str  # 'library', 'plugin', 'build_tool'
    category: str  # 'UI & Compose', 'Build & Plugins', etc.
    repo_versions: Dict[str, Optional[str]] = field(default_factory=dict)
    latest_in_repos: str = "N/A"
    upstream: UpstreamInfo = field(default_factory=lambda: UpstreamInfo(source="N/A"))
    repo_statuses: Dict[str, str] = field(default_factory=dict)
    upstream_status: str = "N/A"


@dataclass
class UpdateAction:
    """Represents a planned version modification in a file."""
    repo_name: str
    file_path: str
    component_identifier: str
    key_or_alias: str
    old_version: str
    new_version: str
    update_type: str  # 'align' or 'upstream'
    is_version_ref: bool = False
    ref_name: Optional[str] = None


@dataclass
class AuditResult:
    """Aggregate result of an audit scan."""
    base_dir: str
    profiles: Dict[str, ProjectProfile]
    components: List[Component]
    discrepancies: List[Tuple[str, str, str]]  # (component_name, latest_repo_info, outdated_repos_info)
    upstream_updates: List[Tuple[str, str, str, str]]  # (component, current, update, source)
    total_components: int = 0
    repo_discrepancies_count: int = 0
    upstream_available_count: int = 0
    up_to_date_count: int = 0
