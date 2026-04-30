from __future__ import annotations

import json

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from isd.application import channels
from isd.application.command_bus import CommandBus
from isd.application.risk_flags import derive_task_risk_flags, risk_flags_to_text
from isd.domain.enums import ChainLevel, GnssSystem, MetricKey, SamplingMode, ThresholdSource


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

        self.parameter_source: str = "default"
        self.threshold_source: str = "default"
        self.source_template_id: str | None = None
        self._updating_form: bool = False
        self.default_algorithm_config: dict = {}
        self.threshold_presets: dict = {}

        self.project_id_edit = QLineEdit()
        self.station_ids_edit = QLineEdit()
        self.date_start_edit = QLineEdit("2024-03-24")
        self.date_end_edit = QLineEdit("2024-03-24")
        self.output_edit = QLineEdit("workspace/outputs")

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

        self.template_combo = QComboBox()
        self.template_name_edit = QLineEdit("task_template")
        self.overwrite_combo = QComboBox()
        self.overwrite_combo.addItems(["OVERWRITE", "CREATE_NEW", "REJECT"])

        load_defaults_btn = QPushButton("加载系统默认")
        load_defaults_btn.clicked.connect(self._load_defaults_from_settings)
        refresh_tpl_btn = QPushButton("刷新模板")
        refresh_tpl_btn.clicked.connect(self._refresh_templates)
        load_tpl_btn = QPushButton("应用模板")
        load_tpl_btn.clicked.connect(self._apply_selected_template)
        save_tpl_btn = QPushButton("保存为模板")
        save_tpl_btn.clicked.connect(self._save_as_template)

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
        self.source_hint = QLabel("参数来源: default | 阈值来源: default")

        form = QFormLayout()
        form.addRow("projectId", self.project_id_edit)
        form.addRow("stationIds(comma)", self.station_ids_edit)
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

        tpl_form = QFormLayout()
        tpl_form.addRow("模板", self.template_combo)
        tpl_form.addRow("模板名", self.template_name_edit)
        tpl_form.addRow("覆盖策略", self.overwrite_combo)

        tpl_btn_row = QHBoxLayout()
        tpl_btn_row.addWidget(load_defaults_btn)
        tpl_btn_row.addWidget(refresh_tpl_btn)
        tpl_btn_row.addWidget(load_tpl_btn)
        tpl_btn_row.addWidget(save_tpl_btn)

        btn_row = QHBoxLayout()
        for w in [validate_btn, create_btn, start_btn, pause_btn, resume_btn, stop_btn]:
            btn_row.addWidget(w)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>数据计算</h2>"))
        box = QGroupBox("任务参数")
        box_layout = QVBoxLayout(box)
        box_layout.addLayout(form)
        box_layout.addLayout(metric_row)
        box_layout.addLayout(sys_row)
        box_layout.addWidget(self.exp_sigma)
        box_layout.addWidget(self.exp_1s)
        box_layout.addWidget(self.enable_nav)
        box_layout.addLayout(tpl_form)
        box_layout.addLayout(tpl_btn_row)
        box_layout.addWidget(self.source_hint)
        box_layout.addWidget(self.risk_hint)
        box_layout.addLayout(btn_row)
        layout.addWidget(box)
        layout.addWidget(QLabel("进度"))
        layout.addWidget(self.progress)
        layout.addWidget(QLabel("日志"))
        layout.addWidget(self.log_text)

        self.signals = TaskSignals()
        self.signals.progress.connect(self._on_progress)
        self.signals.log.connect(self._on_log)

        self.task_service.add_progress_listener(lambda evt: self.signals.progress.emit(evt.model_dump(mode="json")))
        self.task_service.add_log_listener(lambda evt: self.signals.log.emit(evt.model_dump(mode="json")))

        self._bind_risk_inputs()
        self._bind_source_inputs()
        self._load_defaults_from_settings()
        self._refresh_templates()
        self._refresh_risk_hint()

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
            edit.textChanged.connect(self._mark_sources_manual)

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
            c.toggled.connect(self._mark_sources_manual)

        self.chain_combo.currentTextChanged.connect(self._mark_sources_manual)
        self.sampling_combo.currentTextChanged.connect(self._mark_sources_manual)

    def _set_sources(self, parameter_source: str, threshold_source: str, template_id: str | None = None) -> None:
        self.parameter_source = parameter_source
        self.threshold_source = threshold_source
        self.source_template_id = template_id
        extra = f" | 模板={template_id}" if template_id else ""
        self.source_hint.setText(f"参数来源: {parameter_source} | 阈值来源: {threshold_source}{extra}")

    def _mark_sources_manual(self) -> None:
        if self._updating_form:
            return
        self._set_sources("manual", "manual", None)

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
            source = str(preset.get("source") or ThresholdSource.LITERATURE_REFERENCE.value)
            out.append(
                {
                    "metric": metric,
                    "value": float(preset.get("value", 0.0)),
                    "unit": str(preset.get("unit", "")),
                    "source": source,
                }
            )
        return out

    def _build_config(self) -> dict:
        algorithm = dict(self.default_algorithm_config or {})
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

    def _refresh_templates(self) -> None:
        current_id = self.template_combo.currentData()
        rsp = self.bus.dispatch(channels.TEMPLATE_LIST, {"scope": "TASK"})
        if not rsp.success:
            return
        rows = rsp.data or []
        self.template_combo.clear()
        for row in rows:
            label = f"{row.get('name', '-') } ({row.get('id', '-')})"
            self.template_combo.addItem(label, row.get("id"))
        if current_id:
            idx = self.template_combo.findData(current_id)
            if idx >= 0:
                self.template_combo.setCurrentIndex(idx)

    def _load_defaults_from_settings(self) -> None:
        rsp = self.bus.dispatch(channels.SETTINGS_GET, {})
        if not rsp.success:
            return
        cfg = rsp.data or {}

        self.default_algorithm_config = dict(cfg.get("defaultAlgorithmConfig") or {})
        self.threshold_presets = dict(cfg.get("thresholdPresets") or {})
        default_output = str(cfg.get("defaultOutputPath") or "workspace/outputs")

        self._updating_form = True
        try:
            self.output_edit.setText(default_output)
            self.exp_sigma.setChecked(False)
            self.exp_1s.setChecked(False)
            self.enable_nav.setChecked(False)
        finally:
            self._updating_form = False

        self._set_sources("default", "default", None)

    def _apply_config_to_form(self, config: dict, *, template_id: str | None = None) -> None:
        self._updating_form = True
        try:
            self.project_id_edit.setText(str(config.get("project_id") or ""))
            self.station_ids_edit.setText(",".join(config.get("station_ids") or []))

            date_range = config.get("date_range") or {}
            self.date_start_edit.setText(str(date_range.get("start") or self.date_start_edit.text()))
            self.date_end_edit.setText(str(date_range.get("end") or self.date_end_edit.text()))
            self.output_edit.setText(str(config.get("output_path") or self.output_edit.text()))

            chain = str(config.get("chain_level") or self.chain_combo.currentText())
            idx_chain = self.chain_combo.findText(chain)
            if idx_chain >= 0:
                self.chain_combo.setCurrentIndex(idx_chain)

            sampling = str(config.get("sampling_mode") or self.sampling_combo.currentText())
            idx_sampling = self.sampling_combo.findText(sampling)
            if idx_sampling >= 0:
                self.sampling_combo.setCurrentIndex(idx_sampling)

            metric_set = set(config.get("metrics") or [])
            self.metric_roti.setChecked(MetricKey.ROTI.value in metric_set)
            self.metric_aatr.setChecked(MetricKey.AATR.value in metric_set)
            self.metric_iaatr.setChecked(MetricKey.IAATR.value in metric_set)
            self.metric_dixsg.setChecked(MetricKey.DIXSG.value in metric_set)
            self.metric_sigma.setChecked(MetricKey.SIGMA_PHI_F.value in metric_set)

            sys_set = set(config.get("systems") or [])
            self.system_gps.setChecked(GnssSystem.GPS.value in sys_set)
            self.system_glo.setChecked(GnssSystem.GLO.value in sys_set)
            self.system_gal.setChecked(GnssSystem.GAL.value in sys_set)
            self.system_bds.setChecked(GnssSystem.BDS.value in sys_set)

            self.exp_sigma.setChecked(bool(config.get("enable_experimental_sigma_phi_f", False)))
            self.exp_1s.setChecked(bool(config.get("enable_1s_resample", False)))
            self.enable_nav.setChecked(bool(config.get("enable_nav_fallback", False)))

            if isinstance(config.get("algorithm_config"), dict) and config.get("algorithm_config"):
                self.default_algorithm_config = dict(config.get("algorithm_config") or {})

            threshold_cfg = config.get("threshold_config") or []
            if threshold_cfg:
                merged: dict = dict(self.threshold_presets)
                for row in threshold_cfg:
                    metric = row.get("metric")
                    if not metric:
                        continue
                    merged[metric] = {
                        "value": row.get("value"),
                        "unit": row.get("unit"),
                        "source": row.get("source") or ThresholdSource.TEMPLATE.value,
                    }
                self.threshold_presets = merged
        finally:
            self._updating_form = False

        parameter_source = str(config.get("parameter_source") or "template")
        threshold_source = str(config.get("threshold_source") or "template")
        self._set_sources(parameter_source, threshold_source, template_id or config.get("source_template_id"))

    def _apply_selected_template(self) -> None:
        template_id = self.template_combo.currentData()
        if not template_id:
            QMessageBox.warning(self, "Warn", "请先选择模板")
            return

        rsp = self.bus.dispatch(channels.TEMPLATE_GET, {"templateId": template_id})
        if not rsp.success:
            QMessageBox.warning(self, "Warn", rsp.error.message if rsp.error else "模板加载失败")
            return

        payload = rsp.data.get("payload") or {}
        config = payload.get("config") if isinstance(payload, dict) else None
        if not isinstance(config, dict):
            QMessageBox.warning(self, "Warn", "模板中缺少 config 配置")
            return

        self._apply_config_to_form(config, template_id=template_id)
        QMessageBox.information(self, "Template", f"已应用模板: {template_id}")

    def _save_as_template(self) -> None:
        name = self.template_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Warn", "请先填写模板名")
            return

        payload = {
            "name": name,
            "scope": "TASK",
            "description": "Saved from data calculation page",
            "overwriteStrategy": self.overwrite_combo.currentText(),
            "payload": {
                "config": self._build_config(),
            },
        }
        rsp = self.bus.dispatch(channels.TEMPLATE_SAVE, payload)
        if not rsp.success:
            QMessageBox.warning(self, "Warn", rsp.error.message if rsp.error else "模板保存失败")
            return

        saved = rsp.data or {}
        template_id = saved.get("id")
        if template_id:
            self.source_template_id = template_id
            self._refresh_templates()
            idx = self.template_combo.findData(template_id)
            if idx >= 0:
                self.template_combo.setCurrentIndex(idx)
        QMessageBox.information(self, "Template", f"模板已保存: {saved.get('name')} ({saved.get('id')})")

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
            f"providerSummary={provider_summary.get('providerSummaryText')}",
            f"riskFlags={risk_flags}",
            f"sources=parameter:{self.parameter_source},threshold:{self.threshold_source},template:{self.source_template_id}",
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
                "templateId": self.source_template_id,
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
        p = float(event.get("progress", 0.0))
        self.progress.setValue(int(p * 100))

    def _on_log(self, event: dict) -> None:
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
