"""Draw small anti-aliased images as PNG data, in pure Python (no Pillow).

Shapes are given as signed distance functions: negative inside the shape, positive outside,
measured in pixels. The Material theme builds its rounded buttons, fields, chips and switches
from these images, and tools/make_icon.py draws the app icon with them.
"""

from __future__ import annotations

import base64
import math
import struct
import zlib
from typing import Callable, List, Optional, Sequence, Tuple

Color = Tuple[float, float, float, float]  # Red, green and blue from 0 to 255; alpha from 0 to 1.
Distance = Callable[[float, float], float]
Bounds = Tuple[float, float, float, float]


def hex_color(value: str, alpha: float = 1.0) -> Color:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha)


def blend(base: str, overlay: str, amount: float) -> str:
    """Paint overlay over base at the given opacity, like a Material state layer."""
    b = hex_color(base)
    o = hex_color(overlay)
    mixed = (round(b[i] + (o[i] - b[i]) * amount) for i in range(3))
    return "#{:02x}{:02x}{:02x}".format(*mixed)


# --- Shapes ----------------------------------------------------------------------------


def rounded_rect(x0: float, y0: float, x1: float, y1: float, radius: float) -> Distance:
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    half_w, half_h = (x1 - x0) / 2, (y1 - y0) / 2
    r = max(0.0, min(radius, half_w, half_h))
    inner_w, inner_h = half_w - r, half_h - r

    def distance(px: float, py: float) -> float:
        qx = abs(px - cx) - inner_w
        qy = abs(py - cy) - inner_h
        outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
        inside = min(max(qx, qy), 0.0)
        return outside + inside - r

    return distance


def circle(cx: float, cy: float, radius: float) -> Distance:
    return lambda px, py: math.hypot(px - cx, py - cy) - radius


def polyline(points: Sequence[Tuple[float, float]], width: float) -> Distance:
    """A stroke of the given width along the points, with round ends and joins."""
    segments = list(zip(points, points[1:]))
    half = width / 2

    def distance(px: float, py: float) -> float:
        best = math.inf
        for (ax, ay), (bx, by) in segments:
            dx, dy = bx - ax, by - ay
            length = dx * dx + dy * dy
            t = 0.0 if length == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
            best = min(best, math.hypot(px - ax - t * dx, py - ay - t * dy))
        return best - half

    return distance


def union(*shapes: Distance) -> Distance:
    return lambda px, py: min(shape(px, py) for shape in shapes)


def inner_border(shape: Distance, width: float) -> Distance:
    """A border of the given width just inside the edge of shape."""
    return lambda px, py: max(shape(px, py), -shape(px, py) - width)


# --- Canvas ----------------------------------------------------------------------------


class Canvas:
    """An RGBA image that shapes are painted onto, one over another."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._pixels: List[float] = [0.0] * (width * height * 4)  # Premultiplied, 0 to 1.

    def draw(
        self,
        shape: Distance,
        color: Color,
        bounds: Optional[Bounds] = None,
        softness: float = 1.0,
        color_at: Optional[Callable[[float, float], Color]] = None,
    ) -> None:
        """Paint shape in color (or color_at(x, y)), with edges blurred over `softness` pixels.

        bounds limits the pixels that are tested, which makes large images much faster.
        """
        x0, y0, x1, y1 = bounds if bounds is not None else (0, 0, self.width, self.height)
        x0, y0 = max(0, int(math.floor(x0))), max(0, int(math.floor(y0)))
        x1, y1 = min(self.width, int(math.ceil(x1))), min(self.height, int(math.ceil(y1)))
        pixels = self._pixels
        width = self.width
        for y in range(y0, y1):
            py = y + 0.5
            row = y * width
            for x in range(x0, x1):
                px = x + 0.5
                coverage = 0.5 - shape(px, py) / softness
                if coverage <= 0.0:
                    continue
                if coverage > 1.0:
                    coverage = 1.0
                r, g, b, a = color_at(px, py) if color_at is not None else color
                a *= coverage
                keep = 1.0 - a
                i = (row + x) * 4
                pixels[i] = r / 255.0 * a + pixels[i] * keep
                pixels[i + 1] = g / 255.0 * a + pixels[i + 1] * keep
                pixels[i + 2] = b / 255.0 * a + pixels[i + 2] * keep
                pixels[i + 3] = a + pixels[i + 3] * keep

    def rgba(self, x: int, y: int) -> Tuple[int, int, int, int]:
        """The pixel at (x, y) as 8-bit, non-premultiplied red, green, blue and alpha."""
        i = (y * self.width + x) * 4
        r, g, b, a = self._pixels[i : i + 4]
        if a <= 0.0:
            return (0, 0, 0, 0)
        return (round(r / a * 255), round(g / a * 255), round(b / a * 255), round(a * 255))

    def to_png(self) -> bytes:
        rows = bytearray()
        for y in range(self.height):
            rows.append(0)  # No filter.
            for x in range(self.width):
                rows.extend(self.rgba(x, y))

        def chunk(kind: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

        header = struct.pack(">IIBBBBB", self.width, self.height, 8, 6, 0, 0, 0)  # 8-bit RGBA.
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
            + chunk(b"IEND", b"")
        )

    def to_base64(self) -> str:
        return base64.b64encode(self.to_png()).decode("ascii")


# --- Theme pieces ----------------------------------------------------------------------


def pill(
    width: int,
    height: int,
    fill: Optional[str],
    border: Optional[str] = None,
    border_width: float = 1.0,
    radius: Optional[float] = None,
) -> Canvas:
    """A rounded rectangle (fully rounded ends by default), filled and/or outlined."""
    canvas = Canvas(width, height)
    shape = rounded_rect(0, 0, width, height, height / 2 if radius is None else radius)
    if fill:
        canvas.draw(shape, hex_color(fill))
    if border:
        canvas.draw(inner_border(shape, border_width), hex_color(border))
    return canvas


def checkbox(size: int, checked: bool, box: str, mark: str, border_width: float = 2.0) -> Canvas:
    """A Material checkbox: an outlined square, or a filled one with a check mark."""
    canvas = Canvas(size, size)
    inset = size * 0.1
    shape = rounded_rect(inset, inset, size - inset, size - inset, size * 0.12)
    if checked:
        canvas.draw(shape, hex_color(box))
        canvas.draw(
            polyline([(size * 0.28, size * 0.52), (size * 0.43, size * 0.67), (size * 0.73, size * 0.36)], size * 0.11),
            hex_color(mark),
        )
    else:
        canvas.draw(inner_border(shape, border_width), hex_color(box))
    return canvas


def check_mark(size: int, color: str) -> Canvas:
    canvas = Canvas(size, size)
    canvas.draw(
        polyline([(size * 0.2, size * 0.52), (size * 0.4, size * 0.72), (size * 0.8, size * 0.3)], size * 0.12),
        hex_color(color),
    )
    return canvas


def switch(
    width: int, height: int, on: bool, track: str, thumb: str, border: Optional[str] = None
) -> Canvas:
    """A Material switch: a rounded track with a round thumb at its left or right end."""
    canvas = Canvas(width, height)
    track_shape = rounded_rect(0, 0, width, height, height / 2)
    canvas.draw(track_shape, hex_color(track))
    if border:
        canvas.draw(inner_border(track_shape, 2.0), hex_color(border))
    radius = height * (0.34 if on else 0.25)
    cx = width - height / 2 if on else height / 2
    canvas.draw(circle(cx, height / 2, radius), hex_color(thumb))
    return canvas


def app_icon(size: int) -> Canvas:
    """The app icon: a folder holding two copies of a document, on a purple tile."""
    canvas = Canvas(size, size)
    s = size / 1024.0

    def rect(x0: float, y0: float, x1: float, y1: float, r: float) -> Tuple[Distance, Bounds]:
        return rounded_rect(x0 * s, y0 * s, x1 * s, y1 * s, r * s), (x0 * s, y0 * s, x1 * s, y1 * s)

    def grow(bounds: Bounds, by: float) -> Bounds:
        return (bounds[0] - by, bounds[1] - by, bounds[2] + by, bounds[3] + by)

    top, bottom = hex_color("#8069c7"), hex_color("#4f378b")

    def gradient(px: float, py: float) -> Color:
        t = min(1.0, max(0.0, (py / s - 100) / 824))
        return tuple(top[i] + (bottom[i] - top[i]) * t for i in range(3)) + (1.0,)  # type: ignore[return-value]

    shadow, shadow_bounds = rect(100, 116, 924, 940, 184)
    canvas.draw(shadow, (0, 0, 0, 0.3), grow(shadow_bounds, 30 * s), softness=max(1.0, 28 * s))
    tile, tile_bounds = rect(100, 100, 924, 924, 184)
    canvas.draw(tile, (0, 0, 0, 1), tile_bounds, color_at=gradient)

    tab, tab_bounds = rect(232, 320, 440, 440, 36)
    back, back_bounds = rect(232, 380, 792, 770, 48)
    canvas.draw(union(tab, back), hex_color("#d0bcff"), (tab_bounds[0], tab_bounds[1], back_bounds[2], back_bounds[3]))

    for x0, y0, fill, lines in ((330, 236, "#f3edf7", False), (400, 290, "#ffffff", True)):
        sheet_shadow, bounds = rect(x0, y0 + 10, x0 + 340, y0 + 410, 30)
        canvas.draw(sheet_shadow, (0, 0, 0, 0.18), grow(bounds, 16 * s), softness=max(1.0, 14 * s))
        sheet, bounds = rect(x0, y0, x0 + 340, y0 + 400, 30)
        canvas.draw(sheet, hex_color(fill), bounds)
        for line_y, line_end in ((70, 284), (130, 284), (190, 214)) if lines else ():
            line, bounds = rect(x0 + 56, y0 + line_y, x0 + line_end, y0 + line_y + 26, 13)
            canvas.draw(line, hex_color("#cac4d0"), bounds)

    front_shadow, bounds = rect(232, 486, 792, 770, 48)
    canvas.draw(front_shadow, (0, 0, 0, 0.2), grow(bounds, 18 * s), softness=max(1.0, 16 * s))
    front, bounds = rect(232, 500, 792, 770, 48)
    canvas.draw(front, hex_color("#eaddff"), bounds)
    return canvas
