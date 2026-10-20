"""Device detail header, dynamic control panel and tabs."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..controller import AppController
from ..models import ConnectionState, DeviceInfo, DeviceType, Telemetry, rssi_to_bars
from .gatt_browser import GattBrowser
from .icons import DeviceGlyph
from .log_panel import LogPanel
from .panels.base import ControlPanel
from .panels.factory import create_panel
from .theme import ACCENT, GREEN, MUTED, RED
from .widgets import (
    Card,
    MetricTile,
    RssiBars,
    TagRow,
    clear_layout,
    make_button,
    make_pill,
    repolish,
)


class DeviceDetail(QWidget):
    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.device: Optional[DeviceInfo] = None
        self._panel: Optional[ControlPanel] = None
        self._panel_key = ""
        self._panel_type: Optional[DeviceType] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(11)

        self.header_card = Card()
        header = QHBoxLayout()
        header.setSpacing(14)
        self.glyph = DeviceGlyph(DeviceType.UNKNOWN, 64)
        header.addWidget(self.glyph, 0, Qt.AlignTop)

        identity = QVBoxLayout()
        identity.setSpacing(4)
        self.name = QLabel("设备")
        self.name.setObjectName("HeroTitle")
        self.name.setWordWrap(False)
        identity.addWidget(self.name)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Muted")
        identity.addWidget(self.subtitle)
        self.tags = TagRow()
        identity.addWidget(self.tags)
        header.addLayout(identity, 1)

        actions = QVBoxLayout()
        actions.setSpacing(6)
        top_actions = QHBoxLayout()
        top_actions.setSpacing(6)
        self.connect_btn = make_button("连接", "primary")
        self.connect_btn.setMinimumWidth(88)
        self.connect_btn.clicked.connect(self._toggle_connection)
        top_actions.addWidget(self.connect_btn)
        self.default_btn = make_button("设为默认", "ghost")
        self.default_btn.clicked.connect(self._set_default)
        top_actions.addWidget(self.default_btn)
        self.more_btn = QPushButton("⋯")
        self.more_btn.setProperty("variant", "ghost")
        self.more_btn.setFixedWidth(38)
        self.more_btn.setToolTip("更多操作")
        self.more_btn.clicked.connect(self._show_menu)
        top_actions.addWidget(self.more_btn)
        actions.addLayout(top_actions)
        secondary = QHBoxLayout()
        secondary.setSpacing(6)
        self.rename_btn = make_button("重命名", "ghost")
        self.rename_btn.clicked.connect(self._rename)
        self.settings_btn = make_button("系统设置", "ghost")
        self.settings_btn.clicked.connect(self.controller.open_bluetooth_settings)
        secondary.addWidget(self.rename_btn)
        secondary.addWidget(self.settings_btn)
        actions.addLayout(secondary)
        header.addLayout(actions, 0)
        self.header_card.layout.addLayout(header)

        metrics = QHBoxLayout()
        metrics.setSpacing(8)
        self.rssi_tile = MetricTile("信号强度", "—", "RSSI")
        self.battery_tile = MetricTile("设备电量", "—", "Battery Service")
        self.confidence_tile = MetricTile("识别置信度", "—", "类型规则")
        self.services_tile = MetricTile("GATT 服务", "—", "连接后发现")
        for tile in (self.rssi_tile, self.battery_tile, self.confidence_tile, self.services_tile):
            tile.setStyleSheet("QFrame#SubCard { border-radius: 10px; }")
            metrics.addWidget(tile)
        self.header_card.layout.addLayout(metrics)
        layout.addWidget(self.header_card)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        layout.addWidget(self.tabs, 1)

        self.panel_scroll = QScrollArea()
        self.panel_scroll.setWidgetResizable(True)
        self.panel_scroll.setFrameShape(QFrame.NoFrame)
        self.panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.panel_host = QWidget()
        self.panel_layout = QVBoxLayout(self.panel_host)
        self.panel_layout.setContentsMargins(13, 13, 13, 4)
        self.panel_layout.setSpacing(0)
        self.panel_scroll.setWidget(self.panel_host)
        self.tabs.addTab(self.panel_scroll, "控制面板")

        self.gatt = GattBrowser(controller)
        self.tabs.addTab(self.gatt, "GATT 服务")
        self.log = LogPanel(controller)
        self.tabs.addTab(self.log, "通信日志")
        self.tabs.currentChanged.connect(self._tab_changed)

    # ------------------------------------------------------------------
    def show_device(self, device: DeviceInfo) -> None:
        address_changed = self.device is None or self.device.address != device.address
        self.device = device
        self.glyph.set_device_type(device.device_type)
        self.name.setText(device.display_name)
        self.name.setToolTip(device.display_name)
        self.subtitle.setText(
            "%s  ·  %s  ·  %s"
            % (device.device_type.label, device.transport.label, device.short_address)
        )
        tags = []
        if device.connected:
            tags.append(("已连接", "green"))
        elif device.state is ConnectionState.CONNECTING:
            tags.append(("连接中", "amber"))
        elif device.state is ConnectionState.FAILED:
            tags.append(("连接失败", "red"))
        else:
            tags.append(("未连接", ""))
        if device.paired:
            tags.append(("已配对", "blue"))
        if self.controller.is_default(device.address):
            tags.append(("默认设备", "amber"))
        if device.rssi is not None:
            tags.append(("%d dBm" % device.rssi, "blue"))
        if device.device_type is DeviceType.WEARABLE:
            tags.append(("可穿戴", "pink"))
        self.tags.set_tags(tags)
        self._refresh_actions()
        self._refresh_metrics()
        self._ensure_panel(device, address_changed)
        self.gatt.set_device(device, self.controller.services_for(device.address))
        self._update_services_tile()

    def refresh(self) -> None:
        if self.device is None:
            return
        device = self.controller.device(self.device.address)
        if device is None:
            return
        self.device = device
        self.glyph.set_device_type(device.device_type)
        self.name.setText(device.display_name)
        tags = []
        if device.connected:
            tags.append(("已连接", "green"))
        elif device.state is ConnectionState.CONNECTING:
            tags.append(("连接中", "amber"))
        elif device.state is ConnectionState.FAILED:
            tags.append(("连接失败", "red"))
        else:
            tags.append(("未连接", ""))
        if device.paired:
            tags.append(("已配对", "blue"))
        if self.controller.is_default(device.address):
            tags.append(("默认设备", "amber"))
        if device.rssi is not None:
            tags.append(("%d dBm" % device.rssi, "blue"))
        self.tags.set_tags(tags)
        self._refresh_actions()
        self._refresh_metrics()
        if self._panel is not None:
            self._panel.update_device(device, self.controller.telemetry_for(device.address))
        self.gatt.set_device(device, self.controller.services_for(device.address))
        self._update_services_tile()

    def refresh_telemetry(self, address: str) -> None:
        if self.device and address == self.device.address:
            self._refresh_metrics()
            if self._panel:
                self._panel.update_device(self.device, self.controller.telemetry_for(address))

    def refresh_services(self, address: str) -> None:
        if self.device and address == self.device.address:
            self.gatt.set_device(self.device, self.controller.services_for(address))
            self._update_services_tile()

    # ------------------------------------------------------------------
    def _ensure_panel(self, device: DeviceInfo, force: bool = False) -> None:
        key = device.address
        if not force and self._panel is not None and key == self._panel_key and device.device_type is self._panel_type:
            self._panel.update_device(device, self.controller.telemetry_for(device.address))
            return
        if self._panel is not None:
            self._panel.deleteLater()
        self._panel_key = key
        self._panel_type = device.device_type
        self._panel = create_panel(self.controller, device)
        self._panel.tab_requested.connect(self._switch_tab)
        clear_layout(self.panel_layout)
        self.panel_layout.addWidget(self._panel)
        self.panel_layout.addStretch(1)
        self._panel.update_device(device, self.controller.telemetry_for(device.address))

    def _switch_tab(self, name: str) -> None:
        index = {"control": 0, "gatt": 1, "logs": 2}.get(name, 0)
        self.tabs.setCurrentIndex(index)

    def _tab_changed(self, index: int) -> None:
        if index == 1 and self.device:
            self.gatt.set_device(self.device, self.controller.services_for(self.device.address))
        if index == 2:
            self.log._rebuild()

    def _refresh_actions(self) -> None:
        if not self.device:
            return
        if self.device.state is ConnectionState.DISCONNECTING:
            self.connect_btn.setText("断开中…")
            self.connect_btn.setProperty("variant", "ghost")
        elif self.device.connected:
            self.connect_btn.setText("断开连接")
            self.connect_btn.setProperty("variant", "danger")
        elif self.device.state is ConnectionState.CONNECTING:
            self.connect_btn.setText("连接中…")
            self.connect_btn.setProperty("variant", "ghost")
        elif self.device.state is ConnectionState.FAILED:
            self.connect_btn.setText("重新连接")
            self.connect_btn.setProperty("variant", "primary")
        else:
            self.connect_btn.setText("连接设备")
            self.connect_btn.setProperty("variant", "primary")
        self.connect_btn.setEnabled(self.device.state not in (ConnectionState.CONNECTING, ConnectionState.DISCONNECTING))
        repolish(self.connect_btn)
        is_default = self.controller.is_default(self.device.address)
        self.default_btn.setText("已设默认" if is_default else "设为默认")
        self.default_btn.setEnabled(not is_default)
        self.rename_btn.setEnabled(self.device.is_ble or self.device.device_type.group == "audio")

    def _refresh_metrics(self) -> None:
        if not self.device:
            return
        device = self.device
        quality = {4: "极佳", 3: "良好", 2: "一般", 1: "较弱", 0: "未知"}[
            rssi_to_bars(device.rssi)
        ]
        self.rssi_tile.set_value(
            "%d dBm" % device.rssi if device.rssi is not None else "—",
            quality,
        )
        telemetry = self.controller.telemetry_for(device.address)
        battery = telemetry.battery if telemetry else device.metadata.get("battery")
        source = telemetry.extra.get("battery_source", "标准 GATT / 厂商") if telemetry else "等待设备报告"
        self.battery_tile.set_value("%d%%" % int(battery) if battery is not None else "—", source)
        self.confidence_tile.set_value("%.0f%%" % (device.confidence * 100), device.classification_source or "fallback")
        self._update_services_tile()

    def _update_services_tile(self) -> None:
        if not self.device:
            return
        count = len(self.controller.services_for(self.device.address))
        self.services_tile.set_value(str(count) if count else "—", "连接后发现")

    # ------------------------------------------------------------------
    def _toggle_connection(self) -> None:
        if self.device:
            self.controller.toggle_connection(self.device.address)

    def _set_default(self) -> None:
        if self.device:
            self.controller.set_default_device(self.device.address)
            self.refresh()

    def _rename(self) -> None:
        if not self.device:
            return
        new_name, ok = QInputDialog.getText(
            self,
            "重命名设备",
            "新名称：",
            text=self.device.display_name,
        )
        if ok and new_name.strip():
            self.controller.rename_device(self.device.address, new_name)

    def _show_menu(self) -> None:
        if not self.device:
            return
        menu = QMenu(self)
        menu.addAction("打开系统蓝牙设置", self.controller.open_bluetooth_settings)
        menu.addAction("打开声音设置", self.controller.open_sound_settings)
        menu.addAction("刷新遥测", lambda: self.controller.refresh_telemetry(self.device.address))
        menu.addAction("复制设备地址", self._copy_address)
        menu.addSeparator()
        menu.addAction("打开 GATT 浏览器", lambda: self._switch_tab("gatt"))
        menu.addAction("打开通信日志", lambda: self._switch_tab("logs"))
        menu.exec(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))

    def _copy_address(self) -> None:
        from PySide6.QtWidgets import QApplication

        if self.device:
            QApplication.clipboard().setText(self.device.address)
            self.controller.status_message.emit("设备地址已复制")
