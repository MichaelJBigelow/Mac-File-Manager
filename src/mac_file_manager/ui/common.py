"""Widgets and helpers shared by the tabs."""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Optional, Sequence, Tuple

from ..fsutils import ScanCancelled, TrashResult, format_size, move_to_trash

# The most items "Reveal in Finder" opens at once, so a large selection doesn't flood Finder.
MAX_REVEAL = 10


class BackgroundTask:
    """Run work(progress, cancel) on a worker thread and report back on the Tk thread.

    Exactly one of on_done(result), on_error(exception) or on_cancelled() is called.
    """

    POLL_MS = 100

    def __init__(
        self,
        widget: tk.Misc,
        work: Callable[[Callable[[str, int, int], None], threading.Event], Any],
        on_progress: Callable[[str, int, int], None],
        on_done: Callable[[Any], None],
        on_error: Callable[[BaseException], None],
        on_cancelled: Callable[[], None],
    ) -> None:
        self._widget = widget
        self._work = work
        self._on_progress = on_progress
        self._on_done = on_done
        self._on_error = on_error
        self._on_cancelled = on_cancelled
        self._queue: "queue.Queue[Tuple[str, Any]]" = queue.Queue()
        self.cancel_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()
        self._widget.after(self.POLL_MS, self._poll)

    def cancel(self) -> None:
        self.cancel_event.set()

    def _run(self) -> None:
        try:
            result = self._work(self._report_progress, self.cancel_event)
        except ScanCancelled:
            self._queue.put(("cancelled", None))
        except Exception as exc:  # Shown to the user by on_error.
            self._queue.put(("error", exc))
        else:
            self._queue.put(("done", result))

    def _report_progress(self, message: str, done: int, total: int) -> None:
        self._queue.put(("progress", (message, done, total)))

    def _poll(self) -> None:
        latest = None
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "progress":
                    latest = payload
                    continue
                if latest is not None:
                    self._on_progress(*latest)
                if kind == "done":
                    self._on_done(payload)
                elif kind == "error":
                    self._on_error(payload)
                else:
                    self._on_cancelled()
                return
        except queue.Empty:
            pass
        if latest is not None:
            self._on_progress(*latest)
        self._widget.after(self.POLL_MS, self._poll)


class FolderField(ttk.Frame):
    """A path entry with a Choose… button."""

    def __init__(self, master: tk.Misc, variable: tk.StringVar, prompt: str, clearable: bool = False):
        super().__init__(master)
        self.variable = variable
        self._prompt = prompt
        self.entry = ttk.Entry(self, textvariable=variable)
        self.entry.grid(row=0, column=0, sticky="ew")
        self.choose_button = ttk.Button(self, text="Choose…", command=self._choose)
        self.choose_button.grid(row=0, column=1, padx=(6, 0))
        if clearable:
            ttk.Button(self, text="Clear", command=lambda: variable.set("")).grid(
                row=0, column=2, padx=(6, 0)
            )
        self.columnconfigure(0, weight=1)

    def _choose(self) -> None:
        current = os.path.expanduser(self.variable.get().strip())
        initial = current if os.path.isdir(current) else os.path.expanduser("~")
        chosen = filedialog.askdirectory(
            parent=self, initialdir=initial, title=self._prompt, mustexist=True
        )
        if chosen:
            self.variable.set(chosen)


class ProgressRow(ttk.Frame):
    """A progress bar with a status line."""

    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self.bar = ttk.Progressbar(self, mode="determinate", length=220)
        self.bar.grid(row=0, column=0, sticky="w")
        self.status = ttk.Label(self, text="", anchor="w")
        self.status.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self.columnconfigure(1, weight=1)

    def busy(self, message: str, done: int = 0, total: int = 0) -> None:
        if total > 0:
            if str(self.bar.cget("mode")) != "determinate":
                self.bar.stop()
                self.bar.configure(mode="determinate")
            self.bar.configure(maximum=total, value=done)
        elif str(self.bar.cget("mode")) != "indeterminate":
            self.bar.configure(mode="indeterminate")
            self.bar.start(15)
        self.status.configure(text=message)

    def idle(self, message: str) -> None:
        self.bar.stop()
        self.bar.configure(mode="determinate", value=0)
        self.status.configure(text=message)


def scrolled_tree(master: tk.Misc, columns: Sequence[str], **options: Any) -> Tuple[ttk.Frame, ttk.Treeview]:
    frame = ttk.Frame(master)
    tree = ttk.Treeview(frame, columns=tuple(columns), **options)
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    tree.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return frame, tree


def confirm_trash(parent: tk.Misc, count: int, total_size: int, warning: str = "") -> bool:
    noun = "item" if count == 1 else "items"
    message = (
        f"Move {count:,} {noun} ({format_size(total_size)}) to the Trash?\n\n"
        "You can put them back from the Trash until you empty it."
    )
    if warning:
        message = f"{warning}\n\n{message}"
    return messagebox.askyesno(
        "Move to Trash", message, icon=messagebox.WARNING, default=messagebox.NO, parent=parent
    )


def trash_with_feedback(parent: tk.Misc, paths: Sequence[str]) -> TrashResult:
    """Move paths to the Trash and tell the user about any that could not be moved."""
    parent.configure(cursor="watch")
    parent.update_idletasks()
    try:
        result = move_to_trash(paths)
    finally:
        parent.configure(cursor="")
    if result.failed:
        shown = "\n".join(result.failed[:10])
        more = f"\n…and {len(result.failed) - 10:,} more" if len(result.failed) > 10 else ""
        details = f"\n\n{result.details[:1500]}" if result.details else ""
        messagebox.showerror(
            "Move to Trash",
            f"{len(result.failed):,} of {len(paths):,} items could not be moved to the Trash:\n\n"
            f"{shown}{more}{details}",
            parent=parent,
        )
    return result


def show_error(parent: tk.Misc, title: str, message: str) -> None:
    messagebox.showerror(title, message, parent=parent)
