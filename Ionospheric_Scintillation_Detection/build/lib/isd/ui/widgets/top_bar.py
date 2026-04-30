from __future__ import annotations

from PySide6.QtWidgets import QLabel, QHBoxLayout, QWidget


class TopBar(QWidget):
    def __init__(self, title: str = "Ionospheric Scintillation Detection") -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.addWidget(QLabel(f"<b>{title}</b>"))
        layout.addStretch(1)
