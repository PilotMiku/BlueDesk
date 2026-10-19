from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bluedeck.controller import AppController
from bluedeck.ui.main_window import MainWindow
from bluedeck.ui.theme import apply_theme


def test_demo_ui_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("BLUEDESK_DATA_DIR", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    controller = AppController(demo_mode=True, auto_scan=False)
    window = MainWindow(controller)
    window.show()
    QTest.qWait(1300)
    assert len(controller.devices()) == 8
    assert controller.selected is not None
    for address in ("demo:wh1000xm5", "demo:mxmaster3s", "demo:mxkeys", "demo:miband8", "demo:unknown"):
        controller.select(address)
        QTest.qWait(80)
        assert window.detail.device is not None
        assert window.detail.device.address == address
    window.detail.tabs.setCurrentIndex(1)
    QTest.qWait(80)
    assert window.detail.gatt.tree.topLevelItemCount() > 0
    window.detail.tabs.setCurrentIndex(2)
    QTest.qWait(80)
    assert window.detail.log.count_pill.text().endswith("条")
    window.prepare_shutdown()
