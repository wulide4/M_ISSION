from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from isd.application import channels
from isd.ui.i18n import LanguageManager, tr


class TaskManagementPage(QWidget):
    def __init__(self, bus) -> None:
        super().__init__()
        self.bus = bus
        self._lm = LanguageManager.instance()
        self._refresh_timer: QTimer | None = None
        self._build_ui()
        self._start_auto_refresh()
        self._lm.language_changed.connect(self._retranslate)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.title_label = QLabel(tr("task.title"))
        self.title_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #00e5ff; margin: 10px 0;")
        layout.addWidget(self.title_label)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #8b9bb4; font-size: 13px;")
        layout.addWidget(self.status_label)

        self.task_list = QListWidget()
        self.task_list.setMinimumHeight(400)

        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton(tr("task.btn.refresh"))
        self.refresh_btn.setProperty("secondary", "true")
        self.refresh_btn.clicked.connect(self._refresh_task_list)

        self.stop_btn = QPushButton(tr("task.btn.stop"))
        self.stop_btn.setProperty("secondary", "true")
        self.stop_btn.clicked.connect(self._stop_selected_task)

        self.force_delete_btn = QPushButton(tr("task.btn.delete"))
        self.force_delete_btn.setStyleSheet("""
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
        self.force_delete_btn.clicked.connect(self._force_delete_selected_task)

        self.cleanup_btn = QPushButton(tr("task.btn.cleanup"))
        self.cleanup_btn.setProperty("secondary", "true")
        self.cleanup_btn.clicked.connect(self._cleanup_completed)

        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addWidget(self.force_delete_btn)
        btn_layout.addWidget(self.cleanup_btn)
        btn_layout.addStretch()

        layout.addWidget(self.task_list)
        layout.addLayout(btn_layout)
        layout.addStretch()

        self._refresh_task_list()

    def _retranslate(self) -> None:
        self.title_label.setText(tr("task.title"))
        self.refresh_btn.setText(tr("task.btn.refresh"))
        self.stop_btn.setText(tr("task.btn.stop"))
        self.force_delete_btn.setText(tr("task.btn.delete"))
        self.cleanup_btn.setText(tr("task.btn.cleanup"))

    def _start_auto_refresh(self) -> None:
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_task_list)
        self._refresh_timer.start(5000)

    def _refresh_task_list(self) -> None:
        self.task_list.clear()
        rsp = self.bus.dispatch(channels.TASK_LIST, {})
        if not rsp.success:
            self.status_label.setText(tr("task.status.load_failed"))
            return

        tasks = rsp.data or []
        running = sum(1 for t in tasks if t.get("status") == "RUNNING")
        completed = sum(1 for t in tasks if t.get("status") == "COMPLETED")
        self.status_label.setText(tr("task.status.summary").format(len(tasks), running, completed))

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
            QMessageBox.warning(self, tr("dlg.warning"), tr("task.warn.select_stop"))
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
            QMessageBox.warning(self, tr("dlg.warning"), tr("task.warn.select_delete"))
            return
        task = item.data(Qt.ItemDataRole.UserRole)
        task_id = task.get("id")
        if not task_id:
            return
        reply = QMessageBox.question(
            self, tr("dlg.confirm"), tr("task.confirm.delete").format(task_id[:20]),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        rsp = self.bus.dispatch(channels.TASK_DELETE, {"taskId": task_id, "force": True})
        if rsp.success:
            self._refresh_task_list()
        else:
            QMessageBox.critical(self, tr("dlg.error"), tr("task.error.delete_failed").format(
                rsp.error.message if rsp.error else ""))

    def _cleanup_completed(self) -> None:
        reply = QMessageBox.question(
            self, tr("dlg.confirm"), tr("task.confirm.cleanup"),
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
        QMessageBox.information(self, tr("dlg.success"), tr("task.info.deleted").format(deleted))
