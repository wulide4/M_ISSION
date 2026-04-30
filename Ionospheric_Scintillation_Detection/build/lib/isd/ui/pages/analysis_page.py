from __future__ import annotations

from collections import defaultdict

from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from isd.application import channels
from isd.application.command_bus import CommandBus


class AnalysisPage(QWidget):
    def __init__(self, bus: CommandBus) -> None:
        super().__init__()
        self.bus = bus
        self.project_id: str | None = None
        self._rows: list[dict] = []

        self.metric_filter = QLineEdit()
        self.station_filter = QLineEdit()
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Metric", "Count", "Mean(approx)", "EventCount(sum)", "Stations"]
        )
        self.table.itemSelectionChanged.connect(self._render_detail)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)

        refresh_btn = QPushButton("刷新统计")
        refresh_btn.clicked.connect(self.refresh)

        form = QFormLayout()
        form.addRow("指标筛选", self.metric_filter)
        form.addRow("站点筛选", self.station_filter)

        top = QHBoxLayout()
        top.addLayout(form, 5)
        top.addWidget(refresh_btn, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>分析统计</h2>"))
        layout.addLayout(top)
        layout.addWidget(self.table)
        layout.addWidget(QLabel("指标明细"))
        layout.addWidget(self.detail)

    def set_project(self, project_id: str) -> None:
        self.project_id = project_id

    def refresh(self) -> None:
        if not self.project_id:
            return
        rsp = self.bus.dispatch(channels.RESULT_LIST, {"projectId": self.project_id})
        if not rsp.success:
            return

        rows = rsp.data or []
        metric_kw = self.metric_filter.text().strip().upper()
        station_kw = self.station_filter.text().strip().upper()
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
            ev_vals = [
                r.get("stats", {}).get("event_count")
                for r in metric_rows
                if r.get("stats", {}).get("event_count") is not None
            ]
            stations = sorted({r.get("station_id") for r in metric_rows if r.get("station_id")})
            mean_text = f"{sum(mean_vals) / len(mean_vals):.4f}" if mean_vals else "-"
            ev_text = str(sum(ev_vals)) if ev_vals else "-"
            self.table.setItem(i, 0, QTableWidgetItem(metric))
            self.table.setItem(i, 1, QTableWidgetItem(str(len(metric_rows))))
            self.table.setItem(i, 2, QTableWidgetItem(mean_text))
            self.table.setItem(i, 3, QTableWidgetItem(ev_text))
            self.table.setItem(i, 4, QTableWidgetItem(",".join(stations)))

        self._render_detail()

    def _render_detail(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            self.detail.clear()
            return
        metric_item = self.table.item(row, 0)
        if not metric_item:
            self.detail.clear()
            return
        metric = metric_item.text()
        selected = [r for r in self._rows if r.get("metric") == metric]
        stations = defaultdict(list)
        for r in selected:
            sid = r.get("station_id") or "-"
            stations[sid].append(r)

        lines = [f"Metric: {metric}", f"ResultCount: {len(selected)}", ""]
        for sid in sorted(stations.keys()):
            sid_rows = stations[sid]
            means = [x.get("stats", {}).get("mean") for x in sid_rows if x.get("stats", {}).get("mean") is not None]
            mins = [x.get("stats", {}).get("min") for x in sid_rows if x.get("stats", {}).get("min") is not None]
            maxs = [x.get("stats", {}).get("max") for x in sid_rows if x.get("stats", {}).get("max") is not None]
            lines.append(f"[{sid}] count={len(sid_rows)}")
            if means:
                lines.append(f"  mean(avg)={sum(means) / len(means):.4f}")
            if mins:
                lines.append(f"  min(global)={min(mins):.4f}")
            if maxs:
                lines.append(f"  max(global)={max(maxs):.4f}")
            lines.append("")

        self.detail.setPlainText("\n".join(lines))

