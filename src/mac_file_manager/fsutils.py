"""File-system helpers shared by the scanners and the user interface."""

from __future__ import annotations

import os
import stat
import subprocess
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

# Folders with these extensions are bundles or packages: Finder shows each one as a single item.
PACKAGE_EXTENSIONS = frozenset(
    {
        ".app",
        ".appex",
        ".bundle",
        ".dsym",
        ".fcpbundle",
        ".framework",
        ".imovielibrary",
        ".kext",
        ".logicx",
        ".musiclibrary",
        ".photoslibrary",
        ".playground",
        ".plugin",
        ".prefpane",
        ".qlgenerator",
        ".rtfd",
        ".saver",
        ".tvlibrary",
        ".xcarchive",
        ".xcodeproj",
        ".xcworkspace",
        ".xpc",
    }
)

# st_flags bit for an iCloud Drive file whose contents are not downloaded. Reading such a
# file makes macOS download it, so scans skip them.
SF_DATALESS = 0x40000000

TRASH_COMMAND = "/usr/bin/trash"  # Ships with macOS 15 and later.
_TRASH_BATCH_SIZE = 200

# Fallback for macOS 14 and earlier. Paths arrive as arguments, never inside the script text.
_FINDER_TRASH_SCRIPT = """
on run argv
    set failures to {}
    repeat with p in argv
        set itemPath to contents of p
        try
            set itemAlias to (POSIX file itemPath) as alias
            tell application "Finder" to delete itemAlias
        on error errorMessage
            set end of failures to itemPath & ": " & errorMessage
        end try
    end repeat
    set AppleScript's text item delimiters to linefeed
    return failures as text
end run
"""


class ScanCancelled(Exception):
    """Raised inside a scan after the user presses Cancel."""


def check_cancelled(cancel: Optional[threading.Event]) -> None:
    if cancel is not None and cancel.is_set():
        raise ScanCancelled()


def is_package_name(name: str) -> bool:
    """True when a folder with this name is a bundle or package (an app, a library, ...)."""
    return os.path.splitext(name)[1].lower() in PACKAGE_EXTENSIONS


def is_hidden(name: str, st: Optional[os.stat_result] = None) -> bool:
    """True for dot files and for items Finder hides (such as ~/Library)."""
    if name.startswith("."):
        return True
    flags = getattr(st, "st_flags", 0) or 0
    return bool(flags & getattr(stat, "UF_HIDDEN", 0))


def is_dataless(st: os.stat_result) -> bool:
    """True for an iCloud Drive file that is stored only in iCloud."""
    return bool((getattr(st, "st_flags", 0) or 0) & SF_DATALESS)


def format_size(num_bytes: int) -> str:
    """Format a byte count the way Finder does (1 KB = 1,000 bytes)."""
    if num_bytes < 1000:
        return "1 byte" if num_bytes == 1 else f"{num_bytes:,} bytes"
    value = float(num_bytes)
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1000
        if value < 999.95:
            return f"{value:.1f} {unit}"
    return f"{value / 1000:,.1f} PB"


def path_size(path: str, cancel: Optional[threading.Event] = None) -> int:
    """Total size in bytes of a file, or of everything inside a folder.

    Symbolic links are not followed, and a file with several hard links inside the folder
    is counted once. Items that cannot be read are skipped.
    """
    try:
        st = os.lstat(path)
    except OSError:
        return 0
    if not stat.S_ISDIR(st.st_mode):
        return st.st_size

    total = 0
    seen_inodes = set()
    stack = [path]
    while stack:
        check_cancelled(cancel)
        directory = stack.pop()
        try:
            with os.scandir(directory) as it:
                entries = list(it)
        except OSError:
            continue
        for entry in entries:
            try:
                entry_st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISDIR(entry_st.st_mode):
                stack.append(entry.path)
                continue
            if entry_st.st_nlink > 1:
                key = (entry_st.st_dev, entry_st.st_ino)
                if key in seen_inodes:
                    continue
                seen_inodes.add(key)
            total += entry_st.st_size
    return total


def reveal_in_finder(paths: Sequence[str]) -> Optional[str]:
    """Select the items in Finder. Returns an error message, or None on success."""
    if not paths:
        return None
    try:
        completed = subprocess.run(
            ["/usr/bin/open", "-R", *[os.path.abspath(p) for p in paths]],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return str(exc)
    if completed.returncode != 0:
        return completed.stderr.strip() or f"open exited with status {completed.returncode}"
    return None


@dataclass
class TrashResult:
    moved: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    details: str = ""


def move_to_trash(paths: Sequence[str]) -> TrashResult:
    """Move items to the user's Trash, where they can be restored until it is emptied.

    Uses /usr/bin/trash (macOS 15+) and falls back to asking Finder. An item counts as
    moved once it no longer exists at its old path.
    """
    targets = list(dict.fromkeys(os.path.abspath(p) for p in paths))
    messages = []
    for start in range(0, len(targets), _TRASH_BATCH_SIZE):
        batch = targets[start : start + _TRASH_BATCH_SIZE]
        if os.access(TRASH_COMMAND, os.X_OK):
            command = [TRASH_COMMAND, *batch]
        else:
            command = ["/usr/bin/osascript", "-e", _FINDER_TRASH_SCRIPT, *batch]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
        except OSError as exc:
            messages.append(str(exc))
            continue
        for stream in (completed.stdout, completed.stderr):
            if stream and stream.strip():
                messages.append(stream.strip())

    result = TrashResult(details="\n".join(messages))
    for target in targets:
        (result.failed if os.path.lexists(target) else result.moved).append(target)
    if not result.failed:
        result.details = ""
    return result


def display_path(path: str, home: Optional[str] = None) -> str:
    """Shorten a path inside the home folder to ~/..."""
    home = home or os.path.expanduser("~")
    if path == home:
        return "~"
    if path.startswith(home + os.sep):
        return "~" + path[len(home) :]
    return path
