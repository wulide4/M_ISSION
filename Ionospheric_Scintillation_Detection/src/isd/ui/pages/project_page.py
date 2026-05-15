from __future__ import annotations

import os
import re
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QGroupBox,
    QGridLayout,
)


from isd.application import channels
from isd.application.command_bus import CommandBus


class FileTypeDetector:
    """Auto-detect file type and GNSS system from file name."""

    PATTERNS = {
        "OBS": [r"[A-Z0-9]{4}\d{4}\.\d{2}[oO]$", r".*\.rnx$", r".*\.rnx\.gz$", r".*\.obs$"],
        "SP3": [r".*\.sp3$", r".*\.eph$"],
        "CLK": [r".*\.clk$"],
        "ATX": [r".*\.atx$"],
        "NAV": [r".*\.nav$"],
    }

    SYSTEM_PATTERNS = {
        "GPS": [r"COD0MGX", r"GA", r"GP"],
        "GLO": [r"GLONASS", r"GLU", r"GR"],
        "GAL": [r"GAL", r"E", r"GA"],
        "BDS": [r"BDS", r"BDC", r"QZ"],
    }

    @classmethod
    def detect_file_type(cls, filename: str) -> str | None:
        name = os.path.basename(filename).upper()
        for ftype, patterns in cls.PATTERNS.items():
            for pat in patterns:
                if re.match(pat, name, re.IGNORECASE):
                    return ftype
        return None

    @classmethod
    def detect_system(cls, filename: str) -> str | None:
        name = os.path.basename(filename).upper()
        for system, patterns in cls.SYSTEM_PATTERNS.items():
            for pat in patterns:
                if pat in name:
                    return system
        return "UNKNOWN"

    @classmethod
    def detect_station(cls, filename: str) -> str | None:
        name = os.path.basename(filename).upper()
        match = re.match(r"([A-Z0-9]{4})", name)
        if match:
            return match.group(1)
        return None


class MetricIndicator(QWidget):
    """Metric checkbox with green/red availability indicator."""

    def __init__(self, metric_name: str, description: str, parent=None):
        super().__init__(parent)
        self.metric_name = metric_name
        self._available = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.checkbox = QCheckBox(metric_name)
        self.checkbox.setChecked(True)

        self.desc_label = QLabel(description)
        self.desc_label.setStyleSheet("color: #8b9bb4; font-size: 11px;")

        self.indicator = QLabel("●")
        self.indicator.setStyleSheet("color: #ff1744; font-size: 16px; font-weight: bold;")

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout.addWidget(self.checkbox)
        layout.addWidget(self.desc_label)
        layout.addWidget(spacer)
        layout.addWidget(self.indicator)

    def set_available(self, available: bool, degraded: bool = False) -> None:
        self._available = available
        self.checkbox.setEnabled(available)
        if available and not degraded:
            self.indicator.setStyleSheet("color: #00e676; font-size: 16px; font-weight: bold;")
            self.checkbox.setStyleSheet("")
        elif available and degraded:
            self.indicator.setStyleSheet("color: #ffab00; font-size: 16px; font-weight: bold;")
            self.checkbox.setStyleSheet("")
        else:
            self.indicator.setStyleSheet("color: #ff1744; font-size: 16px; font-weight: bold;")
            self.checkbox.setStyleSheet("color: #5a5a5a;")
            self.checkbox.setChecked(False)

    def isChecked(self) -> bool:
        return self.checkbox.isChecked()

    def setChecked(self, checked: bool) -> None:
        self.checkbox.setChecked(checked)


class DataUploadPage(QWidget):
    def __init__(self, bus: CommandBus) -> None:
        super().__init__()
        self.bus = bus
        self.current_project_id: str | None = None
        self.current_task_id: str | None = None
        self.uploaded_files: list[dict] = []
        self._progress_timer: QTimer | None = None
        self._scan_data: dict | None = None
        self._validated_config: dict | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        title = QLabel("数据上传与处理")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #00e5ff; margin: 10px 0;")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(12)
        content_layout.addWidget(title)
        content_layout.addWidget(self._build_file_section())
        content_layout.addWidget(self._build_metric_section())
        content_layout.addWidget(self._build_status_section())
        content_layout.addWidget(self._build_action_section())
        content_layout.addStretch()

        scroll.setWidget(content)
        layout = QVBoxLayout(self)
        layout.addWidget(scroll)

    def _build_file_section(self) -> QGroupBox:
        box = QGroupBox("文件上传")

        self.obs_files = self._make_file_list()
        self.sp3_files = self._make_file_list()
        self.atx_files = self._make_file_list()
        self.clk_files = self._make_file_list()
        self.nav_files = self._make_file_list()

        grid = QGridLayout()
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)

        grid.addWidget(QLabel("<span style='color:#ff6d00'>*</span> OBS观测数据:"), 0, 0)
        grid.addWidget(self._make_upload_btn("添加", self.obs_files, ["OBS"]), 0, 1)
        grid.addWidget(self.obs_files, 1, 0, 1, 2)

        grid.addWidget(QLabel("SP3星历数据 (σφf需要):"), 2, 0)
        grid.addWidget(self._make_upload_btn("添加", self.sp3_files, ["SP3"]), 2, 1)
        grid.addWidget(self.sp3_files, 3, 0, 1, 2)

        grid.addWidget(QLabel("ATX天线数据 (σφf需要):"), 4, 0)
        grid.addWidget(self._make_upload_btn("添加", self.atx_files, ["ATX"]), 4, 1)
        grid.addWidget(self.atx_files, 5, 0, 1, 2)

        grid.addWidget(QLabel("CLK钟差数据:"), 6, 0)
        grid.addWidget(self._make_upload_btn("添加", self.clk_files, ["CLK"]), 6, 1)
        grid.addWidget(self.clk_files, 7, 0, 1, 2)

        grid.addWidget(QLabel("NAV导航数据:"), 8, 0)
        grid.addWidget(self._make_upload_btn("添加", self.nav_files, ["NAV"]), 8, 1)
        grid.addWidget(self.nav_files, 9, 0, 1, 2)

        v_layout = QVBoxLayout(box)
        v_layout.addLayout(grid)

        for ftype in ["obs", "sp3", "atx", "clk", "nav"]:
            file_list = getattr(self, f"{ftype}_files")
            file_list.itemChanged.connect(self._on_file_list_changed)

        return box

    def _build_metric_section(self) -> QGroupBox:
        box = QGroupBox("闪烁指数计算")

        hint = QLabel("选择要计算的指标 (绿色 = 数据满足计算条件, 红色 = 数据不足)")
        hint.setStyleSheet("color: #8b9bb4; font-size: 12px; margin-bottom: 8px;")

        self.metric_roti = MetricIndicator("ROTI", "TEC变化率指数 (需OBS双频数据)")
        self.metric_aatr = MetricIndicator("AATR", "沿弧TEC变化率 (需OBS双频数据)")
        self.metric_iaatr = MetricIndicator("IAATR", "瞬时AATR (需OBS双频数据)")
        self.metric_dixsg = MetricIndicator("DIXSG", "差分电离层梯度 (需≥2站点)")
        self.metric_sigma = MetricIndicator("σφf", "相位闪烁指数 (需OBS+ATX+SP3)")

        v_layout = QVBoxLayout(box)
        v_layout.addWidget(hint)
        v_layout.addWidget(self.metric_roti)
        v_layout.addWidget(self.metric_aatr)
        v_layout.addWidget(self.metric_iaatr)
        v_layout.addWidget(self.metric_dixsg)
        v_layout.addWidget(self.metric_sigma)

        return box

    def _build_status_section(self) -> QGroupBox:
        box = QGroupBox("状态")

        self.status_label = QLabel("请上传必要的文件")
        self.status_label.setStyleSheet("color: #8b9bb4; font-size: 13px;")

        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #00e676; font-size: 13px;")

        v_layout = QVBoxLayout(box)
        v_layout.addWidget(self.status_label)
        v_layout.addWidget(self.info_label)

        return box

    def _build_action_section(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color: #00e676; font-size: 12px;")

        self.progress = QProgressBar()
        self.progress.setMaximumHeight(8)
        self.progress.setTextVisible(True)
        self.progress.hide()

        btn_layout = QHBoxLayout()

        self.process_btn = QPushButton("上传并开始处理")
        self.process_btn.clicked.connect(self._process)
        self.process_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00e676, stop:1 #00e5ff);
                color: #0a0e17;
                font-weight: bold;
                min-height: 40px;
                font-size: 14px;
            }
        """)
        self.process_btn.setEnabled(False)

        clear_all_btn = QPushButton("清空全部")
        clear_all_btn.setProperty("secondary", "true")
        clear_all_btn.clicked.connect(self._clear_all)

        btn_layout.addWidget(self.process_btn)
        btn_layout.addWidget(clear_all_btn)

        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress)
        layout.addLayout(btn_layout)

        return widget

    def _make_file_list(self) -> QListWidget:
        lst = QListWidget()
        lst.setMaximumHeight(60)
        lst.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        return lst

    def _make_upload_btn(self, text: str, target_list: QListWidget, file_types: list) -> QPushButton:
        btn = QPushButton(text)
        btn.setProperty("secondary", "true")
        btn.setMaximumWidth(80)
        btn.clicked.connect(lambda: self._upload_files(target_list, file_types))
        return btn

    def _upload_files(self, target_list: QListWidget, file_types: list) -> None:
        filters = {
            "OBS": "RINEX OBS Files (*.24o *.25o *.rnx *.obs);;All Files (*)",
            "SP3": "SP3 Files (*.sp3 *.eph);;All Files (*)",
            "CLK": "CLK Files (*.clk);;All Files (*)",
            "ATX": "ATX Files (*.atx);;All Files (*)",
            "NAV": "NAV Files (*.nav);;All Files (*)",
        }

        files, _ = QFileDialog.getOpenFileNames(
            self,
            f"选择{file_types[0]}文件",
            "",
            ";".join(filters.get(ft, "All Files (*)") for ft in file_types)
        )

        if not files:
            return

        target_list.clear()

        for path in files:
            filename = os.path.basename(path)
            ftype = FileTypeDetector.detect_file_type(filename)
            system = FileTypeDetector.detect_system(filename)
            station = FileTypeDetector.detect_station(filename)

            item = QListWidgetItem(filename)
            item.setData(Qt.ItemDataRole.UserRole, {
                "path": path,
                "type": ftype,
                "system": system,
                "station": station,
            })

            if ftype in file_types:
                target_list.addItem(item)

        self._on_file_list_changed()

    def _on_file_list_changed(self) -> None:
        self._scan_data = None
        self._validated_config = None
        all_files = []
        for ftype in ["obs", "sp3", "atx", "clk", "nav"]:
            file_list = getattr(self, f"{ftype}_files")
            for i in range(file_list.count()):
                item = file_list.item(i)
                data = item.data(Qt.ItemDataRole.UserRole)
                if data:
                    all_files.append(data)

        self.uploaded_files = all_files

        stations = set()
        systems = set()
        for f in all_files:
            if f.get("station"):
                stations.add(f["station"])
            if f.get("system") and f.get("system") != "UNKNOWN":
                systems.add(f["system"])

        obs_count = self.obs_files.count()
        sp3_count = self.sp3_files.count()
        atx_count = self.atx_files.count()
        clk_count = self.clk_files.count()
        nav_count = self.nav_files.count()

        self._update_metric_indicators(stations, obs_count, sp3_count, atx_count, clk_count, nav_count)

        if obs_count == 0:
            self.status_label.setText("请上传必要的文件 (至少需要OBS观测数据)")
            self.status_label.setStyleSheet("color: #ff1744; font-size: 13px;")
            self.info_label.setText("")
            self.process_btn.setEnabled(False)
        else:
            info_parts = []
            if stations:
                info_parts.append(f"站点: {', '.join(sorted(stations))}")
            if systems:
                info_parts.append(f"系统: {', '.join(sorted(systems))}")
            files_info = f"{obs_count} OBS"
            if sp3_count > 0:
                files_info += f", {sp3_count} SP3"
            if atx_count > 0:
                files_info += f", {atx_count} ATX"
            if clk_count > 0:
                files_info += f", {clk_count} CLK"
            self.info_label.setText(" | ".join(info_parts))
            self.status_label.setText(f"文件已就绪 ({files_info})")
            self.status_label.setStyleSheet("color: #00e676; font-size: 13px;")
            self.process_btn.setEnabled(True)

    def _update_metric_indicators(self, stations: set, obs_count: int, sp3_count: int,
                                    atx_count: int, clk_count: int, nav_count: int) -> None:
        has_obs = obs_count > 0
        has_sp3 = sp3_count > 0
        has_atx = atx_count > 0
        has_clk = clk_count > 0
        has_nav = nav_count > 0
        has_multiple_stations = len(stations) >= 2

        # Check if OBS files have actual dual-frequency GPS data
        has_dual_freq = False
        if has_obs:
            has_dual_freq = self._check_dual_frequency_support()

        # ROTI: needs OBS with dual-frequency GPS data
        self.metric_roti.set_available(has_obs and has_dual_freq)
        # AATR: needs OBS with dual-frequency GPS data
        self.metric_aatr.set_available(has_obs and has_dual_freq)
        # IAATR: needs OBS with dual-frequency GPS data
        self.metric_iaatr.set_available(has_obs and has_dual_freq)
        # DIXSG: needs OBS + at least 2 stations with dual-frequency data
        self.metric_dixsg.set_available(has_obs and has_multiple_stations and has_dual_freq)

        # SIGMA_PHI_F per M_ISSION paper:
        # Full mode: OBS (dual-freq) + SP3 + CLK + ATX (geodetic detrending with precise products)
        # Simplified mode: OBS (dual-freq) only (skip geodetic detrending, use GF phase directly)
        sigma_full = has_obs and has_dual_freq and has_atx and has_sp3 and (has_clk or has_nav)
        sigma_simplified = has_obs and has_dual_freq and not sigma_full
        if sigma_full:
            self.metric_sigma.set_available(True, degraded=False)
        elif sigma_simplified:
            self.metric_sigma.set_available(True, degraded=True)
        else:
            self.metric_sigma.set_available(False)

        any_metric_available = any(
            indicator._available
            for indicator in [
                self.metric_roti,
                self.metric_aatr,
                self.metric_iaatr,
                self.metric_dixsg,
                self.metric_sigma,
            ]
        )

        if obs_count > 0:
            self.process_btn.setEnabled(any_metric_available)
        else:
            self.process_btn.setEnabled(False)

    def _check_dual_frequency_support(self) -> bool:
        """Check if uploaded OBS files contain dual-frequency GPS phase data (L1+L2)."""
        from isd.infrastructure.filesystem.rinex_parser import RinexParser

        for i in range(self.obs_files.count()):
            item = self.obs_files.item(i)
            data = item.data(Qt.ItemDataRole.UserRole) if item else None
            if not data:
                continue
            path = data.get("path", "")
            try:
                parser = RinexParser()
                header = parser.parse_header(Path(path))
                if header.obs_types and "GPS" in header.obs_types:
                    gps_obs = header.obs_types["GPS"]
                    # Check for L1 and L2 phase observations (L1C, L1W, L2C, L2L, L2W, etc.)
                    has_l1 = any(obs.startswith("L1") for obs in gps_obs)
                    has_l2 = any(obs.startswith("L2") for obs in gps_obs)
                    if has_l1 and has_l2:
                        return True
            except Exception:
                continue
        return False

    def _clear_files(self) -> None:
        self._scan_data = None
        self._validated_config = None
        for ftype in ["obs", "sp3", "atx", "clk", "nav"]:
            getattr(self, f"{ftype}_files").clear()
        self.uploaded_files = []

        self.metric_roti.set_available(False)
        self.metric_aatr.set_available(False)
        self.metric_iaatr.set_available(False)
        self.metric_dixsg.set_available(False)
        self.metric_sigma.set_available(False)

        self.metric_roti.setChecked(True)
        self.metric_aatr.setChecked(True)
        self.metric_iaatr.setChecked(True)
        self.metric_dixsg.setChecked(True)
        self.metric_sigma.setChecked(True)

        self.status_label.setText("请上传必要的文件 (带*号的为必填)")
        self.status_label.setStyleSheet("color: #8b9bb4; font-size: 13px;")
        self.info_label.setText("")
        self.process_btn.setEnabled(False)

    def _clear_all(self) -> None:
        self._stop_all_running_tasks()
        self._stop_progress_timer()
        self._reset_progress()
        self._clear_files()

    def _stop_all_running_tasks(self) -> None:
        rsp = self.bus.dispatch(channels.TASK_LIST, {})
        if not rsp.success:
            return
        stopped = []
        for task in rsp.data or []:
            if task.get("status") == "RUNNING":
                task_id = task.get("id")
                if task_id:
                    self.bus.dispatch(channels.TASK_STOP, {"taskId": task_id})
                    stopped.append(task_id)
        if stopped:
            self.status_label.setText(f"已停止 {len(stopped)} 个运行中的任务")
            self.status_label.setStyleSheet("color: #ff6d00; font-size: 13px;")

    def _reset_progress(self) -> None:
        self.current_task_id = None
        self.progress.hide()
        self.progress.setValue(0)
        self.progress_label.setText("")

    def _process(self) -> None:
        self._stop_all_running_tasks()

        obs_count = self.obs_files.count()
        sp3_count = self.sp3_files.count()
        atx_count = self.atx_files.count()

        if obs_count == 0:
            QMessageBox.warning(self, "警告", "请上传至少OBS观测数据文件")
            return

        selected_metrics = []
        if self.metric_roti.isChecked() and self.metric_roti._available:
            selected_metrics.append("ROTI")
        if self.metric_aatr.isChecked() and self.metric_aatr._available:
            selected_metrics.append("AATR")
        if self.metric_iaatr.isChecked() and self.metric_iaatr._available:
            selected_metrics.append("IAATR")
        if self.metric_dixsg.isChecked() and self.metric_dixsg._available:
            selected_metrics.append("DIXSG")
        if self.metric_sigma.isChecked() and self.metric_sigma._available:
            selected_metrics.append("SIGMA_PHI_F")

        if not selected_metrics:
            QMessageBox.warning(self, "警告", "请至少选择一个可用的闪烁指标")
            return

        if not self.uploaded_files:
            QMessageBox.warning(self, "警告", "请先选择输入文件")
            return

        root_candidates = [Path(str(item.get("path", ""))).resolve().parent for item in self.uploaded_files if item.get("path")]
        project_root = str(root_candidates[0]) if root_candidates else str(Path.cwd())

        self.progress.show()
        self.progress.setValue(0)
        self.progress_label.setText("正在创建项目...")

        rsp = self.bus.dispatch(
            channels.PROJECT_CREATE,
            {
                "name": f"auto_project_{len(self.uploaded_files)}",
                "description": "Auto-created project from upload page",
                "rootPath": project_root,
            },
        )
        if not rsp.success:
            self.progress.hide()
            self.progress_label.setText("")
            QMessageBox.critical(self, "错误", rsp.error.message if rsp.error else "创建项目失败")
            return

        self.current_project_id = rsp.data["id"]
        self.progress.setValue(10)
        self.progress_label.setText("正在扫描文件...")

        scan_rsp = self.bus.dispatch(
            channels.PROJECT_SCAN_FILES,
            {
                "projectId": self.current_project_id,
                "paths": [str(f.get("path", "")) for f in self.uploaded_files if f.get("path")],
                "metrics": selected_metrics,
            },
        )
        if not scan_rsp.success:
            self.progress.hide()
            self.progress_label.setText("")
            QMessageBox.critical(self, "错误", scan_rsp.error.message if scan_rsp.error else "文件扫描失败")
            return

        self._scan_data = scan_rsp.data or {}
        files = self._scan_data.get("files") or []
        stations = self._scan_data.get("stations") or []
        dependency_summary = self._scan_data.get("dependencySummary") or {}

        station_ids = sorted({str(row.get("station_code") or "").upper() for row in stations if row.get("station_code")})
        if not station_ids:
            station_ids = sorted({str(row.get("station_id") or "").upper() for row in files if row.get("station_id")})
        if not station_ids:
            self.progress.hide()
            self.progress_label.setText("")
            QMessageBox.critical(self, "错误", "扫描完成但未识别到有效站点")
            return

        system_list = sorted({sys for row in files for sys in (row.get("systems") or []) if sys})
        if not system_list:
            system_list = ["GPS"]

        # Date range should be based on OBS files only (not SP3/CLK which may span more days)
        obs_dates = sorted({
            str(row.get("file_date") or "")
            for row in files
            if row.get("kind") == "OBS" and row.get("file_date")
        })
        if obs_dates:
            date_range = {"start": obs_dates[0], "end": obs_dates[-1]}
        else:
            # Fallback: use all file dates if no OBS dates found
            file_dates = sorted({str(row.get("file_date") or "") for row in files if row.get("file_date")})
            if file_dates:
                date_range = {"start": file_dates[0], "end": file_dates[-1]}
            else:
                date_range = self._detect_date_range()

        chain_level = "FORMAL"
        if selected_metrics and dependency_summary:
            levels = {str(row.get("chainLevel") or "FORMAL") for row in dependency_summary.values()}
            if "DEGRADED" in levels:
                chain_level = "DEGRADED"
            elif "EXPERIMENTAL" in levels:
                chain_level = "EXPERIMENTAL"

        # Build station-to-OBS-file mapping for RINEX data access
        station_obs_map = {}
        for row in files:
            if row.get("kind") == "OBS" and row.get("station_id"):
                station_obs_map[row["station_id"].upper()] = row.get("file_path", "")

        config = {
            "project_id": self.current_project_id,
            "station_ids": station_ids,
            "date_range": date_range,
            "systems": system_list,
            "metrics": selected_metrics,
            "chain_level": chain_level,
            "sampling_mode": "STANDARD_30S",
            "output_path": f"workspace/outputs/{self.current_project_id}",
            "parallelism": 2,
            "enable_intermediate_save": True,
            "enable_intermediate_preview": True,
            "enable_nav_fallback": any((row.get("kind") == "NAV") for row in files),
            "enable_experimental_sigma_phi_f": False,
            "enable_1s_resample": False,
            "parameter_source": "auto",
            "threshold_source": "auto",
            "receiver_threshold_preset": None,
            "threshold_config": [],
            "algorithm_config": {},
            "provider_metadata": {
                "filePaths": [f.get("path", "") for f in self.uploaded_files if f.get("path")],
                "stationProviders": {
                    sid: {"obsPath": path, "coordinateSource": "RINEX_APPROX"}
                    for sid, path in station_obs_map.items()
                },
            },
        }

        validate_rsp = self.bus.dispatch(channels.TASK_VALIDATE, {"config": config})
        if not validate_rsp.success:
            self.progress.hide()
            self.progress_label.setText("")
            QMessageBox.critical(self, "错误", validate_rsp.error.message if validate_rsp.error else "任务校验失败")
            return

        validation = validate_rsp.data or {}
        issues = validation.get("issues") or []
        blocking_issues = [issue for issue in issues if issue.get("blocking")]
        warning_issues = [issue for issue in issues if not issue.get("blocking")]
        if blocking_issues:
            self.progress.hide()
            self.progress_label.setText("")
            message = "\n".join(f"- {issue.get('message', '未知阻断')}" for issue in blocking_issues[:8])
            self.status_label.setText("任务校验未通过")
            self.status_label.setStyleSheet("color: #ff1744; font-size: 13px;")
            self.info_label.setText(message)
            QMessageBox.critical(self, "错误", f"任务校验未通过:\n{message}")
            return

        if validation.get("derivedChainLevel"):
            config["chain_level"] = validation.get("derivedChainLevel")
        if validation.get("derivedSamplingMode"):
            config["sampling_mode"] = validation.get("derivedSamplingMode")
        self._validated_config = config

        self.progress.setValue(35)
        self.progress_label.setText("正在创建任务...")

        create_rsp = self.bus.dispatch(
            channels.TASK_CREATE,
            {
                "name": f"task_{len(self.uploaded_files)}",
                "taskType": "SINGLE",
                "config": config,
            },
        )

        if not create_rsp.success:
            self.progress.hide()
            self.progress_label.setText("")
            QMessageBox.critical(self, "错误", create_rsp.error.message if create_rsp.error else "创建任务失败")
            return

        task_id = create_rsp.data.get("task", {}).get("id")
        start_rsp = self.bus.dispatch(channels.TASK_START, {"taskId": task_id})

        if start_rsp.success:
            self.current_task_id = task_id
            warning_text = ""
            if warning_issues:
                warning_text = " | 警告: " + "; ".join(str(issue.get("message")) for issue in warning_issues[:3])
            self.progress_label.setText(f"任务已启动: {task_id}")
            self.status_label.setText(f"处理中... 任务ID: {task_id}")
            self.status_label.setStyleSheet("color: #00e5ff; font-size: 13px;")
            self.info_label.setText(
                f"站点: {', '.join(station_ids)} | 系统: {', '.join(system_list)} | 日期: {date_range['start']} 至 {date_range['end']}{warning_text}"
            )
            self.progress.setValue(40)
            self._start_progress_timer()
        else:
            self.progress.hide()
            self.progress_label.setText("")
            QMessageBox.warning(self, "警告", "任务创建成功但启动失败，请手动开始")

    def _start_progress_timer(self) -> None:
        if self._progress_timer is not None:
            self._progress_timer.stop()
        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._update_task_progress)
        self._progress_timer.start(2000)

    def _stop_progress_timer(self) -> None:
        if self._progress_timer is not None:
            self._progress_timer.stop()
            self._progress_timer = None

    def _update_task_progress(self) -> None:
        if not self.current_task_id:
            self._stop_progress_timer()
            return

        rsp = self.bus.dispatch(channels.TASK_GET, {"taskId": self.current_task_id})
        if not rsp.success:
            return

        data = rsp.data or {}
        task_inner = data.get("task", {})
        subtasks = data.get("subTasks", [])
        status = task_inner.get("status", "")

        if status == "COMPLETED":
            self.progress.setValue(100)
            self.progress_label.setText("任务已完成!")
            self.status_label.setText("任务已完成")
            self.status_label.setStyleSheet("color: #00e676; font-size: 13px;")
            self._stop_progress_timer()
            return
        elif status == "FAILED":
            self.progress_label.setText("任务失败")
            self.status_label.setText(f"任务失败: {task_inner.get('latest_error', '未知错误')}")
            self.status_label.setStyleSheet("color: #ff1744; font-size: 13px;")
            self._stop_progress_timer()
            return
        elif status == "RUNNING":
            total = len(subtasks)
            if total == 0:
                self.progress_label.setText("正在初始化任务...")
                return
            done = sum(1 for s in subtasks if s.get("status") in ("COMPLETED", "FAILED"))
            pct = int(done / total * 100) if total > 0 else 0
            self.progress.setValue(pct)
            self.progress_label.setText(f"处理中... {done}/{total} ({pct}%)")
        else:
            self.progress_label.setText(f"状态: {status}")

    def _detect_date_range(self) -> dict:
        dates = set()
        for f in self.uploaded_files:
            fname = os.path.basename(f.get("path", ""))
            match = re.search(r"\.(\d{2})[\d.]*\.", fname)
            if match:
                year_2digit = int(match.group(1))
                year = 2000 + year_2digit if year_2digit < 90 else 1900 + year_2digit
                dates.add(year)

        if dates:
            return {
                "start": f"{min(dates)}-01-01",
                "end": f"{max(dates)}-12-31",
            }
        return {"start": "2024-01-01", "end": "2024-12-31"}
