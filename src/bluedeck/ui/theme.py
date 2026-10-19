"""BlueDesk visual theme."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

BG = "#0b1018"
BG_ALT = "#0f1621"
CARD = "#131c2a"
CARD_ALT = "#172235"
BORDER = "#223047"
BORDER_HI = "#314563"
TEXT = "#edf3ff"
MUTED = "#92a2bd"
FAINT = "#657795"
ACCENT = "#5b8cff"
ACCENT_2 = "#7c6cff"
GREEN = "#56d6a0"
AMBER = "#f3b45f"
RED = "#ff7c86"
CYAN = "#55d7d0"
PINK = "#f58bc0"

QSS = """
* {
    font-family: "PingFang SC", "Microsoft YaHei UI", "Segoe UI", "Noto Sans CJK SC", sans-serif;
    font-size: 13px;
}
QMainWindow, QWidget#Root {
    background: #0b1018;
    color: #edf3ff;
}
QWidget {
    color: #edf3ff;
}
QFrame#TopBar {
    background: #0d1420;
    border-bottom: 1px solid #1b2738;
}
QFrame#Sidebar {
    background: #0e1521;
    border: 1px solid #1c293c;
    border-radius: 16px;
}
QFrame#DetailRoot {
    background: transparent;
}
QFrame#Card {
    background: #131c2a;
    border: 1px solid #223047;
    border-radius: 16px;
}
QFrame#SubCard {
    background: #172235;
    border: 1px solid #24344d;
    border-radius: 12px;
}
QFrame#DeviceCard {
    background: #131c2a;
    border: 1px solid #202e43;
    border-radius: 13px;
}
QFrame#DeviceCard:hover {
    background: #172235;
    border-color: #2b405f;
}
QFrame#DeviceCard[selected="true"] {
    background: #182642;
    border: 1px solid #5b8cff;
}
QFrame#Notice {
    background: #201d18;
    border: 1px solid #4b3c24;
    border-radius: 12px;
}
QFrame#InfoBanner {
    background: #142238;
    border: 1px solid #294565;
    border-radius: 12px;
}
QLabel {
    background: transparent;
}
QLabel#AppTitle {
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 0.4px;
}
QLabel#AppSubtitle, QLabel#Muted {
    color: #92a2bd;
}
QLabel#Faint {
    color: #657795;
    font-size: 12px;
}
QLabel#HeroTitle {
    font-size: 25px;
    font-weight: 700;
}
QLabel#SectionTitle {
    font-size: 15px;
    font-weight: 600;
}
QLabel#MetricValue {
    font-size: 24px;
    font-weight: 700;
}
QLabel#MetricValueSmall {
    font-size: 18px;
    font-weight: 600;
}
QLabel#MetricLabel {
    color: #92a2bd;
    font-size: 12px;
}
QLabel#PercentBig {
    font-size: 34px;
    font-weight: 700;
}
QLabel#Pill {
    background: #1b2940;
    color: #a9bbd8;
    border: 1px solid #293d5b;
    border-radius: 9px;
    padding: 2px 8px;
    font-size: 11px;
}
QLabel#Pill[tone="green"] {
    background: #133126;
    color: #68e0b0;
    border-color: #20533f;
}
QLabel#Pill[tone="blue"] {
    background: #162845;
    color: #8db4ff;
    border-color: #2c4c7a;
}
QLabel#Pill[tone="amber"] {
    background: #302617;
    color: #f4c477;
    border-color: #554122;
}
QLabel#Pill[tone="red"] {
    background: #331a20;
    color: #ff9aa2;
    border-color: #5b2a33;
}
QLabel#Pill[tone="pink"] {
    background: #301c2a;
    color: #f7a8cf;
    border-color: #59324a;
}
QLabel#BannerTitle {
    font-weight: 600;
    color: #dce9ff;
}
QLabel#BannerText {
    color: #90a4c4;
    font-size: 12px;
}
QPushButton {
    background: #1a2638;
    color: #dbe7fb;
    border: 1px solid #2a3d58;
    border-radius: 9px;
    padding: 7px 13px;
    min-height: 20px;
}
QPushButton:hover {
    background: #21314a;
    border-color: #3c567a;
}
QPushButton:pressed {
    background: #172235;
}
QPushButton:disabled {
    color: #62738d;
    background: #141d2b;
    border-color: #1d2a3d;
}
QPushButton[variant="primary"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #5b8cff, stop:1 #7467ff);
    border: 1px solid #7c9dff;
    color: #ffffff;
    font-weight: 600;
}
QPushButton[variant="primary"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6d9bff, stop:1 #8678ff);
}
QPushButton[variant="primary"]:disabled {
    background: #263148;
    border-color: #303d55;
    color: #7b8aa4;
}
QPushButton[variant="ghost"] {
    background: transparent;
    border: 1px solid #2b3b52;
}
QPushButton[variant="ghost"]:hover {
    background: #182335;
    border-color: #405a7c;
}
QPushButton[variant="danger"] {
    background: #2c1b22;
    border: 1px solid #5a2e39;
    color: #ff9aa2;
}
QPushButton[variant="danger"]:hover {
    background: #3b222b;
}
QPushButton[variant="media"] {
    background: #172235;
    border: 1px solid #283a55;
    border-radius: 12px;
    padding: 10px 8px;
    font-size: 14px;
}
QPushButton[variant="media"]:hover {
    background: #20304a;
    border-color: #45618a;
}
QPushButton[variant="dpi"] {
    background: #162033;
    border: 1px solid #263752;
    border-radius: 10px;
    padding: 9px 10px;
}
QPushButton[variant="dpi"]:checked {
    background: #20345b;
    border-color: #5b8cff;
    color: #ffffff;
    font-weight: 600;
}
QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 6px 10px;
    color: #9eafc9;
}
QToolButton:hover {
    background: #182335;
    color: #e8f0ff;
}
QToolButton#FilterChip {
    background: #111a28;
    border: 1px solid #202e43;
    border-radius: 10px;
    padding: 5px 10px;
    color: #8fa1bd;
}
QToolButton#FilterChip:hover {
    border-color: #334a6a;
    color: #dbe7fb;
}
QToolButton#FilterChip:checked {
    background: #1b2d4c;
    border-color: #41679b;
    color: #a9c6ff;
}
QToolButton#IconButton {
    background: #162133;
    border: 1px solid #243650;
    border-radius: 10px;
    padding: 7px;
}
QToolButton#IconButton:hover {
    background: #20304a;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #0f1724;
    border: 1px solid #24344c;
    border-radius: 9px;
    padding: 7px 10px;
    selection-background-color: #355b9c;
    color: #e7effd;
}
QLineEdit:focus, QComboBox:focus {
    border-color: #4c73b0;
}
QLineEdit::placeholder {
    color: #5f708b;
}
QComboBox {
    padding-right: 24px;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    background: #131c2a;
    border: 1px solid #2a3d58;
    border-radius: 8px;
    selection-background-color: #223657;
    padding: 4px;
}
QTextEdit, QPlainTextEdit, QTextBrowser {
    background: #0d1520;
    border: 1px solid #223047;
    border-radius: 10px;
    color: #cfe0f8;
    selection-background-color: #355b9c;
    padding: 6px;
}
QTreeWidget, QTreeView, QTableWidget {
    background: #0d1520;
    alternate-background-color: #101a29;
    border: 1px solid #223047;
    border-radius: 10px;
    color: #d8e5fa;
    selection-background-color: #20365a;
    selection-color: #ffffff;
    outline: none;
}
QTreeWidget::item, QTableWidget::item {
    padding: 5px;
    border-bottom: 1px solid #162233;
}
QHeaderView::section {
    background: #121d2c;
    color: #91a5c4;
    border: none;
    border-bottom: 1px solid #223047;
    padding: 7px;
    font-size: 11px;
    font-weight: 600;
}
QTabWidget::pane {
    border: 1px solid #202e43;
    border-radius: 14px;
    background: #0f1723;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #8598b5;
    padding: 9px 18px;
    margin-right: 4px;
    border: 1px solid transparent;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
    font-weight: 500;
}
QTabBar::tab:hover {
    color: #dce8fb;
    background: #131e2d;
}
QTabBar::tab:selected {
    color: #cfe0ff;
    background: #162338;
    border: 1px solid #293c58;
    border-bottom-color: #162338;
}
QSlider::groove:horizontal {
    height: 5px;
    background: #24344d;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5b8cff, stop:1 #8b7bff);
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 16px;
    height: 16px;
    margin: -6px 0;
    background: #f5f8ff;
    border: 2px solid #6f95ff;
    border-radius: 8px;
}
QSlider::groove:vertical {
    width: 5px;
    background: #24344d;
    border-radius: 2px;
}
QSlider::add-page:vertical {
    background: qlineargradient(x1:0, y1:1, x2:0, y2:0, stop:0 #5b8cff, stop:1 #8b7bff);
    border-radius: 2px;
}
QSlider::handle:vertical {
    height: 14px;
    width: 14px;
    margin: 0 -5px;
    background: #f5f8ff;
    border: 2px solid #6f95ff;
    border-radius: 7px;
}
QScrollArea {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    background: transparent;
    width: 9px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #2a3b54;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #3b5376;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
    border: none;
    height: 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 9px;
}
QScrollBar::handle:horizontal {
    background: #2a3b54;
    border-radius: 4px;
    min-width: 30px;
}
QSplitter::handle {
    background: transparent;
    width: 10px;
}
QStatusBar {
    background: #0d1420;
    border-top: 1px solid #1b2738;
    color: #8296b4;
}
QStatusBar::item {
    border: none;
}
QCheckBox {
    color: #a9bad3;
    spacing: 7px;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid #334863;
    background: #101a28;
}
QCheckBox::indicator:checked {
    background: #5b8cff;
    border-color: #7fa2ff;
}
QProgressBar {
    background: #1a2638;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #56d6a0, stop:1 #55d7d0);
    border-radius: 4px;
}
QToolTip {
    background: #172235;
    color: #e6efff;
    border: 1px solid #334a68;
    border-radius: 6px;
    padding: 5px 8px;
}
QDialog {
    background: #0d1420;
}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Base, QColor(BG_ALT))
    palette.setColor(QPalette.AlternateBase, QColor(CARD))
    palette.setColor(QPalette.Text, QColor(TEXT))
    palette.setColor(QPalette.Button, QColor(CARD))
    palette.setColor(QPalette.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipBase, QColor(CARD))
    palette.setColor(QPalette.ToolTipText, QColor(TEXT))
    app.setPalette(palette)
    font = QFont()
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(QSS)
