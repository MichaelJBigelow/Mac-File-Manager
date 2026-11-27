"""Find files with identical contents inside a folder."""

from __future__ import annotations

import hashlib
import os
import stat
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .fsutils import check_cancelled, is_dataless, is_hidden, is_package_name

# Files of the same size are first compared by a hash of their first block, and only files
# that still match are hashed in full.
PARTIAL_HASH_BYTES = 64 * 1024
READ_CHUNK_BYTES = 1024 * 1024

# progress(message, done, total). total == 0 means the amount of work is not known yet.
ProgressCallback = Callable[[str, int, int], None]


@dataclass(frozen=True)
class FileEntry:
    path: str
    size: int
    modified: float


@dataclass
class DuplicateGroup:
    """Files that have the same size and the same contents, oldest first."""

    size: int
    files: List[FileEntry]

    @property
    def reclaimable(self) -> int:
        """Bytes freed by keeping one copy and removing the others."""
        return self.size * (len(self.files) - 1)


@dataclass
class DuplicateScanOptions:
    include_hidden: bool = False
    include_packages: bool = False
    min_size: int = 1  # Bytes. Empty files are never reported.


@dataclass
class DuplicateScanResult:
    groups: List[DuplicateGroup]
    files_scanned: int
    unreadable: List[str] = field(default_factory=list)
    cloud_only: int = 0  # iCloud Drive files skipped because they are not downloaded.

    @property
    def reclaimable(self) -> int:
        return sum(group.reclaimable for group in self.groups)


def _no_progress(message: str, done: int, total: int) -> None:
    pass


def find_duplicates(
    root: str,
    options: Optional[DuplicateScanOptions] = None,
    progress: Optional[ProgressCallback] = None,
    cancel: Optional[threading.Event] = None,
) -> DuplicateScanResult:
    """Find groups of identical files under root.

    Symbolic links are skipped, and hard links to the same file count as one file, because
    removing one of them frees no space. Raises ScanCancelled if cancel is set.
    """
    if not os.path.isdir(root):
        raise NotADirectoryError(f"{root} is not a folder")
    options = options or DuplicateScanOptions()
    progress = progress or _no_progress
    result = DuplicateScanResult(groups=[], files_scanned=0)

    by_size = _collect_files(root, options, progress, cancel, result)
    candidates = [entries for entries in by_size.values() if len(entries) > 1]
    total = sum(len(entries) for entries in candidates)
    done = 0
    progress("Comparing file contents…", 0, total)

    for same_size in candidates:
        size = same_size[0].size
        by_partial: Dict[bytes, List[FileEntry]] = defaultdict(list)
        for entry in same_size:
            digest = _hash_file(entry.path, PARTIAL_HASH_BYTES, cancel)
            done += 1
            if done % 25 == 0 or done == total:
                progress("Comparing file contents…", done, total)
            if digest is None:
                result.unreadable.append(entry.path)
            else:
                by_partial[digest].append(entry)

        for partial_matches in by_partial.values():
            if len(partial_matches) < 2:
                continue
            if size <= PARTIAL_HASH_BYTES:
                result.groups.append(_make_group(size, partial_matches))
                continue
            by_full: Dict[bytes, List[FileEntry]] = defaultdict(list)
            for entry in partial_matches:
                progress(f"Comparing {os.path.basename(entry.path)}…", done, total)
                digest = _hash_file(entry.path, None, cancel)
                if digest is None:
                    result.unreadable.append(entry.path)
                else:
                    by_full[digest].append(entry)
            for matches in by_full.values():
                if len(matches) > 1:
                    result.groups.append(_make_group(size, matches))

    result.groups.sort(key=lambda group: (-group.reclaimable, group.files[0].path))
    return result


def _make_group(size: int, entries: List[FileEntry]) -> DuplicateGroup:
    return DuplicateGroup(size, sorted(entries, key=lambda e: (e.modified, e.path)))


def _collect_files(
    root: str,
    options: DuplicateScanOptions,
    progress: ProgressCallback,
    cancel: Optional[threading.Event],
    result: DuplicateScanResult,
) -> Dict[int, List[FileEntry]]:
    min_size = max(1, options.min_size)
    by_size: Dict[int, List[FileEntry]] = defaultdict(list)
    seen_inodes = set()
    stack = [root]
    while stack:
        check_cancelled(cancel)
        directory = stack.pop()
        try:
            with os.scandir(directory) as it:
                entries = list(it)
        except OSError:
            result.unreadable.append(directory)
            continue
        for entry in entries:
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                result.unreadable.append(entry.path)
                continue
            if stat.S_ISLNK(st.st_mode):
                continue
            if not options.include_hidden and is_hidden(entry.name, st):
                continue
            if stat.S_ISDIR(st.st_mode):
                if options.include_packages or not is_package_name(entry.name):
                    stack.append(entry.path)
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            result.files_scanned += 1
            if result.files_scanned % 500 == 0:
                progress(f"Looking for files… {result.files_scanned:,} so far", 0, 0)
            if st.st_size < min_size:
                continue
            if is_dataless(st):
                result.cloud_only += 1
                continue
            if st.st_nlink > 1:
                key = (st.st_dev, st.st_ino)
                if key in seen_inodes:
                    continue
                seen_inodes.add(key)
            by_size[st.st_size].append(FileEntry(entry.path, st.st_size, st.st_mtime))
    return by_size


def _hash_file(path: str, limit: Optional[int], cancel: Optional[threading.Event]) -> Optional[bytes]:
    """SHA-256 of the first `limit` bytes of a file (all of it if limit is None)."""
    digest = hashlib.sha256()
    remaining = limit
    try:
        with open(path, "rb") as handle:
            while remaining is None or remaining > 0:
                check_cancelled(cancel)
                wanted = READ_CHUNK_BYTES if remaining is None else min(READ_CHUNK_BYTES, remaining)
                chunk = handle.read(wanted)
                if not chunk:
                    break
                digest.update(chunk)
                if remaining is not None:
                    remaining -= len(chunk)
    except OSError:
        return None
    return digest.digest()
