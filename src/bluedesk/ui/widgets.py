"""Reusable custom widgets and small visual primitives."""
from __future__ import annotations

import html
from typing import Optional

from PySide6.QtCore import QEasingCurve, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel as QtLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..models import DeviceType, rssi_to_bars
from .icons import DeviceGlyph
from .theme import ACCENT, AMBER, GREEN, MUTED, RED, TEXT


def clear_layout(layout) -> None:
    if layout is None:
        return
    while layout.count():
        item = layout.takeAt(0)
        child = item.widget()
        if child is not None:
            child.deleteLater()
        else:
            sub = item.layout()
            if sub is not None:
                clear_layout(sub)


class PlainLabel(QtLabel):
    """Treat external text as plain text, never HTML."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setTextFormat(Qt.PlainText)
        self.setText(text)

    def setToolTip(self, text: str) -> None:
        super().setToolTip(plain_tooltip(text))


def plain_tooltip(text: str) -> str:
    return "<qt><pre>" + html.escape(text[:4096]) + "</pre></qt>"


def make_button(text: str, variant: str = "", tooltip: str = "") -> QPushButton:
    button = QPushButton(text)
    if variant:
        button.setProperty("variant", variant)
    if tooltip:
        button.setToolTip(tooltip)
    button.setCursor(Qt.PointingHandCursor)
    return button


def make_pill(text: str, tone: str = "") -> PlainLabel:
    label = PlainLabel(text)
    label.setObjectName("Pill")
    if tone:
        label.setProperty("tone", tone)
    label.setAlignment(Qt.AlignCenter)
    return label


def repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


class Card(QFrame):
    def __init__(self, parent=None, sub: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("SubCard" if sub else "Card")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(18, 16, 18, 16)
        self.layout.setSpacing(10)


class SectionHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = PlainLabel(title)
        self.title.setObjectName("SectionTitle")
        texts.addWidget(self.title)
        self.subtitle = PlainLabel(subtitle)
        self.subtitle.setObjectName("Faint")
        self.subtitle.setWordWrap(True)
        texts.addWidget(self.subtitle)
        self.subtitle.setVisible(bool(subtitle))
        layout.addLayout(texts)
        layout.addStretch(1)


class RssiBars(QWidget):
    def __init__(self, rssi: Optional[int] = None, parent=None) -> None:
        super().__init__(parent)
        self.rssi = rssi
        self.setFixedSize(30, 18)

    def set_rssi(self, rssi: Optional[int]) -> None:
        self.rssi = rssi
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        bars = rssi_to_bars(self.rssi)
        for index in range(4):
            height = 4 + index * 3
            color = QColor(ACCENT if index < bars else "#2b3a51")
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(
                QRectF(index * 7, self.height() - height, 4.5, height), 1.5, 1.5
            )


class StatusDot(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._active = False
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(45)
        self.setFixedSize(16, 16)

    def set_active(self, active: bool) -> None:
        self._active = active
        if active:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            self._phase = 0.0
        self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.09) % 1.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        color = QColor(GREEN if self._active else "#52647e")
        if self._active:
            glow = QColor(color)
            glow.setAlpha(int(50 + 50 * (1 - self._phase)))
            painter.setBrush(glow)
            painter.setPen(Qt.NoPen)
            radius = 5 + 5 * self._phase
            painter.drawEllipse(QRectF(8 - radius, 8 - radius, radius * 2, radius * 2))
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(5, 5, 6, 6))


class MetricTile(QFrame):
    def __init__(self, label: str, value: str = "—", hint: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SubCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(3)
        self.label = PlainLabel(label)
        self.label.setObjectName("MetricLabel")
        self.value = PlainLabel(value)
        self.value.setObjectName("MetricValueSmall")
        self.hint = PlainLabel(hint)
        self.hint.setObjectName("Faint")
        self.hint.setWordWrap(True)
        layout.addWidget(self.label)
        layout.addWidget(self.value)
        layout.addWidget(self.hint)

    def set_value(self, value: str, hint: str = "") -> None:
        self.value.setText(value)
        if hint:
            self.hint.setText(hint)

    def set_accent(self, color: str) -> None:
        self.value.setStyleSheet("color: %s;" % color)


class BatteryRing(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._percent: Optional[int] = None
        self._charging = False
        self.setMinimumSize(104, 104)
        self.setMaximumSize(136, 136)

    def set_level(self, percent: Optional[int], charging: bool = False) -> None:
        self._percent = percent
        self._charging = charging
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        side = min(self.width(), self.height())
        arc_rect = QRectF((self.width() - side) / 2 + 9, (self.height() - side) / 2 + 9, side - 18, side - 18)
        painter.setPen(QPen(QColor("#22324a"), 8, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(arc_rect, 0, 360 * 16)
        if self._percent is not None:
            color = QColor(GREEN if self._percent >= 35 else AMBER if self._percent >= 15 else RED)
            painter.setPen(QPen(color, 8, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(arc_rect, 90 * 16, -int(360 * 16 * max(0, min(100, self._percent)) / 100))
            painter.setPen(QColor(TEXT))
            font = QFont()
            font.setPointSize(18)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(arc_rect, Qt.AlignCenter, "%d%%" % self._percent)
        else:
            painter.setPen(QColor(MUTED))
            font = QFont()
            font.setPointSize(11)
            painter.setFont(font)
            painter.drawText(arc_rect, Qt.AlignCenter, "暂无数据")
        if self._charging:
            painter.setPen(QColor(AMBER))
            font = QFont()
            font.setPointSize(9)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                QRectF(0, self.height() - 23, self.width(), 18),
                Qt.AlignCenter,
                "充电中",
            )


class TagRow(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)

    def set_tags(self, tags) -> None:
        clear_layout(self.layout)
        for text, tone in tags:
            self.layout.addWidget(make_pill(text, tone))
        self.layout.addStretch(1)


class EmptyState(QWidget):
    scan_requested = Signal()
    demo_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.addStretch(2)
        glyph = DeviceGlyph(DeviceType.UNKNOWN, 96)
        glyph.setMaximumSize(96, 96)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(glyph)
        row.addStretch(1)
        layout.addLayout(row)
        title = PlainLabel("选择一个蓝牙设备")
        title.setObjectName("HeroTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        subtitle = PlainLabel("从左侧列表选择设备，BlueDesk 会按设备类型自动加载控制面板。\n未识别的设备也可以使用通用 GATT、RSSI 与日志功能。")
        subtitle.setObjectName("Muted")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        scan = make_button("扫描附近设备", "primary")
        scan.clicked.connect(self.scan_requested.emit)
        demo = make_button("加载演示数据")
        demo.clicked.connect(self.demo_requested.emit)
        buttons.addWidget(scan)
        buttons.addWidget(demo)
        buttons.addStretch(1)
        layout.addSpacing(10)
        layout.addLayout(buttons)
        layout.addStretch(3)
