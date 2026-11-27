"""Draw the app icon and save it as Mac File Manager.app/Contents/Resources/AppIcon.icns.

Run from the repository root: python3 tools/make_icon.py (needs macOS for iconutil).
"""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mac_file_manager.ui.images import app_icon  # noqa: E402

OUTPUT = ROOT / "Mac File Manager.app" / "Contents" / "Resources" / "AppIcon.icns"
SIZES = (16, 32, 128, 256, 512)


def main() -> None:
    rendered = {}
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "AppIcon.iconset"
        iconset.mkdir()
        for size in SIZES:
            for scale in (1, 2):
                pixels = size * scale
                if pixels not in rendered:
                    print(f"Drawing {pixels}×{pixels}…", flush=True)
                    rendered[pixels] = app_icon(pixels).to_png()
                suffix = "" if scale == 1 else "@2x"
                (iconset / f"icon_{size}x{size}{suffix}.png").write_bytes(rendered[pixels])
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(OUTPUT)], check=True)
    print(f"Saved {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
