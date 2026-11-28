"""Find caches, logs, old versions and build output that developer tools leave behind."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import unquote, urlparse

from .fsutils import check_cancelled, is_hidden, is_package_name, path_size

ANDROID_STUDIO = "Android Studio"
VS_CODE = "Visual Studio Code"
GRADLE = "Gradle"
UNITY = "Unity"
TOOLS = (ANDROID_STUDIO, VS_CODE, GRADLE, UNITY)

# Kinds of leftover data.
CACHE = "Cache"
LOGS = "Logs"
BUILD_OUTPUT = "Build output"
OLD_VERSION = "Old version"
ORPHANED = "Orphaned"
NOT_INSTALLED = "App not installed"
IN_USE = "In use"  # Still used by an installed tool. Shown only on request.

ProgressCallback = Callable[[str, int, int], None]


@dataclass
class Leftover:
    tool: str
    kind: str
    path: str
    note: str
    size: int = 0


def _no_progress(message: str, done: int, total: int) -> None:
    pass


def find_leftovers(
    tools: Iterable[str],
    home: Optional[str] = None,
    project_root: Optional[str] = None,
    app_dirs: Optional[Sequence[str]] = None,
    progress: Optional[ProgressCallback] = None,
    cancel: Optional[threading.Event] = None,
    use_spotlight: bool = True,
) -> List[Leftover]:
    """Find leftover data for the chosen tools and measure how much space each item uses.

    home defaults to the user's home folder and app_dirs to /Applications and ~/Applications.
    An app also counts as installed if Spotlight finds it elsewhere, unless use_spotlight is
    False. When project_root is given, it is also searched for project build folders.
    Raises ScanCancelled if cancel is set.
    """
    tools = set(tools)
    progress = progress or _no_progress
    home_path = Path(home) if home else Path.home()
    dirs = [Path(d) for d in app_dirs] if app_dirs is not None else _default_app_dirs(home_path)
    apps = _AppFinder(dirs, use_spotlight)

    progress("Checking developer tool folders…", 0, 0)
    items: List[Leftover] = []
    if ANDROID_STUDIO in tools:
        items.extend(_android_studio(home_path, apps))
    if VS_CODE in tools:
        items.extend(_vs_code(home_path, apps))
    if GRADLE in tools:
        items.extend(_gradle(home_path / ".gradle"))
    if UNITY in tools:
        items.extend(_unity(home_path, apps))
    if project_root:
        items.extend(scan_projects(project_root, tools, progress, cancel))
    items = _without_nested(items)

    for index, item in enumerate(items):
        progress(f"Measuring {os.path.basename(item.path)}…", index, len(items))
        item.size = path_size(item.path, cancel)
    progress("Done", len(items), len(items))
    return items


# --- Helpers ---------------------------------------------------------------------------


class _Collector:
    """Collects leftovers for one tool, keeping only paths that exist."""

    def __init__(self, tool: str) -> None:
        self.tool = tool
        self.items: List[Leftover] = []

    def add(self, path: Path, kind: str, note: str) -> None:
        if os.path.lexists(path):
            self.items.append(Leftover(self.tool, kind, str(path), note))


def _default_app_dirs(home: Path) -> List[Path]:
    return [Path("/Applications"), home / "Applications"]


class _AppFinder:
    """Finds installed apps in the Applications folders and, optionally, with Spotlight.

    Spotlight matters because apps such as VS Code often run from wherever they were
    unzipped; missing one would mark the data of an app in use as left over.
    """

    def __init__(self, app_dirs: Sequence[Path], use_spotlight: bool) -> None:
        self.app_dirs = list(app_dirs)
        self.use_spotlight = use_spotlight
        self._spotlight_cache: Dict[str, List[Path]] = {}

    def find(self, pattern: str) -> List[Path]:
        """App bundles matching a glob pattern such as "Android Studio*.app"."""
        found = set()
        for directory in self.app_dirs:
            try:
                found.update(directory.glob(pattern))
            except OSError:
                continue
        if self.use_spotlight:
            name = Path(pattern).name
            if name not in self._spotlight_cache:
                self._spotlight_cache[name] = _spotlight_apps(name)
            found.update(self._spotlight_cache[name])
        return sorted(found)


def _spotlight_apps(name_pattern: str) -> List[Path]:
    """App bundles Spotlight knows with this file name (* allowed), except ones in a Trash."""
    query = (
        'kMDItemContentType == "com.apple.application-bundle" '
        f'&& kMDItemFSName == "{name_pattern}"'
    )
    try:
        completed = subprocess.run(
            ["/usr/bin/mdfind", query], capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return []
    apps = []
    for line in completed.stdout.splitlines():
        path = Path(line)
        if line.startswith("/") and not {".Trash", ".Trashes"} & set(path.parts) and path.is_dir():
            apps.append(path)
    return apps


def _is_missing(path: str) -> bool:
    """True only when path certainly doesn't exist, not when macOS denies access to it."""
    try:
        os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return True
    except OSError:
        return False
    return False


def _list_dirs(base: Path) -> List[Path]:
    """Sub-folders of base (not following symbolic links), sorted by name."""
    try:
        with os.scandir(base) as it:
            return sorted(
                Path(entry.path) for entry in it if entry.is_dir(follow_symlinks=False)
            )
    except OSError:
        return []


def _glob(base: Path, pattern: str) -> List[Path]:
    try:
        return sorted(base.glob(pattern))
    except OSError:
        return []


def _version_key(text: str) -> Tuple[Tuple[int, ...], int]:
    """Sort key for versions such as 8.5, 8.10.2 or 8.11-rc-1 (a pre-release sorts first)."""
    number, _, suffix = text.partition("-")
    parts = tuple(int(part) for part in re.findall(r"\d+", number))
    return parts, 0 if suffix else 1


def _without_nested(items: List[Leftover]) -> List[Leftover]:
    """Drop duplicates and items inside another item, so no space is counted twice."""
    kept: Dict[str, Leftover] = {}
    for item in sorted(items, key=lambda i: len(i.path)):
        path = Path(item.path)
        if item.path in kept or any(str(parent) in kept for parent in path.parents):
            continue
        kept[item.path] = item
    return list(kept.values())


# Caches that Electron apps such as VS Code and Unity Hub keep in Application Support.
_ELECTRON_CACHES = {
    "Cache": "Web content cache",
    "CachedData": "Compiled code cache",
    "CachedExtensionVSIXs": "Downloaded extension installers",
    "CachedProfilesData": "Profile cache",
    "Code Cache": "Compiled script cache",
    "DawnCache": "Graphics shader cache",
    "DawnGraphiteCache": "Graphics shader cache",
    "DawnWebGPUCache": "Graphics shader cache",
    "GPUCache": "Graphics shader cache",
    "Service Worker/CacheStorage": "Service worker cache",
    "Service Worker/ScriptCache": "Service worker script cache",
}


def _electron_caches(out: _Collector, base: Path, app_label: str) -> None:
    for name, description in _ELECTRON_CACHES.items():
        out.add(base / name, CACHE, f"{description} for {app_label}. It is rebuilt when needed.")
    out.add(base / "logs", LOGS, f"Logs written by {app_label}.")


def _not_found_note(label: str) -> str:
    return f"{label} was not found in /Applications, ~/Applications or by Spotlight."


# --- Android Studio --------------------------------------------------------------------

# AndroidStudio2024.2, AndroidStudioPreview2024.3, AndroidStudio4.0, ...
_ANDROID_STUDIO_DIR = re.compile(r"^AndroidStudio(Preview)?(\d+(?:\.\d+)*)$")


def _android_studio(home: Path, apps: _AppFinder) -> List[Leftover]:
    out = _Collector(ANDROID_STUDIO)
    lib = home / "Library"
    bundles = apps.find("Android Studio*.app")
    preview_installed = any(app.name.startswith("Android Studio Preview") for app in bundles)
    stable_installed = any(not app.name.startswith("Android Studio Preview") for app in bundles)
    installed = stable_installed or preview_installed

    # Android Studio 4.1 and later keep one folder per version in each of these places.
    roles = (
        (lib / "Application Support" / "Google", "Settings and plugins"),
        (lib / "Caches" / "Google", "Caches"),
        (lib / "Logs" / "Google", "Logs"),
    )
    found = []
    newest: Dict[bool, Tuple[int, ...]] = {}
    for base, role in roles:
        for folder in _list_dirs(base):
            match = _ANDROID_STUDIO_DIR.match(folder.name)
            if not match:
                continue
            is_preview = bool(match.group(1))
            version = tuple(int(part) for part in match.group(2).split("."))
            found.append((folder, role, is_preview, version, match.group(2)))
            newest[is_preview] = max(newest.get(is_preview, version), version)

    for folder, role, is_preview, version, label in found:
        name = f"Android Studio {'Preview ' if is_preview else ''}{label}"
        channel_installed = preview_installed if is_preview else stable_installed
        if not channel_installed:
            app = "Android Studio Preview" if is_preview else "Android Studio"
            out.add(folder, NOT_INSTALLED, f"{role} for {name}. {_not_found_note(app)}")
        elif version < newest[is_preview]:
            out.add(folder, OLD_VERSION, f"{role} for {name}. A newer version keeps its own copy.")
        elif role == "Caches":
            out.add(
                folder,
                CACHE,
                f"Caches for {name}. They are rebuilt, but the next launch takes longer.",
            )
        elif role == "Logs":
            out.add(folder, LOGS, f"Logs for {name}.")
        else:
            out.add(folder, IN_USE, f"Settings and plugins for {name}, the version you use now.")

    # Android Studio 4.0 and earlier used different places.
    for base in (lib / "Preferences", lib / "Caches", lib / "Application Support", lib / "Logs"):
        for folder in _list_dirs(base):
            if _ANDROID_STUDIO_DIR.match(folder.name):
                out.add(folder, OLD_VERSION, "Data from Android Studio 4.0 or earlier.")
    for folder in _list_dirs(home):
        if re.match(r"^\.AndroidStudio(Preview)?\d", folder.name):
            out.add(folder, OLD_VERSION, "Data from Android Studio 3.x or earlier.")

    if installed:
        out.add(
            lib / "Android" / "sdk",
            IN_USE,
            "Android SDK: platforms, build tools and emulator images.",
        )
        out.add(home / ".android" / "avd", IN_USE, "Android emulator devices and their disk images.")
        out.add(home / ".android" / "cache", CACHE, "Android SDK download cache.")
    else:
        note = _not_found_note("Android Studio") + " Other tools, such as Flutter, may still use it."
        out.add(lib / "Android", NOT_INSTALLED, f"Android SDK and emulator images. {note}")
        out.add(
            home / ".android",
            NOT_INSTALLED,
            f"Emulator devices, debug signing key and settings. {note}",
        )
        out.add(
            lib / "Preferences" / "com.google.android.studio.plist",
            NOT_INSTALLED,
            f"Android Studio preferences. {_not_found_note('Android Studio')}",
        )
        out.add(
            lib / "Saved Application State" / "com.google.android.studio.savedState",
            NOT_INSTALLED,
            f"Android Studio window positions. {_not_found_note('Android Studio')}",
        )
    return out.items


# --- Visual Studio Code ----------------------------------------------------------------

# (label, app bundle, Application Support folder, folder in home, bundle identifier)
_VS_CODE_VARIANTS = (
    ("Visual Studio Code", "Visual Studio Code.app", "Code", ".vscode", "com.microsoft.VSCode"),
    (
        "VS Code Insiders",
        "Visual Studio Code - Insiders.app",
        "Code - Insiders",
        ".vscode-insiders",
        "com.microsoft.VSCodeInsiders",
    ),
)


def _vs_code(home: Path, apps: _AppFinder) -> List[Leftover]:
    out = _Collector(VS_CODE)
    lib = home / "Library"
    for label, app, support_name, home_folder, bundle_id in _VS_CODE_VARIANTS:
        support = lib / "Application Support" / support_name
        caches = lib / "Caches" / bundle_id
        updates = lib / "Caches" / f"{bundle_id}.ShipIt"
        if not apps.find(app):
            note = _not_found_note(label)
            out.add(support, NOT_INSTALLED, f"Settings, extension data and caches. {note}")
            out.add(home / home_folder, NOT_INSTALLED, f"Installed extensions. {note}")
            out.add(caches, NOT_INSTALLED, f"Caches. {note}")
            out.add(updates, NOT_INSTALLED, f"Downloaded updates. {note}")
            out.add(lib / "Preferences" / f"{bundle_id}.plist", NOT_INSTALLED, f"Preferences. {note}")
            out.add(
                lib / "Saved Application State" / f"{bundle_id}.savedState",
                NOT_INSTALLED,
                f"Window positions. {note}",
            )
            continue
        _electron_caches(out, support, label)
        out.add(caches, CACHE, f"Cache for {label}. It is rebuilt when needed.")
        out.add(updates, CACHE, f"Updates {label} downloaded.")
        out.add(home / home_folder / "extensions", IN_USE, f"Extensions installed in {label}.")
        for folder, project in _orphaned_workspaces(support / "User" / "workspaceStorage"):
            out.add(folder, ORPHANED, f"{label} data for {project}, which no longer exists.")
    return out.items


def _orphaned_workspaces(storage: Path) -> Iterator[Tuple[Path, str]]:
    """Workspace storage folders whose project folder or workspace file is gone."""
    for folder in _list_dirs(storage):
        try:
            data = json.loads((folder / "workspace.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        uri = data.get("folder") or data.get("workspace")
        if not isinstance(uri, str):
            continue
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            continue  # Remote, container and virtual workspaces can't be checked here.
        project = unquote(parsed.path)
        if not project or not _is_missing(project):
            continue  # Still there, or macOS privacy settings don't let us check.
        parts = Path(project).parts
        if len(parts) > 2 and parts[1] == "Volumes" and _is_missing(os.path.join(*parts[:3])):
            continue  # On a disk that isn't connected right now.
        yield folder, project


# --- Gradle ----------------------------------------------------------------------------

_GRADLE_VERSION_DIR = re.compile(r"^\d+(?:\.\d+)+(?:-[\w.-]+)?$")  # 8.5, 8.10.2, 8.11-rc-1
_GRADLE_DIST = re.compile(r"^gradle-(\d+(?:\.\d+)+(?:-[\w.-]+?)?)-(?:bin|all)$")
_NUMBERED_CACHE = re.compile(r"^(.+)-(\d+)$")  # transforms-4, jars-9, modules-2, ...
_GRADLE_CACHE_NAMES = {
    "build-cache": "Local build cache",
    "jars": "Compiled build scripts",
    "journal": "Cache bookkeeping",
    "modules": "Downloaded dependencies",
    "transforms": "Transformed dependencies",
}


def _gradle(gradle_home: Path) -> List[Leftover]:
    out = _Collector(GRADLE)
    caches = gradle_home / "caches"
    cache_dirs = _list_dirs(caches)

    version_dirs = [d for d in cache_dirs if _GRADLE_VERSION_DIR.match(d.name)]
    newest = max(version_dirs, key=lambda d: _version_key(d.name), default=None)
    for folder in version_dirs:
        if folder == newest:
            out.add(folder, CACHE, f"Build caches for Gradle {folder.name}, the newest version here.")
        else:
            out.add(
                folder,
                OLD_VERSION,
                f"Build caches for Gradle {folder.name}. Re-created if a project still uses it.",
            )

    # Shared caches are numbered by format. A lower number is used only by older Gradle versions.
    numbered: Dict[str, List[Tuple[int, Path]]] = {}
    for folder in cache_dirs:
        if folder in version_dirs:
            continue
        match = _NUMBERED_CACHE.match(folder.name)
        if match:
            numbered.setdefault(match.group(1), []).append((int(match.group(2)), folder))
        else:
            out.add(folder, CACHE, "Shared Gradle cache. Gradle rebuilds it when needed.")
    for prefix, entries in sorted(numbered.items()):
        description = _GRADLE_CACHE_NAMES.get(prefix, "Shared Gradle cache")
        top = max(number for number, _ in entries)
        for number, folder in sorted(entries):
            if number == top:
                out.add(folder, CACHE, f"{description}. Gradle downloads or rebuilds them when needed.")
            else:
                out.add(
                    folder,
                    OLD_VERSION,
                    f"{description} in an older format, used only by older Gradle versions.",
                )

    dists = []
    for folder in _list_dirs(gradle_home / "wrapper" / "dists"):
        match = _GRADLE_DIST.match(folder.name)
        if match:
            dists.append((_version_key(match.group(1)), match.group(1), folder))
    newest_dist = max((key for key, _, _ in dists), default=None)
    for key, version, folder in sorted(dists):
        if key == newest_dist:
            out.add(folder, IN_USE, f"Gradle {version}, the newest version a project downloaded.")
        else:
            out.add(
                folder,
                OLD_VERSION,
                f"Gradle {version}, downloaded by a project. Downloaded again if a project needs it.",
            )

    daemons = [d for d in _list_dirs(gradle_home / "daemon") if _GRADLE_VERSION_DIR.match(d.name)]
    newest_daemon = max(daemons, key=lambda d: _version_key(d.name), default=None)
    for folder in daemons:
        kind = LOGS if folder == newest_daemon else OLD_VERSION
        out.add(folder, kind, f"Logs and state from the Gradle {folder.name} background process.")

    out.add(gradle_home / "jdks", CACHE, "JDKs Gradle downloaded for toolchains. Downloaded again if needed.")
    out.add(gradle_home / "native", CACHE, "Native libraries Gradle unpacked. Re-created when needed.")
    out.add(gradle_home / "build-scan-data", CACHE, "Data kept for Gradle build scans.")
    out.add(gradle_home / ".tmp", CACHE, "Temporary files from Gradle builds.")
    return out.items


# --- Unity -----------------------------------------------------------------------------


def _unity(home: Path, apps: _AppFinder) -> List[Leftover]:
    out = _Collector(UNITY)
    lib = home / "Library"
    hub_installed = bool(apps.find("Unity Hub.app"))
    editor_installed = any(
        apps.find(pattern)
        for pattern in ("Unity/Hub/Editor/*/Unity.app", "Unity/Unity.app", "Unity*/Unity.app")
    )
    installed = hub_installed or editor_installed
    note = _not_found_note("Unity")

    if installed:
        out.add(
            lib / "Unity" / "cache",
            CACHE,
            "Unity Package Manager cache. Packages download again when a project needs them.",
        )
        out.add(
            lib / "Unity" / "Asset Store-5.x",
            CACHE,
            "Asset Store packages you downloaded. You can download them again in Unity.",
        )
        out.add(lib / "Logs" / "Unity", LOGS, "Unity Editor logs.")
    else:
        out.add(lib / "Unity", NOT_INSTALLED, f"Package cache, Asset Store downloads and licenses. {note}")
        out.add(lib / "Logs" / "Unity", NOT_INSTALLED, f"Unity Editor logs. {note}")
        out.add(lib / "Application Support" / "Unity", NOT_INSTALLED, f"Unity Editor data. {note}")
        for plist in _glob(lib / "Preferences", "com.unity3d.*.plist"):
            out.add(plist, NOT_INSTALLED, f"Unity preferences. {note}")
    for folder in _glob(lib / "Caches", "com.unity3d.*"):
        out.add(folder, CACHE if installed else NOT_INSTALLED, "Unity cache." + ("" if installed else f" {note}"))

    hub_data = lib / "Application Support" / "UnityHub"
    if hub_installed:
        _electron_caches(out, hub_data, "Unity Hub")
    else:
        out.add(hub_data, NOT_INSTALLED, f"Unity Hub settings and caches. {_not_found_note('Unity Hub')}")
    return out.items


# --- Build output inside projects ------------------------------------------------------

_GRADLE_BUILD_FILES = {"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}
_GRADLE_OUTPUT = {
    "build": (GRADLE, "Gradle build output. Re-created by the next build."),
    ".gradle": (GRADLE, "Gradle's cache for this project. Re-created by the next build."),
    ".kotlin": (GRADLE, "Kotlin compiler data for this project. Re-created by the next build."),
    ".cxx": (ANDROID_STUDIO, "Native (C/C++) build files. Re-created by the next build."),
}
# Keyed by lower-case name, because Unity projects use both Obj and obj.
_UNITY_OUTPUT = {
    "library": "Imported assets. Unity rebuilds them when the project next opens, which can take a while.",
    "temp": "Temporary files. Close the project in Unity before removing them.",
    "obj": "Compiled script files. Re-created by the next build.",
    "logs": "Logs for this project.",
}
_VS_CODE_TEST = ".vscode-test"
_SKIP_DIRS = {".git", ".hg", ".svn", ".Trash", "node_modules"}


def scan_projects(
    root: str,
    tools: Iterable[str],
    progress: Optional[ProgressCallback] = None,
    cancel: Optional[threading.Event] = None,
) -> List[Leftover]:
    """Find build folders of Gradle (including Android), Unity and VS Code extension projects."""
    tools = set(tools)
    progress = progress or _no_progress
    found: List[Leftover] = []
    stack = [root]
    checked = 0
    while stack:
        check_cancelled(cancel)
        directory = stack.pop()
        try:
            with os.scandir(directory) as it:
                entries = list(it)
        except OSError:
            continue
        checked += 1
        if checked % 200 == 0:
            progress(f"Looking for projects… {checked:,} folders checked", 0, 0)

        subdirs = {}
        files = set()
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    subdirs[entry.name] = entry
                else:
                    files.add(entry.name)
            except OSError:
                continue

        if "Assets" in subdirs and "ProjectSettings" in subdirs:
            if UNITY in tools:
                for name, entry in sorted(subdirs.items()):
                    note = _UNITY_OUTPUT.get(name.lower())
                    if note:
                        found.append(Leftover(UNITY, BUILD_OUTPUT, entry.path, note))
            continue  # Nothing else to find inside a Unity project.

        handled = set()
        if files & _GRADLE_BUILD_FILES:
            for name, (tool, note) in _GRADLE_OUTPUT.items():
                if name in subdirs:
                    handled.add(name)
                    if tool in tools:
                        found.append(Leftover(tool, BUILD_OUTPUT, subdirs[name].path, note))
        if _VS_CODE_TEST in subdirs and VS_CODE in tools:
            found.append(
                Leftover(
                    VS_CODE,
                    BUILD_OUTPUT,
                    subdirs[_VS_CODE_TEST].path,
                    "Copies of VS Code downloaded to test an extension. Downloaded again when needed.",
                )
            )

        for name, entry in subdirs.items():
            if name in handled or name in _SKIP_DIRS or is_package_name(name):
                continue
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if is_hidden(name, st):
                continue
            stack.append(entry.path)
    return found
