"""BlueDesk application entry point."""
from __future__ import annotations

import argparse
import os
import signal
import sys
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import __app_title__, __version__
from .controller import AppController
from .ui.icons import make_app_icon
from .ui.main_window import MainWindow
from .ui.theme import apply_theme


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="BlueDesk Bluetooth device manager")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="load simulated devices (no Bluetooth permission required)")
    mode.add_argument("--real", action="store_true", help="use real Bluetooth devices (the default)")
    parser.add_argument("--no-scan", action="store_true", help="do not start BLE scan automatically")
    parser.add_argument("--screenshot", metavar="PATH", help="render the UI to PATH and exit (demo unless --real)")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.version:
        print("BlueDesk %s" % __version__)
        return 0

    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication([sys.argv[0]])
    app.setApplicationName("BlueDesk")
    app.setApplicationDisplayName(__app_title__)
    app.setOrganizationName("BlueDesk")
    app.setWindowIcon(QIcon(make_app_icon(256)))
    apply_theme(app)

    demo = args.demo or (bool(args.screenshot) and not args.real)
    controller = AppController(demo_mode=demo, auto_scan=(not args.no_scan and not demo))

    def handle_exception(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            controller.log("ERROR", "未捕获异常：%s" % text, category="app")
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = handle_exception

    window = MainWindow(controller)
    window.show()
    app.aboutToQuit.connect(window.prepare_shutdown)

    if args.screenshot:
        target = os.path.abspath(args.screenshot)

        def capture() -> None:
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            window.grab().save(target)
            print("screenshot:", target)
            window.close()
            app.quit()

        QTimer.singleShot(3400, capture)

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
