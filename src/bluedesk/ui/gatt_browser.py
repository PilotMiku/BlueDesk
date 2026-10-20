"""Interactive GATT service browser and characteristic console."""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .widgets import PlainLabel as QLabel
from ..ble_uuids import compact_uuid, describe_characteristic, describe_service
from ..codecs import CodecError, encode_payload, format_hex, hexdump
from ..controller import AppController
from ..models import DeviceInfo, GattCharacteristicInfo, GattServiceInfo
from ..security import MAX_GATT_BYTES, MAX_OUTPUT_BLOCKS
from .widgets import clear_layout, make_button, make_pill


class GattBrowser(QWidget):
    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.device: Optional[DeviceInfo] = None
        self._services: List[GattServiceInfo] = []
        self._services_key = None
        self._selected_char: Optional[GattCharacteristicInfo] = None
        self._subscribed: Set[Tuple[str, str]] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("GATT 服务浏览器")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        self.count_pill = make_pill("0 服务", "blue")
        header.addWidget(self.count_pill)
        header.addStretch(1)
        self.device_label = QLabel("未选择设备")
        self.device_label.setObjectName("Faint")
        header.addWidget(self.device_label)
        layout.addLayout(header)

        self.banner = QLabel("")
        self.banner.setObjectName("Faint")
        self.banner.setWordWrap(True)
        self.banner.setVisible(False)
        layout.addWidget(self.banner)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["服务", "特征值", "UUID", "属性"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.header().setStretchLastSection(False)
        self.tree.setColumnWidth(0, 180)
        self.tree.setColumnWidth(1, 190)
        self.tree.setColumnWidth(2, 220)
        self.tree.setColumnWidth(3, 150)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.tree.setMinimumHeight(165)
        layout.addWidget(self.tree, 1)

        detail = QHBoxLayout()
        self.char_label = QLabel("选择一个特征值以读取、写入或订阅通知")
        self.char_label.setObjectName("Muted")
        self.char_label.setWordWrap(True)
        detail.addWidget(self.char_label, 1)
        self.uuid_label = QLabel("")
        self.uuid_label.setObjectName("Faint")
        self.uuid_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail.addWidget(self.uuid_label)
        layout.addLayout(detail)

        editor = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(["HEX", "文本"])
        self.mode.setFixedWidth(82)
        editor.addWidget(self.mode)
        self.input = QLineEdit()
        self.input.setMaxLength(MAX_GATT_BYTES * 3)
        self.input.setPlaceholderText("写入数据，例如 01 02 FF 或文本内容…")
        editor.addWidget(self.input, 1)
        self.with_response = QCheckBox("带响应")
        self.with_response.setChecked(True)
        editor.addWidget(self.with_response)
        self.read_btn = make_button("读取", "ghost")
        self.read_btn.clicked.connect(self._read)
        self.write_btn = make_button("写入", "primary")
        self.write_btn.clicked.connect(self._write)
        self.notify_btn = make_button("订阅", "ghost")
        self.notify_btn.clicked.connect(self._notify)
        for button in (self.read_btn, self.write_btn, self.notify_btn):
            button.setEnabled(False)
            editor.addWidget(button)
        layout.addLayout(editor)

        self.output = QTextBrowser()
        self.output.document().setMaximumBlockCount(MAX_OUTPUT_BLOCKS)
        self.output.setOpenExternalLinks(False)
        self.output.setMinimumHeight(78)
        self.output.setMaximumHeight(112)
        self.output.setFont(QFont("SF Mono, Menlo, Consolas, monospace", 11))
        self.output.setPlaceholderText("读取 / 通知的数据会显示在这里，支持 HEX 与文本视图。")
        layout.addWidget(self.output, 0)

        bottom = QHBoxLayout()
        self.status = QLabel("提示：写入未知特征值前请确认设备协议，错误指令可能改变设备配置。")
        self.status.setObjectName("Faint")
        self.status.setWordWrap(True)
        bottom.addWidget(self.status, 1)
        clear_btn = make_button("清空输出", "ghost")
        clear_btn.clicked.connect(self.output.clear)
        bottom.addWidget(clear_btn)
        layout.addLayout(bottom)

        controller.gatt_value.connect(self._on_value)

    # ------------------------------------------------------------------
    def set_device(self, device: Optional[DeviceInfo], services: List[GattServiceInfo]) -> None:
        address_changed = self.device is None or (device and device.address != self.device.address)
        self.device = device
        self._services = list(services or [])
        if address_changed:
            self.output.clear()
            self._subscribed.clear()
        if device is None:
            self.device_label.setText("未选择设备")
            self.count_pill.setText("0 服务")
            self._services_key = None
            self._populate([])
            return
        self.device_label.setText(device.display_name)
        self.count_pill.setText("%d 服务" % len(self._services))
        if not device.is_ble:
            self.banner.setText("该设备使用经典蓝牙传输。经典蓝牙没有 GATT；请使用系统音量/媒体控制或厂商 RFCOMM 协议。")
            self.banner.setVisible(True)
        else:
            self.banner.setVisible(False)
        fingerprint = (
            device.address,
            tuple(
                (s.uuid, tuple((c.uuid, tuple(c.properties)) for c in s.characteristics))
                for s in self._services
            ),
        )
        if fingerprint == self._services_key and self.tree.topLevelItemCount():
            return
        self._services_key = fingerprint
        self._populate(self._services)
        if device.connected and not self._services:
            self.status.setText("设备已连接但尚未发现服务，请稍候或重新连接。")

    def _populate(self, services: List[GattServiceInfo]) -> None:
        self.tree.clear()
        self._selected_char = None
        self._set_actions(None)
        if not services:
            item = QTreeWidgetItem(["连接 BLE 设备后可浏览 GATT 服务", "", "", ""])
            item.setDisabled(True)
            self.tree.addTopLevelItem(item)
            return
        for service in services:
            parent = QTreeWidgetItem(
                [
                    service.description or "未知服务",
                    "",
                    compact_uuid(service.uuid),
                    "%d 个特征值" % len(service.characteristics),
                ]
            )
            parent.setData(0, Qt.UserRole, {"kind": "service", "uuid": service.uuid})
            parent.setToolTip(0, service.uuid)
            parent.setForeground(0, Qt.white)
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            self.tree.addTopLevelItem(parent)
            for char in service.characteristics:
                child = QTreeWidgetItem(
                    [
                        "",
                        char.description or "特征值",
                        compact_uuid(char.uuid),
                        ", ".join(char.properties) or "—",
                    ]
                )
                child.setData(0, Qt.UserRole, {"kind": "characteristic", "char": char})
                child.setToolTip(1, char.uuid)
                parent.addChild(child)
            parent.setExpanded(True)

    def _selection_changed(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            self._set_actions(None)
            return
        data = items[0].data(0, Qt.UserRole) or {}
        if data.get("kind") != "characteristic":
            self._selected_char = None
            self._set_actions(None)
            self.char_label.setText("服务节点：展开后选择特征值")
            self.uuid_label.setText(data.get("uuid", ""))
            return
        char: GattCharacteristicInfo = data["char"]
        self._selected_char = char
        name = char.description or "特征值"
        self.char_label.setText("%s · %s" % (name, ", ".join(char.properties) or "无属性"))
        self.uuid_label.setText(char.uuid)
        self._set_actions(char)

    def _set_actions(self, char: Optional[GattCharacteristicInfo]) -> None:
        self.read_btn.setEnabled(bool(char and char.can_read))
        self.write_btn.setEnabled(bool(char and char.can_write))
        self.notify_btn.setEnabled(bool(char and char.can_notify))
        if char and self.device:
            key = (self.device.address, char.uuid)
            self.notify_btn.setText("取消订阅" if key in self._subscribed else "订阅")

    def _read(self) -> None:
        if not (self.device and self._selected_char):
            return
        self.controller.read_characteristic(self.device.address, self._selected_char.uuid)

    def _write(self) -> None:
        if not (self.device and self._selected_char):
            return
        try:
            data = encode_payload(self.input.text(), "hex" if self.mode.currentIndex() == 0 else "text")
        except CodecError as exc:
            QMessageBox.warning(self, "数据格式错误", str(exc))
            return
        if not data:
            QMessageBox.information(self, "没有数据", "请输入要写入的内容。")
            return
        self.controller.write_characteristic(
            self.device.address,
            self._selected_char.uuid,
            data,
            self.with_response.isChecked(),
        )

    def _notify(self) -> None:
        if not (self.device and self._selected_char):
            return
        key = (self.device.address, self._selected_char.uuid)
        if key in self._subscribed:
            self._subscribed.discard(key)
        else:
            self._subscribed.add(key)
        self._set_actions(self._selected_char)
        self.controller.toggle_notify(self.device.address, self._selected_char.uuid)

    def _on_value(self, address: str, uuid: str, data: object, source: str) -> None:
        if not self.device or address != self.device.address:
            return
        payload = bytes(data) if not isinstance(data, bytes) else data
        if len(payload) > MAX_GATT_BYTES:
            return
        stamp = time.strftime("%H:%M:%S")
        if source == "notify":
            text = "%s  通知  %s\n%s" % (stamp, compact_uuid(uuid), hexdump(payload))
        elif source == "write":
            text = "%s  写入  %s\n%s" % (stamp, compact_uuid(uuid), hexdump(payload))
        else:
            text = "%s  读取  %s  (%d bytes)\n%s" % (stamp, compact_uuid(uuid), len(payload), hexdump(payload))
        try:
            as_text = payload.decode("utf-8")
            if as_text.isprintable() and as_text.strip():
                text += "\n文本: %s" % as_text
        except UnicodeDecodeError:
            pass
        self.output.moveCursor(QTextCursor.End)
        self.output.insertPlainText(text + "\n")
        self.status.setText("最近数据：%s · %s" % (source, format_hex(payload)))
