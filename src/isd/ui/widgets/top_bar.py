from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QHBoxLayout, QWidget, QFrame, QPushButton

from isd.ui.i18n import LanguageManager, tr


class TopBar(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(56)
        self._lm = LanguageManager.instance()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(16)

        self.icon_label = QLabel("◆")
        self.icon_label.setStyleSheet("""
            color: #00e5ff;
            font-size: 20px;
            font-weight: bold;
        """)

        self.title_label = QLabel(f"<b>{tr('app.title')}</b>")
        self.title_label.setStyleSheet("""
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

        self.status_label = QLabel("● READY")
        self.status_label.setStyleSheet("""
            color: #00e676;
            font-size: 12px;
            font-weight: 500;
        """)

        self.lang_btn = QPushButton(tr("lang.toggle"))
        self.lang_btn.setFixedSize(50, 28)
        self.lang_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 229, 255, 0.15);
                color: #00e5ff;
                border: 1px solid #00e5ff;
                border-radius: 14px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(0, 229, 255, 0.3);
            }
        """)
        self.lang_btn.clicked.connect(self._on_lang_toggle)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(version_label)
        layout.addStretch()
        layout.addWidget(separator)
        layout.addWidget(self.status_label)
        layout.addWidget(self.lang_btn)

        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0d1221, stop:1 #151d33);
                border-bottom: 1px solid #2a3a5c;
            }
        """)

        self._lm.language_changed.connect(self._retranslate)

    def _on_lang_toggle(self) -> None:
        self._lm.switch()

    def _retranslate(self) -> None:
        self.title_label.setText(f"<b>{tr('app.title')}</b>")
        self.lang_btn.setText(tr("lang.toggle"))
