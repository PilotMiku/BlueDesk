"""Export the QPainter app icon as PNG/ICO/ICNS for packaging."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

from bluedesk.ui.icons import make_app_icon


def main() -> int:
    app = QApplication([])
    root = Path(__file__).resolve().parent.parent
    assets = root / "assets"
    assets.mkdir(exist_ok=True)

    png_path = assets / "BlueDesk.png"
    make_app_icon(1024).save(str(png_path))

    ico_path = assets / "BlueDesk.ico"
    Image.open(png_path).save(ico_path, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])

    if shutil.which("iconutil"):
        iconset = assets / "BlueDesk.iconset"
        iconset.mkdir(exist_ok=True)
        image = Image.open(png_path)
        for size, name in (
            (16, "icon_16x16.png"),
            (32, "icon_16x16@2x.png"),
            (32, "icon_32x32.png"),
            (64, "icon_32x32@2x.png"),
            (128, "icon_128x128.png"),
            (256, "icon_128x128@2x.png"),
            (256, "icon_256x256.png"),
            (512, "icon_256x256@2x.png"),
            (512, "icon_512x512.png"),
            (1024, "icon_512x512@2x.png"),
        ):
            image.resize((size, size), Image.LANCZOS).save(iconset / name)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(assets / "BlueDesk.icns")], check=True)
        shutil.rmtree(iconset)

    print("icons written to", assets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
