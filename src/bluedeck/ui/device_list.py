"""Device sidebar and device cards."""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..models import ConnectionState, DeviceInfo, DeviceType, Transport
from .icons import DeviceGlyph
from .theme import ACCENT, GREEN, MUTED, RED
from .widgets import RssiBars, StatusDot, clear_layout, make_button, make_pill, repolish


_TYPE_LABEL = {
    DeviceType.HEADPHONES: "耳机",
    DeviceType.SPEAKER: "音箱",
    DeviceType.CAR_AUDIO: "车载",
    DeviceType.MOUSE: "鼠标",
    DeviceType.KEYBOARD: "键盘",
    DeviceType.GAMEPAD: "手柄",
    DeviceType.WEARABLE: "穿戴",
    DeviceType.PHONE: "手机",
    DeviceType.UNKNOWN: "通用",
}


class DeviceCard(QFrame):
    selected = Signal(str)
    action_requested = Signal(str)

    def __init__(self, device: DeviceInfo, is_selected: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.device = device
        self.setObjectName("DeviceCard")
        self.setProperty("selected", "true" if is_selected else "false")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(
            "%s\n%s\n识别：%s（%s, %.0f%%）"
            % (
                device.display_name,
                device.address,
                device.device_type.label,
                device.classification_reason or device.transport.label,
                device.confidence * 100,
            )
        )
        self.setMinimumHeight(88)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 11, 12, 11)
        layout.setSpacing(10)
        self.glyph = DeviceGlyph(device.device_type, 42)
        layout.addWidget(self.glyph, 0, Qt.AlignTop)

        center = QVBoxLayout()
        center.setSpacing(4)
        name = QLabel(device.display_name)
        name.setStyleSheet("font-size: 14px; font-weight: 600;")
        name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        name.setMinimumWidth(0)
        name.setMaximumWidth(170)
        name.setToolTip(device.display_name)
        center.addWidget(name)
        meta_bits = [
            _TYPE_LABEL.get(device.device_type, "通用"),
            device.transport.label if device.transport is not Transport.UNKNOWN else "蓝牙",
        ]
        if device.paired:
            meta_bits.append("已配对")
        meta = QLabel(" · ".join(meta_bits))
        meta.setObjectName("Faint")
        center.addWidget(meta)
        bottom = QHBoxLayout()
        bottom.setSpacing(5)
        self.rssi_bars = RssiBars(device.rssi)
        bottom.addWidget(self.rssi_bars)
        rssi_text = "—" if device.rssi is None else "%d dBm" % device.rssi
        rssi = QLabel(rssi_text)
        rssi.setObjectName("Faint")
        bottom.addWidget(rssi)
        address = QLabel(device.short_address)
        address.setObjectName("Faint")
        address.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        address.setToolTip(device.address)
        bottom.addWidget(address, 1)
        center.addLayout(bottom)
        layout.addLayout(center, 1)

        right = QVBoxLayout()
        right.setSpacing(6)
        right.setAlignment(Qt.AlignRight | Qt.AlignTop)
        status_row = QHBoxLayout()
        status_row.setSpacing(4)
        self.dot = StatusDot()
        self.dot.set_active(device.connected or device.state is ConnectionState.CONNECTING)
        status_row.addWidget(self.dot)
        state = QLabel(device.state.label)
        state.setObjectName("Faint")
        state.setFixedWidth(42)
        if device.state is ConnectionState.CONNECTED:
            state.setStyleSheet("color: #68e0b0; font-size: 11px;")
        elif device.state is ConnectionState.FAILED:
            state.setStyleSheet("color: #ff9aa2; font-size: 11px;")
        status_row.addWidget(state)
        status_row.addStretch(1)
        right.addLayout(status_row)
        self.action = QPushButton()
        self.action.setCursor(Qt.PointingHandCursor)
        self.action.setFixedWidth(54)
        self.action.clicked.connect(lambda: self.action_requested.emit(self.device.address))
        self._configure_action(device)
        right.addWidget(self.action, 0, Qt.AlignRight)
        layout.addLayout(right, 0)

    def _configure_action(self, device: DeviceInfo) -> None:
        if device.state is ConnectionState.CONNECTING:
            self.action.setText("连接中")
            self.action.setEnabled(False)
            self.action.setProperty("variant", "ghost")
        elif device.connected:
            self.action.setText("断开")
            self.action.setEnabled(True)
            self.action.setProperty("variant", "ghost")
        elif device.state is ConnectionState.FAILED:
            self.action.setText("重试")
            self.action.setEnabled(True)
            self.action.setProperty("variant", "primary")
        else:
            self.action.setText("连接")
            self.action.setEnabled(True)
            self.action.setProperty("variant", "primary")
        repolish(self.action)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", "true" if selected else "false")
        repolish(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.selected.emit(self.device.address)
        super().mousePressEvent(event)


class Sidebar(QFrame):
    selection_changed = Signal(str)
    connect_requested = Signal(str)
    filters_changed = Signal()
    scan_toggle_requested = Signal()
    demo_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setMinimumWidth(318)
        self.setMaximumWidth(430)
        self._selected_key = ""
        self._devices: List[DeviceInfo] = []
        self._cards: List[DeviceCard] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(7)
        title = QLabel("设备")
        title.setStyleSheet("font-size: 17px; font-weight: 700;")
        header.addWidget(title)
        self.count_pill = make_pill("0", "blue")
        self.count_pill.setFixedWidth(32)
        header.addWidget(self.count_pill)
        header.addStretch(1)
        self.scan_btn = QToolButton()
        self.scan_btn.setObjectName("IconButton")
        self.scan_btn.setText("↻")
        self.scan_btn.setToolTip("开始 / 停止 BLE 扫描")
        self.scan_btn.setCursor(Qt.PointingHandCursor)
        self.scan_btn.clicked.connect(self.scan_toggle_requested.emit)
        header.addWidget(self.scan_btn)
        layout.addLayout(header)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索名称或地址…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _text: self.filters_changed.emit())
        layout.addWidget(self.search)

        chips = QHBoxLayout()
        chips.setSpacing(5)
        self.chip_group = QButtonGroup(self)
        self.chip_group.setExclusive(True)
        for index, (label, mode) in enumerate(
            (("全部", "all"), ("已配对", "paired"), ("附近", "nearby"), ("已连接", "connected"))
        ):
            chip = QToolButton()
            chip.setObjectName("FilterChip")
            chip.setText(label)
            chip.setCheckable(True)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setProperty("mode", mode)
            if index == 0:
                chip.setChecked(True)
            self.chip_group.addButton(chip, index)
            chips.addWidget(chip)
        chips.addStretch(1)
        self.chip_group.idClicked.connect(lambda _id: self.filters_changed.emit())
        layout.addLayout(chips)

        self.type_combo = QComboBox()
        self.type_combo.addItem("全部设备类型", None)
        for device_type in (
            DeviceType.HEADPHONES,
            DeviceType.SPEAKER,
            DeviceType.CAR_AUDIO,
            DeviceType.MOUSE,
            DeviceType.KEYBOARD,
            DeviceType.GAMEPAD,
            DeviceType.WEARABLE,
        ):
            self.type_combo.addItem(device_type.label, device_type)
        self.type_combo.currentIndexChanged.connect(lambda _index: self.filters_changed.emit())
        layout.addWidget(self.type_combo)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 2, 2, 2)
        self.list_layout.setSpacing(7)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.list_host)
        layout.addWidget(self.scroll, 1)

        self.footer = QLabel("BLE 实时扫描 · 经典蓝牙来自系统配对列表")
        self.footer.setObjectName("Faint")
        self.footer.setWordWrap(True)
        layout.addWidget(self.footer)

    # ------------------------------------------------------------------
    def mode(self) -> str:
        button = self.chip_group.checkedButton()
        if button is None:
            return "all"
        return str(button.property("mode") or "all")

    def device_type(self) -> Optional[DeviceType]:
        value = self.type_combo.currentData()
        return value if isinstance(value, DeviceType) else None

    def query(self) -> str:
        return self.search.text().strip()

    def set_scanning(self, scanning: bool, message: str = "") -> None:
        self.scan_btn.setText("■" if scanning else "↻")
        self.scan_btn.setStyleSheet("color: #ff9aa2;" if scanning else "")
        self.footer.setText(message or ("正在扫描附近 BLE 设备…" if scanning else "BLE 实时扫描 · 经典蓝牙来自系统配对列表"))

    def set_devices(self, devices: List[DeviceInfo], selected_key: str = "") -> None:
        scroll_value = self.scroll.verticalScrollBar().value()
        self._devices = devices
        self._selected_key = selected_key
        clear_layout(self.list_layout)
        self._cards = []
        self.count_pill.setText(str(len(devices)))
        if not devices:
            empty = QLabel("没有匹配的设备\n调整筛选条件，或点击右上角刷新开始扫描。")
            empty.setAlignment(Qt.AlignCenter)
            empty.setObjectName("Faint")
            empty.setWordWrap(True)
            empty.setMinimumHeight(160)
            self.list_layout.addWidget(empty)
        else:
            for device in devices:
                card = DeviceCard(device, device.key == selected_key)
                card.selected.connect(self.selection_changed.emit)
                card.action_requested.connect(self.connect_requested.emit)
                self.list_layout.addWidget(card)
                self._cards.append(card)
        self.list_layout.addStretch(1)
        self.scroll.verticalScrollBar().setValue(scroll_value)

    def set_selected(self, key: str) -> None:
        self._selected_key = key
        for card in self._cards:
            card.set_selected(card.device.key == key)

    def set_demo_visible(self, visible: bool) -> None:
        self.footer.setText(
            "演示模式：设备与数据均为模拟值"
            if visible
            else "BLE 实时扫描 · 经典蓝牙来自系统配对列表"
        )
