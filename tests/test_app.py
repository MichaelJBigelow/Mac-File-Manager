import tkinter as tk
import unittest

from mac_file_manager.app import MIN_TK_VERSION, MainWindow
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
                for element in ("Filled.Button.shape", "Danger.Button.shape", "Chip.shape", "Switch.indicator", "Field.shape", "Card.shape"):
                    self.assertIn(element, elements)
                self.assertEqual(theme.style.lookup("Title.Card.TLabel", "background"), palette.surface_container_low)

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
