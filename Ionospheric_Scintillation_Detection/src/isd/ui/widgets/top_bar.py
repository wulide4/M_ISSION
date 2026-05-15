from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QHBoxLayout, QWidget, QFrame


class TopBar(QWidget):
    def __init__(self, title: str = "北斗/GNSS 电离层闪烁监测平台") -> None:
        super().__init__()
        self.setFixedHeight(56)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(16)

        icon_label = QLabel("◆")
        icon_label.setStyleSheet("""
            color: #00e5ff;
            font-size: 20px;
            font-weight: bold;
        """)

        title_label = QLabel(f"<b>{title}</b>")
        title_label.setStyleSheet("""
            color: #e0e6ed;
            font-size: 16px;
            font-weight: bold;
            letter-spacing: 1px;
        """)

        version_label = QLabel("v2.0")
        version_label.setStyleSheet("""
            color: #7c4dff;
            font-size: 11px;
            font-weight: bold;
            background-color: rgba(124, 77, 255, 0.2);
            padding: 3px 8px;
            border-radius: 10px;
        """)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setStyleSheet("background-color: #2a3a5c; max-width: 1px;")

        status_label = QLabel("● READY")
        status_label.setStyleSheet("""
            color: #00e676;
            font-size: 12px;
            font-weight: 500;
        """)

        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        layout.addWidget(version_label)
        layout.addStretch()
        layout.addWidget(separator)
        layout.addWidget(status_label)

        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0d1221, stop:1 #151d33);
                border-bottom: 1px solid #2a3a5c;
            }
        """)
