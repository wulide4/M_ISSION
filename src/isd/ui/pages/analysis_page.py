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
from isd.ui.i18n import LanguageManager, tr


class AnalysisPage(QWidget):
    def __init__(self, bus) -> None:
        super().__init__()
        self.bus = bus
        self._lm = LanguageManager.instance()
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
        self.metric_filter.setPlaceholderText("Filter metric...")
        self.metric_filter.setMinimumWidth(150)

        self.station_filter = QComboBox()
        self.station_filter.setEditable(True)
        self.station_filter.setPlaceholderText("Filter station...")
        self.station_filter.setMinimumWidth(150)

        self.table = QTableWidget(0, 9)
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

        self.refresh_btn = QPushButton(tr("vis.btn.refresh"))
        self.refresh_btn.clicked.connect(self._load_task_list)
        self.refresh_btn.setProperty("secondary", "true")

        self.clear_btn = QPushButton(tr("vis.btn.clear"))
        self.clear_btn.setStyleSheet("""
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
        self.clear_btn.clicked.connect(self._delete_all_results)

        self._build_ui()
        self._lm.language_changed.connect(self._retranslate)

        self._load_task_list()
        self._start_auto_refresh()

    def _build_ui(self) -> None:
        form = QFormLayout()
        self._metric_filter_label = QLabel(tr("ana.filter.metric"))
        form.addRow(self._metric_filter_label, self.metric_filter)
        self._station_filter_label = QLabel(tr("ana.filter.station"))
        form.addRow(self._station_filter_label, self.station_filter)

        self._filter_box = QGroupBox(tr("ana.filter.metric"))
        filter_box_layout = QVBoxLayout(self._filter_box)
        filter_box_layout.addLayout(form)

        top = QHBoxLayout()
        top.addWidget(self._filter_box)
        top.addWidget(self.refresh_btn)
        top.addWidget(self.clear_btn)

        layout = QVBoxLayout(self)
        self.title_label = QLabel(tr("ana.title"))
        self.title_label.setStyleSheet("""
            font-size: 22px;
            font-weight: bold;
            color: #00e5ff;
            margin: 10px 0;
        """)
        layout.addWidget(self.title_label)

        self._task_lbl = QLabel(tr("vis.select_task"))
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(self._task_lbl)
        selector_layout.addWidget(self.task_selector)
        selector_layout.addStretch()
        layout.addLayout(selector_layout)

        layout.addLayout(top)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.table)

        self._detail_label = QLabel(tr("ana.detail_title"))
        self._detail_label.setStyleSheet("color: #8b9bb4; font-weight: bold;")
        layout.addWidget(self._detail_label)
        layout.addWidget(self.detail)

        self.metric_filter.currentIndexChanged.connect(self._on_filter_changed)
        self.metric_filter.lineEdit().textChanged.connect(self._on_filter_changed)
        self.station_filter.currentIndexChanged.connect(self._on_filter_changed)
        self.station_filter.lineEdit().textChanged.connect(self._on_filter_changed)

    def _retranslate(self) -> None:
        self.title_label.setText(tr("ana.title"))
        self._task_lbl.setText(tr("vis.select_task"))
        self._metric_filter_label.setText(tr("ana.filter.metric"))
        self._station_filter_label.setText(tr("ana.filter.station"))
        self._filter_box.setTitle(tr("ana.filter.metric"))
        self._detail_label.setText(tr("ana.detail_title"))
        self.refresh_btn.setText(tr("vis.btn.refresh"))
        self.clear_btn.setText(tr("vis.btn.clear"))

        # Update table headers
        self.table.setHorizontalHeaderLabels([
            tr("ana.col.metric"), tr("ana.col.count"), tr("ana.col.min"),
            tr("ana.col.max"), tr("ana.col.mean"), tr("ana.col.threshold"),
            tr("ana.col.events"), tr("ana.col.station"), tr("ana.col.assessment"),
        ])

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
        self.task_selector.addItem(tr("vis.select_task_placeholder"), None)

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
        if not text or self.task_selector.currentData() is None:
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

    def _metric_name(self, key: str) -> str:
        return tr(f"metric.{key}") if key in ("ROTI", "AATR", "IAATR", "DIXSG", "SIGMA_PHI_F", "S4C") else key

    _METRIC_UNITS = {
        "ROTI": "TECU/min",
        "AATR": "TECU/min",
        "IAATR": "TECU/min",
        "DIXSG": "",
        "SIGMA_PHI_F": "m",
        "S4C": "",
    }

    _METRIC_THRESHOLDS = {
        "ROTI": (0.5, "Pi et al. (1997)"),
        "AATR": (0.2, "Sanz et al. (2014)"),
        "IAATR": (0.2, "Sanz et al. (2014)"),
        "DIXSG": (0.5, "Jakowski et al. (2012)"),
        "SIGMA_PHI_F": (0.05, "Ahmed et al. (2015)"),
        "S4C": (0.25, "Van Dierendonck et al. (1993); Zhang et al. (2026)"),
    }

    def _apply_filters(self) -> None:
        metric_kw = self.metric_filter.currentText().strip().upper()
        station_kw = self.station_filter.currentText().strip().upper()

        all_metric_text = tr("ana.filter.all_metric")
        all_station_text = tr("ana.filter.all_station")
        if metric_kw in (all_metric_text, ""):
            metric_kw = ""
        if station_kw in (all_station_text, ""):
            station_kw = ""

        rows = self._all_rows
        if metric_kw:
            rows = [row for row in rows if metric_kw in str(row.get("metric", "")).upper()]
        if station_kw:
            rows = [row for row in rows if station_kw in str(row.get("station_id") or "").upper()]
        self._rows = rows

        by_metric = defaultdict(list)
        for row in rows:
            by_metric[row.get("metric", "UNKNOWN")].append(row)

        metrics = sorted(by_metric.items(), key=lambda x: x[0])
        self.table.setRowCount(len(metrics))

        for i, (metric, metric_rows) in enumerate(metrics):
            mean_vals = [r.get("stats", {}).get("mean") for r in metric_rows if r.get("stats", {}).get("mean") is not None]
            min_vals = [r.get("stats", {}).get("min") for r in metric_rows if r.get("stats", {}).get("min") is not None]
            max_vals = [r.get("stats", {}).get("max") for r in metric_rows if r.get("stats", {}).get("max") is not None]
            ev_vals = [r.get("stats", {}).get("event_count") for r in metric_rows if r.get("stats", {}).get("event_count") is not None]
            stations = sorted({r.get("station_id") for r in metric_rows if r.get("station_id")})

            metric_name = self._metric_name(metric)
            unit = self._METRIC_UNITS.get(metric, "")
            threshold_info = self._METRIC_THRESHOLDS.get(metric)
            threshold_text = f"{threshold_info[0]} {unit}" if threshold_info else "-"
            threshold_val = threshold_info[0] if threshold_info else None

            min_text = f"{min(min_vals):.4f}" if min_vals else "-"
            max_text = f"{max(max_vals):.4f}" if max_vals else "-"
            mean_text = f"{sum(mean_vals) / len(mean_vals):.4f}" if mean_vals else "-"
            ev_text = str(sum(ev_vals)) if ev_vals else "-"
            sta_text = ", ".join(stations) if stations else "-"

            assessment = "-"
            if mean_vals and threshold_val is not None:
                overall_mean = sum(mean_vals) / len(mean_vals)
                if overall_mean > threshold_val:
                    assessment = tr("ana.assess.exceeded")
                elif max_vals and max(max_vals) > threshold_val:
                    assessment = tr("ana.assess.partial")
                else:
                    assessment = tr("ana.assess.normal")

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

        summary = tr("ana.summary").format(
            len(self._all_rows), len(self._rows), len(metrics), len(all_stations)
        )
        self.summary_label.setText(summary)
        self._render_detail()

    def _metric_item(self, name: str) -> QTableWidgetItem:
        item = QTableWidgetItem(name)
        item.setToolTip(name)
        return item

    def _colored_value(self, text: str, vals: list, threshold: float | None) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        if vals and threshold is not None and max(vals) > threshold:
            item.setForeground(QColor("#e74c3c"))
        return item

    def _assessment_item(self, assessment: str) -> QTableWidgetItem:
        item = QTableWidgetItem(assessment)
        exceeded = tr("ana.assess.exceeded")
        partial = tr("ana.assess.partial")
        normal = tr("ana.assess.normal")
        if assessment == exceeded:
            item.setForeground(QColor("#e74c3c"))
        elif assessment == partial:
            item.setForeground(QColor("#f39c12"))
        elif assessment == normal:
            item.setForeground(QColor("#27ae60"))
        return item

    def _delete_all_results(self) -> None:
        reply = QMessageBox.question(
            self, tr("dlg.confirm"), tr("dlg.confirm_clear"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if not self.project_id:
            QMessageBox.warning(self, tr("dlg.warning"), "No project selected")
            return

        task_rsp = self.bus.dispatch(channels.TASK_LIST, {})
        if not task_rsp.success:
            return

        deleted = 0
        for task in task_rsp.data or []:
            if task.get("project_id") == self.project_id:
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
        QMessageBox.information(self, tr("dlg.success"), f"Cleared {deleted} task(s)")

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
        self._available_metrics = sorted({str(r.get("metric", "")) for r in self._all_rows if r.get("metric")})
        self._available_stations = sorted({str(r.get("station_id") or "") for r in self._all_rows if r.get("station_id")})

        current_metric = self.metric_filter.currentText().strip()
        current_station = self.station_filter.currentText().strip()

        self.metric_filter.blockSignals(True)
        self.metric_filter.clear()
        self.metric_filter.addItem(tr("ana.filter.all_metric"))
        for m in self._available_metrics:
            self.metric_filter.addItem(f"{m} ({self._metric_name(m)})", m)
        if current_metric and current_metric != tr("ana.filter.all_metric"):
            idx = self.metric_filter.findText(current_metric)
            if idx >= 0:
                self.metric_filter.setCurrentIndex(idx)
        self.metric_filter.blockSignals(False)

        self.station_filter.blockSignals(True)
        self.station_filter.clear()
        self.station_filter.addItem(tr("ana.filter.all_station"))
        self.station_filter.addItems(self._available_stations)
        if current_station and current_station != tr("ana.filter.all_station"):
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
        metric_item = self.table.item(row, 0)
        if not metric_item:
            self.detail.clear()
            return

        metric_name = metric_item.text()
        metric_key = metric_name
        for k in ("ROTI", "AATR", "IAATR", "DIXSG", "SIGMA_PHI_F", "S4C"):
            if tr(f"metric.{k}") == metric_name:
                metric_key = k
                break

        selected = [r for r in self._rows if r.get("metric") == metric_key]
        if not selected:
            self.detail.clear()
            return

        unit = self._METRIC_UNITS.get(metric_key, "")
        threshold_info = self._METRIC_THRESHOLDS.get(metric_key)
        threshold_text = f"{threshold_info[0]} {unit} ({threshold_info[1]})" if threshold_info else "-"

        stations = defaultdict(list)
        for r in selected:
            sid = r.get("station_id") or "-"
            stations[sid].append(r)

        lines = [
            f"{'=' * 50}",
            f"{tr('detail.metric')}: {metric_name}",
            f"{tr('detail.unit')}: {unit}" if unit else "",
            f"{tr('detail.threshold')}: {threshold_text}",
            f"Results: {len(selected)}",
            f"{'=' * 50}",
            "",
        ]

        for sid in sorted(stations.keys()):
            sid_rows = stations[sid]
            lines.append(f"--- {tr('detail.station')}: {sid} ({len(sid_rows)}) ---")
            for r in sid_rows:
                stats = r.get("stats") or {}
                system = r.get("system") or "-"
                chain = r.get("chain_level") or "-"
                sampling = r.get("sampling_mode") or "-"
                min_v = stats.get("min")
                max_v = stats.get("max")
                mean_v = stats.get("mean")

                parts = [f"  {tr('detail.system')}={system}", f"Chain={chain}", f"Sampling={sampling}"]
                if min_v is not None:
                    parts.append(f"{tr('detail.min')}={min_v:.4f}")
                if max_v is not None:
                    parts.append(f"{tr('detail.max')}={max_v:.4f}")
                if mean_v is not None:
                    parts.append(f"{tr('detail.mean')}={mean_v:.4f}")

                if mean_v is not None and threshold_info:
                    if mean_v > threshold_info[0]:
                        parts.append(f"[{tr('ana.assess.exceeded')}]")
                    elif max_v is not None and max_v > threshold_info[0]:
                        parts.append(f"[{tr('ana.assess.partial')}]")
                    else:
                        parts.append(f"[{tr('ana.assess.normal')}]")

                lines.append(" | ".join(parts))
            lines.append("")

        self.detail.setPlainText("\n".join(lines))
