import json
import os
import tempfile
import subprocess
import threading
import unittest
from pathlib import Path
from unittest import mock

from mac_file_manager import leftovers
from mac_file_manager.fsutils import ScanCancelled
from mac_file_manager.leftovers import (
    ANDROID_STUDIO,
    BUILD_OUTPUT,
    CACHE,
    GRADLE,
    IN_USE,
    LOGS,
    NOT_INSTALLED,
    OLD_VERSION,
    ORPHANED,
    TOOLS,
    UNITY,
    VS_CODE,
    find_leftovers,
    scan_projects,
)


def make(path: Path, size: int = 10) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "data").write_bytes(b"x" * size)
    return path


class LeftoversTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name).resolve()
        self.home = base / "home"
        self.apps = base / "Applications"
        self.home.mkdir()
        self.apps.mkdir()
        self.lib = self.home / "Library"

    def tearDown(self):
        self._tmp.cleanup()

    def install(self, relative: str) -> None:
        (self.apps / relative).mkdir(parents=True)

    def scan(self, tools=TOOLS, project_root=None):
        items = find_leftovers(
            tools,
            home=str(self.home),
            project_root=project_root,
            app_dirs=[str(self.apps)],
            use_spotlight=False,
        )
        return {os.path.relpath(item.path, self.home): item for item in items}

    def kinds(self, items):
        return {path: item.kind for path, item in items.items()}


class AndroidStudioTest(LeftoversTestCase):
    def setUp(self):
        super().setUp()
        google = self.lib / "Caches" / "Google"
        make(google / "AndroidStudio2023.1")
        make(google / "AndroidStudio2024.2")
        make(google / "AndroidStudioPreview2024.3")
        make(google / "Chrome")  # Not Android Studio.
        make(self.lib / "Application Support" / "Google" / "AndroidStudio2024.2")
        make(self.lib / "Logs" / "Google" / "AndroidStudio2024.2")
        make(self.lib / "Preferences" / "AndroidStudio3.6")
        make(self.home / ".AndroidStudio3.1")
        make(self.lib / "Android" / "sdk", size=1000)
        make(self.home / ".android" / "avd")
        make(self.home / ".android" / "cache")

    def test_installed(self):
        self.install("Android Studio.app")
        kinds = self.kinds(self.scan([ANDROID_STUDIO]))
        self.assertEqual(
            kinds,
            {
                "Library/Caches/Google/AndroidStudio2023.1": OLD_VERSION,
                "Library/Caches/Google/AndroidStudio2024.2": CACHE,
                "Library/Caches/Google/AndroidStudioPreview2024.3": NOT_INSTALLED,
                "Library/Application Support/Google/AndroidStudio2024.2": IN_USE,
                "Library/Logs/Google/AndroidStudio2024.2": LOGS,
                "Library/Preferences/AndroidStudio3.6": OLD_VERSION,
                ".AndroidStudio3.1": OLD_VERSION,
                "Library/Android/sdk": IN_USE,
                ".android/avd": IN_USE,
                ".android/cache": CACHE,
            },
        )

    def test_not_installed(self):
        items = self.scan([ANDROID_STUDIO])
        kinds = self.kinds(items)
        self.assertEqual(kinds["Library/Caches/Google/AndroidStudio2024.2"], NOT_INSTALLED)
        self.assertEqual(kinds["Library/Android"], NOT_INSTALLED)
        self.assertEqual(kinds[".android"], NOT_INSTALLED)
        self.assertNotIn(".android/avd", kinds)  # Covered by .android.
        self.assertGreaterEqual(items["Library/Android"].size, 1000)


class VSCodeTest(LeftoversTestCase):
    def setUp(self):
        super().setUp()
        self.support = self.lib / "Application Support" / "Code"
        make(self.support / "CachedData")
        make(self.support / "logs")
        make(self.support / "User" / "settings")
        make(self.home / ".vscode" / "extensions")
        existing = make(self.home / "projects" / "my app")
        storage = self.support / "User" / "workspaceStorage"
        for name, folder in (("alive", existing), ("gone", self.home / "projects" / "old app")):
            make(storage / name)
            (storage / name / "workspace.json").write_text(json.dumps({"folder": Path(folder).as_uri()}))
        make(storage / "remote")
        (storage / "remote" / "workspace.json").write_text(json.dumps({"folder": "vscode-remote://ssh/x"}))
        make(storage / "broken")
        (storage / "broken" / "workspace.json").write_text("not json")

    def test_installed(self):
        self.install("Visual Studio Code.app")
        items = self.scan([VS_CODE])
        self.assertEqual(
            self.kinds(items),
            {
                "Library/Application Support/Code/CachedData": CACHE,
                "Library/Application Support/Code/logs": LOGS,
                "Library/Application Support/Code/User/workspaceStorage/gone": ORPHANED,
                ".vscode/extensions": IN_USE,
            },
        )
        self.assertIn("old app", items["Library/Application Support/Code/User/workspaceStorage/gone"].note)

    def test_not_installed(self):
        kinds = self.kinds(self.scan([VS_CODE]))
        self.assertEqual(
            kinds,
            {"Library/Application Support/Code": NOT_INSTALLED, ".vscode": NOT_INSTALLED},
        )

    def test_installed_outside_applications_is_found_with_spotlight(self):
        unzipped = self.home / "Downloads" / "Visual Studio Code.app"
        unzipped.mkdir(parents=True)

        def spotlight(name):
            return [unzipped] if name == "Visual Studio Code.app" else []

        with mock.patch.object(leftovers, "_spotlight_apps", side_effect=spotlight):
            items = find_leftovers(
                [VS_CODE], home=str(self.home), app_dirs=[str(self.apps)], use_spotlight=True
            )
        kinds = {os.path.relpath(item.path, self.home): item.kind for item in items}
        self.assertEqual(kinds["Library/Application Support/Code/CachedData"], CACHE)
        self.assertNotIn(NOT_INSTALLED, kinds.values())

    def test_project_that_cannot_be_checked_is_not_orphaned(self):
        locked = self.home / "locked"
        make(locked / "project")
        storage = self.support / "User" / "workspaceStorage"
        make(storage / "private")
        (storage / "private" / "workspace.json").write_text(
            json.dumps({"folder": (locked / "project").as_uri()})
        )
        self.install("Visual Studio Code.app")
        locked.chmod(0)  # Like a folder macOS privacy settings won't let the app read.
        try:
            if os.access(locked, os.X_OK):
                self.skipTest("Permissions are not enforced for this user")
            self.assertFalse(leftovers._is_missing(str(locked / "project")))
            self.assertTrue(leftovers._is_missing(str(self.home / "nope")))
            kinds = self.kinds(self.scan([VS_CODE]))
        finally:
            locked.chmod(0o755)
        self.assertNotIn("Library/Application Support/Code/User/workspaceStorage/private", kinds)
        self.assertIn("Library/Application Support/Code/User/workspaceStorage/gone", kinds)


class SpotlightTest(unittest.TestCase):
    def test_keeps_existing_apps_outside_the_trash(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "Tools" / "Visual Studio Code.app"
            trashed = Path(tmp) / ".Trash" / "Visual Studio Code.app"
            app.mkdir(parents=True)
            trashed.mkdir(parents=True)
            output = "\n".join([str(app), str(trashed), str(Path(tmp) / "Gone.app"), ""])
            with mock.patch.object(
                leftovers.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, output, ""),
            ) as run:
                self.assertEqual(leftovers._spotlight_apps("Visual Studio Code.app"), [app])
            query = run.call_args[0][0][1]
            self.assertIn('kMDItemFSName == "Visual Studio Code.app"', query)

    def test_spotlight_failure_means_no_apps(self):
        with mock.patch.object(
            leftovers.subprocess, "run", side_effect=subprocess.TimeoutExpired("mdfind", 15)
        ):
            self.assertEqual(leftovers._spotlight_apps("Unity Hub.app"), [])


class GradleTest(LeftoversTestCase):
    def test_versions(self):
        gradle = self.home / ".gradle"
        for name in ("7.6", "8.5", "8.10.2", "8.10.2-rc-1", "modules-2", "transforms-3", "transforms-4", "kotlin-dsl"):
            make(gradle / "caches" / name)
        make(gradle / "wrapper" / "dists" / "gradle-7.6-bin")
        make(gradle / "wrapper" / "dists" / "gradle-8.10.2-all")
        make(gradle / "daemon" / "7.6")
        make(gradle / "daemon" / "8.10.2")
        make(gradle / "jdks")
        make(gradle / "init.d")  # User configuration: never listed.
        kinds = self.kinds(self.scan([GRADLE]))
        self.assertEqual(
            kinds,
            {
                ".gradle/caches/7.6": OLD_VERSION,
                ".gradle/caches/8.5": OLD_VERSION,
                ".gradle/caches/8.10.2-rc-1": OLD_VERSION,
                ".gradle/caches/8.10.2": CACHE,
                ".gradle/caches/modules-2": CACHE,
                ".gradle/caches/transforms-3": OLD_VERSION,
                ".gradle/caches/transforms-4": CACHE,
                ".gradle/caches/kotlin-dsl": CACHE,
                ".gradle/wrapper/dists/gradle-7.6-bin": OLD_VERSION,
                ".gradle/wrapper/dists/gradle-8.10.2-all": IN_USE,
                ".gradle/daemon/7.6": OLD_VERSION,
                ".gradle/daemon/8.10.2": LOGS,
                ".gradle/jdks": CACHE,
            },
        )

    def test_no_gradle_folder(self):
        self.assertEqual(self.scan([GRADLE]), {})


class UnityTest(LeftoversTestCase):
    def setUp(self):
        super().setUp()
        make(self.lib / "Unity" / "cache")
        make(self.lib / "Unity" / "Licenses")
        make(self.lib / "Logs" / "Unity")
        make(self.lib / "Caches" / "com.unity3d.UnityEditor")
        make(self.lib / "Application Support" / "UnityHub" / "GPUCache")
        (self.lib / "Preferences").mkdir(parents=True)
        (self.lib / "Preferences" / "com.unity3d.UnityEditor5.x.plist").write_text("")

    def test_installed(self):
        self.install("Unity Hub.app")
        self.assertEqual(
            self.kinds(self.scan([UNITY])),
            {
                "Library/Unity/cache": CACHE,
                "Library/Logs/Unity": LOGS,
                "Library/Caches/com.unity3d.UnityEditor": CACHE,
                "Library/Application Support/UnityHub/GPUCache": CACHE,
            },
        )

    def test_editor_without_hub(self):
        self.install("Unity/Hub/Editor/2022.3.10f1/Unity.app")
        kinds = self.kinds(self.scan([UNITY]))
        self.assertEqual(kinds["Library/Unity/cache"], CACHE)
        self.assertEqual(kinds["Library/Application Support/UnityHub"], NOT_INSTALLED)

    def test_not_installed(self):
        kinds = self.kinds(self.scan([UNITY]))
        self.assertEqual(kinds["Library/Unity"], NOT_INSTALLED)
        self.assertEqual(kinds["Library/Preferences/com.unity3d.UnityEditor5.x.plist"], NOT_INSTALLED)
        self.assertNotIn("Library/Unity/cache", kinds)


class ProjectScanTest(LeftoversTestCase):
    def setUp(self):
        super().setUp()
        self.projects = self.home / "Projects"
        android = self.projects / "MyAndroidApp"
        make(android)
        (android / "settings.gradle.kts").write_text("")
        make(android / "build")
        make(android / ".gradle")
        make(android / "app" / "build" / "intermediates")
        make(android / "app" / ".cxx")
        (android / "app" / "build.gradle.kts").write_text("")
        make(android / "docs" / "build")  # No Gradle file next to it: not build output.
        game = self.projects / "Game"
        for name in ("Assets", "ProjectSettings", "Library", "Temp", "obj", "Packages"):
            make(game / name)
        extension = self.projects / "extension"
        make(extension / ".vscode-test")
        make(self.projects / "web" / "node_modules" / "pkg" / "build")
        (self.projects / "web" / "node_modules" / "pkg" / "build.gradle").write_text("")

    def test_finds_build_output(self):
        found = scan_projects(str(self.projects), TOOLS)
        kinds = {os.path.relpath(item.path, self.projects): (item.tool, item.kind) for item in found}
        self.assertEqual(
            kinds,
            {
                "MyAndroidApp/build": (GRADLE, BUILD_OUTPUT),
                "MyAndroidApp/.gradle": (GRADLE, BUILD_OUTPUT),
                "MyAndroidApp/app/build": (GRADLE, BUILD_OUTPUT),
                "MyAndroidApp/app/.cxx": (ANDROID_STUDIO, BUILD_OUTPUT),
                "Game/Library": (UNITY, BUILD_OUTPUT),
                "Game/Temp": (UNITY, BUILD_OUTPUT),
                "Game/obj": (UNITY, BUILD_OUTPUT),
                "extension/.vscode-test": (VS_CODE, BUILD_OUTPUT),
            },
        )

    def test_only_selected_tools(self):
        found = scan_projects(str(self.projects), [UNITY])
        self.assertEqual({item.tool for item in found}, {UNITY})

    def test_combined_with_home_scan_and_sizes(self):
        items = self.scan([GRADLE], project_root=str(self.projects))
        self.assertIn("Projects/MyAndroidApp/build", items)
        self.assertTrue(all(item.size > 0 for item in items.values()))

    def test_nested_items_are_dropped(self):
        # The projects folder is inside ~/.gradle here, so its items overlap the home scan.
        gradle_cache = make(self.home / ".gradle" / "caches" / "modules-2")
        (gradle_cache / "settings.gradle").write_text("")
        make(gradle_cache / "build")
        items = self.scan([GRADLE], project_root=str(gradle_cache))
        self.assertEqual(list(items), [".gradle/caches/modules-2"])

    def test_cancel(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(ScanCancelled):
            find_leftovers(
                TOOLS,
                home=str(self.home),
                project_root=str(self.projects),
                app_dirs=[str(self.apps)],
                cancel=cancel,
                use_spotlight=False,
            )


if __name__ == "__main__":
    unittest.main()
