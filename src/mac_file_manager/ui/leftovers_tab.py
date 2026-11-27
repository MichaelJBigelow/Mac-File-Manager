"""The Developer Leftovers tab."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional

from ..fsutils import display_path, format_size, reveal_in_finder
from ..leftovers import IN_USE, NOT_INSTALLED, TOOLS, Leftover, find_leftovers
from .common import (
    MAX_REVEAL,
    BackgroundTask,
    FolderField,
    ProgressRow,
    confirm_trash,
    scrolled_tree,
    show_error,
    trash_with_feedback,
)

_COLUMNS = (
    ("tool", "Tool", 150, "w", False),
    ("kind", "Type", 130, "w", False),
    ("size", "Size", 90, "e", False),
    ("location", "Location", 480, "w", True),
)


class LeftoversTab(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=12)
        self.tool_vars = {tool: tk.BooleanVar(value=True) for tool in TOOLS}
        self.project_folder = tk.StringVar()
        self.show_in_use = tk.BooleanVar(value=False)
        self._task: Optional[BackgroundTask] = None
        self._results: List[Leftover] = []
        self._rows: Dict[str, Leftover] = {}  # Tree id -> item.
        self._sort_column = "size"
        self._sort_descending = True
        self._build()

    # --- Layout ----------------------------------------------------------------------

    def _build(self) -> None:
        ttk.Label(
            self,
            text=(
                "Finds caches, logs, old versions and build output that developer tools leave "
                "on your Mac."
            ),
        ).grid(row=0, column=0, sticky="w")

        tools = ttk.Frame(self)
        tools.grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Label(tools, text="Tools:").grid(row=0, column=0, padx=(0, 6))
        for column, tool in enumerate(TOOLS, start=1):
            ttk.Checkbutton(tools, text=tool, variable=self.tool_vars[tool]).grid(
                row=0, column=column, padx=(0, 14)
            )

        projects = ttk.Frame(self)
        projects.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(projects, text="Projects folder (optional):").grid(row=0, column=0, padx=(0, 6))
        FolderField(
            projects, self.project_folder, "Choose a folder that contains your projects", clearable=True
        ).grid(row=0, column=1, sticky="ew")
        projects.columnconfigure(1, weight=1)
        ttk.Label(
            self,
            text=(
                "Build folders are also listed for the Gradle, Android, Unity and VS Code "
                "extension projects found in this folder."
            ),
            foreground="gray",
        ).grid(row=3, column=0, sticky="w", pady=(2, 0))

        controls = ttk.Frame(self)
        controls.grid(row=4, column=0, sticky="ew", pady=(10, 6))
        self.scan_button = ttk.Button(controls, text="Find Leftovers", command=self._toggle_scan)
        self.scan_button.grid(row=0, column=0)
        ttk.Checkbutton(
            controls, text="Show items still in use", variable=self.show_in_use, command=self._render
        ).grid(row=0, column=1, padx=(12, 0))
        self.progress = ProgressRow(controls)
        self.progress.grid(row=0, column=2, sticky="ew", padx=(12, 0))
        controls.columnconfigure(2, weight=1)

        tree_frame, self.tree = scrolled_tree(
            self, [name for name, *_ in _COLUMNS], show="headings", selectmode="extended"
        )
        tree_frame.grid(row=5, column=0, sticky="nsew")
        for name, title, width, anchor, stretch in _COLUMNS:
            self.tree.heading(name, text=title, command=lambda n=name: self._sort_by(n))
            self.tree.column(name, width=width, anchor=anchor, stretch=stretch)
        self.tree.tag_configure("in_use", foreground="gray")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_note())
        self.tree.bind("<Double-1>", lambda _event: self._reveal())

        self.note = ttk.Label(self, text="", anchor="w", wraplength=900, justify="left")
        self.note.grid(row=6, column=0, sticky="ew", pady=(6, 0))
        self.bind("<Configure>", lambda event: self.note.configure(wraplength=max(300, event.width - 30)))

        actions = ttk.Frame(self)
        actions.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(actions, text="Reveal in Finder", command=self._reveal).grid(row=0, column=0)
        ttk.Button(actions, text="Move to Trash…", command=self._trash_selected).grid(
            row=0, column=1, padx=(6, 0)
        )
        self.summary = ttk.Label(actions, text="", anchor="e")
        self.summary.grid(row=0, column=2, sticky="e")
        actions.columnconfigure(2, weight=1)

        self.rowconfigure(5, weight=1)
        self.columnconfigure(0, weight=1)
        self.progress.idle("Click Find Leftovers to check your Mac.")

    # --- Scanning --------------------------------------------------------------------

    def _toggle_scan(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self.scan_button.configure(state="disabled")
            self.progress.busy("Stopping…")
            return

        tools = [tool for tool, var in self.tool_vars.items() if var.get()]
        if not tools:
            show_error(self, "Find Leftovers", "Choose at least one tool.")
            return
        typed = self.project_folder.get().strip()
        project_root = os.path.abspath(os.path.expanduser(typed)) if typed else None
        if project_root and not os.path.isdir(project_root):
            show_error(self, "Find Leftovers", "The projects folder doesn't exist. Choose another or clear it.")
            return

        self._results = []
        self._render()
        self.scan_button.configure(text="Cancel")
        self.progress.busy("Checking developer tool folders…")
        self._task = BackgroundTask(
            self,
            lambda progress, cancel: find_leftovers(
                tools, project_root=project_root, progress=progress, cancel=cancel
            ),
            on_progress=self.progress.busy,
            on_done=self._scan_finished,
            on_error=self._scan_failed,
            on_cancelled=lambda: self._scan_ended("Search cancelled."),
        )
        self._task.start()

    def _scan_ended(self, message: str) -> None:
        self._task = None
        self.scan_button.configure(text="Find Leftovers", state="normal")
        self.progress.idle(message)

    def _scan_failed(self, error: BaseException) -> None:
        self._scan_ended("The search stopped because of an error.")
        show_error(self, "Find Leftovers", str(error))

    def _scan_finished(self, results: List[Leftover]) -> None:
        self._results = results
        self._scan_ended("Done." if results else "Nothing found.")
        self._render()

    # --- Results ---------------------------------------------------------------------

    def _visible(self) -> List[Leftover]:
        show_in_use = self.show_in_use.get()
        return [item for item in self._results if show_in_use or item.kind != IN_USE]

    def _sort_by(self, column: str) -> None:
        if column == self._sort_column:
            self._sort_descending = not self._sort_descending
        else:
            self._sort_column = column
            self._sort_descending = column == "size"
        self._render()

    def _render(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._rows.clear()
        keys = {
            "tool": lambda item: (item.tool, item.path),
            "kind": lambda item: (item.kind, item.path),
            "size": lambda item: (item.size, item.path),
            "location": lambda item: item.path.lower(),
        }
        items = sorted(self._visible(), key=keys[self._sort_column], reverse=self._sort_descending)
        for item in items:
            row = self.tree.insert(
                "",
                "end",
                values=(item.tool, item.kind, format_size(item.size), display_path(item.path)),
                tags=("in_use",) if item.kind == IN_USE else (),
            )
            self._rows[row] = item
        self._show_note()
        self._update_summary()

    def _update_summary(self) -> None:
        visible = self._visible()
        hidden = len(self._results) - len(visible)
        if not self._results:
            self.summary.configure(text="")
            return
        noun = "item" if len(visible) == 1 else "items"
        text = f"{len(visible):,} {noun} · {format_size(sum(item.size for item in visible))}"
        if hidden:
            text += f" · {hidden:,} in use not shown"
        self.summary.configure(text=text)

    def _selected(self) -> List[Leftover]:
        return [self._rows[row] for row in self.tree.selection() if row in self._rows]

    def _show_note(self) -> None:
        selected = self._selected()
        if len(selected) == 1:
            self.note.configure(text=f"{selected[0].note}\n{selected[0].path}")
        elif selected:
            total = sum(item.size for item in selected)
            self.note.configure(text=f"{len(selected):,} items selected · {format_size(total)}")
        else:
            self.note.configure(text="")

    # --- Actions ---------------------------------------------------------------------

    def _reveal(self) -> None:
        selected = self._selected()
        if not selected:
            return
        error = reveal_in_finder([item.path for item in selected[:MAX_REVEAL]])
        if error:
            show_error(self, "Reveal in Finder", error)

    def _trash_selected(self) -> None:
        selected = self._selected()
        if not selected:
            show_error(self, "Move to Trash", "Select the items you want to remove first.")
            return
        warnings = []
        in_use = [item for item in selected if item.kind == IN_USE]
        if in_use:
            warnings.append(
                f"{len(in_use):,} of these items are still used by an installed tool, "
                "which may have to download or rebuild them."
            )
        if any(item.kind == NOT_INSTALLED for item in selected):
            warnings.append(
                "Items marked “App not installed” include settings. "
                "Keep them if you plan to install the app again."
            )
        total = sum(item.size for item in selected)
        if not confirm_trash(self, len(selected), total, "\n\n".join(warnings)):
            return

        result = trash_with_feedback(self, [item.path for item in selected])
        moved = set(result.moved)
        self._results = [item for item in self._results if os.path.abspath(item.path) not in moved]
        self._render()
