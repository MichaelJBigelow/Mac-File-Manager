import os
import tempfile
import threading
import unittest
from pathlib import Path

from mac_file_manager.duplicates import PARTIAL_HASH_BYTES, DuplicateScanOptions, find_duplicates
from mac_file_manager.fsutils import ScanCancelled


def write(path: Path, data: bytes, mtime: float = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


class FindDuplicatesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        big = os.urandom(PARTIAL_HASH_BYTES * 3)
        write(self.root / "a.txt", b"hello", mtime=2_000_000)
        write(self.root / "sub" / "b.txt", b"hello", mtime=1_000_000)
        write(self.root / "c.txt", b"world")
        write(self.root / "empty1", b"")
        write(self.root / "empty2", b"")
        write(self.root / ".hidden.txt", b"hello")
        write(self.root / "Tool.app" / "Contents" / "e.txt", b"hello")
        write(self.root / "big1.bin", big)
        write(self.root / "deep" / "big2.bin", big)
        # Same size and same first block as big1, different ending: not a duplicate.
        write(self.root / "big3.bin", big[:-1] + bytes([(big[-1] + 1) % 256]))
        os.symlink(self.root / "a.txt", self.root / "link-to-a.txt")
        os.link(self.root / "c.txt", self.root / "hardlink-to-c.txt")

    def tearDown(self):
        self._tmp.cleanup()

    def groups(self, **options):
        result = find_duplicates(str(self.root), DuplicateScanOptions(**options))
        return [sorted(os.path.relpath(f.path, self.root) for f in g.files) for g in result.groups], result

    def test_finds_identical_files_only(self):
        groups, result = self.groups()
        self.assertEqual(sorted(groups), [["a.txt", "sub/b.txt"], ["big1.bin", "deep/big2.bin"]])
        self.assertEqual(result.files_scanned, 9)  # Links, hidden files and the app are skipped.

    def test_sorted_by_space_freed_and_oldest_first(self):
        result = find_duplicates(str(self.root))
        self.assertEqual(result.groups[0].size, PARTIAL_HASH_BYTES * 3)
        small = result.groups[1]
        self.assertEqual([Path(f.path).name for f in small.files], ["b.txt", "a.txt"])
        self.assertEqual(small.reclaimable, 5)
        self.assertEqual(result.reclaimable, PARTIAL_HASH_BYTES * 3 + 5)

    def test_include_hidden_and_packages(self):
        groups, _ = self.groups(include_hidden=True, include_packages=True)
        self.assertIn([".hidden.txt", "Tool.app/Contents/e.txt", "a.txt", "sub/b.txt"], groups)

    def test_minimum_size(self):
        groups, _ = self.groups(min_size=100)
        self.assertEqual(groups, [["big1.bin", "deep/big2.bin"]])

    def test_hard_links_are_not_duplicates(self):
        groups, _ = self.groups()
        self.assertFalse(any("c.txt" in group for group in groups))

    def test_cancel(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(ScanCancelled):
            find_duplicates(str(self.root), cancel=cancel)

    def test_missing_folder(self):
        with self.assertRaises(NotADirectoryError):
            find_duplicates(str(self.root / "missing"))

    def test_progress_is_reported(self):
        calls = []
        find_duplicates(str(self.root), progress=lambda *args: calls.append(args))
        self.assertTrue(calls)
        self.assertEqual(calls[-1][1], calls[-1][2])  # Finished: done == total.


if __name__ == "__main__":
    unittest.main()
