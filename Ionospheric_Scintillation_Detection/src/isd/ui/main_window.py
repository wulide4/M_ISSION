from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QListWidgetItem,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from isd.application.bootstrap import AppContext
from isd.ui.pages.home_page import HomePage
from isd.ui.pages.analysis_page import AnalysisPage
from isd.ui.pages.project_page import DataUploadPage
from isd.ui.pages.report_page import ReportCenterPage
from isd.ui.pages.settings_page import SettingsPage
from isd.ui.pages.task_page import TaskManagementPage
from isd.ui.pages.visualization_page import VisualizationPage
from isd.ui.widgets.side_nav import SideNav
from isd.ui.widgets.top_bar import TopBar


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.setWindowTitle("北斗/GNSS 电离层闪烁监测软件平台")
        self.resize(1480, 900)
        self._apply_theme()

        self.nav = SideNav()
        self.stack = QStackedWidget()

        self.home_page = HomePage()
        self.data_upload_page = DataUploadPage(context.command_bus)
        self.task_page = TaskManagementPage(context.command_bus)
        self.visual_page = VisualizationPage(context.command_bus)
        self.analysis_page = AnalysisPage(context.command_bus)
        self.report_page = ReportCenterPage(context.command_bus)
        self.settings_page = SettingsPage(context.command_bus)

        self._add_page("首页", self.home_page)
        self._add_page("任务管理", self.task_page)
        self._add_page("数据上传与处理", self.data_upload_page)
        self._add_page("结果可视化", self.visual_page)
        self._add_page("分析统计", self.analysis_page)
        self._add_page("报告中心", self.report_page)
        self._add_page("系统设置", self.settings_page)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        self.nav.setCurrentRow(0)

        split = QSplitter()
        split.addWidget(self.nav)
        split.addWidget(self.stack)
        split.setSizes([220, 1260])

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(TopBar())
        layout.addWidget(split)
        self.setCentralWidget(root)

        status = QStatusBar()
        status.showMessage("READY")
        self.setStatusBar(status)

    def _apply_theme(self) -> None:
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#0a0e17"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#e0e6ed"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#121a2e"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#1a2540"))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#00e5ff"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#0a0e17"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#e0e6ed"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#1a2540"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e0e6ed"))
        palette.setColor(QPalette.ColorRole.BrightText, QColor("#ff1744"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#2196f3"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        self.setPalette(palette)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #0a0e17;
            }
            QWidget {
                background-color: #0a0e17;
                color: #e0e6ed;
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            }
            QLabel {
                color: #e0e6ed;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2196f3, stop:1 #7c4dff);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                min-height: 28px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #00e5ff, stop:1 #2196f3);
            }
            QPushButton:pressed {
                background: #7c4dff;
            }
            QPushButton[secondary="true"] {
                background: #1a2540;
                color: #e0e6ed;
                border: 1px solid #2a3a5c;
            }
            QPushButton[secondary="true"]:hover {
                border-color: #00e5ff;
                color: #00e5ff;
            }
            QLineEdit {
                background-color: #121a2e;
                color: #e0e6ed;
                border: 1px solid #2a3a5c;
                border-radius: 4px;
                padding: 6px 10px;
                min-height: 24px;
            }
            QLineEdit:focus {
                border-color: #00e5ff;
            }
            QGroupBox {
                background-color: #1a2540;
                border: 1px solid #2a3a5c;
                border-radius: 8px;
                margin-top: 12px;
                padding: 12px;
                font-weight: bold;
            }
            QGroupBox::title {
                color: #00e5ff;
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0 8px;
            }
            QTableWidget {
                background-color: #121a2e;
                color: #e0e6ed;
                border: 1px solid #2a3a5c;
                border-radius: 4px;
                gridline-color: #2a3a5c;
                selection-background-color: #2196f3;
            }
            QHeaderView::section {
                background-color: #1a2540;
                color: #00e5ff;
                padding: 6px;
                border: none;
                font-weight: bold;
            }
            QCheckBox {
                color: #e0e6ed;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 2px solid #2a3a5c;
                background-color: #121a2e;
            }
            QCheckBox::indicator:checked {
                background-color: #00e5ff;
                border-color: #00e5ff;
            }
            QCheckBox::indicator:hover {
                border-color: #00e5ff;
            }
            QProgressBar {
                background-color: #121a2e;
                border: 1px solid #2a3a5c;
                border-radius: 4px;
                text-align: center;
                color: #e0e6ed;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00e5ff, stop:1 #2196f3);
                border-radius: 3px;
            }
            QListWidget {
                background-color: #121a2e;
                color: #e0e6ed;
                border: 1px solid #2a3a5c;
                border-radius: 4px;
                outline: none;
            }
            QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid #2a3a5c;
            }
            QListWidget::item:selected {
                background-color: #2196f3;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            QStatusBar {
                background-color: #121a2e;
                color: #8b9bb4;
                border-top: 1px solid #2a3a5c;
            }
            QSplitter::handle {
                background-color: #2a3a5c;
            }
        """)

    def _add_page(self, title: str, page: QWidget) -> None:
        self.nav.addItem(QListWidgetItem(title))
        self.stack.addWidget(page)

    def _on_nav_changed(self, idx: int) -> None:
        _ = idx
        cur_proj = self.data_upload_page.current_project_id
        if cur_proj:
            self.visual_page.set_project(cur_proj)
            self.analysis_page.set_project(cur_proj)
            self.analysis_page.refresh()
            self.report_page.project_id_edit.setText(cur_proj)


def run(context: AppContext) -> int:
    app = QApplication.instance() or QApplication([])
    win = MainWindow(context)
    win.show()
    return app.exec()
