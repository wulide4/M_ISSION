from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from isd.application import channels
from isd.application.command_bus import CommandBus


class ProjectManagementPage(QWidget):
    def __init__(self, bus: CommandBus) -> None:
        super().__init__()
        self.bus = bus
        self.current_project_id: str | None = None

        self.name_edit = QLineEdit("demo_project")
        self.root_edit = QLineEdit()
        self.desc_edit = QLineEdit()

        browse_btn = QPushButton("选择目录")
        browse_btn.clicked.connect(self._browse)

        create_btn = QPushButton("新建项目")
        create_btn.clicked.connect(self._create_project)

        open_btn = QPushButton("刷新项目列表")
        open_btn.clicked.connect(self.refresh_projects)
        delete_btn = QPushButton("删除选中项目")
        delete_btn.clicked.connect(self._delete_selected_project)

        scan_btn = QPushButton("扫描文件")
        scan_btn.clicked.connect(self._scan)
        rescan_btn = QPushButton("重扫项目(项目根目录)")
        rescan_btn.clicked.connect(self._rescan_project_root)

        self.projects_table = QTableWidget(0, 6)
        self.projects_table.setHorizontalHeaderLabels(["ID", "Name", "Root", "Updated", "RootOK", "WorkspaceOK"])
        self.projects_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.projects_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.projects_table.cellClicked.connect(self._select_project)

        self.files_table = QTableWidget(0, 6)
        self.files_table.setHorizontalHeaderLabels(["kind", "file", "station", "date", "sample(s)", "status"])

        self.stations_table = QTableWidget(0, 5)
        self.stations_table.setHorizontalHeaderLabels(["station", "systems", "receiver", "antenna", "coord"])

        self.dependency_table = QTableWidget(0, 7)
        self.dependency_table.setHorizontalHeaderLabels(
            ["date", "SP3", "CLK", "ATX", "NAV", "chain", "status"]
        )
        self.summary_label = QLabel("项目状态摘要：未选择项目")

        form = QFormLayout()
        form.addRow("项目名", self.name_edit)
        form.addRow("根目录", self.root_edit)
        form.addRow("描述", self.desc_edit)

        top = QHBoxLayout()
        top.addWidget(browse_btn)
        top.addWidget(create_btn)
        top.addWidget(scan_btn)
        top.addWidget(rescan_btn)
        top.addWidget(open_btn)
        top.addWidget(delete_btn)

        cfg_box = QGroupBox("项目管理")
        cfg_layout = QVBoxLayout(cfg_box)
        cfg_layout.addLayout(form)
        cfg_layout.addLayout(top)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>项目管理</h2>"))
        layout.addWidget(cfg_box)
        layout.addWidget(QLabel("项目列表"))
        layout.addWidget(self.projects_table)
        layout.addWidget(QLabel("文件校验结果"))
        layout.addWidget(self.files_table)
        layout.addWidget(QLabel("站点详情"))
        layout.addWidget(self.stations_table)
        layout.addWidget(QLabel("依赖匹配摘要"))
        layout.addWidget(self.dependency_table)
        layout.addWidget(self.summary_label)

    def _browse(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "Select project root")
        if p:
            self.root_edit.setText(p)

    def _create_project(self) -> None:
        if not self.root_edit.text().strip():
            QMessageBox.warning(self, "warn", "请选择根目录")
            return
        rsp = self.bus.dispatch(
            channels.PROJECT_CREATE,
            {
                "name": self.name_edit.text().strip(),
                "description": self.desc_edit.text().strip(),
                "rootPath": self.root_edit.text().strip(),
            },
        )
        if not rsp.success:
            QMessageBox.critical(self, "error", rsp.error.message if rsp.error else "create failed")
            return
        self.current_project_id = rsp.data["id"]
        self.refresh_projects()
        QMessageBox.information(self, "ok", f"项目已创建: {self.name_edit.text().strip()}")

    def refresh_projects(self) -> None:
        rsp = self.bus.dispatch(channels.PROJECT_LIST, {})
        if not rsp.success:
            QMessageBox.critical(
                self,
                "error",
                rsp.error.message if rsp.error else "project list failed",
            )
            return
        rows = rsp.data or []
        self.projects_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.projects_table.setItem(i, 0, QTableWidgetItem(r.get("id", "")))
            self.projects_table.setItem(i, 1, QTableWidgetItem(r.get("name", "")))
            self.projects_table.setItem(i, 2, QTableWidgetItem(r.get("root_path", "")))
            self.projects_table.setItem(i, 3, QTableWidgetItem(r.get("updated_at", "")))
            self.projects_table.setItem(i, 4, QTableWidgetItem("Y" if r.get("rootPathExists") else "N"))
            self.projects_table.setItem(i, 5, QTableWidgetItem("Y" if r.get("workspacePathExists") else "N"))

    def _select_project(self, row: int, col: int) -> None:
        _ = col
        item = self.projects_table.item(row, 0)
        if item:
            self.current_project_id = item.text()
            open_rsp = self.bus.dispatch(channels.PROJECT_OPEN, {"projectId": self.current_project_id})
            if open_rsp.success:
                project = open_rsp.data or {}
                self.root_edit.setText(project.get("root_path", ""))
                self.summary_label.setText(
                    f"项目状态摘要：project={project.get('name', '-')}, "
                    f"id={project.get('id', '-')}, root={project.get('root_path', '-')}"
                )

    def _delete_selected_project(self) -> None:
        row = self.projects_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "warn", "请先在项目列表选择一行")
            return
        project_id_item = self.projects_table.item(row, 0)
        project_name_item = self.projects_table.item(row, 1)
        if not project_id_item:
            QMessageBox.warning(self, "warn", "未找到项目ID")
            return
        project_id = project_id_item.text().strip()
        project_name = project_name_item.text().strip() if project_name_item else project_id

        confirm = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除项目 '{project_name}' 吗？\n这会删除项目记录、任务与结果。",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        rsp = self.bus.dispatch(channels.PROJECT_DELETE, {"projectId": project_id})
        if not rsp.success:
            QMessageBox.critical(self, "error", rsp.error.message if rsp.error else "delete failed")
            return

        if self.current_project_id == project_id:
            self.current_project_id = None
        self.refresh_projects()
        QMessageBox.information(self, "ok", f"项目已删除: {project_name}")

    def _scan(self) -> None:
        if not self.current_project_id:
            QMessageBox.warning(self, "warn", "先选择项目")
            return
        payload = {"projectId": self.current_project_id}
        if self.root_edit.text().strip():
            payload["paths"] = [self.root_edit.text().strip()]
        payload["metrics"] = ["SIGMA_PHI_F"]
        rsp = self.bus.dispatch(channels.PROJECT_SCAN_FILES, payload)
        self._apply_scan_response(rsp)

    def _rescan_project_root(self) -> None:
        if not self.current_project_id:
            QMessageBox.warning(self, "warn", "先选择项目")
            return
        rsp = self.bus.dispatch(
            channels.PROJECT_SCAN_FILES,
            {"projectId": self.current_project_id, "metrics": ["SIGMA_PHI_F"]},
        )
        self._apply_scan_response(rsp)

    def _apply_scan_response(self, rsp) -> None:
        if not rsp.success:
            QMessageBox.critical(self, "error", rsp.error.message if rsp.error else "scan failed")
            return

        files = rsp.data.get("files", [])
        stations = rsp.data.get("stations", [])
        dependency = rsp.data.get("dependencySummary", {})
        summary = rsp.data.get("summary", {})

        self.files_table.setRowCount(len(files))
        for i, f in enumerate(files):
            self.files_table.setItem(i, 0, QTableWidgetItem(f.get("kind", "")))
            self.files_table.setItem(i, 1, QTableWidgetItem(f.get("file_name", "")))
            self.files_table.setItem(i, 2, QTableWidgetItem(f.get("station_id", "")))
            self.files_table.setItem(i, 3, QTableWidgetItem(str(f.get("file_date", ""))))
            self.files_table.setItem(i, 4, QTableWidgetItem(str(f.get("sampling_interval_sec", ""))))
            self.files_table.setItem(i, 5, QTableWidgetItem(f.get("validation_status", "")))

        self.stations_table.setRowCount(len(stations))
        for i, s in enumerate(stations):
            self.stations_table.setItem(i, 0, QTableWidgetItem(s.get("station_code", "")))
            self.stations_table.setItem(i, 1, QTableWidgetItem(",".join(s.get("systems", []))))
            self.stations_table.setItem(i, 2, QTableWidgetItem(str(s.get("receiver_model", ""))))
            self.stations_table.setItem(i, 3, QTableWidgetItem(str(s.get("antenna_model", ""))))
            self.stations_table.setItem(i, 4, QTableWidgetItem(str(s.get("coordinate_source", ""))))

        dates = sorted(dependency.keys())
        self.dependency_table.setRowCount(len(dates))
        for i, day in enumerate(dates):
            row = dependency.get(day, {})
            self.dependency_table.setItem(i, 0, QTableWidgetItem(day))
            self.dependency_table.setItem(i, 1, QTableWidgetItem(str(row.get("SP3", ""))))
            self.dependency_table.setItem(i, 2, QTableWidgetItem(str(row.get("CLK", ""))))
            self.dependency_table.setItem(i, 3, QTableWidgetItem(str(row.get("ATX", ""))))
            self.dependency_table.setItem(i, 4, QTableWidgetItem(str(row.get("NAV", ""))))
            self.dependency_table.setItem(i, 5, QTableWidgetItem(str(row.get("chainLevel", ""))))
            self.dependency_table.setItem(i, 6, QTableWidgetItem(str(row.get("status", ""))))

        state = summary.get("projectState", "UNKNOWN")
        self.summary_label.setText(
            "项目状态摘要："
            f"state={state}, files={summary.get('fileCount', 0)}, "
            f"stations={summary.get('stationCount', 0)}, "
            f"matched={summary.get('matchedFileCount', 0)}, "
            f"issues={summary.get('scanIssueCount', 0)}, "
            f"readyDates={summary.get('readyDateCount', 0)}/{summary.get('dependencyDateCount', 0)}"
        )
