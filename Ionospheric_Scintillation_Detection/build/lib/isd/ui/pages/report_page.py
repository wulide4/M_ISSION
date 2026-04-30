from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from isd.application import channels
from isd.application.command_bus import CommandBus
from isd.application.risk_flags import risk_flags_to_text


class ReportCenterPage(QWidget):
    def __init__(self, bus: CommandBus) -> None:
        super().__init__()
        self.bus = bus

        self.project_id_edit = QLineEdit()
        self.template_edit = QLineEdit("default_template")
        self.result_ids_edit = QLineEdit()
        self.title_edit = QLineEdit("Scintillation Report")
        self.output_edit = QLineEdit("workspace/reports/report_demo.pdf")

        self.include_param_snapshot = QCheckBox("包含参数快照")
        self.include_param_snapshot.setChecked(True)
        self.include_log_summary = QCheckBox("包含日志摘要")
        self.include_log_summary.setChecked(True)
        self.include_non_gps_sigma = QCheckBox("报告纳入非GPS SIGMA_PHI_F（实验项）")
        self.include_non_gps_sigma.setChecked(False)

        self.preview_box = QTextEdit()
        self.preview_box.setReadOnly(True)
        self.result_picker = QListWidget()
        self.result_picker.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.result_picker.itemSelectionChanged.connect(self._sync_selected_result_ids)

        self.risk_hint = QLabel("报告风险标识: N/A")
        self.state_hint = QLabel("状态[IDLE] 等待操作")

        form = QFormLayout()
        form.addRow("projectId", self.project_id_edit)
        form.addRow("templateId", self.template_edit)
        form.addRow("resultIds(csv)", self.result_ids_edit)
        form.addRow("title", self.title_edit)
        form.addRow("outputPath", self.output_edit)
        form.addRow(self.include_param_snapshot)
        form.addRow(self.include_log_summary)
        form.addRow(self.include_non_gps_sigma)

        load_templates_btn = QPushButton("加载模板")
        load_templates_btn.clicked.connect(self.load_templates)
        load_results_btn = QPushButton("加载项目结果")
        load_results_btn.clicked.connect(self.load_project_results)
        preview_btn = QPushButton("预览")
        preview_btn.clicked.connect(self.preview)
        export_btn = QPushButton("导出")
        export_btn.clicked.connect(self.export)
        browse_btn = QPushButton("选择导出文件")
        browse_btn.clicked.connect(self.browse)

        row = QHBoxLayout()
        row.addWidget(load_templates_btn)
        row.addWidget(load_results_btn)
        row.addWidget(browse_btn)
        row.addWidget(preview_btn)
        row.addWidget(export_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>报告中心</h2>"))
        layout.addLayout(form)
        layout.addLayout(row)
        layout.addWidget(self.state_hint)
        layout.addWidget(self.risk_hint)
        layout.addWidget(QLabel("项目结果选择（可多选）"))
        layout.addWidget(self.result_picker)
        layout.addWidget(self.preview_box)

    def _set_state(self, state: str, text: str) -> None:
        self.state_hint.setText(f"状态[{state}] {text}")

    def _payload(self) -> dict:
        ids = [x.strip() for x in self.result_ids_edit.text().split(",") if x.strip()]
        return {
            "projectId": self.project_id_edit.text().strip() or None,
            "templateId": self.template_edit.text().strip(),
            "resultIds": ids,
            "options": {
                "title": self.title_edit.text().strip(),
                "includeParameterSnapshot": self.include_param_snapshot.isChecked(),
                "includeLogSummary": self.include_log_summary.isChecked(),
                "includeNonGpsSigmaPhiF": self.include_non_gps_sigma.isChecked(),
            },
        }

    def browse(self) -> None:
        p, _ = QFileDialog.getSaveFileName(
            self,
            "导出报告",
            self.output_edit.text(),
            "PDF (*.pdf);;Text (*.txt)",
        )
        if p:
            self.output_edit.setText(p)

    def load_templates(self) -> None:
        rsp = self.bus.dispatch(channels.REPORT_LIST_TEMPLATES, {})
        if not rsp.success:
            QMessageBox.warning(self, "warn", rsp.error.message if rsp.error else "load templates failed")
            self._set_state("LOAD_FAILED", "加载模板失败")
            return
        templates = rsp.data or []
        if not templates:
            self._set_state("READY", "模板列表为空，保持默认模板")
            return

        self.template_edit.setText(templates[0].get("id", "default_template"))
        self._set_state("READY", f"模板数量: {len(templates)}")
        QMessageBox.information(self, "ok", f"模板数量: {len(templates)}，默认使用 {self.template_edit.text()}")

    def load_project_results(self) -> None:
        project_id = self.project_id_edit.text().strip()
        if not project_id:
            QMessageBox.warning(self, "warn", "请先填写 projectId")
            return

        rsp = self.bus.dispatch(channels.RESULT_LIST, {"projectId": project_id})
        if not rsp.success:
            QMessageBox.warning(self, "warn", rsp.error.message if rsp.error else "load results failed")
            self._set_state("LOAD_FAILED", "加载项目结果失败")
            return

        self.result_picker.clear()
        for row in rsp.data or []:
            rid = row.get("id", "")
            metric = row.get("metric", "-")
            station = row.get("station_id") or "-"
            label = f"{metric} | {station} | {rid}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, rid)
            self.result_picker.addItem(item)

        self._sync_selected_result_ids()
        self._set_state("READY", f"已加载结果 {self.result_picker.count()} 条")
        QMessageBox.information(self, "ok", f"已加载结果数量: {self.result_picker.count()}")

    def _sync_selected_result_ids(self) -> None:
        selected = []
        for item in self.result_picker.selectedItems():
            rid = item.data(Qt.ItemDataRole.UserRole)
            if rid:
                selected.append(str(rid))
        self.result_ids_edit.setText(",".join(selected))

    def preview(self) -> None:
        self._set_state("PREVIEW_LOADING", "正在生成预览")
        rsp = self.bus.dispatch(channels.REPORT_PREVIEW, self._payload())
        if not rsp.success:
            QMessageBox.warning(self, "warn", rsp.error.message if rsp.error else "preview failed")
            self._set_state("PREVIEW_FAILED", rsp.error.message if rsp.error else "预览失败")
            return

        data = rsp.data or {}
        risk_flags = data.get("summary", {}).get("riskFlags", []) or []
        self.risk_hint.setText(f"报告风险标识: {risk_flags_to_text(risk_flags)}")
        self.preview_box.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
        self._set_state("PREVIEW_READY", f"预览结果数量: {data.get('summary', {}).get('resultCount', 0)}")

    def export(self) -> None:
        payload = self._payload()
        payload["outputPath"] = self.output_edit.text().strip()
        self._set_state("EXPORTING", "正在导出报告")

        rsp = self.bus.dispatch(channels.REPORT_EXPORT, payload)
        if not rsp.success:
            QMessageBox.warning(self, "warn", rsp.error.message if rsp.error else "export failed")
            self._set_state("EXPORT_FAILED", rsp.error.message if rsp.error else "导出失败")
            return

        out = rsp.data.get("outputPath")
        exists = Path(out).exists() if out else False
        warning = rsp.data.get("warning")
        format_name = rsp.data.get("format", "TEXT")
        fallback_used = bool(rsp.data.get("fallbackUsed"))

        message = f"Exported: {out}\nexists={exists}\nformat={format_name}\nfallbackUsed={fallback_used}"
        if warning:
            message += f"\nwarning={warning}"

        self._set_state("EXPORT_SUCCESS", f"导出完成（{format_name}）")
        QMessageBox.information(self, "ok", message)
