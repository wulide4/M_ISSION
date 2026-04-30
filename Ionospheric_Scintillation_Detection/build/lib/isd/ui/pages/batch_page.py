from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from isd.application import channels
from isd.application.command_bus import CommandBus

_TERMINAL_STATUS = {"COMPLETED", "FAILED", "CANCELLED", "PARTIAL_COMPLETED"}


class BatchPage(QWidget):
    def __init__(self, bus: CommandBus) -> None:
        super().__init__()
        self.bus = bus
        self.project_id: str | None = None
        self._task_rows: list[dict] = []
        self._queue_ids: list[str] = []
        self._queue_index = 0

        self.status_label = QLabel("队列状态: idle")
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["TaskId", "Name", "Status", "Type", "CreatedAt", "Summary"])

        refresh_btn = QPushButton("刷新队列")
        refresh_btn.clicked.connect(self.refresh)
        start_btn = QPushButton("开始选中")
        start_btn.clicked.connect(lambda: self._act_selected(channels.TASK_START))
        pause_btn = QPushButton("暂停选中")
        pause_btn.clicked.connect(lambda: self._act_selected(channels.TASK_PAUSE))
        resume_btn = QPushButton("继续选中")
        resume_btn.clicked.connect(lambda: self._act_selected(channels.TASK_RESUME))
        stop_btn = QPushButton("停止选中")
        stop_btn.clicked.connect(lambda: self._act_selected(channels.TASK_STOP))
        retry_btn = QPushButton("重试选中")
        retry_btn.clicked.connect(lambda: self._act_selected(channels.TASK_RETRY))

        start_all_btn = QPushButton("顺序运行全部READY")
        start_all_btn.clicked.connect(self.start_ready_queue)
        stop_all_btn = QPushButton("停止自动队列")
        stop_all_btn.clicked.connect(self.stop_ready_queue)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>批处理</h2>"))
        layout.addWidget(self.status_label)

        row1 = QHBoxLayout()
        row1.addWidget(refresh_btn)
        row1.addWidget(start_btn)
        row1.addWidget(pause_btn)
        row1.addWidget(resume_btn)
        row1.addWidget(stop_btn)
        row1.addWidget(retry_btn)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(start_all_btn)
        row2.addWidget(stop_all_btn)
        row2.addStretch(1)
        layout.addLayout(row2)
        layout.addWidget(self.table)

        self.queue_timer = QTimer(self)
        self.queue_timer.setInterval(1500)
        self.queue_timer.timeout.connect(self._tick_queue)

    def set_project(self, project_id: str) -> None:
        self.project_id = project_id
        self.refresh()

    def refresh(self) -> None:
        payload = {"projectId": self.project_id} if self.project_id else {}
        rsp = self.bus.dispatch(channels.TASK_LIST, payload)
        if not rsp.success:
            return
        self._task_rows = rsp.data or []
        self.table.setRowCount(len(self._task_rows))
        for i, row in enumerate(self._task_rows):
            self.table.setItem(i, 0, QTableWidgetItem(row.get("id", "")))
            self.table.setItem(i, 1, QTableWidgetItem(row.get("name", "")))
            self.table.setItem(i, 2, QTableWidgetItem(row.get("status", "")))
            self.table.setItem(i, 3, QTableWidgetItem(row.get("task_type", "")))
            self.table.setItem(i, 4, QTableWidgetItem(row.get("created_at", "")))
            self.table.setItem(i, 5, QTableWidgetItem(row.get("summary", "") or ""))

    def _selected_task_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        return item.text().strip()

    def _act_selected(self, action: str) -> None:
        task_id = self._selected_task_id()
        if not task_id:
            QMessageBox.warning(self, "warn", "请选择任务")
            return
        rsp = self.bus.dispatch(action, {"taskId": task_id})
        if not rsp.success:
            QMessageBox.warning(self, "warn", rsp.error.message if rsp.error else "任务操作失败")
            return
        self.refresh()

    def start_ready_queue(self) -> None:
        self.refresh()
        ready_tasks = [x for x in self._task_rows if x.get("status") == "READY"]
        if not ready_tasks:
            QMessageBox.information(self, "info", "当前没有 READY 任务")
            return
        ready_tasks.sort(key=lambda x: x.get("created_at", ""))
        self._queue_ids = [x["id"] for x in ready_tasks if x.get("id")]
        self._queue_index = 0
        self._start_queue_current()
        self.queue_timer.start()

    def stop_ready_queue(self) -> None:
        self.queue_timer.stop()
        self._queue_ids = []
        self._queue_index = 0
        self.status_label.setText("队列状态: stopped")

    def _start_queue_current(self) -> None:
        if self._queue_index >= len(self._queue_ids):
            self.stop_ready_queue()
            self.status_label.setText("队列状态: completed")
            return
        task_id = self._queue_ids[self._queue_index]
        rsp = self.bus.dispatch(channels.TASK_START, {"taskId": task_id})
        if rsp.success:
            self.status_label.setText(
                f"队列状态: running ({self._queue_index + 1}/{len(self._queue_ids)}) task={task_id}"
            )
        else:
            self.status_label.setText(
                f"队列状态: start failed ({self._queue_index + 1}/{len(self._queue_ids)}) task={task_id}"
            )
            self._queue_index += 1
            self._start_queue_current()

    def _tick_queue(self) -> None:
        if not self._queue_ids:
            return
        self.refresh()
        if self._queue_index >= len(self._queue_ids):
            self.stop_ready_queue()
            return
        current_id = self._queue_ids[self._queue_index]
        row = next((x for x in self._task_rows if x.get("id") == current_id), None)
        if not row:
            self._queue_index += 1
            self._start_queue_current()
            return
        status = row.get("status")
        if status in _TERMINAL_STATUS:
            self._queue_index += 1
            self._start_queue_current()

