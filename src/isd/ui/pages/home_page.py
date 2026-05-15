from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from isd.ui.i18n import LanguageManager, tr


class HomePage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._lm = LanguageManager.instance()
        self._build_ui()
        self._lm.language_changed.connect(self._retranslate)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        self.title_label = QLabel(tr("home.welcome"))
        self.title_label.setStyleSheet("""
            font-size: 28px;
            font-weight: bold;
            color: #00e5ff;
            margin-bottom: 8px;
        """)

        self.subtitle_label = QLabel(tr("home.subtitle"))
        self.subtitle_label.setStyleSheet("""
            font-size: 16px;
            color: #8b9bb4;
            margin-bottom: 30px;
        """)

        card_layout = QHBoxLayout()
        card_layout.setSpacing(20)

        self.card1 = self._make_card(
            tr("home.card.upload.title"),
            tr("home.card.upload.desc"),
            "#2196f3",
            "📡"
        )
        self.card2 = self._make_card(
            tr("home.card.visual.title"),
            tr("home.card.visual.desc"),
            "#7c4dff",
            "📊"
        )
        self.card3 = self._make_card(
            tr("home.card.analysis.title"),
            tr("home.card.analysis.desc"),
            "#00e676",
            "📈"
        )
        self.card4 = self._make_card(
            tr("home.card.settings.title"),
            tr("home.card.settings.desc"),
            "#ff6d00",
            "⚙️"
        )

        card_layout.addWidget(self.card1)
        card_layout.addWidget(self.card2)
        card_layout.addWidget(self.card3)
        card_layout.addWidget(self.card4)

        self.info_box = self._make_info_box()

        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)
        layout.addLayout(card_layout)
        layout.addWidget(self.info_box)
        layout.addStretch()

    def _retranslate(self) -> None:
        self.title_label.setText(tr("home.welcome"))
        self.subtitle_label.setText(tr("home.subtitle"))

        for card, title_key, desc_key in [
            (self.card1, "home.card.upload.title", "home.card.upload.desc"),
            (self.card2, "home.card.visual.title", "home.card.visual.desc"),
            (self.card3, "home.card.analysis.title", "home.card.analysis.desc"),
            (self.card4, "home.card.settings.title", "home.card.settings.desc"),
        ]:
            # card layout: icon, title, desc
            layout = card.layout()
            if layout and layout.count() >= 3:
                title_w = layout.itemAt(1).widget()
                desc_w = layout.itemAt(2).widget()
                if title_w:
                    title_w.setText(tr(title_key))
                if desc_w:
                    desc_w.setText(tr(desc_key))

        # Update info box
        self._update_info_box()

    def _update_info_box(self) -> None:
        layout = self.info_box.layout()
        if not layout:
            return
        # Clear existing widgets
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        title = QLabel(tr("home.quickstart"))
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #00e5ff;")
        layout.addWidget(title)

        for key in ("home.step1", "home.step2", "home.step3", "home.step4"):
            label = QLabel(tr(key))
            label.setStyleSheet("font-size: 12px; color: #8b9bb4; padding: 4px 0;")
            layout.addWidget(label)

    def _make_card(self, title: str, desc: str, color: str, icon: str) -> QWidget:
        card = QFrame()
        card.setFrameShape(QFrame.Shape.NoFrame)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #1a2540;
                border: 1px solid #2a3a5c;
                border-radius: 12px;
                padding: 20px;
            }}
            QFrame:hover {{
                border-color: {color};
                background-color: rgba(33, 150, 243, 0.1);
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"font-size: 32px; color: {color};")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {color};")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc_label = QLabel(desc)
        desc_label.setStyleSheet("font-size: 12px; color: #8b9bb4;")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)

        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        layout.addWidget(desc_label)

        return card

    def _make_info_box(self) -> QWidget:
        box = QFrame()
        box.setFrameShape(QFrame.Shape.NoFrame)
        box.setStyleSheet("""
            QFrame {
                background-color: #121a2e;
                border: 1px solid #2a3a5c;
                border-radius: 8px;
                padding: 16px;
            }
        """)

        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        title = QLabel(tr("home.quickstart"))
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #00e5ff;")
        layout.addWidget(title)

        for key in ("home.step1", "home.step2", "home.step3", "home.step4"):
            label = QLabel(tr(key))
            label.setStyleSheet("font-size: 12px; color: #8b9bb4; padding: 4px 0;")
            layout.addWidget(label)

        return box

    def update_projects(self, rows: list[dict]) -> None:
        pass

    def update_tasks(self, rows: list[dict]) -> None:
        pass
