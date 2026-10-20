"""Bluetooth keyboard control panel."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QSlider

from ...models import DeviceInfo, Telemetry
from ..widgets import MetricTile, make_button, make_pill
from .base import ControlPanel


class KeyboardPanel(ControlPanel):
    def _build(self) -> None:
        top = QHBoxLayout()
        top.setSpacing(13)
        light, light_body = self.card(
            "背光亮度", "调节键盘背光与灯效", ("需要厂商协议", "red"), add=False
        )
        row = QHBoxLayout()
        self.light_value = QLabel("%d%%" % int(self.device.metadata.get("backlight") or 65))
        self.light_value.setObjectName("PercentBig")
        self.light_value.setStyleSheet("color: #9fe6a5;")
        row.addWidget(self.light_value)
        row.addStretch(1)
        self.light_state = make_pill("未加载协议", "red")
        row.addWidget(self.light_state)
        light_body.addLayout(row)
        self.light_slider = QSlider(Qt.Horizontal)
        self.light_slider.setRange(0, 100)
        self.light_slider.setValue(int(self.device.metadata.get("backlight") or 65))
        self.light_slider.setEnabled(False)
        self.light_slider.valueChanged.connect(lambda value: self.light_value.setText("%d%%" % value))
        light_body.addWidget(self.light_slider)
        mode_row = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(["常亮", "呼吸", "涟漪", "星光", "关闭"])
        self.mode.setEnabled(False)
        mode_row.addWidget(self.mode, 1)
        self.apply = make_button("应用", "primary")
        self.apply.setEnabled(False)
        mode_row.addWidget(self.apply)
        light_body.addLayout(mode_row)
        top.addWidget(light, 2)

        self.battery = self.battery_card()
        self.battery.setMinimumWidth(205)
        top.addWidget(self.battery, 1)
        self.layout.addLayout(top)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self.signal_tile = MetricTile("信号强度", "—", "RSSI")
        self.layout_tile = MetricTile("布局", str(self.device.metadata.get("layout") or "—"), "ANSI / ISO")
        self.link_tile = MetricTile("连接状态", "未连接", "BLE HID")
        metrics.addWidget(self.signal_tile)
        metrics.addWidget(self.layout_tile)
        metrics.addWidget(self.link_tile)
        self.layout.addLayout(metrics)

        mapping, mapping_body = self.card(
            "按键映射", "把物理按键映射到功能或组合键", ("需要厂商协议", "red")
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        grid.addWidget(self._muted("物理按键"), 0, 0)
        grid.addWidget(self._muted("映射功能"), 0, 1)
        grid.addWidget(self._muted("状态"), 0, 2)
        rows = (
            ("F1 – F12", "媒体键 / 宏", "需要厂商配置工具"),
            ("Caps Lock", "Ctrl / Esc", "系统可重映射"),
            ("右侧 Alt", "Command / Win", "系统可重映射"),
            ("Fn 组合键", "亮度 / 音量", "固件层控制"),
        )
        for index, (key, action, state) in enumerate(rows, start=1):
            grid.addWidget(QLabel(key), index, 0)
            value = QLabel(action)
            value.setStyleSheet("color: #aebed6;")
            grid.addWidget(value, index, 1)
            status = QLabel(state)
            status.setObjectName("Faint")
            grid.addWidget(status, index, 2)
        mapping_body.addLayout(grid)

        self.notice(
            "背光与按键映射依赖厂商 HID/GATT 协议",
            "标准 BLE HID 只定义输入报告，不定义背光或按键重映射。"
            "Blueprint 层已预留 set_backlight() / set_key_mapping() 接口；"
            "接入厂商协议后可替换为真实读写。",
        )

    @staticmethod
    def _muted(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Faint")
        return label

    def refresh(self) -> None:
        self.signal_tile.set_value(
            "%d dBm" % self.device.rssi if self.device.rssi is not None else "—",
            "信号强度",
        )
        self.link_tile.set_value(self.device.state.label, self.device.transport.label)
        self.refresh_battery()
