"""Communication / application log panel."""
from __future__ import annotations

import html
import time
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..controller import AppController
from ..models import LogEntry
from .widgets import make_button, make_pill

CATEGORIES = {
    "全部": "",
    "连接": "connect",
    "GATT": "gatt",
    "扫描": "scan",
    "音频": "audio",
    "数据": "data",
    "平台": "platform",
    "设备": "device",
    "演示": "demo",
    "日志": "log",
}

LEVEL_COLORS = {
    "DEBUG": "#657795",
    "INFO": "#8db4ff",
    "DATA": "#55d7d0",
    "WARN": "#f3b45f",
    "ERROR": "#ff7c86",
}


class LogPanel(QWidget):
    def __init__(self, controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._entries: List[LogEntry] = list(controller.log_store.entries)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)

        header = QHBoxLayout()
        title = QLabel("通信与运行日志")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        self.count_pill = make_pill("%d 条" % len(self._entries), "blue")
        header.addWidget(self.count_pill)
        header.addStretch(1)
        self.filter = QComboBox()
        for label in CATEGORIES:
            self.filter.addItem(label, CATEGORIES[label])
        self.filter.currentIndexChanged.connect(self._rebuild)
        header.addWidget(self.filter)
        self.search = QLineEdit()
        self.search.setPlaceholderText("过滤日志…")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(190)
        self.search.textChanged.connect(self._rebuild)
        header.addWidget(self.search)
        layout.addLayout(header)

        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(False)
        self.view.setFont(QFont("SF Mono, Menlo, Consolas, monospace", 11))
        self.view.document().setMaximumBlockCount(2500)
        layout.addWidget(self.view, 1)

        footer = QHBoxLayout()
        self.hint = QLabel("HEX 数据、连接状态、GATT 读写与错误都会记录。日志写入应用数据目录的 bluedeck.jsonl。")
        self.hint.setObjectName("Faint")
        self.hint.setWordWrap(True)
        footer.addWidget(self.hint, 1)
        export = make_button("导出日志", "ghost")
        export.clicked.connect(self._export)
        clear = make_button("清空", "ghost")
        clear.clicked.connect(self._clear)
        footer.addWidget(export)
        footer.addWidget(clear)
        layout.addLayout(footer)

        self._rebuild()

    def add_entry(self, entry: LogEntry) -> None:
        self._entries.append(entry)
        if len(self._entries) > 3000:
            self._entries = self._entries[-3000:]
        if self._accepts(entry):
            self._append(entry)
        self.count_pill.setText("%d 条" % len(self._entries))

    def _accepts(self, entry: LogEntry) -> bool:
        category = self.filter.currentData() or ""
        if category and entry.category != category:
            return False
        needle = self.search.text().strip().lower()
        if needle:
            haystack = " ".join(
                [entry.message, entry.address, entry.category, entry.level, entry.data]
            ).lower()
            if needle not in haystack:
                return False
        return True

    def _append(self, entry: LogEntry) -> None:
        bar = self.view.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 6
        stamp = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        color = LEVEL_COLORS.get(entry.level, "#aebed6")
        category = html.escape(entry.category)
        message = html.escape(entry.message).replace("\n", "<br>")
        address = html.escape(entry.address[:22]) if entry.address else ""
        row = (
            '<div style="margin:2px 0; font-family: SF Mono, Menlo, Consolas, monospace; font-size:11px;">'
            '<span style="color:#5f708b;">%s</span> '
            '<span style="color:%s; font-weight:600;">%-5s</span> '
            '<span style="color:#657795;">[%s]</span> '
            '%s<span style="color:#d8e5fa;">%s</span></div>'
            % (
                stamp,
                color,
                html.escape(entry.level),
                category,
                ('<span style="color:#899dbd;">%s</span> ' % address) if address else "",
                message,
            )
        )
        self.view.append(row)
        if at_bottom:
            self.view.moveCursor(QTextCursor.End)

    def _rebuild(self) -> None:
        self.view.clear()
        for entry in self._entries:
            if self._accepts(entry):
                self._append(entry)
        self.view.moveCursor(QTextCursor.End)

    def _export(self) -> None:
        default = str(Path.home() / "Desktop" / time.strftime("bluedesk-logs-%Y%m%d-%H%M.csv"))
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "导出日志",
            default,
            "CSV 文件 (*.csv);;JSON 文件 (*.json);;文本文件 (*.txt)",
        )
        if path:
            try:
                self.controller.export_logs(path)
            except OSError as exc:
                QMessageBox.warning(self, "导出失败", str(exc))

    def _clear(self) -> None:
        self.controller.clear_logs()
        self._entries.clear()
        self.view.clear()
        self.count_pill.setText("0 条")
