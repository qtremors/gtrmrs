"""Normalize catalog declarations without claiming resolved dependency versions."""

from __future__ import annotations

import json
from typing import Any


def _version(value: Any, versions: dict, library: bool) -> dict:
    reference = None
    if isinstance(value, dict) and "ref" in value:
        if set(value) != {"ref"} or not isinstance(value["ref"], str):
            raise ValueError("version.ref must be a single string reference")
        reference = value["ref"]
        if reference not in versions:
            raise ValueError("undefined version reference: " + reference)
        value = versions[reference]
    kind, issue, constraint = "literal", None, None
    if value is None:
        kind = "managed" if library else "unsupported"
        issue = None if library else "No plugin version declared"
        display = None
    elif isinstance(value, str):
        display = value
        if not value:
            kind, issue = "unsupported", "Empty version declaration"
        elif value.endswith("+") or value.startswith("latest.") or any(char in value for char in "[],()!"):
            kind, constraint = "constraint", value
    elif isinstance(value, dict):
        kind = "constraint"
        constraint = json.loads(json.dumps(value, default=str))
        display = next((value[key] for key in ("strictly", "require", "prefer")
                        if isinstance(value.get(key), str) and value[key]), "Constraint")
        invalid = set(value) - {"strictly", "require", "prefer", "reject", "rejectAll"}
        if invalid:
            issue = "Unsupported constraint keys: " + ", ".join(sorted(invalid))
        elif not value:
            issue = "Empty version constraint"
        elif any(key in value and (not isinstance(value[key], str) or not value[key])
                 for key in ("strictly", "require", "prefer")):
            issue = "Constraint versions must be nonempty strings"
        elif "reject" in value and (not isinstance(value["reject"], list)
                                    or any(not isinstance(item, str) for item in value["reject"])):
            issue = "Constraint reject must be a list of strings"
        elif "rejectAll" in value and not isinstance(value["rejectAll"], bool):
            issue = "Constraint rejectAll must be a boolean"
        if issue:
            kind = "unsupported"
    else:
        display, kind, issue = str(value), "unsupported", "Unsupported version value type"
    return {"version": display, "version_kind": kind, "version_constraint": constraint,
            "version_issue": issue, "is_ref": reference is not None, "ref_name": reference}


def normalize_catalog(data: dict, path: str) -> dict:
    """Validate section/coordinate shapes and retain rich declaration metadata."""
    sections = {}
    for name in ("versions", "libraries", "plugins"):
        section = data.get(name, {})
        if not isinstance(section, dict):
            raise ValueError("{}: [{}] must be a table".format(path, name))
        sections[name] = section
    versions = sections["versions"]
    result = {"versions": versions, "libraries": {}, "plugins": {}}
    for section in ("libraries", "plugins"):
        library = section == "libraries"
        for alias, entry in sections[section].items():
            try:
                if isinstance(entry, str):
                    parts = entry.split(":")
                    width = 2 if library else 1
                    if len(parts) not in (width, width + 1) or not all(parts[:width]):
                        raise ValueError("Invalid coordinate shorthand")
                    identifier = ":".join(parts[:width])
                    version = parts[width] if len(parts) > width else None
                elif isinstance(entry, dict):
                    if library:
                        identifier = entry.get("module")
                        if identifier is None:
                            group, name = entry.get("group"), entry.get("name")
                            if not isinstance(group, str) or not isinstance(name, str):
                                raise ValueError("Library needs module or string group/name fields")
                            identifier = group + ":" + name
                    else:
                        identifier = entry.get("id")
                    if not isinstance(identifier, str) or not identifier:
                        raise ValueError("Missing or invalid component identifier")
                    if "version.ref" in entry:
                        if "version" in entry:
                            raise ValueError("Conflicting version and version.ref declarations")
                        version = {"ref": entry["version.ref"]}
                    else:
                        version = entry.get("version")
                else:
                    raise ValueError("Component declaration must be a string or table")
                if library:
                    parts = identifier.split(":")
                    if len(parts) != 2 or not all(parts):
                        raise ValueError("Library module must have group:name form")
                    normalized = {"coord": identifier, "group": parts[0], "name": parts[1]}
                else:
                    normalized = {"id": identifier}
                normalized.update(_version(version, versions, library))
                result[section][alias] = normalized
            except ValueError as exc:
                raise ValueError("{}: [{}].{}: {}".format(path, section, alias, exc)) from exc
    return result
