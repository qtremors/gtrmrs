"""Single-pass file-size accounting without following filesystem links."""

from __future__ import annotations

import fnmatch
import os
import shutil
import stat
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


REASONS = {
    "rust": "Compiled dependencies, debug symbols, incremental state and build profiles",
    "web": "Generated web build output and bundler caches",
    "gradle": "Local Gradle/Kotlin caches and generated Android intermediates",
    "python": "Generated Python bytecode and tool caches",
    "node": "Installed JavaScript dependencies; reinstall from the manifest/lockfile",
    "venv": "Python environment; recreate and reinstall dependencies before use",
}
SENSITIVE = (
    ".env", ".env.*", "*.jks", "*.keystore", "*.p12", "*.pfx", "*.pem",
    "*.key", "*.p8", "*.p7b", "*.p7c", "*.der", "*.cer", "*.crt",
    "credentials", "credentials*.json", "*credentials.json", "secrets.json",
    "client_secret*.json", "*service-account*.json", "*service_account*.json",
    "*firebase-adminsdk*.json", "google-services.json",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".netrc", ".npmrc", ".pypirc", ".pgpass",
    "*.db", "*.sqlite", "*.sqlite3",
    "*.db-wal", "*.db-shm", "*.db-journal",
    "*.sqlite-wal", "*.sqlite-shm", "*.sqlite-journal",
    "*.sqlite3-wal", "*.sqlite3-shm", "*.sqlite3-journal",
    "local.properties", "signing.properties", "keystore.properties",
)
GRADLE_MARKERS = {"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}
ANDROID_GENERATED = {"intermediates", "generated", "kotlin", "tmp", "reports", "test-results"}
PYTHON_CACHES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def _linked(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & 0x400  # Windows reparse points
    )


def _git(repo: str, *args: str, data: Optional[bytes] = None) -> bytes:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", repo, *args],
        input=data, capture_output=True, timeout=30, env=env,
    )
    if result.returncode not in (0, 1) or (result.returncode and args[0] != "check-ignore"):
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or "Git failed")
    return result.stdout


@dataclass
class Candidate:
    path: str
    repo: str
    kind: str
    reason: str
    bytes: int = 0
    files: int = 0
    blockers: List[str] = field(default_factory=list)
    breakdown: Dict[str, int] = field(default_factory=dict)
    identity: Tuple[int, int] = (0, 0)

    @property
    def eligible(self) -> bool:
        return not self.blockers


@dataclass
class Repository:
    path: str
    bytes: int = 0
    files: int = 0
    git_bytes: int = 0
    git_objects: Dict[str, int] = field(default_factory=dict)


@dataclass
class Audit:
    root: str
    bytes: int = 0
    files: int = 0
    repositories: List[Repository] = field(default_factory=list)
    candidates: List[Candidate] = field(default_factory=list)
    skipped_links: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    keep_patterns: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = asdict(self)
        for entry, candidate in zip(result["candidates"], self.candidates):
            entry["eligible"] = candidate.eligible
        result["candidate_bytes"] = sum(c.bytes for c in self.candidates if c.eligible)
        return result


def _classification(path: Path, siblings: set) -> Optional[Tuple[str, str]]:
    name = path.name
    if name in {"debug", "release"}:
        target = path.parent if path.parent.name == "target" else path.parent.parent
        standard_target = path.parent == target or path.parent.name.count("-") >= 2
        if standard_target and target.name == "target" and (target.parent / "Cargo.toml").is_file():
            return "build", "rust"
    if name == "node_modules" and "package.json" in siblings:
        return "dependencies", "node"
    if name in {".next", ".nuxt", ".parcel-cache", ".turbo"} and "package.json" in siblings:
        return "build", "web"
    if name in {".venv", "venv"} and (path / "pyvenv.cfg").is_file():
        return "dependencies", "venv"
    if name in {".gradle", ".kotlin", ".cxx", ".externalNativeBuild"} and GRADLE_MARKERS & siblings:
        return "cache", "gradle"
    if name in ANDROID_GENERATED and path.parent.name == "build":
        if any((path.parent.parent / marker).is_file() for marker in GRADLE_MARKERS):
            return "build", "gradle"
    if name in PYTHON_CACHES:
        return "cache", "python"
    return None


def _protects_directory(name: str) -> bool:
    lower = name.lower()
    return lower in {
        ".git", ".hg", ".svn", "dist", "outputs", "models", "vendor", "third-party",
        "snapshots", "recovery", "recommit-tools",
        ".ssh", ".aws", ".gnupg", ".kube",
    } or "backup" in lower


class StorageEngine:
    def audit(self, root: str, keep_patterns: Optional[List[str]] = None) -> Audit:
        path = Path(os.path.abspath(root))
        if not path.is_dir() or _linked(path.lstat()):
            raise ValueError("Scan a real directory, not a link or junction")
        patterns = []
        for value in keep_patterns or []:
            pattern = value.replace("\\", "/").rstrip("/")
            if not pattern or pattern.startswith("/") or ":" in pattern or ".." in pattern.split("/"):
                raise ValueError("Keep patterns must be names or paths relative to the scan root")
            patterns.append(pattern.removeprefix("./"))
        audit = Audit(str(path), keep_patterns=patterns)
        # Discover the owning repository when starting from a project subdirectory.
        owner = None
        for ancestor in (path,) + tuple(path.parents):
            if (ancestor / ".git").exists():
                owner = Repository(str(ancestor))
                audit.repositories.append(owner)
                break
        self._walk(path, audit, owner, protected=any(_protects_directory(part) for part in path.parts))
        self._validate_candidates(audit)
        for repo in audit.repositories:
            try:
                counts = _git(repo.path, "count-objects", "-v").decode("ascii")
                repo.git_objects = {
                    key: int(value) for key, value in
                    (line.split(": ", 1) for line in counts.splitlines())
                }
            except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
                audit.errors.append("Git object summary unavailable for {}: {}".format(repo.path, exc))
        audit.repositories.sort(key=lambda repo: repo.bytes, reverse=True)
        audit.candidates.sort(key=lambda candidate: candidate.bytes, reverse=True)
        return audit

    def _walk(self, path: Path, audit: Audit, repo: Optional[Repository],
              candidate: Optional[Candidate] = None, protected: bool = False,
              in_git: bool = False) -> Tuple[int, int]:
        total = files = 0
        if candidate is not None and self._kept(path, audit):
            self._block(candidate, "Matches a user keep pattern: " + path.relative_to(audit.root).as_posix())
        try:
            with os.scandir(str(path)) as iterator:
                entries = list(iterator)
            names = {entry.name for entry in entries}
            if ".git" in names:
                if candidate is not None:
                    self._block(candidate, "Contains a nested Git repository")
                if not protected and candidate is None and (repo is None or repo.path != str(path)):
                    repo = Repository(str(path))
                    audit.repositories.append(repo)
            for entry in entries:
                child = path / entry.name
                try:
                    info = entry.stat(follow_symlinks=False)
                    if _linked(info):
                        audit.skipped_links.append(str(child))
                        if candidate is not None:
                            self._block(candidate, "Contains a skipped link or junction")
                        continue
                    if stat.S_ISDIR(info.st_mode):
                        retained = _protects_directory(entry.name)
                        if candidate is not None and candidate.kind == "dependencies":
                            # Packages commonly ship their own dist/vendor/models folders.
                            # These are installed dependency contents, not project releases.
                            retained = entry.name.lower() in {".git", ".hg", ".svn", "recovery", ".ssh", ".aws", ".gnupg", ".kube"} or "backup" in entry.name.lower()
                        child_protected = protected or retained
                        if candidate is not None and retained:
                            self._block(candidate, "Contains protected directory: " + child.relative_to(candidate.path).as_posix())
                        child_candidate = candidate
                        classification = None if child_protected or candidate else _classification(child, names)
                        if classification and repo is not None:
                            kind, reason = classification
                            # Windows DirEntry.stat can omit file IDs; lstat supplies them.
                            identity = child.lstat()
                            child_candidate = Candidate(
                                str(child), repo.path, kind, REASONS[reason],
                                identity=(identity.st_dev, identity.st_ino),
                            )
                            audit.candidates.append(child_candidate)
                        size, count = self._walk(
                            child, audit, repo, child_candidate, child_protected,
                            in_git or entry.name == ".git",
                        )
                        if candidate is not None:
                            rel = child.relative_to(candidate.path)
                            if len(rel.parts) <= 2:
                                candidate.breakdown[rel.as_posix()] = size
                    else:
                        size, count = info.st_size, 1
                        if repo is not None:
                            repo.bytes += size
                            repo.files += count
                            if in_git or entry.name == ".git":
                                repo.git_bytes += size
                        if candidate is not None and not stat.S_ISREG(info.st_mode):
                            self._block(candidate, "Contains a special filesystem entry")
                        if candidate is not None and any(
                            fnmatch.fnmatch(entry.name.lower(), pattern) for pattern in SENSITIVE
                        ):
                            self._block(candidate, "Contains credentials, local configuration or database files: " + child.relative_to(candidate.path).as_posix())
                        if candidate is not None and self._kept(child, audit):
                            self._block(candidate, "Matches a user keep pattern: " + child.relative_to(audit.root).as_posix())
                    total += size
                    files += count
                except OSError as exc:
                    audit.errors.append("{}: {}".format(child, exc))
                    if candidate is not None:
                        self._block(candidate, "Could not inspect every file")
        except OSError as exc:
            audit.errors.append("{}: {}".format(path, exc))
            if candidate is not None:
                self._block(candidate, "Could not inspect every file")
        if candidate is not None and str(path) == candidate.path:
            candidate.bytes, candidate.files = total, files
        if str(path) == audit.root:
            audit.bytes, audit.files = total, files
        return total, files

    @staticmethod
    def _kept(path: Path, audit: Audit) -> bool:
        if not audit.keep_patterns:
            return False
        relative = path.relative_to(audit.root)
        labels = ["."] + [Path(*relative.parts[:index]).as_posix()
                          for index in range(1, len(relative.parts) + 1)]
        for pattern in audit.keep_patterns:
            if os.name == "nt":
                pattern = pattern.casefold()
            for label in labels:
                if "/" not in pattern:
                    label = label.rsplit("/", 1)[-1]
                if os.name == "nt":
                    label = label.casefold()
                if fnmatch.fnmatchcase(label, pattern):
                    return True
        return False

    @staticmethod
    def _block(candidate: Candidate, reason: str) -> None:
        prefix = reason.split(":", 1)[0]
        matches = sum(item.split(":", 1)[0] == prefix for item in candidate.blockers)
        if reason not in candidate.blockers and matches < 3:
            candidate.blockers.append(reason)

    def _validate_candidates(self, audit: Audit) -> None:
        grouped: Dict[str, List[Candidate]] = {}
        for candidate in audit.candidates:
            grouped.setdefault(candidate.repo, []).append(candidate)
        for repo, candidates in grouped.items():
            paths = [Path(c.path).relative_to(repo).as_posix() + "/" for c in candidates]
            try:
                ignored_paths = _git(
                    repo, "check-ignore", "--stdin", "-z",
                    data=b"\0".join(os.fsencode(p) for p in paths) + b"\0",
                ).split(b"\0")
                # Includes both tracked files and unignored files, even inside otherwise
                # ignored output directories. Use literal pathspecs for unusual names.
                magic = ":(literal,icase)" if os.name == "nt" else ":(literal)"
                remaining_paths = _git(
                    repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--",
                    *[magic + p for p in paths],
                ).split(b"\0")
                def normalize(value: bytes) -> str:
                    decoded = os.fsdecode(value)
                    return decoded.casefold() if os.name == "nt" else decoded

                ignored = {normalize(name) for name in ignored_paths if name}
                remaining = [normalize(name) for name in remaining_paths if name]
                for candidate, relative in zip(candidates, paths):
                    prefix = normalize(os.fsencode(relative))
                    if prefix not in ignored:
                        self._block(candidate, "Directory is not ignored by Git")
                    if any(name.startswith(prefix) for name in remaining):
                        self._block(candidate, "Contains tracked or unignored files")
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                for candidate in candidates:
                    self._block(candidate, "Git could not verify cleanup eligibility")
                audit.errors.append("Git cleanup checks failed for {}: {}".format(repo, exc))

    def clean(self, audit: Audit, selected: List[Candidate], apply: bool = False) -> List[dict]:
        """Preview by default. Reinspect each selected subtree immediately before removal."""
        results = []
        known = {id(candidate) for candidate in audit.candidates}
        for candidate in selected:
            result = {"path": candidate.path, "bytes": candidate.bytes, "status": "preview"}
            try:
                if id(candidate) not in known or not candidate.eligible:
                    raise ValueError("Candidate is not eligible for cleanup")
                path = Path(candidate.path)
                root = Path(audit.root)
                if root not in path.parents or Path(os.path.realpath(str(path))) != path:
                    raise ValueError("Cleanup path escaped the scan root or became a link")
                info = path.lstat()
                if _linked(info) or (info.st_dev, info.st_ino) != candidate.identity:
                    raise ValueError("Directory changed since the audit")
                if apply:
                    fresh = Audit(audit.root, keep_patterns=list(audit.keep_patterns))
                    current = Candidate(candidate.path, candidate.repo, candidate.kind, candidate.reason)
                    fresh.candidates.append(current)
                    self._walk(path, fresh, Repository(candidate.repo), current)
                    self._validate_candidates(fresh)
                    if current.blockers:
                        raise ValueError("; ".join(current.blockers))
                    # Revalidate the absolute boundary and identity after inspecting contents.
                    info = path.lstat()
                    if Path(os.path.realpath(str(path))) != path or _linked(info) or (
                        info.st_dev, info.st_ino
                    ) != candidate.identity:
                        raise ValueError("Directory changed during cleanup checks")
                    shutil.rmtree(str(path))
                    result.update(status="removed", bytes=current.bytes)
            except (OSError, ValueError) as exc:
                result.update(status="refused", error=str(exc))
            results.append(result)
        return results
