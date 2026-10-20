"""Smart watch / band panel."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from ..widgets import PlainLabel as QLabel
from ...models import DeviceInfo, Telemetry
from ..theme import AMBER, GREEN, MUTED, PINK
from ..widgets import Card, MetricTile, StatusDot, make_button
from .base import ControlPanel


class WearablePanel(ControlPanel):
    def _build(self) -> None:
        top = QHBoxLayout()
        top.setSpacing(13)
        self.battery = self.battery_card()
        self.battery.setMinimumWidth(190)
        top.addWidget(self.battery, 1)

        heart, heart_body = self.card("实时心率", "Heart Rate Measurement 0x2A37", ("标准 GATT", "green"), add=False)
        row = QHBoxLayout()
        self.heart_value = QLabel("—")
        self.heart_value.setObjectName("PercentBig")
        self.heart_value.setStyleSheet("color: #ff9fba;")
        row.addWidget(self.heart_value)
        unit = QLabel("bpm")
        unit.setObjectName("Muted")
        row.addWidget(unit, 0, Qt.AlignBottom)
        row.addStretch(1)
        self.heart_dot = StatusDot()
        self.heart_dot.set_active(False)
        row.addWidget(self.heart_dot)
        heart_body.addLayout(row)
        self.heart_hint = QLabel("连接并订阅后更新")
        self.heart_hint.setObjectName("Faint")
        heart_body.addWidget(self.heart_hint)
        top.addWidget(heart, 1)

        steps, steps_body = self.card("今日步数", "厂商健康服务", ("需要厂商协议", "red"), add=False)
        self.steps_value = QLabel("—")
        self.steps_value.setObjectName("PercentBig")
        self.steps_value.setStyleSheet("color: #9bceff;")
        steps_body.addWidget(self.steps_value)
        self.steps_hint = QLabel("连接后同步")
        self.steps_hint.setObjectName("Faint")
        steps_body.addWidget(self.steps_hint)
        top.addWidget(steps, 1)
        self.layout.addLayout(top)

        firmware, firmware_body = self.card("设备与固件", "Device Information Service 0x180A")
        self.model_row = kv_row("型号", "—")
        self.firmware_row = kv_row("固件版本", "—")
        self.serial_row = kv_row("序列号", "—")
        self.manufacturer_row = kv_row("制造商", "—")
        for row_widget in (self.model_row, self.firmware_row, self.serial_row, self.manufacturer_row):
            firmware_body.addWidget(row_widget)
        actions = QHBoxLayout()
        sync = make_button("同步数据", "primary")
        sync.clicked.connect(lambda: self.controller.refresh_telemetry(self.device.address))
        gatt = make_button("查看 GATT 服务", "ghost")
        gatt.clicked.connect(lambda: self.tab_requested.emit("gatt"))
        actions.addWidget(sync)
        actions.addWidget(gatt)
        actions.addStretch(1)
        firmware_body.addLayout(actions)

        self.notice(
            "步数、睡眠、血氧等通常不是标准 GATT",
            "心率与电量可通过公开 GATT 特征值读取；步数、睡眠、压力、血氧、通知同步等"
            "通常依赖小米 / 华为 / Garmin / Fitbit 等厂商私有协议与认证。"
            "当前面板会在数据可用时展示，否则保留占位。",
        )

    def refresh(self) -> None:
        telemetry = self.telemetry
        self.refresh_battery()
        if telemetry and telemetry.heart_rate is not None:
            self.heart_value.setText(str(telemetry.heart_rate))
            self.heart_hint.setText("最近一次通知")
            self.heart_dot.set_active(True)
        else:
            self.heart_value.setText("—")
            self.heart_hint.setText("连接并订阅后更新")
            self.heart_dot.set_active(False)
            metadata_hr = self.device.metadata.get("heart_rate")
            if metadata_hr:
                self.heart_value.setText(str(metadata_hr))
                self.heart_hint.setText("演示数据")
        steps = telemetry.steps if telemetry else None
        if steps is None:
            steps = self.device.metadata.get("steps")
        if steps is not None:
            self.steps_value.setText("{:,}".format(int(steps)))
            self.steps_hint.setText("步")
        self.model_row.value.setText((telemetry.model if telemetry and telemetry.model else self.device.metadata.get("model") or self.device.name) or "—")
        self.firmware_row.value.setText((telemetry.firmware if telemetry and telemetry.firmware else self.device.metadata.get("firmware") or "—"))
        self.serial_row.value.setText((telemetry.serial if telemetry and telemetry.serial else "—"))
        self.manufacturer_row.value.setText((telemetry.manufacturer if telemetry and telemetry.manufacturer else "—"))


def kv_row(label: str, value: str):
    from .base import InfoRow

    return InfoRow(label, value)
