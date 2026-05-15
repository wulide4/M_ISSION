from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from isd.application import channels
from isd.application.command_bus import CommandBus
from isd.application.risk_flags import derive_task_risk_flags, risk_flags_to_text
from isd.domain.enums import ChainLevel, GnssSystem, MetricKey, SamplingMode


class TaskSignals(QObject):
    progress = Signal(dict)
    log = Signal(dict)


class DataCalculationPage(QWidget):
    def __init__(self, bus: CommandBus, task_service) -> None:
        super().__init__()
        self.bus = bus
        self.task_service = task_service
        self.current_task_id: str | None = None
        self.last_risk_flags: list[str] = []

        self.parameter_source: str = "auto"
        self.threshold_source: str = "auto"
        self.source_template_id: str | None = None
        self._updating_form: bool = False
        self.default_algorithm_config: dict = {}
        self.threshold_presets: dict = {}

        self.project_id_edit = QLineEdit()
        self.station_ids_edit = QLineEdit()
        self.date_start_edit = QLineEdit("2024-03-24")
        self.date_end_edit = QLineEdit("2024-03-24")
        self.output_edit = QLineEdit("workspace/outputs")
        self.station_picker = QListWidget()
        self.station_picker.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.station_picker.itemSelectionChanged.connect(self._sync_station_ids_from_picker)
        self.station_ids_edit.editingFinished.connect(self._sync_picker_from_station_ids)

        self.metric_roti = QCheckBox("ROTI")
        self.metric_aatr = QCheckBox("AATR")
        self.metric_iaatr = QCheckBox("IAATR")
        self.metric_dixsg = QCheckBox("DIXSG")
        self.metric_sigma = QCheckBox("SIGMA_PHI_F")
        self.metric_roti.setChecked(True)

        self.system_gps = QCheckBox("GPS")
        self.system_glo = QCheckBox("GLO")
        self.system_gal = QCheckBox("GAL")
        self.system_bds = QCheckBox("BDS")
        self.system_gps.setChecked(True)

        self.chain_combo = QComboBox()
        self.chain_combo.addItems([x.value for x in ChainLevel])
        self.sampling_combo = QComboBox()
        self.sampling_combo.addItems([x.value for x in SamplingMode])

        self.exp_sigma = QCheckBox("启用非GPS SIGMA实验")
        self.exp_1s = QCheckBox("启用1s重采样")
        self.enable_nav = QCheckBox("启用NAV降级")

        load_stations_btn = QPushButton("加载项目站点")
        load_stations_btn.clicked.connect(self._load_project_stations)
        auto_detect_btn = QPushButton("自动识别站点")
        auto_detect_btn.clicked.connect(self._auto_detect_stations)

        validate_btn = QPushButton("校验")
        validate_btn.clicked.connect(self._validate)
        create_btn = QPushButton("创建任务")
        create_btn.clicked.connect(self._create)
        start_btn = QPushButton("开始")
        start_btn.clicked.connect(self._start)
        pause_btn = QPushButton("暂停")
        pause_btn.clicked.connect(self._pause)
        resume_btn = QPushButton("继续")
        resume_btn.clicked.connect(self._resume)
        stop_btn = QPushButton("停止")
        stop_btn.clicked.connect(self._stop)

        self.progress = QProgressBar()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.risk_hint = QLabel("风险标识: FORMAL_PIPELINE")
        self.source_hint = QLabel("参数来源: 自动 | 阈值来源: 自动")

        for w in [
            self.project_id_edit,
            self.station_ids_edit,
            self.date_start_edit,
            self.date_end_edit,
            self.output_edit,
            self.chain_combo,
            self.sampling_combo,
        ]:
            w.setMinimumHeight(28)
        self.station_picker.setMinimumHeight(96)
        self.progress.setMinimumHeight(22)
        self.log_text.setMinimumHeight(180)

        form = QFormLayout()
        form.setVerticalSpacing(8)
        form.setHorizontalSpacing(12)
        form.addRow("projectId", self.project_id_edit)
        form.addRow("stationIds(逗号分隔)", self.station_ids_edit)
        form.addRow("start", self.date_start_edit)
        form.addRow("end", self.date_end_edit)
        form.addRow("output", self.output_edit)
        form.addRow("chain", self.chain_combo)
        form.addRow("sampling", self.sampling_combo)

        metric_row = QHBoxLayout()
        for w in [self.metric_roti, self.metric_aatr, self.metric_iaatr, self.metric_dixsg, self.metric_sigma]:
            metric_row.addWidget(w)

        sys_row = QHBoxLayout()
        for w in [self.system_gps, self.system_glo, self.system_gal, self.system_bds]:
            sys_row.addWidget(w)

        station_btn_row = QHBoxLayout()
        station_btn_row.addWidget(load_stations_btn)
        station_btn_row.addWidget(auto_detect_btn)
        station_btn_row.addStretch(1)

        station_box = QGroupBox("站点选择（可鼠标多选）")
        station_layout = QVBoxLayout(station_box)
        station_layout.addWidget(self.station_picker)

        btn_row = QHBoxLayout()
        for w in [validate_btn, create_btn, start_btn, pause_btn, resume_btn, stop_btn]:
            btn_row.addWidget(w)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.addWidget(QLabel("<h2>数据计算</h2>"))
        box = QGroupBox("任务参数")
        box_layout = QVBoxLayout(box)
        box_layout.addLayout(form)
        box_layout.addWidget(station_box)
        box_layout.addLayout(metric_row)
        box_layout.addLayout(sys_row)
        box_layout.addWidget(self.exp_sigma)
        box_layout.addWidget(self.exp_1s)
        box_layout.addWidget(self.enable_nav)
        box_layout.addLayout(station_btn_row)
        box_layout.addWidget(self.source_hint)
        box_layout.addWidget(self.risk_hint)
        box_layout.addLayout(btn_row)
        content_layout.addWidget(box)
        content_layout.addWidget(QLabel("进度"))
        content_layout.addWidget(self.progress)
        content_layout.addWidget(QLabel("日志"))
        content_layout.addWidget(self.log_text)
        content_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll)

        self.signals = TaskSignals()
        self.signals.progress.connect(self._on_progress)
        self.signals.log.connect(self._on_log)

        self.task_service.add_progress_listener(lambda evt: self.signals.progress.emit(evt.model_dump(mode="json")))
        self.task_service.add_log_listener(lambda evt: self.signals.log.emit(evt.model_dump(mode="json")))

        self._bind_risk_inputs()
        self._bind_source_inputs()
        self._refresh_risk_hint()

    def set_project(self, project_id: str) -> None:
        self._updating_form = True
        try:
            self.project_id_edit.setText(project_id)
        finally:
            self._updating_form = False
        self._load_project_stations()

    def _load_project_stations(self) -> None:
        project_id = self.project_id_edit.text().strip()
        self.station_picker.clear()
        if not project_id:
            return
        rsp = self.bus.dispatch(channels.PROJECT_GET_STATIONS, {"projectId": project_id})
        if not rsp.success:
            return
        rows = sorted(rsp.data or [], key=lambda x: str(x.get("station_code", "")))
        for row in rows:
            code = str(row.get("station_code") or "").strip()
            if not code:
                continue
            systems = row.get("systems") or []
            label = f"{code} ({','.join(systems)})" if systems else code
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, code)
            self.station_picker.addItem(item)
        self._sync_picker_from_station_ids()

    def _auto_detect_stations(self) -> None:
        project_id = self.project_id_edit.text().strip()
        if not project_id:
            QMessageBox.warning(self, "警告", "请先输入项目ID")
            return
        rsp = self.bus.dispatch(channels.PROJECT_SCAN_FILES, {"projectId": project_id})
        if not rsp.success:
            QMessageBox.warning(self, "警告", "扫描项目文件失败")
            return
        self._load_project_stations()
        QMessageBox.information(self, "成功", "站点已自动识别")

    def _sync_station_ids_from_picker(self) -> None:
        if self._updating_form:
            return
        selected_codes = sorted(
            {
                str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
                for item in self.station_picker.selectedItems()
            }
        )
        selected_codes = [x for x in selected_codes if x]
        self._updating_form = True
        try:
            self.station_ids_edit.setText(",".join(selected_codes))
        finally:
            self._updating_form = False
        self._set_sources("auto", "auto", None)

    def _sync_picker_from_station_ids(self) -> None:
        if self.station_picker.count() == 0:
            return
        station_ids = {
            x.strip().upper()
            for x in self.station_ids_edit.text().split(",")
            if x.strip()
        }
        self._updating_form = True
        try:
            for i in range(self.station_picker.count()):
                item = self.station_picker.item(i)
                code = str(item.data(Qt.ItemDataRole.UserRole) or "").strip().upper()
                item.setSelected(code in station_ids)
        finally:
            self._updating_form = False

    def _bind_risk_inputs(self) -> None:
        watches = [
            self.metric_roti,
            self.metric_aatr,
            self.metric_iaatr,
            self.metric_dixsg,
            self.metric_sigma,
            self.system_gps,
            self.system_glo,
            self.system_gal,
            self.system_bds,
            self.exp_sigma,
            self.exp_1s,
            self.enable_nav,
        ]
        for widget in watches:
            widget.toggled.connect(self._refresh_risk_hint)
        self.chain_combo.currentTextChanged.connect(self._refresh_risk_hint)
        self.sampling_combo.currentTextChanged.connect(self._refresh_risk_hint)

    def _bind_source_inputs(self) -> None:
        edits = [
            self.project_id_edit,
            self.station_ids_edit,
            self.date_start_edit,
            self.date_end_edit,
            self.output_edit,
        ]
        for edit in edits:
            edit.textChanged.connect(self._mark_sources_auto)

        checks = [
            self.metric_roti,
            self.metric_aatr,
            self.metric_iaatr,
            self.metric_dixsg,
            self.metric_sigma,
            self.system_gps,
            self.system_glo,
            self.system_gal,
            self.system_bds,
            self.exp_sigma,
            self.exp_1s,
            self.enable_nav,
        ]
        for c in checks:
            c.toggled.connect(self._mark_sources_auto)

        self.chain_combo.currentTextChanged.connect(self._mark_sources_auto)
        self.sampling_combo.currentTextChanged.connect(self._mark_sources_auto)

    def _set_sources(self, parameter_source: str, threshold_source: str, template_id: str | None = None) -> None:
        self.parameter_source = parameter_source
        self.threshold_source = threshold_source
        self.source_template_id = template_id
        self.source_hint.setText(f"参数来源: {parameter_source} | 阈值来源: {threshold_source}")

    def _mark_sources_auto(self) -> None:
        if self._updating_form:
            return
        self._set_sources("auto", "auto", None)

    def _metrics(self) -> list[str]:
        mapping = [
            (self.metric_roti, MetricKey.ROTI.value),
            (self.metric_aatr, MetricKey.AATR.value),
            (self.metric_iaatr, MetricKey.IAATR.value),
            (self.metric_dixsg, MetricKey.DIXSG.value),
            (self.metric_sigma, MetricKey.SIGMA_PHI_F.value),
        ]
        return [name for checkbox, name in mapping if checkbox.isChecked()]

    def _systems(self) -> list[str]:
        mapping = [
            (self.system_gps, GnssSystem.GPS.value),
            (self.system_glo, GnssSystem.GLO.value),
            (self.system_gal, GnssSystem.GAL.value),
            (self.system_bds, GnssSystem.BDS.value),
        ]
        return [name for checkbox, name in mapping if checkbox.isChecked()]

    def _build_threshold_config(self) -> list[dict]:
        out: list[dict] = []
        metric_keys = self._metrics()
        for metric in metric_keys:
            preset = self.threshold_presets.get(metric)
            if not isinstance(preset, dict):
                continue
            out.append(
                {
                    "metric": metric,
                    "value": float(preset.get("value", 0.0)),
                    "unit": str(preset.get("unit", "")),
                    "source": str(preset.get("source", "LITERATURE_REFERENCE")),
                }
            )
        return out

    def _build_config(self) -> dict:
        # Load user settings from settings service, fall back to stored defaults
        user_algo = self._load_user_algorithm_config()
        algorithm = dict(self.default_algorithm_config or {})
        if user_algo:
            self._deep_update(algorithm, user_algo)
        return {
            "project_id": self.project_id_edit.text().strip(),
            "station_ids": [x.strip() for x in self.station_ids_edit.text().split(",") if x.strip()],
            "date_range": {
                "start": self.date_start_edit.text().strip(),
                "end": self.date_end_edit.text().strip(),
            },
            "systems": self._systems(),
            "metrics": self._metrics(),
            "chain_level": self.chain_combo.currentText(),
            "sampling_mode": self.sampling_combo.currentText(),
            "output_path": self.output_edit.text().strip(),
            "parallelism": 2,
            "enable_intermediate_save": True,
            "enable_intermediate_preview": True,
            "enable_nav_fallback": self.enable_nav.isChecked(),
            "enable_experimental_sigma_phi_f": self.exp_sigma.isChecked(),
            "enable_1s_resample": self.exp_1s.isChecked(),
            "parameter_source": self.parameter_source,
            "threshold_source": self.threshold_source,
            "source_template_id": self.source_template_id,
            "receiver_threshold_preset": None,
            "threshold_config": self._build_threshold_config(),
            "algorithm_config": algorithm,
        }

    def _load_user_algorithm_config(self) -> dict:
        """Load algorithm config from user settings, mapping UI keys to TaskConfig keys."""
        rsp = self.bus.dispatch(channels.SETTINGS_GET, {})
        if not rsp.success:
            return {}
        cfg = rsp.data or {}
        algo = cfg.get("defaultAlgorithmConfig") or {}
        result = {}
        for src_key, dst_key in [
            ("cutoffElevationDeg", "cutoff_elevation_deg"),
            ("minArcEpochs", "min_arc_epochs"),
            ("rotiWindowMin", "roti_window_min"),
            ("sigmaPhiFWindowMin", "sigma_phi_f_window_min"),
            ("butterworthOrder", "butterworth_order"),
            ("butterworthLowHz", "butterworth_low_hz"),
            ("butterworthHighHz", "butterworth_high_hz"),
        ]:
            if src_key in algo:
                result[dst_key] = algo[src_key]

        # DIXSG config
        dixsg = algo.get("dixsgConfig") or {}
        dixsg_mapped = {}
        for src_key, dst_key in [
            ("sensitivityLevels", "sensitivity_levels"),
            ("sensitivityFirst", "sensitivity_first"),
            ("sensitivityStep", "sensitivity_step"),
            ("maxDistanceKm", "max_distance_km"),
            ("gridSizeDeg", "grid_size_deg"),
        ]:
            if src_key in dixsg:
                dixsg_mapped[dst_key] = dixsg[src_key]
        # Also check flat keys (algorithm.defaults.json format)
        for src_key, dst_key in [
            ("dixsgSensitivityLevels", "sensitivity_levels"),
            ("dixsgSensitivityFirst", "sensitivity_first"),
            ("dixsgSensitivityStep", "sensitivity_step"),
            ("dixsgMaxDistanceKm", "max_distance_km"),
            ("dixsgGridSizeDeg", "grid_size_deg"),
        ]:
            if src_key in algo and dst_key not in dixsg_mapped:
                dixsg_mapped[dst_key] = algo[src_key]
        if "latRange" in dixsg:
            dixsg_mapped["lat_range"] = tuple(dixsg["latRange"])
        if "lonRange" in dixsg:
            dixsg_mapped["lon_range"] = tuple(dixsg["lonRange"])
        if dixsg_mapped:
            result["dixsg"] = dixsg_mapped

        # Cycle slip config
        cs = algo.get("cycleSlipConfig") or {}
        cs_mapped = {}
        for src_key, dst_key in [
            ("windowSize", "window_size"),
            ("gfThresholdFactor", "gf_threshold_factor"),
            ("hmwThresholdFactor", "hmw_threshold_factor"),
            ("minObsForStats", "min_obs_for_stats"),
        ]:
            if src_key in cs:
                cs_mapped[dst_key] = cs[src_key]
        if cs_mapped:
            result["cycle_slip"] = cs_mapped

        return result

    @staticmethod
    def _deep_update(base: dict, patch: dict) -> None:
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                DataCalculationPage._deep_update(base[key], value)
            else:
                base[key] = value

    def _validate(self) -> None:
        rsp = self.bus.dispatch(channels.TASK_VALIDATE, {"config": self._build_config()})
        if not rsp.success:
            QMessageBox.critical(self, "Error", rsp.error.message if rsp.error else "validate failed")
            return
        can_run = rsp.data.get("canRun")
        issues = rsp.data.get("issues")
        derived_chain = rsp.data.get("derivedChainLevel")
        derived_sampling = rsp.data.get("derivedSamplingMode")
        risk_flags = rsp.data.get("riskFlags", []) or []
        provider_summary = rsp.data.get("providerSummary") or {}
        self.last_risk_flags = list(risk_flags)
        self.risk_hint.setText(f"风险标识: {risk_flags_to_text(self.last_risk_flags)}")
        lines = [
            f"canRun={can_run}",
            f"derivedChainLevel={derived_chain}",
            f"derivedSamplingMode={derived_sampling}",
            f"providerChainHint={provider_summary.get('providerChainHint')}",
            f"issues={len(issues)}",
        ]
        for issue in issues[:12]:
            level = issue.get("level", "")
            code = issue.get("code", "")
            message = issue.get("message", "")
            lines.append(f"- [{level}] {code}: {message}")
        QMessageBox.information(self, "Validate", "\n".join(lines))

    def _create(self) -> None:
        rsp = self.bus.dispatch(
            channels.TASK_CREATE,
            {
                "name": "single_task",
                "taskType": "SINGLE",
                "config": self._build_config(),
            },
        )
        if not rsp.success:
            QMessageBox.critical(self, "Error", rsp.error.message if rsp.error else "create failed")
            return
        self.current_task_id = rsp.data["task"]["id"]
        QMessageBox.information(self, "Task", f"Created {self.current_task_id}")

    def _start(self) -> None:
        if not self.current_task_id:
            QMessageBox.warning(self, "Warn", "No task created")
            return
        rsp = self.bus.dispatch(channels.TASK_START, {"taskId": self.current_task_id})
        if not rsp.success:
            QMessageBox.critical(self, "Error", rsp.error.message if rsp.error else "start failed")

    def _pause(self) -> None:
        if self.current_task_id:
            self.bus.dispatch(channels.TASK_PAUSE, {"taskId": self.current_task_id})

    def _resume(self) -> None:
        if self.current_task_id:
            self.bus.dispatch(channels.TASK_RESUME, {"taskId": self.current_task_id})

    def _stop(self) -> None:
        if self.current_task_id:
            self.bus.dispatch(channels.TASK_STOP, {"taskId": self.current_task_id})

    def _on_progress(self, event: dict) -> None:
        if self.current_task_id and event.get("task_id") != self.current_task_id:
            return
        p = float(event.get("progress", 0.0))
        self.progress.setValue(int(p * 100))

    def _on_log(self, event: dict) -> None:
        if self.current_task_id and event.get("task_id") != self.current_task_id:
            return
        self.log_text.append(f"[{event.get('timestamp')}] {event.get('level')} {event.get('message')}")

    def _refresh_risk_hint(self) -> None:
        cfg = self._build_config()
        risk_flags = derive_task_risk_flags(
            derived_chain_level=cfg.get("chain_level"),
            derived_sampling_mode=cfg.get("sampling_mode"),
            metrics=cfg.get("metrics", []),
            systems=cfg.get("systems", []),
            nav_fallback_enabled=bool(cfg.get("enable_nav_fallback")),
        )
        self.risk_hint.setText(f"风险标识: {risk_flags_to_text(risk_flags)}")
