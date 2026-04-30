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
    QListWidget,
    QMessageBox,
    QPushButton,
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

        self.non_gps_sigma = QCheckBox("启用非GPS σϕf实验模式")
        self.experimental_1s = QCheckBox("启用1s实验降采样")
        self.nav_degraded = QCheckBox("启用NAV工程降级模式")

        self.rinex_policy = QComboBox()
        self.rinex_policy.addItems(["WARNING", "BLOCK"])
        self.default_output_path = QLineEdit("workspace/outputs")

        self.cutoff_edit = QLineEdit("30")
        self.min_arc_edit = QLineEdit("10")
        self.roti_window_edit = QLineEdit("5")
        self.sigma_window_edit = QLineEdit("5")
        self.bw_order_edit = QLineEdit("6")
        self.bw_low_edit = QLineEdit("0.001")
        self.bw_high_edit = QLineEdit("0.015")

        self.threshold_text = QTextEdit()
        self.threshold_text.setPlaceholderText('{"ROTI": {"value": 0.5, "unit": "TECU/min", "source": "LITERATURE_REFERENCE"}}')

        self.receiver_list = QListWidget()
        self.receiver_list.itemClicked.connect(self._on_receiver_selected)
        self.receiver_name_edit = QLineEdit()
        self.receiver_threshold_text = QTextEdit()
        self.receiver_threshold_text.setPlaceholderText('{"ROTI": 0.5, "AATR": 0.2}')

        load_btn = QPushButton("加载")
        load_btn.clicked.connect(self.load)
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.save)

        receiver_load_btn = QPushButton("读取接收机预设")
        receiver_load_btn.clicked.connect(self._load_receiver_preset)
        receiver_save_btn = QPushButton("保存接收机预设")
        receiver_save_btn.clicked.connect(self._save_receiver_preset)
        receiver_delete_btn = QPushButton("删除接收机预设")
        receiver_delete_btn.clicked.connect(self._delete_receiver_preset)

        system_form = QFormLayout()
        system_form.addRow(self.non_gps_sigma)
        system_form.addRow(self.experimental_1s)
        system_form.addRow(self.nav_degraded)
        system_form.addRow("RINEX近似坐标策略", self.rinex_policy)
        system_form.addRow("默认输出路径", self.default_output_path)

        algo_form = QFormLayout()
        algo_form.addRow("cutoffElevationDeg", self.cutoff_edit)
        algo_form.addRow("minArcEpochs", self.min_arc_edit)
        algo_form.addRow("rotiWindowMin", self.roti_window_edit)
        algo_form.addRow("sigmaPhiFWindowMin", self.sigma_window_edit)
        algo_form.addRow("butterworthOrder", self.bw_order_edit)
        algo_form.addRow("butterworthLowHz", self.bw_low_edit)
        algo_form.addRow("butterworthHighHz", self.bw_high_edit)

        system_box = QGroupBox("系统开关")
        system_box.setLayout(system_form)

        algo_box = QGroupBox("默认算法参数")
        algo_box.setLayout(algo_form)

        threshold_box = QGroupBox("阈值预设（JSON）")
        threshold_layout = QVBoxLayout(threshold_box)
        threshold_layout.addWidget(self.threshold_text)

        receiver_box = QGroupBox("接收机阈值预设管理")
        receiver_layout = QVBoxLayout(receiver_box)
        receiver_form = QFormLayout()
        receiver_form.addRow("receiverModel", self.receiver_name_edit)
        receiver_layout.addLayout(receiver_form)
        receiver_layout.addWidget(QLabel("receiverThresholds(JSON)"))
        receiver_layout.addWidget(self.receiver_threshold_text)
        receiver_btn_row = QHBoxLayout()
        receiver_btn_row.addWidget(receiver_load_btn)
        receiver_btn_row.addWidget(receiver_save_btn)
        receiver_btn_row.addWidget(receiver_delete_btn)
        receiver_layout.addLayout(receiver_btn_row)
        receiver_layout.addWidget(QLabel("已保存接收机预设"))
        receiver_layout.addWidget(self.receiver_list)

        action_row = QHBoxLayout()
        action_row.addWidget(load_btn)
        action_row.addWidget(save_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>系统设置</h2>"))
        layout.addWidget(system_box)
        layout.addWidget(algo_box)
        layout.addWidget(threshold_box)
        layout.addWidget(receiver_box)
        layout.addLayout(action_row)
        layout.addStretch(1)

        self.load()

    def load(self) -> None:
        rsp = self.bus.dispatch(channels.SETTINGS_GET, {})
        if not rsp.success:
            QMessageBox.warning(self, "warn", rsp.error.message if rsp.error else "加载设置失败")
            return
        cfg = rsp.data or {}
        self._settings = cfg

        self.non_gps_sigma.setChecked(bool(cfg.get("enableNonGpsSigmaPhiF", False)))
        self.experimental_1s.setChecked(bool(cfg.get("enableExperimental1sResample", False)))
        self.nav_degraded.setChecked(bool(cfg.get("enableNavDegradedMode", False)))

        rinex = str(cfg.get("rinexApproxSigmaPhiFPolicy", "WARNING")).upper()
        idx = self.rinex_policy.findText(rinex)
        self.rinex_policy.setCurrentIndex(idx if idx >= 0 else 0)

        self.default_output_path.setText(str(cfg.get("defaultOutputPath", "workspace/outputs")))

        algo = cfg.get("defaultAlgorithmConfig") or {}
        self.cutoff_edit.setText(str(algo.get("cutoffElevationDeg", 30)))
        self.min_arc_edit.setText(str(algo.get("minArcEpochs", 10)))
        self.roti_window_edit.setText(str(algo.get("rotiWindowMin", 5)))
        self.sigma_window_edit.setText(str(algo.get("sigmaPhiFWindowMin", 5)))
        self.bw_order_edit.setText(str(algo.get("butterworthOrder", 6)))
        self.bw_low_edit.setText(str(algo.get("butterworthLowHz", 0.001)))
        self.bw_high_edit.setText(str(algo.get("butterworthHighHz", 0.015)))

        thresholds = cfg.get("thresholdPresets") or {}
        self.threshold_text.setPlainText(json.dumps(thresholds, ensure_ascii=False, indent=2))
        self._refresh_receiver_list()

    def save(self) -> None:
        try:
            threshold_presets = json.loads(self.threshold_text.toPlainText().strip() or "{}")
            receiver_threshold_presets = self._settings.get("receiverThresholdPresets") or {}
            payload = {
                "enableNonGpsSigmaPhiF": self.non_gps_sigma.isChecked(),
                "enableExperimental1sResample": self.experimental_1s.isChecked(),
                "enableNavDegradedMode": self.nav_degraded.isChecked(),
                "rinexApproxSigmaPhiFPolicy": self.rinex_policy.currentText(),
                "defaultOutputPath": self.default_output_path.text().strip() or "workspace/outputs",
                "defaultAlgorithmConfig": {
                    "cutoffElevationDeg": float(self.cutoff_edit.text().strip()),
                    "minArcEpochs": int(float(self.min_arc_edit.text().strip())),
                    "rotiWindowMin": int(float(self.roti_window_edit.text().strip())),
                    "sigmaPhiFWindowMin": int(float(self.sigma_window_edit.text().strip())),
                    "butterworthOrder": int(float(self.bw_order_edit.text().strip())),
                    "butterworthLowHz": float(self.bw_low_edit.text().strip()),
                    "butterworthHighHz": float(self.bw_high_edit.text().strip()),
                },
                "thresholdPresets": threshold_presets,
                "receiverThresholdPresets": receiver_threshold_presets,
            }
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "warn", f"参数格式错误: {exc}")
            return

        rsp = self.bus.dispatch(channels.SETTINGS_UPDATE, payload)
        if rsp.success:
            self._settings = rsp.data or {}
            self._refresh_receiver_list()
            QMessageBox.information(self, "ok", "设置已保存")
        else:
            QMessageBox.warning(self, "warn", rsp.error.message if rsp.error else "保存失败")

    def _refresh_receiver_list(self) -> None:
        self.receiver_list.clear()
        presets = self._settings.get("receiverThresholdPresets") or {}
        for name in sorted(presets.keys()):
            self.receiver_list.addItem(name)

    def _on_receiver_selected(self) -> None:
        self._load_receiver_preset()

    def _load_receiver_preset(self) -> None:
        name = self.receiver_name_edit.text().strip()
        if not name and self.receiver_list.currentItem():
            name = self.receiver_list.currentItem().text().strip()
        if not name:
            QMessageBox.warning(self, "warn", "请先输入或选择 receiverModel")
            return

        presets = self._settings.get("receiverThresholdPresets") or {}
        payload = presets.get(name)
        if payload is None:
            QMessageBox.warning(self, "warn", f"未找到接收机预设: {name}")
            return

        self.receiver_name_edit.setText(name)
        self.receiver_threshold_text.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))

    def _save_receiver_preset(self) -> None:
        name = self.receiver_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "warn", "请先输入 receiverModel")
            return

        try:
            preset_payload = json.loads(self.receiver_threshold_text.toPlainText().strip() or "{}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "warn", f"JSON 解析失败: {exc}")
            return

        presets = dict(self._settings.get("receiverThresholdPresets") or {})
        presets[name] = preset_payload
        self._settings["receiverThresholdPresets"] = presets
        self._refresh_receiver_list()
        QMessageBox.information(self, "ok", f"接收机预设已写入缓存: {name}（点保存后落库）")

    def _delete_receiver_preset(self) -> None:
        name = self.receiver_name_edit.text().strip()
        if not name and self.receiver_list.currentItem():
            name = self.receiver_list.currentItem().text().strip()
        if not name:
            QMessageBox.warning(self, "warn", "请先选择要删除的 receiverModel")
            return

        presets = dict(self._settings.get("receiverThresholdPresets") or {})
        if name not in presets:
            QMessageBox.warning(self, "warn", f"预设不存在: {name}")
            return

        presets.pop(name, None)
        self._settings["receiverThresholdPresets"] = presets
        self.receiver_threshold_text.clear()
        self._refresh_receiver_list()
        QMessageBox.information(self, "ok", f"接收机预设已从缓存删除: {name}（点保存后落库）")
