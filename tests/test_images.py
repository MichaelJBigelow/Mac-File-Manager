import struct
import unittest
import zlib

from mac_file_manager.ui import images


def decode(png: bytes):
    """Width, height and rows of RGBA tuples of a PNG written by Canvas.to_png."""
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    pos, chunks = 8, {}
    while pos < len(png):
        (length,) = struct.unpack(">I", png[pos : pos + 4])
        kind = png[pos + 4 : pos + 8]
        data = png[pos + 8 : pos + 8 + length]
        (crc,) = struct.unpack(">I", png[pos + 8 + length : pos + 12 + length])
        assert crc == zlib.crc32(kind + data)
        chunks[kind] = data
        pos += 12 + length
    width, height, depth, color_type = struct.unpack(">IIBB", chunks[b"IHDR"][:10])
    assert (depth, color_type) == (8, 6)
    raw = zlib.decompress(chunks[b"IDAT"])
    rows = []
    stride = width * 4 + 1
    for y in range(height):
        line = raw[y * stride + 1 : (y + 1) * stride]
        rows.append([tuple(line[x * 4 : x * 4 + 4]) for x in range(width)])
    return width, height, rows


class ImagesTest(unittest.TestCase):
    def test_pill_has_transparent_corners_and_solid_middle(self):
        width, height, rows = decode(images.pill(42, 40, "#6750a4").to_png())
        self.assertEqual((width, height), (42, 40))
        self.assertEqual(rows[0][0][3], 0)
        self.assertEqual(rows[20][21], (0x67, 0x50, 0xA4, 255))
        self.assertTrue(0 < rows[3][8][3] < 255)  # The rounded corner's edge is anti-aliased.

    def test_outline_only(self):
        _, _, rows = decode(images.pill(40, 40, None, "#79747e", radius=6).to_png())
        self.assertEqual(rows[20][20][3], 0)  # Inside is empty.
        self.assertEqual(rows[20][0], (0x79, 0x74, 0x7E, 255))  # The edge is drawn.

    def test_blend(self):
        self.assertEqual(images.blend("#000000", "#ffffff", 0.5), "#808080")
        self.assertEqual(images.blend("#6750a4", "#ffffff", 0.0), "#6750a4")

    def test_checkbox_switch_and_icon(self):
        for canvas in (
            images.checkbox(18, True, "#6750a4", "#ffffff"),
            images.switch(44, 26, True, "#6750a4", "#ffffff"),
            images.check_mark(18, "#000000"),
            images.app_icon(64),
        ):
            width, height, _ = decode(canvas.to_png())
            self.assertEqual((width, height), (canvas.width, canvas.height))
        _, _, icon = decode(images.app_icon(64).to_png())
        self.assertEqual(icon[0][0][3], 0)  # Outside the tile.
        self.assertEqual(icon[32][32][3], 255)  # Inside the tile.


if __name__ == "__main__":
    unittest.main()
