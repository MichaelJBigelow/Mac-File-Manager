"""A Material Design 3 look for the app, built on ttk's "clam" theme.

Colors are the Material 3 baseline scheme, light or dark to match macOS. Buttons, text
fields, chips, switches, cards, scroll bars and the progress bar are rounded images drawn by
ui.images, which needs Tk 8.6 or later (Tk 8.5 can't load PNG images).
"""

from __future__ import annotations

import subprocess
import tkinter as tk
from dataclasses import dataclass
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any, Dict, List, Optional, Tuple

from . import images


@dataclass(frozen=True)
class Palette:
    primary: str
    on_primary: str
    primary_container: str
    on_primary_container: str
    secondary_container: str
    on_secondary_container: str
    error: str
    on_error: str
    surface: str
    on_surface: str
    on_surface_variant: str
    outline: str
    outline_variant: str
    surface_container_lowest: str
    surface_container_low: str
    surface_container: str
    surface_container_high: str
    surface_container_highest: str
    inverse_surface: str
    inverse_on_surface: str
    inverse_primary: str


LIGHT = Palette(
    primary="#6750a4",
    on_primary="#ffffff",
    primary_container="#eaddff",
    on_primary_container="#21005d",
    secondary_container="#e8def8",
    on_secondary_container="#1d192b",
    error="#b3261e",
    on_error="#ffffff",
    surface="#fef7ff",
    on_surface="#1d1b20",
    on_surface_variant="#49454f",
    outline="#79747e",
    outline_variant="#cac4d0",
    surface_container_lowest="#ffffff",
    surface_container_low="#f7f2fa",
    surface_container="#f3edf7",
    surface_container_high="#ece6f0",
    surface_container_highest="#e6e0e9",
    inverse_surface="#322f35",
    inverse_on_surface="#f5eff7",
    inverse_primary="#d0bcff",
)

DARK = Palette(
    primary="#d0bcff",
    on_primary="#381e72",
    primary_container="#4f378b",
    on_primary_container="#eaddff",
    secondary_container="#4a4458",
    on_secondary_container="#e8def8",
    error="#f2b8b5",
    on_error="#601410",
    surface="#141218",
    on_surface="#e6e0e9",
    on_surface_variant="#cac4d0",
    outline="#938f99",
    outline_variant="#49454f",
    surface_container_lowest="#0f0d13",
    surface_container_low="#1d1b20",
    surface_container="#211f26",
    surface_container_high="#2b2930",
    surface_container_highest="#36343b",
    inverse_surface="#e6e0e9",
    inverse_on_surface="#322f35",
    inverse_primary="#6750a4",
)

# Opacity of Material state layers.
HOVER = 0.08
PRESSED = 0.12
DISABLED_CONTAINER = 0.12
DISABLED_CONTENT = 0.38

BUTTON_HEIGHT = 40
CHIP_HEIGHT = 32
FIELD_HEIGHT = 40
CARD_RADIUS = 16

# How large stretchable images are encoded (see Theme._shape): wider than any button or chip,
# and than any text field or progress bar.
WIDE = 600
WIDER = 2000


def is_dark_mode() -> bool:
    """True when macOS uses its dark appearance."""
    try:
        completed = subprocess.run(
            ["/usr/bin/defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.stdout.strip().lower() == "dark"


class Fonts:
    """The Material type scale, in the system font."""

    def __init__(self, root: tk.Misc) -> None:
        family = tkfont.nametofont("TkDefaultFont").actual("family")
        self.headline = tkfont.Font(root, family=family, size=22)
        self.title = tkfont.Font(root, family=family, size=15, weight="bold")
        self.body = tkfont.Font(root, family=family, size=13)
        self.label = tkfont.Font(root, family=family, size=13, weight="bold")
        self.small = tkfont.Font(root, family=family, size=11)


# Text roles for labels: (font attribute, palette color attribute).
_LABEL_ROLES = {
    "Headline": ("headline", "on_surface"),
    "Title": ("title", "on_surface"),
    "Body": ("body", "on_surface"),
    "Secondary": ("body", "on_surface_variant"),
    "Caption": ("small", "on_surface_variant"),
}


class Theme:
    """Applies the Material theme to a Tk root and keeps the images it needs alive.

    Label styles are named "<Role>.<Container>.TLabel", for example "Title.Card.TLabel",
    where Role is Headline, Title, Body, Secondary or Caption and Container is Surface
    (the window background), Card or Snackbar. Buttons: Filled, Tonal, Outlined, Text and
    Danger (".TButton"). Check buttons: Chip and Switch (".TCheckbutton"). Frames: Card,
    OnCard (a plain frame inside a card) and Snackbar (".TFrame"). Tabs use "Tab.TButton".
    """

    def __init__(self, root: tk.Tk, dark: Optional[bool] = None) -> None:
        self.root = root
        self.dark = is_dark_mode() if dark is None else dark
        self.palette = DARK if self.dark else LIGHT
        self.fonts = Fonts(root)
        self.style = ttk.Style(root)
        self._images: List[tk.PhotoImage] = []
        self._apply()

    # --- Public helpers --------------------------------------------------------------

    @property
    def card(self) -> str:
        return self.palette.surface_container_low

    def image(self, canvas: images.Canvas, width: Optional[int] = None, height: Optional[int] = None) -> tk.PhotoImage:
        photo = tk.PhotoImage(master=self.root, data=canvas.to_base64(width, height))
        self._images.append(photo)
        return photo

    # --- Building the theme ----------------------------------------------------------

    def _apply(self) -> None:
        p = self.palette
        style = self.style
        name = "material-dark" if self.dark else "material-light"
        style.theme_create(name, parent="clam")
        style.theme_use(name)
        self.root.configure(background=p.surface)
        style.configure(
            ".",
            background=p.surface,
            foreground=p.on_surface,
            font=self.fonts.body,
            bordercolor=p.outline_variant,
            lightcolor=p.surface,
            darkcolor=p.surface,
            troughcolor=p.surface_container_highest,
            focuscolor=p.primary,
            selectbackground=p.primary_container,
            selectforeground=p.on_primary_container,
            insertcolor=p.on_surface,
            fieldbackground=p.surface_container_lowest,
            relief="flat",
            borderwidth=0,
        )
        style.configure("TFrame", background=p.surface)
        style.configure("TLabel", background=p.surface, foreground=p.on_surface)
        self._frames()
        self._labels()
        self._buttons()
        self._tabs()
        self._chips()
        self._switch()
        self._entry()
        self._tree()
        self._scrollbar()
        self._progressbar()

    def _shape(
        self,
        name: str,
        normal: images.Canvas,
        *states: Tuple[Any, ...],
        stretch: Tuple[Optional[int], Optional[int]] = (None, None),
        **options: Any,
    ) -> None:
        """Create an image element from a canvas and (state, ..., canvas) pairs.

        ttk fills a widget by tiling the stretchable middle of an element's image, once per
        tile. With a middle of a pixel or two, a card took over 100,000 draws and the window
        took seconds to redraw. So the images are encoded `stretch` (width, height) large, with
        their middle repeated, while the element still asks for only the canvas's own size.
        """
        width, height = stretch
        if width:
            options.setdefault("width", normal.width)
        if height:
            options.setdefault("height", normal.height)
        specs = [tuple(state[:-1]) + (self.image(state[-1], width, height),) for state in states]
        self.style.element_create(name, "image", self.image(normal, width, height), *specs, **options)

    def _frames(self) -> None:
        p = self.palette
        self.style.configure("OnCard.TFrame", background=self.card)

        # A card is a plain fill with a small image in each corner. A card-sized image would
        # be redrawn behind every widget in the card each time any of them changes (macOS
        # redraws the whole area), which halved the frame rate.
        r = CARD_RADIUS
        corners = {"nw": (0, 0), "ne": (-2 * r, 0), "sw": (0, -2 * r), "se": (-2 * r, -2 * r)}
        layout: List[Tuple[str, Dict[str, Any]]] = [("Card.fill", {"sticky": "nsew"})]
        for corner, (dx, dy) in corners.items():
            canvas = images.Canvas(r, r)
            canvas.draw(images.rounded_rect(0, 0, r, r, 0), images.hex_color(p.surface))
            canvas.draw(images.rounded_rect(dx, dy, dx + 3 * r, dy + 3 * r, r), images.hex_color(self.card))
            self._shape(f"Card.{corner}", canvas, sticky=corner)
            layout.append((f"Card.{corner}", {"sticky": corner}))
        self.style.layout("Card.TFrame", layout)
        self.style.configure("Card.TFrame", background=self.card)

        # The snackbar is small and shown only briefly, so one stretched image is fine.
        radius = 8
        size = radius * 2 + 2
        self._shape(
            "Snackbar.shape",
            images.pill(size, size, p.inverse_surface, radius=radius),
            stretch=(800, 80),
            border=radius,
            sticky="nsew",
        )
        self.style.layout("Snackbar.TFrame", _framed("Snackbar.fill", "Snackbar.shape"))
        # The fill behind the rounded corners is the window background.
        self.style.configure("Snackbar.TFrame", background=p.surface)

    def _labels(self) -> None:
        p = self.palette
        containers = {"Surface": p.surface, "Card": self.card, "Snackbar": p.inverse_surface}
        for container, background in containers.items():
            for role, (font_name, color_name) in _LABEL_ROLES.items():
                foreground = p.inverse_on_surface if container == "Snackbar" else getattr(p, color_name)
                self.style.configure(
                    f"{role}.{container}.TLabel",
                    background=background,
                    foreground=foreground,
                    font=getattr(self.fonts, font_name),
                )

    def _buttons(self) -> None:
        p = self.palette
        card = self.card
        variants: Dict[str, Tuple[Optional[str], str, str, Optional[str]]] = {
            # name: (container color, label color, state layer color, outline color)
            "Filled": (p.primary, p.on_primary, p.on_primary, None),
            "Tonal": (p.secondary_container, p.on_secondary_container, p.on_secondary_container, None),
            "Outlined": (None, p.primary, p.primary, p.outline),
            "Text": (None, p.primary, p.primary, None),
            "Danger": (p.error, p.on_error, p.on_error, None),
        }
        disabled_label = images.blend(card, p.on_surface, DISABLED_CONTENT)
        disabled_fill = images.blend(card, p.on_surface, DISABLED_CONTAINER)
        h, w = BUTTON_HEIGHT, BUTTON_HEIGHT + 2  # The extra width is the part that stretches.
        for variant, (fill, label, layer, outline) in variants.items():
            base = fill or card
            self._shape(
                f"{variant}.Button.shape",
                images.pill(w, h, fill, outline),
                ("disabled", images.pill(w, h, disabled_fill if fill else None, disabled_fill if outline else None)),
                ("pressed", images.pill(w, h, images.blend(base, layer, PRESSED), outline)),
                ("active", images.pill(w, h, images.blend(base, layer, HOVER), outline)),
                stretch=(WIDE, None),
                border=(h // 2, 0),
                sticky="nsew",
            )
            style_name = f"{variant}.TButton"
            self.style.layout(style_name, _framed(f"{variant}.Button.fill", f"{variant}.Button.shape", _BUTTON_LABEL))
            self.style.configure(
                style_name, background=card, foreground=label, font=self.fonts.label, anchor="center", padding=(16, 0)
            )
            self.style.map(
                style_name,
                foreground=[("disabled", disabled_label)],
                background=[("active", card), ("pressed", card), ("disabled", card)],
            )

    def _tabs(self) -> None:
        p = self.palette
        hover = images.blend(p.surface, p.on_surface, HOVER)
        pressed = images.blend(p.surface, p.on_surface, PRESSED)
        self.style.layout("Tab.TButton", [("Button.border", {"sticky": "nsew", "children": _BUTTON_LABEL})])
        self.style.configure(
            "Tab.TButton",
            font=self.fonts.label,
            foreground=p.on_surface_variant,
            background=p.surface,
            bordercolor=p.surface,
            lightcolor=p.surface,
            darkcolor=p.surface,
            borderwidth=0,
            padding=(20, 10),
            anchor="center",
        )
        colors = [("pressed", pressed), ("active", hover)]
        self.style.map(
            "Tab.TButton",
            foreground=[("selected", p.primary), ("active", p.on_surface)],
            background=colors,
            bordercolor=colors,
            lightcolor=colors,
            darkcolor=colors,
        )

    def _chips(self) -> None:
        """Material filter chips: outlined when off, tonal with a check mark when on."""
        p = self.palette
        card = self.card
        h = CHIP_HEIGHT
        selected = p.secondary_container
        self._shape(
            "Chip.shape",
            images.pill(h, h, None, p.outline_variant, radius=8),
            ("selected", "active", images.pill(h, h, images.blend(selected, p.on_secondary_container, HOVER), radius=8)),
            ("selected", images.pill(h, h, selected, radius=8)),
            ("active", images.pill(h, h, images.blend(card, p.on_surface_variant, HOVER), p.outline_variant, radius=8)),
            stretch=(WIDE, None),
            border=8,
            sticky="nsew",
        )
        style_name = "Chip.TCheckbutton"
        self.style.layout(style_name, _framed("Chip.fill", "Chip.shape", _CHECKBUTTON_LABEL))
        check = self.image(images.check_mark(18, p.on_secondary_container))
        self.style.configure(
            style_name,
            background=card,
            foreground=p.on_surface_variant,
            font=self.fonts.label,
            padding=(12, 0),
            compound="left",
            image="",
        )
        # The check mark shows only while the chip is on, as in Material filter chips.
        self.style.map(
            style_name,
            foreground=[("selected", p.on_secondary_container)],
            background=[("active", card)],
            image=[("selected", check)],
        )

    def _switch(self) -> None:
        p = self.palette
        card = self.card
        w, h = 44, 26
        self._shape(
            "Switch.indicator",
            images.switch(w, h, False, p.surface_container_highest, p.outline, p.outline),
            ("selected", images.switch(w, h, True, p.primary, p.on_primary)),
            width=w + 10,
            sticky="e",
        )
        self.style.layout(
            "Switch.TCheckbutton",
            [
                (
                    "Switch.fill",
                    {
                        "sticky": "nsew",
                        "children": [
                            (
                                "Checkbutton.padding",
                                {
                                    "sticky": "nsew",
                                    "children": [
                                        ("Checkbutton.label", {"side": "left", "sticky": "w"}),
                                        ("Switch.indicator", {"side": "left", "sticky": "e"}),
                                    ],
                                },
                            )
                        ],
                    },
                )
            ],
        )
        self.style.configure("Switch.TCheckbutton", background=card, foreground=p.on_surface, font=self.fonts.body, padding=(0, 4))
        self.style.map("Switch.TCheckbutton", background=[("active", card)])

    def _entry(self) -> None:
        """Outlined text fields: the outline turns primary and thicker with focus."""
        p = self.palette
        card = self.card
        h = FIELD_HEIGHT
        self._shape(
            "Field.shape",
            images.pill(h, h, None, p.outline, radius=6),
            ("focus", images.pill(h, h, None, p.primary, border_width=2, radius=6)),
            ("hover", images.pill(h, h, None, p.on_surface, radius=6)),
            stretch=(WIDER, None),
            border=8,
            sticky="nsew",
        )
        self.style.layout(
            "TEntry",
            _framed("Field.fill", "Field.shape", [("Entry.padding", {"sticky": "nsew", "children": [("Entry.textarea", {"sticky": "nsew"})]})]),
        )
        self.style.configure(
            "TEntry",
            background=card,
            foreground=p.on_surface,
            insertcolor=p.on_surface,
            selectbackground=p.primary_container,
            selectforeground=p.on_primary_container,
            padding=(12, 0),
        )
        self.style.map("TEntry", foreground=[("disabled", images.blend(card, p.on_surface, DISABLED_CONTENT))])

    def _tree(self) -> None:
        p = self.palette
        card = self.card
        self.style.layout("Treeview", [("Treeview.treearea", {"sticky": "nsew"})])
        self.style.configure(
            "Treeview",
            background=card,
            fieldbackground=card,
            foreground=p.on_surface,
            font=self.fonts.body,
            rowheight=32,
            borderwidth=0,
            indicatorsize=10,
        )
        self.style.map(
            "Treeview",
            background=[("selected", p.secondary_container)],
            foreground=[("selected", p.on_secondary_container)],
        )
        hover = images.blend(card, p.on_surface, HOVER)
        self.style.configure(
            "Treeview.Heading",
            background=card,
            foreground=p.on_surface_variant,
            font=self.fonts.label,
            relief="flat",
            borderwidth=0,
            bordercolor=card,
            lightcolor=card,
            darkcolor=card,
            padding=(8, 8),
        )
        colors = [("active", hover)]
        self.style.map("Treeview.Heading", background=colors, lightcolor=colors, darkcolor=colors, bordercolor=colors)

    def _scrollbar(self) -> None:
        p = self.palette
        w, h = 12, 24
        self._shape(
            "Material.Vertical.Scrollbar.thumb",
            _scroll_thumb(w, h, p.outline_variant),
            ("active", _scroll_thumb(w, h, p.outline)),
            stretch=(None, WIDE),
            border=(0, 6),
            sticky="nsew",
        )
        self.style.layout(
            "Vertical.TScrollbar",
            [
                (
                    "Vertical.Scrollbar.trough",
                    {"sticky": "ns", "children": [("Material.Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nsew"})]},
                )
            ],
        )
        self.style.configure("Vertical.TScrollbar", troughcolor=self.card, bordercolor=self.card, lightcolor=self.card, darkcolor=self.card)

    def _progressbar(self) -> None:
        """A Material linear progress indicator: a 4 px rounded bar on a tonal track."""
        p = self.palette
        w, h = 6, 4
        for name, color, sticky in (("trough", p.secondary_container, "ew"), ("pbar", p.primary, "nsw")):
            self._shape(
                f"Material.Progressbar.{name}",
                images.pill(w, h, color),
                stretch=(WIDER, None),
                border=(2, 0),
                sticky=sticky,
            )
        self.style.layout(
            "Horizontal.TProgressbar",
            [
                (
                    "Progress.fill",
                    {
                        "sticky": "nsew",
                        "children": [
                            (
                                "Material.Progressbar.trough",
                                {"sticky": "nsew", "children": [("Material.Progressbar.pbar", {"side": "left", "sticky": "ns"})]},
                            )
                        ],
                    },
                )
            ],
        )
        self.style.configure("Horizontal.TProgressbar", background=self.card)


_BUTTON_LABEL = [("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]
_CHECKBUTTON_LABEL = [("Checkbutton.padding", {"sticky": "nsew", "children": [("Checkbutton.label", {"sticky": "nsew"})]})]


def _framed(fill: str, shape: str, children: Optional[list] = None) -> list:
    """A layout: a background fill (behind the rounded corners), the shape, then children."""
    shape_spec: Dict[str, Any] = {"sticky": "nsew"}
    if children:
        shape_spec["children"] = children
    return [(fill, {"sticky": "nsew", "children": [(shape, shape_spec)]})]


def _scroll_thumb(width: int, height: int, color: str) -> images.Canvas:
    canvas = images.Canvas(width, height)
    canvas.draw(images.rounded_rect(3, 1, width - 3, height - 1, (width - 6) / 2), images.hex_color(color))
    return canvas
