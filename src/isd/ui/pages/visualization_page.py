from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QObject
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
from isd.ui.i18n import LanguageManager, tr
from isd.ui.widgets.map_widget import MapWidget


class _NoScaleAxis(pg.AxisItem):
    """AxisItem that always uses scale=1.0 for tick labels."""

    def tickStrings(self, values, scale, spacing):
        return super().tickStrings(values, 1.0, spacing)


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
    lat = station.get("latitude")
    lon = station.get("longitude")
    h = station.get("height") or 0.0
    if lat is not None and lon is not None and (abs(lat) > 180 or abs(lon) > 180):
        new_lat, new_lon = _ecef_to_lla(float(lat), float(lon), float(h))
        station = {**station, "latitude": new_lat, "longitude": new_lon}
    return station


def _grid_binning(
    all_ipp_lats: list[np.ndarray],
    all_ipp_lons: list[np.ndarray],
    all_values: list[np.ndarray],
    lat_edges: np.ndarray,
    lon_edges: np.ndarray,
    n_hours: int = 24,
) -> np.ndarray:
    """Grid binning per M_ISSION get_rotigrid.m / hourgrid.m.

    Bins scatter-point IPP observations into a regular lat/lon grid.
    Overlapping values in the same cell are averaged.
    Returns (n_hours, nlat, nlon) array with NaN where no data.
    """
    nlat = len(lat_edges) - 1
    nlon = len(lon_edges) - 1
    lat_min = float(lat_edges[0])
    lon_min = float(lon_edges[0])
    lat_res = float(lat_edges[1] - lat_edges[0])
    lon_res = float(lon_edges[1] - lon_edges[0])

    grid_3d = np.full((n_hours, nlat, nlon), np.nan, dtype=float)

    for h in range(n_hours):
        grid = np.full((nlat, nlon), np.nan, dtype=float)

        for ipp_lats, ipp_lons, values in zip(all_ipp_lats, all_ipp_lons, all_values):
            n_epochs = ipp_lats.shape[0]
            ep_per_hour = max(1, n_epochs // n_hours)
            s_idx = h * ep_per_hour
            e_idx = min(s_idx + ep_per_hour, n_epochs)
            if s_idx >= n_epochs:
                continue

            seg_lats = ipp_lats[s_idx:e_idx]
            seg_lons = ipp_lons[s_idx:e_idx]
            seg_vals = values[s_idx:e_idx]

            valid = np.isfinite(seg_lats) & np.isfinite(seg_lons) & np.isfinite(seg_vals)
            lat_v = seg_lats[valid]
            lon_v = seg_lons[valid]
            val_v = seg_vals[valid]

            lat_idx = np.ceil((lat_v - lat_min) / lat_res).astype(int) - 1
            lon_idx = np.ceil((lon_v - lon_min) / lon_res).astype(int) - 1

            in_bounds = (lat_idx >= 0) & (lat_idx < nlat) & (lon_idx >= 0) & (lon_idx < nlon)
            lat_idx = lat_idx[in_bounds]
            lon_idx = lon_idx[in_bounds]
            val_v = val_v[in_bounds]

            # Vectorized binning: first-hit assignment + running average
            valid_idx = lat_idx >= 0  # all are in-bounds from earlier filter
            li = lat_idx[valid_idx]
            lo = lon_idx[valid_idx]
            vv = val_v[valid_idx]
            if li.size == 0:
                continue
            # Mark empty cells with first value
            empty_mask = np.isnan(grid[li, lo])
            grid[li[empty_mask], lo[empty_mask]] = vv[empty_mask]
            # Average already-filled cells
            filled_mask = ~empty_mask
            if filled_mask.any():
                grid[li[filled_mask], lo[filled_mask]] = (
                    grid[li[filled_mask], lo[filled_mask]] + vv[filled_mask]
                ) / 2.0

        grid_3d[h] = grid

    return grid_3d


def _idw_interpolate(
    sta_data: dict[str, tuple[float, float, np.ndarray]],
    lat_edges: np.ndarray,
    lon_edges: np.ndarray,
    n_hours: int = 24,
    power: float = 2.0,
) -> np.ndarray:
    """Inverse Distance Weighting interpolation — fallback for results without IPP data."""
    nlat = len(lat_edges) - 1
    nlon = len(lon_edges) - 1
    lat_centers = 0.5 * (lat_edges[:-1] + lat_edges[1:])
    lon_centers = 0.5 * (lon_edges[:-1] + lon_edges[1:])
    lon_grid, lat_grid = np.meshgrid(lon_centers, lat_centers)

    codes = list(sta_data.keys())
    sta_lats = np.array([sta_data[c][0] for c in codes])
    sta_lons = np.array([sta_data[c][1] for c in codes])

    sta_hourly = np.full((len(codes), n_hours), np.nan, dtype=float)
    for i, code in enumerate(codes):
        vals = sta_data[code][2]
        if vals.ndim == 2:
            n_epochs = vals.shape[0]
            ep_per_hour = max(1, n_epochs // n_hours)
            for h in range(n_hours):
                s_idx = h * ep_per_hour
                e_idx = min(s_idx + ep_per_hour, n_epochs)
                if s_idx < n_epochs:
                    chunk = vals[s_idx:e_idx, :]
                    v = np.nanmean(chunk)
                    if np.isfinite(v):
                        sta_hourly[i, h] = v
        else:
            if vals.ndim == 1 and len(vals) <= n_hours:
                for h in range(len(vals)):
                    if np.isfinite(vals[h]):
                        sta_hourly[i, h] = float(vals[h])
            elif vals.ndim == 1:
                ep_per_hour = max(1, len(vals) // n_hours)
                for h in range(n_hours):
                    s_idx = h * ep_per_hour
                    e_idx = min(s_idx + ep_per_hour, len(vals))
                    v = np.nanmean(vals[s_idx:e_idx])
                    if np.isfinite(v):
                        sta_hourly[i, h] = v

    grid_3d = np.full((n_hours, nlat, nlon), np.nan, dtype=float)
    for h in range(n_hours):
        valid_mask = np.isfinite(sta_hourly[:, h])
        if not valid_mask.any():
            continue
        sv = sta_hourly[valid_mask, h]
        sl = sta_lats[valid_mask]
        sw = sta_lons[valid_mask]

        weights = np.zeros((nlat, nlon, len(sv)), dtype=float)
        for k in range(len(sv)):
            dist2 = (lat_grid - sl[k]) ** 2 + (lon_grid - sw[k]) ** 2
            dist2 = np.maximum(dist2, 1e-10)
            weights[:, :, k] = 1.0 / (dist2 ** (power / 2.0))

        w_sum = weights.sum(axis=2)
        w_sum[w_sum < 1e-30] = np.nan
        field = np.nansum(weights * sv[np.newaxis, np.newaxis, :], axis=2) / w_sum
        grid_3d[h, :, :] = field

    return grid_3d


class _MapComputeWorker(QObject):
    """Background worker for grid-binning map computation (M_ISSION style)."""
    finished = Signal(object)

    def __init__(self, bus: CommandBus, payload: dict, all_results: list,
                 stations_cache: list, project_id: str | None,
                 result_row: dict, metric: str) -> None:
        super().__init__()
        self.bus = bus
        self.payload = payload
        self.all_results = all_results
        self.stations_cache = stations_cache
        self.project_id = project_id
        self.result_row = result_row
        self.metric = metric

    def run(self) -> None:
        try:
            result = self._compute_map_data()
            self.finished.emit(result)
        except Exception:
            self.finished.emit(None)

    def _compute_map_data(self) -> dict | None:
        metric = self.metric
        info = VisualizationPage.METRIC_INFO.get(metric, {})
        unit = info.get("unit", "")

        # Collect per-station data (with optional IPP)
        all_ipp_lats: list[np.ndarray] = []
        all_ipp_lons: list[np.ndarray] = []
        all_values_2d: list[np.ndarray] = []
        sta_data: dict[str, tuple[float, float, np.ndarray]] = {}

        loaded_stations: set[str] = set()
        for r in self.all_results:
            r_metric = r.get("metric", "")
            r_station = (r.get("station_id") or "").upper()
            if r_metric != metric or not r_station:
                continue
            if r_station in loaded_stations:
                continue

            s_payload = {
                "resultId": str(r.get("id") or ""),
                "projectId": str(r.get("project_id") or self.project_id or ""),
            }
            s_rsp = self.bus.dispatch(channels.RESULT_GET_SERIES, s_payload)
            if not s_rsp.success:
                continue
            s_raw = s_rsp.data or {}
            try:
                s_vals = np.asarray(s_raw.get("values", []), dtype=float)
                s_ipp_b = np.asarray(s_raw.get("ipp_b", []), dtype=float)
                s_ipp_l = np.asarray(s_raw.get("ipp_l", []), dtype=float)
            except Exception:
                continue

            if s_vals.size == 0:
                continue

            # For AATR (1D hourly), use iaatr_raw (2D per-epoch) for grid binning
            s_vals_for_map = s_vals
            if self.metric == "AATR":
                iaatr_raw = np.asarray(s_raw.get("iaatr_raw", []), dtype=float)
                if iaatr_raw.size > 0 and iaatr_raw.ndim == 2:
                    s_vals_for_map = iaatr_raw

            # Match station coordinates from cache
            sl, sw = None, None
            for s in self.stations_cache:
                code = (s.get("station_code") or "").upper()
                sid = (s.get("station_id") or "").upper()
                if code == r_station or sid == r_station:
                    sl = s.get("latitude")
                    sw = s.get("longitude")
                    break

            has_ipp = s_ipp_b.size > 0 and s_ipp_l.size > 0 and s_ipp_b.shape == s_vals_for_map.shape
            if has_ipp:
                all_ipp_lats.append(s_ipp_b)
                all_ipp_lons.append(s_ipp_l)
                all_values_2d.append(s_vals_for_map)
            elif sl is not None and sw is not None:
                sta_data[r_station] = (sl, sw, s_vals)

            loaded_stations.add(r_station)

        # Fallback: try loading current result if not yet loaded
        station_id = (self.result_row.get("station_id") or "").upper()
        if station_id and station_id not in loaded_stations:
            rsp = self.bus.dispatch(channels.RESULT_GET_SERIES, self.payload)
            if rsp.success:
                data = rsp.data or {}
                try:
                    values = np.asarray(data.get("values", []), dtype=float)
                    ipp_b = np.asarray(data.get("ipp_b", []), dtype=float)
                    ipp_l = np.asarray(data.get("ipp_l", []), dtype=float)

                    # For AATR, use iaatr_raw for grid binning
                    vals_for_map = values
                    if self.metric == "AATR":
                        iaatr_raw = np.asarray(data.get("iaatr_raw", []), dtype=float)
                        if iaatr_raw.size > 0 and iaatr_raw.ndim == 2:
                            vals_for_map = iaatr_raw

                    has_ipp = ipp_b.size > 0 and ipp_l.size > 0 and ipp_b.shape == vals_for_map.shape
                    if vals_for_map.size > 0 and has_ipp:
                        all_ipp_lats.append(ipp_b)
                        all_ipp_lons.append(ipp_l)
                        all_values_2d.append(vals_for_map)
                        loaded_stations.add(station_id)
                    elif values.size > 0:
                        for sta in self.stations_cache:
                            code = (sta.get("station_code") or "").upper()
                            sid = (sta.get("station_id") or "").upper()
                            if code == station_id or sid == station_id:
                                slat = sta.get("latitude")
                                slon = sta.get("longitude")
                                if slat is not None and slon is not None:
                                    sta_data[station_id] = (slat, slon, values)
                                break
                        loaded_stations.add(station_id)
                except Exception:
                    pass

        # Primary path: IPP grid binning
        if all_ipp_lats:
            return self._build_ipp_grid(all_ipp_lats, all_ipp_lons, all_values_2d, unit, metric, loaded_stations)

        # Fallback: station-based IDW for results without IPP data
        if sta_data:
            return self._build_idw_fallback(sta_data, unit, metric, station_id)

        return None

    def _build_ipp_grid(self, all_ipp_lats, all_ipp_lons, all_values_2d, unit, metric, loaded_stations) -> dict:
        all_lat_pts = np.concatenate([a[np.isfinite(a)].ravel() for a in all_ipp_lats])
        all_lon_pts = np.concatenate([a[np.isfinite(a)].ravel() for a in all_ipp_lons])
        if all_lat_pts.size == 0 or all_lon_pts.size == 0:
            return None

        # Use station coordinates for display bounds (zoom to station region),
        # not raw IPP coverage which can span the entire globe.
        sta_lats = [s["latitude"] for s in self.stations_cache if s.get("latitude") is not None]
        sta_lons = [s["longitude"] for s in self.stations_cache if s.get("longitude") is not None]
        if sta_lats and sta_lons:
            lat_lo = max(-90.0, min(sta_lats) - 8.0)
            lat_hi = min(90.0, max(sta_lats) + 8.0)
            lon_lo = max(-180.0, min(sta_lons) - 12.0)
            lon_hi = min(180.0, max(sta_lons) + 12.0)
        else:
            lat_lo = max(-90.0, float(np.min(all_lat_pts)) - 3.0)
            lat_hi = min(90.0, float(np.max(all_lat_pts)) + 3.0)
            lon_lo = max(-180.0, float(np.min(all_lon_pts)) - 5.0)
            lon_hi = min(180.0, float(np.max(all_lon_pts)) + 5.0)

        grid_res = 1.0
        lat_edges = np.arange(lat_lo, lat_hi + grid_res * 0.5, grid_res)
        lon_edges = np.arange(lon_lo, lon_hi + grid_res * 0.5, grid_res)

        grid_3d = _grid_binning(
            all_ipp_lats, all_ipp_lons, all_values_2d,
            lat_edges, lon_edges, n_hours=24,
        )

        finite = grid_3d[np.isfinite(grid_3d)]
        vmax = float(np.nanmax(finite)) if finite.size > 0 else 1.0
        vmax = max(vmax, 0.01)

        return {
            "grid_3d": grid_3d,
            "lat_edges": lat_edges,
            "lon_edges": lon_edges,
            "unit": unit,
            "metric": metric,
            "station_id": self.result_row.get("station_id", ""),
            "n_sta": len(loaded_stations),
            "vmin": 0.0,
            "vmax": vmax,
        }

    def _build_idw_fallback(self, sta_data, unit, metric, station_id) -> dict:
        all_lats = [sl for sl, _, _ in sta_data.values()]
        all_lons = [sw for _, sw, _ in sta_data.values()]
        lat_lo = min(all_lats) - 15.0
        lat_hi = max(all_lats) + 15.0
        lon_lo = min(all_lons) - 20.0
        lon_hi = max(all_lons) + 20.0
        lat_lo, lat_hi = max(-90.0, lat_lo), min(90.0, lat_hi)
        lon_lo, lon_hi = max(-180.0, lon_lo), min(180.0, lon_hi)

        grid_res = 1.0
        lat_edges = np.arange(lat_lo, lat_hi + grid_res * 0.5, grid_res)
        lon_edges = np.arange(lon_lo, lon_hi + grid_res * 0.5, grid_res)

        grid_3d = _idw_interpolate(sta_data, lat_edges, lon_edges, n_hours=24, power=2.0)

        finite = grid_3d[np.isfinite(grid_3d)]
        vmax = float(np.nanmax(finite)) if finite.size > 0 else 1.0
        vmax = max(vmax, 0.01)

        return {
            "grid_3d": grid_3d,
            "lat_edges": lat_edges,
            "lon_edges": lon_edges,
            "unit": unit,
            "metric": metric,
            "station_id": station_id,
            "n_sta": len(sta_data),
            "vmin": 0.0,
            "vmax": vmax,
        }


class VisualizationPage(QWidget):
    def __init__(self, bus: CommandBus) -> None:
        super().__init__()
        self.bus = bus
        self._lm = LanguageManager.instance()
        self.project_id: str | None = None
        self._all_results: list[dict[str, Any]] = []
        self._filtered_results: list[dict[str, Any]] = []
        self._current_result: dict[str, Any] | None = None
        self._refresh_timer: QTimer | None = None
        self._stations_cache: list[dict[str, Any]] = []

        self.task_selector = QComboBox()
        self.task_selector.setMinimumWidth(300)
        self.task_selector.currentTextChanged.connect(self._on_task_selector_changed)

        # Filters
        self.station_filter = QComboBox()
        self.station_filter.setMinimumWidth(120)
        self.system_filter = QComboBox()
        self.system_filter.setMinimumWidth(100)
        self.metric_filter = QComboBox()
        self.metric_filter.setMinimumWidth(120)
        self.station_filter.currentIndexChanged.connect(self._apply_filters)
        self.system_filter.currentIndexChanged.connect(self._apply_filters)
        self.metric_filter.currentIndexChanged.connect(self._apply_filters)

        self.result_list = QListWidget()
        self.result_list.itemClicked.connect(self._on_result_selected)

        self.series_plot = pg.PlotWidget(
            axisItems={"left": _NoScaleAxis(orientation="left")}
        )
        self.series_plot.setBackground("#121a2e")
        self.series_plot.showGrid(x=True, y=True, alpha=0.25)
        self.series_plot.getAxis("bottom").setTextPen("#8b9bb4")
        self.series_plot.getAxis("left").setTextPen("#8b9bb4")

        # Cartopy Robinson geographic map widgets (replacing pyqtgraph ImageView)
        self.grid_map = MapWidget()
        self.metric_map = MapWidget()

        # Background map computation
        self._map_thread: QThread | None = None
        self._map_worker: _MapComputeWorker | None = None
        self._zombie_map_threads: list[QThread] = []

        # Store tab widgets for dynamic show/hide
        self._grid_tab_widget: QWidget | None = None
        self._map_tab_widget: QWidget | None = None

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)

        self.status_hint = QLabel(tr("vis.status.loading"))

        self._build_ui()
        self._load_task_list()
        self._start_auto_refresh()

        self._lm.language_changed.connect(self._retranslate)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.title_label = QLabel(tr("vis.title"))
        self.title_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #00e5ff; margin: 10px 0;")
        layout.addWidget(self.title_label)

        selector_layout = QHBoxLayout()
        self.task_lbl = QLabel(tr("vis.select_task"))
        selector_layout.addWidget(self.task_lbl)
        selector_layout.addWidget(self.task_selector)
        selector_layout.addStretch()
        layout.addLayout(selector_layout)

        # Filter row
        filter_layout = QHBoxLayout()
        self.station_filter_lbl = QLabel(tr("vis.filter.station"))
        filter_layout.addWidget(self.station_filter_lbl)
        filter_layout.addWidget(self.station_filter)
        self.system_filter_lbl = QLabel(tr("vis.filter.system"))
        filter_layout.addWidget(self.system_filter_lbl)
        filter_layout.addWidget(self.system_filter)
        self.metric_filter_lbl = QLabel(tr("vis.filter.metric"))
        filter_layout.addWidget(self.metric_filter_lbl)
        filter_layout.addWidget(self.metric_filter)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        layout.addWidget(self.status_hint)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.setStyleSheet("""
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
        self._series_tab_idx = self.tabs.addTab(series_tab, tr("vis.tab.series"))

        # Grid and Map tab widgets are created but NOT added to tabs initially.
        # They are dynamically inserted based on the selected metric type.
        grid_tab = QWidget()
        grid_layout = QVBoxLayout(grid_tab)
        grid_layout.addWidget(self.grid_map)
        self._grid_tab_idx = -1
        self._grid_tab_widget = grid_tab

        map_tab = QWidget()
        map_layout = QVBoxLayout(map_tab)
        map_layout.addWidget(self.metric_map)
        self._map_tab_idx = -1
        self._map_tab_widget = map_tab

        detail_tab = QWidget()
        detail_layout = QVBoxLayout(detail_tab)
        detail_layout.addWidget(self.detail_text)
        self._detail_tab_idx = self.tabs.addTab(detail_tab, tr("vis.tab.detail"))

        main_split = QSplitter(Qt.Orientation.Horizontal)
        main_split.addWidget(self.result_list)
        main_split.addWidget(self.tabs)
        main_split.setSizes([300, 1100])
        layout.addWidget(main_split)

        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton(tr("vis.btn.refresh"))
        self.refresh_btn.setProperty("secondary", "true")
        self.refresh_btn.clicked.connect(self._load_task_list)
        self.export_btn = QPushButton(tr("vis.btn.export"))
        self.export_btn.setProperty("secondary", "true")
        self.export_btn.clicked.connect(self._export_current_result)
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
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addWidget(self.export_btn)
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _retranslate(self) -> None:
        self.title_label.setText(tr("vis.title"))
        self.task_lbl.setText(tr("vis.select_task"))
        self.station_filter_lbl.setText(tr("vis.filter.station"))
        self.system_filter_lbl.setText(tr("vis.filter.system"))
        self.metric_filter_lbl.setText(tr("vis.filter.metric"))
        self.status_hint.setText(tr("vis.status.loading"))
        self.refresh_btn.setText(tr("vis.btn.refresh"))
        self.export_btn.setText(tr("vis.btn.export"))
        self.clear_btn.setText(tr("vis.btn.clear"))
        self.tabs.setTabText(self._series_tab_idx, tr("vis.tab.series"))
        if self._grid_tab_idx >= 0:
            self.tabs.setTabText(self._grid_tab_idx, tr("vis.tab.grid"))
        if self._map_tab_idx >= 0:
            self.tabs.setTabText(self._map_tab_idx, tr("vis.tab.map"))
        self.tabs.setTabText(self._detail_tab_idx, tr("vis.tab.detail"))
        # Repopulate filters so "All" text updates
        if self._all_results:
            self._populate_filters()

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
        if text == tr("vis.select_task_placeholder"):
            self.project_id = None
            self._all_results = []
            self._filtered_results = []
            self.result_list.clear()
            self._clear_panels()
            self._set_status(tr("vis.status.select_task"))
            return

        task_data = self.task_selector.currentData()
        if task_data:
            self.project_id = task_data.get("project_id")
            self.refresh()

    def refresh(self) -> None:
        if not self.project_id:
            self._all_results = []
            self._filtered_results = []
            self.result_list.clear()
            self._clear_panels()
            self._set_status(tr("vis.status.select_task"))
            return

        rsp = self.bus.dispatch(channels.RESULT_LIST, {"projectId": self.project_id})
        if not rsp.success:
            self._all_results = []
            self._filtered_results = []
            self.result_list.clear()
            self._set_status(tr("vis.status.failed"))
            return

        self._all_results = rsp.data or []

        sta_rsp = self.bus.dispatch(channels.PROJECT_GET_STATIONS, {"projectId": self.project_id})
        raw_stations = sta_rsp.data if sta_rsp.success else []
        self._stations_cache = [_ensure_geographic(s) for s in raw_stations]

        # Auto-zoom maps to station region to avoid rendering the full globe
        if self._stations_cache:
            self.grid_map.set_station_bounds(self._stations_cache)
            self.metric_map.set_station_bounds(self._stations_cache)

        self._populate_filters()
        self._apply_filters()

        self._set_status(tr("vis.status.loaded").replace("{0}", str(len(self._all_results))))

    def _populate_filters(self) -> None:
        all_stations = sorted({str(r.get("station_id", "")) for r in self._all_results if r.get("station_id")})
        all_systems = sorted({str(r.get("system", "")) for r in self._all_results if r.get("system")})
        all_metrics = sorted({str(r.get("metric", "")) for r in self._all_results if r.get("metric")})

        for combo, items, all_text in [
            (self.station_filter, all_stations, tr("vis.filter.all")),
            (self.system_filter, all_systems, tr("vis.filter.all")),
            (self.metric_filter, all_metrics, tr("vis.filter.all")),
        ]:
            combo.blockSignals(True)
            current = combo.currentText()
            combo.clear()
            combo.addItem(all_text, "")
            for item in items:
                combo.addItem(item, item)
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    def _apply_filters(self) -> None:
        station_kw = self.station_filter.currentData() or ""
        system_kw = self.system_filter.currentData() or ""
        metric_kw = self.metric_filter.currentData() or ""

        filtered = self._all_results
        if station_kw:
            filtered = [r for r in filtered if r.get("station_id", "") == station_kw]
        if system_kw:
            filtered = [r for r in filtered if r.get("system", "") == system_kw]
        if metric_kw:
            filtered = [r for r in filtered if r.get("metric", "") == metric_kw]

        self._filtered_results = filtered
        self._render_result_list()

        if self._filtered_results:
            self.result_list.setCurrentRow(0)
            self._on_result_selected(self.result_list.item(0))

    def _set_status(self, msg: str) -> None:
        self.status_hint.setText(msg)

    def _render_result_list(self) -> None:
        self.result_list.clear()
        for row in self._filtered_results:
            metric = row.get("metric", "-")
            station = row.get("station_id") or "-"
            system = row.get("system") or "-"
            text = f"{metric} | {station} | {system}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, row)
            self.result_list.addItem(item)

    def _clear_panels(self) -> None:
        self._cancel_map_thread()
        self.series_plot.clear()
        self.grid_map.clear()
        self.metric_map.clear()
        self.detail_text.clear()

    def _on_result_selected(self, item: QListWidgetItem) -> None:
        if not item:
            return
        row = item.data(Qt.ItemDataRole.UserRole) or {}
        self._current_result = row
        metric = row.get("metric", "")

        # DIXSG: Series + Grid + Detail  (DIXSG is a regional raster, no Map)
        # Others: Series + Map  + Detail  (regional map via IPP interpolation, no Grid)
        grid_visible = metric == "DIXSG"
        map_visible = metric != "DIXSG"

        self._sync_tab_visibility(grid_visible, map_visible)
        self._render_detail_card(row)

        # Defer heavy I/O so the tab switch repaints first
        QTimer.singleShot(0, lambda row=row, grid_visible=grid_visible, map_visible=map_visible:
                          self._deferred_load(row, grid_visible, map_visible))

    def _deferred_load(self, row: dict, grid_visible: bool, map_visible: bool) -> None:
        self._load_series(row)
        if grid_visible:
            self._load_grid(row)
        if map_visible:
            self._load_map_async(row)

    def _sync_tab_visibility(self, grid_visible: bool, map_visible: bool) -> None:
        """Show or hide Grid and Map tabs based on metric type."""
        # Remove tabs in reverse index order to avoid index shifting issues
        indices = []
        if self._map_tab_idx >= 0:
            indices.append(self._map_tab_idx)
        if self._grid_tab_idx >= 0:
            indices.append(self._grid_tab_idx)
        for idx in sorted(indices, reverse=True):
            if idx < self.tabs.count():
                self.tabs.removeTab(idx)
        self._grid_tab_idx = -1
        self._map_tab_idx = -1

        # Re-insert in correct positions: Series(0), [Grid(1)], [Map(1|2)], Detail(last)
        insert_pos = 1  # after Series tab

        if grid_visible and self._grid_tab_widget is not None:
            self._grid_tab_idx = self.tabs.insertTab(insert_pos, self._grid_tab_widget, tr("vis.tab.grid"))
            insert_pos += 1
        if map_visible and self._map_tab_widget is not None:
            self._map_tab_idx = self.tabs.insertTab(insert_pos, self._map_tab_widget, tr("vis.tab.map"))
            insert_pos += 1

        # Update detail tab index
        self._detail_tab_idx = self.tabs.count() - 1

        # Auto-switch to the newly inserted tab so it renders immediately
        if grid_visible and self._grid_tab_idx >= 0:
            self.tabs.setCurrentIndex(self._grid_tab_idx)
        elif map_visible and self._map_tab_idx >= 0:
            self.tabs.setCurrentIndex(self._map_tab_idx)

    def _on_tab_changed(self, index: int) -> None:
        """Lazy-render maps only when their tab becomes active."""
        grid_idx = getattr(self, "_grid_tab_idx", -1)
        map_idx = getattr(self, "_map_tab_idx", -1)
        if index == grid_idx and grid_idx >= 0:
            self.grid_map.ensure_rendered()
        elif index == map_idx and map_idx >= 0:
            self.metric_map.ensure_rendered()

    METRIC_INFO = {
        "ROTI": {"unit": "TECU/min", "label": "ROTI (TECU/min)", "threshold": 0.5, "threshold_source": "Pi et al. (1997)"},
        "AATR": {"unit": "TECU/min", "label": "AATR (TECU/min)", "threshold": 0.2, "threshold_source": "Sanz et al. (2014)"},
        "IAATR": {"unit": "TECU/min", "label": "IAATR (TECU/min)", "threshold": 0.2, "threshold_source": "Sanz et al. (2014)"},
        "DIXSG": {"unit": "index", "label": "DIXSG", "threshold": 0.5, "threshold_source": "Jakowski et al. (2012)"},
        "SIGMA_PHI_F": {"unit": "m", "label": "σϕf (m)", "threshold": 0.05, "threshold_source": "Ahmed et al. (2015)"},
        "S4C": {"unit": "dimensionless", "label": "S4C", "threshold": 0.25, "threshold_source": "Van Dierendonck et al. (1993); Zhang et al. (2026)"},
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
            reason = rsp.error.message if rsp.error else "unknown error"
            self.series_plot.setTitle(f"{metric} - data unavailable: {reason}", color="#ff1744", size="10pt")
            return

        data = rsp.data or {}
        try:
            values = np.asarray(data.get("values", []), dtype=float)
        except Exception:
            self.series_plot.clear()
            return

        info = self.METRIC_INFO.get(result_row.get("metric", ""), {})
        y_label = info.get("label", "Value")
        station = result_row.get("station_id", "-")
        system = result_row.get("system", "-")
        metric = result_row.get("metric", "")

        self.series_plot.clear()
        self.series_plot.setTitle(f"{metric} - {station} ({system})", color="#8b9bb4", size="11pt")
        self.series_plot.setLabel("left", y_label, color="#8b9bb4")

        is_hourly = metric in ("AATR", "DIXSG")
        self.series_plot.setLabel("bottom", "Hour (UT)" if is_hourly else "Epoch", color="#8b9bb4")
        self.series_plot.addLegend(offset=(60, 10))

        time_axis = np.asarray(data.get("time", np.arange(values.shape[0] if values.ndim >= 1 else 0)), dtype=float)
        if is_hourly and values.ndim == 1 and time_axis.shape[0] <= 25:
            time_axis = np.arange(time_axis.shape[0], dtype=float)

        view_range = self._compute_view_range(time_axis, values, info)

        if values.ndim == 1:
            y = values
            if time_axis.shape[0] != y.shape[0]:
                time_axis = np.arange(y.shape[0], dtype=float)
            label = "RMS AATR" if metric == "AATR" else ("aDIXSG" if metric == "DIXSG" else metric)
            pen_width = 2.5 if is_hourly else 1.5
            self.series_plot.plot(time_axis, y, pen=pg.mkPen("#00e5ff", width=pen_width), name=label,
                                 symbol='o' if is_hourly else None, symbolSize=8, symbolBrush='#00e5ff')
        elif values.ndim >= 2:
            if time_axis.shape[0] != values.shape[0]:
                time_axis = np.arange(values.shape[0], dtype=float)
            num_cols = min(values.shape[1], 8)
            colors = ["#00e5ff", "#ff6b6b", "#ffd93d", "#6bcb77", "#4d96ff", "#ff922b", "#cc5de8", "#20c997"]
            sat_ids = result_row.get("satellite_ids") or []
            system = result_row.get("system", "GPS")
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
            mean_val = np.nanmean(values, axis=1)
            self.series_plot.plot(
                time_axis, mean_val,
                pen=pg.mkPen("w", width=2.0, style=Qt.PenStyle.DashLine),
                name="Mean",
            )
        else:
            self.series_plot.clear()
            return

        threshold = info.get("threshold")
        if threshold is not None:
            self.series_plot.addLine(
                y=threshold,
                pen=pg.mkPen("#ff1744", width=1.5, style=Qt.PenStyle.DashLine),
            )

        if view_range is not None:
            pi = self.series_plot.getPlotItem()
            pi.setRange(**view_range, padding=0, disableAutoRange=True)

    def _compute_view_range(self, time_axis: np.ndarray, values: np.ndarray, info: dict) -> dict | None:
        finite_mask = np.isfinite(values)
        if not finite_mask.any():
            return None
        finite_vals = values[finite_mask]
        y_min = float(np.percentile(finite_vals, 1))
        y_max = float(np.percentile(finite_vals, 99))
        threshold = info.get("threshold")
        if threshold is not None:
            y_min = min(y_min, threshold * 0.8)
            y_max = max(y_max, threshold * 1.2)
        if y_max - y_min < 1e-12:
            y_min -= 0.5
            y_max += 0.5
        y_padding = (y_max - y_min) * 0.1
        y_min -= y_padding
        y_max += y_padding
        x_min = float(time_axis[0])
        x_max = float(time_axis[-1])
        if x_max - x_min < 1e-12:
            x_min -= 1.0
            x_max += 1.0
        x_padding = (x_max - x_min) * 0.02
        x_min -= x_padding
        x_max += x_padding
        return {"xRange": (x_min, x_max), "yRange": (y_min, y_max)}

    # ── DIXSG Grid — real geographic Robinson map with discrete colorbar ──

    def _load_grid(self, result_row: dict[str, Any]) -> None:
        metric = result_row.get("metric", "")
        payload = {
            "resultId": str(result_row.get("id") or ""),
            "projectId": str(result_row.get("project_id") or self.project_id or ""),
        }
        if not payload["resultId"] or not payload["projectId"]:
            self.grid_map.clear()
            return

        rsp = self.bus.dispatch(channels.RESULT_GET_GRID, payload)
        if rsp.success:
            data = rsp.data or {}
            grid = np.asarray(data.get("grid", []), dtype=float)
            if grid.ndim == 3 and grid.shape[0] == 24 and grid.size > 0:
                self._render_dixsg_map(grid, data, metric)
                return

        # Fallback: no pre-computed grid — show empty map
        self.grid_map.clear()

    def _render_dixsg_map(
        self, grid: np.ndarray, data: dict, metric: str,
    ) -> None:
        """Render DIXSG grid on the Cartopy Robinson map with discrete colorbar."""
        info = self.METRIC_INFO.get(metric, {})
        unit = info.get("unit", "")

        # Extract coordinate ranges from grid metadata (lat_range, lon_range, or mbl)
        lat_range = data.get("lat_range")
        lon_range = data.get("lon_range")
        mbl = data.get("mbl")

        if lat_range is not None and lon_range is not None:
            lat_lo, lat_hi = float(lat_range[0]), float(lat_range[1])
            lon_lo, lon_hi = float(lon_range[0]), float(lon_range[1])
        elif mbl is not None:
            mbl = np.asarray(mbl).flatten()
            lon_lo, lon_hi = float(mbl[1]), float(mbl[0])
            lat_lo, lat_hi = float(mbl[3]), float(mbl[2])
        else:
            # Fallback: derive from station bounds
            sta_lats = [s["latitude"] for s in self._stations_cache if s.get("latitude") is not None]
            sta_lons = [s["longitude"] for s in self._stations_cache if s.get("longitude") is not None]
            if sta_lats and sta_lons:
                lat_lo = min(sta_lats) - 15.0
                lat_hi = max(sta_lats) + 15.0
                lon_lo = min(sta_lons) - 20.0
                lon_hi = max(sta_lons) + 20.0
            else:
                lat_lo, lat_hi = 0.0, 40.0
                lon_lo, lon_hi = 80.0, 130.0

        # Fixed 1.0° resolution grid edges
        grid_res = 1.0
        nlat = grid.shape[1]
        nlon = grid.shape[2]
        lat_edges = np.linspace(lat_lo, lat_hi, nlat + 1)
        lon_edges = np.linspace(lon_lo, lon_hi, nlon + 1)

        # DIXSG discrete levels: extract from grid data
        finite = grid[np.isfinite(grid)]
        dixsg_levels = None
        if finite.size > 0:
            max_val = int(np.nanmax(finite))
            if max_val > 0:
                dixsg_levels = max_val

        vmax = max(float(np.nanmax(finite)) if finite.size > 0 else 1.0, 0.01)

        stations = [
            {"latitude": s["latitude"], "longitude": s["longitude"],
             "station_code": s.get("station_code", "")}
            for s in self._stations_cache
            if s.get("latitude") is not None and s.get("longitude") is not None
        ]

        self.grid_map.set_map_data(
            grid_3d=grid,
            lat_edges=lat_edges,
            lon_edges=lon_edges,
            stations=stations,
            metric=metric,
            unit=unit,
            vmin=0.0,
            vmax=vmax,
            dixsg_levels=dixsg_levels,
        )

    # ── Regional Map for non-DIXSG metrics — IDW interpolation on Cartopy Robinson map ──

    def _load_map_async(self, result_row: dict[str, Any]) -> None:
        """Launch IDW map computation in a background thread."""
        metric = result_row.get("metric", "")
        if metric == "DIXSG":
            return

        payload = {
            "resultId": str(result_row.get("id") or ""),
            "projectId": str(result_row.get("project_id") or self.project_id or ""),
        }
        if not payload["resultId"] or not payload["projectId"]:
            self.metric_map.clear()
            return

        self._cancel_map_thread()
        self.metric_map.clear()
        self.status_hint.setText(f"{metric} — computing map...")

        self._map_thread = QThread()
        self._map_worker = _MapComputeWorker(
            self.bus, payload, self._all_results, self._stations_cache,
            self.project_id, result_row, metric,
        )
        self._map_worker.moveToThread(self._map_thread)
        self._map_thread.started.connect(self._map_worker.run)
        self._map_worker.finished.connect(self._on_map_computed)
        self._map_worker.finished.connect(self._map_thread.quit)
        self._map_thread.start()

    def _cancel_map_thread(self) -> None:
        # Park old thread so it won't be GC'd while running.
        if self._map_thread is not None:
            if self._map_thread.isRunning():
                try:
                    self._map_worker.finished.disconnect(self._on_map_computed)
                except (RuntimeError, TypeError):
                    pass
                try:
                    self._map_worker.finished.disconnect(self._map_thread.quit)
                except (RuntimeError, TypeError):
                    pass
                self._map_thread.quit()
            self._zombie_map_threads.append(self._map_thread)
        self._map_thread = None
        self._map_worker = None
        # Reap finished zombies
        self._zombie_map_threads = [t for t in self._zombie_map_threads if t.isRunning()]

    def _on_map_computed(self, result: dict | None) -> None:
        """Handle IDW map computation result — pass data to Cartopy MapWidget."""
        if result is None:
            self.metric_map.clear()
            self.status_hint.setText(tr("vis.status.no_data"))
            return

        grid_3d = result["grid_3d"]
        lat_edges = result["lat_edges"]
        lon_edges = result["lon_edges"]
        unit = result["unit"]
        metric = result["metric"]
        n_sta = result["n_sta"]
        vmin = result["vmin"]
        vmax = result["vmax"]

        stations = [
            {"latitude": s["latitude"], "longitude": s["longitude"],
             "station_code": s.get("station_code", "")}
            for s in self._stations_cache
            if s.get("latitude") is not None and s.get("longitude") is not None
        ]

        self.metric_map.set_map_data(
            grid_3d=grid_3d,
            lat_edges=lat_edges,
            lon_edges=lon_edges,
            stations=stations,
            metric=metric,
            unit=unit,
            vmin=vmin,
            vmax=vmax,
        )

        self.status_hint.setText(
            f"{metric} {tr('vis.tab.map')} — {n_sta} stations, IPP grid binning, 24 hourly frames"
        )

    def _render_detail_card(self, result_row: dict[str, Any]) -> None:
        stats = result_row.get("stats") or {}
        risk_flags = derive_result_risk_flags(result_row)
        metric = result_row.get("metric", "-")
        info = self.METRIC_INFO.get(metric, {})
        unit = info.get("unit", "")
        threshold = info.get("threshold")
        threshold_src = info.get("threshold_source", "")

        lines = [
            f"{tr('detail.metric')}: {metric}",
            f"{tr('detail.unit')}: {unit}" if unit else "",
            f"{tr('detail.station')}: {result_row.get('station_id', '-')}",
            f"{tr('detail.system')}: {result_row.get('system', '-')}",
            f"{tr('detail.chain')}: {result_row.get('chain_level', '-')}",
            f"{tr('detail.sampling')}: {result_row.get('sampling_mode', '-')}",
            f"{tr('detail.coord_src')}: {result_row.get('coordinate_source', '-')}",
            f"{tr('detail.threshold_src')}: {result_row.get('threshold_source', '-')}",
            "",
            f"{tr('detail.stats')}:",
            f"  {tr('detail.min')}: {stats.get('min', '-')}",
            f"  {tr('detail.max')}: {stats.get('max', '-')}",
            f"  {tr('detail.mean')}: {stats.get('mean', '-')}",
            f"  {tr('detail.missing')}: {stats.get('missing_ratio', '-')}",
            "",
        ]
        if threshold is not None:
            lines.append(f"{tr('detail.threshold')}: {threshold} {unit} ({threshold_src})")
        lines.append(f"{tr('detail.risk')}: {risk_flags_to_text(risk_flags)}")
        self.detail_text.setPlainText("\n".join(lines))

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
            QMessageBox.critical(self, tr("dlg.error"), "Failed to get task list")
            return

        deleted = 0
        for task in task_rsp.data or []:
            task_project_id = task.get("project_id")
            if task_project_id == self.project_id:
                task_id = task.get("id")
                if task_id:
                    self.bus.dispatch(channels.TASK_DELETE, {"taskId": task_id, "force": True})
                    deleted += 1

        self._all_results = []
        self._filtered_results = []
        self.result_list.clear()
        self._clear_panels()
        self._set_status(f"Cleared {deleted} task(s)")
        self._load_task_list()
        QMessageBox.information(self, tr("dlg.success"), f"Cleared {deleted} task(s)")

    def _export_current_result(self) -> None:
        if not self._current_result:
            QMessageBox.warning(self, tr("dlg.warning"), tr("export.select_result"))
            return

        project_id = self._current_result.get("project_id") or self.project_id or "default"
        default_dir = Path("workspace") / "outputs" / str(project_id)
        try:
            default_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            QMessageBox.critical(self, tr("dlg.error"), "Cannot create export directory")
            return

        default_name = f"{self._current_result.get('metric', 'result')}_{self._current_result.get('id', 'x')}.npz"
        output_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            tr("export.title"),
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
            QMessageBox.information(self, tr("export.done"), f"Exported: {rsp.data.get('outputPath')}")
        else:
            QMessageBox.critical(self, tr("export.failed"), rsp.error.message if rsp.error else "Export failed")
