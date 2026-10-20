"""Bluetooth mouse control panel."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QGridLayout, QHBoxLayout, QPushButton, QVBoxLayout

from ..widgets import PlainLabel as QLabel
from ...codecs import build_dpi_packet
from ...models import DeviceInfo, Telemetry
from ..widgets import Card, MetricTile, make_button, make_pill, repolish
from .base import ControlPanel


class MousePanel(ControlPanel):
    def _build(self) -> None:
        self._dpi = int(self.device.metadata.get("dpi") or 1600)
        self._selected_dpi = self._dpi

        top = QHBoxLayout()
        top.setSpacing(13)
        dpi_card, dpi_body = self.card(
            "DPI 档位", "修改指针灵敏度", ("需要厂商协议", "red"), add=False
        )
        current_row = QHBoxLayout()
        self.dpi_value = QLabel(str(self._dpi))
        self.dpi_value.setObjectName("PercentBig")
        self.dpi_value.setStyleSheet("color: #c7b6ff;")
        current_row.addWidget(self.dpi_value)
        current_row.addWidget(QLabel("DPI"))
        current_row.addStretch(1)
        self.protocol_state = make_pill("未加载协议", "red")
        current_row.addWidget(self.protocol_state)
        dpi_body.addLayout(current_row)
        self.dpi_group = QButtonGroup(self)
        self.dpi_group.setExclusive(True)
        dpi_row = QHBoxLayout()
        dpi_row.setSpacing(7)
        for index, value in enumerate((400, 800, 1600, 3200)):
            button = QPushButton(str(value))
            button.setProperty("variant", "dpi")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setChecked(value == self._dpi)
            self.dpi_group.addButton(button, index)
            button.clicked.connect(lambda _checked=False, dpi=value: self._choose_dpi(dpi))
            dpi_row.addWidget(button)
        dpi_body.addLayout(dpi_row)
        apply_row = QHBoxLayout()
        self.apply_dpi = make_button("应用 DPI", "primary")
        self.apply_dpi.clicked.connect(self._apply_dpi)
        self.apply_dpi.setEnabled(bool(self.device.metadata.get("demo") or self.device.metadata.get("vendor_protocol")))
        apply_row.addWidget(self.apply_dpi)
        profile = QLabel("配置档 %s" % self.device.metadata.get("profile", 1))
        profile.setObjectName("Faint")
        apply_row.addWidget(profile)
        apply_row.addStretch(1)
        dpi_body.addLayout(apply_row)
        top.addWidget(dpi_card, 2)

        self.battery = self.battery_card()
        self.battery.setMinimumWidth(205)
        top.addWidget(self.battery, 1)
        self.layout.addLayout(top)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self.signal_tile = MetricTile("信号强度", "—", "RSSI")
        self.poll_tile = MetricTile(
            "轮询率",
            "%s Hz" % (self.device.metadata.get("polling_rate") or "—"),
            "厂商 HID 报告只读",
        )
        self.link_tile = MetricTile("连接状态", "未连接", "BLE HID")
        metrics.addWidget(self.signal_tile)
        metrics.addWidget(self.poll_tile)
        metrics.addWidget(self.link_tile)
        self.layout.addLayout(metrics)

        mapping, mapping_body = self.card(
            "按键功能配置", "将鼠标按键映射到常用动作", ("需要厂商协议", "red")
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(7)
        grid.addWidget(self._muted_label("按键"), 0, 0)
        grid.addWidget(self._muted_label("当前功能"), 0, 1)
        grid.addWidget(self._muted_label("可配置动作"), 0, 2)
        rows = (
            ("左键", "主点击", "默认 / 双击 / 宏"),
            ("右键", "辅助点击", "默认 / 返回 / 宏"),
            ("中键", "中键点击", "默认 / 粘贴 / 宏"),
            ("侧键 ×2", "前进 / 后退", "默认 / 音量 / 媒体"),
            ("滚轮", "垂直滚动", "默认 / 水平滚动 / 缩放"),
        )
        for index, (key, current, actions) in enumerate(rows, start=1):
            grid.addWidget(QLabel(key), index, 0)
            value = QLabel(current)
            value.setStyleSheet("color: #aebed6;")
            grid.addWidget(value, index, 1)
            action = QLabel(actions)
            action.setObjectName("Faint")
            grid.addWidget(action, index, 2)
        mapping_body.addLayout(grid)

        self.notice(
            "标准 BLE HID 不提供 DPI / 轮询率配置",
            "鼠标厂商通常通过 HID++（Logitech）、私有 HID Report 或厂商 GATT 服务读写配置。"
            "BlueDesk 已提供协议适配器接口和示例 DPI 数据帧，但默认不会向未知设备发送写指令，"
            "以免误改设置。",
        )

    @staticmethod
    def _muted_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Faint")
        return label

    def _choose_dpi(self, dpi: int) -> None:
        self._selected_dpi = dpi
        self.dpi_value.setText(str(dpi))

    def _apply_dpi(self) -> None:
        if self.device.metadata.get("demo"):
            self._dpi = self._selected_dpi
            self.device.metadata["dpi"] = self._dpi
            self.controller.log(
                "INFO",
                "演示模式：DPI 切换为 %d（未发送真实指令）" % self._dpi,
                address=self.device.address,
                category="vendor",
            )
            self.controller.status_message.emit("演示模式：DPI 已切换为 %d" % self._dpi)
            return
        if not self.device.metadata.get("vendor_protocol"):
            self.controller.status_message.emit("未加载该鼠标的厂商协议，无法应用 DPI")
            return
        try:
            packet = build_dpi_packet(self._selected_dpi, int(self.device.metadata.get("profile", 1)))
        except Exception as exc:
            self.controller.status_message.emit(str(exc))
            return
        self.controller.write_characteristic(
            self.device.address,
            "0000ffe1-0000-1000-8000-00805f9b34fb",
            packet,
        )

    def refresh(self) -> None:
        self.signal_tile.set_value(
            "%d dBm" % self.device.rssi if self.device.rssi is not None else "—",
            "信号强度",
        )
        self.link_tile.set_value(self.device.state.label, self.device.transport.label)
        if self.device.metadata.get("demo") or self.device.metadata.get("vendor_protocol"):
            self.protocol_state.setText("演示协议" if self.device.metadata.get("demo") else "已加载协议")
            self.protocol_state.setProperty("tone", "green")
            repolish(self.protocol_state)
        self.refresh_battery()
        current = self.device.metadata.get("dpi")
        if current:
            self.dpi_value.setText(str(current))
