"""Generic Bluetooth device panel and gamepad variant."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QGridLayout, QHBoxLayout, QVBoxLayout

from ..widgets import PlainLabel as QLabel
from ...models import DeviceInfo, Telemetry
from ..widgets import Card, MetricTile, clear_layout, make_button, make_pill
from .base import ControlPanel, InfoRow


class GenericPanel(ControlPanel):
    def _build(self) -> None:
        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self.signal_tile = MetricTile("信号强度", "—", "RSSI")
        self.link_tile = MetricTile("连接状态", "未连接", "GATT / 系统")
        self.service_tile = MetricTile("GATT 服务", "—", "连接后发现")
        metrics.addWidget(self.signal_tile)
        metrics.addWidget(self.link_tile)
        metrics.addWidget(self.service_tile)
        self.layout.addLayout(metrics)

        info, info_body = self.card("设备信息", "来自扫描广播与系统配对列表")
        self.address_row = InfoRow("地址 / 设备 ID", self.device.address or "—")
        self.transport_row = InfoRow("传输", self.device.transport.label)
        self.paired_row = InfoRow("配对状态", "已配对" if self.device.paired else "未配对")
        self.source_row = InfoRow("发现来源", self.device.source)
        self.confidence_row = InfoRow("类型置信度", "%.0f%%" % (self.device.confidence * 100))
        for row in (
            self.address_row,
            self.transport_row,
            self.paired_row,
            self.source_row,
            self.confidence_row,
        ):
            info_body.addWidget(row)

        identify, identify_body = self.card(
            "设备类型识别", "Class of Device · Appearance · Service UUID · 名称", (self.device.device_type.short_label, "blue")
        )
        self.identify_big = QLabel(self.device.device_type.label)
        self.identify_big.setObjectName("HeroTitle")
        self.identify_big.setStyleSheet("color: %s;" % self.device.device_type.accent)
        identify_body.addWidget(self.identify_big)
        self.reason = QLabel(self.device.classification_reason or "未提供识别依据")
        self.reason.setObjectName("Muted")
        self.reason.setWordWrap(True)
        identify_body.addWidget(self.reason)
        self.identify_source = QLabel("规则来源：%s" % (self.device.classification_source or "fallback"))
        self.identify_source.setObjectName("Faint")
        identify_body.addWidget(self.identify_source)

        services, services_body = self.card("服务与特征值", "连接后可在 GATT 标签页读写与订阅")
        self.services_preview = QVBoxLayout()
        self.services_preview.setSpacing(4)
        services_body.addLayout(self.services_preview)
        service_actions = QHBoxLayout()
        gatt = make_button("打开 GATT 浏览器", "primary")
        gatt.clicked.connect(lambda: self.tab_requested.emit("gatt"))
        logs = make_button("通信日志", "ghost")
        logs.clicked.connect(lambda: self.tab_requested.emit("logs"))
        service_actions.addWidget(gatt)
        service_actions.addWidget(logs)
        service_actions.addStretch(1)
        services_body.addLayout(service_actions)

        actions, actions_body = self.card("通用操作", "连接、系统设置与设备地址")
        row = QHBoxLayout()
        self.connect_btn = make_button("连接设备", "primary")
        self.connect_btn.clicked.connect(self._toggle_connection)
        system = make_button("系统蓝牙设置", "ghost")
        system.clicked.connect(self.controller.open_bluetooth_settings)
        copy = make_button("复制地址", "ghost")
        copy.clicked.connect(self._copy_address)
        log_btn = make_button("记录日志", "ghost")
        log_btn.clicked.connect(self._log_snapshot)
        for button in (self.connect_btn, system, copy, log_btn):
            row.addWidget(button)
        row.addStretch(1)
        actions_body.addLayout(row)

        self.notice(
            "通用设备模式",
            "未识别的设备仍可进行连接/断开、RSSI 观察、GATT 服务浏览、特征值读写与通知订阅。"
            "所有写操作都会记录到日志，便于调试硬件协议。",
        )

    def _toggle_connection(self) -> None:
        self.controller.toggle_connection(self.device.address)

    def _copy_address(self) -> None:
        QApplication.clipboard().setText(self.device.address)
        self.controller.status_message.emit("设备地址已复制")
        self.controller.log("INFO", "已复制地址 %s" % self.device.address, address=self.device.address)

    def _log_snapshot(self) -> None:
        self.controller.log(
            "INFO",
            "设备快照：%s" % self.device.to_dict(),
            address=self.device.address,
            category="device",
        )
        self.controller.status_message.emit("设备快照已写入日志")

    def _render_services(self) -> None:
        clear_layout(self.services_preview)
        services = self.controller.services_for(self.device.address)
        self.service_tile.set_value(str(len(services)) if services else "—", "连接后发现")
        if not services:
            label = QLabel("尚未发现 GATT 服务。连接 BLE 设备后自动读取。")
            label.setObjectName("Faint")
            label.setWordWrap(True)
            self.services_preview.addWidget(label)
            return
        shown = 0
        for service in services[:4]:
            chars = len(service.characteristics)
            text = "%s  ·  %d 个特征值" % (service.description or service.uuid, chars)
            row = QLabel(text)
            row.setStyleSheet("color: #aebed6;")
            self.services_preview.addWidget(row)
            shown += 1
        if len(services) > shown:
            more = QLabel("还有 %d 个服务，请在 GATT 标签页查看。" % (len(services) - shown))
            more.setObjectName("Faint")
            self.services_preview.addWidget(more)

    def refresh(self) -> None:
        self.signal_tile.set_value(
            "%d dBm" % self.device.rssi if self.device.rssi is not None else "—",
            "信号强度",
        )
        self.link_tile.set_value(self.device.state.label, self.device.transport.label)
        self.address_row.set_value(self.device.address or "—")
        self.transport_row.set_value(self.device.transport.label)
        self.paired_row.set_value("已配对" if self.device.paired else "未配对")
        self.source_row.set_value(self.device.source)
        self.confidence_row.set_value("%.0f%%" % (self.device.confidence * 100))
        self.identify_big.setText(self.device.device_type.label)
        self.identify_big.setStyleSheet("color: %s;" % self.device.device_type.accent)
        self.reason.setText(self.device.classification_reason or "未提供识别依据")
        self.identify_source.setText("规则来源：%s" % (self.device.classification_source or "fallback"))
        self.connect_btn.setText("断开连接" if self.device.connected else "连接设备")
        self.connect_btn.setProperty("variant", "danger" if self.device.connected else "primary")
        self.connect_btn.style().unpolish(self.connect_btn)
        self.connect_btn.style().polish(self.connect_btn)
        self._render_services()
        self.refresh_battery()


class GamepadPanel(GenericPanel):
    def _build(self) -> None:
        super()._build()
        self.battery = self.battery_card()
        self.layout.insertWidget(0, self.battery)

        mapping, mapping_body = self.card(
            "手柄按键与摇杆", "标准 HID 输入可以读取，重映射依赖厂商协议", ("需要厂商协议", "red")
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        grid.addWidget(self._muted("控件"), 0, 0)
        grid.addWidget(self._muted("标准能力"), 0, 1)
        grid.addWidget(self._muted("高级配置"), 0, 2)
        for index, (control, standard, advanced) in enumerate(
            (
                ("A / B / X / Y", "按键报告", "宏 / 连发"),
                ("十字键", "方向报告", "映射"),
                ("双摇杆", "轴报告", "死区 / 曲线"),
                ("扳机键", "模拟轴", "触发点"),
                ("振动马达", "输出报告", "强度 / 波形"),
            ),
            start=1,
        ):
            grid.addWidget(QLabel(control), index, 0)
            grid.addWidget(QLabel(standard), index, 1)
            hint = QLabel(advanced)
            hint.setObjectName("Faint")
            grid.addWidget(hint, index, 2)
        mapping_body.addLayout(grid)
        self.layout.insertWidget(1, mapping)

    @staticmethod
    def _muted(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Faint")
        return label
