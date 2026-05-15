"""Geographic map widget using Cartopy + Matplotlib rendered in a background thread.

Provides regional maps with coastlines, raster data overlay,
station markers, colorbar, and a time slider for 24-hour animation.
Heavy Cartopy rendering happens off the GUI thread to prevent freezes.
"""
from __future__ import annotations

import io
import math

import numpy as np
from matplotlib.figure import Figure
from matplotlib.colors import LinearSegmentedColormap
from PySide6.QtCore import Qt, QThread, QTimer, Signal, QObject
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

import cartopy.crs as ccrs
import cartopy.feature as cfeature

# ── Parula colormap (MATLAB default) ──

_PARULA_DATA = [
    (0.2422, 0.1504, 0.6603),
    (0.2810, 0.1806, 0.7257),
    (0.2782, 0.2234, 0.7813),
    (0.2534, 0.2720, 0.8295),
    (0.2160, 0.3243, 0.8649),
    (0.1726, 0.3786, 0.8860),
    (0.1281, 0.4332, 0.8912),
    (0.0889, 0.4876, 0.8814),
    (0.0622, 0.5411, 0.8572),
    (0.0533, 0.5938, 0.8207),
    (0.0645, 0.6450, 0.7746),
    (0.0952, 0.6941, 0.7220),
    (0.1421, 0.7400, 0.6673),
    (0.2011, 0.7823, 0.6149),
    (0.2681, 0.8203, 0.5676),
    (0.3404, 0.8533, 0.5279),
    (0.4155, 0.8805, 0.4971),
    (0.4914, 0.9013, 0.4760),
    (0.5671, 0.9159, 0.4641),
    (0.6430, 0.9240, 0.4595),
    (0.7187, 0.9256, 0.4610),
    (0.7936, 0.9206, 0.4678),
    (0.8680, 0.9090, 0.4786),
    (0.9411, 0.8910, 0.4928),
    (0.9746, 0.8740, 0.5010),
    (0.9780, 0.8570, 0.5100),
    (0.9750, 0.8400, 0.5200),
    (0.9680, 0.8230, 0.5300),
    (0.9590, 0.8060, 0.5400),
    (0.9470, 0.7890, 0.5500),
]

_parula_cmap = LinearSegmentedColormap.from_list("parula", _PARULA_DATA, N=256)


def _render_to_bytes(
    frame_info: dict,
    grid_2d: np.ndarray,
    hour: int,
    station_bounds: tuple | None,
) -> bytes:
    """Render a map frame to PNG bytes (called from background thread)."""
    fig = Figure(figsize=(10, 5), dpi=100, facecolor="#121a2e")
    ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
    ax.set_facecolor("#121a2e")

    lat_edges = frame_info["lat_edges"]
    lon_edges = frame_info["lon_edges"]
    lon_2d, lat_2d = np.meshgrid(lon_edges, lat_edges)

    if grid_2d is not None:
        data_2d = grid_2d
    else:
        data_2d = np.full((len(lat_edges) - 1, len(lon_edges) - 1), np.nan)

    # Features
    ax.add_feature(cfeature.LAND, facecolor="#80b380", alpha=0.6)
    ax.add_feature(cfeature.OCEAN, facecolor="#0a0e17")
    ax.coastlines(resolution="110m", color="#5a6a8a", linewidth=0.5)

    lat_lo = frame_info["lat_lo"]
    lat_hi = frame_info["lat_hi"]
    lon_lo = frame_info["lon_lo"]
    lon_hi = frame_info["lon_hi"]

    # Gridlines
    ax.gridlines(
        draw_labels=True, color="#5a6a8a", alpha=0.6,
        linestyle="--", linewidth=0.5,
    )
    ax.top_labels = False
    ax.right_labels = False

    # Auto-zoom to station region
    ax.set_extent([lon_lo, lon_hi, lat_lo, lat_hi], crs=ccrs.PlateCarree())

    # Raster overlay
    masked_data = np.ma.masked_where(np.isnan(data_2d), data_2d)
    mesh = ax.pcolormesh(
        lon_2d, lat_2d, masked_data,
        transform=ccrs.PlateCarree(),
        cmap=_parula_cmap,
        vmin=frame_info["vmin"],
        vmax=frame_info["vmax"],
        shading="flat",
    )

    # Station markers
    for sta in frame_info.get("stations", []):
        slat = sta.get("latitude")
        slon = sta.get("longitude")
        code = sta.get("station_code", "")
        if slat is None or slon is None:
            continue
        ax.plot(
            slon, slat, marker="o", color="#ffd700", markersize=7,
            markeredgecolor="white", markeredgewidth=0.8,
            transform=ccrs.PlateCarree(), zorder=5,
        )
        ax.text(
            slon + 0.5, slat + 0.5, code, color="#ffd700", fontsize=8,
            fontweight="bold", transform=ccrs.PlateCarree(), zorder=5,
        )

    # Title
    metric = frame_info.get("metric", "")
    ax.set_title(
        f"{metric} Hour - {hour}" if metric else f"Hour {hour}",
        color="#8b9bb4", fontsize=12, pad=10,
    )

    # Colorbar
    cbar = fig.colorbar(mesh, ax=ax, orientation="vertical", pad=0.05, shrink=0.8, aspect=30)
    dixsg_levels = frame_info.get("dixsg_levels")
    if dixsg_levels is not None and dixsg_levels > 0:
        n_levels = dixsg_levels + 1
        ticks = np.linspace(0.5, n_levels - 0.5, n_levels)
        labels = [str(i) for i in range(n_levels)]
        cbar.set_ticks(ticks)
        cbar.set_ticklabels(labels)
        mesh.set_clim(0, n_levels)
    cbar.set_label(frame_info.get("unit", ""), color="#8b9bb4", fontsize=9)
    cbar.ax.yaxis.set_tick_params(color="#8b9bb4")
    for lbl in cbar.ax.yaxis.get_ticklabels():
        lbl.set_color("#8b9bb4")

    fig.tight_layout(pad=1.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    buf.seek(0)
    return buf.getvalue()


class _RenderWorker(QObject):
    """Renders a map frame in a background thread."""
    finished = Signal(bytes, int, int)  # (png_bytes, hour, version)

    def __init__(self, frame_info: dict, grid_2d: np.ndarray | None,
                 hour: int, station_bounds: tuple | None,
                 version: int) -> None:
        super().__init__()
        self._frame_info = frame_info
        self._grid_2d = grid_2d
        self._hour = hour
        self._station_bounds = station_bounds
        self._version = version

    def run(self) -> None:
        try:
            png_data = _render_to_bytes(
                self._frame_info, self._grid_2d, self._hour, self._station_bounds,
            )
            self.finished.emit(png_data, self._hour, self._version)
        except Exception:
            self.finished.emit(b"", self._hour, self._version)


class MapWidget(QWidget):
    """Geographic map widget with time slider for animated regional maps.

    Heavy Cartopy rendering is done in a background QThread. The GUI thread
    only displays the resulting image, so it never freezes.
    """

    hour_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._grid_3d: np.ndarray | None = None
        self._current_hour = 0
        self._n_hours = 0
        self._frame_info: dict = {}
        self._station_bounds: tuple | None = None
        self._rendered = False
        self._slider_timer: QTimer | None = None
        self._render_version = 0  # Monotonically increasing version counter

        # Image display
        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setMinimumHeight(300)
        self._image_label.setStyleSheet("background-color: #121a2e;")

        # Background render thread
        self._render_thread: QThread | None = None
        self._render_worker: _RenderWorker | None = None
        # Park old threads here so they don't get GC'd while still running.
        # Cleaned up lazily in _invalidate_render().
        self._zombie_threads: list[QThread] = []

        # Time slider
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 23)
        self._slider.setValue(0)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._slider.setTickInterval(1)
        self._slider.valueChanged.connect(self._on_slider_changed)

        self._hour_label = QLabel("Hour: 0")
        self._hour_label.setStyleSheet("color: #8b9bb4; font-size: 12px; min-width: 60px;")

        slider_layout = QHBoxLayout()
        slider_layout.addWidget(self._hour_label)
        slider_layout.addWidget(self._slider, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._image_label, 1)
        layout.addLayout(slider_layout)

    # ── Public API ──

    def set_station_bounds(self, stations: list[dict]) -> None:
        if not stations:
            return
        lats = [s["latitude"] for s in stations if s.get("latitude") is not None]
        lons = [s["longitude"] for s in stations if s.get("longitude") is not None]
        if not lats or not lons:
            return
        lat_lo = min(lats) - 5.0
        lat_hi = max(lats) + 5.0
        lon_lo = min(lons) - 8.0
        lon_hi = max(lons) + 8.0
        lat_lo, lat_hi = max(-90.0, lat_lo), min(90.0, lat_hi)
        lon_lo, lon_hi = max(-180.0, lon_lo), min(180.0, lon_hi)
        self._station_bounds = (lon_lo, lon_hi, lat_lo, lat_hi)
        self._rendered = False

    def ensure_rendered(self) -> None:
        if self._rendered:
            # Re-render to match current widget size
            if self._frame_info:
                self._start_render(self._current_hour)
            elif self._station_bounds:
                self._start_render_empty()
            return
        self._rendered = True
        if self._frame_info:
            self._start_render(self._current_hour)
        else:
            self._start_render_empty()

    def set_map_data(
        self,
        grid_3d: np.ndarray,
        lat_edges: np.ndarray,
        lon_edges: np.ndarray,
        stations: list[dict] | None = None,
        metric: str = "",
        unit: str = "",
        vmin: float = 0.0,
        vmax: float = 1.0,
        dixsg_levels: int | None = None,
    ) -> None:
        self._grid_3d = grid_3d
        n_hours = grid_3d.shape[0] if grid_3d.ndim == 3 else 1
        self._n_hours = n_hours
        self._slider.setRange(0, max(0, n_hours - 1))
        self._slider.setValue(0)
        self._current_hour = 0

        self._frame_info = {
            "lat_edges": lat_edges,
            "lon_edges": lon_edges,
            "lat_lo": float(lat_edges[0]),
            "lat_hi": float(lat_edges[-1]),
            "lon_lo": float(lon_edges[0]),
            "lon_hi": float(lon_edges[-1]),
            "stations": stations or [],
            "metric": metric,
            "unit": unit,
            "vmin": vmin,
            "vmax": vmax,
            "dixsg_levels": dixsg_levels,
        }

        self._start_render(0)
        self._rendered = True

    def update_data_only(self, grid_3d: np.ndarray) -> None:
        self._grid_3d = grid_3d
        self._start_render(self._current_hour)

    def clear(self) -> None:
        self._invalidate_render()
        self._frame_info = {}
        self._grid_3d = None
        self._n_hours = 0
        self._slider.setRange(0, 23)
        self._slider.setValue(0)
        self._current_hour = 0
        self._hour_label.setText("Hour: 0")
        self._rendered = False
        self._image_label.clear()
        self._image_label.setStyleSheet("background-color: #121a2e;")

    # ── Background rendering ──

    def _invalidate_render(self) -> None:
        """Bump version so any in-flight render result is discarded."""
        self._render_version += 1
        # Move current thread to zombie list so it won't be GC'd while running.
        # The version check in _on_render_done ensures its result is ignored.
        if self._render_thread is not None:
            self._zombie_threads.append(self._render_thread)
        self._render_thread = None
        self._render_worker = None
        # Reap finished zombies
        self._zombie_threads = [t for t in self._zombie_threads if t.isRunning()]

    def _start_render(self, hour: int) -> None:
        self._invalidate_render()

        info = self._frame_info
        if not info:
            return

        grid_2d = None
        if self._grid_3d is not None:
            grid_2d = self._grid_3d[hour] if self._grid_3d.ndim == 3 else self._grid_3d

        version = self._render_version
        self._render_thread = QThread()
        self._render_worker = _RenderWorker(info, grid_2d, hour, self._station_bounds, version)
        self._render_worker.moveToThread(self._render_thread)
        self._render_thread.started.connect(self._render_worker.run)
        self._render_worker.finished.connect(self._on_render_done)
        self._render_worker.finished.connect(self._render_thread.quit)
        self._render_thread.start()

    def _start_render_empty(self) -> None:
        """Render an empty map (coastlines only) in background."""
        self._invalidate_render()

        if not self._station_bounds:
            return

        lon_lo, lon_hi, lat_lo, lat_hi = self._station_bounds
        grid_res = 1.0
        lat_edges = np.arange(lat_lo, lat_hi + grid_res * 0.5, grid_res)
        lon_edges = np.arange(lon_lo, lon_hi + grid_res * 0.5, grid_res)
        empty_info = {
            "lat_edges": lat_edges,
            "lon_edges": lon_edges,
            "lat_lo": lat_lo,
            "lat_hi": lat_hi,
            "lon_lo": lon_lo,
            "lon_hi": lon_hi,
            "stations": [],
            "metric": "",
            "unit": "",
            "vmin": 0.0,
            "vmax": 1.0,
            "dixsg_levels": None,
        }

        version = self._render_version
        self._render_thread = QThread()
        self._render_worker = _RenderWorker(empty_info, None, 0, self._station_bounds, version)
        self._render_worker.moveToThread(self._render_thread)
        self._render_thread.started.connect(self._render_worker.run)
        self._render_worker.finished.connect(self._on_render_done)
        self._render_worker.finished.connect(self._render_thread.quit)
        self._render_thread.start()

    def _on_render_done(self, png_data: bytes, hour: int, version: int) -> None:
        # Discard stale results from superseded render requests
        if version != self._render_version:
            return
        if not png_data:
            return
        img = QImage()
        img.loadFromData(png_data)
        if img.isNull():
            return
        scaled = img.scaled(
            self._image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(QPixmap.fromImage(scaled))

    # ── Slider ──

    def _on_slider_changed(self, value: int) -> None:
        self._current_hour = value
        self._hour_label.setText(f"Hour: {value}")
        self.hour_changed.emit(value)
        # Debounce: wait 200ms after last slider change before rendering
        if self._frame_info and self._rendered:
            if self._slider_timer is None:
                self._slider_timer = QTimer(self)
                self._slider_timer.setSingleShot(True)
                self._slider_timer.timeout.connect(self._do_slider_render)
            self._slider_timer.start(200)

    def _do_slider_render(self) -> None:
        self._start_render(self._current_hour)
