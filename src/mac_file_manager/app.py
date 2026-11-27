"""The main window."""

from __future__ import annotations

import sys
import tkinter as tk
import traceback
from tkinter import messagebox, ttk

from . import APP_NAME, __version__
from .ui.duplicates_tab import DuplicatesTab
from .ui.leftovers_tab import LeftoversTab


class MainWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(APP_NAME)
        root.geometry("1040x700")
        root.minsize(820, 520)

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        self.duplicates_tab = DuplicatesTab(notebook)
        self.leftovers_tab = LeftoversTab(notebook)
        notebook.add(self.duplicates_tab, text="Duplicate Files")
        notebook.add(self.leftovers_tab, text="Developer Leftovers")

        root.report_callback_exception = self._report_error
        if root.tk.call("tk", "windowingsystem") == "aqua":
            root.createcommand("tkAboutDialog", self._show_about)

    def _show_about(self) -> None:
        messagebox.showinfo(
            f"About {APP_NAME}",
            f"{APP_NAME} {__version__}\n\nFinds duplicate files and data that developer tools leave behind.",
            parent=self.root,
        )

    def _report_error(self, exc_type, exc_value, exc_traceback) -> None:
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)
        messagebox.showerror(APP_NAME, f"Something went wrong:\n\n{exc_value}", parent=self.root)


def bring_to_front(root: tk.Tk) -> None:
    """Show the window above other apps' windows when the app starts."""
    root.lift()
    root.attributes("-topmost", True)
    root.after(300, lambda: root.attributes("-topmost", False))
    root.focus_force()


def main() -> None:
    root = tk.Tk()
    MainWindow(root)
    bring_to_front(root)
    root.mainloop()
