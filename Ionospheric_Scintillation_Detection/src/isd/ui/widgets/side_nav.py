from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView


class SideNav(QListWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self.setStyleSheet("""
            QListWidget {
                background-color: #0a0e17;
                border: none;
                padding: 8px 0;
                outline: none;
            }
            QListWidget::item {
                color: #8b9bb4;
                padding: 14px 20px;
                border: none;
                border-left: 3px solid transparent;
                margin: 2px 0;
                font-size: 14px;
                font-weight: 500;
                transition: all 0.2s ease;
            }
            QListWidget::item:hover {
                color: #e0e6ed;
                background-color: rgba(33, 150, 243, 0.1);
                border-left-color: #2196f3;
            }
            QListWidget::item:selected {
                color: #00e5ff;
                background-color: rgba(0, 229, 255, 0.15);
                border-left-color: #00e5ff;
                font-weight: bold;
            }
        """)
