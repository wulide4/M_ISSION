from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class HomePage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        title = QLabel("欢迎使用")
        title.setStyleSheet("""
            font-size: 28px;
            font-weight: bold;
            color: #00e5ff;
            margin-bottom: 8px;
        """)

        subtitle = QLabel("北斗/GNSS 电离层闪烁监测平台")
        subtitle.setStyleSheet("""
            font-size: 16px;
            color: #8b9bb4;
            margin-bottom: 30px;
        """)

        card_layout = QHBoxLayout()
        card_layout.setSpacing(20)

        card1 = self._make_card(
            "数据上传",
            "上传OBS/SP3/ATX等数据文件",
            "#2196f3",
            "📡"
        )
        card2 = self._make_card(
            "结果可视化",
            "查看闪烁指数计算结果",
            "#7c4dff",
            "📊"
        )
        card3 = self._make_card(
            "分析统计",
            "统计分析闪烁事件",
            "#00e676",
            "📈"
        )
        card4 = self._make_card(
            "系统设置",
            "配置算法参数和阈值",
            "#ff6d00",
            "⚙️"
        )

        card_layout.addWidget(card1)
        card_layout.addWidget(card2)
        card_layout.addWidget(card3)
        card_layout.addWidget(card4)

        info_box = self._make_info_box()

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(card_layout)
        layout.addWidget(info_box)
        layout.addStretch()

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
        icon_label.setStyleSheet(f"""
            font-size: 32px;
            color: {color};
        """)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            font-size: 16px;
            font-weight: bold;
            color: {color};
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc_label = QLabel(desc)
        desc_label.setStyleSheet("""
            font-size: 12px;
            color: #8b9bb4;
        """)
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

        title = QLabel("快速开始")
        title.setStyleSheet("""
            font-size: 14px;
            font-weight: bold;
            color: #00e5ff;
        """)

        steps = [
            "1. 进入「数据上传」页面，上传观测数据(OBS)、星历(SP3)、天线(ATX)文件",
            "2. 选择要计算的闪烁指数指标（默认ROTI）",
            "3. 点击「开始处理」进行计算",
            "4. 在「结果可视化」页面查看时序图和统计结果",
        ]

        for step in steps:
            label = QLabel(step)
            label.setStyleSheet("""
                font-size: 12px;
                color: #8b9bb4;
                padding: 4px 0;
            """)
            layout.addWidget(label)

        return box

    def update_projects(self, rows: list[dict]) -> None:
        pass

    def update_tasks(self, rows: list[dict]) -> None:
        pass
