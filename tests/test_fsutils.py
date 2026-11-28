import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mac_file_manager import fsutils
from mac_file_manager.fsutils import display_path, format_size, is_hidden, is_package_name, path_size


class FormatSizeTest(unittest.TestCase):
    def test_values(self):
        self.assertEqual(format_size(0), "0 bytes")
        self.assertEqual(format_size(1), "1 byte")
        self.assertEqual(format_size(999), "999 bytes")
        self.assertEqual(format_size(1000), "1.0 KB")
        self.assertEqual(format_size(999_949), "999.9 KB")
        self.assertEqual(format_size(999_950), "1.0 MB")
        self.assertEqual(format_size(12_300_000_000), "12.3 GB")
        self.assertEqual(format_size(2 * 10**15), "2.0 PB")


class NamesTest(unittest.TestCase):
    def test_packages(self):
        self.assertTrue(is_package_name("Xcode.app"))
        self.assertTrue(is_package_name("Photos Library.photoslibrary"))
        self.assertTrue(is_package_name("App.dSYM"))
        self.assertFalse(is_package_name("Documents"))

    def test_hidden(self):
        self.assertTrue(is_hidden(".git"))
        self.assertFalse(is_hidden("Documents"))
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Library"
            folder.mkdir()
            self.assertFalse(is_hidden(folder.name, os.lstat(folder)))
            os.chflags(folder, stat.UF_HIDDEN)  # How macOS hides ~/Library.
            self.assertTrue(is_hidden(folder.name, os.lstat(folder)))

    def test_display_path(self):
        self.assertEqual(display_path("/Users/me/Library", "/Users/me"), "~/Library")
        self.assertEqual(display_path("/Users/me", "/Users/me"), "~")
        self.assertEqual(display_path("/Users/meow", "/Users/me"), "/Users/meow")


class PathSizeTest(unittest.TestCase):
    def test_counts_files_once_and_skips_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sub").mkdir()
            (root / "a").write_bytes(b"x" * 100)
            (root / "sub" / "b").write_bytes(b"y" * 50)
            os.link(root / "a", root / "sub" / "a-again")
            os.symlink(root / "sub", root / "link")
            size = path_size(str(root))
            self.assertGreaterEqual(size, 150)
            self.assertLess(size, 150 + 200)  # The symlink adds only its own few bytes.
            self.assertEqual(path_size(str(root / "a")), 100)
            self.assertEqual(path_size(str(root / "missing")), 0)


class MoveToTrashTest(unittest.TestCase):
    def test_reports_moved_and_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            gone = os.path.join(tmp, "gone")
            stays = os.path.join(tmp, "stays")
            Path(stays).write_text("x")

            def fake_run(command, **kwargs):
                self.assertEqual(command[0], fsutils.TRASH_COMMAND)
                self.assertEqual(command[1:], [gone, stays])
                return subprocess.CompletedProcess(command, 1, "", "could not move stays")

            with mock.patch.object(fsutils.os, "access", return_value=True), mock.patch.object(
                fsutils.subprocess, "run", side_effect=fake_run
            ):
                result = fsutils.move_to_trash([gone, stays, gone])
            self.assertEqual(result.moved, [gone])
            self.assertEqual(result.failed, [stays])
            self.assertIn("could not move stays", result.details)

    def test_uses_finder_without_trash_command_and_batches(self):
        paths = [f"/nonexistent/{i}" for i in range(fsutils._TRASH_BATCH_SIZE + 5)]
        commands = []

        def fake_run(command, **kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        with mock.patch.object(fsutils.os, "access", return_value=False), mock.patch.object(
            fsutils.subprocess, "run", side_effect=fake_run
        ):
            result = fsutils.move_to_trash(paths)
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[0][:2], ["/usr/bin/osascript", "-e"])
        self.assertEqual(commands[0][3:] + commands[1][3:], paths)
        self.assertEqual(result.moved, paths)
        self.assertEqual(result.details, "")


if __name__ == "__main__":
    unittest.main()
