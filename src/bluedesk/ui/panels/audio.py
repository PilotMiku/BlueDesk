"""Headphone / speaker / car-audio control panel."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ...models import DeviceInfo, Telemetry
from ..theme import ACCENT, MUTED
from ..widgets import Card, MetricTile, RssiBars, make_button, make_pill
from .base import ControlPanel


class AudioPanel(ControlPanel):
    def _build(self) -> None:
        self._updating_volume = False
        self._muted = False

        top = QHBoxLayout()
        top.setSpacing(13)
        volume, volume_body = self.card(
            "输出音量", "控制系统当前音频输出", ("系统级", "blue"), add=False
        )
        percent_row = QHBoxLayout()
        self.percent = QLabel("—")
        self.percent.setObjectName("PercentBig")
        self.percent.setStyleSheet("color: #cfe0ff;")
        percent_row.addWidget(self.percent)
        percent_row.addStretch(1)
        self.volume_state = QLabel("拖动滑杆调整")
        self.volume_state.setObjectName("Faint")
        percent_row.addWidget(self.volume_state, 0, Qt.AlignBottom)
        volume_body.addLayout(percent_row)
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(0)
        self.volume_slider.valueChanged.connect(self._volume_changed)
        volume_body.addWidget(self.volume_slider)
        controls = QHBoxLayout()
        self.mute_btn = make_button("静音", "ghost", "切换系统静音")
        self.mute_btn.clicked.connect(self._toggle_mute)
        controls.addWidget(self.mute_btn)
        sound = make_button("声音设置", "ghost")
        sound.clicked.connect(self.controller.open_sound_settings)
        controls.addWidget(sound)
        controls.addStretch(1)
        volume_body.addLayout(controls)
        top.addWidget(volume, 2)

        self.battery = self.battery_card()
        self.battery.setMinimumWidth(205)
        top.addWidget(self.battery, 1)
        self.layout.addLayout(top)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self.signal_tile = MetricTile("信号强度", "—", "RSSI")
        self.signal_tile.value.setStyleSheet("color: #8db4ff;")
        self.link_tile = MetricTile("连接状态", "未连接", "系统 / GATT")
        self.type_tile = MetricTile("音频链路", self.device.transport.label, "A2DP / AVRCP")
        metrics.addWidget(self.signal_tile)
        metrics.addWidget(self.link_tile)
        metrics.addWidget(self.type_tile)
        self.layout.addLayout(metrics)

        media, media_body = self.card(
            "媒体控制", "发送系统媒体按键；macOS 通过 AppleScript 控制播放器", ("系统级", "blue")
        )
        media_row = QHBoxLayout()
        media_row.setSpacing(8)
        for command, icon, label in (
            ("previous", "⏮", "上一首"),
            ("play_pause", "⏯", "播放 / 暂停"),
            ("next", "⏭", "下一首"),
            ("stop", "⏹", "停止"),
        ):
            button = QPushButton("%s\n%s" % (icon, label))
            button.setProperty("variant", "media")
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(52)
            button.clicked.connect(lambda _checked=False, cmd=command: self.controller.media_command(cmd))
            media_row.addWidget(button)
        media_body.addLayout(media_row)
        hint = QLabel("媒体指令作用于当前系统默认播放器 / 输出设备，不使用蓝牙私有协议。")
        hint.setObjectName("Faint")
        hint.setWordWrap(True)
        media_body.addWidget(hint)

        self.eq_card, eq_body = self.card(
            "音效均衡器", "5 段 EQ · 标准 A2DP 不携带设备 EQ 指令", ("需要厂商协议", "red")
        )
        eq_row = QHBoxLayout()
        eq_row.setSpacing(16)
        self.eq_sliders = []
        for frequency in ("60", "230", "910", "3600", "14000"):
            column = QVBoxLayout()
            column.setSpacing(5)
            slider = QSlider(Qt.Vertical)
            slider.setRange(-12, 12)
            slider.setValue(0)
            slider.setFixedHeight(108)
            slider.setEnabled(False)
            value_label = QLabel("0 dB")
            value_label.setObjectName("Faint")
            value_label.setAlignment(Qt.AlignCenter)
            slider.valueChanged.connect(
                lambda value, label=value_label: label.setText("%+d dB" % value)
            )
            name = QLabel("%s Hz" % frequency)
            name.setObjectName("Faint")
            name.setAlignment(Qt.AlignCenter)
            column.addWidget(slider, 0, Qt.AlignHCenter)
            column.addWidget(value_label)
            column.addWidget(name)
            eq_row.addLayout(column)
            self.eq_sliders.append(slider)
        eq_row.addStretch(1)
        eq_body.addLayout(eq_row)
        apply_row = QHBoxLayout()
        apply = make_button("应用到设备", "primary")
        apply.setEnabled(False)
        reset = make_button("重置", "ghost")
        reset.setEnabled(False)
        apply_row.addWidget(apply)
        apply_row.addWidget(reset)
        apply_row.addStretch(1)
        eq_body.addLayout(apply_row)

        self.notice(
            "高级音频功能需要厂商协议",
            "音量与媒体传输使用系统能力。EQ、降噪、空间音频、固件升级通常依赖 Sony / Bose / "
            "Jabra / Apple 等厂商私有 GATT 或 RFCOMM 协议，当前版本只提供可替换的协议适配层与界面占位。",
        )

        QTimer.singleShot(0, self._load_volume)

    # ------------------------------------------------------------------
    def _load_volume(self) -> None:
        value = self.controller.get_volume()
        if value is not None:
            self._updating_volume = True
            self.volume_slider.setValue(value)
            self.percent.setText("%d%%" % value)
            self._updating_volume = False

    def _volume_changed(self, value: int) -> None:
        if self._updating_volume:
            return
        self.percent.setText("%d%%" % value)
        self.controller.set_volume(value)

    def _toggle_mute(self) -> None:
        self._muted = not self._muted
        self.mute_btn.setText("取消静音" if self._muted else "静音")
        self.controller.set_muted(self._muted)

    def refresh(self) -> None:
        self.signal_tile.set_value(
            "%d dBm" % self.device.rssi if self.device.rssi is not None else "—",
            "信号强度",
        )
        self.link_tile.set_value(self.device.state.label, self.device.transport.label)
        self.type_tile.set_value(self.device.transport.label, "A2DP / AVRCP")
        self.refresh_battery()
