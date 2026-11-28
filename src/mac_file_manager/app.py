"""The main window."""

from __future__ import annotations

import sys
import tkinter as tk
import traceback
from tkinter import messagebox, ttk
from typing import Optional

from . import APP_NAME, __version__
from .ui.common import Snackbar, TabBar
from .ui.duplicates_tab import DuplicatesTab
from .ui.images import app_icon
from .ui.leftovers_tab import LeftoversTab
from .ui.theme import Theme


class MainWindow:
    def __init__(self, root: tk.Tk, theme: Optional[Theme] = None) -> None:
        self.root = root
        root.title(APP_NAME)
        root.geometry("1100x800")
        root.minsize(900, 680)
        self.theme = theme or Theme(root)

        app_bar = ttk.Frame(root, padding=(28, 18, 28, 6))
        app_bar.grid(row=0, column=0, sticky="ew")
        self._icon = self.theme.image(app_icon(36))
        ttk.Label(app_bar, image=self._icon, style="Body.Surface.TLabel").grid(row=0, column=0, padx=(0, 12))
        ttk.Label(app_bar, text=APP_NAME, style="Headline.Surface.TLabel").grid(row=0, column=1, sticky="w")

        content = ttk.Frame(root)
        self.tabs = TabBar(root, content, self.theme)
        self.tabs.grid(row=1, column=0, sticky="ew", padx=16)
        content.grid(row=2, column=0, sticky="nsew")
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        self.snackbar = Snackbar(root)
        self.duplicates_tab = DuplicatesTab(content, self.theme, self.snackbar.show)
        self.leftovers_tab = LeftoversTab(content, self.theme, self.snackbar.show)
        self.tabs.add("Duplicate Files", self.duplicates_tab)
        self.tabs.add("Developer Leftovers", self.leftovers_tab)

        root.rowconfigure(2, weight=1)
        root.columnconfigure(0, weight=1)
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


# Tk 8.5, which comes with Apple's own Python, draws empty windows on current macOS and can't
# load the PNG images the theme is made of.
MIN_TK_VERSION = 8.6


def main() -> None:
    if tk.TkVersion < MIN_TK_VERSION:
        raise RuntimeError(
            f"{APP_NAME} needs Tk {MIN_TK_VERSION} or later, but this Python has Tk {tk.TkVersion}. "
            "Install Python from python.org, or run: brew install python-tk"
        )
    root = tk.Tk()
    MainWindow(root)
    bring_to_front(root)
    root.mainloop()
