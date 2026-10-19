"""Vector glyphs and application icon helpers."""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QWidget

from ..models import DeviceType


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def draw_bluetooth_rune(painter: QPainter, rect: QRectF, color: QColor, width: float = 2.4) -> None:
    painter.setPen(_pen(color, width))
    painter.setBrush(Qt.NoBrush)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    top = QPointF(x + w * 0.52, y + h * 0.1)
    bottom = QPointF(x + w * 0.52, y + h * 0.9)
    upper_right = QPointF(x + w * 0.76, y + h * 0.33)
    lower_left = QPointF(x + w * 0.26, y + h * 0.67)
    lower_right = QPointF(x + w * 0.76, y + h * 0.67)
    upper_left = QPointF(x + w * 0.26, y + h * 0.33)
    painter.drawLine(top, upper_right)
    painter.drawLine(upper_right, lower_left)
    painter.drawLine(lower_left, lower_right)
    painter.drawLine(lower_right, bottom)
    painter.drawLine(bottom, top)


def draw_device_glyph(
    painter: QPainter,
    rect: QRectF,
    device_type: DeviceType,
    color: QColor,
    width: float = 2.0,
) -> None:
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(_pen(color, width))
    painter.setBrush(Qt.NoBrush)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()

    def r(rx: float, ry: float, rw: float, rh: float) -> QRectF:
        return QRectF(x + w * rx, y + h * ry, w * rw, h * rh)

    if device_type is DeviceType.HEADPHONES:
        painter.drawArc(r(0.16, 0.22, 0.68, 0.62), 0, 180 * 16)
        painter.drawRoundedRect(r(0.17, 0.52, 0.17, 0.32), 4, 4)
        painter.drawRoundedRect(r(0.66, 0.52, 0.17, 0.32), 4, 4)
    elif device_type in (DeviceType.SPEAKER, DeviceType.CAR_AUDIO):
        if device_type is DeviceType.SPEAKER:
            painter.drawRoundedRect(r(0.25, 0.16, 0.5, 0.68), 6, 6)
            painter.drawEllipse(r(0.38, 0.52, 0.24, 0.24))
            painter.drawEllipse(r(0.44, 0.28, 0.12, 0.12))
        else:
            path = QPainterPath()
            path.moveTo(x + w * 0.12, y + h * 0.62)
            path.lineTo(x + w * 0.2, y + h * 0.43)
            path.cubicTo(x + w * 0.3, y + h * 0.32, x + w * 0.62, y + h * 0.32, x + w * 0.72, y + h * 0.43)
            path.lineTo(x + w * 0.88, y + h * 0.62)
            path.lineTo(x + w * 0.78, y + h * 0.62)
            path.lineTo(x + w * 0.7, y + h * 0.72)
            path.lineTo(x + w * 0.28, y + h * 0.72)
            path.lineTo(x + w * 0.2, y + h * 0.62)
            path.closeSubpath()
            painter.drawPath(path)
            painter.drawEllipse(r(0.24, 0.64, 0.14, 0.14))
            painter.drawEllipse(r(0.62, 0.64, 0.14, 0.14))
    elif device_type is DeviceType.MOUSE:
        painter.drawRoundedRect(r(0.31, 0.12, 0.38, 0.76), 12, 12)
        painter.drawLine(QPointF(x + w * 0.5, y + h * 0.14), QPointF(x + w * 0.5, y + h * 0.42))
        painter.drawArc(r(0.38, 0.2, 0.24, 0.26), 0, 180 * 16)
    elif device_type is DeviceType.KEYBOARD:
        painter.drawRoundedRect(r(0.1, 0.3, 0.8, 0.4), 6, 6)
        for row, count in ((0.4, 4), (0.52, 5), (0.62, 4)):
            for index in range(count):
                cx = x + w * (0.2 + index * (0.6 / max(1, count - 1)))
                painter.drawPoint(QPointF(cx, y + h * row))
    elif device_type is DeviceType.GAMEPAD:
        path = QPainterPath()
        path.moveTo(x + w * 0.2, y + h * 0.36)
        path.cubicTo(x + w * 0.38, y + h * 0.24, x + w * 0.62, y + h * 0.24, x + w * 0.8, y + h * 0.36)
        path.cubicTo(x + w * 0.92, y + h * 0.48, x + w * 0.82, y + h * 0.76, x + w * 0.7, y + h * 0.76)
        path.cubicTo(x + w * 0.6, y + h * 0.76, x + w * 0.58, y + h * 0.64, x + w * 0.5, y + h * 0.64)
        path.cubicTo(x + w * 0.42, y + h * 0.64, x + w * 0.4, y + h * 0.76, x + w * 0.3, y + h * 0.76)
        path.cubicTo(x + w * 0.18, y + h * 0.76, x + w * 0.08, y + h * 0.48, x + w * 0.2, y + h * 0.36)
        painter.drawPath(path)
        painter.drawLine(QPointF(x + w * 0.3, y + h * 0.44), QPointF(x + w * 0.3, y + h * 0.56))
        painter.drawLine(QPointF(x + w * 0.24, y + h * 0.5), QPointF(x + w * 0.36, y + h * 0.5))
        painter.drawEllipse(r(0.63, 0.43, 0.08, 0.08))
        painter.drawEllipse(r(0.71, 0.52, 0.08, 0.08))
    elif device_type is DeviceType.WEARABLE:
        painter.drawRoundedRect(r(0.3, 0.3, 0.4, 0.4), 10, 10)
        painter.drawRoundedRect(r(0.4, 0.1, 0.2, 0.2), 5, 5)
        painter.drawRoundedRect(r(0.4, 0.7, 0.2, 0.2), 5, 5)
        painter.drawLine(QPointF(x + w * 0.5, y + h * 0.42), QPointF(x + w * 0.5, y + h * 0.52))
        painter.drawLine(QPointF(x + w * 0.5, y + h * 0.52), QPointF(x + w * 0.58, y + h * 0.56))
    elif device_type is DeviceType.PHONE:
        painter.drawRoundedRect(r(0.3, 0.12, 0.4, 0.76), 7, 7)
        painter.drawLine(QPointF(x + w * 0.44, y + h * 0.2), QPointF(x + w * 0.56, y + h * 0.2))
        painter.drawEllipse(r(0.46, 0.79, 0.08, 0.03))
    else:
        draw_bluetooth_rune(painter, rect.adjusted(4, 4, -4, -4), color, width)
    painter.restore()


class DeviceGlyph(QWidget):
    def __init__(self, device_type: DeviceType = DeviceType.UNKNOWN, size: int = 40, parent=None) -> None:
        super().__init__(parent)
        self.device_type = device_type
        self._size = size
        self.setFixedSize(size, size)

    def set_device_type(self, device_type: DeviceType) -> None:
        if device_type is not self.device_type:
            self.device_type = device_type
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(5, 5, self.width() - 10, self.height() - 10)
        color = QColor(self.device_type.accent)
        glow = QColor(color)
        glow.setAlpha(30)
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2), 13, 13)
        draw_device_glyph(painter, rect, self.device_type, color, max(1.8, self.width() / 26.0))


def make_app_icon(size: int = 128) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0, QColor("#5b8cff"))
    gradient.setColorAt(1, QColor("#7b5dff"))
    painter.setPen(Qt.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(2, 2, size - 4, size - 4), size * 0.24, size * 0.24)
    draw_bluetooth_rune(
        painter,
        QRectF(size * 0.2, size * 0.14, size * 0.6, size * 0.72),
        QColor("#ffffff"),
        size * 0.055,
    )
    painter.end()
    return pixmap
