"""Main application window."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..controller import AppController
from ..models import DeviceInfo
from ..settings import app_data_dir
from .. import __version__
from .device_detail import DeviceDetail
from .device_list import Sidebar
from .icons import make_app_icon
from .theme import ACCENT, MUTED, apply_theme
from .widgets import EmptyState, StatusDot, make_button, make_pill


class MainWindow(QMainWindow):
    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._shutdown_done = False
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._reset_status)

        self.setWindowTitle("BlueDesk · 蓝牙设备管理与控制")
        self.setWindowIcon(QIcon(make_app_icon(256)))
        self.resize(1240, 820)
        self.setMinimumSize(980, 680)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_topbar())

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(14, 12, 14, 10)
        body_layout.setSpacing(11)
        self.sidebar = Sidebar()
        self.detail = DeviceDetail(controller)
        self.empty = EmptyState()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.detail)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([370, 845])
        body_layout.addWidget(splitter, 1)
        layout.addWidget(body, 1)

        self._build_statusbar()
        self._wire()
        self._refresh_devices()
        selected = self.controller.selected
        if selected:
            self._on_selection(selected)
        else:
            self.stack.setCurrentWidget(self.empty)
        QTimer.singleShot(2300, self.controller.select_default_if_available)
        QTimer.singleShot(2600, self._demo_tick)
        self._demo_timer = QTimer(self)
        self._demo_timer.setInterval(4500)
        self._demo_timer.timeout.connect(self._demo_tick)
        self._demo_timer.start()

        geometry = self.controller.settings.window_geometry
        if geometry:
            try:
                self.restoreGeometry(base64.b64decode(geometry.encode("ascii")))
            except Exception:
                pass
        self._update_scan_ui(False, "准备就绪")
        if self.controller.demo_mode:
            self.demo_pill.setVisible(True)
            self.demo_btn.setVisible(False)
            self.sidebar.set_demo_visible(True)

    # ------------------------------------------------------------------
    def _build_topbar(self) -> QWidget:
        top = QFrame()
        top.setObjectName("TopBar")
        top.setFixedHeight(72)
        layout = QHBoxLayout(top)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(11)

        logo = QLabel()
        logo.setPixmap(make_app_icon(42))
        logo.setFixedSize(42, 42)
        layout.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        app_title = QLabel("BlueDesk")
        app_title.setObjectName("AppTitle")
        subtitle = QLabel("蓝牙设备管理与控制台")
        subtitle.setObjectName("AppSubtitle")
        titles.addWidget(app_title)
        titles.addWidget(subtitle)
        layout.addLayout(titles)
        layout.addSpacing(14)

        self.demo_pill = make_pill("演示模式", "amber")
        self.demo_pill.setVisible(False)
        layout.addWidget(self.demo_pill)
        self.platform_pill = make_pill(self.controller.platform_summary(), "blue")
        self.platform_pill.setToolTip(self.controller.platform.permission_hint())
        layout.addWidget(self.platform_pill)
        layout.addStretch(1)

        self.scan_dot = StatusDot()
        layout.addWidget(self.scan_dot)
        self.scan_status = QLabel("准备就绪")
        self.scan_status.setObjectName("Faint")
        self.scan_status.setMinimumWidth(130)
        layout.addWidget(self.scan_status)

        self.scan_btn = make_button("扫描设备", "primary")
        self.scan_btn.setMinimumWidth(96)
        self.scan_btn.clicked.connect(self.controller.toggle_scan)
        layout.addWidget(self.scan_btn)
        self.demo_btn = make_button("演示数据", "ghost")
        self.demo_btn.setToolTip("加载模拟设备，不需要蓝牙权限")
        self.demo_btn.clicked.connect(self._load_demo)
        layout.addWidget(self.demo_btn)
        self.settings_btn = QPushButton("系统蓝牙")
        self.settings_btn.setProperty("variant", "ghost")
        self.settings_btn.clicked.connect(self.controller.open_bluetooth_settings)
        layout.addWidget(self.settings_btn)
        return top

    def _build_statusbar(self) -> None:
        bar = QStatusBar()
        bar.setSizeGripEnabled(False)
        self.status_label = QLabel("BlueDesk 已就绪")
        self.status_label.setObjectName("Faint")
        bar.addWidget(self.status_label, 1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Faint")
        bar.addPermanentWidget(self.count_label)
        version = QLabel("v%s · %s" % (__version__, self.controller.platform.system))
        version.setObjectName("Faint")
        bar.addPermanentWidget(version)
        self.setStatusBar(bar)

    # ------------------------------------------------------------------
    def _wire(self) -> None:
        self.sidebar.selection_changed.connect(self.controller.select)
        self.sidebar.connect_requested.connect(self._quick_connect)
        self.sidebar.filters_changed.connect(self._schedule_refresh)
        self.sidebar.scan_toggle_requested.connect(self.controller.toggle_scan)
        self.sidebar.demo_requested.connect(self._load_demo)
        self.empty.scan_requested.connect(self.controller.start_scan)
        self.empty.demo_requested.connect(self._load_demo)

        self.controller.devices_changed.connect(self._schedule_refresh)
        self.controller.device_updated.connect(self._device_updated)
        self.controller.selection_changed.connect(self._on_selection)
        self.controller.scan_state_changed.connect(self._update_scan_ui)
        self.controller.telemetry_changed.connect(self._telemetry_changed)
        self.controller.services_changed.connect(self._services_changed)
        self.controller.log_entry.connect(self.detail.log.add_entry)
        self.controller.status_message.connect(self._show_status)
        self.controller.operation_finished.connect(self._operation_finished)
        self.controller.volume_changed.connect(lambda _value: None)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(180)
        self._refresh_timer.timeout.connect(self._refresh_devices)

        QShortcut(QKeySequence("Ctrl+R"), self, activated=self.controller.toggle_scan)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.sidebar.search.setFocus)
        QShortcut(QKeySequence("Ctrl+D"), self, activated=self._load_demo)
        QShortcut(QKeySequence("Esc"), self, activated=self.controller.stop_scan)

    # ------------------------------------------------------------------
    def _schedule_refresh(self) -> None:
        self._refresh_timer.start()

    def _refresh_devices(self) -> None:
        devices = self.controller.filtered_devices(
            mode=self.sidebar.mode(),
            query=self.sidebar.query(),
            device_type=self.sidebar.device_type(),
        )
        selected = self.controller.selected
        self.sidebar.set_devices(devices, selected.key if selected else "")
        all_devices = self.controller.devices()
        connected = len([d for d in all_devices if d.connected])
        self.count_label.setText("设备 %d · 已连接 %d · 平台 %s" % (len(all_devices), connected, self.controller.platform.system))
        if selected is None and all_devices:
            self.stack.setCurrentWidget(self.empty)
        elif selected is not None:
            self.stack.setCurrentWidget(self.detail)
        else:
            self.stack.setCurrentWidget(self.empty)

    def _device_updated(self, device: DeviceInfo) -> None:
        selected = self.controller.selected
        if selected and device.address == selected.address:
            self.detail.refresh()
        self._schedule_refresh()

    def _on_selection(self, device: Optional[DeviceInfo]) -> None:
        if device is None:
            self.stack.setCurrentWidget(self.empty)
            return
        self.stack.setCurrentWidget(self.detail)
        self.detail.show_device(device)
        self.sidebar.set_selected(device.key)
        self.detail.tabs.setCurrentIndex(0)

    def _telemetry_changed(self, address: str, telemetry) -> None:
        self.detail.refresh_telemetry(address)

    def _services_changed(self, address: str, services) -> None:
        self.detail.refresh_services(address)

    def _update_scan_ui(self, active: bool, message: str) -> None:
        self.scan_dot.set_active(active)
        self.scan_status.setText(message or ("正在扫描附近设备…" if active else "准备就绪"))
        self.scan_btn.setText("停止扫描" if active else "扫描设备")
        self.scan_btn.setProperty("variant", "danger" if active else "primary")
        self.scan_btn.style().unpolish(self.scan_btn)
        self.scan_btn.style().polish(self.scan_btn)
        self.sidebar.set_scanning(active, message)

    def _show_status(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #a9c6ff;")
        self._status_timer.start(6000)

    def _reset_status(self) -> None:
        self.status_label.setText("BlueDesk 已就绪")
        self.status_label.setStyleSheet("")

    def _operation_finished(self, message: str, ok: bool) -> None:
        self._show_status(message)

    def _quick_connect(self, address: str) -> None:
        self.controller.select(address)
        self.controller.toggle_connection(address)

    def _load_demo(self) -> None:
        self.controller.load_demo_devices(auto_connect=True)
        self.demo_pill.setVisible(True)
        self.demo_btn.setVisible(False)
        self.sidebar.set_demo_visible(True)
        self._show_status("演示数据已加载")
        QTimer.singleShot(800, self._demo_tick)

    def _demo_tick(self) -> None:
        if not self.controller.demo_mode:
            return
        self.controller.simulate_rssi()
        if self.controller.selected:
            self.detail.refresh()

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        self.prepare_shutdown()
        super().closeEvent(event)

    def prepare_shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        try:
            geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
            self.controller.settings.window_geometry = geometry
            self.controller.settings_store.save()
        except Exception:
            pass
        self.controller.shutdown()
