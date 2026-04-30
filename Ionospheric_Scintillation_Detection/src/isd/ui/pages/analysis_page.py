from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from isd.application import channels

# ---------- Chinese labels ----------

METRIC_NAMES = {
    "ROTI": "ROTI (电离层变化率总电子含量)",
    "AATR": "AATR (绝对电离层变化率)",
    "IAATR": "IAATR (瞬时绝对电离层变化率)",
    "DIXSG": "DIXSG (空间梯度扰动指数)",
    "SIGMA_PHI_F": "σφf (振幅闪烁指数)",
}

METRIC_UNITS = {
    "ROTI": "TECU/min",
    "AATR": "TECU/min",
    "IAATR": "TECU/min",
    "DIXSG": "无量纲",
    "SIGMA_PHI_F": "rad",
}

METRIC_THRESHOLDS = {
    "ROTI": (0.5, "Pi et al. (1997)"),
    "AATR": (0.2, "Sanz et al. (2014)"),
    "IAATR": (0.2, "Sanz et al. (2014)"),
    "DIXSG": (0.5, "Jakowski et al. (2012)"),
    "SIGMA_PHI_F": (0.3, "Ahmed et al. (2015)"),
}

SYSTEM_NAMES = {
    "GPS": "GPS",
    "GLO": "GLONASS",
    "GAL": "Galileo",
    "BDS": "BeiDou",
}

CHAIN_NAMES = {
    "FORMAL": "正式链",
    "DEGRADED": "降级链",
    "EXPERIMENTAL": "实验链",
    "SYNTHETIC": "合成数据",
}


class AnalysisPage(QWidget):
    def __init__(self, bus) -> None:
        super().__init__()
        self.bus = bus
        self.project_id: str | None = None
        self._rows: list[dict] = []
        self._all_rows: list[dict] = []
        self._available_metrics: list[str] = []
        self._available_stations: list[str] = []
        self._refresh_timer: QTimer | None = None

        self.task_selector = QComboBox()
        self.task_selector.setMinimumWidth(300)
        self.task_selector.currentTextChanged.connect(self._on_task_selector_changed)

        self.metric_filter = QComboBox()
        self.metric_filter.setEditable(True)
        self.metric_filter.setPlaceholderText("输入指标名称筛选...")
        self.metric_filter.setMinimumWidth(150)

        self.station_filter = QComboBox()
        self.station_filter.setEditable(True)
        self.station_filter.setPlaceholderText("输入站点名称筛选...")
        self.station_filter.setMinimumWidth(150)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["指标名称", "数量", "最小值", "最大值", "均值", "阈值", "事件总数", "站点", "评估"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._render_detail)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("color: #8b9bb4; font-size: 12px; padding: 4px 0;")

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._load_task_list)
        refresh_btn.setProperty("secondary", "true")

        delete_all_btn = QPushButton("清空结果")
        delete_all_btn.setStyleSheet("""
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
        delete_all_btn.clicked.connect(self._delete_all_results)

        form = QFormLayout()
        form.addRow("指标筛选", self.metric_filter)
        form.addRow("站点筛选", self.station_filter)

        filter_box = QGroupBox("筛选条件")
        filter_box_layout = QVBoxLayout(filter_box)
        filter_box_layout.addLayout(form)

        top = QHBoxLayout()
        top.addWidget(filter_box)
        top.addWidget(refresh_btn)
        top.addWidget(delete_all_btn)

        layout = QVBoxLayout(self)
        title = QLabel("分析统计")
        title.setStyleSheet("""
            font-size: 22px;
            font-weight: bold;
            color: #00e5ff;
            margin: 10px 0;
        """)
        layout.addWidget(title)

        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("选择任务:"))
        selector_layout.addWidget(self.task_selector)
        selector_layout.addStretch()
        layout.addLayout(selector_layout)

        layout.addLayout(top)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.table)

        detail_label = QLabel("指标明细")
        detail_label.setStyleSheet("color: #8b9bb4; font-weight: bold;")
        layout.addWidget(detail_label)
        layout.addWidget(self.detail)

        self.metric_filter.currentIndexChanged.connect(self._on_filter_changed)
        self.metric_filter.lineEdit().textChanged.connect(self._on_filter_changed)
        self.station_filter.currentIndexChanged.connect(self._on_filter_changed)
        self.station_filter.lineEdit().textChanged.connect(self._on_filter_changed)

        self._load_task_list()
        self._start_auto_refresh()

    def _start_auto_refresh(self) -> None:
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._load_task_list)
        self._refresh_timer.start(5000)

    def set_project(self, project_id: str) -> None:
        self.project_id = project_id
        self.refresh()

    def _load_task_list(self) -> None:
        self.task_selector.blockSignals(True)
        self.task_selector.clear()
        self.task_selector.addItem("-- 选择任务 --", None)

        rsp = self.bus.dispatch(channels.TASK_LIST, {})
        if rsp.success:
            for task in rsp.data or []:
                task_id = task.get("id", "")
                name = task.get("name", "unnamed")
                status = task.get("status", "")
                text = f"{name} [{status}] {task_id[:12]}..."
                self.task_selector.addItem(text, task)

        self.task_selector.blockSignals(False)

    def _on_task_selector_changed(self, text: str) -> None:
        if text == "-- 选择任务 --":
            self.project_id = None
            self._all_rows = []
            self._rows = []
            self.table.setRowCount(0)
            self.detail.clear()
            self.summary_label.setText("")
            return

        task_data = self.task_selector.currentData()
        if task_data:
            self.project_id = task_data.get("project_id")
            self.refresh()

    def _on_filter_changed(self) -> None:
        self._apply_filters()

    def _apply_filters(self) -> None:
        metric_kw = self.metric_filter.currentText().strip().upper()
        station_kw = self.station_filter.currentText().strip().upper()

        if metric_kw in ("全部指标", ""):
            metric_kw = ""
        if station_kw in ("全部站点", ""):
            station_kw = ""

        rows = self._all_rows
        if metric_kw:
            rows = [row for row in rows if metric_kw in str(row.get("metric", "")).upper()]
        if station_kw:
            rows = [
                row
                for row in rows
                if station_kw in str(row.get("station_id") or "").upper()
            ]
        self._rows = rows

        by_metric = defaultdict(list)
        for row in rows:
            by_metric[row.get("metric", "UNKNOWN")].append(row)

        metrics = sorted(by_metric.items(), key=lambda x: x[0])
        self.table.setRowCount(len(metrics))

        for i, (metric, metric_rows) in enumerate(metrics):
            mean_vals = [
                r.get("stats", {}).get("mean")
                for r in metric_rows
                if r.get("stats", {}).get("mean") is not None
            ]
            min_vals = [
                r.get("stats", {}).get("min")
                for r in metric_rows
                if r.get("stats", {}).get("min") is not None
            ]
            max_vals = [
                r.get("stats", {}).get("max")
                for r in metric_rows
                if r.get("stats", {}).get("max") is not None
            ]
            ev_vals = [
                r.get("stats", {}).get("event_count")
                for r in metric_rows
                if r.get("stats", {}).get("event_count") is not None
            ]
            stations = sorted({r.get("station_id") for r in metric_rows if r.get("station_id")})

            metric_name = METRIC_NAMES.get(metric, metric)
            unit = METRIC_UNITS.get(metric, "")
            threshold_info = METRIC_THRESHOLDS.get(metric)
            threshold_text = f"{threshold_info[0]} {unit}" if threshold_info else "-"
            threshold_val = threshold_info[0] if threshold_info else None

            min_text = f"{min(min_vals):.4f}" if min_vals else "-"
            max_text = f"{max(max_vals):.4f}" if max_vals else "-"
            mean_text = f"{sum(mean_vals) / len(mean_vals):.4f}" if mean_vals else "-"
            ev_text = str(sum(ev_vals)) if ev_vals else "-"
            sta_text = ", ".join(stations) if stations else "-"

            # Assessment: use mean as primary criterion
            assessment = "-"
            if mean_vals and threshold_val is not None:
                overall_mean = sum(mean_vals) / len(mean_vals)
                if overall_mean > threshold_val:
                    assessment = "超出阈值"
                elif max_vals and max(max_vals) > threshold_val:
                    assessment = "部分超出"
                else:
                    assessment = "正常"

            self.table.setItem(i, 0, self._metric_item(metric_name))
            self.table.setItem(i, 1, QTableWidgetItem(str(len(metric_rows))))
            self.table.setItem(i, 2, QTableWidgetItem(min_text))
            self.table.setItem(i, 3, self._colored_value(max_text, max_vals, threshold_val))
            self.table.setItem(i, 4, QTableWidgetItem(mean_text))
            self.table.setItem(i, 5, QTableWidgetItem(threshold_text))
            self.table.setItem(i, 6, QTableWidgetItem(ev_text))
            self.table.setItem(i, 7, QTableWidgetItem(sta_text))
            self.table.setItem(i, 8, self._assessment_item(assessment))

        self.table.resizeColumnsToContents()
        all_stations = set()
        for r in self._rows:
            sid = r.get("station_id")
            if sid:
                all_stations.add(sid)
        self.summary_label.setText(
            f"共 {len(self._all_rows)} 条结果，筛选后 {len(self._rows)} 条，"
            f"涉及 {len(metrics)} 个指标、{len(all_stations)} 个站点"
        )

        self._render_detail()

    def _metric_item(self, name: str) -> QTableWidgetItem:
        item = QTableWidgetItem(name)
        item.setToolTip(name)
        return item

    def _colored_value(self, text: str, vals: list, threshold: float | None) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        if vals and threshold is not None and max(vals) > threshold:
            item.setForeground(QColor("#e74c3c"))
            item.setFont(item.font())
        return item

    def _assessment_item(self, assessment: str) -> QTableWidgetItem:
        item = QTableWidgetItem(assessment)
        if assessment == "超出阈值":
            item.setForeground(QColor("#e74c3c"))
        elif assessment == "部分超出":
            item.setForeground(QColor("#f39c12"))
        elif assessment == "正常":
            item.setForeground(QColor("#27ae60"))
        return item

    def _delete_all_results(self) -> None:
        reply = QMessageBox.question(
            self, "确认", "确定要清空所有结果吗？\n此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if not self.project_id:
            QMessageBox.warning(self, "警告", "请先选择一个任务")
            return

        task_rsp = self.bus.dispatch(channels.TASK_LIST, {})
        if not task_rsp.success:
            QMessageBox.critical(self, "错误", "获取任务列表失败")
            return

        deleted = 0
        for task in task_rsp.data or []:
            task_project_id = task.get("project_id")
            if task_project_id == self.project_id:
                task_id = task.get("id")
                if task_id:
                    self.bus.dispatch(channels.TASK_DELETE, {"taskId": task_id, "force": True})
                    deleted += 1

        self._all_rows = []
        self._rows = []
        self.table.setRowCount(0)
        self.detail.clear()
        self.summary_label.setText("")
        self._load_task_list()
        QMessageBox.information(self, "完成", f"已清空 {deleted} 个任务的结果")

    def refresh(self) -> None:
        if not self.project_id:
            self.table.setRowCount(0)
            self.detail.clear()
            self.summary_label.setText("")
            return

        rsp = self.bus.dispatch(channels.RESULT_LIST, {"projectId": self.project_id})
        if not rsp.success:
            self.table.setRowCount(0)
            return

        self._all_rows = rsp.data or []

        self._available_metrics = sorted(set(
            str(r.get("metric", "")) for r in self._all_rows if r.get("metric")
        ))
        self._available_stations = sorted(set(
            str(r.get("station_id") or "") for r in self._all_rows if r.get("station_id")
        ))

        current_metric = self.metric_filter.currentText().strip()
        current_station = self.station_filter.currentText().strip()

        self.metric_filter.blockSignals(True)
        self.metric_filter.clear()
        self.metric_filter.addItem("全部指标")
        for m in self._available_metrics:
            label = f"{m} ({METRIC_NAMES.get(m, '')})"
            self.metric_filter.addItem(label, m)
        if current_metric and current_metric != "全部指标":
            idx = self.metric_filter.findText(current_metric)
            if idx >= 0:
                self.metric_filter.setCurrentIndex(idx)
        self.metric_filter.blockSignals(False)

        self.station_filter.blockSignals(True)
        self.station_filter.clear()
        self.station_filter.addItem("全部站点")
        self.station_filter.addItems(self._available_stations)
        if current_station and current_station != "全部站点":
            idx = self.station_filter.findText(current_station)
            if idx >= 0:
                self.station_filter.setCurrentIndex(idx)
        self.station_filter.blockSignals(False)

        self._apply_filters()

    def _render_detail(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            self.detail.clear()
            return
        # Get metric key from the original data
        metric_item = self.table.item(row, 0)
        if not metric_item:
            self.detail.clear()
            return
        # Match metric by Chinese name back to key
        metric_name = metric_item.text()
        metric_key = metric_name
        for k, v in METRIC_NAMES.items():
            if v == metric_name:
                metric_key = k
                break

        selected = [r for r in self._rows if r.get("metric") == metric_key]
        if not selected:
            self.detail.clear()
            return

        unit = METRIC_UNITS.get(metric_key, "")
        threshold_info = METRIC_THRESHOLDS.get(metric_key)
        threshold_text = f"{threshold_info[0]} {unit} ({threshold_info[1]})" if threshold_info else "-"

        stations = defaultdict(list)
        for r in selected:
            sid = r.get("station_id") or "-"
            stations[sid].append(r)

        lines = [
            f"{'='*50}",
            f"指标: {metric_name}",
            f"单位: {unit}" if unit else "",
            f"告警阈值: {threshold_text}",
            f"结果数量: {len(selected)}",
            f"{'='*50}",
            "",
        ]

        for sid in sorted(stations.keys()):
            sid_rows = stations[sid]
            lines.append(f"--- 测站: {sid} ({len(sid_rows)} 条) ---")

            for r in sid_rows:
                stats = r.get("stats") or {}
                system = SYSTEM_NAMES.get(r.get("system"), r.get("system") or "-")
                chain = CHAIN_NAMES.get(r.get("chain_level"), r.get("chain_level") or "-")
                sampling = r.get("sampling_mode") or "-"
                min_v = stats.get("min")
                max_v = stats.get("max")
                mean_v = stats.get("mean")
                ev = stats.get("event_count")

                parts = [f"  系统={system}", f"链={chain}", f"采样={sampling}"]
                if min_v is not None:
                    parts.append(f"最小={min_v:.4f}")
                if max_v is not None:
                    parts.append(f"最大={max_v:.4f}")
                if mean_v is not None:
                    parts.append(f"均值={mean_v:.4f}")
                if ev is not None:
                    parts.append(f"事件={ev}")

                # Threshold assessment — use mean as primary criterion
                if mean_v is not None and threshold_info:
                    if mean_v > threshold_info[0]:
                        parts.append("[超出阈值]")
                    elif max_v is not None and max_v > threshold_info[0]:
                        parts.append("[部分超出]")
                    else:
                        parts.append("[正常]")

                lines.append(" | ".join(parts))
            lines.append("")

        self.detail.setPlainText("\n".join(lines))
