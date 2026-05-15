from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QFrame,
    QVBoxLayout,
    QWidget,
)

from isd.application import channels


class TaskManagementPage(QWidget):
    def __init__(self, bus) -> None:
        super().__init__()
        self.bus = bus
        self._refresh_timer: QTimer | None = None
        self._build_ui()
        self._start_auto_refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("任务管理")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #00e5ff; margin: 10px 0;")
        layout.addWidget(title)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #8b9bb4; font-size: 13px;")
        layout.addWidget(self.status_label)

        self.task_list = QListWidget()
        self.task_list.setMinimumHeight(400)

        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("刷新")
        refresh_btn.setProperty("secondary", "true")
        refresh_btn.clicked.connect(self._refresh_task_list)

        stop_btn = QPushButton("停止")
        stop_btn.setProperty("secondary", "true")
        stop_btn.clicked.connect(self._stop_selected_task)

        force_delete_btn = QPushButton("删除任务")
        force_delete_btn.setStyleSheet("""
            QPushButton {
                background: #ff1744;
                color: white;
                font-weight: bold;
                min-height: 28px;
                border: none;
                border-radius: 4px;
                padding: 4px 16px;
            }
            QPushButton:hover {
                background: #ff4569;
            }
        """)
        force_delete_btn.clicked.connect(self._force_delete_selected_task)

        cleanup_btn = QPushButton("清理已完成")
        cleanup_btn.setProperty("secondary", "true")
        cleanup_btn.clicked.connect(self._cleanup_completed)

        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(stop_btn)
        btn_layout.addWidget(force_delete_btn)
        btn_layout.addWidget(cleanup_btn)
        btn_layout.addStretch()

        layout.addWidget(self.task_list)
        layout.addLayout(btn_layout)
        layout.addStretch()

        self._refresh_task_list()

    def _start_auto_refresh(self) -> None:
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_task_list)
        self._refresh_timer.start(5000)

    def _refresh_task_list(self) -> None:
        self.task_list.clear()
        rsp = self.bus.dispatch(channels.TASK_LIST, {})
        if not rsp.success:
            self.status_label.setText("加载失败")
            return

        tasks = rsp.data or []
        running = sum(1 for t in tasks if t.get("status") == "RUNNING")
        completed = sum(1 for t in tasks if t.get("status") == "COMPLETED")
        self.status_label.setText(f"共 {len(tasks)} 个任务 | 运行中: {running} | 已完成: {completed}")

        for task in tasks:
            task_id = task.get("id", "")
            status = task.get("status", "")
            name = task.get("name", "")
            summary = task.get("summary") or ""

            status_color = {
                "RUNNING": QColor("#00e676"),
                "COMPLETED": QColor("#2196f3"),
                "FAILED": QColor("#ff1744"),
                "CANCELLED": QColor("#ff6d00"),
                "READY": QColor("#8b9bb4"),
            }.get(status, QColor("#ffffff"))

            indicator = {
                "RUNNING": "●",
                "COMPLETED": "●",
                "FAILED": "●",
                "CANCELLED": "○",
                "READY": "○",
            }.get(status, "○")

            text = f"{indicator} {name} | {status} | {summary} | {task_id[:16]}..."
            item = QListWidgetItem(text)
            item.setForeground(QBrush(status_color))
            item.setData(Qt.ItemDataRole.UserRole, task)
            self.task_list.addItem(item)

    def _stop_selected_task(self) -> None:
        item = self.task_list.currentItem()
        if not item:
            QMessageBox.warning(self, "警告", "请先选择要停止的任务")
            return
        task = item.data(Qt.ItemDataRole.UserRole)
        task_id = task.get("id")
        if not task_id:
            return
        self.bus.dispatch(channels.TASK_STOP, {"taskId": task_id})
        self._refresh_task_list()

    def _force_delete_selected_task(self) -> None:
        item = self.task_list.currentItem()
        if not item:
            QMessageBox.warning(self, "警告", "请先选择要删除的任务")
            return
        task = item.data(Qt.ItemDataRole.UserRole)
        task_id = task.get("id")
        if not task_id:
            return
        reply = QMessageBox.question(
            self, "确认", f"确定要删除任务 {task_id[:20]} 吗？\n这将删除所有相关数据且无法恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        rsp = self.bus.dispatch(channels.TASK_DELETE, {"taskId": task_id, "force": True})
        if rsp.success:
            self._refresh_task_list()
        else:
            QMessageBox.critical(self, "错误", f"删除失败: {rsp.error.message if rsp.error else '未知错误'}")

    def _cleanup_completed(self) -> None:
        reply = QMessageBox.question(
            self, "确认", "确定要删除所有已取消和已完成的任务吗？\n这将删除所有相关数据且无法恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        rsp = self.bus.dispatch(channels.TASK_LIST, {})
        if not rsp.success:
            return

        deleted = 0
        for task in rsp.data or []:
            status = task.get("status", "")
            if status in ("COMPLETED", "CANCELLED", "FAILED"):
                task_id = task.get("id")
                if task_id:
                    result = self.bus.dispatch(channels.TASK_DELETE, {"taskId": task_id})
                    if result.success:
                        deleted += 1

        self._refresh_task_list()
        QMessageBox.information(self, "完成", f"已删除 {deleted} 个任务")
