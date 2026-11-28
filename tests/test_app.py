import time
import tkinter as tk
import unittest

from mac_file_manager.app import MIN_TK_VERSION, MainWindow
from mac_file_manager.duplicates import DuplicateGroup, DuplicateScanResult, FileEntry
from mac_file_manager.ui.theme import DARK, LIGHT, Theme


@unittest.skipIf(tk.TkVersion < MIN_TK_VERSION, f"The app needs Tk {MIN_TK_VERSION} or later")
class MainWindowTest(unittest.TestCase):
    def make_root(self) -> tk.Tk:
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"No display: {exc}")
        root.withdraw()
        self.addCleanup(root.destroy)
        return root

    def test_builds_both_tabs(self):
        root = self.make_root()
        window = MainWindow(root, Theme(root, dark=False))
        root.update_idletasks()
        self.assertEqual(window.tabs.titles(), ["Duplicate Files", "Developer Leftovers"])
        self.assertEqual(window.tabs.selected, 0)
        window.tabs.select(1)
        self.assertEqual(window.tabs.selected, 1)

    def test_light_and_dark_themes(self):
        for dark, palette in ((False, LIGHT), (True, DARK)):
            with self.subTest(dark=dark):
                root = self.make_root()
                theme = Theme(root, dark=dark)
                self.assertIs(theme.palette, palette)
                self.assertEqual(root.cget("background"), palette.surface)
                elements = theme.style.element_names()
                for element in ("Filled.Button.shape", "Danger.Button.shape", "Chip.shape", "Switch.indicator", "Field.shape", "Card.nw", "Card.se", "Snackbar.shape"):
                    self.assertIn(element, elements)
                self.assertEqual(theme.style.lookup("Title.Card.TLabel", "background"), palette.surface_container_low)

    def test_large_results_are_added_in_batches(self):
        root = self.make_root()
        window = MainWindow(root, Theme(root, dark=False))
        tab = window.duplicates_tab
        tab._root_folder = "/tmp/photos"
        count = tab.INSERT_BATCH * 2 + 10
        groups = [
            DuplicateGroup(10, [FileEntry(f"/tmp/photos/{g}/{i}.jpg", 10, 0.0) for i in range(2)])
            for g in range(count)
        ]
        tab._scan_finished(DuplicateScanResult(groups, files_scanned=count * 2))
        self.assertEqual(len(tab.tree.get_children()), tab.INSERT_BATCH)
        deadline = time.monotonic() + 10
        while tab._insert_job is not None and time.monotonic() < deadline:
            root.update()
        self.assertEqual(len(tab.tree.get_children()), count)
        self.assertIn(f"{count:,} sets", tab.summary.cget("text"))

        # Starting over (as a new search does) stops the batches still waiting.
        tab._scan_finished(DuplicateScanResult(groups, files_scanned=count * 2))
        tab._clear_results()
        root.update()
        self.assertEqual(tab.tree.get_children(), ())
        self.assertIsNone(tab._insert_job)

    def test_snackbar_shows_and_hides(self):
        root = self.make_root()
        window = MainWindow(root, Theme(root, dark=False))
        window.snackbar.show("Moved 1 item to the Trash.", duration_ms=10_000)
        root.update_idletasks()
        self.assertTrue(window.snackbar._frame.winfo_ismapped() or window.snackbar._frame.place_info())
        window.snackbar.hide()
        self.assertEqual(window.snackbar._frame.place_info(), {})


if __name__ == "__main__":
    unittest.main()
