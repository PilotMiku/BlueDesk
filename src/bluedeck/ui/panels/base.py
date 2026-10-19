"""Shared control-panel scaffolding."""
from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...controller import AppController
from ...models import DeviceCapabilities, DeviceInfo, Telemetry, capabilities_for
from ...protocols import FeatureStatus
from ..widgets import BatteryRing, Card, SectionHeader, make_pill


class InfoRow(QWidget):
    def __init__(self, label: str, value: str = "—", parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(10)
        self.label = QLabel(label)
        self.label.setObjectName("Muted")
        self.value = QLabel(value)
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.value.setStyleSheet("font-weight: 500;")
        layout.addWidget(self.label)
        layout.addStretch(1)
        layout.addWidget(self.value)

    def set_value(self, value: str) -> None:
        self.value.setText(value)


class BatteryCard(Card):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(180)
        layout = QHBoxLayout()
        layout.setSpacing(10)
        self.ring = BatteryRing()
        layout.addWidget(self.ring)
        text = QVBoxLayout()
        text.setSpacing(3)
        title = QLabel("设备电量")
        title.setObjectName("SectionTitle")
        text.addWidget(title)
        self.status = QLabel("连接后读取")
        self.status.setObjectName("Faint")
        self.status.setWordWrap(True)
        text.addWidget(self.status)
        self.source = QLabel("Battery Level 0x2A19")
        self.source.setObjectName("Faint")
        self.source.setWordWrap(True)
        text.addWidget(self.source)
        text.addStretch(1)
        layout.addLayout(text, 1)
        self.layout.addLayout(layout)

    def set_telemetry(self, telemetry: Optional[Telemetry]) -> None:
        if telemetry and telemetry.battery is not None:
            self.ring.set_level(telemetry.battery, bool(telemetry.charging))
            self.status.setText("充电中" if telemetry.charging else "电量正常")
            self.status.setStyleSheet("color: #56d6a0;" if telemetry.battery >= 20 else "color: #ff9aa2;")
        else:
            self.ring.set_level(None)
            self.status.setText("连接后读取")
            self.status.setStyleSheet("")


class ControlPanel(QWidget):
    tab_requested = Signal(str)

    def __init__(self, controller: AppController, device: DeviceInfo, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.device = device
        self.capabilities: DeviceCapabilities = capabilities_for(device.device_type)
        self.telemetry: Optional[Telemetry] = controller.telemetry_for(device.address)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 12)
        self.layout.setSpacing(13)
        self._battery_cards = []
        self._build()
        self.layout.addStretch(1)

    def _build(self) -> None:
        raise NotImplementedError

    def update_device(self, device: DeviceInfo, telemetry: Optional[Telemetry]) -> None:
        self.device = device
        self.telemetry = telemetry
        self.refresh()

    def refresh(self) -> None:
        pass

    # ------------------------------------------------------------------
    def card(
        self,
        title: str,
        subtitle: str = "",
        badge: Optional[Tuple[str, str]] = None,
        add: bool = True,
    ) -> Tuple[Card, QVBoxLayout]:
        card = Card()
        header = QHBoxLayout()
        header.setSpacing(8)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        texts.addWidget(title_label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("Faint")
            sub.setWordWrap(True)
            texts.addWidget(sub)
        header.addLayout(texts, 1)
        if badge:
            header.addWidget(make_pill(badge[0], badge[1]), 0, Qt.AlignTop)
        card.layout.addLayout(header)
        body = QVBoxLayout()
        body.setSpacing(8)
        card.layout.addLayout(body)
        if add:
            self.layout.addWidget(card)
        return card, body

    def notice(self, title: str, text: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Notice")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(13, 10, 13, 10)
        layout.setSpacing(10)
        marker = QLabel("!")
        marker.setFixedSize(22, 22)
        marker.setAlignment(Qt.AlignCenter)
        marker.setStyleSheet(
            "background: #4b3a1e; color: #f4c477; border-radius: 11px; font-weight: 700;"
        )
        layout.addWidget(marker, 0, Qt.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        heading = QLabel(title)
        heading.setObjectName("BannerTitle")
        body = QLabel(text)
        body.setObjectName("BannerText")
        body.setWordWrap(True)
        texts.addWidget(heading)
        texts.addWidget(body)
        layout.addLayout(texts, 1)
        self.layout.addWidget(frame)
        return frame

    def battery_card(self) -> BatteryCard:
        card = BatteryCard()
        self._battery_cards.append(card)
        return card

    def refresh_battery(self) -> None:
        for card in self._battery_cards:
            card.set_telemetry(self.telemetry)

    def info_card(self, title: str, rows) -> Tuple[Card, dict]:
        card, body = self.card(title)
        widgets = {}
        for key, label, value in rows:
            row = InfoRow(label, value)
            body.addWidget(row)
            widgets[key] = row
        return card, widgets

    def state_pill(self) -> Tuple[str, str]:
        if self.device.connected:
            return "已连接", "green"
        if self.device.state.value == "connecting":
            return "连接中", "amber"
        if self.device.state.value == "failed":
            return "连接失败", "red"
        return "未连接", ""
