"""The Duplicate Files tab."""

from __future__ import annotations

import os
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional

from ..duplicates import DuplicateGroup, DuplicateScanOptions, DuplicateScanResult, FileEntry, find_duplicates
from ..fsutils import format_size, reveal_in_finder
from .common import (
    MAX_REVEAL,
    BackgroundTask,
    FolderField,
    ProgressRow,
    card,
    confirm_trash,
    scrolled_tree,
    show_error,
    trash_with_feedback,
)
from .theme import Theme


class DuplicatesTab(ttk.Frame):
    def __init__(self, master: tk.Misc, theme: Theme, notify: Callable[[str], None]) -> None:
        super().__init__(master, padding=(24, 20, 24, 24))
        self._theme = theme
        self._notify = notify
        self.folder = tk.StringVar()
        self.include_hidden = tk.BooleanVar(value=False)
        self.include_packages = tk.BooleanVar(value=False)
        self.min_size_kb = tk.StringVar(value="0")
        self._task: Optional[BackgroundTask] = None
        self._root_folder = ""
        self._groups: Dict[str, DuplicateGroup] = {}  # Tree id of a group row -> group.
        self._files: Dict[str, FileEntry] = {}  # Tree id of a file row -> file.
        self._build()

    # --- Layout ----------------------------------------------------------------------

    def _build(self) -> None:
        search = card(
            self,
            "Find duplicate files",
            "Finds files with exactly the same contents, whatever their names.",
        )
        search.grid(row=0, column=0, sticky="ew")

        folder_row = ttk.Frame(search, style="OnCard.TFrame")
        folder_row.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        ttk.Label(folder_row, text="Folder", style="Body.Card.TLabel").grid(row=0, column=0, padx=(0, 12))
        self.folder_field = FolderField(folder_row, self.folder, "Choose a folder to search for duplicates")
        self.folder_field.grid(row=0, column=1, sticky="ew")
        folder_row.columnconfigure(1, weight=1)

        options = ttk.Frame(search, style="OnCard.TFrame")
        options.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        ttk.Checkbutton(
            options, text="Hidden files", variable=self.include_hidden, style="Chip.TCheckbutton"
        ).grid(row=0, column=0, padx=(0, 8))
        ttk.Checkbutton(
            options, text="Inside apps and packages", variable=self.include_packages, style="Chip.TCheckbutton"
        ).grid(row=0, column=1, padx=(0, 24))
        ttk.Label(options, text="Ignore files smaller than", style="Secondary.Card.TLabel").grid(row=0, column=2)
        ttk.Entry(options, textvariable=self.min_size_kb, width=7, justify="right").grid(row=0, column=3, padx=8)
        ttk.Label(options, text="KB", style="Secondary.Card.TLabel").grid(row=0, column=4)

        controls = ttk.Frame(search, style="OnCard.TFrame")
        controls.grid(row=4, column=0, sticky="ew", pady=(20, 0))
        self.scan_button = ttk.Button(
            controls, text="Find Duplicates", style="Filled.TButton", command=self._toggle_scan, width=16
        )
        self.scan_button.grid(row=0, column=0, sticky="nw")
        self.progress = ProgressRow(controls)
        self.progress.grid(row=0, column=1, sticky="ew", padx=(20, 0), pady=(10, 0))
        controls.columnconfigure(1, weight=1)

        results = card(self)
        results.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        header = ttk.Frame(results, style="OnCard.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="Results", style="Title.Card.TLabel").grid(row=0, column=0, sticky="w")
        self.summary = ttk.Label(header, text="", style="Secondary.Card.TLabel")
        self.summary.grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Button(
            header, text="Select Extra Copies", style="Text.TButton", command=self._select_extra_copies
        ).grid(row=0, column=2, sticky="e")
        header.columnconfigure(1, weight=1)

        tree_frame, self.tree = scrolled_tree(
            results, ("folder", "size", "modified"), selectmode="extended"
        )
        tree_frame.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.tree.heading("#0", text="Name", anchor="w")
        self.tree.heading("folder", text="Folder", anchor="w")
        self.tree.heading("size", text="Size", anchor="e")
        self.tree.heading("modified", text="Modified", anchor="w")
        self.tree.column("#0", width=340, stretch=True)
        self.tree.column("folder", width=300, stretch=True)
        self.tree.column("size", width=90, anchor="e", stretch=False)
        self.tree.column("modified", width=150, stretch=False)
        self.tree.tag_configure(
            "group",
            font=self._theme.fonts.label,
            background=self._theme.palette.surface_container,
            foreground=self._theme.palette.on_surface,
        )
        self.tree.bind("<Double-1>", lambda _event: self._reveal())

        actions = ttk.Frame(results, style="OnCard.TFrame")
        actions.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        ttk.Button(actions, text="Reveal in Finder", style="Outlined.TButton", command=self._reveal).grid(
            row=0, column=1, padx=(0, 8)
        )
        ttk.Button(
            actions, text="Move to Trash…", style="Danger.TButton", command=self._trash_selected
        ).grid(row=0, column=2)
        actions.columnconfigure(0, weight=1)

        results.rowconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self.progress.idle("Choose a folder, then click Find Duplicates.")

    # --- Scanning --------------------------------------------------------------------

    def _toggle_scan(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self.scan_button.configure(state="disabled")
            self.progress.busy("Stopping…")
            return

        typed = self.folder.get().strip()
        folder = os.path.abspath(os.path.expanduser(typed)) if typed else ""
        if not folder or not os.path.isdir(folder):
            show_error(self, "Find Duplicates", "Choose a folder that exists.")
            return
        try:
            min_kb = float(self.min_size_kb.get().strip() or "0")
            if min_kb < 0:
                raise ValueError
        except ValueError:
            show_error(self, "Find Duplicates", "The minimum size must be a number of KB, such as 0 or 100.")
            return

        options = DuplicateScanOptions(
            include_hidden=self.include_hidden.get(),
            include_packages=self.include_packages.get(),
            min_size=max(1, int(min_kb * 1000)),
        )
        self._clear_results()
        self._root_folder = folder
        self.scan_button.configure(text="Cancel", style="Tonal.TButton")
        self.progress.busy("Looking for files…")
        self._task = BackgroundTask(
            self,
            lambda progress, cancel: find_duplicates(folder, options, progress, cancel),
            on_progress=self.progress.busy,
            on_done=self._scan_finished,
            on_error=self._scan_failed,
            on_cancelled=lambda: self._scan_ended("Search cancelled."),
        )
        self._task.start()

    def _scan_ended(self, message: str) -> None:
        self._task = None
        self.scan_button.configure(text="Find Duplicates", style="Filled.TButton", state="normal")
        self.progress.idle(message)

    def _scan_failed(self, error: BaseException) -> None:
        self._scan_ended("The search stopped because of an error.")
        show_error(self, "Find Duplicates", str(error))

    def _scan_finished(self, result: DuplicateScanResult) -> None:
        for group in result.groups:
            self._insert_group(group)
        message = f"Checked {result.files_scanned:,} files."
        if result.unreadable:
            message += f" {len(result.unreadable):,} could not be read."
        if result.cloud_only:
            message += f" Skipped {result.cloud_only:,} iCloud files that aren't downloaded."
        self._scan_ended(message)
        self._update_summary()

    # --- Results ---------------------------------------------------------------------

    def _clear_results(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._groups.clear()
        self._files.clear()
        self._update_summary()

    def _insert_group(self, group: DuplicateGroup) -> None:
        group_id = self.tree.insert("", "end", text=self._group_label(group), open=True, tags=("group",))
        self._groups[group_id] = group
        top = os.path.basename(self._root_folder) or self._root_folder
        for entry in group.files:
            relative = os.path.relpath(os.path.dirname(entry.path), self._root_folder)
            shown_folder = top if relative == "." else os.path.join(top, relative)
            file_id = self.tree.insert(
                group_id,
                "end",
                text=os.path.basename(entry.path),
                values=(
                    shown_folder,
                    format_size(entry.size),
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(entry.modified)),
                ),
            )
            self._files[file_id] = entry

    @staticmethod
    def _group_label(group: DuplicateGroup) -> str:
        return (
            f"{len(group.files)} copies, {format_size(group.size)} each "
            f"({format_size(group.reclaimable)} can be freed)"
        )

    def _update_summary(self) -> None:
        if not self._groups:
            self.summary.configure(text="")
            return
        reclaimable = sum(group.reclaimable for group in self._groups.values())
        noun = "set" if len(self._groups) == 1 else "sets"
        self.summary.configure(
            text=f"{len(self._groups):,} {noun} of duplicates · {format_size(reclaimable)} can be freed"
        )

    def _selected_files(self) -> List[str]:
        return [item for item in self.tree.selection() if item in self._files]

    # --- Actions ---------------------------------------------------------------------

    def _reveal(self) -> None:
        paths = []
        for item in self.tree.selection():
            if item in self._files:
                paths.append(self._files[item].path)
            elif item in self._groups:
                paths.append(self._groups[item].files[0].path)
        if not paths:
            return
        error = reveal_in_finder(list(dict.fromkeys(paths))[:MAX_REVEAL])
        if error:
            show_error(self, "Reveal in Finder", error)

    def _select_extra_copies(self) -> None:
        """Select every copy except the oldest one in each set."""
        extra = []
        for group_id in self._groups:
            extra.extend(self.tree.get_children(group_id)[1:])
        self.tree.selection_set(extra)
        if extra:
            self.tree.see(extra[0])

    def _trash_selected(self) -> None:
        selected = self._selected_files()
        if not selected:
            show_error(self, "Move to Trash", "Select the copies you want to remove first.")
            return
        selected_set = set(selected)
        whole_groups = sum(
            1
            for group_id in self._groups
            if all(child in selected_set for child in self.tree.get_children(group_id))
        )
        warning = ""
        if whole_groups:
            noun = "set" if whole_groups == 1 else "sets"
            warning = f"Every copy is selected in {whole_groups:,} {noun}, so no copy of those files will be left."
        total = sum(self._files[item].size for item in selected)
        if not confirm_trash(self, len(selected), total, warning):
            return

        result = trash_with_feedback(self, [self._files[item].path for item in selected])
        if result.moved:
            self._notify(_moved_message(len(result.moved)))
        moved = set(result.moved)
        for item in selected:
            # A row can already be gone: removing the last other copy removes the whole set.
            if item in self._files and self._files[item].path in moved:
                self._remove_file_row(item)
        self._update_summary()

    def _remove_file_row(self, item: str) -> None:
        group_id = self.tree.parent(item)
        self.tree.delete(item)
        del self._files[item]
        group = self._groups[group_id]
        remaining = [self._files[child] for child in self.tree.get_children(group_id)]
        if len(remaining) < 2:
            for child in self.tree.get_children(group_id):
                del self._files[child]
            self.tree.delete(group_id)
            del self._groups[group_id]
            return
        group.files = remaining
        self.tree.item(group_id, text=self._group_label(group))


def _moved_message(count: int) -> str:
    return f"Moved {count:,} {'item' if count == 1 else 'items'} to the Trash."
