from __future__ import annotations

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
from isd.ui.pages.data_calc_page import DataCalculationPage
from isd.ui.pages.home_page import HomePage
from isd.ui.pages.analysis_page import AnalysisPage
from isd.ui.pages.batch_page import BatchPage
from isd.ui.pages.project_page import ProjectManagementPage
from isd.ui.pages.report_page import ReportCenterPage
from isd.ui.pages.settings_page import SettingsPage
from isd.ui.pages.visualization_page import VisualizationPage
from isd.ui.widgets.side_nav import SideNav
from isd.ui.widgets.top_bar import TopBar


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.setWindowTitle("北斗/GNSS 电离层闪烁监测软件平台 - Python MVP")
        self.resize(1480, 900)

        self.nav = SideNav()
        self.stack = QStackedWidget()

        self.home_page = HomePage()
        self.project_page = ProjectManagementPage(context.command_bus)
        self.data_calc_page = DataCalculationPage(context.command_bus, context.task_service)
        self.batch_page = BatchPage(context.command_bus)
        self.visual_page = VisualizationPage(context.command_bus)
        self.analysis_page = AnalysisPage(context.command_bus)
        self.report_page = ReportCenterPage(context.command_bus)
        self.settings_page = SettingsPage(context.command_bus)

        self._add_page("首页", self.home_page)
        self._add_page("项目管理", self.project_page)
        self._add_page("数据计算", self.data_calc_page)
        self._add_page("批处理", self.batch_page)
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

        self.project_page.refresh_projects()

    def _add_page(self, title: str, page: QWidget) -> None:
        self.nav.addItem(QListWidgetItem(title))
        self.stack.addWidget(page)

    def _on_nav_changed(self, idx: int) -> None:
        _ = idx
        cur_proj = self.project_page.current_project_id
        if cur_proj:
            self.data_calc_page.project_id_edit.setText(cur_proj)
            self.visual_page.set_project(cur_proj)
            self.batch_page.set_project(cur_proj)
            self.analysis_page.set_project(cur_proj)
            self.analysis_page.refresh()
            self.report_page.project_id_edit.setText(cur_proj)


def run(context: AppContext) -> int:
    app = QApplication.instance() or QApplication([])
    win = MainWindow(context)
    win.show()
    return app.exec()
