"""Find duplicate files: group by size first, then by SHA-256."""
from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

CHUNK = 1024 * 1024
KEEP_RULES = ("oldest", "newest", "shortest")


@dataclass
class Group:
    sha256: str
    size: int
    files: list[str]

    @property
    def reclaimable(self) -> int:
        return self.size * (len(self.files) - 1)


@dataclass
class Error:
    path: str
    message: str


@dataclass
class Result:
    root: str
    files_scanned: int = 0
    groups: list[Group] = field(default_factory=list)
    errors: list[Error] = field(default_factory=list)

    @property
    def reclaimable(self) -> int:
        return sum(g.reclaimable for g in self.groups)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _walk(folder: str, errors: list[Error]):
    """Regular files under `folder`, without following symlinks."""
    try:
        entries = list(os.scandir(folder))
    except OSError as e:
        errors.append(Error(folder, e.strerror or str(e)))
        return
    for entry in entries:
        try:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                yield from _walk(entry.path, errors)
            elif entry.is_file():
                yield entry.path, entry.stat().st_size
        except OSError as e:
            errors.append(Error(entry.path, e.strerror or str(e)))


def scan(root: str | Path, min_size: int = 1) -> Result:
    root = Path(root).resolve()
    result = Result(root=str(root))

    by_size: dict[int, list[str]] = defaultdict(list)
    for path, size in _walk(str(root), result.errors):
        if size >= min_size:
            by_size[size].append(path)
            result.files_scanned += 1

    for size, paths in sorted(by_size.items(), reverse=True):
        if len(paths) < 2:
            continue  # a file with a unique size cannot have a duplicate: never read it
        by_hash: dict[str, list[str]] = defaultdict(list)
        for path in paths:
            try:
                by_hash[sha256(path)].append(path)
            except OSError as e:
                result.errors.append(Error(path, e.strerror or str(e)))
        for digest, same in by_hash.items():
            if len(same) > 1:
                result.groups.append(Group(digest, size, sorted(same)))
    return result


def file_to_keep(group: Group, rule: str = "oldest") -> str:
    """Ties are broken by alphabetical path order, so the choice is always the same."""
    if rule == "shortest":
        return min(group.files, key=lambda f: (len(f), f))
    mtimes = {f: os.stat(f).st_mtime for f in group.files}
    if rule == "newest":
        return min(group.files, key=lambda f: (-mtimes[f], f))
    return min(group.files, key=lambda f: (mtimes[f], f))


def clean(result: Result, keep: dict[str, str]) -> list[str]:
    """Delete every file except the one kept for each group. Returns the deleted paths."""
    deleted = []
    for group in result.groups:
        for path in group.files:
            if path == keep[group.sha256]:
                continue
            try:
                os.remove(path)
                deleted.append(path)
            except OSError as e:
                result.errors.append(Error(path, f"could not delete: {e.strerror or e}"))
    return deleted
