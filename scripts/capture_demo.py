"""Render demo screenshots for documentation and visual regression."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bluedesk.controller import AppController
from bluedesk.ui.main_window import MainWindow
from bluedesk.ui.theme import apply_theme


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="docs/screenshots")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    app = QApplication([])
    apply_theme(app)
    controller = AppController(demo_mode=True, auto_scan=False)
    window = MainWindow(controller)
    window.show()
    QTest.qWait(1500)
    window.grab().save(str(out / "overview.png"))

    for address, name in (
        ("demo:wh1000xm5", "audio"),
        ("demo:mxmaster3s", "mouse"),
        ("demo:mxkeys", "keyboard"),
        ("demo:miband8", "wearable"),
        ("demo:unknown", "generic"),
    ):
        controller.select(address)
        QTest.qWait(300)
        window.grab().save(str(out / (name + ".png")))

    controller.select("demo:miband8")
    QTest.qWait(250)
    window.detail.tabs.setCurrentIndex(1)
    QTest.qWait(350)
    battery_item = window.detail.gatt.tree.topLevelItem(2)
    if battery_item is not None and battery_item.childCount():
        window.detail.gatt.tree.setCurrentItem(battery_item.child(0))
        window.detail.gatt.read_btn.click()
        QTest.qWait(250)
    window.grab().save(str(out / "gatt.png"))

    window.detail.tabs.setCurrentIndex(2)
    QTest.qWait(250)
    window.grab().save(str(out / "logs.png"))

    window.prepare_shutdown()
    print("screenshots written to", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
