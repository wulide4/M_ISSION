from __future__ import annotations

from PySide6.QtWidgets import QLabel, QHBoxLayout, QWidget


class StatusBarWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.label = QLabel("READY")
        layout = QHBoxLayout(self)
        layout.addWidget(self.label)
        layout.addStretch(1)

    def set_text(self, text: str) -> None:
        self.label.setText(text)
