from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


class HomePage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.recent_projects = QTableWidget(0, 3)
        self.recent_projects.setHorizontalHeaderLabels(["Project", "Path", "Updated"])

        self.recent_tasks = QTableWidget(0, 3)
        self.recent_tasks.setHorizontalHeaderLabels(["Task", "Status", "Created"])

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>首页</h2>"))
        layout.addWidget(QLabel("最近项目"))
        layout.addWidget(self.recent_projects)
        layout.addWidget(QLabel("最近任务"))
        layout.addWidget(self.recent_tasks)

    def update_projects(self, rows: list[dict]) -> None:
        self.recent_projects.setRowCount(len(rows))
        for i, r in enumerate(rows[:10]):
            self.recent_projects.setItem(i, 0, QTableWidgetItem(r.get("name", "")))
            self.recent_projects.setItem(i, 1, QTableWidgetItem(r.get("root_path", "")))
            self.recent_projects.setItem(i, 2, QTableWidgetItem(r.get("updated_at", "")))

    def update_tasks(self, rows: list[dict]) -> None:
        self.recent_tasks.setRowCount(len(rows))
        for i, r in enumerate(rows[:10]):
            self.recent_tasks.setItem(i, 0, QTableWidgetItem(r.get("name", "")))
            self.recent_tasks.setItem(i, 1, QTableWidgetItem(r.get("status", "")))
            self.recent_tasks.setItem(i, 2, QTableWidgetItem(r.get("created_at", "")))
