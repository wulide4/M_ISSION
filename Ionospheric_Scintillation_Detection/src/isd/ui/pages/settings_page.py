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


class SettingsPage(QWidget):
    def __init__(self, bus: CommandBus) -> None:
        super().__init__()
        self.bus = bus
        self._settings: dict = {}

        self._build_ui()
        self.load()

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)

        title = QLabel("系统设置")
        title.setStyleSheet("""
            font-size: 22px;
            font-weight: bold;
            color: #00e5ff;
            margin: 10px 0;
        """)
        layout.addWidget(title)

        layout.addWidget(self._build_basic_section())
        layout.addWidget(self._build_algo_section())
        layout.addWidget(self._build_dixsg_section())
        layout.addWidget(self._build_cycle_slip_section())
        layout.addWidget(self._build_threshold_section())
        layout.addWidget(self._build_action_section())

        scroll.setWidget(content)
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(scroll)

    def _build_basic_section(self) -> QGroupBox:
        box = QGroupBox("基本参数")

        self.enable_nav = QCheckBox("启用NAV降级模式")
        self.enable_resample = QCheckBox("启用1s重采样")

        self.default_output = QLineEdit("workspace/outputs")
        self.cutoff_edit = QLineEdit("30")
        self.roti_window_edit = QLineEdit("5")

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.addRow("默认输出路径", self.default_output)
        form.addRow("截止高度角(°)", self.cutoff_edit)
        form.addRow("ROTI窗口(min)", self.roti_window_edit)
        form.addRow("", self.enable_nav)
        form.addRow("", self.enable_resample)

        v_layout = QVBoxLayout(box)
        v_layout.addLayout(form)

        return box

    def _build_algo_section(self) -> QGroupBox:
        box = QGroupBox("算法参数")

        self.sigma_window_edit = QLineEdit("5")
        self.bw_order_edit = QLineEdit("6")
        self.bw_low_edit = QLineEdit("0.001")
        self.bw_high_edit = QLineEdit("0.015")

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.addRow("σφf窗口(min)", self.sigma_window_edit)
        form.addRow("Butterworth阶数", self.bw_order_edit)
        form.addRow("低频截止(Hz)", self.bw_low_edit)
        form.addRow("高频截止(Hz)", self.bw_high_edit)

        v_layout = QVBoxLayout(box)
        v_layout.addLayout(form)

        return box

    def _build_dixsg_section(self) -> QGroupBox:
        box = QGroupBox("DIXSG参数 (空间梯度扰动指数)")

        self.dixsg_levels_edit = QLineEdit("8")
        self.dixsg_first_edit = QLineEdit("50")
        self.dixsg_step_edit = QLineEdit("50")
        self.dixsg_max_dist_edit = QLineEdit("1000")
        self.dixsg_grid_size_edit = QLineEdit("1.0")
        self.dixsg_lat_range_edit = QLineEdit("-90,90")
        self.dixsg_lon_range_edit = QLineEdit("-180,180")

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.addRow("灵敏度等级数", self.dixsg_levels_edit)
        form.addRow("起始灵敏度", self.dixsg_first_edit)
        form.addRow("灵敏度步长", self.dixsg_step_edit)
        form.addRow("最大基线距离(km)", self.dixsg_max_dist_edit)
        form.addRow("网格大小(°)", self.dixsg_grid_size_edit)
        form.addRow("纬度范围", self.dixsg_lat_range_edit)
        form.addRow("经度范围", self.dixsg_lon_range_edit)

        v_layout = QVBoxLayout(box)
        v_layout.addLayout(form)

        return box

    def _build_cycle_slip_section(self) -> QGroupBox:
        box = QGroupBox("周跳检测参数 (TurboEdit)")

        self.cs_window_edit = QLineEdit("30")
        self.cs_gf_factor_edit = QLineEdit("4.0")
        self.cs_hmw_factor_edit = QLineEdit("5.0")
        self.cs_min_obs_edit = QLineEdit("5")
        self.min_arc_edit = QLineEdit("10")

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.addRow("检测窗口(历元)", self.cs_window_edit)
        form.addRow("GF阈值因子", self.cs_gf_factor_edit)
        form.addRow("HMW阈值因子 (×σ)", self.cs_hmw_factor_edit)
        form.addRow("最小统计样本数", self.cs_min_obs_edit)
        form.addRow("最短弧段(历元)", self.min_arc_edit)

        v_layout = QVBoxLayout(box)
        v_layout.addLayout(form)

        return box

    def _build_threshold_section(self) -> QGroupBox:
        box = QGroupBox("阈值配置")

        hint = QLabel("JSON格式，如: {\"ROTI\": {\"value\": 0.5, \"unit\": \"TECU/min\"}}")
        hint.setStyleSheet("color: #8b9bb4; font-size: 11px;")

        self.threshold_text = QTextEdit()
        self.threshold_text.setMaximumHeight(120)
        self.threshold_text.setPlaceholderText('{"ROTI": {"value": 0.5, "unit": "TECU/min"}}')

        v_layout = QVBoxLayout(box)
        v_layout.addWidget(hint)
        v_layout.addWidget(self.threshold_text)

        return box

    def _build_action_section(self) -> QWidget:
        widget = QWidget()

        btn_layout = QHBoxLayout()

        load_btn = QPushButton("加载")
        load_btn.clicked.connect(self.load)
        load_btn.setProperty("secondary", "true")

        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.save)

        reset_btn = QPushButton("重置")
        reset_btn.clicked.connect(self._reset)
        reset_btn.setProperty("secondary", "true")

        btn_layout.addWidget(load_btn)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(reset_btn)
        btn_layout.addStretch()

        layout = QVBoxLayout(widget)
        layout.addLayout(btn_layout)

        return widget

    def _reset(self) -> None:
        self.enable_nav.setChecked(False)
        self.enable_resample.setChecked(False)
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
        self.default_output.setText(str(cfg.get("defaultOutputPath", "workspace/outputs")))

        algo = cfg.get("defaultAlgorithmConfig") or {}
        self.cutoff_edit.setText(str(algo.get("cutoffElevationDeg", 30)))
        self.roti_window_edit.setText(str(algo.get("rotiWindowMin", 5)))
        self.sigma_window_edit.setText(str(algo.get("sigmaPhiFWindowMin", 5)))
        self.bw_order_edit.setText(str(algo.get("butterworthOrder", 6)))
        self.bw_low_edit.setText(str(algo.get("butterworthLowHz", 0.001)))
        self.bw_high_edit.setText(str(algo.get("butterworthHighHz", 0.015)))

        # DIXSG parameters
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

        # Cycle slip parameters
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
            QMessageBox.warning(self, "警告", f"JSON格式错误: {exc}")
            return

        try:
            # Parse lat/lon ranges
            lat_text = self.dixsg_lat_range_edit.text().strip()
            lon_text = self.dixsg_lon_range_edit.text().strip()
            lat_parts = [float(x.strip()) for x in lat_text.split(",")]
            lon_parts = [float(x.strip()) for x in lon_text.split(",")]
            if len(lat_parts) != 2 or len(lon_parts) != 2:
                raise ValueError("纬度/经度范围需要两个值，用逗号分隔")

            payload = {
                "enableNavDegradedMode": self.enable_nav.isChecked(),
                "enableExperimental1sResample": self.enable_resample.isChecked(),
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
            QMessageBox.warning(self, "警告", f"参数格式错误: {exc}")
            return

        rsp = self.bus.dispatch(channels.SETTINGS_UPDATE, payload)
        if rsp.success:
            self._settings = rsp.data or {}
            QMessageBox.information(self, "成功", "设置已保存")
        else:
            QMessageBox.warning(self, "警告", rsp.error.message if rsp.error else "保存失败")
