"""Read real Bluetooth devices and scan briefly without connecting to any device."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from bluedesk.controller import AppController
from bluedesk.ui.main_window import MainWindow
from bluedesk.ui.theme import apply_theme


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=12, help="scan duration, 1 to 60 seconds")
    parser.add_argument("--screenshot", type=Path, help="save the real device UI to this PNG")
    args = parser.parse_args()
    if not 1 <= args.seconds <= 60:
        parser.error("--seconds must be between 1 and 60")

    app = QApplication([])
    apply_theme(app)
    controller = AppController(demo_mode=False, auto_scan=False)
    window = MainWindow(controller)
    window.show()
    discovered = set()
    errors = []
    controller.scan_service.device_found.connect(lambda device: discovered.add(device.address))
    controller.scan_service.error.connect(errors.append)
    print("正在读取真实配对设备并扫描附近 BLE 设备；如弹出蓝牙权限提示，请允许。", flush=True)

    def finish():
        if args.screenshot:
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(args.screenshot))
        print(json.dumps({
            "mode": "real",
            "paired_count": sum(d.paired for d in controller.devices()),
            "nearby_ble_count": len(discovered),
            "device_count": len(controller.devices()),
            "unnamed_count": sum(not d.name for d in controller.devices()),
            "devices": [{
                "name": d.display_name, "connected": d.connected,
                "battery": controller.telemetry_for(d.address).battery
                if controller.telemetry_for(d.address) else None,
            } for d in controller.devices() if d.paired or d.name][:20],
            "scan_errors": errors,
        }, ensure_ascii=False, indent=2), flush=True)
        window.close()
        app.quit()

    QTimer.singleShot(200, controller.start_scan)
    QTimer.singleShot(args.seconds * 1000, finish)
    app.exec()
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
