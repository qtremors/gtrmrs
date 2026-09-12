"""
html.py

Standalone interactive HTML report generator for dependency audits.
"""

from __future__ import annotations

import os
from typing import List

from gtrmrs.deps.models import AuditResult, Component


class HtmlReporter:
    """Generates an interactive HTML audit report."""

    def generate(self, result: AuditResult, output_path: str) -> None:
        """Writes the standalone interactive HTML report to output_path."""
        repos = sorted(result.profiles.keys())
        total_items = result.total_components
        outdated_count = result.repo_discrepancies_count
        upstream_count = result.upstream_available_count
        up_to_date_count = result.up_to_date_count

        repo_names_joined = ", ".join(repos)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Android Repositories Dependency & Upgrade Audit</title>
<style>
  :root {{
    --bg: #0f172a;
    --card-bg: #1e293b;
    --border: #334155;
    --text: #f8fafc;
    --text-muted: #94a3b8;
    --primary: #38bdf8;
    --success: #10b981;
    --success-bg: rgba(16, 185, 129, 0.15);
    --warning: #f59e0b;
    --warning-bg: rgba(245, 158, 11, 0.15);
    --danger: #ef4444;
    --danger-bg: rgba(239, 68, 68, 0.15);
    --info: #818cf8;
    --info-bg: rgba(129, 140, 248, 0.15);
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 24px;
    line-height: 1.5;
  }}
  .container {{ max-width: 1600px; margin: 0 auto; }}
  header {{
    margin-bottom: 24px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
  }}
  h1 {{ font-size: 26px; font-weight: 700; color: #fff; margin-bottom: 6px; }}
  .subtitle {{ color: var(--text-muted); font-size: 14px; }}
  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }}
  .stat-card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px 20px;
  }}
  .stat-val {{ font-size: 28px; font-weight: 800; margin-bottom: 4px; }}
  .stat-lbl {{ color: var(--text-muted); font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; }}
  
  .repo-summary-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 16px;
    margin-bottom: 28px;
  }}
  .repo-card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
  }}
  .repo-title {{ font-size: 17px; font-weight: 700; color: var(--primary); margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }}
  .repo-meta {{ font-size: 13px; color: var(--text-muted); margin-bottom: 6px; display: flex; justify-content: space-between; }}
  .repo-meta strong {{ color: #e2e8f0; }}

  .controls {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 20px;
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    align-items: center;
    justify-content: space-between;
  }}
  .search-box {{
    flex: 1;
    min-width: 280px;
    padding: 10px 14px;
    border-radius: 6px;
    background: #0f172a;
    border: 1px solid var(--border);
    color: #fff;
    font-size: 14px;
  }}
  .search-box:focus {{ outline: none; border-color: var(--primary); }}
  .filter-group {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .filter-btn {{
    background: #0f172a;
    border: 1px solid var(--border);
    color: var(--text-muted);
    padding: 8px 14px;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;
  }}
  .filter-btn.active, .filter-btn:hover {{
    background: var(--primary);
    color: #0f172a;
    font-weight: 600;
    border-color: var(--primary);
  }}

  .table-wrap {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow-x: auto;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    text-align: left;
    font-size: 13px;
  }}
  th {{
    background: #141f32;
    padding: 12px 14px;
    font-weight: 600;
    color: var(--text-muted);
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
    position: sticky;
    top: 0;
  }}
  td {{
    padding: 12px 14px;
    border-bottom: 1px solid #27354a;
    vertical-align: middle;
  }}
  tr:hover td {{ background: rgba(56, 189, 248, 0.03); }}
  
  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  }}
  .badge-success {{ background: var(--success-bg); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.3); }}
  .badge-warning {{ background: var(--warning-bg); color: var(--warning); border: 1px solid rgba(245, 158, 11, 0.3); }}
  .badge-danger {{ background: var(--danger-bg); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); }}
  .badge-info {{ background: var(--info-bg); color: var(--info); border: 1px solid rgba(129, 140, 248, 0.3); }}
  .badge-muted {{ background: rgba(148, 163, 184, 0.1); color: #64748b; }}
  
  .comp-name {{ font-weight: 600; color: #fff; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }}
  .comp-type {{ font-size: 11px; color: var(--text-muted); text-transform: uppercase; margin-top: 2px; }}
  .comp-cat {{ display: inline-block; font-size: 11px; color: #38bdf8; background: rgba(56, 189, 248, 0.1); padding: 1px 6px; border-radius: 3px; margin-top: 3px; }}
</style>
</head>
<body>

<div class="container">
  <header>
    <h1>Android Repositories Dependency & Upgrade Audit</h1>
    <div class="subtitle">Scanned repos: <strong>{repo_names_joined}</strong></div>
  </header>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-val" style="color: var(--primary);">{total_items}</div>
      <div class="stat-lbl">Total Components Scanned</div>
    </div>
    <div class="stat-card">
      <div class="stat-val" style="color: var(--warning);">{outdated_count}</div>
      <div class="stat-lbl">Discrepancies Across Repos</div>
    </div>
    <div class="stat-card">
      <div class="stat-val" style="color: var(--danger);">{upstream_count}</div>
      <div class="stat-lbl">Newer Upstream Available</div>
    </div>
    <div class="stat-card">
      <div class="stat-val" style="color: var(--success);">{up_to_date_count}</div>
      <div class="stat-lbl">Fully Up-to-Date</div>
    </div>
  </div>

  <div class="repo-summary-grid">
"""

        for r in repos:
            prof = result.profiles[r]
            g_ver = prof.build_tool_version or "N/A"
            agp_ver = prof.plugin_versions.get("agp") or "N/A"
            kotlin_ver = prof.plugin_versions.get("kotlin-compose") or prof.plugin_versions.get("kotlin-android") or "N/A"
            msdk = ", ".join(prof.sdk_info.get("minSdk", ["24"]))
            csdk = ", ".join(prof.sdk_info.get("compileSdk", ["37"]))
            libs_cnt = prof.libraries_count

            html += f"""
    <div class="repo-card">
      <div class="repo-title">
        <span>{r}</span>
        <span class="badge badge-info">{libs_cnt} libs</span>
      </div>
      <div class="repo-meta"><span>Gradle:</span> <strong>{g_ver}</strong></div>
      <div class="repo-meta"><span>AGP:</span> <strong>{agp_ver}</strong></div>
      <div class="repo-meta"><span>Kotlin:</span> <strong>{kotlin_ver}</strong></div>
      <div class="repo-meta"><span>SDKs (min / compile):</span> <strong>{msdk} / {csdk}</strong></div>
    </div>
"""

        html += """
  </div>

  <div class="controls">
    <input type="text" id="searchInput" class="search-box" placeholder="Search by library name, artifact, group or version..." onkeyup="filterTable()">
    <div class="filter-group">
      <button class="filter-btn active" onclick="setFilter('all', this)">All Items</button>
      <button class="filter-btn" onclick="setFilter('repo-outdated', this)">Repo Discrepancies</button>
      <button class="filter-btn" onclick="setFilter('upstream-update', this)">Upstream Updates</button>
      <button class="filter-btn" onclick="setFilter('Build & Plugins', this)">Build & Plugins</button>
      <button class="filter-btn" onclick="setFilter('UI & Compose', this)">UI & Compose</button>
      <button class="filter-btn" onclick="setFilter('AndroidX & Architecture', this)">AndroidX</button>
      <button class="filter-btn" onclick="setFilter('Media & Graphics', this)">Media</button>
      <button class="filter-btn" onclick="setFilter('Testing', this)">Testing</button>
    </div>
  </div>

  <div class="table-wrap">
    <table id="depTable">
      <thead>
        <tr>
          <th>Component / Artifact</th>
"""
        for r in repos:
            html += f"          <th>{r}</th>\n"
        html += """          <th>Latest in Repos</th>
          <th>Upstream Stable</th>
          <th>Upstream Status</th>
        </tr>
      </thead>
      <tbody>
"""

        def render_repo_cell(v, st):
            if st == "unused" or not v:
                return '<span class="badge badge-muted">-</span>'
            if st == "bom-managed":
                return '<span class="badge badge-info">BOM</span>'
            if st == "repo-outdated":
                return f'<span class="badge badge-warning">{v}</span>'
            return f'<span class="badge badge-success">{v}</span>'

        def render_upstream_status_badge(st, up_stable, up_overall):
            if st == "Newer Stable Available":
                return f'<span class="badge badge-danger">Update: {up_stable}</span>'
            if st == "Newer Preview Available":
                return f'<span class="badge badge-warning">Preview: {up_overall}</span>'
            if st == "Up to Date":
                return '<span class="badge badge-success">OK Up to Date</span>'
            if st == "BOM Managed":
                return '<span class="badge badge-info">Managed by BOM</span>'
            return f'<span class="badge badge-muted">{st}</span>'

        for comp in result.components:
            name = comp.identifier
            cat = comp.category
            ctype = comp.component_type
            in_repo_max = comp.latest_in_repos
            up_stable = comp.upstream.latest_stable or "-"
            up_overall = comp.upstream.latest_overall or "-"
            up_status = comp.upstream_status

            has_repo_outdated = any(s == "repo-outdated" for s in comp.repo_statuses.values())
            has_upstream_update = up_status in ["Newer Stable Available", "Newer Preview Available"]

            row_classes = []
            if has_repo_outdated:
                row_classes.append("row-repo-outdated")
            if has_upstream_update:
                row_classes.append("row-upstream-update")

            class_attr = f'class="{" ".join(row_classes)}"' if row_classes else ""

            html += f"""
        <tr {class_attr} data-category="{cat}">
          <td>
            <div class="comp-name">{name}</div>
            <div><span class="comp-cat">{cat}</span> <span class="comp-type">{ctype}</span></div>
          </td>
"""
            for r in repos:
                v = comp.repo_versions.get(r)
                st = comp.repo_statuses.get(r, "unused")
                html += f"          <td>{render_repo_cell(v, st)}</td>\n"

            html += f"""          <td><strong style="color: var(--primary);">{in_repo_max}</strong></td>
          <td><strong>{up_stable}</strong></td>
          <td>{render_upstream_status_badge(up_status, up_stable, up_overall)}</td>
        </tr>
"""

        html += """
      </tbody>
    </table>
  </div>
</div>

<script>
let currentFilter = 'all';

function setFilter(filter, btn) {
  currentFilter = filter;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  filterTable();
}

function filterTable() {
  const q = document.getElementById('searchInput').value.toLowerCase();
  const rows = document.querySelectorAll('#depTable tbody tr');

  rows.forEach(tr => {
    const text = tr.innerText.toLowerCase();
    const cat = tr.getAttribute('data-category');
    const isRepoOutdated = tr.classList.contains('row-repo-outdated');
    const isUpstreamUpdate = tr.classList.contains('row-upstream-update');

    let matchesFilter = true;
    if (currentFilter === 'repo-outdated') {
      matchesFilter = isRepoOutdated;
    } else if (currentFilter === 'upstream-update') {
      matchesFilter = isUpstreamUpdate;
    } else if (currentFilter !== 'all') {
      matchesFilter = (cat === currentFilter);
    }

    const matchesQuery = !q || text.includes(q);
    tr.style.display = (matchesFilter && matchesQuery) ? '' : 'none';
  });
}
</script>

</body>
</html>
"""

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
