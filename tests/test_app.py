import tkinter as tk
import unittest

from mac_file_manager.app import MainWindow


class MainWindowTest(unittest.TestCase):
    def test_builds_both_tabs(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"No display: {exc}")
        root.withdraw()
        try:
            window = MainWindow(root)
            root.update_idletasks()
            notebook = window.duplicates_tab.master
            self.assertEqual(
                [notebook.tab(tab, "text") for tab in notebook.tabs()],
                ["Duplicate Files", "Developer Leftovers"],
            )
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
