"""Data Preprocessing page with sky plots and satellite elevation charts."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from isd.application import channels
from isd.application.command_bus import CommandBus
from isd.ui.i18n import LanguageManager, tr


class _PolarPlotWidget(pg.PlotWidget):
    """Polar (sky) plot using pyqtgraph. 0° = North, 90° = East.

    Zenith is at center (elevation=90°); horizon is at the outer ring.
    Azimuth is plotted clockwise from North.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setBackground("#121a2e")
        self.setAspectLocked(True)
        self.hideButtons()

        plot = self.getPlotItem()
        plot.getAxis("bottom").setPen("#8b9bb4")
        plot.getAxis("left").setPen("#8b9bb4")
        plot.getAxis("bottom").setTextPen("#8b9bb4")
        plot.getAxis("left").setTextPen("#8b9bb4")

    def draw_grid(self) -> None:
        """Draw elevation circles (30, 60, 90) and azimuth lines (N/E/S/W)."""
        self.clear()
        pi = self.getPlotItem()
        for elev in [0, 30, 60]:
            r = 90 - elev
            angle = np.linspace(0, 2 * np.pi, 200)
            x = r * np.sin(angle)
            y = r * np.cos(angle)
            self.plot(x, y, pen=pg.mkPen("#2a3a5c", width=1))

        for az in range(0, 360, 45):
            rad = math.radians(az)
            x_end = 90 * math.sin(rad)
            y_end = 90 * math.cos(rad)
            self.plot([0, x_end], [0, y_end], pen=pg.mkPen("#2a3a5c", width=0.5))

        # Cardinal labels
        for az_deg, label_text, color in [
            (0, "N", "#ff6b6b"),
            (90, "E", "#8b9bb4"),
            (180, "S", "#8b9bb4"),
            (270, "W", "#8b9bb4"),
        ]:
            rad = math.radians(az_deg)
            r = 98
            x = r * math.sin(rad)
            y = r * math.cos(rad)
            txt = pg.TextItem(text=label_text, color=color, anchor=(0.5, 0.5))
            txt.setPos(x, y)
            self.addItem(txt)

        # Elevation labels
        for elev in [30, 60]:
            txt = pg.TextItem(text=f"{elev}°", color="#8b9bb4", anchor=(0, 0))
            txt.setPos(2, 90 - elev)
            self.addItem(txt)

        pi.setRange(xRange=(-105, 105), yRange=(-105, 105), padding=0)

    def plot_satellite_track(
        self,
        azimuth_rad: np.ndarray,
        elevation_rad: np.ndarray,
        color: str = "#00e5ff",
        label: str = "",
    ) -> None:
        """Plot a single satellite track in polar coords, splitting at discontinuities."""
        mask = np.isfinite(azimuth_rad) & np.isfinite(elevation_rad) & (elevation_rad > 0)
        if mask.sum() < 2:
            return
        az = azimuth_rad[mask]
        el = elevation_rad[mask]

        # Convert: r = 90 - elevation_deg, angle = azimuth
        r = 90.0 - np.degrees(el)
        x = r * np.sin(az)
        y = r * np.cos(az)

        # Detect large jumps where azimuth wraps around (e.g. 359° -> 1°)
        # In polar (x,y) space this shows as a large spatial gap
        if len(x) > 1:
            dx = np.abs(np.diff(x))
            dy = np.abs(np.diff(y))
            jump = np.sqrt(dx ** 2 + dy ** 2)
            split_indices = np.where(jump > 30)[0]  # 30 units ≈ 30° gap threshold
        else:
            split_indices = np.array([], dtype=int)

        if len(split_indices) == 0:
            self.plot(x, y, pen=pg.mkPen(color, width=1.2))
        else:
            # Split into continuous segments
            prev = 0
            for idx in split_indices:
                seg_x = x[prev:idx + 1]
                seg_y = y[prev:idx + 1]
                if len(seg_x) >= 2:
                    self.plot(seg_x, seg_y, pen=pg.mkPen(color, width=1.2))
                prev = idx + 1
            # Last segment
            seg_x = x[prev:]
            seg_y = y[prev:]
            if len(seg_x) >= 2:
                self.plot(seg_x, seg_y, pen=pg.mkPen(color, width=1.2))

        # Label at last valid position
        if label:
            txt = pg.TextItem(text=label, color=color, anchor=(0, 1))
            txt.setPos(x[-1], y[-1])
            self.addItem(txt)


_SAT_COLORS = [
    "#00e5ff", "#ff6b6b", "#ffd93d", "#6bcb77", "#4d96ff",
    "#ff922b", "#cc5de8", "#20c997", "#e84393", "#fdcb6e",
    "#6c5ce7", "#00cec9", "#fd79a8", "#55efc4", "#a29bfe",
]


class PreprocessPage(QWidget):
    def __init__(self, bus: CommandBus) -> None:
        super().__init__()
        self.bus = bus
        self.project_id: str | None = None
        self._lm = LanguageManager.instance()

        # Task selector
        self.task_combo = QComboBox()
        self.task_combo.setMinimumWidth(350)
        self.task_combo.currentIndexChanged.connect(self._on_task_changed)

        # Station / system selectors
        self.station_combo = QComboBox()
        self.station_combo.setMinimumWidth(200)
        self.station_combo.currentIndexChanged.connect(self._on_station_changed)
        self.system_combo = QComboBox()
        self.system_combo.addItems(["GPS", "GLO", "GAL", "BDS"])
        self.system_combo.setMinimumWidth(100)
        self.system_combo.currentIndexChanged.connect(self._on_station_changed)

        self.sky_plot = _PolarPlotWidget()
        self.sky_plot.draw_grid()

        self.elev_plot = pg.PlotWidget()
        self.elev_plot.setBackground("#121a2e")
        self.elev_plot.showGrid(x=True, y=True, alpha=0.25)
        self.elev_plot.getAxis("bottom").setTextPen("#8b9bb4")
        self.elev_plot.getAxis("left").setTextPen("#8b9bb4")
        self.elev_plot.addLegend(offset=(60, 10))

        self.sat_count_plot = pg.PlotWidget()
        self.sat_count_plot.setBackground("#121a2e")
        self.sat_count_plot.showGrid(x=True, y=True, alpha=0.25)
        self.sat_count_plot.getAxis("bottom").setTextPen("#8b9bb4")
        self.sat_count_plot.getAxis("left").setTextPen("#8b9bb4")

        self.status_label = QLabel(tr("preprocess.no_data"))
        self.status_label.setStyleSheet("color: #8b9bb4; font-size: 12px;")

        self._build_ui()
        self._load_task_list()
        self._start_auto_refresh()
        self._lm.language_changed.connect(self._retranslate)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.title_label = QLabel(tr("preprocess.title"))
        self.title_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #00e5ff; margin: 10px 0;")
        layout.addWidget(self.title_label)

        # Task selector row
        task_row = QHBoxLayout()
        self.task_lbl = QLabel(tr("vis.select_task"))
        task_row.addWidget(self.task_lbl)
        task_row.addWidget(self.task_combo)
        task_row.addStretch()
        layout.addLayout(task_row)

        # Station / system row
        ctrl = QHBoxLayout()
        self.station_lbl = QLabel(tr("preprocess.select_station"))
        ctrl.addWidget(self.station_lbl)
        ctrl.addWidget(self.station_combo)
        self.system_lbl = QLabel(tr("preprocess.select_system"))
        ctrl.addWidget(self.system_lbl)
        ctrl.addWidget(self.system_combo)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        layout.addWidget(self.status_label)

        # Splitter: sky plot | elevation + sat count
        right_split = QSplitter(Qt.Orientation.Vertical)
        right_split.addWidget(self.elev_plot)
        right_split.addWidget(self.sat_count_plot)
        right_split.setSizes([400, 200])

        main_split = QSplitter(Qt.Orientation.Horizontal)
        main_split.addWidget(self.sky_plot)
        main_split.addWidget(right_split)
        main_split.setSizes([500, 700])
        layout.addWidget(main_split)

    def _start_auto_refresh(self) -> None:
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._load_task_list)
        self._refresh_timer.start(5000)

    def _retranslate(self) -> None:
        self.title_label.setText(tr("preprocess.title"))
        self.task_lbl.setText(tr("vis.select_task"))
        self.station_lbl.setText(tr("preprocess.select_station"))
        self.system_lbl.setText(tr("preprocess.select_system"))
        if not self.project_id:
            self.status_label.setText(tr("preprocess.no_data"))

    def _load_task_list(self) -> None:
        self.task_combo.blockSignals(True)
        current_data = self.task_combo.currentData()
        self.task_combo.clear()
        self.task_combo.addItem(tr("vis.select_task_placeholder"), None)

        rsp = self.bus.dispatch(channels.TASK_LIST, {})
        if rsp.success:
            for task in rsp.data or []:
                task_id = task.get("id", "")
                name = task.get("name", "unnamed")
                status = task.get("status", "")
                text = f"{name} [{status}] {task_id[:12]}..."
                self.task_combo.addItem(text, task)

        # Restore previous selection
        if current_data:
            for i in range(self.task_combo.count()):
                if self.task_combo.itemData(i) and self.task_combo.itemData(i).get("id") == current_data.get("id"):
                    self.task_combo.setCurrentIndex(i)
                    break

        self.task_combo.blockSignals(False)

    def _on_task_changed(self, index: int) -> None:
        task_data = self.task_combo.currentData()
        if not task_data:
            self.project_id = None
            self.station_combo.clear()
            self._clear_plots()
            self.status_label.setText(tr("preprocess.no_data"))
            return

        self.project_id = task_data.get("project_id")
        self._load_stations_for_task(task_data)

    def _load_stations_for_task(self, task_data: dict) -> None:
        """Load station list from task config and auto-select first station."""
        if not self.project_id:
            return

        # Get stations from project
        rsp = self.bus.dispatch(channels.PROJECT_GET_STATIONS, {"projectId": self.project_id})
        self.station_combo.blockSignals(True)
        self.station_combo.clear()
        if rsp.success:
            for sta in rsp.data or []:
                code = sta.get("station_code", "")
                if code:
                    self.station_combo.addItem(code, sta)
        self.station_combo.blockSignals(False)

        # Auto-load if a station is available
        if self.station_combo.count() > 0:
            self._on_station_changed(0)
        else:
            self._clear_plots()
            self.status_label.setText(tr("preprocess.no_data"))

    def _on_station_changed(self, index: int) -> None:
        """Auto-load data when station or system changes."""
        station_data = self.station_combo.currentData()
        if not station_data or not self.project_id:
            return
        self._load_data(station_data)

    def _clear_plots(self) -> None:
        self.sky_plot.draw_grid()
        self.elev_plot.clear()
        self.sat_count_plot.clear()

    def _load_data(self, station_data: dict) -> None:
        station_code = station_data.get("station_code", "")
        gnss_system = self.system_combo.currentText()

        obs_path = self._find_obs_file(station_code)
        if not obs_path:
            self.status_label.setText(f"No OBS file found for station {station_code}")
            self._clear_plots()
            return

        sp3_paths = self._find_sp3_files()

        self.status_label.setText("Loading...")
        self.sky_plot.draw_grid()
        self.elev_plot.clear()
        self.sat_count_plot.clear()

        try:
            from isd.algorithms.rinex_compute import compute_scintillation_from_rinex
            result = compute_scintillation_from_rinex(
                obs_path,
                compute_metrics=[],
                sp3_paths=sp3_paths,
                gnss_system=gnss_system,
            )
        except Exception as exc:
            self.status_label.setText(f"Error: {exc}")
            return

        if result.elevation_rad is None or result.azimuth_rad is None:
            self.status_label.setText("No SP3 data — cannot compute sky plot without ephemeris")
            return

        elev = result.elevation_rad
        az = result.azimuth_rad
        sat_ids = result.satellite_ids or []

        n_sats = elev.shape[1] if elev.ndim == 2 else 1
        n_epochs = elev.shape[0]

        # ── Sky plot ──
        self.sky_plot.draw_grid()
        for col in range(min(n_sats, 15)):
            if elev.ndim == 2:
                e_col = elev[:, col]
                a_col = az[:, col]
            else:
                e_col = elev
                a_col = az

            label = sat_ids[col] if col < len(sat_ids) else f"S{col + 1:02d}"
            color = _SAT_COLORS[col % len(_SAT_COLORS)]
            self.sky_plot.plot_satellite_track(a_col, e_col, color=color, label=label)

        # ── Elevation vs time ──
        self.elev_plot.setTitle("Satellite Elevation", color="#8b9bb4", size="11pt")
        self.elev_plot.setLabel("left", "Elevation (°)", color="#8b9bb4")
        self.elev_plot.setLabel("bottom", "Epoch", color="#8b9bb4")

        time_axis = np.arange(n_epochs, dtype=float)
        for col in range(min(n_sats, 15)):
            if elev.ndim == 2:
                e_col = np.degrees(elev[:, col])
            else:
                e_col = np.degrees(elev)

            label = sat_ids[col] if col < len(sat_ids) else f"S{col + 1:02d}"
            color = _SAT_COLORS[col % len(_SAT_COLORS)]
            self.elev_plot.plot(
                time_axis, e_col,
                pen=pg.mkPen(color, width=1.0),
                name=label,
            )

        # ── Satellite count vs time ──
        self.sat_count_plot.setTitle("Satellite Count", color="#8b9bb4", size="11pt")
        self.sat_count_plot.setLabel("left", "# Satellites", color="#8b9bb4")
        self.sat_count_plot.setLabel("bottom", "Epoch", color="#8b9bb4")

        if elev.ndim == 2:
            above_horizon = np.isfinite(elev) & (elev > 0)
            sat_count = above_horizon.sum(axis=1).astype(float)
        else:
            sat_count = np.where(np.isfinite(elev) & (elev > 0), 1.0, 0.0)

        self.sat_count_plot.plot(
            time_axis, sat_count,
            pen=pg.mkPen("#00e5ff", width=2.0),
            fillLevel=0,
            fillBrush=pg.mkBrush(0, 229, 255, 40),
        )

        self.status_label.setText(
            f"Station: {station_code} | System: {gnss_system} | "
            f"Satellites: {n_sats} | Epochs: {n_epochs}"
        )

    def set_project(self, project_id: str) -> None:
        self.project_id = project_id
        # Reload task list filtered to this project and try to auto-load
        self._load_task_list()
        # Also load stations for this project
        self._load_stations_from_project(project_id)

    def _load_stations_from_project(self, project_id: str) -> None:
        """Load station combo from project (used when set_project is called from nav)."""
        rsp = self.bus.dispatch(channels.PROJECT_GET_STATIONS, {"projectId": project_id})
        self.station_combo.blockSignals(True)
        current = self.station_combo.currentText()
        self.station_combo.clear()
        if rsp.success:
            for sta in rsp.data or []:
                code = sta.get("station_code", "")
                if code:
                    self.station_combo.addItem(code, sta)
        # Restore selection
        idx = self.station_combo.findText(current)
        if idx >= 0:
            self.station_combo.setCurrentIndex(idx)
        self.station_combo.blockSignals(False)

    def _find_obs_file(self, station_code: str) -> str | None:
        """Find OBS file for the given station from project files."""
        scan_rsp = self.bus.dispatch(channels.PROJECT_SCAN_FILES, {
            "projectId": self.project_id,
        })
        if not scan_rsp.success:
            return None
        files = (scan_rsp.data or {}).get("files", [])
        for f in files:
            if f.get("kind") == "OBS":
                sid = (f.get("station_id") or "").upper()
                code = (f.get("station_code") or "").upper()
                path = f.get("file_path", "")
                if station_code.upper() in (sid, code) and path:
                    return path
        return None

    def _find_sp3_files(self) -> list[str]:
        """Find SP3 files for the current project."""
        scan_rsp = self.bus.dispatch(channels.PROJECT_SCAN_FILES, {
            "projectId": self.project_id,
        })
        if not scan_rsp.success:
            return []
        files = (scan_rsp.data or {}).get("files", [])
        paths = []
        for f in files:
            if f.get("kind") == "SP3":
                path = f.get("file_path", "")
                if path:
                    paths.append(path)
        return paths
