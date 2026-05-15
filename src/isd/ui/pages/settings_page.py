from __future__ import annotations

import json

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
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from isd.application import channels
from isd.application.command_bus import CommandBus
from isd.ui.i18n import LanguageManager, tr


class SettingsPage(QWidget):
    def __init__(self, bus: CommandBus) -> None:
        super().__init__()
        self.bus = bus
        self._lm = LanguageManager.instance()
        self._settings: dict = {}

        self._build_ui()
        self.load()
        self._lm.language_changed.connect(self._retranslate)

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)

        self.title_label = QLabel(tr("set.title"))
        self.title_label.setStyleSheet("""
            font-size: 22px;
            font-weight: bold;
            color: #00e5ff;
            margin: 10px 0;
        """)
        layout.addWidget(self.title_label)

        self._basic_box = self._build_basic_section()
        self._algo_box = self._build_algo_section()
        self._dixsg_box = self._build_dixsg_section()
        self._cs_box = self._build_cycle_slip_section()
        self._threshold_box = self._build_threshold_section()
        self._action_widget = self._build_action_section()

        layout.addWidget(self._basic_box)
        layout.addWidget(self._algo_box)
        layout.addWidget(self._dixsg_box)
        layout.addWidget(self._cs_box)
        layout.addWidget(self._threshold_box)
        layout.addWidget(self._action_widget)

        scroll.setWidget(content)
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(scroll)

    def _build_basic_section(self) -> QGroupBox:
        box = QGroupBox(tr("set.basic"))

        self.enable_nav = QCheckBox(tr("set.enable_nav"))
        self.enable_resample = QCheckBox(tr("set.enable_resample"))
        self.non_gps_sigma = QCheckBox("启用非GPS σϕf 实验模式")
        self.rinex_policy = QComboBox()
        self.rinex_policy.addItems(["WARNING", "BLOCK"])

        self.default_output = QLineEdit("workspace/outputs")
        self.cutoff_edit = QLineEdit("30")
        self.roti_window_edit = QLineEdit("5")

        self._basic_form_labels = []
        form = QFormLayout()
        form.setVerticalSpacing(10)
        lbl = QLabel(tr("set.default_output"))
        self._basic_form_labels.append(("set.default_output", lbl))
        form.addRow(lbl, self.default_output)
        lbl2 = QLabel(tr("set.cutoff"))
        self._basic_form_labels.append(("set.cutoff", lbl2))
        form.addRow(lbl2, self.cutoff_edit)
        lbl3 = QLabel(tr("set.roti_window"))
        self._basic_form_labels.append(("set.roti_window", lbl3))
        form.addRow(lbl3, self.roti_window_edit)
        form.addRow("", self.enable_nav)
        form.addRow("", self.enable_resample)
        form.addRow("", self.non_gps_sigma)
        form.addRow("RINEX近似坐标策略", self.rinex_policy)

        v_layout = QVBoxLayout(box)
        v_layout.addLayout(form)
        return box

    def _build_algo_section(self) -> QGroupBox:
        box = QGroupBox(tr("set.algo"))

        self.sigma_window_edit = QLineEdit("5")
        self.bw_order_edit = QLineEdit("6")
        self.bw_low_edit = QLineEdit("0.001")
        self.bw_high_edit = QLineEdit("0.015")

        self._algo_form_labels = []
        form = QFormLayout()
        form.setVerticalSpacing(10)
        for key, widget in [
            ("set.sigma_window", self.sigma_window_edit),
            ("set.bw_order", self.bw_order_edit),
            ("set.bw_low", self.bw_low_edit),
            ("set.bw_high", self.bw_high_edit),
        ]:
            lbl = QLabel(tr(key))
            self._algo_form_labels.append((key, lbl))
            form.addRow(lbl, widget)

        v_layout = QVBoxLayout(box)
        v_layout.addLayout(form)
        return box

    def _build_dixsg_section(self) -> QGroupBox:
        box = QGroupBox(tr("set.dixsg"))

        self.dixsg_levels_edit = QLineEdit("8")
        self.dixsg_first_edit = QLineEdit("50")
        self.dixsg_step_edit = QLineEdit("50")
        self.dixsg_max_dist_edit = QLineEdit("1000")
        self.dixsg_grid_size_edit = QLineEdit("1.0")
        self.dixsg_lat_range_edit = QLineEdit("-90,90")
        self.dixsg_lon_range_edit = QLineEdit("-180,180")

        self._dixsg_form_labels = []
        form = QFormLayout()
        form.setVerticalSpacing(10)
        for key, widget in [
            ("set.dixsg.levels", self.dixsg_levels_edit),
            ("set.dixsg.first", self.dixsg_first_edit),
            ("set.dixsg.step", self.dixsg_step_edit),
            ("set.dixsg.max_dist", self.dixsg_max_dist_edit),
            ("set.dixsg.grid", self.dixsg_grid_size_edit),
            ("set.dixsg.lat", self.dixsg_lat_range_edit),
            ("set.dixsg.lon", self.dixsg_lon_range_edit),
        ]:
            lbl = QLabel(tr(key))
            self._dixsg_form_labels.append((key, lbl))
            form.addRow(lbl, widget)

        v_layout = QVBoxLayout(box)
        v_layout.addLayout(form)
        return box

    def _build_cycle_slip_section(self) -> QGroupBox:
        box = QGroupBox(tr("set.cycle_slip"))

        self.cs_window_edit = QLineEdit("30")
        self.cs_gf_factor_edit = QLineEdit("4.0")
        self.cs_hmw_factor_edit = QLineEdit("5.0")
        self.cs_min_obs_edit = QLineEdit("5")
        self.min_arc_edit = QLineEdit("10")

        self._cs_form_labels = []
        form = QFormLayout()
        form.setVerticalSpacing(10)
        for key, widget in [
            ("set.cs.window", self.cs_window_edit),
            ("set.cs.gf", self.cs_gf_factor_edit),
            ("set.cs.hmw", self.cs_hmw_factor_edit),
            ("set.cs.min_obs", self.cs_min_obs_edit),
            ("set.cs.min_arc", self.min_arc_edit),
        ]:
            lbl = QLabel(tr(key))
            self._cs_form_labels.append((key, lbl))
            form.addRow(lbl, widget)

        v_layout = QVBoxLayout(box)
        v_layout.addLayout(form)
        return box

    def _build_threshold_section(self) -> QGroupBox:
        box = QGroupBox(tr("set.threshold"))

        self._threshold_hint = QLabel(
            'JSON: {"ROTI": {"value": 0.5, "unit": "TECU/min"}}'
        )
        self._threshold_hint.setStyleSheet("color: #8b9bb4; font-size: 11px;")

        self.threshold_text = QTextEdit()
        self.threshold_text.setMaximumHeight(120)
        self.threshold_text.setPlaceholderText('{"ROTI": {"value": 0.5, "unit": "TECU/min"}}')

        v_layout = QVBoxLayout(box)
        v_layout.addWidget(self._threshold_hint)
        v_layout.addWidget(self.threshold_text)
        return box

    def _build_action_section(self) -> QWidget:
        widget = QWidget()
        btn_layout = QHBoxLayout()

        self.load_btn = QPushButton(tr("set.btn.load"))
        self.load_btn.clicked.connect(self.load)
        self.load_btn.setProperty("secondary", "true")

        self.save_btn = QPushButton(tr("set.btn.save"))
        self.save_btn.clicked.connect(self.save)

        self.reset_btn = QPushButton(tr("set.btn.reset"))
        self.reset_btn.clicked.connect(self._reset)
        self.reset_btn.setProperty("secondary", "true")

        btn_layout.addWidget(self.load_btn)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.reset_btn)
        btn_layout.addStretch()

        layout = QVBoxLayout(widget)
        layout.addLayout(btn_layout)
        return widget

    def _retranslate(self) -> None:
        self.title_label.setText(tr("set.title"))
        self._basic_box.setTitle(tr("set.basic"))
        self._algo_box.setTitle(tr("set.algo"))
        self._dixsg_box.setTitle(tr("set.dixsg"))
        self._cs_box.setTitle(tr("set.cycle_slip"))
        self._threshold_box.setTitle(tr("set.threshold"))
        self.load_btn.setText(tr("set.btn.load"))
        self.save_btn.setText(tr("set.btn.save"))
        self.reset_btn.setText(tr("set.btn.reset"))
        self.enable_nav.setText(tr("set.enable_nav"))
        self.enable_resample.setText(tr("set.enable_resample"))
        self.non_gps_sigma.setText(tr("set.enable_non_gps_sigma"))

        for labels_list in (self._basic_form_labels, self._algo_form_labels,
                            self._dixsg_form_labels, self._cs_form_labels):
            for key, lbl in labels_list:
                lbl.setText(tr(key))

    def _reset(self) -> None:
        self.enable_nav.setChecked(False)
        self.enable_resample.setChecked(False)
        self.non_gps_sigma.setChecked(False)
        self.rinex_policy.setCurrentIndex(0)
        self.default_output.setText("workspace/outputs")
        self.cutoff_edit.setText("30")
        self.roti_window_edit.setText("5")
        self.sigma_window_edit.setText("5")
        self.bw_order_edit.setText("6")
        self.bw_low_edit.setText("0.001")
        self.bw_high_edit.setText("0.015")
        self.dixsg_levels_edit.setText("8")
        self.dixsg_first_edit.setText("50")
        self.dixsg_step_edit.setText("50")
        self.dixsg_max_dist_edit.setText("1000")
        self.dixsg_grid_size_edit.setText("1.0")
        self.dixsg_lat_range_edit.setText("-90,90")
        self.dixsg_lon_range_edit.setText("-180,180")
        self.cs_window_edit.setText("30")
        self.cs_gf_factor_edit.setText("4.0")
        self.cs_hmw_factor_edit.setText("5.0")
        self.cs_min_obs_edit.setText("5")
        self.min_arc_edit.setText("10")
        self.threshold_text.clear()

    def load(self) -> None:
        rsp = self.bus.dispatch(channels.SETTINGS_GET, {})
        if not rsp.success:
            return
        cfg = rsp.data or {}
        self._settings = cfg

        self.enable_nav.setChecked(bool(cfg.get("enableNavDegradedMode", False)))
        self.enable_resample.setChecked(bool(cfg.get("enableExperimental1sResample", False)))
        self.non_gps_sigma.setChecked(bool(cfg.get("enableNonGpsSigmaPhiF", False)))
        rinex_pol = str(cfg.get("rinexApproxSigmaPhiFPolicy", "WARNING")).upper()
        idx = self.rinex_policy.findText(rinex_pol)
        self.rinex_policy.setCurrentIndex(idx if idx >= 0 else 0)
        self.default_output.setText(str(cfg.get("defaultOutputPath", "workspace/outputs")))

        algo = cfg.get("defaultAlgorithmConfig") or {}
        self.cutoff_edit.setText(str(algo.get("cutoffElevationDeg", 30)))
        self.roti_window_edit.setText(str(algo.get("rotiWindowMin", 5)))
        self.sigma_window_edit.setText(str(algo.get("sigmaPhiFWindowMin", 5)))
        self.bw_order_edit.setText(str(algo.get("butterworthOrder", 6)))
        self.bw_low_edit.setText(str(algo.get("butterworthLowHz", 0.001)))
        self.bw_high_edit.setText(str(algo.get("butterworthHighHz", 0.015)))

        dixsg = algo.get("dixsgConfig") or {}
        self.dixsg_levels_edit.setText(str(dixsg.get("sensitivityLevels", algo.get("dixsgSensitivityLevels", 8))))
        self.dixsg_first_edit.setText(str(dixsg.get("sensitivityFirst", algo.get("dixsgSensitivityFirst", 50))))
        self.dixsg_step_edit.setText(str(dixsg.get("sensitivityStep", algo.get("dixsgSensitivityStep", 50))))
        self.dixsg_max_dist_edit.setText(str(dixsg.get("maxDistanceKm", algo.get("dixsgMaxDistanceKm", 1000))))
        self.dixsg_grid_size_edit.setText(str(dixsg.get("gridSizeDeg", algo.get("dixsgGridSizeDeg", 1.0))))
        lat_range = dixsg.get("latRange", [-90, 90])
        lon_range = dixsg.get("lonRange", [-180, 180])
        self.dixsg_lat_range_edit.setText(f"{lat_range[0]},{lat_range[1]}" if isinstance(lat_range, list) else "-90,90")
        self.dixsg_lon_range_edit.setText(f"{lon_range[0]},{lon_range[1]}" if isinstance(lon_range, list) else "-180,180")

        cs = algo.get("cycleSlipConfig") or {}
        self.cs_window_edit.setText(str(cs.get("windowSize", algo.get("cycleSlipWindow", 30))))
        self.cs_gf_factor_edit.setText(str(cs.get("gfThresholdFactor", algo.get("gfThresholdFactor", 4.0))))
        self.cs_hmw_factor_edit.setText(str(cs.get("hmwThresholdFactor", algo.get("hmwThresholdFactor", 5.0))))
        self.cs_min_obs_edit.setText(str(cs.get("minObsForStats", 5)))
        self.min_arc_edit.setText(str(algo.get("minArcEpochs", 10)))

        thresholds = cfg.get("thresholdPresets") or {}
        self.threshold_text.setPlainText(json.dumps(thresholds, ensure_ascii=False, indent=2))

    def save(self) -> None:
        try:
            threshold_presets = json.loads(self.threshold_text.toPlainText().strip() or "{}")
        except Exception as exc:
            QMessageBox.warning(self, tr("dlg.warning"), f"JSON error: {exc}")
            return

        try:
            lat_text = self.dixsg_lat_range_edit.text().strip()
            lon_text = self.dixsg_lon_range_edit.text().strip()
            lat_parts = [float(x.strip()) for x in lat_text.split(",")]
            lon_parts = [float(x.strip()) for x in lon_text.split(",")]
            if len(lat_parts) != 2 or len(lon_parts) != 2:
                raise ValueError("Lat/lon range needs two comma-separated values")

            payload = {
                "enableNavDegradedMode": self.enable_nav.isChecked(),
                "enableExperimental1sResample": self.enable_resample.isChecked(),
                "enableNonGpsSigmaPhiF": self.non_gps_sigma.isChecked(),
                "rinexApproxSigmaPhiFPolicy": self.rinex_policy.currentText(),
                "defaultOutputPath": self.default_output.text().strip() or "workspace/outputs",
                "defaultAlgorithmConfig": {
                    "cutoffElevationDeg": float(self.cutoff_edit.text().strip()),
                    "minArcEpochs": int(float(self.min_arc_edit.text().strip())),
                    "rotiWindowMin": int(float(self.roti_window_edit.text().strip())),
                    "sigmaPhiFWindowMin": int(float(self.sigma_window_edit.text().strip())),
                    "butterworthOrder": int(float(self.bw_order_edit.text().strip())),
                    "butterworthLowHz": float(self.bw_low_edit.text().strip()),
                    "butterworthHighHz": float(self.bw_high_edit.text().strip()),
                    "dixsgConfig": {
                        "sensitivityLevels": int(float(self.dixsg_levels_edit.text().strip())),
                        "sensitivityFirst": float(self.dixsg_first_edit.text().strip()),
                        "sensitivityStep": float(self.dixsg_step_edit.text().strip()),
                        "maxDistanceKm": float(self.dixsg_max_dist_edit.text().strip()),
                        "gridSizeDeg": float(self.dixsg_grid_size_edit.text().strip()),
                        "latRange": lat_parts,
                        "lonRange": lon_parts,
                    },
                    "cycleSlipConfig": {
                        "windowSize": int(float(self.cs_window_edit.text().strip())),
                        "gfThresholdFactor": float(self.cs_gf_factor_edit.text().strip()),
                        "hmwThresholdFactor": float(self.cs_hmw_factor_edit.text().strip()),
                        "minObsForStats": int(float(self.cs_min_obs_edit.text().strip())),
                    },
                },
                "thresholdPresets": threshold_presets,
            }
        except Exception as exc:
            QMessageBox.warning(self, tr("dlg.warning"), f"Parameter error: {exc}")
            return

        rsp = self.bus.dispatch(channels.SETTINGS_UPDATE, payload)
        if rsp.success:
            self._settings = rsp.data or {}
            QMessageBox.information(self, tr("dlg.success"), tr("set.btn.save"))
        else:
            QMessageBox.warning(self, tr("dlg.warning"), rsp.error.message if rsp.error else "Save failed")
