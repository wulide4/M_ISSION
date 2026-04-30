from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


from isd.application import channels
from isd.application.command_bus import CommandBus
from isd.application.risk_flags import derive_result_risk_flags, risk_flags_to_text


def _ecef_to_lla(x: float, y: float, z: float) -> tuple[float, float]:
    """Convert ECEF X,Y,Z (meters) to geodetic lat, lon (degrees). WGS-84."""
    a = 6378137.0
    f = 1.0 / 298.257223563
    b = a * (1 - f)
    e2 = 1 - (b / a) ** 2
    lon = math.atan2(y, x)
    p = math.sqrt(x * x + y * y)
    lat = math.atan2(z, p * (1 - e2))
    for _ in range(10):
        nu = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        lat = math.atan2(z + e2 * nu * math.sin(lat), p)
    return math.degrees(lat), math.degrees(lon)


def _ensure_geographic(station: dict) -> dict:
    """If station lat/lon look like ECEF (|value| > 180), convert to degrees."""
    lat = station.get("latitude")
    lon = station.get("longitude")
    h = station.get("height") or 0.0
    if lat is not None and lon is not None and (abs(lat) > 180 or abs(lon) > 180):
        new_lat, new_lon = _ecef_to_lla(float(lat), float(lon), float(h))
        station = {**station, "latitude": new_lat, "longitude": new_lon}
    return station


class VisualizationPage(QWidget):
    def __init__(self, bus: CommandBus) -> None:
        super().__init__()
        self.bus = bus
        self.project_id: str | None = None
        self._all_results: list[dict[str, Any]] = []
        self._current_result: dict[str, Any] | None = None
        self._refresh_timer: QTimer | None = None
        self._stations_cache: list[dict[str, Any]] = []
        self._station_markers: list = []  # pyqtgraph items to remove on refresh

        self.task_selector = QComboBox()
        self.task_selector.setMinimumWidth(300)
        self.task_selector.currentTextChanged.connect(self._on_task_selector_changed)

        self.result_list = QListWidget()
        self.result_list.itemClicked.connect(self._on_result_selected)

        self.series_plot = pg.PlotWidget()
        self.series_plot.setBackground("#121a2e")
        self.series_plot.showGrid(x=True, y=True, alpha=0.25)
        self.series_plot.getAxis("bottom").setTextPen("#8b9bb4")
        self.series_plot.getAxis("left").setTextPen("#8b9bb4")

        self.grid_view = pg.ImageView()
        self.grid_view.ui.roiBtn.hide()
        self.grid_view.ui.menuBtn.hide()
        # Hide the histogram's gradient/level bar visually but keep the widget
        # so the splitter doesn't collapse the time slider (roiPlot)
        self.grid_view.ui.histogram.setMinimumWidth(0)
        self.grid_view.ui.histogram.setMaximumWidth(0)
        self.grid_view.setImage(np.zeros((2, 2), dtype=float))
        self.grid_view.getView().invertY(False)
        self._grid_lat_range: list[float] = [-90.0, 90.0]
        self._grid_lon_range: list[float] = [-180.0, 180.0]
        self._grid_axis_labels: list = []

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)

        self.status_hint = QLabel("状态: 加载中...")

        self._build_ui()
        self._load_task_list()
        self._start_auto_refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("结果可视化")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #00e5ff; margin: 10px 0;")
        layout.addWidget(title)

        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("选择任务:"))
        selector_layout.addWidget(self.task_selector)
        selector_layout.addStretch()
        layout.addLayout(selector_layout)

        layout.addWidget(self.status_hint)

        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #2a3a5c;
                border-radius: 4px;
                background-color: #121a2e;
            }
            QTabBar::tab {
                background-color: #1a2540;
                color: #8b9bb4;
                padding: 8px 16px;
                border: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #2196f3;
                color: white;
            }
            QTabBar::tab:hover {
                background-color: #2a3a5c;
            }
        """)

        series_tab = QWidget()
        series_layout = QVBoxLayout(series_tab)
        series_layout.addWidget(self.series_plot)
        tabs.addTab(series_tab, "时序图")

        grid_tab = QWidget()
        grid_layout = QVBoxLayout(grid_tab)
        grid_layout.addWidget(self.grid_view)
        tabs.addTab(grid_tab, "区域栅格")

        detail_tab = QWidget()
        detail_layout = QVBoxLayout(detail_tab)
        detail_layout.addWidget(self.detail_text)
        tabs.addTab(detail_tab, "详情")

        main_split = QSplitter(Qt.Orientation.Horizontal)
        main_split.addWidget(self.result_list)
        main_split.addWidget(tabs)
        main_split.setSizes([300, 1100])
        layout.addWidget(main_split)

        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("刷新")
        refresh_btn.setProperty("secondary", "true")
        refresh_btn.clicked.connect(self._load_task_list)
        export_btn = QPushButton("导出")
        export_btn.setProperty("secondary", "true")
        export_btn.clicked.connect(self._export_current_result)
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
        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(export_btn)
        btn_layout.addWidget(delete_all_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

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

        # 获取任务列表
        rsp = self.bus.dispatch(channels.TASK_LIST, {})
        if rsp.success:
            for task in rsp.data or []:
                task_id = task.get("id", "")
                name = task.get("name", "unnamed")
                status = task.get("status", "")
                task_summary = task.get("summary") or ""
                text = f"{name} [{status}] {task_id[:12]}..."
                # 保存完整task数据
                self.task_selector.addItem(text, task)

        self.task_selector.blockSignals(False)

    def _on_task_selector_changed(self, text: str) -> None:
        if text == "-- 选择任务 --":
            self.project_id = None
            self._all_results = []
            self.result_list.clear()
            self._clear_panels()
            self._set_status("请选择任务")
            return

        task_data = self.task_selector.currentData()
        if task_data:
            self.project_id = task_data.get("project_id")
            self.refresh()

    def refresh(self) -> None:
        if not self.project_id:
            self._all_results = []
            self.result_list.clear()
            self._clear_panels()
            self._set_status("请选择任务")
            return

        rsp = self.bus.dispatch(channels.RESULT_LIST, {"projectId": self.project_id})
        if not rsp.success:
            self._all_results = []
            self.result_list.clear()
            self._set_status("加载失败")
            return

        self._all_results = rsp.data or []

        # Cache station coordinates for grid overlay (convert ECEF if needed)
        sta_rsp = self.bus.dispatch(channels.PROJECT_GET_STATIONS, {"projectId": self.project_id})
        raw_stations = sta_rsp.data if sta_rsp.success else []
        self._stations_cache = [_ensure_geographic(s) for s in raw_stations]

        self._set_status(f"已加载 {len(self._all_results)} 条结果")
        self._render_result_list()

        if self._all_results:
            self.result_list.setCurrentRow(0)
            self._on_result_selected(self.result_list.item(0))

    def _set_status(self, msg: str) -> None:
        self.status_hint.setText(f"状态: {msg}")

    def _render_result_list(self) -> None:
        self.result_list.clear()

        for row in self._all_results:
            metric = row.get("metric", "-")
            station = row.get("station_id") or "-"
            system = row.get("system") or "-"
            text = f"{metric} | {station} | {system}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, row)
            self.result_list.addItem(item)

    def _clear_panels(self) -> None:
        self.series_plot.clear()
        self.grid_view.setImage(np.zeros((2, 2), dtype=float), autoLevels=True)
        self.detail_text.clear()

    def _on_result_selected(self, item: QListWidgetItem) -> None:
        if not item:
            return
        row = item.data(Qt.ItemDataRole.UserRole) or {}
        self._current_result = row
        self._render_detail_card(row)
        self._load_series(row)
        self._load_grid(row)

    # Metric display metadata for axis labels and threshold overlays
    METRIC_INFO = {
        "ROTI": {"unit": "TECU/min", "label": "ROTI (TECU/min)", "threshold": 0.5, "threshold_source": "Pi et al. (1997)"},
        "AATR": {"unit": "TECU/min", "label": "AATR (TECU/min)", "threshold": 0.2, "threshold_source": "Sanz et al. (2014)"},
        "IAATR": {"unit": "TECU/min", "label": "IAATR (TECU/min)", "threshold": 0.2, "threshold_source": "Sanz et al. (2014)"},
        "DIXSG": {"unit": "index", "label": "DIXSG", "threshold": 0.5, "threshold_source": "Jakowski et al. (2012)"},
        "SIGMA_PHI_F": {"unit": "rad", "label": "σϕf (rad)", "threshold": 0.3, "threshold_source": "Ahmed et al. (2015)"},
    }

    def _load_series(self, result_row: dict[str, Any]) -> None:
        payload = {
            "resultId": str(result_row.get("id") or ""),
            "projectId": str(result_row.get("project_id") or self.project_id or ""),
        }
        if not payload["resultId"] or not payload["projectId"]:
            self.series_plot.clear()
            return

        rsp = self.bus.dispatch(channels.RESULT_GET_SERIES, payload)
        if not rsp.success:
            self.series_plot.clear()
            metric = result_row.get("metric", "")
            reason = rsp.error.message if rsp.error else "未知错误"
            self.series_plot.setTitle(f"{metric} - 时序数据不可用: {reason}", color="#ff1744", size="10pt")
            return

        data = rsp.data or {}
        try:
            values = np.asarray(data.get("values", []), dtype=float)
        except Exception:
            self.series_plot.clear()
            return

        metric = result_row.get("metric", "")
        info = self.METRIC_INFO.get(metric, {})
        y_label = info.get("label", "Value")
        station = result_row.get("station_id", "-")
        system = result_row.get("system", "-")

        self.series_plot.clear()
        self.series_plot.setTitle(f"{metric} - {station} ({system})", color="#8b9bb4", size="11pt")
        self.series_plot.setLabel("left", y_label, color="#8b9bb4")

        # AATR and DIXSG are hourly-aggregated metrics (24 values per day)
        is_hourly = metric in ("AATR", "DIXSG")
        if is_hourly:
            self.series_plot.setLabel("bottom", "Hour (UT)", color="#8b9bb4")
        else:
            self.series_plot.setLabel("bottom", "Epoch", color="#8b9bb4")
        self.series_plot.addLegend(offset=(60, 10))

        time_axis = np.asarray(data.get("time", np.arange(values.shape[0] if values.ndim >= 1 else 0)), dtype=float)

        # For hourly metrics, convert epoch index to hour labels
        if is_hourly and values.ndim == 1 and time_axis.shape[0] <= 25:
            time_axis = np.arange(time_axis.shape[0], dtype=float)

        if values.ndim == 1:
            y = values
            if time_axis.shape[0] != y.shape[0]:
                time_axis = np.arange(y.shape[0], dtype=float)
            label = "RMS AATR" if metric == "AATR" else ("aDIXSG" if metric == "DIXSG" else "Mean")
            pen_width = 2.5 if is_hourly else 1.5
            self.series_plot.plot(time_axis, y, pen=pg.mkPen("#00e5ff", width=pen_width), name=label,
                                 symbol='o' if is_hourly else None, symbolSize=8, symbolBrush='#00e5ff')
            self._auto_zoom_series(time_axis, y[np.newaxis, :] if y.ndim == 1 else y, info)
        elif values.ndim >= 2:
            if time_axis.shape[0] != values.shape[0]:
                time_axis = np.arange(values.shape[0], dtype=float)
            # Plot individual satellite traces (up to 8 visible)
            num_cols = min(values.shape[1], 8)
            colors = ["#00e5ff", "#ff6b6b", "#ffd93d", "#6bcb77", "#4d96ff", "#ff922b", "#cc5de8", "#20c997"]
            # Use actual satellite IDs from result metadata
            sat_ids = result_row.get("satellite_ids") or []
            system = result_row.get("system", "GPS")
            # Generate system-appropriate default satellite IDs when metadata is missing
            _SYS_PREFIX = {"GPS": "G", "GLO": "R", "GAL": "E", "BDS": "C"}
            sys_prefix = _SYS_PREFIX.get(system, "G")
            for col in range(num_cols):
                col_data = values[:, col]
                finite_mask = np.isfinite(col_data)
                if finite_mask.sum() < 2:
                    continue
                if col < len(sat_ids) and sat_ids[col]:
                    label = sat_ids[col]
                else:
                    label = f"{sys_prefix}{col + 1:02d}"
                self.series_plot.plot(
                    time_axis, col_data,
                    pen=pg.mkPen(colors[col % len(colors)], width=1.0),
                    name=label,
                )
            # Also plot mean trace
            mean_val = np.nanmean(values, axis=1)
            self.series_plot.plot(
                time_axis, mean_val,
                pen=pg.mkPen("w", width=2.0, style=Qt.PenStyle.DashLine),
                name="Mean",
            )
            self._auto_zoom_series(time_axis, values, info)
        else:
            self.series_plot.clear()
            return

        # Draw threshold line if available
        threshold = info.get("threshold")
        if threshold is not None:
            self.series_plot.addLine(
                y=threshold,
                pen=pg.mkPen("#ff1744", width=1.5, style=Qt.PenStyle.DashLine),
            )

    def _auto_zoom_series(self, time_axis: np.ndarray, values: np.ndarray, info: dict) -> None:
        """Auto-zoom the series plot to the most suitable view range based on finite data."""
        finite_mask = np.isfinite(values)
        if not finite_mask.any():
            return

        # Y range: use percentiles to avoid extreme outliers dominating the view
        finite_vals = values[finite_mask]
        y_min = float(np.percentile(finite_vals, 1))
        y_max = float(np.percentile(finite_vals, 99))

        # Extend Y range to include threshold if present
        threshold = info.get("threshold")
        if threshold is not None:
            y_min = min(y_min, threshold * 0.8)
            y_max = max(y_max, threshold * 1.2)

        # Handle degenerate case where all values are the same
        if y_max - y_min < 1e-12:
            y_min -= 0.5
            y_max += 0.5

        y_padding = (y_max - y_min) * 0.1
        y_min -= y_padding
        y_max += y_padding

        # X range: based on time axis, with small padding
        x_min = float(time_axis[0])
        x_max = float(time_axis[-1])
        if x_max - x_min < 1e-12:
            x_min -= 1.0
            x_max += 1.0
        x_padding = (x_max - x_min) * 0.02
        x_min -= x_padding
        x_max += x_padding

        self.series_plot.setXRange(x_min, x_max, padding=0)
        self.series_plot.setYRange(y_min, y_max, padding=0)

    def _load_grid(self, result_row: dict[str, Any]) -> None:
        self._clear_overlay_items()

        payload = {
            "resultId": str(result_row.get("id") or ""),
            "projectId": str(result_row.get("project_id") or self.project_id or ""),
        }
        if not payload["resultId"] or not payload["projectId"]:
            self.grid_view.setImage(np.zeros((2, 2), dtype=float), autoLevels=True)
            return

        rsp = self.bus.dispatch(channels.RESULT_GET_GRID, payload)
        if not rsp.success:
            self.grid_view.setImage(np.zeros((2, 2), dtype=float), autoLevels=True)
            metric = result_row.get("metric", "")
            reason = rsp.error.message if rsp.error else "未知错误"
            self.status_hint.setText(f"栅格数据不可用 ({metric}): {reason}")
            return

        data = rsp.data or {}
        grid = np.asarray(data.get("grid", []), dtype=float)
        if grid.size == 0:
            self.grid_view.setImage(np.zeros((2, 2), dtype=float), autoLevels=True)
            return

        metric = result_row.get("metric", "")

        if grid.ndim == 3 and grid.shape[0] == 24 and metric == "DIXSG":
            # DIXSG 3D grid: (24 hours, lat_bins, lon_bins)
            grid_t = np.transpose(grid, (0, 2, 1))  # (24, lon, lat)
            display = np.nan_to_num(grid_t, nan=0.0)
            self.grid_view.setImage(display, autoLevels=True)
            # Extract lat/lon range from saved data
            lat_range = data.get("lat_range")
            lon_range = data.get("lon_range")
            self._setup_dixsg_grid_axes(display, grid.shape[2], grid.shape[1], lat_range, lon_range)
        else:
            heatmap = self._to_heatmap(grid)
            display = np.nan_to_num(heatmap, nan=0.0)
            self.grid_view.setImage(display, autoLevels=True)
            self._auto_zoom_grid(display)

    def _clear_overlay_items(self) -> None:
        """Remove all overlay items (station markers + axis labels) from grid view."""
        view = self.grid_view.getView()
        if view is None:
            return
        for item in self._station_markers + self._grid_axis_labels:
            try:
                view.removeItem(item)
            except Exception:
                pass
        self._station_markers.clear()
        self._grid_axis_labels.clear()

    def _setup_dixsg_grid_axes(
        self,
        display: np.ndarray,
        numlon: int,
        numlat: int,
        lat_range: list[float] | None = None,
        lon_range: list[float] | None = None,
    ) -> None:
        """Configure ImageView for DIXSG geographic grid display with station markers."""
        view = self.grid_view.getView()
        if view is None:
            return

        self._clear_overlay_items()

        # Set color levels to maximize visual contrast
        finite = display[np.isfinite(display) & (display > 0)]
        if len(finite) > 0:
            vmin = 0.0
            vmax = float(np.percentile(finite, 97))
            if vmax < 0.1:
                vmax = float(np.max(finite)) if len(finite) > 0 else 1.0
            self.grid_view.setLevels(vmin, vmax)

        # Grid mapping using actual lat/lon range from data
        if lat_range is not None:
            lat_lo, lat_hi = float(lat_range[0]), float(lat_range[1])
        else:
            lat_lo, lat_hi = -90.0, 90.0
        if lon_range is not None:
            lon_lo, lon_hi = float(lon_range[0]), float(lon_range[1])
        else:
            lon_lo, lon_hi = -180.0, 180.0
        self._grid_lat_range = [lat_lo, lat_hi]
        self._grid_lon_range = [lon_lo, lon_hi]
        dlon = (lon_hi - lon_lo) / max(1, numlon)
        dlat = (lat_hi - lat_lo) / max(1, numlat)

        # Collect valid station positions in pixel coords
        sta_pixels = []
        for sta in self._stations_cache:
            lat = sta.get("latitude")
            lon = sta.get("longitude")
            code = sta.get("station_code", "")
            if lat is None or lon is None:
                continue
            px = (lon - lon_lo) / dlon
            py = (lat - lat_lo) / dlat
            if -50 <= px <= numlon + 50 and -50 <= py <= numlat + 50:
                sta_pixels.append((px, py, code))

        # Auto-zoom to station region
        if sta_pixels:
            px_vals = [s[0] for s in sta_pixels]
            py_vals = [s[1] for s in sta_pixels]
            x_min, x_max = min(px_vals), max(px_vals)
            y_min, y_max = min(py_vals), max(py_vals)
            x_pad = max((x_max - x_min) * 0.3, 20)
            y_pad = max((y_max - y_min) * 0.3, 20)
            view.setRange(
                xRange=(max(0, x_min - x_pad), min(numlon, x_max + x_pad)),
                yRange=(max(0, y_min - y_pad), min(numlat, y_max + y_pad)),
                padding=0.02,
            )
        else:
            view.setRange(xRange=(0, numlon), yRange=(0, numlat), padding=0.02)

        # --- Draw longitude tick labels along bottom edge ---
        lon_step = self._nice_tick_step(lon_lo, lon_hi, target_ticks=8)
        lon_ticks = np.arange(
            math.ceil(lon_lo / lon_step) * lon_step,
            lon_hi + lon_step * 0.01,
            lon_step,
        )
        for lon_val in lon_ticks:
            px = (lon_val - lon_lo) / dlon
            if px < -5 or px > numlon + 5:
                continue
            txt = pg.TextItem(
                text=f"{lon_val:.0f}°",
                color=(200, 210, 230),
                anchor=(0.5, 0),
            )
            txt.setPos(px, numlat + 1)
            view.addItem(txt)
            self._grid_axis_labels.append(txt)

        # --- Draw latitude tick labels along left edge ---
        lat_step = self._nice_tick_step(lat_lo, lat_hi, target_ticks=6)
        lat_ticks = np.arange(
            math.ceil(lat_lo / lat_step) * lat_step,
            lat_hi + lat_step * 0.01,
            lat_step,
        )
        for lat_val in lat_ticks:
            py = (lat_val - lat_lo) / dlat
            if py < -5 or py > numlat + 5:
                continue
            txt = pg.TextItem(
                text=f"{lat_val:.0f}°",
                color=(200, 210, 230),
                anchor=(1, 0.5),
            )
            txt.setPos(-1, py)
            view.addItem(txt)
            self._grid_axis_labels.append(txt)

        # Axis title labels
        lon_title = pg.TextItem(text="经度 (°E)", color=(180, 200, 230), anchor=(0.5, 0))
        lon_title.setPos(numlon / 2, numlat + 4)
        view.addItem(lon_title)
        self._grid_axis_labels.append(lon_title)

        lat_title = pg.TextItem(text="纬度 (°N)", color=(180, 200, 230), anchor=(0.5, 0.5))
        lat_title.setPos(-5, numlat / 2)
        lat_title.setRotation(-90)
        view.addItem(lat_title)
        self._grid_axis_labels.append(lat_title)

        # Draw station markers and labels
        for px, py, code in sta_pixels:
            scatter = pg.ScatterPlotItem(
                [px], [py],
                pen=pg.mkPen(color=(255, 255, 0), width=2),
                brush=pg.mkBrush(255, 255, 0, 200),
                size=10,
            )
            view.addItem(scatter)
            self._station_markers.append(scatter)

            label = pg.TextItem(
                text=code,
                color=(255, 255, 0),
                anchor=(0, 1.5),
            )
            label.setPos(px, py)
            view.addItem(label)
            self._station_markers.append(label)

    @staticmethod
    def _nice_tick_step(lo: float, hi: float, target_ticks: int = 6) -> float:
        """Pick a 'nice' tick step (1, 2, 5, 10, ...) for the given range."""
        raw = (hi - lo) / max(1, target_ticks)
        mag = 10 ** math.floor(math.log10(max(raw, 1e-10)))
        for nice in (1, 2, 5, 10, 20, 50):
            if nice * mag >= raw:
                return nice * mag
        return raw

    def _auto_zoom_grid(self, grid: np.ndarray) -> None:
        """Auto-zoom the grid ImageView to fit the data with appropriate color levels."""
        if grid.size == 0:
            return

        finite_mask = np.isfinite(grid)
        if not finite_mask.any():
            return

        finite_vals = grid[finite_mask]
        vmin = float(np.percentile(finite_vals, 1))
        vmax = float(np.percentile(finite_vals, 99))

        # Handle degenerate case
        if vmax - vmin < 1e-12:
            center = (vmax + vmin) / 2.0
            vmin = center - 0.5
            vmax = center + 0.5

        # Set color levels to focus on the meaningful data range
        self.grid_view.setLevels(vmin, vmax)

        # Reset view to fit the image
        view = self.grid_view.getView()
        if view is not None:
            view.setRange(xRange=(0, grid.shape[1]), yRange=(0, grid.shape[0]), padding=0.05)

    def _to_heatmap(self, grid: np.ndarray) -> np.ndarray:
        if grid.ndim == 2:
            return grid
        if grid.ndim == 3:
            return np.nanmean(grid, axis=0)
        flat = grid.ravel()
        side = max(2, int(np.ceil(np.sqrt(flat.size))))
        out = np.full((side, side), np.nan, dtype=float)
        out.flat[: flat.size] = flat
        return out

    def _render_detail_card(self, result_row: dict[str, Any]) -> None:
        stats = result_row.get("stats") or {}
        risk_flags = derive_result_risk_flags(result_row)
        metric = result_row.get("metric", "-")
        info = self.METRIC_INFO.get(metric, {})
        unit = info.get("unit", "")
        threshold = info.get("threshold")
        threshold_src = info.get("threshold_source", "")

        lines = [
            f"指标: {metric}",
            f"单位: {unit}" if unit else "",
            f"站点: {result_row.get('station_id', '-')}",
            f"系统: {result_row.get('system', '-')}",
            f"链级: {result_row.get('chain_level', '-')}",
            f"采样: {result_row.get('sampling_mode', '-')}",
            f"坐标源: {result_row.get('coordinate_source', '-')}",
            f"阈值源: {result_row.get('threshold_source', '-')}",
            "",
            "统计:",
            f"  最小值: {stats.get('min', '-')}",
            f"  最大值: {stats.get('max', '-')}",
            f"  平均值: {stats.get('mean', '-')}",
            f"  缺失率: {stats.get('missing_ratio', '-')}",
            "",
        ]
        if threshold is not None:
            lines.append(f"阈值: {threshold} {unit} ({threshold_src})")
        lines.append(f"风险: {risk_flags_to_text(risk_flags)}")
        self.detail_text.setPlainText("\n".join(lines))

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

        # 获取该项目的所有任务并删除结果
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
                    # 删除任务及其结果
                    self.bus.dispatch(channels.TASK_DELETE, {"taskId": task_id, "force": True})
                    deleted += 1

        self._all_results = []
        self.result_list.clear()
        self._clear_panels()
        self._set_status(f"已清空 {deleted} 个任务的结果")
        self._load_task_list()
        QMessageBox.information(self, "完成", f"已清空 {deleted} 个任务的结果")

    def _export_current_result(self) -> None:
        if not self._current_result:
            QMessageBox.warning(self, "警告", "请先选择结果")
            return

        project_id = self._current_result.get("project_id") or self.project_id or "default"
        default_dir = Path("workspace") / "outputs" / str(project_id)
        try:
            default_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            QMessageBox.critical(self, "错误", "无法创建导出目录")
            return

        default_name = f"{self._current_result.get('metric', 'result')}_{self._current_result.get('id', 'x')}.npz"
        output_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出结果",
            str(default_dir / default_name),
            "NumPy (*.npz);;MATLAB (*.mat);;JSON (*.json)",
        )
        if not output_path:
            return

        path = Path(output_path)
        if not path.suffix:
            if "matlab" in selected_filter.lower():
                path = path.with_suffix(".mat")
            elif "json" in selected_filter.lower():
                path = path.with_suffix(".json")
            else:
                path = path.with_suffix(".npz")

        payload = {
            "outputPath": str(path),
            "resultId": self._current_result.get("id"),
            "projectId": self._current_result.get("project_id") or self.project_id,
        }
        rsp = self.bus.dispatch(channels.RESULT_EXPORT, payload)
        if rsp.success:
            QMessageBox.information(self, "成功", f"导出完成: {rsp.data.get('outputPath')}")
        else:
            QMessageBox.critical(self, "错误", rsp.error.message if rsp.error else "导出失败")
