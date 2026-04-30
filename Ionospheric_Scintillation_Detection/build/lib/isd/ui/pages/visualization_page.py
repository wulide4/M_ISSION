from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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


class VisualizationPage(QWidget):
    def __init__(self, bus: CommandBus) -> None:
        super().__init__()
        self.bus = bus
        self.project_id: str | None = None
        self._all_results: list[dict[str, Any]] = []
        self._current_result: dict[str, Any] | None = None

        self.project_filter = QLineEdit()
        self.project_filter.setReadOnly(True)
        self.project_filter.setPlaceholderText("当前项目")

        self.metric_filter = QLineEdit()
        self.metric_filter.setPlaceholderText("按指标筛选，例如 ROTI / DIXSG")
        self.station_filter = QLineEdit()
        self.station_filter.setPlaceholderText("按站点筛选，例如 ALBH")
        self.metric_filter.textChanged.connect(self._render_result_list)
        self.station_filter.textChanged.connect(self._render_result_list)

        self.result_list = QListWidget()
        self.result_list.itemClicked.connect(self._on_result_selected)

        self.series_plot = pg.PlotWidget()
        self.series_plot.setBackground("k")
        self.series_plot.showGrid(x=True, y=True, alpha=0.25)

        self.grid_view = pg.ImageView()
        self.grid_view.ui.roiBtn.hide()
        self.grid_view.ui.menuBtn.hide()
        self.grid_view.setImage(np.zeros((2, 2), dtype=float))

        self.intermediate_list = QListWidget()
        self.intermediate_list.itemClicked.connect(self._preview_intermediate_file)
        self.intermediate_preview = QTextEdit()
        self.intermediate_preview.setReadOnly(True)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText("选择结果后显示统计卡片与元数据。")
        self.risk_hint = QLabel("风险标识: FORMAL_PIPELINE")
        self.grid_hint = QLabel("区域栅格: N/A")
        self.status_hint = QLabel("状态[NO_PROJECT] 未选择项目")

        refresh_btn = QPushButton("刷新结果")
        refresh_btn.clicked.connect(self.refresh)
        export_btn = QPushButton("导出当前结果")
        export_btn.clicked.connect(self._export_current_result)

        filter_form = QFormLayout()
        filter_form.addRow("项目", self.project_filter)
        filter_form.addRow("指标筛选", self.metric_filter)
        filter_form.addRow("站点筛选", self.station_filter)

        tabs = QTabWidget()

        series_tab = QWidget()
        series_layout = QVBoxLayout(series_tab)
        series_layout.addWidget(self.series_plot)
        tabs.addTab(series_tab, "时序图")

        grid_tab = QWidget()
        grid_layout = QVBoxLayout(grid_tab)
        grid_layout.addWidget(self.grid_view)
        grid_layout.addWidget(self.grid_hint)
        tabs.addTab(grid_tab, "区域栅格")

        intermediate_tab = QWidget()
        intermediate_layout = QVBoxLayout(intermediate_tab)
        split_mid = QSplitter(Qt.Orientation.Horizontal)
        split_mid.addWidget(self.intermediate_list)
        split_mid.addWidget(self.intermediate_preview)
        split_mid.setSizes([360, 880])
        intermediate_layout.addWidget(split_mid)
        tabs.addTab(intermediate_tab, "中间结果")

        detail_tab = QWidget()
        detail_layout = QVBoxLayout(detail_tab)
        detail_layout.addWidget(self.risk_hint)
        detail_layout.addWidget(self.detail_text)
        tabs.addTab(detail_tab, "详情卡")

        root = QVBoxLayout(self)
        root.addWidget(QLabel("<h2>结果可视化</h2>"))

        top_row = QHBoxLayout()
        top_row.addLayout(filter_form, 5)
        top_row.addWidget(refresh_btn, 1)
        top_row.addWidget(export_btn, 1)
        root.addLayout(top_row)
        root.addWidget(self.status_hint)

        main_split = QSplitter(Qt.Orientation.Horizontal)
        main_split.addWidget(self.result_list)
        main_split.addWidget(tabs)
        main_split.setSizes([360, 1160])
        root.addWidget(main_split)

    def set_project(self, project_id: str) -> None:
        self.project_id = project_id
        self.project_filter.setText(project_id)
        self.metric_filter.clear()
        self.station_filter.clear()
        self._set_status("LOADING", f"当前项目 {project_id}，正在刷新结果")
        self.refresh()

    def refresh(self) -> None:
        if not self.project_id:
            self._all_results = []
            self._render_result_list()
            self._set_status("NO_PROJECT", "未选择项目")
            return

        rsp = self.bus.dispatch(channels.RESULT_LIST, {"projectId": self.project_id})
        if not rsp.success:
            msg = rsp.error.message if rsp.error else "结果列表加载失败"
            QMessageBox.warning(self, "warn", msg)
            self._set_status("LOAD_FAILED", msg)
            self._all_results = []
            self._render_result_list()
            return

        self._all_results = rsp.data or []
        self._set_status("READY", f"已加载结果 {len(self._all_results)} 条")
        self._render_result_list()

    def _set_status(self, state: str, message: str) -> None:
        self.status_hint.setText(f"状态[{state}] {message}")

    def _render_result_list(self) -> None:
        self.result_list.clear()
        self._current_result = None

        metric_kw = self.metric_filter.text().strip().upper()
        station_kw = self.station_filter.text().strip().upper()

        filtered: list[dict[str, Any]] = []
        for row in self._all_results:
            metric = str(row.get("metric", "")).upper()
            station = str(row.get("station_id") or "").upper()
            if metric_kw and metric_kw not in metric:
                continue
            if station_kw and station_kw not in station:
                continue
            filtered.append(row)

        for row in filtered:
            metric = row.get("metric", "-")
            station = row.get("station_id") or "-"
            system = row.get("system") or "-"
            created_at = row.get("created_at", "")
            text = f"{metric} | {station} | {system} | {created_at}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, row)
            self.result_list.addItem(item)

        if not filtered:
            self._clear_result_panels()
            if self.project_id:
                self._set_status(
                    "NO_RESULT",
                    f"当前筛选无结果（project={self.project_id}, metric={metric_kw or '*'}, station={station_kw or '*'})",
                )
            return

        first_item = self.result_list.item(0)
        self.result_list.setCurrentRow(0)
        self._on_result_selected(first_item)

    def _clear_result_panels(self) -> None:
        self.series_plot.clear()
        self.grid_view.setImage(np.zeros((2, 2), dtype=float), autoLevels=True)
        self.intermediate_list.clear()
        self.intermediate_preview.clear()
        self.detail_text.clear()
        self.risk_hint.setText("风险标识: FORMAL_PIPELINE")
        self.grid_hint.setText("区域栅格: N/A")

    def _on_result_selected(self, item: QListWidgetItem) -> None:
        row = item.data(Qt.ItemDataRole.UserRole) or {}
        self._current_result = row
        self._render_detail_card(row)
        self._load_series(row)
        self._load_grid(row)
        self._load_intermediate_files(row)

    def _result_query_payload(self, result_row: dict[str, Any]) -> dict[str, str]:
        return {
            "resultId": str(result_row.get("id") or ""),
            "projectId": str(result_row.get("project_id") or self.project_id or ""),
        }

    def _load_series(self, result_row: dict[str, Any]) -> None:
        payload = self._result_query_payload(result_row)
        if not payload["resultId"] or not payload["projectId"]:
            self._set_status("FORMAT_INVALID", "结果缺少 resultId/projectId")
            self.series_plot.clear()
            return

        rsp = self.bus.dispatch(channels.RESULT_GET_SERIES, payload)
        if not rsp.success:
            code = rsp.error.code if rsp.error else "UNKNOWN"
            msg = rsp.error.message if rsp.error else "时序加载失败"
            if code in {"SERIES_NOT_AVAILABLE", "SERIES_FORMAT_INVALID"}:
                self._set_status("FORMAT_INVALID", msg)
            else:
                self._set_status("LOAD_FAILED", msg)
            self.series_plot.clear()
            return

        data = rsp.data or {}
        try:
            values = np.asarray(data["values"], dtype=float)
        except Exception:  # noqa: BLE001
            self._set_status("FORMAT_INVALID", "时序 values 字段格式不正确")
            self.series_plot.clear()
            return

        if values.ndim == 1:
            y = values
        elif values.ndim >= 2:
            y = np.nanmean(values, axis=1)
        else:
            self._set_status("FORMAT_INVALID", "时序 values 维度无效")
            self.series_plot.clear()
            return

        time_axis = np.asarray(data.get("time", np.arange(y.shape[0])), dtype=float)
        if time_axis.shape[0] != y.shape[0]:
            time_axis = np.arange(y.shape[0], dtype=float)

        self.series_plot.clear()
        self.series_plot.plot(time_axis, y, pen=pg.mkPen("#00e5ff", width=1.5))
        self._set_status("READY", f"已渲染时序数据（{y.shape[0]} 点）")

    def _load_grid(self, result_row: dict[str, Any]) -> None:
        payload = self._result_query_payload(result_row)
        if not payload["resultId"] or not payload["projectId"]:
            self.grid_view.setImage(np.zeros((2, 2), dtype=float), autoLevels=True)
            self.grid_hint.setText("区域栅格: 结果缺少 resultId/projectId")
            return

        rsp = self.bus.dispatch(channels.RESULT_GET_GRID, payload)
        if not rsp.success:
            code = rsp.error.code if rsp.error else "UNKNOWN"
            msg = rsp.error.message if rsp.error else "栅格加载失败"
            if code == "GRID_NOT_AVAILABLE":
                self.grid_view.setImage(np.zeros((2, 2), dtype=float), autoLevels=True)
                self.grid_hint.setText("区域栅格: 当前结果没有 grid 数据")
                return
            if code == "GRID_FORMAT_INVALID":
                self.grid_view.setImage(np.zeros((2, 2), dtype=float), autoLevels=True)
                self.grid_hint.setText("区域栅格: grid 数据格式错误")
                self._set_status("FORMAT_INVALID", msg)
                return
            self.grid_view.setImage(np.zeros((2, 2), dtype=float), autoLevels=True)
            self.grid_hint.setText(f"区域栅格: 加载失败（{msg}）")
            self._set_status("LOAD_FAILED", msg)
            return

        data = rsp.data or {}
        grid = np.asarray(data.get("grid", []), dtype=float)
        if grid.size == 0:
            self.grid_view.setImage(np.zeros((2, 2), dtype=float), autoLevels=True)
            self.grid_hint.setText("区域栅格: grid 为空")
            return

        heatmap = self._to_heatmap(grid)
        self.grid_view.setImage(np.nan_to_num(heatmap, nan=0.0), autoLevels=True)

        coverage = data.get("coverage")
        valid_count = data.get("validCount")
        total_count = data.get("totalCount")
        shape = data.get("shape") or list(grid.shape)
        if coverage is None:
            total = int(grid.size)
            valid = int(np.isfinite(grid).sum())
            coverage = float(valid / total) if total > 0 else 0.0
            valid_count = valid
            total_count = total

        self.grid_hint.setText(
            f"区域栅格: shape={shape} | 有效网格={valid_count}/{total_count} | 覆盖率={float(coverage):.2%}"
        )

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

    def _load_intermediate_files(self, result_row: dict[str, Any]) -> None:
        self.intermediate_list.clear()
        self.intermediate_preview.clear()

        task_id = result_row.get("task_id")
        if not task_id:
            self.intermediate_preview.setPlainText("当前结果没有 task_id，无法加载中间结果。")
            return

        payload = {
            "taskId": task_id,
            "subTaskId": result_row.get("sub_task_id"),
            "stepKey": result_row.get("metric"),
            "projectId": result_row.get("project_id") or self.project_id,
        }
        rsp = self.bus.dispatch(channels.RESULT_GET_INTERMEDIATE, payload)
        if not rsp.success:
            self.intermediate_preview.setPlainText(rsp.error.message if rsp.error else "中间结果加载失败")
            return

        files = (rsp.data or {}).get("files", [])
        if not files:
            note = (rsp.data or {}).get("note", "未找到中间结果文件")
            self.intermediate_preview.setPlainText(note)
            return

        for file_info in files:
            label = file_info.get("label") or Path(file_info.get("filePath", "")).name
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, file_info.get("filePath"))
            self.intermediate_list.addItem(item)

    def _preview_intermediate_file(self, item: QListWidgetItem) -> None:
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not file_path:
            return
        path = Path(file_path)
        if not path.exists():
            self.intermediate_preview.setPlainText(f"文件不存在: {path}")
            return

        try:
            if path.suffix.lower() == ".json":
                content = json.loads(path.read_text(encoding="utf-8"))
                self.intermediate_preview.setPlainText(json.dumps(content, ensure_ascii=False, indent=2)[:8000])
            else:
                self.intermediate_preview.setPlainText(path.read_text(encoding="utf-8")[:8000])
        except Exception as exc:  # noqa: BLE001
            self.intermediate_preview.setPlainText(f"预览失败: {exc}")

    def _render_detail_card(self, result_row: dict[str, Any]) -> None:
        stats = result_row.get("stats") or {}
        risk_flags = derive_result_risk_flags(result_row)
        self.risk_hint.setText(f"风险标识: {risk_flags_to_text(risk_flags)}")
        lines = [
            f"id: {result_row.get('id', '-')}",
            f"metric: {result_row.get('metric', '-')}",
            f"station: {result_row.get('station_id', '-')}",
            f"system: {result_row.get('system', '-')}",
            f"task: {result_row.get('task_id', '-')}",
            f"subTask: {result_row.get('sub_task_id', '-')}",
            f"chain: {result_row.get('chain_level', '-')}",
            f"sampling: {result_row.get('sampling_mode', '-')}",
            f"coordinateSource: {result_row.get('coordinate_source', '-')}",
            f"thresholdSource: {result_row.get('threshold_source', '-')}",
            f"parameterSourceSummary: {result_row.get('parameter_source_summary', '-')}",
            f"createdAt: {result_row.get('created_at', '-')}",
            "",
            "stats:",
            f"  min={stats.get('min')}",
            f"  max={stats.get('max')}",
            f"  mean={stats.get('mean')}",
            f"  missingRatio={stats.get('missing_ratio')}",
            f"  eventCount={stats.get('event_count')}",
            "",
            f"dataPath: {result_row.get('data_path', '-')}",
            f"previewImagePath: {result_row.get('preview_image_path', '-')}",
        ]
        self.detail_text.setPlainText("\n".join(lines))

    def _export_current_result(self) -> None:
        if not self._current_result:
            QMessageBox.warning(self, "warn", "请先选择一个结果")
            return

        project_id = self._current_result.get("project_id") or self.project_id or "default"
        default_dir = Path("workspace") / "outputs" / str(project_id)
        try:
            default_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "error", f"无法创建导出目录: {exc}")
            return

        default_name = f"{self._current_result.get('metric', 'result')}_{self._current_result.get('id', 'x')}.npz"
        output_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出结果",
            str(default_dir / default_name),
            "NumPy (*.npz);;Parquet (*.parquet);;MATLAB (*.mat);;JSON (*.json)",
        )
        if not output_path:
            return

        path = Path(output_path)
        if not path.suffix:
            if "parquet" in selected_filter.lower():
                path = path.with_suffix(".parquet")
            elif "matlab" in selected_filter.lower():
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
        if not rsp.success:
            QMessageBox.critical(self, "error", rsp.error.message if rsp.error else "导出失败")
            self._set_status("LOAD_FAILED", "结果导出失败")
            return

        self._set_status("READY", f"导出完成: {rsp.data.get('outputPath')}")
        QMessageBox.information(self, "ok", f"导出完成: {rsp.data.get('outputPath')}")
